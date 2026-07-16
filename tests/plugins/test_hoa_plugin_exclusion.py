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

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from locksmith.plugins import manager as manager_module
from locksmith.plugins import storage
from locksmith.plugins.base import VaultPlugin
from locksmith.plugins.manager import PluginManager


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


def _fake_brand(*, peel_core_pages: bool):
    return SimpleNamespace(peel_core_pages=peel_core_pages)


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
