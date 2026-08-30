from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS repositories (
    path TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    added_at TEXT NOT NULL
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
    claimed_by TEXT
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
    created_at TEXT NOT NULL,
    last_used_at TEXT
);
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    attempt_number INTEGER NOT NULL,
    thread_id TEXT,
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

    def migrate(self, *, freeze_on_weekly_reset: bool = True, now: str) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
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
            connection.execute(
                "INSERT OR IGNORE INTO schema_version(version, applied_at) VALUES(1, ?)",
                (now,),
            )
            connection.execute(
                """INSERT OR IGNORE INTO pool_state(
                    id, state, freeze_on_weekly_reset, updated_at
                ) VALUES(1, 'RUNNING', ?, ?)""",
                (int(freeze_on_weekly_reset), now),
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
