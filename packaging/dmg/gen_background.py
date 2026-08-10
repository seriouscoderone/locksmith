#!/usr/bin/env python3
"""Render a brand's DMG mount-window background into its release dir.

``create-dmg --background`` paints this image behind the two icons in the
mounted volume window: the app on the left, the ``/Applications`` symlink on
the right. The image carries the "drag me there" affordance — an arrow between
the two icons and a caption naming the app.

**This image is brand-specific**, because the caption names the app. A single
committed ``packaging/dmg/background.png`` is how the Usurance DMG came to
mount a window reading *"Locksmith — drag to Applications"* next to an icon
labelled ``Usurance.app``: the icon label is brand-selected but the background
was shared. That is the same defect class as the v0.3.6 Usurance MSI wearing
Locksmith's triquetra (``packaging/wix/gen_ui_images.py``) — fixed the same
way, by rendering per brand into ``brandlib.brand_release_dir``.

Geometry is NOT duplicated here. Window size and both icon positions are read
from ``brandlib.render_dmg_layout()`` — the same function that writes the
``dmg-layout.json`` ``build-macos.sh`` feeds to ``create-dmg``. That is what
keeps the painted arrow aligned with where the icons actually land: move an
icon in ``render_dmg_layout`` and the arrow follows on the next render.

``scripts/brand_apply.py`` runs this as a **subprocess** — Qt's application
object is a process-wide singleton and ``brand_apply`` is imported by non-Qt
tests, so Qt must never be initialised in the caller. Standalone::

    .venv/bin/python packaging/dmg/gen_background.py --brand usurance

Palette comes from the brand's ``[dmg]`` table (every key optional):

=============  ===========================================================
``bg``         the window background (default: the reference near-white)
``accent``     the arrow (default: the reference gray)
``text``       the caption (default: ``accent``)
=============  ===========================================================

Colors must NOT live under ``[assets]``: ``scripts/check-brand-complete.py``
validates every ``[assets]`` value as a filename in the brand dir.
"""
from __future__ import annotations

import argparse
import os
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Locksmith reference palette — the default when a brand states no [dmg] table.
DEFAULT_BG = "#F2F2F4"
DEFAULT_ACCENT = "#B0B0B6"

CAPTION_PT = 13
CAPTION_BASELINE_UP = 55   # px above the window bottom
ARROW_GAP = 26             # clearance between an icon's edge and the arrow
ARROW_HEAD = 13            # arrowhead length
ARROW_THICKNESS = 2

OUTPUT_NAME = "background.png"


def _dmg(manifest: dict) -> dict:
    return manifest.get("dmg", {}) or {}


def _color(value: str, key: str):
    """Parse a ``[dmg]`` color, loudly. An unparseable QColor silently fills
    black, which would ship a black DMG window."""
    from PySide6.QtGui import QColor
    color = QColor(value)
    if not color.isValid():
        raise SystemExit(f"gen_background: [dmg] {key} = {value!r} is not a color")
    return color


def _qt_app():
    """Own the Qt singleton for this (sub)process, headless by default."""
    from PySide6.QtGui import QGuiApplication
    if QGuiApplication.instance() is None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        return QGuiApplication([sys.argv[0] or "gen_background"])
    return QGuiApplication.instance()


def geometry(manifest: dict) -> dict:
    """Window size + icon centers, read from the SAME source as dmg-layout.json.

    Returns pixel values with a top-left origin, matching
    ``brandlib.render_dmg_layout``'s stated convention.
    """
    sys.path.insert(0, str(REPO / "packaging"))
    import brandlib  # noqa: PLC0415 — keep import cost off the module surface

    layout = brandlib.render_dmg_layout(manifest)
    name = manifest["brand"]["display_name"]
    icons = {i["name"]: i for i in layout["icons"]}
    w, h = layout["window"]["size"]
    return {
        "width": w,
        "height": h,
        "icon_size": layout["icon_size"],
        "app": icons[f"{name}.app"]["pos"],
        "apps": icons["Applications"]["pos"],
        "name": name,
    }


