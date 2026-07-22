# -*- encoding: utf-8 -*-
"""Brand-gated exclusion of the in-tree ``kerifoundation`` plugin.

The HOA peel must not load the KERI Foundation wallet-provider plugin at
runtime when the active brand sets ``peel_core_pages`` (the HOA bootstrap
flag). ``pyproject.toml``'s entry-point declaration is shared across brands
and stays untouched (removing it there broke the default Locksmith build in
an earlier attempt — see backlog note); the exclusion must happen inside
``PluginManager.discover()``, gated on the active brand, by filtering the
entry point whose name is ``kerifoundation`` before it is loaded/instantiated.

Default (non-HOA) brand must load kerifoundation exactly as before —
``tests/test_plugins_manager.py::test_entry_point_fallback_still_works``
already guards that; this file adds an explicit brand-gated pair of tests
plus a default-brand sanity check local to the exclusion feature.
"""
from __future__ import annotations

import logging
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from locksmith.plugins import manager as manager_module
from locksmith.plugins import storage
from locksmith.plugins.base import VaultPlugin
from locksmith.plugins.manager import PluginManager

# keri ogler loggers have propagate=False by default, which prevents pytest
# caplog (which installs its handler on the root logger only) from seeing
# them. Mirrors tests/test_plugins_manager.py::_caplog_propagate.
_LOGGERS_TO_PROPAGATE = ["locksmith.plugins.manager"]


@contextmanager
def _caplog_propagate(caplog, level="INFO"):
    loggers = [logging.getLogger(n) for n in _LOGGERS_TO_PROPAGATE]
    orig_propagate = [lg.propagate for lg in loggers]
    orig_level = [lg.level for lg in loggers]
    for lg in loggers:
        lg.propagate = True
        lg.setLevel(logging.DEBUG)
    try:
        with caplog.at_level(level):
            yield
    finally:
        for lg, prop, lvl in zip(loggers, orig_propagate, orig_level):
            lg.propagate = prop
            lg.setLevel(lvl)


@pytest.fixture
def isolated_plugin_root(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    if "echo_app" in sys.modules:
        del sys.modules["echo_app"]
    yield tmp_path
    if "echo_app" in sys.modules:
        del sys.modules["echo_app"]


@pytest.fixture
def fake_app():
    from locksmith.core.configing import Environments
    app = MagicMock()
    app.config = SimpleNamespace(base="", environment=Environments.DEVELOPMENT)
    return app


def _fake_brand(*, peel_core_pages: bool, bundled_plugins: tuple = ()):
    return SimpleNamespace(
        peel_core_pages=peel_core_pages, bundled_plugins=bundled_plugins,
    )


def test_kerifoundation_excluded_when_brand_peels_core_pages(
    isolated_plugin_root, fake_app, monkeypatch,
):
    monkeypatch.setattr(
        manager_module, "brand", lambda: _fake_brand(peel_core_pages=True),
    )
    mgr = PluginManager(fake_app, keri_base=isolated_plugin_root / "keri")
    mgr.discover()
    assert "kerifoundation" not in mgr.loaded_ids()
    assert mgr.get_plugin("kerifoundation") is None


def test_kerifoundation_loads_when_brand_does_not_peel_core_pages(
    isolated_plugin_root, fake_app, monkeypatch,
):
    monkeypatch.setattr(
        manager_module, "brand", lambda: _fake_brand(peel_core_pages=False),
    )
    mgr = PluginManager(fake_app, keri_base=isolated_plugin_root / "keri")
    mgr.discover()
    assert "kerifoundation" in mgr.loaded_ids()
    kf = mgr.get_plugin("kerifoundation")
    assert isinstance(kf, VaultPlugin)


def test_kerifoundation_loads_under_ambient_default_brand(
    isolated_plugin_root, fake_app,
):
    """No monkeypatch of brand() at all — the real default brand (Locksmith,
    peel_core_pages=False) must still load kerifoundation, matching
    tests/test_plugins_manager.py::test_entry_point_fallback_still_works."""
    mgr = PluginManager(fake_app, keri_base=isolated_plugin_root / "keri")
    mgr.discover()
    assert "kerifoundation" in mgr.loaded_ids()


# --------------------------------------------------------------------------
# [plugins] bundled brand-composition gating (HOA #4): the carrier entry
# point — a BUNDLED_ONLY_PLUGIN_IDS member — loads iff the active brand
# explicitly lists it under bundled_plugins, replacing the old peel-based
# HOA_ONLY_PLUGIN_IDS heuristic. kerifoundation's HOA_PEELED_PLUGIN_IDS path
# is untouched by this change.
# --------------------------------------------------------------------------

def test_bundled_only_plugin_skipped_when_brand_omits_it(
    isolated_plugin_root, fake_app, monkeypatch, caplog,
):
    monkeypatch.setattr(
        manager_module, "brand",
        lambda: _fake_brand(peel_core_pages=True, bundled_plugins=()),
    )
    mgr = PluginManager(fake_app, keri_base=isolated_plugin_root / "keri")
    with _caplog_propagate(caplog, "INFO"):
        mgr.discover()
    assert "carrier" not in mgr.loaded_ids()
    assert mgr.get_plugin("carrier") is None
    assert any(
        "plugin.skipped reason=not_bundled plugin_id=carrier" in rec.getMessage()
        for rec in caplog.records
    )


def test_bundled_only_plugin_loads_when_brand_lists_it(
    isolated_plugin_root, fake_app, monkeypatch, qtbot,
):
    # discover() runs CarrierPlugin.initialize(), which builds the real
    # CarrierPlaceholderPage QWidget — qtbot guarantees a QApplication exists.
    monkeypatch.setattr(
        manager_module, "brand",
        lambda: _fake_brand(peel_core_pages=False, bundled_plugins=("carrier",)),
    )
    mgr = PluginManager(fake_app, keri_base=isolated_plugin_root / "keri")
    mgr.discover()
    assert "carrier" in mgr.loaded_ids()
    assert mgr.get_plugin("carrier") is not None


def test_kerifoundation_still_skipped_under_peel(
    isolated_plugin_root, fake_app, monkeypatch,
):
    """Unchanged HOA_PEELED_PLUGIN_IDS behavior: kerifoundation stays
    excluded under a peel brand regardless of bundled_plugins."""
    monkeypatch.setattr(
        manager_module, "brand",
        lambda: _fake_brand(peel_core_pages=True, bundled_plugins=("carrier",)),
    )
    mgr = PluginManager(fake_app, keri_base=isolated_plugin_root / "keri")
    mgr.discover()
    assert "kerifoundation" not in mgr.loaded_ids()
    assert mgr.get_plugin("kerifoundation") is None
