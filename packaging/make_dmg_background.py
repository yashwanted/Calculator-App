#!/usr/bin/env python3
"""Draw the disk image window background: an arrow from the app to Applications.

Usage: make_dmg_background.py OUTPUT.png
Writes OUTPUT.png and a Retina OUTPUT@2x.png, which dmgbuild combines.
"""

import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"  # No window is needed to draw it.

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QColor,
    QFont,
    QGuiApplication,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

# Window size in points. Keep in step with packaging/dmg_settings.py.
WIDTH, HEIGHT = 640, 400
APP_X, APPLICATIONS_X, ICON_Y = 170, 470, 180
ICON_SIZE = 128

BACKGROUND = "#F4F3F0"  # The app's light theme.
ARROW = "#E2502E"  # The icon's coral.
CAPTION = "#62656E"


def draw(scale: int) -> QPixmap:
    pixmap = QPixmap(WIDTH * scale, HEIGHT * scale)
    pixmap.fill(QColor(BACKGROUND))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(scale, scale)

    # A gently curved arrow between the two icons.
    gap = ICON_SIZE / 2 + 22
    start = QPointF(APP_X + gap, ICON_Y)
    end = QPointF(APPLICATIONS_X - gap, ICON_Y)
    control = QPointF((start.x() + end.x()) / 2, ICON_Y - 26)
    path = QPainterPath(start)
    path.quadTo(control, end)
    pen = QPen(QColor(ARROW), 5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)
    # The arrowhead follows the curve's direction where it ends.
    direction = QLineF(control, end).angle()
    head = QPainterPath()
    for side in (150, -150):
        barb = QLineF.fromPolar(18, direction + side).translated(end)
        head.moveTo(barb.p2())
        head.lineTo(end)
    painter.drawPath(head)

    font = QFont("Helvetica Neue")
    font.setPointSizeF(15)
    font.setWeight(QFont.Weight.Medium)
    painter.setFont(font)
    painter.setPen(QColor(CAPTION))
    painter.drawText(
        QRectF(0, 300, WIDTH, 40),
        Qt.AlignmentFlag.AlignCenter,
        "Drag Calculator to Applications to install it",
    )
    painter.end()
    return pixmap


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    output = Path(sys.argv[1])
    output.parent.mkdir(parents=True, exist_ok=True)
    app = QGuiApplication([])  # Required before anything can be drawn.
    for scale, path in ((1, output), (2, output.with_name(f"{output.stem}@2x.png"))):
        if not draw(scale).save(str(path)):
            raise SystemExit(f"Could not save {path}")
    del app


if __name__ == "__main__":
    main()
