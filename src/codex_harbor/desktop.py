"""Optional native desktop host. The scheduler survives hiding the window."""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

from .config import load_config


def bundled_dashboard() -> str:
    """Use the installed UI even when attaching to an already-running daemon."""
    from .api.dashboard import DASHBOARD

    assets = Path(__file__).parent / "assets"
    page = DASHBOARD.replace(
        '<link rel="stylesheet" href="/assets/desktop.css">',
        "<style>" + (assets / "desktop.css").read_text(encoding="utf-8") + "</style>",
    )
    page = page.replace(
        '<script src="/assets/desktop.js"></script>',
        "<script>" + (assets / "desktop.js").read_text(encoding="utf-8") + "</script>",
    )
    icon = base64.b64encode((assets / "harbor.svg").read_bytes()).decode("ascii")
    return page.replace("/assets/harbor.svg", "data:image/svg+xml;base64," + icon)


def desktop_command(config_path: str | None = None) -> list[str]:
    executable = Path(sys.executable)
    if not getattr(sys, "frozen", False) and os.name == "nt":
        executable = executable.with_name("pythonw.exe")
    command = [str(executable)]
    if not getattr(sys, "frozen", False):
        command += ["-m", "codex_harbor.desktop"]
    if config_path:
        command += ["--config", str(Path(config_path).resolve())]
    return command + ["--background"]


def set_autostart(enabled: bool, config_path: str | None = None) -> None:
    if os.name != "nt":
        raise OSError("当前版本仅在 Windows 支持登录后自动启动。")
    import winreg

    with winreg.CreateKey(
        winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"
    ) as key:
        if enabled:
            winreg.SetValueEx(
                key,
                "CodexHarbor",
                0,
                winreg.REG_SZ,
                subprocess.list2cmdline(desktop_command(config_path)),
            )
        else:
            try:
                winreg.DeleteValue(key, "CodexHarbor")
            except FileNotFoundError:
                pass


def autostart_enabled() -> bool:
    if os.name != "nt":
        return False
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"
        ) as key:
            return bool(winreg.QueryValueEx(key, "CodexHarbor")[0])
    except FileNotFoundError:
        return False


async def run_service(config_path: str | None, stop: threading.Event) -> None:
    from .daemon import serve

    service = asyncio.create_task(serve(config_path))
    try:
        while not stop.is_set() and not service.done():
            await asyncio.sleep(0.2)
        if service.done():
            service.result()
    finally:
        service.cancel()
        await asyncio.gather(service, return_exceptions=True)


