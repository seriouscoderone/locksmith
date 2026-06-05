"""Generate assets/custom/AppIcon.icns and AppIcon.ico from SymbolLogo.svg.

Composites the triquetra symbol onto a macOS-style squircle plate
with a soft cream gradient, renders the 10 sizes Apple expects
(16-1024 px, @1x and @2x), and packs them with iconutil for macOS.

The same squircle composition is then re-rendered at the six sizes
Windows expects (16/32/48/64/128/256) and packed into a multi-image
.ico via Pillow.

Run from the repo root after any change to the source SVG:
    python packaging/build-appicon.py

Both .icns and .ico outputs are committed; CI does not regenerate them.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice, QRectF, Qt
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
FULL_SVG = REPO_ROOT / "assets" / "custom" / "FullLogo.svg"
OUT_ICNS = REPO_ROOT / "assets" / "custom" / "AppIcon.icns"
OUT_ICO = REPO_ROOT / "assets" / "custom" / "AppIcon.ico"
OUT_WIX_BANNER = REPO_ROOT / "packaging" / "wix" / "banner.png"
OUT_WIX_DIALOG = REPO_ROOT / "packaging" / "wix" / "dialog.png"

# Windows ICO contains nested PNG/BMP frames at well-known sizes.
ICO_SIZES = [16, 32, 48, 64, 128, 256]

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


def _qimage_to_pil(img: QImage) -> Image.Image:
    """Marshal a QImage through PNG bytes into a PIL Image (RGBA)."""
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return Image.open(BytesIO(bytes(buf.data()))).convert("RGBA")


def build_icns() -> None:
    iconset_dir = REPO_ROOT / "build" / "AppIcon.iconset"
    if iconset_dir.exists():
        shutil.rmtree(iconset_dir)
    iconset_dir.mkdir(parents=True)

    for size, filename in ICONSET_FILES:
        out = iconset_dir / filename
        render(size).save(str(out), "PNG")
        print(f"  {size:4d}px -> {out.relative_to(REPO_ROOT)}")

    if not sys.platform.startswith("darwin"):
        print("(skipping iconutil — only available on macOS)")
        return

    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(OUT_ICNS)],
        check=True,
    )
    print(f"wrote {OUT_ICNS.relative_to(REPO_ROOT)} ({OUT_ICNS.stat().st_size:,} bytes)")


def build_wix_banner() -> None:
    """493x58 PNG: white background, SymbolLogo mark on the right (WixUI banner slot)."""
    OUT_WIX_BANNER.parent.mkdir(parents=True, exist_ok=True)
    img = QImage(493, 58, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor("#FFFFFF"))
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    mark = 44
    mx = 493 - mark - 12
    my = (58 - mark) // 2
    QSvgRenderer(str(SVG)).render(painter, QRectF(mx, my, mark, mark))
    painter.end()
    img.save(str(OUT_WIX_BANNER), "PNG")
    print(f"wrote {OUT_WIX_BANNER.relative_to(REPO_ROOT)}")


def build_wix_dialog() -> None:
    """493x312 PNG: cream background, centered FullLogo (WixUI welcome/exit slot)."""
    OUT_WIX_DIALOG.parent.mkdir(parents=True, exist_ok=True)
    img = QImage(493, 312, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor("#FBF7EE"))
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    logo_w, logo_h = 320, 160
    x = (493 - logo_w) // 2
    y = (312 - logo_h) // 2 - 16
    QSvgRenderer(str(FULL_SVG)).render(painter, QRectF(x, y, logo_w, logo_h))
    painter.end()
    img.save(str(OUT_WIX_DIALOG), "PNG")
    print(f"wrote {OUT_WIX_DIALOG.relative_to(REPO_ROOT)}")


def build_ico() -> None:
    """Render the squircle plate at ICO_SIZES and pack into a multi-image .ico.

    Pillow's ICO writer takes the primary image and uses `sizes=` to know
    which frames to embed; `append_images` adds extra source frames. We give
    the largest size as the primary image and append all smaller sizes so
    each frame is rendered from its own Qt-rendered PNG (no downscaling).
    """
    frames_desc = sorted(ICO_SIZES, reverse=True)
    frames = {size: _qimage_to_pil(render(size)) for size in frames_desc}
    primary = frames[frames_desc[0]]
    primary.save(
        OUT_ICO,
        format="ICO",
        sizes=[(s, s) for s in frames_desc],
        append_images=[frames[s] for s in frames_desc[1:]],
    )
    print(f"wrote {OUT_ICO.relative_to(REPO_ROOT)} ({OUT_ICO.stat().st_size:,} bytes)")


def main() -> int:
    QGuiApplication.instance() or QGuiApplication(sys.argv)
    build_icns()
    build_ico()
    build_wix_banner()
    build_wix_dialog()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
