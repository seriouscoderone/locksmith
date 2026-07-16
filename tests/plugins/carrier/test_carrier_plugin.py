# -*- encoding: utf-8 -*-
"""Tests for the bundled ``carrier`` role-plugin (Task 9).

Covers:
- The plugin declares the exact carrier_license gate (schema SAID + trusted
  DOI issuer AID + required "active" TEL state) — Tasks 6-8's gate/activation
  machinery consumes this declaration verbatim.
- ``get_pages()`` exposes the "carrier" placeholder page (a real QWidget,
  built via ``qtbot`` so Qt object lifetime is managed by the test).
- Because ``required_credential`` is set, ``discover_and_initialize_vault_ui``
  (Task 7) must not auto-register the plugin's surface — it stays dormant
  until ``reevaluate_role_gates`` reveals it (Task 8, exercised elsewhere).
- Brand-gating (this task's refinement): the carrier entry point is only
  loaded by ``PluginManager.discover()`` under a peel/HOA brand
  (``brand().peel_core_pages`` True); the default (non-HOA) Locksmith build
  must not load it at all, and kerifoundation's existing Task 2b exclusion
  under a peel brand must not regress.
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
from locksmith.plugins.carrier.plugin import CarrierPlugin
from locksmith.plugins.manager import PluginManager


def test_carrier_plugin_declares_the_license_gate():
    p = CarrierPlugin()
    rc = p.required_credential
    assert rc.schema_said == "EOBjUL6H9FQdr_PlXVU_cv_iaXdK5Pg8L3M2YQrnHivI"
    assert "EOtKW1M3PReijqHMu92uX5FG0fCPwIfH7plPQSifb34" in rc.issuer_aids
    assert rc.required_state == "active"


def test_carrier_plugin_exposes_a_placeholder_page(qtbot):
    p = CarrierPlugin()
    p.initialize(MagicMock())
    pages = p.get_pages()
    assert "carrier" in pages
    qtbot.addWidget(pages["carrier"])


def test_carrier_plugin_is_a_vault_plugin():
    assert issubclass(CarrierPlugin, VaultPlugin)


def test_carrier_plugin_vault_lifecycle_hooks_are_noops(qtbot):
    """on_vault_opened/on_vault_closed do no plugin-local work — gate
    evaluation/reveal is driven entirely by PluginManager.reevaluate_role_gates
    (Task 8). These must not raise."""
    p = CarrierPlugin()
    p.initialize(MagicMock())
    assert p.on_vault_opened(MagicMock()) is None
    assert p.on_vault_closed(MagicMock(), clear=True) is None


def test_carrier_plugin_menu_entry_and_section(qtbot):
    p = CarrierPlugin()
    p.initialize(MagicMock())
    entry = p.get_menu_entry()
    qtbot.addWidget(entry)
    assert p.get_menu_section() == []


def test_carrier_plugin_not_auto_registered_at_vault_ui_init(qtbot):
    """The concrete CarrierPlugin (not a generic gated stub) must stay
    dormant at vault-UI init — only reevaluate_role_gates may reveal it."""
    p = CarrierPlugin()
    p.initialize(MagicMock())
    mgr = object.__new__(PluginManager)
    mgr._plugins = {"carrier": p}
    vault_page = MagicMock()
    nav_menu = MagicMock()

    mgr.discover_and_initialize_vault_ui(vault_page, nav_menu)

    vault_page.register_page.assert_not_called()
    nav_menu.register_plugin_section.assert_not_called()


# --------------------------------------------------------------------------
# Brand-gating: carrier entry point loads only under peel/HOA brands.
# --------------------------------------------------------------------------

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


def test_carrier_loads_under_peel_brand(isolated_plugin_root, fake_app, monkeypatch, qtbot):
    # discover() runs CarrierPlugin.initialize(), which builds the real
    # CarrierPlaceholderPage QWidget — qtbot guarantees a QApplication
    # exists for that construction.
    monkeypatch.setattr(
        manager_module, "brand", lambda: _fake_brand(peel_core_pages=True),
    )
    mgr = PluginManager(fake_app, keri_base=isolated_plugin_root / "keri")
    mgr.discover()
    assert "carrier" in mgr.loaded_ids()
    carrier = mgr.get_plugin("carrier")
    assert isinstance(carrier, VaultPlugin)
    # Task 2b's kerifoundation exclusion must not regress under the peel brand.
    assert "kerifoundation" not in mgr.loaded_ids()


def test_carrier_skipped_under_default_brand(isolated_plugin_root, fake_app, monkeypatch):
    monkeypatch.setattr(
        manager_module, "brand", lambda: _fake_brand(peel_core_pages=False),
    )
    mgr = PluginManager(fake_app, keri_base=isolated_plugin_root / "keri")
    mgr.discover()
    assert "carrier" not in mgr.loaded_ids()
    assert mgr.get_plugin("carrier") is None
    # Default build keeps kerifoundation exactly as before.
    assert "kerifoundation" in mgr.loaded_ids()


def test_carrier_skipped_under_ambient_default_brand(isolated_plugin_root, fake_app):
    """No monkeypatch of brand() at all — the real default brand (Locksmith,
    peel_core_pages=False) must not load carrier. This is the hard
    constraint: the DEFAULT locksmith build must stay carrier-free."""
    mgr = PluginManager(fake_app, keri_base=isolated_plugin_root / "keri")
    mgr.discover()
    assert "carrier" not in mgr.loaded_ids()
