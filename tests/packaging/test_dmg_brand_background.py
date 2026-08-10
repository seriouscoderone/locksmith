"""The DMG mount-window background must be BRAND art.

Regression cover for the macOS twin of the v0.3.6 MSI leak: a single committed
`packaging/dmg/background.png` whose caption read "Locksmith - drag to
Applications" was handed to `create-dmg` for every brand, so the Usurance DMG
mounted a window naming Locksmith next to an icon labelled `Usurance.app`.

These tests are static + render-only; they never invoke `create-dmg`. Mount
geometry is only confirmed by a real DMG build.

Rendering runs in a SUBPROCESS: gen_background initialises Qt, and this repo has
an order-dependent process-wide Qt singleton landmine (see
tests/unit/branding/conftest.py). Keep Qt out of the test process.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GEN = REPO_ROOT / "packaging" / "dmg" / "gen_background.py"
BUILD_MACOS = REPO_ROOT / "packaging" / "build-macos.sh"
BRAND_APPLY = REPO_ROOT / "scripts" / "brand_apply.py"

BRANDS = ("locksmith", "usurance")
BACKGROUND = "background.png"


def _render(brand: str, out: Path) -> Path:
    subprocess.run([sys.executable, str(GEN), "--brand", brand, "--out", str(out)],
                   check=True, cwd=REPO_ROOT)
    return out


@pytest.fixture(scope="module")
def rendered(tmp_path_factory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("dmgbg")
    return {b: _render(b, root / b) for b in BRANDS}


def _manifest(brand: str) -> dict:
    path = REPO_ROOT / "brands" / brand / "brand.toml"
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _image(png: Path):
    from PIL import Image
    return Image.open(png).convert("RGB")


# --- the leak itself ---------------------------------------------------------

def test_each_brand_renders_its_own_background(rendered):
    """No two brands may ship a byte-identical DMG background."""
    lock = (rendered["locksmith"] / BACKGROUND).read_bytes()
    usur = (rendered["usurance"] / BACKGROUND).read_bytes()
    assert lock and usur
    assert lock != usur, (
        "background.png is identical for locksmith and usurance — the caption "
        "names the app, so a shared image tells one brand's user to drag the "
        "other brand's name to Applications")


def test_no_shared_committed_background_is_tracked():
    """The shared asset must stay deleted AND ignored, or it silently wins again."""
    tracked = subprocess.run(
        ["git", "ls-files", "packaging/dmg/background.png"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    assert not tracked, (
        "packaging/dmg/background.png is tracked again — that shared image is "
        "exactly what shipped Locksmith's caption in the Usurance DMG")

    ignored = subprocess.run(
        ["git", "check-ignore", "packaging/dmg/background.png"],
        cwd=REPO_ROOT, capture_output=True, text=True)
    assert ignored.returncode == 0, (
        "packaging/dmg/background.png is not gitignored — a stray local render "
        "can be committed back into the shared path")


def test_build_macos_reads_the_brand_background():
    """build-macos.sh must point create-dmg at the brand's release dir."""
    text = BUILD_MACOS.read_text(encoding="utf-8")
    assert '--background "$LOCKSMITH_RELEASE/background.png"' in text, (
        "build-macos.sh no longer feeds create-dmg the per-brand background")
    assert '--background "packaging/dmg/background.png"' not in text


def test_brand_apply_renders_the_background():
    """brand_apply must stage background.png beside dmg-layout.json."""
    text = BRAND_APPLY.read_text(encoding="utf-8")
    assert "_render_dmg_background(brand_dir, out)" in text, (
        "brand_apply no longer renders the DMG background — the brand release "
        "dir will have a dmg-layout.json with no background beside it")


# --- the caption -------------------------------------------------------------
#
# A caption is drawn text, so assert it is PRESENT (ink in the caption band)
# rather than OCR-ing it. That it names the RIGHT brand is covered by the
# byte-difference test above plus the source-level dash check below.

