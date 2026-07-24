"""The Qt startup splash (``locksmith.main._make_splash``).

Replaces PyInstaller's Tcl/Tk ``Splash()`` — that splash can't run inside a
macOS ``.app`` (so macOS had no splash) and DPI-rescales on Windows (the splash
"moves and shrinks"). A ``QSplashScreen`` works on every platform and is
DPI-correct.
"""
import pytest


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.mark.xfail(reason="_make_splash moves to :/ in Task 5 (atomic-brand-bundles)", strict=False)
def test_make_splash_returns_splashscreen_when_art_present(qapp):
    from PySide6.QtWidgets import QSplashScreen
    from locksmith.main import _make_splash

    splash = _make_splash()
    assert isinstance(splash, QSplashScreen)
    assert not splash.pixmap().isNull()  # the bundled SplashScreen.png loaded


def test_make_splash_returns_none_when_art_missing(qapp, monkeypatch, tmp_path):
    """Missing art must yield None (no splash) rather than crash startup."""
    import locksmith.ui.styles as styles
    # _make_splash resolves the art under _asset_root()/assets/custom/.
    monkeypatch.setattr(styles, "_asset_root", lambda: tmp_path, raising=True)
    from locksmith.main import _make_splash

    assert _make_splash() is None
