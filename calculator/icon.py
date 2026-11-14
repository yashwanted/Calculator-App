"""The app icon, drawn in code so that no image files are needed."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPen, QPixmap



def make_app_icon() -> QIcon:
    """Draw the app icon: a coral tile with the four essential symbols."""
    size = 1024
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # macOS icons sit inside a margin and have generously rounded corners.
    tile = QRectF(100, 100, 824, 824)
    gradient = QLinearGradient(tile.topLeft(), tile.bottomRight())
    gradient.setColorAt(0.0, QColor("#FF9472"))
    gradient.setColorAt(1.0, QColor("#E2502E"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    painter.drawRoundedRect(tile, 186, 186)

    pen = QPen(QColor("#FFFFFF"), 62)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    arm = 82
    left, right, top, bottom = 340, 684, 340, 684
    # Plus.
    painter.drawLine(left - arm, top, left + arm, top)
    painter.drawLine(left, top - arm, left, top + arm)
    # Minus.
    painter.drawLine(right - arm, top, right + arm, top)
    # Times.
    diagonal = round(arm * 0.76)
    painter.drawLine(
        left - diagonal, bottom - diagonal, left + diagonal, bottom + diagonal
    )
    painter.drawLine(
        left - diagonal, bottom + diagonal, left + diagonal, bottom - diagonal
    )
    # Equals.
    painter.drawLine(right - arm, bottom - 50, right + arm, bottom - 50)
    painter.drawLine(right - arm, bottom + 50, right + arm, bottom + 50)
    painter.end()

    icon = QIcon()
    for edge in (16, 32, 64, 128, 256, 512, 1024):
        icon.addPixmap(
            pixmap.scaled(
                edge,
                edge,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
    return icon
