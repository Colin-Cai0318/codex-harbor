from datetime import UTC, datetime

from codex_harbor.domain import QuotaWindow
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
