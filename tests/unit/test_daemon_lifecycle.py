from __future__ import annotations

from types import SimpleNamespace

import pytest

from codex_harbor import daemon


@pytest.mark.asyncio
@pytest.mark.parametrize("server_error", [None, RuntimeError("bind failed")])
async def test_daemon_coordinates_scheduler_shutdown(monkeypatch, tmp_path, server_error):
    events = []
    values = {
        "codex": {"approval_policy": "never", "sandbox": "workspace-write"},
        "scheduler": {"stale_worker_seconds": 45},
        "harbor": {"bind": "127.0.0.1", "port": 8765},
        "quota": {},
        "profiles": {},
    }
    container = SimpleNamespace(
        config=SimpleNamespace(values=values, data_dir=tmp_path),
        repository=object(),
    )
    monkeypatch.setattr(daemon.ApplicationContainer, "build", lambda _path: container)

    class Client:
        async def __aenter__(self):
            events.append("client-enter")
            return self

        async def __aexit__(self, *_args):
            events.append("client-exit")

    monkeypatch.setattr(daemon, "AppServerClient", lambda *_args, **_kwargs: Client())

    async def load(_client):
        return object()

    monkeypatch.setattr(daemon.ModelRegistry, "load", load)

    class FakeScheduler:
        def __init__(self, *_args, **_kwargs):
            self.stopping = False

        async def run_forever(self):
            events.append("scheduler-run")
            while not self.stopping:
                await daemon.asyncio.sleep(0)

        async def stop(self):
            events.append("scheduler-stop")

    monkeypatch.setattr(daemon, "Scheduler", FakeScheduler)
    monkeypatch.setattr(daemon, "create_app", lambda *_args, **_kwargs: object())

    class Server:
        def __init__(self, _config):
            pass

        async def serve(self):
            await daemon.asyncio.sleep(0)
            if server_error:
                raise server_error
            events.append("server-served")

    monkeypatch.setattr(daemon.uvicorn, "Config", lambda *args, **kwargs: (args, kwargs))
    monkeypatch.setattr(daemon.uvicorn, "Server", Server)

    if server_error:
        with pytest.raises(RuntimeError, match="bind failed"):
            await daemon.serve("test.toml")
    else:
        await daemon.serve("test.toml")
    assert events[-2:] == ["scheduler-stop", "client-exit"]
    assert "scheduler-run" in events
