from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from codex_harbor import cli


@pytest.mark.parametrize("failure", ["start", "models"])
async def test_cli_initialization_failure_closes_client(monkeypatch, failure):
    client = AsyncMock()
    load = AsyncMock(return_value=object())
    if failure == "start":
        client.start.side_effect = RuntimeError("startup")
    else:
        load.side_effect = RuntimeError("models")
    monkeypatch.setattr(cli, "AppServerClient", lambda *_a: client)
    monkeypatch.setattr(cli.ModelRegistry, "load", load)
    container = SimpleNamespace(config=SimpleNamespace(section=lambda _key: {}))
    with pytest.raises(RuntimeError):
        await cli._runtime_parts(container)
    client.close.assert_awaited_once()


async def test_cli_uses_isolated_worker_connections(monkeypatch):
    client = AsyncMock()
    monkeypatch.setattr(cli, "AppServerClient", lambda *_a: client)
    monkeypatch.setattr(cli.ModelRegistry, "load", AsyncMock(return_value=object()))
    container = SimpleNamespace(config=SimpleNamespace(section=lambda _key: {}))
    _, _, runtime = await cli._runtime_parts(container)
    assert runtime.isolated_workers


async def test_cli_scheduler_closes_after_stop_failure(monkeypatch, tmp_path):
    client = AsyncMock()
    scheduler = SimpleNamespace(
        run_forever=AsyncMock(), stop=AsyncMock(side_effect=RuntimeError("stop"))
    )
    monkeypatch.setattr(
        cli, "_runtime_parts", AsyncMock(return_value=(client, object(), object()))
    )
    monkeypatch.setattr(cli, "Scheduler", lambda *a: scheduler)
    container = SimpleNamespace(
        repository=object(),
        config=SimpleNamespace(
            values={"scheduler": {"stale_worker_seconds": 45}}, data_dir=tmp_path
        ),
    )
    with pytest.raises(RuntimeError, match="stop"):
        await cli._run_scheduler(container)
    scheduler.stop.assert_awaited_once()
    client.close.assert_awaited_once()
