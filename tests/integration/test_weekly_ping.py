import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from codex_harbor.api import create_app
from codex_harbor.domain import QuotaWindow, RuntimeTurnResult
from codex_harbor.quota.weekly_ping import WeeklyPingManager

NOW = datetime(2026, 9, 8, tzinfo=UTC)


def windows(reset=NOW, available=True):
    return [
        QuotaWindow("PRIMARY_5H", available=available),
        QuotaWindow("WEEKLY", reset_at=reset.isoformat() if reset else None),
    ]


def manager(repository):
    sender = AsyncMock(
        return_value=RuntimeTurnResult("ping-thread", "ping-turn", "completed")
    )
    return WeeklyPingManager(repository, sender=sender), sender


async def test_default_off_and_future_revision(repository):
    ping, send = manager(repository)
    await ping.tick(windows(), now=NOW)
    send.assert_not_awaited()
    ping.set_enabled(True)
    await ping.tick(windows(NOW + timedelta(days=1)), now=NOW)
    await ping.tick(windows(NOW + timedelta(days=2)), now=NOW + timedelta(hours=1))
    send.assert_not_awaited()
    assert ping.settings()["observed_reset"] == (NOW + timedelta(days=2)).isoformat()


async def test_boundary_sends_once_across_restart_and_toggle(repository):
    ping, send = manager(repository)
    ping.set_enabled(True)
    await ping.tick(windows(), now=NOW - timedelta(seconds=1))
    await ping.tick(windows(), now=NOW)
    restarted = WeeklyPingManager(repository, sender=send)
    await restarted.tick(windows(), now=NOW)
    restarted.set_enabled(False)
    restarted.set_enabled(True)
    await restarted.tick(windows(), now=NOW)
    send.assert_awaited_once()
    assert restarted.settings()["last_ping"]["status"] == "SENT"
    assert restarted.settings()["last_ping"]["next_reset_at"] is None
    new = windows(NOW + timedelta(days=7))
    restarted.observe_confirmation(new)
    await restarted.tick(new, now=NOW + timedelta(seconds=5))
    assert restarted.settings()["last_ping"]["next_reset_at"] == new[1].reset_at
    send.assert_awaited_once()
    await restarted.tick(new, now=NOW + timedelta(days=7))
    assert send.await_count == 2


async def test_fresh_available_quota_required_and_offline_catchup(repository):
    ping, send = manager(repository)
    ping.set_enabled(True)
    await ping.tick(windows(), now=NOW - timedelta(seconds=1))
    await ping.tick([], now=NOW)
    await ping.tick(windows(available=False), now=NOW)
    send.assert_not_awaited()
    await ping.tick(windows(NOW + timedelta(days=7)), now=NOW + timedelta(hours=1))
    send.assert_awaited_once()


async def test_expired_window_can_become_null_until_first_message(repository):
    ping, send = manager(repository)
    ping.set_enabled(True)
    await ping.tick(windows(), now=NOW - timedelta(seconds=1))
    await ping.tick(windows(None), now=NOW)
    send.assert_awaited_once()


@pytest.mark.parametrize("error", [TimeoutError(), RuntimeError("delivery unknown")])
async def test_uncertain_failure_never_repeats(repository, error):
    ping, send = manager(repository)
    send.side_effect = error
    ping.set_enabled(True)
    await ping.tick(windows(), now=NOW)
    await WeeklyPingManager(repository, sender=send).tick(windows(), now=NOW)
    send.assert_awaited_once()
    assert ping.settings()["last_ping"]["status"] == "FAILED"


async def test_concurrent_ticks_claim_once(repository):
    ping, send = manager(repository)
    ping.set_enabled(True)
    await asyncio.gather(ping.tick(windows(), now=NOW), ping.tick(windows(), now=NOW))
    send.assert_awaited_once()


async def test_reset_timestamp_jitter_does_not_send_twice(repository):
    ping, send = manager(repository)
    ping.set_enabled(True)
    await ping.tick(windows(), now=NOW)
    await ping.tick(windows(NOW + timedelta(seconds=1)), now=NOW + timedelta(seconds=2))
    ping.set_enabled(False)
    ping.set_enabled(True)
    await ping.tick(windows(NOW + timedelta(seconds=1)), now=NOW + timedelta(seconds=2))
    send.assert_awaited_once()


async def test_small_reset_revision_is_not_timer_confirmation(repository):
    ping, _ = manager(repository)
    ping.set_enabled(True)
    await ping.tick(windows(), now=NOW)
    ping.observe_confirmation(windows(NOW + timedelta(seconds=1)), now=NOW)
    assert ping.settings()["last_ping"]["next_reset_at"] is None


