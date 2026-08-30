from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import Any

from ..codex.app_server_client import AppServerClient
from ..domain import QuotaWindow


class QuotaProvider(ABC):
    name = "base"

    @abstractmethod
    async def snapshot(self) -> list[QuotaWindow]:
        raise NotImplementedError


class FakeQuotaProvider(QuotaProvider):
    name = "fake"

    def __init__(self, windows: list[QuotaWindow] | None = None):
        self.windows = windows or [QuotaWindow("PRIMARY_5H"), QuotaWindow("WEEKLY")]

    async def snapshot(self) -> list[QuotaWindow]:
        return self.windows

    def exhaust(self, quota_type: str, seconds: int = 60) -> None:
        reset = (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat()
        for window in self.windows:
            if window.quota_type == quota_type:
                window.available = False
                window.used_percent = 100
                window.remaining = 0
                window.reset_at = reset


def _iso_from_epoch(value: Any) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(int(value), tz=UTC).isoformat()


class CodexQuotaProvider(QuotaProvider):
    name = "codex"

    def __init__(self, client: AppServerClient):
        self.client = client

    async def snapshot(self) -> list[QuotaWindow]:
        response = await self.client.rate_limits()
        snapshot = response.get("rateLimits", {})
        reached = bool(snapshot.get("rateLimitReachedType"))
        spend_control = bool(snapshot.get("spendControlReached"))
        result: list[QuotaWindow] = []
        for key, quota_type in (("primary", "PRIMARY_5H"), ("secondary", "WEEKLY")):
            raw = snapshot.get(key)
            if not raw:
                continue
            reset_at = _iso_from_epoch(raw.get("resetsAt"))
            duration = raw.get("windowDurationMins")
            window_id = f"{quota_type}:{raw.get('resetsAt')}:{duration}"
            used = float(raw.get("usedPercent", 0))
            result.append(
                QuotaWindow(
                    quota_type=quota_type,
                    available=not spend_control
                    and used < 100
                    and not (reached and key == "primary"),
                    used_percent=used,
                    remaining=max(0.0, 100.0 - used),
                    reset_at=reset_at,
                    window_id=window_id,
                    source="account/rateLimits/read",
                )
            )
        return result
