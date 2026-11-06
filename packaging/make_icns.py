#!/usr/bin/env python3
"""Create packaging/Calculator.icns from the icon drawn in calculator/ui.py."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"  # No window is needed to draw it.

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QSize  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from calculator.ui import make_app_icon  # noqa: E402

# Every size macOS looks for, each at normal and Retina resolution.
POINT_SIZES = (16, 32, 128, 256, 512)


def main() -> None:
    app = QApplication([])  # Required before anything can be drawn.
    icon = make_app_icon()
    output = ROOT / "packaging" / "Calculator.icns"
    with tempfile.TemporaryDirectory() as folder:
        iconset = Path(folder) / "Calculator.iconset"
        iconset.mkdir()
        for size in POINT_SIZES:
            for scale, suffix in ((1, ""), (2, "@2x")):
                pixels = size * scale
                pixmap = icon.pixmap(QSize(pixels, pixels))
                if pixmap.width() != pixels or pixmap.height() != pixels:
                    raise SystemExit(f"Icon drawn at the wrong size for {pixels}px")
                if not pixmap.save(str(iconset / f"icon_{size}x{size}{suffix}.png")):
                    raise SystemExit(f"Could not save the {pixels}px icon")
        subprocess.run(
            ["iconutil", "--convert", "icns", "--output", str(output), str(iconset)],
            check=True,
        )
    del app
    print(f"Created {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
