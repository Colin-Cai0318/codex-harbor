"""Check the frozen Windows app against an isolated API, without model turns."""

from __future__ import annotations

import io
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

import pefile
import uvicorn
from PIL import Image
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer, QUrl
from PySide6.QtWebSockets import QWebSocket

from codex_harbor.api import create_app
from codex_harbor.application import ApplicationContainer


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def evaluate(address, expression):
    connection = QWebSocket()
    loop = QEventLoop()
    result = []
    connection.connected.connect(
        lambda: connection.sendTextMessage(
            json.dumps(
                {
                    "id": 1,
                    "method": "Runtime.evaluate",
                    "params": {
                        "expression": expression,
                        "returnByValue": True,
                        "awaitPromise": True,
                    },
                }
            )
        )
    )

    def received(message):
        data = json.loads(message)
        if data.get("id") == 1:
            result.append(data)
            loop.quit()

    connection.textMessageReceived.connect(received)
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(10000)
    connection.open(QUrl(address))
    loop.exec()
    connection.close()
    assert result, "DevTools did not answer"
    assert "exceptionDetails" not in result[0].get("result", {}), result
    return result[0]["result"]["result"].get("value")


def main():
    root = Path(__file__).resolve().parents[1]
    # An SVG-only rebuild must also refresh Windows Explorer's embedded icon.
    expected = Image.open(root / "build/desktop/harbor.ico")
    embedded_sizes = set()
    with pefile.PE(str(root / "dist/CodexHarbor/CodexHarbor.exe")) as executable:
        for resource in executable.DIRECTORY_ENTRY_RESOURCE.entries:
            if resource.id != 3:  # RT_ICON
                continue
            for item in resource.directory.entries:
                entry = item.directory.entries[0].data.struct
                pixels = executable.get_data(entry.OffsetToData, entry.Size)
                icon = Image.open(io.BytesIO(pixels)).convert("RGBA")
                assert (
                    icon.tobytes()
                    == expected.ico.getimage(icon.size).convert("RGBA").tobytes()
                ), f"Stale embedded icon: {icon.size}"
                embedded_sizes.add(icon.size)
    assert embedded_sizes == expected.ico.sizes(), embedded_sizes
    app = QCoreApplication([])
    with tempfile.TemporaryDirectory(prefix="harbor-packaged-") as folder:
        port, debug_port = free_port(), free_port()
        config = Path(folder) / "config.toml"
        config.write_text(
            f"[harbor]\ndata_dir={json.dumps(folder)}\nport={port}\n", encoding="utf-8"
        )
        # Remove the health route to exercise attachment to a compatible older daemon.
        container = ApplicationContainer.build(str(config))
        api = create_app(container.repository)
        api.router.routes[:] = [
            route
            for route in api.router.routes
            if getattr(route, "path", "") != "/api/health"
        ]
        server = uvicorn.Server(
            uvicorn.Config(api, host="127.0.0.1", port=port, log_level="error")
        )
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        deadline = time.monotonic() + 15
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.1)
        assert server.started
        env = dict(os.environ, QTWEBENGINE_REMOTE_DEBUGGING=f"127.0.0.1:{debug_port}")
        env.pop("HARBOR_DATA_DIR", None)
        process = subprocess.Popen(
            [
                str(root / "dist/CodexHarbor/CodexHarbor.exe"),
                "--config",
                str(config),
                "--background",
            ],
            env=env,
        )
        try:
            tabs = []
            deadline = time.monotonic() + 35
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    log = Path(folder) / "logs" / "desktop.log"
                    raise AssertionError(
                        f"Packaged application exited {process.returncode}: "
                        + (
                            log.read_text(encoding="utf-8")
                            if log.exists()
                            else "no desktop log"
                        )
                    )
                try:
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{debug_port}/json/list", timeout=2
                    ) as response:
                        tabs = [
                            tab
                            for tab in json.load(response)
                            if tab.get("title") == "Codex Harbor"
                        ]
                    if tabs:
                        break
                except OSError:
                    pass
                time.sleep(0.3)
            assert tabs, "Packaged UI did not load"
            address = tabs[0]["webSocketDebuggerUrl"]
            value = evaluate(
                address,
                "({navigation:document.querySelectorAll('[data-page]').length, brand:document.querySelector('.brand').textContent.trim(), error:byId('errorNotice').textContent})",
            )
            assert value["navigation"] == 5, value
            assert not value["error"], value
            assert (
                evaluate(
                    address,
                    "request('/api/pool',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({max_workers:7})}).then(p=>p.max_workers)",
                )
                == 7
            )
            assert container.repository.get_pool()["max_workers"] == 7
            output = root / ".harbor/desktop-qa/packaged-result.json"
            output.write_text(
                json.dumps(
                    {
                        "passed": [
                            "embedded-icon-all-sizes",
                            "frozen-ui",
                            "legacy-service-attachment",
                            "same-origin-api-mutation",
                        ],
                        "ui": value,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            print(output.read_text(encoding="utf-8"))
        finally:
            # Only the test-created UI is stopped; its backend is this isolated server.
            process.terminate()
            process.wait(timeout=10)
            server.should_exit = True
            thread.join(timeout=10)
    app.quit()


if __name__ == "__main__":
    main()