def _draw_arrow(painter, x0: float, x1: float, y: float, color) -> None:
    """A left-to-right arrow from x0 to x1, vertically centered on y."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QPen, QPolygonF

    pen = QPen(color)
    pen.setWidth(ARROW_THICKNESS)
    painter.setPen(pen)
    painter.drawLine(QPointF(x0, y), QPointF(x1 - ARROW_HEAD, y))

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawPolygon(QPolygonF([
        QPointF(x1, y),
        QPointF(x1 - ARROW_HEAD, y - ARROW_HEAD * 0.55),
        QPointF(x1 - ARROW_HEAD, y + ARROW_HEAD * 0.55),
    ]))


def _draw_caption(painter, text: str, geo: dict, color) -> None:
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QFont

    font = QFont()
    font.setPointSize(CAPTION_PT)
    painter.setFont(font)
    painter.setPen(color)
    box = QRectF(0, geo["height"] - CAPTION_BASELINE_UP, geo["width"], CAPTION_PT * 2.2)
    painter.drawText(box, int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop), text)


def build_background(manifest: dict, out_dir: Path) -> Path:
    from PySide6.QtGui import QImage, QPainter

    cfg = _dmg(manifest)
    geo = geometry(manifest)
    accent = _color(cfg.get("accent", DEFAULT_ACCENT), "accent")
    text_color = _color(cfg.get("text") or cfg.get("accent", DEFAULT_ACCENT), "text")

    img = QImage(geo["width"], geo["height"], QImage.Format.Format_ARGB32)
    img.fill(_color(cfg.get("bg", DEFAULT_BG), "bg"))

    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

    half = geo["icon_size"] / 2
    x0 = geo["app"][0] + half + ARROW_GAP
    x1 = geo["apps"][0] - half - ARROW_GAP
    _draw_arrow(p, x0, x1, geo["app"][1], accent)

    # A hyphen, not an em dash: the caption renders under the offscreen Qt
    # platform whose default font substitution dropped U+2014 to a tofu box in
    # the hand-made asset this generator replaces.
    _draw_caption(p, f"{geo['name']} - drag to Applications", geo, text_color)
    p.end()

    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / OUTPUT_NAME
    if not img.save(str(out), "PNG"):
        raise SystemExit(f"gen_background: failed to save {out}")
    print(f"wrote {out}  {img.width()}x{img.height()}")
    return out


def render_dmg_background(brand_dir: Path, manifest: dict, out_dir: Path) -> Path:
    """Render the DMG background for one brand into ``out_dir``."""
    _qt_app()
    return build_background(manifest, Path(out_dir))


def load_manifest(brand_dir: Path) -> dict:
    toml_path = Path(brand_dir) / "brand.toml"
    if not toml_path.is_file():
        return {}
    return tomllib.loads(toml_path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Render a per-brand DMG background.")
    ap.add_argument("--brand", default=None,
                    help="brand id under brands/ (default: $LOCKSMITH_BRAND, "
                         "else locksmith)")
    ap.add_argument("--brand-dir", default=None,
                    help="explicit brand source dir (overrides --brand; used by "
                         "scripts/brand_apply.py, which has already resolved it)")
    ap.add_argument("--out", default=None,
                    help="output dir (default: the brand's release dir)")
    args = ap.parse_args(argv)

    sys.path.insert(0, str(REPO / "packaging"))
    import brandlib  # noqa: PLC0415

    brand_id = args.brand or brandlib.active_brand_id()
    brand_dir = Path(args.brand_dir) if args.brand_dir else REPO / "brands" / brand_id
    out_dir = Path(args.out) if args.out else brandlib.brand_release_dir(brand_id)
    render_dmg_background(brand_dir, load_manifest(brand_dir), out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
