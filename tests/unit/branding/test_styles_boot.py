# tests/unit/branding/test_styles_boot.py
import importlib, os, sys
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts")); sys.path.insert(0, str(REPO / "packaging"))
brand_apply = importlib.import_module("brand_apply")
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap


def test_set_global_styles_registers_bundle_and_splash_resolves(monkeypatch):
    out = REPO / "src" / "locksmith" / "release"           # default locksmith bundle
    brand_apply.apply("locksmith", REPO, out=out, check=False)
    from locksmith.core import branding
    branding._reset_cache_for_tests()
    monkeypatch.delenv(branding.BRAND_CONFIG_ENV_VAR, raising=False)
    from locksmith.ui.styles import set_global_styles
    app = QApplication.instance() or QApplication([])
    try:
        set_global_styles(app)                                  # registers the rcc
        assert app.applicationName() == "Locksmith"
        assert not QPixmap(":/assets/custom/SplashScreen.png").isNull()   # splash via :/
    finally:
        branding._reset_cache_for_tests()   # unregisters — leave no bundle registered
