from __future__ import annotations

from datetime import UTC, datetime

from ..domain import PoolStatus, TaskStatus
from ..storage.repository import HarborRepository
from .provider import QuotaProvider


def weekly_window_changed(
    previous: dict | None, current: object, *, observed_at: datetime | None = None
) -> bool:
    if not previous:
        return False
    old_id = previous.get("window_id")
    new_id = getattr(current, "window_id", None)
    old_reset = previous.get("reset_at")
    new_reset = getattr(current, "reset_at", None)
    if not (
        old_id
        and new_id
        and old_id != new_id
        and old_reset
        and new_reset
        and new_reset > old_reset
    ):
        return False
    try:
        old_boundary = datetime.fromisoformat(old_reset)
    except (TypeError, ValueError):
        return False
    observation = observed_at or datetime.now(UTC)
    if old_boundary.tzinfo is None:
        old_boundary = old_boundary.replace(tzinfo=UTC)
    # Providers may revise a future reset estimate or switch quota buckets.
    # A real reset cannot be declared until the old boundary was actually crossed.
    return observation >= old_boundary


class QuotaManager:
    def __init__(self, repository: HarborRepository, provider: QuotaProvider):
        self.repository = repository
        self.provider = provider

    async def refresh(self) -> list:
        previous = {
            row["quota_type"]: row
            for row in self.repository.list_quotas()
            if row["provider"] == self.provider.name
        }
        windows = await self.provider.snapshot()
        for window in windows:
            self.repository.save_quota(self.provider.name, window)
        weekly = next(
            (window for window in windows if window.quota_type == "WEEKLY"), None
        )
        pool = self.repository.get_pool()
        if (
            weekly
            and bool(pool["freeze_on_weekly_reset"])
            and pool["state"] == PoolStatus.RUNNING
            and weekly_window_changed(previous.get("WEEKLY"), weekly)
        ):
            self.repository.begin_weekly_drain(
                weekly.window_id or weekly.reset_at or "unknown"
            )
        return windows

    def release_quota_waiters(self) -> int:
        quotas = self.repository.list_quotas()
        if not quotas or any(not bool(item["available"]) for item in quotas):
            return 0
        now = datetime.now(UTC).isoformat()
        changed = 0
        for task in self.repository.list_tasks([TaskStatus.WAIT_QUOTA]):
            if not task.get("resume_at") or task["resume_at"] <= now:
                self.repository.transition(task["id"], TaskStatus.READY)
                changed += 1
        return changed
