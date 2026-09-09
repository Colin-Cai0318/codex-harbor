from __future__ import annotations

import asyncio
import threading
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from codex_harbor import daemon, desktop


def test_bundled_ui_does_not_depend_on_daemon_assets():
    page = desktop.bundled_dashboard()
    assert "/assets/desktop.js" not in page
    assert "/assets/desktop.css" not in page
    assert "data:image/svg+xml;base64," in page
    assert "'/api/recovery-watches'" in page


def test_windows_login_startup_enable_and_disable(monkeypatch, tmp_path):
    values = {}

    def read(key, name):
        if name not in values:
            raise FileNotFoundError(name)
        return values[name], 1

    def remove(key, name):
        if name not in values:
            raise FileNotFoundError(name)
        del values[name]

    registry = SimpleNamespace(
        HKEY_CURRENT_USER=1,
        REG_SZ=1,
        CreateKey=lambda *args: nullcontext("user-key"),
        OpenKey=lambda *args: nullcontext("user-key"),
        SetValueEx=lambda key, name, reserved, kind, value: values.update(
            {name: value}
        ),
        QueryValueEx=read,
        DeleteValue=remove,
    )
    monkeypatch.setitem(desktop.sys.modules, "winreg", registry)
    monkeypatch.setattr(desktop, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(desktop.sys, "frozen", True, raising=False)
    monkeypatch.setattr(desktop.sys, "executable", str(tmp_path / "Harbor App.exe"))
    assert not desktop.autostart_enabled()
    desktop.set_autostart(True, str(tmp_path / "app config.toml"))
    assert desktop.autostart_enabled()
    assert "--background" in values["CodexHarbor"]
    assert "app config.toml" in values["CodexHarbor"]
    desktop.set_autostart(False)
    desktop.set_autostart(False)
    assert not desktop.autostart_enabled()


@pytest.mark.asyncio
async def test_desktop_stop_cleans_up_owned_service(monkeypatch):
    started = asyncio.Event()
    cleaned = []

    async def serve(path):
        assert path == "test.toml"
        try:
            started.set()
            await asyncio.Future()
        finally:
            cleaned.append(True)

    monkeypatch.setattr(daemon, "serve", serve)
    stop = threading.Event()
    task = asyncio.create_task(desktop.run_service("test.toml", stop))
    await started.wait()
    stop.set()
    await asyncio.wait_for(task, 2)
    assert cleaned == [True]


@pytest.mark.asyncio
async def test_desktop_reports_startup_failure(monkeypatch):
    async def serve(path):
        raise RuntimeError("Codex unavailable")

    monkeypatch.setattr(daemon, "serve", serve)
    with pytest.raises(RuntimeError, match="Codex unavailable"):
        await desktop.run_service(None, threading.Event())


def test_frozen_startup_keeps_config_path_as_one_argument(monkeypatch, tmp_path):
    monkeypatch.setattr(desktop.sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        desktop.sys, "executable", str(tmp_path / "App Space" / "Harbor.exe")
    )
    config = tmp_path / "Config Space" / "config.toml"
    command = desktop.desktop_command(str(config))
    assert command == [
        desktop.sys.executable,
        "--config",
        str(config.resolve()),
        "--background",
    ]
