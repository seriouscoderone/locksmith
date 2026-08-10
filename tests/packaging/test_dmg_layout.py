"""DMG layout sanity checks.

dmg-layout.json is no longer a tracked file (scripts/brand_apply.py renders
it per-brand into the brand release dir via brandlib.render_dmg_layout,
gitignored — see the atomic-brand-bundles refactor). These checks render
the locksmith brand's layout in-memory so they stay fresh-clone-safe (no
dependency on a stray on-disk render at the old packaging/dmg/layout.json
location).
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DMG_DIR = REPO_ROOT / "packaging" / "dmg"
GEN_BG = DMG_DIR / "gen_background.py"

sys.path.insert(0, str(REPO_ROOT / "packaging"))
import brandlib  # noqa: E402


def _layout() -> dict:
    return brandlib.render_dmg_layout(brandlib.load_brand_manifest("locksmith"))


def test_layout_renders_a_dict():
    # The on-disk packaging/dmg/layout.json is retired (brand-generated into
    # the release dir now); the meaningful check is that rendering produces
    # a well-formed layout for the reference brand.
    data = _layout()
    assert isinstance(data, dict)
    assert data


def test_background_is_generated_per_brand_not_committed():
    # The background carries a caption naming the app, so it is brand art: it
    # is rendered per brand into the brand release dir, and the old shared
    # packaging/dmg/background.png is deleted + gitignored. Full cover lives in
    # tests/packaging/test_dmg_brand_background.py.
    assert GEN_BG.is_file(), "the per-brand DMG background generator is missing"
    assert _layout()["background"] == "background.png"


def test_layout_has_window_size():
    data = _layout()
    assert "window" in data and "size" in data["window"]
    w, h = data["window"]["size"]
    # Match create-dmg --window-size — width should accommodate the bg
    assert w >= 540 and h >= 380


def test_layout_has_app_icon_position():
    data = _layout()
    icons = {i["name"]: i for i in data["icons"]}
    assert "Locksmith.app" in icons
    assert "Applications" in icons
    # Drag-target should be on the right of the app icon
    assert icons["Applications"]["pos"][0] > icons["Locksmith.app"]["pos"][0]


def test_layout_has_icon_size():
    data = _layout()
    assert data["icon_size"] >= 80
