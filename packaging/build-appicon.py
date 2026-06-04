"""Generate assets/custom/AppIcon.icns from SymbolLogo.svg.

Composites the triquetra symbol onto a macOS-style squircle plate
with a soft cream gradient, renders the 10 sizes Apple expects
(16-1024 px, @1x and @2x), and packs them with iconutil.

Run from the repo root after any change to the source SVG:
    python packaging/build-appicon.py

The .icns output is committed; CI does not regenerate it.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
)
from PySide6.QtSvg import QSvgRenderer

REPO_ROOT = Path(__file__).resolve().parent.parent
SVG = REPO_ROOT / "assets" / "custom" / "SymbolLogo.svg"
OUT_ICNS = REPO_ROOT / "assets" / "custom" / "AppIcon.icns"

# macOS Sonoma squircle: ~22.5% corner radius relative to side.
CORNER_RADIUS_RATIO = 0.225

# Soft cream gradient — complements the symbol's warm earth tones.
PLATE_TOP = QColor("#FBF7EE")
PLATE_BOTTOM = QColor("#E8DFD0")

# Symbol safe-area: ~18% padding inside the squircle.
SYMBOL_PADDING_RATIO = 0.18

ICONSET_FILES = [
    (16, "icon_16x16.png"),
    (32, "icon_16x16@2x.png"),
    (32, "icon_32x32.png"),
    (64, "icon_32x32@2x.png"),
    (128, "icon_128x128.png"),
    (256, "icon_128x128@2x.png"),
    (256, "icon_256x256.png"),
    (512, "icon_256x256@2x.png"),
    (512, "icon_512x512.png"),
    (1024, "icon_512x512@2x.png"),
]


def render(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)

    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    plate = QPainterPath()
    radius = size * CORNER_RADIUS_RATIO
    plate.addRoundedRect(0, 0, size, size, radius, radius)

    grad = QLinearGradient(0, 0, 0, size)
    grad.setColorAt(0.0, PLATE_TOP)
    grad.setColorAt(1.0, PLATE_BOTTOM)
    painter.fillPath(plate, grad)

    painter.setClipPath(plate)
    pad = size * SYMBOL_PADDING_RATIO
    inner = QRectF(pad, pad, size - 2 * pad, size - 2 * pad)
    QSvgRenderer(str(SVG)).render(painter, inner)
    painter.end()
    return img


def main() -> int:
    QGuiApplication.instance() or QGuiApplication(sys.argv)

    iconset_dir = REPO_ROOT / "build" / "AppIcon.iconset"
    if iconset_dir.exists():
        shutil.rmtree(iconset_dir)
    iconset_dir.mkdir(parents=True)

    for size, filename in ICONSET_FILES:
        out = iconset_dir / filename
        render(size).save(str(out), "PNG")
        print(f"  {size:4d}px -> {out.relative_to(REPO_ROOT)}")

    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(OUT_ICNS)],
        check=True,
    )
    print(f"wrote {OUT_ICNS.relative_to(REPO_ROOT)} ({OUT_ICNS.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
