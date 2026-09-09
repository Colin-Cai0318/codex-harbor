"""Real Qt/WebEngine smoke test with isolated storage and a fake local API.

No Codex turns are run. Screenshots and results go to .harbor/desktop-qa.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

import uvicorn
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMainWindow

from codex_harbor import daemon, desktop
from codex_harbor.api import create_app
from codex_harbor.application import ApplicationContainer

root = Path(__file__).resolve().parents[1]
output = root / ".harbor" / "desktop-qa"
output.mkdir(parents=True, exist_ok=True)
temporary = tempfile.TemporaryDirectory(
    prefix="harbor-desktop-", ignore_cleanup_errors=True
)
os.environ["HARBOR_DATA_DIR"] = temporary.name
with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
config = Path(temporary.name) / "config.toml"
config.write_text(f"[harbor]\nport={port}\n", encoding="utf-8")
sys.argv = ["harbor-desktop", "--config", str(config)]


class Client:
    async def project_list(self):
        return []


async def fake_serve(path):
    container = ApplicationContainer.build(path)
    app = create_app(container.repository, app_server_client=Client())
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    try:
        await server.serve()
    finally:
        await server.shutdown()


daemon.serve = fake_serve
original_exec = QApplication.exec
results = []
failed = []


def instrumented_exec(app):
    def fail(message):
        failed.append(message)
        finish()

    def finish():
        window = next(
            (w for w in app.topLevelWidgets() if isinstance(w, QMainWindow)), None
        )
        if window and window.service:
            window.quitting = True
            window.poll.stop()
            window.service.stop_event.set()
        else:
            app.quit()

    def check_js(expression, callback):
        window.web.page().runJavaScript(expression, callback)

    def stage(index=0):
        pages = ["tasks", "recovery", "repositories", "activity", "settings"]
        if index == len(pages):
            window.resize(860, 680)
            check_js(
                "document.querySelector('[data-page=tasks]').click(); applyTheme('dark');",
                lambda _: QTimer.singleShot(500, dark),
            )
            return
        page = pages[index]

        def capture():
            def checked(value):
                data = json.loads(value)
                if data["overflow"] or data["error"]:
                    fail(f"{page}: {data}")
                    return
                window.grab().save(str(output / (page + ".png")))
                results.append(page)
                stage(index + 1)

            check_js(
                "JSON.stringify({overflow:document.documentElement.scrollWidth>innerWidth,error:document.querySelector('#errorNotice').classList.contains('show'),page:document.querySelector('.page').dataset.currentPage})",
                checked,
            )

        check_js(
            f"document.querySelector('[data-page={page}]').click()",
            lambda _: QTimer.singleShot(650, capture),
        )

    def dark():
        window.grab().save(str(output / "dark-compact.png"))
        # Exercise hide/restore while the owned service remains alive.
        window.close()
        if window.tray.isSystemTrayAvailable() and window.isVisible():
            fail("Close did not hide the window")
            return
        if not window.service or not window.service.isRunning():
            fail("Hiding stopped the service")
            return
        window.reveal()
        results.append("tray-hide-restore")
        check_js(
            "document.querySelector('[data-page=settings]').click()",
            lambda _: QTimer.singleShot(300, check_settings),
        )

    def check_settings():
        check_js(
            "JSON.stringify({count:document.querySelectorAll('#maxWorkersInput').length,connected:document.querySelector('#maxWorkersInput').isConnected})",
            lambda value: complete(value),
        )

    def complete(value):
        if json.loads(value) != {"count": 1, "connected": True}:
            fail("Settings did not survive navigation: " + value)
            return
        results.append("settings-navigation")
        check_js(
            "byId('maxWorkersInput').value='5';byId('maxWorkersInput').dispatchEvent(new Event('change'));",
            lambda _: QTimer.singleShot(700, verify_mutation),
        )

    def verify_mutation():
        pool = ApplicationContainer.build(str(config)).repository.get_pool()
        if pool["max_workers"] != 5:
            fail("UI setting did not persist through the local API")
            return
        results.append("settings-api-persistence")
        window.hide()
        peer = subprocess.Popen(
            [sys.executable, "-m", "codex_harbor.desktop", "--config", str(config)],
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

        def verify_peer():
            if peer.poll() is None:
                QTimer.singleShot(200, verify_peer)
                return
            if peer.returncode != 0 or not window.isVisible():
                fail("Second launch did not activate the existing window")
                return
            results.append("single-instance-activation")
            finish()

        QTimer.singleShot(200, verify_peer)

    window = next(w for w in app.topLevelWidgets() if isinstance(w, QMainWindow))

    def wait_ready():
        if window.stack.currentIndex() == 1:
            QTimer.singleShot(600, stage)
        elif failed:
            return
        else:
            QTimer.singleShot(250, wait_ready)

    QTimer.singleShot(250, wait_ready)
    QTimer.singleShot(30000, lambda: fail("Timed out"))
    return original_exec()


QApplication.exec = instrumented_exec
desktop.main()
(output / "result.json").write_text(
    json.dumps({"passed": results, "failed": failed}, indent=2), encoding="utf-8"
)
print(json.dumps({"passed": results, "failed": failed}))
sys.exit(bool(failed))