async def test_expired_next_boundary_is_not_timer_confirmation(repository):
    ping, _ = manager(repository)
    ping.set_enabled(True)
    await ping.tick(windows(), now=NOW)
    ping.observe_confirmation(
        windows(NOW + timedelta(days=7)), now=NOW + timedelta(days=8)
    )
    assert ping.settings()["last_ping"]["next_reset_at"] is None


async def test_slow_ping_does_not_block_scheduler_and_shutdown(
    repository, config_values, tmp_path
):
    from unittest.mock import Mock

    from codex_harbor.domain import PoolStatus
    from codex_harbor.scheduler import Scheduler

    repository.set_pool(PoolStatus.FROZEN)
    quota = Mock()
    quota.refresh = AsyncMock(
        return_value=windows(datetime.now(UTC) - timedelta(seconds=1))
    )
    scheduler = Scheduler(
        repository, object(), object(), quota, Mock(), config_values, tmp_path
    )
    ping, send = manager(repository)
    ping.set_enabled(True)
    started = asyncio.Event()

    async def slow(*args):
        started.set()
        await asyncio.Event().wait()

    send.side_effect = slow
    scheduler.weekly_ping = ping
    try:
        await asyncio.wait_for(scheduler.tick(), timeout=0.5)
        await asyncio.wait_for(started.wait(), timeout=0.5)
        await asyncio.wait_for(scheduler.tick(), timeout=0.5)
        send.assert_awaited_once()
    finally:
        await asyncio.wait_for(scheduler.stop(), timeout=0.5)


def test_api_persists_switch_and_preserves_reserve(repository):
    client = TestClient(create_app(repository), base_url="http://127.0.0.1")
    assert client.get("/api/weekly-ping").json()["enabled"] is False
    assert (
        client.patch("/api/weekly-ping", json={"enabled": True}).json()["model"]
        == "gpt-5.6-luna"
    )
    assert (
        TestClient(create_app(repository), base_url="http://127.0.0.1").get("/api/weekly-ping").json()["enabled"]
        is True
    )
    assert client.get("/api/recovery-settings").json()["allow_luna_reserve"] is False
    assert client.patch("/api/weekly-ping", json={}).status_code == 422
    assert 'id="weeklyPing"' in client.get("/").text


async def test_cancelled_delivery_keeps_durable_claim(repository):
    ping, send = manager(repository)
    ping.set_enabled(True)
    send.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await ping.tick(windows(), now=NOW)
    assert ping.settings()["last_ping"]["status"] == "STARTED"
    await WeeklyPingManager(repository, sender=send).tick(windows(), now=NOW)
    send.assert_awaited_once()


async def test_sender_uses_luna_low_readonly_and_closes_on_failure(
    monkeypatch, tmp_path
):
    from types import SimpleNamespace

    from codex_harbor.quota import weekly_ping

    client = AsyncMock()
    client.__aenter__.return_value = client
    client.model_list.return_value = [
        {
            "model": "gpt-5.6-luna",
            "supportedReasoningEfforts": [{"reasoningEffort": "low"}],
        }
    ]
    client.thread_start.return_value = {"thread": {"id": "ping"}}
    client.turn_start.return_value = {"turn": {"id": "turn"}}
    client.wait_turn.return_value = {"status": "failed", "error": "quota"}
    monkeypatch.setattr(weekly_ping, "AppServerClient", lambda *a, **kw: client)
    with pytest.raises(RuntimeError, match="quota"):
        await weekly_ping.send_weekly_ping(
            SimpleNamespace(executable="codex", request_timeout=30), tmp_path
        )
    assert client.thread_start.call_args.kwargs["sandbox"] == "read-only"
    assert client.turn_start.call_args.kwargs["model"] == "gpt-5.6-luna"
    assert client.turn_start.call_args.kwargs["effort"] == "low"
    client.__aexit__.assert_awaited_once()


async def test_frozen_pool_sends_but_failed_refresh_does_not(
    repository, config_values, tmp_path
):
    from unittest.mock import Mock

    from codex_harbor.domain import PoolStatus
    from codex_harbor.scheduler import Scheduler

    repository.set_pool(PoolStatus.FROZEN)
    quota = Mock()
    quota.refresh = AsyncMock(
        return_value=windows(datetime.now(UTC) - timedelta(seconds=1))
    )
    scheduler = Scheduler(
        repository, object(), object(), quota, Mock(), config_values, tmp_path
    )
    ping, send = manager(repository)
    ping.set_enabled(True)
    scheduler.weekly_ping = ping
    quota.refresh.side_effect = RuntimeError("offline")
    await scheduler.tick()
    send.assert_not_awaited()
    quota.refresh.side_effect = None
    await scheduler.tick()
    await scheduler.weekly_ping_task
    send.assert_awaited_once()
    assert repository.get_pool()["state"] == PoolStatus.FROZEN
