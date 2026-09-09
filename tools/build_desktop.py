"""Build a self-contained desktop directory; run with the bundle/desktop extras."""

import os
import subprocess
import sys
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

root = Path(__file__).resolve().parents[1]
build = root / "build" / "desktop"
build.mkdir(parents=True, exist_ok=True)
app = QGuiApplication([])
canvas = QImage(256, 256, QImage.Format.Format_ARGB32)
canvas.fill(Qt.GlobalColor.transparent)
painter = QPainter(canvas)
QSvgRenderer(str(root / "src/codex_harbor/assets/harbor.svg")).render(painter)
painter.end()
canvas.save(str(build / "harbor.png"))
Image.open(build / "harbor.png").save(
    build / "harbor.ico",
    sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
)
subprocess.run(
    [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--windowed",
        "--onedir",
        "--name",
        "CodexHarbor",
        "--icon",
        str(build / "harbor.ico"),
        "--specpath",
        str(build),
        "--workpath",
        str(build / "work"),
        "--distpath",
        str(root / "dist"),
        "--collect-data",
        "codex_harbor",
        "--collect-submodules",
        "uvicorn",
        "--copy-metadata",
        "codex-harbor",
        str(root / "tools/desktop_entry.py"),
    ],
    cwd=root,
    check=True,
)

# Qt on Windows uses the OS ICU ABI (unsuffixed ucnv_* exports). A Poppler/Git
# installation on PATH can trick PyInstaller into collecting a different ICU
# under the same filename. Keep the OS library out of our private search path.
if os.name == "nt":
    runtime_dir = (root / "dist" / "CodexHarbor" / "_internal").resolve()
    icu_shadow = runtime_dir / "icuuc.dll"
    assert icu_shadow.resolve().parent == runtime_dir
    icu_shadow.unlink(missing_ok=True)