def main() -> (
    None
):  # pragma: no cover - exercised by tools/verify_desktop.py in real Qt
    parser = argparse.ArgumentParser(description="Codex Harbor desktop")
    parser.add_argument("--config")
    parser.add_argument("--background", action="store_true")
    args = parser.parse_args()
    try:
        from PySide6.QtCore import QThread, QTimer, QUrl, Signal
        from PySide6.QtGui import QAction, QDesktopServices, QIcon
        from PySide6.QtNetwork import (
            QLocalServer,
            QLocalSocket,
            QNetworkAccessManager,
            QNetworkReply,
            QNetworkRequest,
        )
        from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWidgets import (
            QApplication,
            QLabel,
            QMainWindow,
            QMenu,
            QMessageBox,
            QPushButton,
            QStackedWidget,
            QSystemTrayIcon,
            QVBoxLayout,
            QWidget,
        )
    except ImportError as error:
        raise SystemExit("请先安装桌面依赖：uv sync --extra desktop") from error

    config = load_config(args.config)
    config.ensure_layout()
    # GUI entry points have no console streams; uvicorn logging needs a file.
    if sys.stdout is None:
        sys.stdout = open(
            config.data_dir / "logs" / "desktop.log", "a", encoding="utf-8", buffering=1
        )
    if sys.stderr is None:
        sys.stderr = sys.stdout
    host = config.section("harbor")["bind"]
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("桌面应用仅支持本机回环地址。")
    url = f"http://{'[::1]' if host == '::1' else host}:{int(config.section('harbor')['port'])}"
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Codex Harbor")
    app.setOrganizationName("CodexHarbor")
    app.setQuitOnLastWindowClosed(False)
    icon = QIcon(str(Path(__file__).parent / "assets" / "harbor.svg"))
    app.setWindowIcon(icon)
    instance_name = (
        "codex-harbor-"
        + hashlib.sha256(str(config.data_dir).lower().encode()).hexdigest()[:20]
    )
    peer = QLocalSocket()
    peer.connectToServer(instance_name)
    if peer.waitForConnected(500):
        peer.write(b"show")
        peer.waitForBytesWritten(500)
        peer.disconnectFromServer()
        return
    instance = QLocalServer()
    instance.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    if not instance.listen(instance_name):
        QMessageBox.warning(
            None, "Codex Harbor", "另一个桌面实例正在启动。请稍后从托盘打开。"
        )
        return

    class Service(QThread):
        failed = Signal(str)

        def __init__(self):
            super().__init__()
            self.stop_event = threading.Event()

        def run(self):
            try:
                asyncio.run(
                    run_service(
                        str(config.source) if config.source else None, self.stop_event
                    )
                )
            except BaseException as error:  # noqa: BLE001 - deliver worker failures, including uvicorn SystemExit, to the GUI
                self.failed.emit(str(error))

    class LocalPage(QWebEnginePage):
        def acceptNavigationRequest(self, target, kind, main_frame):
            if target.scheme() in {"about", "data"} or (
                target.scheme(),
                target.host(),
                target.port(),
            ) == ("http", host, int(config.section("harbor")["port"])):
                return True
            if (
                kind == QWebEnginePage.NavigationType.NavigationTypeLinkClicked
                and target.scheme() in {"http", "https"}
            ):
                QDesktopServices.openUrl(target)
            return False

    class Window(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Codex Harbor · 代码港")
            self.resize(1320, 880)
            self.setMinimumSize(820, 600)
            self.service = None
            self.quitting = False
            self.ready = False
            self.checking = False
            self.health_path = "/api/health"
            self.stack = QStackedWidget()
            self.setCentralWidget(self.stack)
            landing = QWidget()
            layout = QVBoxLayout(landing)
            layout.setContentsMargins(64, 64, 64, 64)
            layout.addStretch()
            title = QLabel("Codex Harbor")
            title.setStyleSheet("font-size:36px;font-weight:600;color:#173d3b")
            layout.addWidget(title)
            self.message = QLabel("正在连接你的代码港…")
            self.message.setWordWrap(True)
            layout.addWidget(self.message)
            self.retry = QPushButton("重新连接")
            self.retry.clicked.connect(self.check_service)
            layout.addWidget(self.retry)
            logs = QPushButton("打开日志目录")
            logs.clicked.connect(
                lambda: QDesktopServices.openUrl(
                    QUrl.fromLocalFile(str(config.data_dir / "logs"))
                )
            )
            layout.addWidget(logs)
            layout.addStretch()
            self.stack.addWidget(landing)
            self.profile = QWebEngineProfile("harbor-desktop", self)
            self.profile.setHttpAcceptLanguage("zh-CN,zh;q=0.9,en;q=0.8")
            self.profile.setPersistentStoragePath(
                str(config.data_dir / "desktop" / "web")
            )
            self.profile.setCachePath(str(config.data_dir / "desktop" / "cache"))
            self.web = QWebEngineView()
            self.web.setPage(LocalPage(self.profile, self.web))
            self.web.loadFinished.connect(self.page_loaded)
            self.stack.addWidget(self.web)
            self.network = QNetworkAccessManager(self)
            self.tray = QSystemTrayIcon(icon, self)
            self.tray.setToolTip("Codex Harbor · 正在连接")
            menu = QMenu(self)
            menu.addAction("打开 Codex Harbor", self.reveal)
            menu.addSeparator()
            self.pool_actions = []
            for label, action in [
                ("暂停新任务", "pause"),
                ("恢复调度", "resume"),
                ("冻结调度", "freeze"),
            ]:
                entry = menu.addAction(
                    label, lambda checked=False, action=action: self.pool_action(action)
                )
                entry.setEnabled(False)
                self.pool_actions.append(entry)
            menu.addSeparator()
            startup = QAction("登录 Windows 后自动启动", self)
            startup.setCheckable(True)
            startup.setChecked(autostart_enabled())
            startup.setEnabled(os.name == "nt")

            def change_startup(enabled):
                try:
                    set_autostart(
                        enabled, str(config.source) if config.source else None
                    )
                except OSError as error:
                    startup.blockSignals(True)
                    startup.setChecked(not enabled)
                    startup.blockSignals(False)
                    QMessageBox.warning(self, "自动启动设置失败", str(error))

            startup.toggled.connect(change_startup)
            menu.addAction(startup)
            menu.addAction("在浏览器打开", lambda: QDesktopServices.openUrl(QUrl(url)))
            menu.addAction(
                "打开数据目录",
                lambda: QDesktopServices.openUrl(
                    QUrl.fromLocalFile(str(config.data_dir))
                ),
            )
            menu.addSeparator()
            menu.addAction("退出桌面应用", self.shutdown)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(
                lambda reason: (
                    self.reveal()
                    if reason
                    in {
                        QSystemTrayIcon.ActivationReason.Trigger,
                        QSystemTrayIcon.ActivationReason.DoubleClick,
                    }
                    else None
                )
            )
            self.tray.show()
            self.menuBar().addMenu("应用").addActions(menu.actions())
            self.poll = QTimer(self)
            self.poll.setInterval(3000)
            self.poll.timeout.connect(self.check_service)
            self.poll.start()
            QTimer.singleShot(0, self.check_service)

        def reveal(self):
            self.showNormal()
            self.raise_()
            self.activateWindow()

        def page_loaded(self, ok):
            if ok:
                self.stack.setCurrentIndex(1)
            else:
                self.ready = False
                self.message.setText("页面加载失败，请重新连接。")
                self.stack.setCurrentIndex(0)

        def check_service(self):
            if self.checking or self.quitting:
                return
            self.checking = True
            self.poll.start()
            request = QNetworkRequest(QUrl(url + self.health_path))
            request.setTransferTimeout(2000)
            reply = self.network.get(request)

            def completed():
                self.checking = False
                if (
                    reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
                    == 404
                    and self.health_path == "/api/health"
                ):
                    self.health_path = "/openapi.json"
                    reply.deleteLater()
                    self.check_service()
                    return
                try:
                    data = json.loads(bytes(reply.readAll()))
                    healthy = (
                        data.get("application") == "codex-harbor"
                        if self.health_path == "/api/health"
                        else (
                            data.get("info", {}).get("title") == "Codex Harbor"
                            and "/api/recovery-watches" in data.get("paths", {})
                        )
                    )
                except (ValueError, AttributeError):
                    healthy = False
                for action in self.pool_actions:
                    action.setEnabled(healthy)
                if healthy:
                    self.tray.setToolTip("Codex Harbor · 后台服务运行中")
                    if not self.ready:
                        self.ready = True
                        self.web.setHtml(bundled_dashboard(), QUrl(url + "/"))
                else:
                    self.ready = False
                    self.stack.setCurrentIndex(0)
                    self.tray.setToolTip("Codex Harbor · 服务未就绪")
                    if (
                        reply.error()
                        == QNetworkReply.NetworkError.ConnectionRefusedError
                        and self.service is None
                    ):
                        self.message.setText(
                            "正在启动后台服务，首次连接 Codex 可能需要一些时间…"
                        )
                        self.service = Service()
                        self.service.failed.connect(self.service_failed)
                        self.service.finished.connect(self.service_finished)
                        self.service.start()
                    elif self.service is None:
                        self.message.setText(
                            "该地址没有响应为 Harbor 服务。请检查端口、配置或先更新已运行的旧版服务。"
                        )
                reply.deleteLater()

            reply.finished.connect(completed)

        def service_failed(self, message):
            self.poll.stop()
            self.message.setText(
                "后台服务启动或运行失败：\n"
                + message
                + "\n请确认 Codex CLI 已安装并登录，再点击重新连接。"
            )
            self.stack.setCurrentIndex(0)

        def service_finished(self):
            self.service.deleteLater()
            self.service = None
            if self.quitting:
                self.tray.hide()
                app.quit()

        def pool_action(self, action):
            request = QNetworkRequest(QUrl(url + "/api/pool/" + action))
            reply = self.network.post(request, b"")

            def completed():
                if reply.error() != QNetworkReply.NetworkError.NoError:
                    self.tray.showMessage("操作失败", reply.errorString())
                else:
                    self.tray.showMessage(
                        "Codex Harbor",
                        {
                            "pause": "已暂停新任务，当前任务继续运行",
                            "resume": "已恢复调度",
                            "freeze": "已冻结调度",
                        }[action],
                    )
                reply.deleteLater()

            reply.finished.connect(completed)

        def closeEvent(self, event):
            event.ignore()
            if QSystemTrayIcon.isSystemTrayAvailable():
                self.hide()
                self.tray.showMessage(
                    "Codex Harbor", "已收起到系统托盘，后台任务继续运行。"
                )
            else:
                self.shutdown()

        def shutdown(self):
            if self.quitting:
                return
            if self.service is not None:
                answer = QMessageBox.question(
                    self,
                    "退出 Codex Harbor",
                    "退出将停止本应用启动的后台服务，运行中的任务会中断并在下次启动时恢复。只需后台运行请关闭窗口。\n\n确定退出？",
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return
            self.quitting = True
            self.poll.stop()
            if self.service is not None:
                self.message.setText("正在保存状态并停止后台服务…")
                self.stack.setCurrentIndex(0)
                self.reveal()
                self.service.stop_event.set()
            else:
                self.tray.hide()
                app.quit()

    window = Window()

    def activate_instance():
        while instance.hasPendingConnections():
            connection = instance.nextPendingConnection()
            connection.disconnectFromServer()
            connection.deleteLater()
        window.reveal()

    instance.newConnection.connect(activate_instance)
    if not args.background or not QSystemTrayIcon.isSystemTrayAvailable():
        window.show()
    app.exec()
    instance.close()


if __name__ == "__main__":
    main()
