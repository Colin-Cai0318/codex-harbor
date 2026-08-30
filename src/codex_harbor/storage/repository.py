from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ..domain import (
    ACTIVE_TASK_STATES,
    EffectiveAgentConfig,
    PoolStatus,
    QuotaWindow,
    TaskSpec,
    TaskStatus,
    ThreadRole,
    utc_now,
    validate_transition,
)
from .db import Database

UNSET = object()


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    result = dict(row)
    if "acceptance_commands" in result:
        result["acceptance_commands"] = json.loads(
            result["acceptance_commands"] or "[]"
        )
    return result


class HarborRepository:
    def __init__(self, database: Database):
        self.db = database

    def add_repository(self, path: str | Path) -> dict[str, Any]:
        resolved = Path(path).expanduser().resolve()
        if not resolved.is_dir():
            raise ValueError(f"repository does not exist: {resolved}")
        now = utc_now()
        with self.db.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO repositories(path, name, added_at) VALUES(?, ?, ?)",
                (str(resolved), resolved.name, now),
            )
        return {"path": str(resolved), "name": resolved.name, "added_at": now}

    def list_repositories(self) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            return [
                dict(row)
                for row in conn.execute("SELECT * FROM repositories ORDER BY added_at")
            ]

    def is_registered_repository(self, path: str | Path) -> bool:
        resolved = str(Path(path).expanduser().resolve())
        with self.db.connect() as conn:
            return (
                conn.execute(
                    "SELECT 1 FROM repositories WHERE path = ?", (resolved,)
                ).fetchone()
                is not None
            )

    def _next_task_id(self, conn: sqlite3.Connection) -> str:
        rows = conn.execute(
            "SELECT id FROM tasks WHERE id LIKE 'T%' ORDER BY id DESC"
        ).fetchall()
        maximum = 0
        for row in rows:
            suffix = row["id"][1:]
            if suffix.isdigit():
                maximum = max(maximum, int(suffix))
        return f"T{maximum + 1:03d}"

    def create_task(self, spec: TaskSpec) -> dict[str, Any]:
        repository = str(Path(spec.repository).expanduser().resolve())
        now = utc_now()
        with self.db.transaction(immediate=True) as conn:
            if (
                conn.execute(
                    "SELECT 1 FROM repositories WHERE path = ?", (repository,)
                ).fetchone()
                is None
            ):
                raise ValueError(
                    "repository is not registered; run 'harbor repo add' first"
                )
            task_id = spec.task_id or self._next_task_id(conn)
            if not task_id or any(
                char
                not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
                for char in task_id
            ):
                raise ValueError(
                    "task id may only contain letters, digits, underscore, and hyphen"
                )
            for dependency in spec.depends_on:
                if (
                    conn.execute(
                        "SELECT 1 FROM tasks WHERE id = ?", (dependency,)
                    ).fetchone()
                    is None
                ):
                    raise ValueError(f"unknown dependency: {dependency}")
            conn.execute(
                """INSERT INTO tasks(
                    id, title, description, repository, execution_backend, prompt, status,
                    priority, created_at, updated_at, max_attempts, acceptance_commands,
                    model, reasoning_effort, profile, exclusive_group
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task_id,
                    spec.title,
                    spec.description,
                    repository,
                    spec.execution_backend,
                    spec.prompt,
                    TaskStatus.CREATED,
                    spec.priority,
                    now,
                    now,
                    spec.max_attempts,
                    json.dumps(spec.acceptance_commands),
                    spec.model,
                    spec.reasoning_effort,
                    spec.profile,
                    spec.exclusive_group,
                ),
            )
            conn.executemany(
                "INSERT INTO task_dependencies(task_id, depends_on) VALUES(?, ?)",
                [(task_id, dependency) for dependency in spec.depends_on],
            )
            self._event(conn, task_id, "TASK_CREATED", {"title": spec.title})
            self._set_status(conn, task_id, TaskStatus.PENDING)
            target = TaskStatus.WAIT_DEP if spec.depends_on else TaskStatus.READY
            self._set_status(conn, task_id, target)
        return self.get_task(task_id)

    def get_task(self, task_id: str) -> dict[str, Any]:
        with self.db.connect() as conn:
            task = row_dict(
                conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            )
            if task is None:
                raise KeyError(task_id)
            task["depends_on"] = [
                row[0]
                for row in conn.execute(
                    "SELECT depends_on FROM task_dependencies WHERE task_id = ? ORDER BY depends_on",
                    (task_id,),
                )
            ]
            task["threads"] = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM codex_threads WHERE task_id = ? ORDER BY created_at",
                    (task_id,),
                )
            ]
            latest_attempt = conn.execute(
                """SELECT attempt_number, thread_id, turn_id, started_at, finished_at, result,
                          error_type, requested_model, requested_reasoning_effort,
                          effective_model, effective_reasoning_effort
                   FROM attempts WHERE task_id=? ORDER BY attempt_number DESC LIMIT 1""",
                (task_id,),
            ).fetchone()
            task["latest_attempt"] = (
                dict(latest_attempt) if latest_attempt is not None else None
            )
            worker = conn.execute(
                "SELECT * FROM workers WHERE task_id=? ORDER BY started_at DESC LIMIT 1",
                (task_id,),
            ).fetchone()
            task["worker"] = dict(worker) if worker is not None else None
            return task

    def list_tasks(self, statuses: Iterable[str] | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM tasks"
        params: list[Any] = []
        if statuses:
            values = [str(value) for value in statuses]
            query += f" WHERE status IN ({','.join('?' for _ in values)})"
            params.extend(values)
        query += " ORDER BY priority, created_at, id"
        with self.db.connect() as conn:
            return [row_dict(row) for row in conn.execute(query, params)]  # type: ignore[misc]

    def _event(
        self,
        conn: sqlite3.Connection,
        task_id: str | None,
        event_type: str,
        payload: Any = None,
    ) -> None:
        conn.execute(
            "INSERT INTO events(task_id, timestamp, event_type, payload) VALUES(?, ?, ?, ?)",
            (
                task_id,
                utc_now(),
                event_type,
                json.dumps(payload, default=str) if payload is not None else None,
            ),
        )

    def add_event(
        self, task_id: str | None, event_type: str, payload: Any = None
    ) -> None:
        with self.db.connect() as conn:
            self._event(conn, task_id, event_type, payload)

    def _set_status(
        self,
        conn: sqlite3.Connection,
        task_id: str,
        status: TaskStatus,
        *,
        reason: str | None = None,
        resume_at: str | None = None,
    ) -> None:
        row = conn.execute(
            "SELECT status FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if row is None:
            raise KeyError(task_id)
        validate_transition(row["status"], status)
        conn.execute(
            "UPDATE tasks SET status=?, blocked_reason=?, resume_at=?, updated_at=? WHERE id=?",
            (status, reason, resume_at, utc_now(), task_id),
        )
        self._event(
            conn,
            task_id,
            "TASK_STATUS_CHANGED",
            {"from": row["status"], "to": status, "reason": reason},
        )

    def transition(
        self,
        task_id: str,
        status: TaskStatus,
        *,
        reason: str | None = None,
        resume_at: str | None = None,
    ) -> None:
        with self.db.transaction(immediate=True) as conn:
            self._set_status(conn, task_id, status, reason=reason, resume_at=resume_at)

    def force_recovery_ready(self, task_id: str, reason: str) -> None:
        with self.db.transaction(immediate=True) as conn:
            row = conn.execute(
                "SELECT status FROM tasks WHERE id=?", (task_id,)
            ).fetchone()
            if row and TaskStatus(row["status"]) in {
                TaskStatus.CLAIMED,
                TaskStatus.RUNNING,
                TaskStatus.RETRY_WAIT,
                TaskStatus.WAIT_QUOTA,
            }:
                conn.execute(
                    "UPDATE tasks SET status='READY', claimed_by=NULL, resume_at=NULL, updated_at=? WHERE id=?",
                    (utc_now(), task_id),
                )
                self._event(
                    conn,
                    task_id,
                    "TASK_RECOVERY_QUEUED",
                    {"reason": reason, "from": row["status"]},
                )

    def refresh_dependencies(self) -> int:
        changed = 0
        with self.db.transaction(immediate=True) as conn:
            waiting = conn.execute(
                "SELECT id FROM tasks WHERE status='WAIT_DEP'"
            ).fetchall()
            for task in waiting:
                incomplete = conn.execute(
                    """SELECT 1 FROM task_dependencies d JOIN tasks t ON t.id=d.depends_on
                       WHERE d.task_id=? AND t.status <> 'SUCCEEDED' LIMIT 1""",
                    (task["id"],),
                ).fetchone()
                if incomplete is None:
                    self._set_status(conn, task["id"], TaskStatus.READY)
                    changed += 1
        return changed

    def claim_next(
        self, worker_id: str, *, grandfathered_only: bool = False
    ) -> dict[str, Any] | None:
        with self.db.transaction(immediate=True) as conn:
            conditions = ["t.status='READY'"]
            if grandfathered_only:
                conditions.append("t.grandfathered=1")
            conditions.append(
                "(t.exclusive_group IS NULL OR NOT EXISTS (SELECT 1 FROM tasks a WHERE a.exclusive_group=t.exclusive_group AND a.status IN ('CLAIMED','RUNNING','WAIT_QUOTA','RETRY_WAIT')))"
            )
            row = conn.execute(
                f"SELECT t.* FROM tasks t WHERE {' AND '.join(conditions)} ORDER BY t.priority, t.created_at, t.id LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            self._set_status(conn, row["id"], TaskStatus.CLAIMED)
            conn.execute(
                "UPDATE tasks SET claimed_by=? WHERE id=?", (worker_id, row["id"])
            )
            self._event(conn, row["id"], "TASK_CLAIMED", {"worker_id": worker_id})
        return self.get_task(row["id"])

    def create_attempt(
        self, task_id: str, config: EffectiveAgentConfig, thread_id: str | None = None
    ) -> int:
        with self.db.transaction(immediate=True) as conn:
            row = conn.execute(
                "SELECT current_attempt FROM tasks WHERE id=?", (task_id,)
            ).fetchone()
            if row is None:
                raise KeyError(task_id)
            number = int(row["current_attempt"]) + 1
            conn.execute(
                "UPDATE tasks SET current_attempt=?, updated_at=? WHERE id=?",
                (number, utc_now(), task_id),
            )
            conn.execute(
                """INSERT INTO attempts(task_id, attempt_number, thread_id, started_at,
                   requested_model, requested_reasoning_effort, effective_model, effective_reasoning_effort)
                   VALUES(?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task_id,
                    number,
                    thread_id,
                    utc_now(),
                    config.requested_model,
                    config.requested_reasoning_effort,
                    config.effective_model,
                    config.effective_reasoning_effort,
                ),
            )
            return number

    def finish_attempt(
        self,
        task_id: str,
        number: int,
        result: str,
        *,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE attempts SET finished_at=?, result=?, error_type=?, error_message=? WHERE task_id=? AND attempt_number=?",
                (utc_now(), result, error_type, error_message, task_id, number),
            )

    def bind_attempt_thread(
        self,
        task_id: str,
        number: int,
        thread_id: str,
        turn_id: str | None = None,
    ) -> None:
        now = utc_now()
        with self.db.transaction(immediate=True) as conn:
            conn.execute(
                """UPDATE attempts SET thread_id=?, turn_id=?
                   WHERE task_id=? AND attempt_number=?""",
                (thread_id, turn_id, task_id, number),
            )
            conn.execute(
                "UPDATE codex_threads SET last_used_at=? WHERE thread_id=?",
                (now, thread_id),
            )
            self._event(
                conn,
                task_id,
                "CODEX_TURN_RECORDED",
                {
                    "attempt": number,
                    "thread_id": thread_id,
                    "turn_id": turn_id,
                },
            )

    def record_failure(self, task_id: str) -> int:
        with self.db.transaction(immediate=True) as conn:
            row = conn.execute(
                "SELECT failure_count FROM tasks WHERE id=?", (task_id,)
            ).fetchone()
            if row is None:
                raise KeyError(task_id)
            count = int(row["failure_count"]) + 1
            conn.execute(
                "UPDATE tasks SET failure_count=?, updated_at=? WHERE id=?",
                (count, utc_now(), task_id),
            )
            return count

    def set_thread(
        self,
        task_id: str,
        thread_id: str,
        role: ThreadRole,
        *,
        parent_thread_id: str | None = None,
        model: str | None = None,
    ) -> None:
        now = utc_now()
        with self.db.transaction(immediate=True) as conn:
            conn.execute(
                """INSERT INTO codex_threads(thread_id, task_id, role, parent_thread_id, state, model, created_at, last_used_at)
                   VALUES(?, ?, ?, ?, 'ACTIVE', ?, ?, ?)
                   ON CONFLICT(thread_id) DO UPDATE SET state='ACTIVE', last_used_at=excluded.last_used_at""",
                (thread_id, task_id, role, parent_thread_id, model, now, now),
            )
            if role == ThreadRole.ROOT:
                conn.execute(
                    "UPDATE tasks SET root_thread_id=?, updated_at=? WHERE id=?",
                    (thread_id, now, task_id),
                )
            self._event(
                conn,
                task_id,
                "CODEX_THREAD_CREATED",
                {"thread_id": thread_id, "role": role},
            )

    def set_worktree(self, task_id: str, path: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE tasks SET worktree_path=?, updated_at=? WHERE id=?",
                (path, utc_now(), task_id),
            )

    def set_claim_running(self, task_id: str) -> None:
        self.transition(task_id, TaskStatus.RUNNING)

    def clear_claim(self, task_id: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE tasks SET claimed_by=NULL, updated_at=? WHERE id=?",
                (utc_now(), task_id),
            )

    def worker_heartbeat(
        self, worker_id: str, task_id: str | None, state: str, pid: int | None = None
    ) -> None:
        now = utc_now()
        with self.db.connect() as conn:
            conn.execute(
                """INSERT INTO workers(worker_id, task_id, pid, state, started_at, heartbeat_at)
                   VALUES(?, ?, ?, ?, ?, ?)
                   ON CONFLICT(worker_id) DO UPDATE SET task_id=excluded.task_id, pid=excluded.pid,
                   state=excluded.state, heartbeat_at=excluded.heartbeat_at""",
                (worker_id, task_id, pid or os.getpid(), state, now, now),
            )

    def remove_worker(self, worker_id: str) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM workers WHERE worker_id=?", (worker_id,))

    def list_workers(self) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            return [
                dict(row)
                for row in conn.execute("SELECT * FROM workers ORDER BY worker_id")
            ]

    def get_pool(self) -> dict[str, Any]:
        with self.db.connect() as conn:
            return dict(conn.execute("SELECT * FROM pool_state WHERE id=1").fetchone())

    def set_pool(self, state: PoolStatus, *, event_type: str | None = None) -> None:
        with self.db.transaction(immediate=True) as conn:
            conn.execute(
                "UPDATE pool_state SET state=?, updated_at=? WHERE id=1",
                (state, utc_now()),
            )
            self._event(conn, None, event_type or f"POOL_{state}", None)

    def set_freeze_on_weekly_reset(self, enabled: bool) -> None:
        with self.db.transaction(immediate=True) as conn:
            conn.execute(
                "UPDATE pool_state SET freeze_on_weekly_reset=?, updated_at=? WHERE id=1",
                (int(enabled), utc_now()),
            )
            self._event(
                conn,
                None,
                "POOL_WEEKLY_FREEZE_CHANGED",
                {"enabled": enabled},
            )

    def set_max_workers(self, max_workers: int) -> None:
        if not 1 <= max_workers <= 64:
            raise ValueError("max_workers must be between 1 and 64")
        with self.db.transaction(immediate=True) as conn:
            conn.execute(
                "UPDATE pool_state SET max_workers=?, updated_at=? WHERE id=1",
                (max_workers, utc_now()),
            )
            self._event(
                conn,
                None,
                "POOL_MAX_WORKERS_CHANGED",
                {"max_workers": max_workers},
            )

    def begin_weekly_drain(self, new_window: str) -> None:
        now = utc_now()
        with self.db.transaction(immediate=True) as conn:
            generation = f"weekly:{new_window}"
            conn.execute(
                "UPDATE pool_state SET state='DRAINING', drain_generation=?, freeze_triggered_at=?, last_weekly_window=?, updated_at=? WHERE id=1",
                (generation, now, new_window, now),
            )
            placeholders = ",".join("?" for _ in ACTIVE_TASK_STATES)
            conn.execute(
                f"UPDATE tasks SET grandfathered=1, drain_generation=? WHERE status IN ({placeholders})",
                (generation, *[str(state) for state in ACTIVE_TASK_STATES]),
            )
            self._event(conn, None, "WEEKLY_WINDOW_CHANGED", {"window_id": new_window})
            self._event(conn, None, "POOL_DRAINING", {"drain_generation": generation})

    def freeze_if_drained(self) -> bool:
        with self.db.transaction(immediate=True) as conn:
            pool = conn.execute("SELECT state FROM pool_state WHERE id=1").fetchone()
            if not pool or pool["state"] != PoolStatus.DRAINING:
                return False
            remaining = conn.execute(
                "SELECT 1 FROM tasks WHERE grandfathered=1 AND status NOT IN ('SUCCEEDED','FAILED','CANCELLED','BLOCKED') LIMIT 1"
            ).fetchone()
            if remaining:
                return False
            conn.execute(
                "UPDATE pool_state SET state='FROZEN', updated_at=? WHERE id=1",
                (utc_now(),),
            )
            self._event(conn, None, "POOL_FROZEN", None)
            return True

    def save_quota(self, provider: str, window: QuotaWindow) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """INSERT INTO quotas(provider, quota_type, available, used_percent, remaining, reset_at, window_id, updated_at, source)
                   VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(provider, quota_type) DO UPDATE SET available=excluded.available,
                   used_percent=excluded.used_percent, remaining=excluded.remaining, reset_at=excluded.reset_at,
                   window_id=excluded.window_id, updated_at=excluded.updated_at, source=excluded.source""",
                (
                    provider,
                    window.quota_type,
                    int(window.available),
                    window.used_percent,
                    window.remaining,
                    window.reset_at,
                    window.window_id,
                    window.updated_at,
                    window.source,
                ),
            )

    def list_quotas(self) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            return [
                dict(row)
                for row in conn.execute("SELECT * FROM quotas ORDER BY quota_type")
            ]

    def list_events(
        self, task_id: str | None = None, limit: int = 200
    ) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            if task_id:
                rows = conn.execute(
                    "SELECT * FROM events WHERE task_id=? ORDER BY id DESC LIMIT ?",
                    (task_id, limit),
                )
            else:
                rows = conn.execute(
                    "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
                )
            result = []
            for row in rows:
                item = dict(row)
                item["payload"] = (
                    json.loads(item["payload"]) if item["payload"] else None
                )
                result.append(item)
            return result

    def update_agent_config(
        self,
        task_id: str,
        *,
        model: str | None | object = UNSET,
        reasoning: str | None | object = UNSET,
    ) -> dict[str, Any]:
        with self.db.transaction(immediate=True) as conn:
            row = conn.execute(
                "SELECT status, model, reasoning_effort, pending_model, pending_reasoning_effort, pending_model_set, pending_reasoning_set FROM tasks WHERE id=?",
                (task_id,),
            ).fetchone()
            if row is None:
                raise KeyError(task_id)
            active = TaskStatus(row["status"]) in {
                TaskStatus.CLAIMED,
                TaskStatus.RUNNING,
            }
            if active:
                pending_model = row["pending_model"] if model is UNSET else model
                pending_reasoning = (
                    row["pending_reasoning_effort"] if reasoning is UNSET else reasoning
                )
                conn.execute(
                    """UPDATE tasks SET pending_model=?, pending_reasoning_effort=?,
                       pending_model_set=?, pending_reasoning_set=?, updated_at=? WHERE id=?""",
                    (
                        pending_model,
                        pending_reasoning,
                        int(bool(row["pending_model_set"]) or model is not UNSET),
                        int(
                            bool(row["pending_reasoning_set"]) or reasoning is not UNSET
                        ),
                        utc_now(),
                        task_id,
                    ),
                )
            else:
                current_model = row["model"] if model is UNSET else model
                current_reasoning = (
                    row["reasoning_effort"] if reasoning is UNSET else reasoning
                )
                conn.execute(
                    """UPDATE tasks SET model=?, reasoning_effort=?, pending_model=NULL,
                       pending_reasoning_effort=NULL, pending_model_set=0, pending_reasoning_set=0,
                       updated_at=? WHERE id=?""",
                    (current_model, current_reasoning, utc_now(), task_id),
                )
            if model is not UNSET and model != row["model"]:
                self._event(
                    conn,
                    task_id,
                    "TASK_MODEL_CHANGED",
                    {"model": model, "applies": "next_turn" if active else "now"},
                )
            if reasoning is not UNSET and reasoning != row["reasoning_effort"]:
                self._event(
                    conn,
                    task_id,
                    "TASK_REASONING_CHANGED",
                    {
                        "reasoning": reasoning,
                        "applies": "next_turn" if active else "now",
                    },
                )
        return self.get_task(task_id)

    def cancel_task(self, task_id: str) -> dict[str, Any]:
        task = self.get_task(task_id)
        if TaskStatus(task["status"]) not in {
            TaskStatus.SUCCEEDED,
            TaskStatus.CANCELLED,
        }:
            self.transition(task_id, TaskStatus.CANCELLED)
        return self.get_task(task_id)

    def retry_task(self, task_id: str) -> dict[str, Any]:
        task = self.get_task(task_id)
        if TaskStatus(task["status"]) not in {
            TaskStatus.FAILED,
            TaskStatus.BLOCKED,
            TaskStatus.CANCELLED,
        }:
            raise ValueError(f"task {task_id} is not retryable from {task['status']}")
        with self.db.transaction(immediate=True) as conn:
            conn.execute(
                "UPDATE tasks SET failure_count=0, updated_at=? WHERE id=?",
                (utc_now(), task_id),
            )
            self._set_status(conn, task_id, TaskStatus.READY)
        return self.get_task(task_id)

    def delete_task(self, task_id: str) -> None:
        task = self.get_task(task_id)
        if TaskStatus(task["status"]) in ACTIVE_TASK_STATES:
            raise ValueError("cancel an active task before deleting it")
        with self.db.connect() as conn:
            conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))

    def apply_pending_agent_config(self, task_id: str) -> None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT pending_model, pending_reasoning_effort, pending_model_set, pending_reasoning_set FROM tasks WHERE id=?",
                (task_id,),
            ).fetchone()
            if row and (row["pending_model_set"] or row["pending_reasoning_set"]):
                model_expression = (
                    "pending_model" if row["pending_model_set"] else "model"
                )
                reasoning_expression = (
                    "pending_reasoning_effort"
                    if row["pending_reasoning_set"]
                    else "reasoning_effort"
                )
                conn.execute(
                    f"""UPDATE tasks SET model={model_expression}, reasoning_effort={reasoning_expression},
                       pending_model=NULL, pending_reasoning_effort=NULL, pending_model_set=0,
                       pending_reasoning_set=0, updated_at=? WHERE id=?""",
                    (utc_now(), task_id),
                )

    def active_tasks(self) -> list[dict[str, Any]]:
        return self.list_tasks([str(state) for state in ACTIVE_TASK_STATES])