@pytest.mark.parametrize("brand", BRANDS)
def test_caption_band_has_ink(rendered, brand):
    """The caption band must not be blank — a missing font would render nothing."""
    img = _image(rendered[brand] / BACKGROUND)
    w, h = img.size
    bg = img.getpixel((5, 5))
    ink = sum(1 for y in range(h - 60, h - 20) for x in range(w)
              if img.getpixel((x, y)) != bg)
    assert ink > 200, (
        f"{brand}: DMG caption band is effectively blank ({ink} non-bg pixels) — "
        "the caption is the only thing naming the app in the mount window")


def test_caption_uses_no_character_the_render_font_lacks(rendered):
    """The hand-made asset shipped a tofu box where its em dash should be.

    The generator states a hyphen for exactly that reason; if someone puts the
    em dash back, this catches the regression at the source rather than in a
    shipped DMG.
    """
    src = GEN.read_text(encoding="utf-8")
    drawn = [ln for ln in src.splitlines() if "drag to Applications" in ln
             and "_draw_caption" in ln]
    assert drawn, "caption line not found in gen_background.py"
    assert "—" not in drawn[0] and "–" not in drawn[0], (
        "the DMG caption uses an em/en dash again — the offscreen Qt platform's "
        "font substitution renders it as a tofu box")


# --- geometry ----------------------------------------------------------------

@pytest.mark.parametrize("brand", BRANDS)
def test_background_matches_the_layout_window_size(rendered, brand):
    """The image must be exactly the window create-dmg opens, or it tiles/crops."""
    sys.path.insert(0, str(REPO_ROOT / "packaging"))
    import brandlib

    layout = brandlib.render_dmg_layout(_manifest(brand))
    want = tuple(layout["window"]["size"])
    got = _image(rendered[brand] / BACKGROUND).size
    assert got == want, (
        f"{brand}: background is {got} but dmg-layout.json opens a {want} window")


@pytest.mark.parametrize("brand", BRANDS)
def test_arrow_stays_clear_of_both_icons(rendered, brand):
    """The painted arrow must sit BETWEEN the icons, not under them.

    Both the arrow and dmg-layout.json's icon positions come from
    render_dmg_layout, so this fails the moment those two drift apart.
    """
    sys.path.insert(0, str(REPO_ROOT / "packaging"))
    import brandlib

    manifest = _manifest(brand)
    layout = brandlib.render_dmg_layout(manifest)
    icons = {i["name"]: i for i in layout["icons"]}
    name = manifest["brand"]["display_name"]
    half = layout["icon_size"] / 2
    app_right = icons[f"{name}.app"]["pos"][0] + half
    apps_left = icons["Applications"]["pos"][0] - half
    row_y = icons[f"{name}.app"]["pos"][1]

    img = _image(rendered[brand] / BACKGROUND)
    bg = img.getpixel((5, 5))
    ink_x = [x for x in range(img.size[0])
             if any(img.getpixel((x, y)) != bg
                    for y in range(row_y - 12, row_y + 12))]
    assert ink_x, f"{brand}: no arrow drawn on the icon row (y={row_y})"
    assert min(ink_x) > app_right, (
        f"{brand}: arrow starts at x={min(ink_x)}, under the app icon "
        f"(right edge {app_right})")
    assert max(ink_x) < apps_left, (
        f"{brand}: arrow ends at x={max(ink_x)}, under the Applications icon "
        f"(left edge {apps_left})")


# --- palette -----------------------------------------------------------------

def test_usurance_background_uses_its_own_palette(rendered):
    """Usurance states a [dmg] table; the render must actually honour it."""
    cfg = _manifest("usurance").get("dmg", {})
    assert cfg, "usurance brand.toml lost its [dmg] table"

    img = _image(rendered["usurance"] / BACKGROUND)
    want = tuple(int(cfg["bg"].lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    assert img.getpixel((5, 5)) == want, (
        f"usurance DMG background corner is {img.getpixel((5, 5))}, expected "
        f"{want} from [dmg] bg")


def test_locksmith_needs_no_dmg_table(rendered):
    """The reference brand states no [dmg] table and must still render."""
    assert "dmg" not in _manifest("locksmith"), (
        "locksmith gained a [dmg] table — this test guards the defaults path")
    assert (rendered["locksmith"] / BACKGROUND).stat().st_size > 0
