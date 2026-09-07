from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from ..codex import AppServerClient, ModelRegistry
from ..runtime import CodexAppServerRuntime

MODEL = "gpt-5.6-luna"
EFFORT = "low"
PROMPT = "Reply exactly OK. Do not use tools, read files, or perform any other work."


def boundary(value):
    if not value:
        return None
    try:
        result = datetime.fromisoformat(value)
        return (
            result.replace(tzinfo=UTC)
            if result.tzinfo is None
            else result.astimezone(UTC)
        )
    except (ValueError, TypeError):
        return None


async def send_weekly_ping(control, cwd):
    """A fresh, short, read-only conversation; release its writer on every exit."""
    async with AppServerClient(
        control.executable, request_timeout=control.request_timeout
    ) as client:
        registry = await ModelRegistry.load(client)
        config = registry.resolve(
            task_model=MODEL, task_reasoning=EFFORT, global_model=MODEL
        )
        runtime = CodexAppServerRuntime(client, sandbox="read-only")
        result = await runtime.start_task(str(cwd), PROMPT, config)
        if result.status != "completed":
            raise RuntimeError(result.error or result.status)
        return result


class WeeklyPingManager:
    def __init__(self, repository, client=None, *, sender=None):
        self.repository = repository
        self.client = client
        self.sender = sender or send_weekly_ping

    def settings(self):
        with self.repository.db.connect() as conn:
            row = dict(
                conn.execute("SELECT * FROM weekly_ping_settings WHERE id=1").fetchone()
            )
            latest = conn.execute(
                "SELECT * FROM weekly_pings ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
        return {
            "enabled": bool(row["enabled"]),
            "observed_reset": row["observed_reset"],
            "model": MODEL,
            "reasoning_effort": EFFORT,
            "last_ping": dict(latest) if latest else None,
        }

    def set_enabled(self, enabled):
        with self.repository.db.connect() as conn:
            # Forget the disabled interval, but never delete the deduplication ledger.
            conn.execute(
                "UPDATE weekly_ping_settings SET enabled=?, observed_reset=CASE WHEN enabled != ? THEN NULL ELSE observed_reset END WHERE id=1",
                (int(enabled), int(enabled)),
            )
        return self.settings()

    async def tick(self, windows, *, now=None):
        now = now or datetime.now(UTC)
        weekly = next((w for w in windows if w.quota_type == "WEEKLY"), None)
        primary = next((w for w in windows if w.quota_type == "PRIMARY_5H"), None)
        current = boundary(weekly.reset_at) if weekly else None
        if not weekly:
            return
        with self.repository.db.transaction(immediate=True) as conn:
            settings = conn.execute(
                "SELECT * FROM weekly_ping_settings WHERE id=1"
            ).fetchone()
            if not settings["enabled"]:
                return
            previous = boundary(settings["observed_reset"])
            if previous is None or previous > now:
                if current is None:
                    return
                # Initial observation and revisions before a boundary are not resets.
                conn.execute(
                    "UPDATE weekly_ping_settings SET observed_reset=? WHERE id=1",
                    (current.isoformat(),),
                )
                previous = current
            if (
                previous > now
                or not primary
                or not primary.available
                or not weekly.available
            ):
                return
            reset = previous.isoformat()
            claimed = conn.execute(
                "INSERT OR IGNORE INTO weekly_pings(reset_at,status,started_at) VALUES(?,'STARTED',?)",
                (reset, now.isoformat()),
            ).rowcount
            if current and current > previous:
                conn.execute(
                    "UPDATE weekly_ping_settings SET observed_reset=? WHERE id=1",
                    (current.isoformat(),),
                )
            if not claimed:
                return
        # Durable claim precedes inference. Uncertain delivery is never auto-retried.
        cwd = Path(self.repository.db.path).parent / "weekly-ping"
        try:
            cwd.mkdir(parents=True, exist_ok=True)
            result = await asyncio.wait_for(self.sender(self.client, cwd), timeout=90)
        except Exception as error:  # noqa: BLE001 - optional automation must not stop scheduling
            with self.repository.db.connect() as conn:
                conn.execute(
                    "UPDATE weekly_pings SET status='FAILED',error=?,finished_at=? WHERE reset_at=?",
                    (
                        str(error) or type(error).__name__,
                        datetime.now(UTC).isoformat(),
                        reset,
                    ),
                )
            self.repository.add_event(
                None, "WEEKLY_PING_FAILED", {"reset_at": reset, "error": str(error)}
            )
            return
        with self.repository.db.connect() as conn:
            conn.execute(
                "UPDATE weekly_pings SET status='SENT',thread_id=?,turn_id=?,finished_at=? WHERE reset_at=?",
                (
                    result.thread_id,
                    result.turn_id,
                    datetime.now(UTC).isoformat(),
                    reset,
                ),
            )
        self.repository.add_event(
            None,
            "WEEKLY_PING_SENT",
            {
                "reset_at": reset,
                "thread_id": result.thread_id,
                "model": MODEL,
                "reasoning_effort": EFFORT,
            },
        )

    def observe_confirmation(self, windows):
        weekly = next((w for w in windows if w.quota_type == "WEEKLY"), None)
        current = boundary(weekly.reset_at) if weekly else None
        if not current:
            return
        with self.repository.db.connect() as conn:
            conn.execute(
                "UPDATE weekly_pings SET next_reset_at=? WHERE status='SENT' AND next_reset_at IS NULL AND reset_at < ?",
                (current.isoformat(), current.isoformat()),
            )
