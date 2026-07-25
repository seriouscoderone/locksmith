import importlib
import os
import gc
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

_REPO = Path(__file__).resolve().parents[1]


def _build_default_bundle():
    rcc = _REPO / "src" / "locksmith" / "release" / "assets.rcc"
    if not rcc.is_file():
        sys.path.insert(0, str(_REPO / "scripts")); sys.path.insert(0, str(_REPO / "packaging"))
        importlib.import_module("brand_apply").apply(
            "locksmith", _REPO, out=_REPO / "src" / "locksmith" / "release", check=False)
    return rcc


@pytest.fixture(scope="session", autouse=True)
def _ensure_default_brand_bundle():
    """Build (NOT register) the reference bundle once so :/ can be registered.

    resources_rc.py no longer exists; compiled assets live in the gitignored
    release/assets.rcc built by brand_apply. Registration is per-test, because
    Qt resource overlap is first-registered-wins — a global default would
    shadow brand-override tests. Cheap + idempotent.
    """
    _build_default_bundle()
    yield


@pytest.fixture
def default_brand_resources(monkeypatch):
    """Opt-in: register the default bundle for one test, then detach.

    For generic tests that load :/assets/... without calling set_global_styles.
    Do NOT combine with a brand-override in the same test (first-wins).
    """
    from locksmith.core import branding
    _build_default_bundle()
    monkeypatch.delenv(branding.BRAND_CONFIG_ENV_VAR, raising=False)
    branding._reset_cache_for_tests()
    rcc = branding.register_brand_resources()
    yield rcc
    branding._reset_cache_for_tests()   # unregisters (see Task 4)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    app.closeAllWindows()
    app.processEvents()
    app.quit()
    gc.collect()


@pytest.fixture(autouse=True)
def cleanup_qt_widgets(qapp):
    yield
    for widget in list(qapp.topLevelWidgets()):
        widget.close()
        widget.deleteLater()
    qapp.processEvents()
    gc.collect()
