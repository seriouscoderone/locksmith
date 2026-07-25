"""Guard test: PyInstaller specs bundle the compiled brand resource bundle
(assets.rcc) from the brand release dir, not the loose assets/ tree.

After Tasks 3-5, all runtime asset access goes through :/ (assets.rcc
registered at startup via register_brand_resources()); _asset_root() has
zero remaining disk-read callers. Bundling the loose assets/ tree alongside
assets.rcc would ship duplicate/stale (non-brand-aliased) art for no reason.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_macos_spec_bundles_rcc_not_loose_assets():
    spec = (REPO / "packaging" / "Locksmith.macos.spec").read_text()
    assert "assets.rcc" in spec                       # the compiled bundle is shipped
    assert '(str(REPO_ROOT / "assets"), "assets")' not in spec   # loose tree dropped


def test_windows_spec_bundles_rcc():
    spec = (REPO / "packaging" / "Locksmith.windows.spec").read_text()
    assert "assets.rcc" in spec


def test_windows_spec_drops_loose_assets():
    spec = (REPO / "packaging" / "Locksmith.windows.spec").read_text()
    assert '(str(ASSETS), "assets")' not in spec
