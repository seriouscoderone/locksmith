"""The Qt startup splash (``locksmith.main._make_splash``).

Replaces PyInstaller's Tcl/Tk ``Splash()`` — that splash can't run inside a
macOS ``.app`` (so macOS had no splash) and DPI-rescales on Windows (the splash
"moves and shrinks"). A ``QSplashScreen`` works on every platform and is
DPI-correct.

``_make_splash`` loads its art from ``:/assets/custom/SplashScreen.png``, so
the test that exercises the happy path must register the brand bundle first
(see ``locksmith.core.branding.register_brand_resources``) — same as the real
boot sequence (``QApplication(...)`` -> ``set_global_styles(app)`` registers
-> ``_make_splash()`` reads ``:/``).
"""
import importlib
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "packaging"))


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_make_splash_returns_splashscreen_when_art_present(qapp):
    from PySide6.QtWidgets import QSplashScreen
    from locksmith.core import branding
    from locksmith.main import _make_splash

    brand_apply = importlib.import_module("brand_apply")
    out = REPO / "src" / "locksmith" / "release"  # default locksmith bundle
    brand_apply.apply("locksmith", REPO, out=out, check=False)

    branding._reset_cache_for_tests()
    try:
        branding.register_brand_resources()
        splash = _make_splash()
        assert isinstance(splash, QSplashScreen)
        assert not splash.pixmap().isNull()  # the bundled SplashScreen.png loaded
    finally:
        branding._reset_cache_for_tests()


def test_make_splash_returns_none_when_art_missing(qapp):
    """Missing art must yield None (no splash) rather than crash startup.

    ``_make_splash`` resolves its art from ``:/assets/custom/SplashScreen.png``
    (a Qt resource), not a disk path, so "missing art" now means "no brand
    bundle registered". Force that state directly (regardless of what any
    sibling test left registered) rather than relying on run order.
    """
    from locksmith.core import branding
    from locksmith.main import _make_splash

    branding._reset_cache_for_tests()  # unregisters — guarantee nothing is registered
    try:
        assert _make_splash() is None
    finally:
        branding._reset_cache_for_tests()
