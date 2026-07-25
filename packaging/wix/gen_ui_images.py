"""Regenerate WiX dialog.png + banner.png.

The WixUI_InstallDir dialog set uses ``WixUIDialogBmp`` as the FULL
background of the Welcome and Exit screens and ``WixUIBannerBmp`` as
the top banner on intermediate screens. WixUI then draws title +
description text on top — so the image must leave the right ~329 px
(dialog) and the left ~370 px (banner) clear, otherwise the text
overlaps brand art (as it did in v0.1.4).

Run from the repo root::

    .venv/bin/python packaging/wix/gen_ui_images.py

The SymbolLogo.svg source is brand-specific (moved to brands/<brand>/ — see
the atomic-brand-bundles refactor); selects via $LOCKSMITH_BRAND same as the
rest of the packaging tooling (brandlib.active_brand_id(), default
"locksmith"). banner.png/dialog.png themselves are neutral WixUI chrome and
always land in packaging/wix/ regardless of brand.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "packaging"))
import brandlib  # noqa: E402

ASSETS = REPO / "brands" / brandlib.active_brand_id()
OUT = REPO / "packaging" / "wix"

DIALOG_W, DIALOG_H = 493, 312
BANNER_W, BANNER_H = 493, 58

BG_COLOR = QColor(249, 245, 236)   # cream #f9f5ec
LEFT_BG = QColor(244, 238, 225)    # slightly darker cream for the panel
LEFT_PANEL_W = 164                 # leaves ~329 px of clear space on the right


def _render_svg(svg_path: Path, size: int) -> QImage:
    renderer = QSvgRenderer(str(svg_path))
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(p)
    p.end()
    return img


def build_dialog() -> None:
    img = QImage(DIALOG_W, DIALOG_H, QImage.Format.Format_ARGB32)
    img.fill(BG_COLOR)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    p.fillRect(0, 0, LEFT_PANEL_W, DIALOG_H, LEFT_BG)
    logo_size = 110
    logo = _render_svg(ASSETS / "SymbolLogo.svg", logo_size)
    lx = (LEFT_PANEL_W - logo_size) // 2
    ly = (DIALOG_H - logo_size) // 2
    p.drawImage(lx, ly, logo)
    p.end()
    out = OUT / "dialog.png"
    if not img.save(str(out), "PNG"):
        raise SystemExit(f"Failed to save {out}")
    print(f"wrote {out}  {img.width()}x{img.height()}")


def build_banner() -> None:
    img = QImage(BANNER_W, BANNER_H, QImage.Format.Format_ARGB32)
    img.fill(BG_COLOR)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    logo_size = 44
    logo = _render_svg(ASSETS / "SymbolLogo.svg", logo_size)
    margin_right = 12
    bx = BANNER_W - logo_size - margin_right
    by = (BANNER_H - logo_size) // 2
    p.drawImage(bx, by, logo)
    p.end()
    out = OUT / "banner.png"
    if not img.save(str(out), "PNG"):
        raise SystemExit(f"Failed to save {out}")
    print(f"wrote {out}  {img.width()}x{img.height()}")


if __name__ == "__main__":
    QApplication.instance() or QApplication(sys.argv)
    build_dialog()
    build_banner()
