import importlib
import os
import shutil
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts")); sys.path.insert(0, str(REPO / "packaging"))
brand_apply = importlib.import_module("brand_apply")

branding = importlib.import_module("locksmith.core.branding")

_DEFAULT_RCC = REPO / "src" / "locksmith" / "release" / "assets.rcc"


def _ensure_default_bundle() -> Path:
    """Build the reference locksmith bundle if it isn't already on disk.

    ``set_global_styles`` now registers a real ``assets.rcc`` as its first
    action (``register_brand_resources()`` fails loud without one), so any
    test that calls it needs a bundle to resolve — this builds the default
    one instead of relying on a leftover from a previous task/run.
    """
    if not _DEFAULT_RCC.is_file():
        brand_apply.apply("locksmith", REPO, out=_DEFAULT_RCC.parent, check=False)
    return _DEFAULT_RCC


@pytest.fixture
def app():
    from PySide6.QtWidgets import QApplication
    inst = QApplication.instance() or QApplication([])
    yield inst


def test_set_global_styles_applies_brand_identity(app):
    from locksmith.ui import styles
    _ensure_default_bundle()
    branding._reset_cache_for_tests()
    try:
        styles.set_global_styles(app)
        assert app.applicationName() == branding.brand().display_name == "Locksmith"
        assert app.organizationName() == branding.brand().org_name == "keri.host"
        assert app.organizationDomain() == branding.brand().org_domain == "keri.host"
    finally:
        branding._reset_cache_for_tests()


def test_set_global_styles_applies_theme(app, tmp_path, monkeypatch):
    import json
    from locksmith.ui import styles, colors
    default_rcc = _ensure_default_bundle()
    cfg = tmp_path / "brandcfg.json"
    cfg.write_text(json.dumps({"display_name": "Acme", "theme": {"primary": "#0055AA"}}))
    # register_brand_resources() looks for assets.rcc beside the resolved
    # brand.json — stage a real (default) one so registration succeeds while
    # the display_name/theme override still comes from brandcfg.json.
    shutil.copyfile(default_rcc, tmp_path / "assets.rcc")
    monkeypatch.setenv("LOCKSMITH_BRAND_CONFIG", str(cfg))
    branding._reset_cache_for_tests()
    try:
        styles.set_global_styles(app)
        assert colors.PRIMARY == "#0055AA"
    finally:
        colors.PRIMARY = "#F57B03"
        branding._reset_cache_for_tests()
