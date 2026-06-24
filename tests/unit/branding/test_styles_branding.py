import importlib
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

branding = importlib.import_module("locksmith.core.branding")


@pytest.fixture
def app():
    from PySide6.QtWidgets import QApplication
    inst = QApplication.instance() or QApplication([])
    yield inst


def test_set_global_styles_applies_brand_identity(app):
    from locksmith.ui import styles
    branding._reset_cache_for_tests()
    styles.set_global_styles(app)
    assert app.applicationName() == branding.brand().display_name == "Locksmith"
    assert app.organizationName() == branding.brand().org_name == "keri.host"
    assert app.organizationDomain() == branding.brand().org_domain == "keri.host"


def test_set_global_styles_applies_theme(app, tmp_path, monkeypatch):
    import json
    from locksmith.ui import styles, colors
    cfg = tmp_path / "brandcfg.json"
    cfg.write_text(json.dumps({"display_name": "Acme", "theme": {"primary": "#0055AA"}}))
    monkeypatch.setenv("LOCKSMITH_BRAND_CONFIG", str(cfg))
    branding._reset_cache_for_tests()
    try:
        styles.set_global_styles(app)
        assert colors.PRIMARY == "#0055AA"
    finally:
        colors.PRIMARY = "#F57B03"
