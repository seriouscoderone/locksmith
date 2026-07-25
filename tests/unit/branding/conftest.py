"""Test-isolation shims for the branding suite.

Two independent, order-dependent landmines make ``pytest tests/unit/branding/``
(the whole directory) fail depending on collection/run order, while every file
passes on its own. Both are neutralised here so the directory runs green
regardless of order. (The session-scoped ``qapp``/``cleanup_qt_widgets``
fixtures in ``tests/conftest.py`` do NOT apply: ``tests/unit/pytest.ini`` makes
``tests/unit`` the rootdir, so pytest's ``confcutdir`` stops before that root
conftest.)

1. Qt singleton *type*. Sibling tests create the process-wide Qt singleton as a
   bare ``QGuiApplication`` (``QGuiApplication.instance() or
   QGuiApplication([])``), whereas ``test_styles_branding`` /
   ``test_styles_boot`` need a ``QApplication`` — only the latter has
   ``setStyle`` (``styles.set_global_styles`` calls it). Qt allows exactly one
   application object per process, so whichever test ran first won the
   singleton; a ``QGuiApplication``-first order left the styles tests calling
   ``setStyle`` on a ``QGuiApplication`` -> ``AttributeError``. We create the
   ``QApplication`` *superset* up front (session-scoped, autouse) so every
   later ``*.instance()`` call — widget or GUI flavour — resolves to it.

2. ``keri`` namespace shadow (root cause). Several sibling tests do
   ``sys.path.insert(0, <repo>/scripts)`` at import time. ``scripts/keri/`` is
   a kli config-data directory (``cf/*.json`` witness OOBIs) with no
   ``__init__.py``, so once ``scripts`` is on ``sys.path[0]`` a *first*
   ``import keri`` resolves to that PEP-420 namespace package instead of real
   keripy — and namespace packages have no ``__version__``, so keripy's own
   ``from keri import __version__`` blows up (``ImportError: ... 'keri'
   (unknown location)``) the first time any test imports a keri-backed module
   (e.g. the kerifoundation plugin). Importing the real ``keri`` here —
   conftest runs before any test module's ``sys.path.insert`` — caches it in
   ``sys.modules`` so the data directory can never win.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# (2) Cache real keripy before any sibling test inserts <repo>/scripts, whose
#     ``keri/`` data dir would otherwise namespace-shadow it. See docstring.
import keri  # noqa: E402,F401

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _branding_qapplication():
    """Own the process-wide Qt singleton as a ``QApplication`` (widget-level
    superset of ``QGuiApplication``) before any per-test app fixture runs, so
    the styles tests' ``setStyle`` always has a real ``QApplication``. See
    docstring (1)."""
    app = QApplication.instance() or QApplication([])
    yield app
