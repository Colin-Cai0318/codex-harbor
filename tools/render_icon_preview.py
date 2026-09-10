"""Render the source SVG on both application backgrounds for README/visual QA."""

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

root = Path(__file__).resolve().parents[1]
app = QGuiApplication([])
canvas = QImage(1000, 380, QImage.Format.Format_ARGB32)
painter = QPainter(canvas)
painter.setRenderHint(QPainter.RenderHint.Antialiasing)
renderer = QSvgRenderer(str(root / "src/codex_harbor/assets/harbor.svg"))
assert renderer.isValid()
for left, background, foreground, label in [
    (0, "#f5f7f6", "#28554f", "LIGHT"),
    (500, "#151d1b", "#dce9df", "DARK"),
]:
    painter.fillRect(left, 0, 500, 380, QColor(background))
    painter.setPen(QColor(foreground))
    painter.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
    painter.drawText(
        QRectF(left + 30, 20, 440, 25), Qt.AlignmentFlag.AlignCenter, label
    )
    renderer.render(painter, QRectF(left + 186, 62, 128, 128))
    painter.setFont(QFont("Segoe UI", 18, QFont.Weight.DemiBold))
    painter.drawText(
        QRectF(left, 210, 500, 34), Qt.AlignmentFlag.AlignCenter, "Codex Harbor"
    )
    for x, size in [(164, 16), (204, 24), (252, 32), (308, 48)]:
        renderer.render(
            painter, QRectF(left + x - size / 2, 302 - size / 2, size, size)
        )
    painter.setFont(QFont("Segoe UI", 9))
    painter.drawText(
        QRectF(left, 338, 500, 24), Qt.AlignmentFlag.AlignCenter, "16 / 24 / 32 / 48 px"
    )
painter.end()
destination = root / "docs/images/anchor-preview.png"
destination.parent.mkdir(parents=True, exist_ok=True)
assert canvas.save(str(destination))
print(destination)
