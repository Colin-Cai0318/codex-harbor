from datetime import UTC, datetime

from codex_harbor.domain import QuotaWindow
from codex_harbor.quota import CodexQuotaProvider, FakeQuotaProvider
from codex_harbor.quota.manager import weekly_window_changed


def test_weekly_reset_requires_window_and_reset_advance():
    previous = {"window_id": "week-1", "reset_at": "2026-09-01T00:00:00+00:00"}
    current = QuotaWindow(
        "WEEKLY", window_id="week-2", reset_at="2026-09-08T00:00:00+00:00"
    )
    assert weekly_window_changed(
        previous, current, observed_at=datetime(2026, 9, 1, tzinfo=UTC)
    )
    current.window_id = "week-1"
    assert not weekly_window_changed(
        previous, current, observed_at=datetime(2026, 9, 1, tzinfo=UTC)
    )


def test_zero_usage_alone_is_not_a_reset():
    previous = {"window_id": "week-1", "reset_at": "2026-09-01T00:00:00+00:00"}
    current = QuotaWindow(
        "WEEKLY", used_percent=0, window_id="week-1", reset_at=previous["reset_at"]
    )
    assert not weekly_window_changed(previous, current)


def test_future_reset_revision_is_not_a_weekly_reset():
    previous = {
        "window_id": "week-old-estimate",
        "reset_at": "2026-09-05T23:50:00+00:00",
    }
    current = QuotaWindow(
        "WEEKLY", window_id="week-new-estimate", reset_at="2026-09-05T23:52:00+00:00"
    )
    assert not weekly_window_changed(
        previous, current, observed_at=datetime(2026, 8, 30, tzinfo=UTC)
    )


def test_fake_provider_exhausts_only_requested_window():
    provider = FakeQuotaProvider(
        [QuotaWindow("PRIMARY_5H"), QuotaWindow("WEEKLY")]
    )

    provider.exhaust("PRIMARY_5H", seconds=30)

    primary, weekly = provider.windows
    assert not primary.available
    assert primary.used_percent == 100
    assert primary.remaining == 0
    assert datetime.fromisoformat(primary.reset_at) > datetime.now(UTC)
    assert weekly.available


class RateLimitClientStub:
    def __init__(self, response):
        self.response = response

    async def rate_limits(self):
        return self.response


async def test_codex_provider_maps_primary_limit_and_weekly_remaining():
    provider = CodexQuotaProvider(
        RateLimitClientStub(
            {
                "rateLimits": {
                    "rateLimitReachedType": "primary",
                    "spendControlReached": False,
                    "primary": {
                        "usedPercent": 100,
                        "resetsAt": 1788147002,
                        "windowDurationMins": 300,
                    },
                    "secondary": {
                        "usedPercent": 57,
                        "resetsAt": 1788652331,
                        "windowDurationMins": 10080,
                    },
                }
            }
        )
    )

    primary, weekly = await provider.snapshot()

    assert primary.quota_type == "PRIMARY_5H"
    assert not primary.available
    assert primary.remaining == 0
    assert primary.window_id == "PRIMARY_5H:1788147002:300"
    assert primary.reset_at == "2026-08-31T03:30:02+00:00"
    assert weekly.quota_type == "WEEKLY"
    assert weekly.available
    assert weekly.remaining == 43
    assert weekly.source == "account/rateLimits/read"


async def test_codex_provider_spend_control_blocks_all_present_windows():
    provider = CodexQuotaProvider(
        RateLimitClientStub(
            {
                "rateLimits": {
                    "spendControlReached": True,
                    "primary": {"usedPercent": 1},
                    "secondary": {"usedPercent": 2},
                }
            }
        )
    )

    windows = await provider.snapshot()

    assert len(windows) == 2
    assert all(not window.available for window in windows)
    assert all(window.reset_at is None for window in windows)
