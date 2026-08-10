"""The WiX installer chrome (banner.png / dialog.png) must be BRAND art.

Regression cover for the v0.3.6 leak: the Usurance MSI's welcome dialog showed
*Locksmith's* triquetra. Root cause was a shared output path — both generators
rendered the *selected* brand's SVG into one committed `packaging/wix/` pair, so
every brand's MSI linked whichever brand was rendered last, and `wix build`
listed that shared dir as its FIRST -bindpath.

These tests are static + render-only; they never invoke `wix`. The end-to-end
MSI is built on the Windows CI leg.

Rendering runs in a SUBPROCESS: gen_ui_images initialises Qt, and this repo has
an order-dependent process-wide Qt singleton landmine (see
tests/unit/branding/conftest.py). Keep Qt out of the test process.
"""
from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WIX_DIR = REPO_ROOT / "packaging" / "wix"
GEN = WIX_DIR / "gen_ui_images.py"

BRANDS = ("locksmith", "usurance")
IMAGES = ("dialog.png", "banner.png")


def _render(brand: str, out: Path) -> Path:
    subprocess.run([sys.executable, str(GEN), "--brand", brand, "--out", str(out)],
                   check=True, cwd=REPO_ROOT)
    return out


@pytest.fixture(scope="module")
def rendered(tmp_path_factory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("wixchrome")
    return {b: _render(b, root / b) for b in BRANDS}


def _pixel(png: Path, x: int, y: int) -> tuple[int, int, int]:
    from PIL import Image
    with Image.open(png) as img:
        return img.convert("RGB").getpixel((x, y))


# --- the leak itself ---------------------------------------------------------

def test_each_brand_renders_its_own_chrome(rendered):
    """No two brands may ship byte-identical installer chrome."""
    for name in IMAGES:
        lock = (rendered["locksmith"] / name).read_bytes()
        usur = (rendered["usurance"] / name).read_bytes()
        assert lock and usur
        assert lock != usur, (
            f"{name} is identical for locksmith and usurance — the brand's art "
            "is not reaching its own installer")


def test_no_shared_committed_chrome_in_packaging_wix():
    """A committed packaging/wix pair silently wins for every brand."""
    for name in IMAGES:
        stray = WIX_DIR / name
        assert not stray.exists(), (
            f"{stray} is back: a single shared {name} is brand art masquerading "
            "as neutral chrome (v0.3.6 Usurance MSI showed Locksmith's mark)")


def test_wix_build_prefers_the_brand_release_dir():
    """`-bindpath $releaseDir` must precede `-bindpath $wixDir` (first hit wins)."""
    ps1 = (REPO_ROOT / "packaging" / "build-windows.ps1").read_text(encoding="utf-8")
    release_at = ps1.index("-bindpath $releaseDir")
    wix_at = ps1.index("-bindpath $wixDir")
    assert release_at < wix_at, (
        "packaging/wix/ is searched before the brand release dir — any stray "
        "shared banner/dialog/license there would override the brand's own")


def test_wxs_references_chrome_by_bare_name():
    """Bare names are what let the bindpath order above select the brand's art."""
    wxs = (WIX_DIR / "Locksmith.wxs.in").read_text(encoding="utf-8")
    assert 'Id="WixUIBannerBmp" Value="banner.png"' in wxs
    assert 'Id="WixUIDialogBmp" Value="dialog.png"' in wxs


# --- the images are usable WixUI slots ---------------------------------------

@pytest.mark.parametrize("brand", BRANDS)
def test_dimensions(rendered, brand):
    from PIL import Image
    with Image.open(rendered[brand] / "dialog.png") as img:
        assert img.size == (493, 312), f"{brand} dialog {img.size}"
    with Image.open(rendered[brand] / "banner.png") as img:
        assert img.size == (493, 58), f"{brand} banner {img.size}"


@pytest.mark.parametrize("brand", BRANDS)
def test_wixui_text_areas_stay_clear(rendered, brand):
    """WixUI paints the title/description over the dialog's right side and the
    banner's left side; brand art there overlaps the text (the v0.1.4 bug)."""
    dialog = rendered[brand] / "dialog.png"
    corners = [_pixel(dialog, x, y) for x in (200, 480) for y in (8, 300)]
    assert len(set(corners)) == 1, f"{brand} dialog right side is not flat: {corners}"
    banner = rendered[brand] / "banner.png"
    left = [_pixel(banner, x, y) for x in (4, 200, 360) for y in (4, 54)]
    assert len(set(left)) == 1, f"{brand} banner left side is not flat: {left}"


def test_brand_palette_is_applied(rendered):
    """The [wix] table drives the palette — not a hardcoded Locksmith cream."""
    # dialog art panel, x < LEFT_PANEL_W (164)
    assert _pixel(rendered["locksmith"] / "dialog.png", 10, 10) == (0xF4, 0xEE, 0xE1)
    assert _pixel(rendered["usurance"] / "dialog.png", 10, 10) == (0x2A, 0xAB, 0xB3)
    # dialog text area
    assert _pixel(rendered["locksmith"] / "dialog.png", 480, 10) == (0xF9, 0xF5, 0xEC)
    assert _pixel(rendered["usurance"] / "dialog.png", 480, 10) == (0xFF, 0xFF, 0xFF)


@pytest.mark.parametrize("brand", BRANDS)
def test_the_mark_actually_rendered(rendered, brand):
    """Guard the silent-blank failure: an unloadable/invisible SVG (e.g. the
    reversed white mark on a white banner) leaves a flat image."""
    for name, box in (("dialog.png", [(x, y) for x in range(20, 145, 8)
                                      for y in range(110, 205, 8)]),
                      ("banner.png", [(x, y) for x in range(440, 485, 4)
                                      for y in range(10, 50, 4)])):
        colors = {_pixel(rendered[brand] / name, x, y) for x, y in box}
        assert len(colors) > 3, f"{brand} {name} has no visible mark: {colors}"


# --- brand-scoped resolution -------------------------------------------------

def test_resolve_symbol_never_borrows_another_brands_mark(tmp_path):
    sys.path.insert(0, str(WIX_DIR))
    gen = importlib.import_module("gen_ui_images")
    empty = tmp_path / "brands" / "nomark"
    empty.mkdir(parents=True)
    with pytest.raises(SystemExit, match="refusing to fall back"):
        gen.resolve_symbol(empty, {"assets": {"symbol_logo": "SymbolLogo.svg"}})


def test_resolve_symbol_honours_the_wix_slot_keys():
    sys.path.insert(0, str(WIX_DIR))
    gen = importlib.import_module("gen_ui_images")
    brand_dir = REPO_ROOT / "brands" / "usurance"
    manifest = gen.load_manifest(brand_dir)
    assert gen.resolve_symbol(brand_dir, manifest, "panel_symbol").name \
        == "SymbolLogoWhite.svg"
    assert gen.resolve_symbol(brand_dir, manifest, "banner_symbol").name \
        == "SymbolLogoBlack.svg"
    # locksmith states no [wix] table at all -> the plain symbol both times
    lock = REPO_ROOT / "brands" / "locksmith"
    lock_manifest = gen.load_manifest(lock)
    for key in ("panel_symbol", "banner_symbol"):
        assert gen.resolve_symbol(lock, lock_manifest, key).name == "SymbolLogo.svg"


def test_unknown_slot_fails_loud():
    sys.path.insert(0, str(WIX_DIR))
    gen = importlib.import_module("gen_ui_images")
    with pytest.raises(SystemExit, match="unknown"):
        gen.resolve_symbol(REPO_ROOT / "brands" / "locksmith",
                           {"wix": {"panel_symbol": "full_logo"}})
