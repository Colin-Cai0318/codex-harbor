from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS weekly_ping_settings (
    id INTEGER PRIMARY KEY CHECK(id=1),
    enabled INTEGER NOT NULL DEFAULT 0,
    observed_reset TEXT
);
INSERT OR IGNORE INTO weekly_ping_settings(id) VALUES(1);
CREATE TABLE IF NOT EXISTS weekly_pings (
    reset_at TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    thread_id TEXT,
    turn_id TEXT,
    next_reset_at TEXT,
    error TEXT
);
CREATE TABLE IF NOT EXISTS recovery_settings (
    id INTEGER PRIMARY KEY CHECK(id=1),
    allow_luna_reserve INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO recovery_settings(id,allow_luna_reserve) VALUES(1,0);
CREATE TABLE IF NOT EXISTS recovery_watches (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    spec TEXT NOT NULL,
    threshold REAL NOT NULL,
    baseline_turn_id TEXT,
    baseline_status TEXT,
    trigger_mode TEXT NOT NULL DEFAULT 'on_failure',
    resume_after TEXT,
    state TEXT NOT NULL DEFAULT 'ARMED',
    task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
    reserve_status TEXT,
    reserve_note TEXT,
    reserve_turn_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS active_recovery_thread ON recovery_watches(thread_id)
    WHERE state IN ('ARMED', 'WAITING', 'HANDED_OFF');
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS repositories (
    path TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    added_at TEXT NOT NULL,
    codex_project_id TEXT
);
CREATE TABLE IF NOT EXISTS task_groups (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    repository TEXT NOT NULL REFERENCES repositories(path),
    codex_project_id TEXT,
    origin_thread_id TEXT,
    session_mode TEXT NOT NULL DEFAULT 'isolated',
    reuse_worktree INTEGER NOT NULL DEFAULT 0,
    failure_policy TEXT NOT NULL DEFAULT 'block_following',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    repository TEXT NOT NULL REFERENCES repositories(path),
    execution_backend TEXT NOT NULL DEFAULT 'local',
    prompt TEXT NOT NULL,
    status TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 100,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    current_attempt INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    root_thread_id TEXT,
    resume_at TEXT,
    blocked_reason TEXT,
    worktree_path TEXT,
    acceptance_commands TEXT NOT NULL DEFAULT '[]',
    model TEXT,
    reasoning_effort TEXT,
    pending_model TEXT,
    pending_reasoning_effort TEXT,
    pending_model_set INTEGER NOT NULL DEFAULT 0,
    pending_reasoning_set INTEGER NOT NULL DEFAULT 0,
    profile TEXT,
    grandfathered INTEGER NOT NULL DEFAULT 0,
    drain_generation TEXT,
    exclusive_group TEXT,
    claimed_by TEXT,
    task_group_id TEXT,
    codex_project_id TEXT,
    origin_thread_id TEXT,
    session_parent_task_id TEXT,
    reuse_parent_worktree INTEGER NOT NULL DEFAULT 0,
    worktree_owner_task_id TEXT,
    workspace_mode TEXT NOT NULL DEFAULT 'project',
    workspace_owned INTEGER NOT NULL DEFAULT 0,
    conversation_mode TEXT,
    conversation_cwd TEXT,
    runtime_workspace_roots TEXT NOT NULL DEFAULT '[]',
    direct_prompt INTEGER NOT NULL DEFAULT 0,
    preserve_thread_name INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tasks_schedule ON tasks(status, priority, created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_group ON tasks(exclusive_group, status);
CREATE TABLE IF NOT EXISTS codex_threads (
    thread_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    parent_thread_id TEXT,
    state TEXT,
    model TEXT,
    project_id TEXT,
    created_at TEXT NOT NULL,
    last_used_at TEXT
);
CREATE TABLE IF NOT EXISTS task_thread_links (
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    thread_id TEXT NOT NULL REFERENCES codex_threads(thread_id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    inherited_from_task_id TEXT,
    linked_at TEXT NOT NULL,
    PRIMARY KEY(task_id, thread_id)
);
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    attempt_number INTEGER NOT NULL,
    thread_id TEXT,
    turn_id TEXT,
    started_at TEXT,
    finished_at TEXT,
    result TEXT,
    error_type TEXT,
    error_message TEXT,
    requested_model TEXT,
    requested_reasoning_effort TEXT,
    effective_model TEXT,
    effective_reasoning_effort TEXT,
    UNIQUE(task_id, attempt_number)
);
CREATE TABLE IF NOT EXISTS task_dependencies (
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    depends_on TEXT NOT NULL REFERENCES tasks(id),
    PRIMARY KEY(task_id, depends_on),
    CHECK(task_id <> depends_on)
);
CREATE TABLE IF NOT EXISTS workers (
    worker_id TEXT PRIMARY KEY,
    task_id TEXT REFERENCES tasks(id),
    pid INTEGER,
    state TEXT,
    started_at TEXT,
    heartbeat_at TEXT
);
CREATE TABLE IF NOT EXISTS pool_state (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    state TEXT NOT NULL,
    freeze_on_weekly_reset INTEGER NOT NULL DEFAULT 0,
    max_workers INTEGER NOT NULL DEFAULT 3,
    drain_generation TEXT,
    freeze_triggered_at TEXT,
    last_weekly_window TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS quotas (
    provider TEXT NOT NULL,
    quota_type TEXT NOT NULL,
    available INTEGER NOT NULL DEFAULT 1,
    used_percent REAL,
    remaining REAL,
    reset_at TEXT,
    window_id TEXT,
    updated_at TEXT,
    source TEXT,
    PRIMARY KEY(provider, quota_type)
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT REFERENCES tasks(id) ON DELETE CASCADE,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id, id);
"""


class ClosingConnection(sqlite3.Connection):
    """sqlite3 context manager that also releases the OS handle."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            self.path,
            timeout=30,
            isolation_level=None,
            factory=ClosingConnection,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def migrate(
        self,
        *,
        freeze_on_weekly_reset: bool = True,
        max_workers: int = 3,
        now: str,
    ) -> None:
        max_workers = max(1, min(64, int(max_workers)))
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            watch_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(recovery_watches)")
            }
            for column in ("reserve_status", "reserve_note", "reserve_turn_id"):
                if column not in watch_columns:
                    connection.execute(
                        f"ALTER TABLE recovery_watches ADD COLUMN {column} TEXT"
                    )
            if "trigger_mode" not in watch_columns:
                connection.execute(
                    "ALTER TABLE recovery_watches ADD COLUMN trigger_mode TEXT NOT NULL DEFAULT 'on_failure'"
                )
            if "resume_after" not in watch_columns:
                connection.execute(
                    "ALTER TABLE recovery_watches ADD COLUMN resume_after TEXT"
                )
            task_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(tasks)")
            }
            if "pending_model_set" not in task_columns:
                connection.execute(
                    "ALTER TABLE tasks ADD COLUMN pending_model_set INTEGER NOT NULL DEFAULT 0"
                )
            if "pending_reasoning_set" not in task_columns:
                connection.execute(
                    "ALTER TABLE tasks ADD COLUMN pending_reasoning_set INTEGER NOT NULL DEFAULT 0"
                )
            if "failure_count" not in task_columns:
                connection.execute(
                    "ALTER TABLE tasks ADD COLUMN failure_count INTEGER NOT NULL DEFAULT 0"
                )
            task_v4_columns = {
                "task_group_id": "TEXT",
                "codex_project_id": "TEXT",
                "origin_thread_id": "TEXT",
                "session_parent_task_id": "TEXT",
                "reuse_parent_worktree": "INTEGER NOT NULL DEFAULT 0",
                "worktree_owner_task_id": "TEXT",
                "workspace_mode": "TEXT NOT NULL DEFAULT 'project'",
                "workspace_owned": "INTEGER NOT NULL DEFAULT 0",
            }
            for column, declaration in task_v4_columns.items():
                if column not in task_columns:
                    connection.execute(
                        f"ALTER TABLE tasks ADD COLUMN {column} {declaration}"
                    )
            repository_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(repositories)")
            }
            if "codex_project_id" not in repository_columns:
                connection.execute(
                    "ALTER TABLE repositories ADD COLUMN codex_project_id TEXT"
                )
            thread_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(codex_threads)")
            }
            if "project_id" not in thread_columns:
                connection.execute(
                    "ALTER TABLE codex_threads ADD COLUMN project_id TEXT"
                )
            attempt_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(attempts)")
            }
            if "turn_id" not in attempt_columns:
                connection.execute("ALTER TABLE attempts ADD COLUMN turn_id TEXT")
            pool_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(pool_state)")
            }
            if "max_workers" not in pool_columns:
                connection.execute(
                    "ALTER TABLE pool_state ADD COLUMN max_workers INTEGER NOT NULL DEFAULT 3"
                )
                connection.execute(
                    "UPDATE pool_state SET max_workers=? WHERE id=1", (max_workers,)
                )
            connection.execute(
                "INSERT OR IGNORE INTO schema_version(version, applied_at) VALUES(1, ?)",
                (now,),
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_version(version, applied_at) VALUES(2, ?)",
                (now,),
            )
            version_three = connection.execute(
                "SELECT 1 FROM schema_version WHERE version=3"
            ).fetchone()
            if version_three is None:
                quota_error_match = """
                    lower(COALESCE(error_message, '')) LIKE '%usagelimitexceeded%'
                    OR lower(COALESCE(error_message, '')) LIKE '%hit your usage limit%'
                """
                repaired_tasks = [
                    row["id"]
                    for row in connection.execute(
                        f"""SELECT t.id FROM tasks t
                            JOIN attempts a ON a.task_id=t.id
                            WHERE t.status='FAILED'
                              AND a.attempt_number=(
                                  SELECT MAX(last.attempt_number)
                                  FROM attempts last WHERE last.task_id=t.id
                              )
                              AND ({quota_error_match})"""
                    )
                ]
                connection.execute(
                    f"""UPDATE attempts
                        SET result='WAIT_QUOTA', error_type='RATE_LIMIT_5H'
                        WHERE {quota_error_match}"""
                )
                connection.execute(
                    """UPDATE tasks SET failure_count=(
                           SELECT COUNT(*) FROM attempts a
                           WHERE a.task_id=tasks.id
                             AND a.result IN ('FAILED', 'ACCEPTANCE_FAILED')
                             AND COALESCE(a.error_type, '') NOT IN (
                                 'RATE_LIMIT_5H', 'RATE_LIMIT_WEEKLY'
                             )
                       )"""
                )
                for task_id in repaired_tasks:
                    connection.execute(
                        """UPDATE tasks SET status='WAIT_QUOTA',
                           blocked_reason='RATE_LIMIT_5H', resume_at=NULL,
                           claimed_by=NULL, updated_at=? WHERE id=?""",
                        (now, task_id),
                    )
                    connection.execute(
                        """INSERT INTO events(task_id, timestamp, event_type, payload)
                           VALUES(?, ?, 'TASK_QUOTA_FAILURE_REPAIRED', ?)""",
                        (
                            task_id,
                            now,
                            (
                                '{"from":"FAILED","to":"WAIT_QUOTA",'
                                '"reason":"usageLimitExceeded"}'
                            ),
                        ),
                    )
                connection.execute(
                    "INSERT INTO schema_version(version, applied_at) VALUES(3, ?)",
                    (now,),
                )
            version_four = connection.execute(
                "SELECT 1 FROM schema_version WHERE version=4"
            ).fetchone()
            if version_four is None:
                connection.execute(
                    """INSERT OR IGNORE INTO task_thread_links(
                           task_id, thread_id, role, inherited_from_task_id, linked_at
                       )
                       SELECT task_id, thread_id, role, NULL, created_at
                       FROM codex_threads"""
                )
                connection.execute(
                    """UPDATE tasks SET worktree_owner_task_id=id
                       WHERE worktree_path IS NOT NULL
                         AND worktree_owner_task_id IS NULL"""
                )
                connection.execute(
                    """UPDATE tasks SET workspace_mode='isolated', workspace_owned=1
                       WHERE worktree_path IS NOT NULL"""
                )
                connection.execute(
                    "INSERT INTO schema_version(version, applied_at) VALUES(4, ?)",
                    (now,),
                )
            version_five = connection.execute(
                "SELECT 1 FROM schema_version WHERE version=5"
            ).fetchone()
            if version_five is None:
                task_v5_columns = {
                    "conversation_mode": "TEXT",
                    "conversation_cwd": "TEXT",
                    "runtime_workspace_roots": "TEXT NOT NULL DEFAULT '[]'",
                    "direct_prompt": "INTEGER NOT NULL DEFAULT 0",
                    "preserve_thread_name": "INTEGER NOT NULL DEFAULT 0",
                }
                current_columns = {
                    row["name"]
                    for row in connection.execute("PRAGMA table_info(tasks)")
                }
                for column, declaration in task_v5_columns.items():
                    if column not in current_columns:
                        connection.execute(
                            f"ALTER TABLE tasks ADD COLUMN {column} {declaration}"
                        )
                connection.execute(
                    "INSERT INTO schema_version(version, applied_at) VALUES(5, ?)",
                    (now,),
                )
            connection.execute(
                """INSERT OR IGNORE INTO pool_state(
                    id, state, freeze_on_weekly_reset, max_workers, updated_at
                ) VALUES(1, 'RUNNING', ?, ?, ?)""",
                (int(freeze_on_weekly_reset), max_workers, now),
            )

    @contextmanager
    def transaction(self, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
