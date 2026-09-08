from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import UTC, datetime

from ..domain import TaskSpec, TaskStatus, utc_now
from .reserve import RESERVE_EFFORT, RESERVE_MODEL, prepare_reserve_checkpoint


def quota_failure(turn: dict) -> bool:
    if turn.get("status") != "failed":
        return False
    error = json.dumps(turn.get("error") or {}).lower()
    return any(
        token in error
        for token in (
            "usagelimitexceeded",
            "hit your usage limit",
            "primary rate limit",
            "5 hour",
            "5-hour",
            "5h usage",
        )
    )


class AutoResumeManager:
    """Durable, inference-free protection for one explicitly selected conversation."""

    def __init__(self, repository, client):
        self.repository = repository
        self.client = client

    def list(self):
        with self.repository.db.connect() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM recovery_watches ORDER BY created_at"
                )
            ]

    def settings(self):
        with self.repository.db.connect() as conn:
            enabled = conn.execute(
                "SELECT allow_luna_reserve FROM recovery_settings WHERE id=1"
            ).fetchone()[0]
        return {
            "allow_luna_reserve": bool(enabled),
            "reserve_model": RESERVE_MODEL,
            "reserve_reasoning_effort": RESERVE_EFFORT,
            "max_reserve_turns_per_watch": 1,
        }

    def set_reserve_enabled(self, enabled: bool):
        with self.repository.db.connect() as conn:
            conn.execute(
                "UPDATE recovery_settings SET allow_luna_reserve=? WHERE id=1",
                (int(enabled),),
            )
        return self.settings()

    async def _reserve_checkpoint(self, watch):
        with self.repository.db.transaction(immediate=True) as conn:
            changed = conn.execute(
                "UPDATE recovery_watches SET reserve_status='STARTED',updated_at=? "
                "WHERE id=? AND task_id IS NULL AND reserve_status IS NULL AND state='ARMED'",
                (utc_now(), watch["id"]),
            ).rowcount
        if not changed:
            return
        turn_id = None
        try:
            note, turn_id = await prepare_reserve_checkpoint(
                self.client, watch["thread_id"]
            )
            status = "COMPLETED"
        except Exception as error:  # noqa: BLE001 - checkpoint failure must not prevent task registration
            status, note = "FAILED", str(error)[-1000:]
        with self.repository.db.connect() as conn:
            conn.execute(
                "UPDATE recovery_watches SET reserve_status=?,reserve_note=?,reserve_turn_id=?,updated_at=? WHERE id=?",
                (status, note, turn_id, utc_now(), watch["id"]),
            )
        self.repository.add_event(
            None,
            "LUNA_RESERVE_CHECKPOINT",
            {
                "watch_id": watch["id"],
                "thread_id": watch["thread_id"],
                "model": RESERVE_MODEL,
                "reasoning_effort": RESERVE_EFFORT,
                "status": status,
            },
        )

    def arm(
        self,
        spec: TaskSpec,
        thread: dict,
        threshold: float,
        *,
        trigger_mode: str = "on_failure",
        resume_after: str | None = None,
    ):
        if spec.model == RESERVE_MODEL:
            raise ValueError(
                "recovery requires the main model; gpt-reserve is checkpoint-only"
            )
        if trigger_mode not in {"on_failure", "after_reset"}:
            raise ValueError("unknown recovery trigger mode")
        if trigger_mode == "after_reset":
            if not resume_after:
                raise ValueError(
                    "after_reset requires the observed reset time as resume_after"
                )
            boundary = datetime.fromisoformat(resume_after)
            if boundary.tzinfo is None:
                raise ValueError("resume_after requires a timezone")
            resume_after = boundary.astimezone(UTC).isoformat()
        elif resume_after is not None:
            raise ValueError("resume_after is only valid for after_reset")
        turns = thread.get("turns") or []
        last = turns[-1] if turns else {}
        now = utc_now()
        with self.repository.db.transaction(immediate=True) as conn:
            existing = conn.execute(
                "SELECT * FROM recovery_watches WHERE thread_id=? "
                "AND state IN ('ARMED', 'WAITING', 'HANDED_OFF')",
                (spec.origin_thread_id,),
            ).fetchone()
            if existing:
                if existing["trigger_mode"] != trigger_mode:
                    raise ValueError(
                        "cancel the existing watch before changing its trigger mode"
                    )
                return dict(existing)
            watch_id = f"R{uuid.uuid4().hex[:12]}"
            conn.execute(
                "INSERT INTO recovery_watches(id,thread_id,spec,threshold,"
                "baseline_turn_id,baseline_status,created_at,updated_at,trigger_mode,resume_after) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    watch_id,
                    spec.origin_thread_id,
                    json.dumps(asdict(spec)),
                    threshold,
                    last.get("id"),
                    last.get("status"),
                    now,
                    now,
                    trigger_mode,
                    resume_after,
                ),
            )
            if trigger_mode == "after_reset":
                task_id = self.repository._insert_task(conn, spec, spec.repository, now)
                self.repository._set_status(
                    conn, task_id, TaskStatus.WAIT_QUOTA, reason="AUTO_RESUME_ARMED"
                )
                conn.execute(
                    "UPDATE tasks SET resume_at=? WHERE id=?", (resume_after, task_id)
                )
                conn.execute(
                    "UPDATE recovery_watches SET task_id=?,state='WAITING' WHERE id=?",
                    (task_id, watch_id),
                )
            return dict(
                conn.execute(
                    "SELECT * FROM recovery_watches WHERE id=?", (watch_id,)
                ).fetchone()
            )

    def cancel(self, watch_id):
        with self.repository.db.transaction(immediate=True) as conn:
            row = conn.execute(
                "SELECT * FROM recovery_watches WHERE id=?", (watch_id,)
            ).fetchone()
            if row is None:
                raise KeyError(watch_id)
            if row["task_id"]:
                task = conn.execute(
                    "SELECT status FROM tasks WHERE id=?", (row["task_id"],)
                ).fetchone()
                if task and task["status"] not in {"SUCCEEDED", "CANCELLED"}:
                    self.repository._set_status(
                        conn, row["task_id"], TaskStatus.CANCELLED
                    )
            conn.execute(
                "UPDATE recovery_watches SET state='CANCELLED',updated_at=? WHERE id=?",
                (utc_now(), watch_id),
            )
        return {"id": watch_id, "state": "CANCELLED"}

    async def tick(self, windows):
        primary = next((w for w in windows if w.quota_type == "PRIMARY_5H"), None)
        for watch in self.list():
            if watch["state"] == "HANDED_OFF":
                task = self.repository.get_task(watch["task_id"])
                if (
                    watch["trigger_mode"] == "on_failure"
                    and task["current_attempt"] == 0
                    and hasattr(self.client, "thread_inspect_latest")
                ):
                    try:
                        inspected = await self.client.thread_inspect_latest(
                            watch["thread_id"]
                        )
                        latest = (inspected["thread"].get("turns") or [{}])[-1]
                        if (
                            latest.get("id") != watch["baseline_turn_id"]
                            and latest.get("status") == "completed"
                        ):
                            self.cancel(watch["id"])
                            continue
                    except Exception as error:  # noqa: BLE001 - isolate individual watch checks
                        self.repository.add_event(
                            task["id"],
                            "AUTO_RESUME_CHECK_FAILED",
                            {"error": str(error)[-1000:]},
                        )
                        continue
                if task["status"] in {"SUCCEEDED", "CANCELLED", "FAILED", "BLOCKED"}:
                    with self.repository.db.connect() as conn:
                        conn.execute(
                            "UPDATE recovery_watches SET state='COMPLETED',updated_at=? WHERE id=?",
                            (utc_now(), watch["id"]),
                        )
                continue
            if watch["state"] not in {"ARMED", "WAITING"}:
                continue
            try:
                if hasattr(self.client, "thread_inspect_latest"):
                    inspected = await self.client.thread_inspect_latest(
                        watch["thread_id"]
                    )
                else:
                    inspected = await self.client.thread_read(
                        watch["thread_id"], include_turns=True
                    )
                thread = inspected.get("thread", inspected)
                turns = thread.get("turns") or []
                last = turns[-1] if turns else {}
                if watch["trigger_mode"] == "after_reset":
                    # A scheduling acknowledgement may finish normally. Only an
                    # explicit cancellation or the scheduled task ends this watch.
                    if last.get("status") not in {"completed", "failed", "interrupted"}:
                        continue
                    if (
                        not primary
                        or not primary.available
                        or any(not window.available for window in windows)
                        or datetime.now(UTC)
                        < datetime.fromisoformat(watch["resume_after"])
                    ):
                        continue
                    with self.repository.db.transaction(immediate=True) as conn:
                        current = conn.execute(
                            "SELECT * FROM recovery_watches WHERE id=?", (watch["id"],)
                        ).fetchone()
                        if current["state"] != "WAITING":
                            continue
                        task = conn.execute(
                            "SELECT status FROM tasks WHERE id=?", (current["task_id"],)
                        ).fetchone()
                        if task["status"] != "WAIT_QUOTA":
                            conn.execute(
                                "UPDATE recovery_watches SET state='COMPLETED',updated_at=? WHERE id=?",
                                (utc_now(), watch["id"]),
                            )
                            continue
                        conn.execute(
                            "UPDATE tasks SET blocked_reason='RESET_RESUME_CONFIRMED',updated_at=? WHERE id=?",
                            (utc_now(), current["task_id"]),
                        )
                        conn.execute(
                            "UPDATE recovery_watches SET state='HANDED_OFF',updated_at=? WHERE id=?",
                            (utc_now(), watch["id"]),
                        )
                        self.repository._event(
                            conn,
                            current["task_id"],
                            "AUTO_RESUME_RESET_CONFIRMED",
                            {
                                "thread_id": watch["thread_id"],
                                "resume_after": watch["resume_after"],
                            },
                        )
                    continue
                reserve_finished = (
                    watch["reserve_status"] == "COMPLETED"
                    and last.get("id") == watch["reserve_turn_id"]
                )
                failed = quota_failure(last) or (
                    reserve_finished and not watch["task_id"]
                )
                finished = (
                    not reserve_finished
                    and last.get("status") == "completed"
                    and (
                        last.get("id") != watch["baseline_turn_id"]
                        or watch["baseline_status"] != "completed"
                    )
                )
                near_limit = (
                    primary
                    and primary.used_percent is not None
                    and primary.used_percent >= watch["threshold"]
                )
                if (
                    failed
                    and not watch["task_id"]
                    and primary
                    and not primary.available
                    and self.settings()["allow_luna_reserve"]
                ):
                    await self._reserve_checkpoint(watch)
                with self.repository.db.transaction(immediate=True) as conn:
                    # Recheck under the write lock: cancellation and another daemon
                    # may have changed the watch while the read RPC was in flight.
                    current = conn.execute(
                        "SELECT * FROM recovery_watches WHERE id=?", (watch["id"],)
                    ).fetchone()
                    if current["state"] not in {"ARMED", "WAITING"}:
                        continue
                    task_id = current["task_id"]
                    if task_id:
                        task_status = conn.execute(
                            "SELECT status FROM tasks WHERE id=?", (task_id,)
                        ).fetchone()["status"]
                        if task_status != "WAIT_QUOTA":
                            conn.execute(
                                "UPDATE recovery_watches SET state='COMPLETED',updated_at=? WHERE id=?",
                                (utc_now(), watch["id"]),
                            )
                            continue
                    if finished:
                        if task_id:
                            self.repository._set_status(
                                conn,
                                task_id,
                                TaskStatus.CANCELLED,
                                reason="ORIGINAL_TURN_COMPLETED",
                            )
                        conn.execute(
                            "UPDATE recovery_watches SET state='COMPLETED',updated_at=? WHERE id=?",
                            (utc_now(), watch["id"]),
                        )
                        continue
                    if not task_id and (near_limit or failed):
                        spec = TaskSpec(**json.loads(watch["spec"]))
                        if current["reserve_status"] == "COMPLETED":
                            spec.prompt += (
                                "\n\nLuna Reserve 续接摘要（以原对话和工作区实际状态为准）：\n"
                                + current["reserve_note"]
                            )
                        task_id = self.repository._insert_task(
                            conn, spec, spec.repository, utc_now()
                        )
                        self.repository._set_status(
                            conn,
                            task_id,
                            TaskStatus.WAIT_QUOTA,
                            reason="AUTO_RESUME_ARMED",
                        )
                        conn.execute(
                            "UPDATE recovery_watches SET task_id=?,state='WAITING',updated_at=? WHERE id=?",
                            (task_id, utc_now(), watch["id"]),
                        )
                    if task_id and failed:
                        # If observation happens after reset (e.g. daemon restart),
                        # the provider reports the *next* window's boundary. Do
                        # not postpone old failed work by another five hours.
                        reset = (
                            primary.reset_at
                            if primary and (not primary.available or near_limit)
                            else None
                        )
                        # Only a future boundary is a useful delay. Fresh quota
                        # telemetry still gates release in QuotaManager.
                        if reset and datetime.fromisoformat(reset) <= datetime.now(UTC):
                            reset = None
                        conn.execute(
                            "UPDATE tasks SET blocked_reason='RATE_LIMIT_5H',resume_at=?,updated_at=? WHERE id=?",
                            (reset, utc_now(), task_id),
                        )
                        conn.execute(
                            "UPDATE recovery_watches SET state='HANDED_OFF',baseline_turn_id=?,updated_at=? WHERE id=?",
                            (
                                current["reserve_turn_id"] or last.get("id"),
                                utc_now(),
                                watch["id"],
                            ),
                        )
                        self.repository._event(
                            conn,
                            task_id,
                            "AUTO_RESUME_QUOTA_CONFIRMED",
                            {
                                "thread_id": watch["thread_id"],
                                "turn_id": last.get("id"),
                            },
                        )
            except Exception as error:  # noqa: BLE001 - retain durable watch on RPC/storage errors
                self.repository.add_event(
                    watch["task_id"],
                    "AUTO_RESUME_CHECK_FAILED",
                    {"watch_id": watch["id"], "error": str(error)[-1000:]},
                )
