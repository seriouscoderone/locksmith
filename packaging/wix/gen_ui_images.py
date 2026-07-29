"""Render a brand's WiX UI chrome — dialog.png + banner.png — into its release dir.

The WixUI_InstallDir dialog set uses ``WixUIDialogBmp`` as the FULL
background of the Welcome and Exit screens and ``WixUIBannerBmp`` as the
top banner on intermediate screens. WixUI then draws title + description
text on top — so the image must leave the right ~329 px (dialog) and the
left ~370 px (banner) clear, otherwise the text overlaps brand art (as it
did in v0.1.4).

**These images are brand-specific.** They carry the brand's symbol mark and
palette, so they are rendered per-brand into that brand's release dir
(``brandlib.brand_release_dir``) alongside the rendered ``Locksmith.wxs`` —
never into a single shared committed path under ``packaging/wix/``. A shared
committed pair is exactly how the v0.3.6 **Usurance** MSI came to show
**Locksmith's** triquetra on its welcome dialog: the source SVG became
brand-selected while the output path stayed shared, so every brand's MSI
picked up whichever brand was rendered last (and committed).

``scripts/brand_apply.py`` runs this as a **subprocess** — Qt's application
object is a process-wide singleton and ``brand_apply`` is imported by non-Qt
tests, so Qt must never be initialised in the caller. Standalone::

    .venv/bin/python packaging/wix/gen_ui_images.py --brand usurance

Palette + mark come from the brand's ``[wix]`` table (every key optional):

===============  =========================================================
``dialog_bg``    background of the welcome/exit dialog (default: cream)
``panel_bg``     the dialog's left art panel (default: cream)
``banner_bg``    background of the top banner (default: ``dialog_bg``)
``panel_symbol`` which ``[assets]`` symbol slot the dialog's art panel
                 uses — one of ``symbol_logo`` / ``symbol_logo_white`` /
                 ``symbol_logo_black`` (default: ``symbol_logo``)
``banner_symbol`` same, for the banner (default: ``symbol_logo``). It is a
                 separate key because the two sit on different backgrounds:
                 usurance's teal panel wants the reversed white mark, while
                 that same mark on the white banner is invisible.
===============  =========================================================

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

DIALOG_W, DIALOG_H = 493, 312
BANNER_W, BANNER_H = 493, 58

# Locksmith reference palette — the default when a brand states no [wix] table.
DEFAULT_DIALOG_BG = "#F9F5EC"   # cream
DEFAULT_PANEL_BG = "#F4EEE1"    # slightly darker cream for the art panel

LEFT_PANEL_W = 164              # leaves ~329 px of clear space on the right
DIALOG_LOGO = 110
BANNER_LOGO = 44
BANNER_MARGIN_RIGHT = 12

# Canonical filenames for the symbol slots this renderer can draw, keyed by
# brand.toml [assets] key (mirrors scripts/generate_qrc._QRC_SLOTS).
SYMBOL_SLOTS = {
    "symbol_logo": "SymbolLogo.svg",
    "symbol_logo_white": "SymbolLogoWhite.svg",
    "symbol_logo_black": "SymbolLogoBlack.svg",
}

OUTPUT_NAMES = ("dialog.png", "banner.png")


def _wix(manifest: dict) -> dict:
    return manifest.get("wix", {}) or {}


def resolve_symbol(brand_dir: Path, manifest: dict, key: str = "panel_symbol") -> Path:
    """The SVG the WiX chrome draws for this brand, per ``[wix] <key>``.

    Falls back only WITHIN the brand (requested slot -> the brand's own
    ``symbol_logo``); a missing mark is a hard error. Never substitutes
    another brand's art — that fallback is the leak this module exists to
    prevent.
    """
    slot = _wix(manifest).get(key, "symbol_logo")
    if slot not in SYMBOL_SLOTS:
        raise SystemExit(
            f"gen_ui_images: unknown [wix] {key} {slot!r}; "
            f"expected one of {sorted(SYMBOL_SLOTS)}")
    assets = manifest.get("assets", {})
    for candidate in (slot, "symbol_logo"):
        fname = assets.get(candidate) or SYMBOL_SLOTS[candidate]
        path = brand_dir / fname
        if path.is_file():
            return path
    raise SystemExit(
        f"gen_ui_images: no symbol art for slot {slot!r} in {brand_dir} — "
        "refusing to fall back to another brand's mark")


def _color(value: str, key: str):
    """Parse a ``[wix]`` color, loudly. An unparseable QColor silently fills
    black, which would ship a black installer dialog."""
    from PySide6.QtGui import QColor
    color = QColor(value)
    if not color.isValid():
        raise SystemExit(f"gen_ui_images: [wix] {key} = {value!r} is not a color")
    return color


def _qt_app():
    """Own the Qt singleton for this (sub)process, headless by default."""
    from PySide6.QtGui import QGuiApplication
    if QGuiApplication.instance() is None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        return QGuiApplication([sys.argv[0] or "gen_ui_images"])
    return QGuiApplication.instance()


def _draw_symbol(painter, svg_path: Path, cx: float, cy: float, box: float) -> None:
    """Draw ``svg_path`` centered on (cx, cy), fitted into a ``box``-px square
    with its aspect ratio preserved (brand marks are not all square: locksmith's
    is 94x94, usurance's 707x513 — stretching to the box squashes it)."""
    from PySide6.QtCore import QRectF
    from PySide6.QtSvg import QSvgRenderer

    renderer = QSvgRenderer(str(svg_path))
    if not renderer.isValid():
        print(f"gen_ui_images: WARNING {svg_path} is not a loadable SVG "
              "— chrome will render without the mark", file=sys.stderr)
        return
    native = renderer.defaultSize()
    w, h = native.width() or 1, native.height() or 1
    scale = box / max(w, h)
    fw, fh = w * scale, h * scale
    renderer.render(painter, QRectF(cx - fw / 2, cy - fh / 2, fw, fh))


def _painter(img):
    from PySide6.QtGui import QPainter
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    return p


def _save(img, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    if not img.save(str(out), "PNG"):
        raise SystemExit(f"gen_ui_images: failed to save {out}")
    print(f"wrote {out}  {img.width()}x{img.height()}")
    return out


def build_dialog(symbol: Path, manifest: dict, out_dir: Path) -> Path:
    from PySide6.QtGui import QImage

    cfg = _wix(manifest)
    img = QImage(DIALOG_W, DIALOG_H, QImage.Format.Format_ARGB32)
    img.fill(_color(cfg.get("dialog_bg", DEFAULT_DIALOG_BG), "dialog_bg"))
    p = _painter(img)
    p.fillRect(0, 0, LEFT_PANEL_W, DIALOG_H,
               _color(cfg.get("panel_bg", DEFAULT_PANEL_BG), "panel_bg"))
    _draw_symbol(p, symbol, LEFT_PANEL_W / 2, DIALOG_H / 2, DIALOG_LOGO)
    p.end()
    return _save(img, out_dir / "dialog.png")


def build_banner(symbol: Path, manifest: dict, out_dir: Path) -> Path:
    from PySide6.QtGui import QImage

    cfg = _wix(manifest)
    bg = cfg.get("banner_bg") or cfg.get("dialog_bg", DEFAULT_DIALOG_BG)
    img = QImage(BANNER_W, BANNER_H, QImage.Format.Format_ARGB32)
    img.fill(_color(bg, "banner_bg"))
    p = _painter(img)
    cx = BANNER_W - BANNER_MARGIN_RIGHT - BANNER_LOGO / 2
    _draw_symbol(p, symbol, cx, BANNER_H / 2, BANNER_LOGO)
    p.end()
    return _save(img, out_dir / "banner.png")


def render_wix_images(brand_dir: Path, manifest: dict, out_dir: Path) -> list[Path]:
    """Render both WiX chrome images for one brand into ``out_dir``."""
    brand_dir, out_dir = Path(brand_dir), Path(out_dir)
    panel = resolve_symbol(brand_dir, manifest, "panel_symbol")
    banner = resolve_symbol(brand_dir, manifest, "banner_symbol")
    _qt_app()
    return [build_dialog(panel, manifest, out_dir),
            build_banner(banner, manifest, out_dir)]


def load_manifest(brand_dir: Path) -> dict:
    toml_path = Path(brand_dir) / "brand.toml"
    if not toml_path.is_file():
        return {}
    return tomllib.loads(toml_path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Render per-brand WiX UI chrome.")
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
    import brandlib  # noqa: PLC0415 — keep import cost off the module surface

    brand_id = args.brand or brandlib.active_brand_id()
    brand_dir = Path(args.brand_dir) if args.brand_dir else REPO / "brands" / brand_id
    out_dir = Path(args.out) if args.out else brandlib.brand_release_dir(brand_id)
    render_wix_images(brand_dir, load_manifest(brand_dir), out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
