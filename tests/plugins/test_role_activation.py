# -*- encoding: utf-8 -*-
"""Tests for the role-activation seam + RevealBundledSurface strategy (Task 7).

Covers:
- ``RevealBundledSurface`` strategy: register/unregister the plugin's surface
  (pages + menu entry) on activate/deactivate.
- ``PluginManager.reevaluate_role_gates`` transition logic: fire activation
  only on the unsatisfied->satisfied edge, deactivate on satisfied->unsatisfied,
  and the ``on_role_credential_activated`` named seam.
- ``PluginManager._gated_plugins`` / ``_held_credentials`` / ``_matching_credential``
  helpers, including the credentialing.py -> gate-shape mapping and the
  ``chain_verified`` derivation from the reger ``saved`` (fully-verified) index.

Strategy + transition tests mock the surface host and the vault-credential
source (real end-to-end wiring is Task 10). One offscreen UI test exercises the
real HoaVaultPage host methods (register/unregister page + menu add/remove).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from locksmith.plugins import manager as m
from locksmith.plugins.credential_gate import RequiredCredential
from locksmith.plugins.role_activation import (
    RevealBundledSurface,
    RoleActivationStrategy,
)


# --------------------------------------------------------------------------
# RevealBundledSurface strategy
# --------------------------------------------------------------------------

def test_reveal_registers_surface_on_activate():
    host = MagicMock()
    plugin = MagicMock()
    plugin.plugin_id = "carrier"
    plugin.get_pages.return_value = {"carrier": MagicMock()}
    plugin.get_menu_entry.return_value = MagicMock()
    plugin.get_menu_section.return_value = []
    RevealBundledSurface().activate(plugin, MagicMock(), host)
    host.register_page.assert_called_once()
    host.add_menu_entry.assert_called_once()


def test_reveal_unregisters_surface_on_deactivate():
    host = MagicMock()
    plugin = MagicMock()
    plugin.plugin_id = "carrier"
    plugin.get_pages.return_value = {"carrier": MagicMock()}
    RevealBundledSurface().deactivate(plugin, host)
    host.unregister_page.assert_called_once_with("carrier")
    host.remove_menu_entry.assert_called_once_with("carrier")


def test_reveal_skips_menu_entry_when_none():
    host = MagicMock()
    plugin = MagicMock()
    plugin.plugin_id = "carrier"
    plugin.get_pages.return_value = {"carrier": MagicMock()}
    plugin.get_menu_entry.return_value = None
    RevealBundledSurface().activate(plugin, MagicMock(), host)
    host.register_page.assert_called_once()
    host.add_menu_entry.assert_not_called()


def test_reveal_bundled_surface_satisfies_protocol():
    assert isinstance(RevealBundledSurface(), RoleActivationStrategy)


# --------------------------------------------------------------------------
# reevaluate_role_gates — transition logic
# --------------------------------------------------------------------------

def _bare_manager():
    """A PluginManager with __init__ bypassed, wired with the role-gate state
    the reevaluate loop reads. Individual tests override collaborators."""
    mgr = object.__new__(m.PluginManager)
    mgr._activation_strategy = MagicMock()
    mgr._active_roles = set()
    mgr._surface_host = MagicMock()
    return mgr


def test_reevaluate_fires_activation_only_on_transition(monkeypatch):
    mgr = _bare_manager()
    plugin = MagicMock()
    plugin.plugin_id = "carrier"
    plugin.required_credential = MagicMock()
    mgr._gated_plugins = lambda: [plugin]
    mgr._held_credentials = lambda vault: ["creds"]
    mgr._matching_credential = lambda held, req: "the-cred"
    fired = []
    monkeypatch.setattr(m, "gate_satisfied", lambda creds, req: True)
    mgr.on_role_credential_activated = lambda p, c: fired.append(p.plugin_id)

    mgr.reevaluate_role_gates(MagicMock())
    mgr.reevaluate_role_gates(MagicMock())  # second run: no new transition

    assert fired == ["carrier"]
    mgr._activation_strategy.activate.assert_called_once()
    assert "carrier" in mgr._active_roles


def test_reevaluate_passes_matched_credential_to_activate(monkeypatch):
    mgr = _bare_manager()
    plugin = MagicMock()
    plugin.plugin_id = "carrier"
    plugin.required_credential = MagicMock()
    mgr._gated_plugins = lambda: [plugin]
    mgr._held_credentials = lambda vault: ["held"]
    mgr._matching_credential = lambda held, req: "MATCHED"
    monkeypatch.setattr(m, "gate_satisfied", lambda creds, req: True)

    mgr.reevaluate_role_gates(MagicMock())

    mgr._activation_strategy.activate.assert_called_once_with(
        plugin, "MATCHED", mgr._surface_host,
    )


def test_reevaluate_deactivates_on_revocation(monkeypatch):
    mgr = _bare_manager()
    plugin = MagicMock()
    plugin.plugin_id = "carrier"
    plugin.required_credential = MagicMock()
    mgr._gated_plugins = lambda: [plugin]
    mgr._held_credentials = lambda vault: []
    mgr._matching_credential = lambda held, req: None
    mgr._active_roles.add("carrier")  # already active
    monkeypatch.setattr(m, "gate_satisfied", lambda creds, req: False)

    mgr.reevaluate_role_gates(MagicMock())

    mgr._activation_strategy.deactivate.assert_called_once_with(
        plugin, mgr._surface_host,
    )
    assert "carrier" not in mgr._active_roles


def test_reevaluate_noop_when_unsatisfied_and_inactive(monkeypatch):
    mgr = _bare_manager()
    plugin = MagicMock()
    plugin.plugin_id = "carrier"
    plugin.required_credential = MagicMock()
    mgr._gated_plugins = lambda: [plugin]
    mgr._held_credentials = lambda vault: []
    monkeypatch.setattr(m, "gate_satisfied", lambda creds, req: False)

    mgr.reevaluate_role_gates(MagicMock())

    mgr._activation_strategy.activate.assert_not_called()
    mgr._activation_strategy.deactivate.assert_not_called()
    assert mgr._active_roles == set()


def test_reevaluate_noop_when_satisfied_and_already_active(monkeypatch):
    mgr = _bare_manager()
    plugin = MagicMock()
    plugin.plugin_id = "carrier"
    plugin.required_credential = MagicMock()
    mgr._gated_plugins = lambda: [plugin]
    mgr._held_credentials = lambda vault: ["held"]
    mgr._matching_credential = lambda held, req: "c"
    mgr._active_roles.add("carrier")
    monkeypatch.setattr(m, "gate_satisfied", lambda creds, req: True)

    mgr.reevaluate_role_gates(MagicMock())

    mgr._activation_strategy.activate.assert_not_called()
    mgr._activation_strategy.deactivate.assert_not_called()


def test_on_role_credential_activated_default_is_noop():
    mgr = _bare_manager()
    # Default seam must exist and not raise.
    assert mgr.on_role_credential_activated(MagicMock(), MagicMock()) is None


# --------------------------------------------------------------------------
# _gated_plugins
# --------------------------------------------------------------------------

def test_gated_plugins_selects_only_credential_gated():
    mgr = object.__new__(m.PluginManager)
    gated = SimpleNamespace(
        plugin_id="carrier",
        required_credential=RequiredCredential(schema_said="ES", issuer_aids=["EI"]),
    )
    ungated = SimpleNamespace(plugin_id="open", required_credential=None)
    no_attr = SimpleNamespace(plugin_id="legacy")  # no required_credential attr
    mgr._plugins = {"carrier": gated, "open": ungated, "legacy": no_attr}

    ids = [p.plugin_id for p in mgr._gated_plugins()]
    assert ids == ["carrier"]


# --------------------------------------------------------------------------
# _held_credentials — credentialing.py -> gate-shape mapping
# --------------------------------------------------------------------------

class _FakeSaider:
    def __init__(self, qb64):
        self.qb64 = qb64


class _FakeStatus:
    def __init__(self, et):
        self.et = et


class _FakeTever:
    def __init__(self, state_by_said):
        self._state_by_said = state_by_said

    def vcState(self, said):
        return self._state_by_said.get(said)


class _FakeCreder:
    def __init__(self, schema, issuer, regid):
        self.schema = schema
        self.issuer = issuer
        self.regid = regid


class _Getter:
    """Mimics a keri suber .get(keys=(k,)) lookup over a dict keyed by the
    first key component."""

    def __init__(self, data):
        self._data = data

    def get(self, keys):
        key = keys[0] if isinstance(keys, tuple) else keys
        return self._data.get(key)


def _fake_vault(*, habs, subjs, creds, saved, tevers):
    reger = SimpleNamespace(
        subjs=_Getter(subjs),
        creds=_Getter(creds),
        saved=_Getter(saved),
        tevers=tevers,
    )
    return SimpleNamespace(
        hby=SimpleNamespace(habs=habs),
        rgy=SimpleNamespace(reger=reger),
    )


def test_held_credentials_maps_verified_active_credential():
    mgr = object.__new__(m.PluginManager)
    vault = _fake_vault(
        habs={"EHolder": object()},
        subjs={"EHolder": [_FakeSaider("ECredSaid")]},
        creds={"ECredSaid": _FakeCreder("ESchema", "EIssuer", "EReg")},
        saved={"ECredSaid": _FakeSaider("ECredSaid")},  # present => verified
        tevers={"EReg": _FakeTever({"ECredSaid": _FakeStatus("iss")})},
    )
    held = mgr._held_credentials(vault)
    assert len(held) == 1
    c = held[0]
    assert c.schema_said == "ESchema"
    assert c.issuer_aid == "EIssuer"
    assert c.state == "active"
    assert c.chain_verified is True


def test_held_credentials_backed_issuance_is_active():
    mgr = object.__new__(m.PluginManager)
    vault = _fake_vault(
        habs={"EHolder": object()},
        subjs={"EHolder": [_FakeSaider("ECredSaid")]},
        creds={"ECredSaid": _FakeCreder("ESchema", "EIssuer", "EReg")},
        saved={"ECredSaid": _FakeSaider("ECredSaid")},
        tevers={"EReg": _FakeTever({"ECredSaid": _FakeStatus("bis")})},
    )
    held = mgr._held_credentials(vault)
    assert held[0].state == "active"


def test_held_credentials_revoked_maps_to_revoked_state():
    mgr = object.__new__(m.PluginManager)
    vault = _fake_vault(
        habs={"EHolder": object()},
        subjs={"EHolder": [_FakeSaider("ECredSaid")]},
        creds={"ECredSaid": _FakeCreder("ESchema", "EIssuer", "EReg")},
        saved={"ECredSaid": _FakeSaider("ECredSaid")},
        tevers={"EReg": _FakeTever({"ECredSaid": _FakeStatus("rev")})},
    )
    held = mgr._held_credentials(vault)
    assert held[0].state == "revoked"
    # brv (backed revoked) also maps to revoked
    vault.rgy.reger.tevers = {"EReg": _FakeTever({"ECredSaid": _FakeStatus("brv")})}
    assert mgr._held_credentials(vault)[0].state == "revoked"


def test_held_credentials_unsaved_maps_chain_verified_false():
    """A credential enumerated but absent from the reger ``saved`` (fully
    verified) index -- e.g. sitting in missing-chain/registry/schema escrow --
    must map to chain_verified=False, never silently trusted."""
    mgr = object.__new__(m.PluginManager)
    vault = _fake_vault(
        habs={"EHolder": object()},
        subjs={"EHolder": [_FakeSaider("EEscrowed")]},
        creds={"EEscrowed": _FakeCreder("ESchema", "EIssuer", "EReg")},
        saved={},  # NOT in saved index => not fully verified
        tevers={"EReg": _FakeTever({"EEscrowed": _FakeStatus("iss")})},
    )
    held = mgr._held_credentials(vault)
    assert held[0].chain_verified is False


def test_held_credentials_missing_tever_maps_state_unknown():
    mgr = object.__new__(m.PluginManager)
    vault = _fake_vault(
        habs={"EHolder": object()},
        subjs={"EHolder": [_FakeSaider("ECredSaid")]},
        creds={"ECredSaid": _FakeCreder("ESchema", "EIssuer", "EMissingReg")},
        saved={"ECredSaid": _FakeSaider("ECredSaid")},
        tevers={},  # registry Tever not present => state cannot be resolved
    )
    held = mgr._held_credentials(vault)
    assert held[0].state == "unknown"


def test_held_credentials_dedupes_across_habs():
    mgr = object.__new__(m.PluginManager)
    shared = _FakeSaider("EShared")
    vault = _fake_vault(
        habs={"EHolderA": object(), "EHolderB": object()},
        subjs={"EHolderA": [shared], "EHolderB": [shared]},
        creds={"EShared": _FakeCreder("ESchema", "EIssuer", "EReg")},
        saved={"EShared": _FakeSaider("EShared")},
        tevers={"EReg": _FakeTever({"EShared": _FakeStatus("iss")})},
    )
    held = mgr._held_credentials(vault)
    assert len(held) == 1


# --------------------------------------------------------------------------
# _matching_credential
# --------------------------------------------------------------------------

REQ = RequiredCredential(schema_said="ESchema", issuer_aids=["EIssuer"], required_state="active")


def _held(schema="ESchema", issuer="EIssuer", state="active", chain=True):
    return SimpleNamespace(
        schema_said=schema, issuer_aid=issuer, state=state, chain_verified=chain,
    )


def test_matching_credential_returns_first_satisfying():
    mgr = object.__new__(m.PluginManager)
    good = _held()
    held = [_held(schema="EOther"), good]
    assert mgr._matching_credential(held, REQ) is good


def test_matching_credential_returns_none_when_no_match():
    mgr = object.__new__(m.PluginManager)
    held = [_held(chain=False), _held(state="revoked")]
    assert mgr._matching_credential(held, REQ) is None


# --------------------------------------------------------------------------
# discover_and_initialize_vault_ui — gated plugins must NOT auto-register
# --------------------------------------------------------------------------

def test_vault_ui_init_skips_gated_plugins_and_sets_surface_host():
    from locksmith.plugins.base import VaultPlugin

    class _Gated(VaultPlugin):
        plugin_id = "carrier"
        required_credential = RequiredCredential(schema_said="ES", issuer_aids=["EI"])

        def initialize(self, app): ...
        def on_vault_opened(self, vault): ...
        def on_vault_closed(self, vault, *, clear=False): ...
        def get_menu_entry(self): return MagicMock()
        def get_menu_section(self): return []
        def get_pages(self): return {"carrier": MagicMock()}

    class _Ungated(_Gated):
        plugin_id = "open"
        required_credential = None

    mgr = object.__new__(m.PluginManager)
    mgr._plugins = {"carrier": _Gated(), "open": _Ungated()}
    vault_page = MagicMock()
    nav_menu = MagicMock()

    mgr.discover_and_initialize_vault_ui(vault_page, nav_menu)

    # Surface host captured for later gate re-evaluation.
    assert mgr._surface_host is vault_page
    # Ungated plugin auto-registered exactly as before; gated one skipped.
    nav_menu.register_plugin_section.assert_called_once()
    assert nav_menu.register_plugin_section.call_args.args[0] == "open"


def test_vault_ui_init_skips_non_vault_plugins():
    from locksmith.plugins.base import AppPlugin

    class _AppOnly(AppPlugin):
        plugin_id = "appish"

        def initialize(self, app): ...

    mgr = object.__new__(m.PluginManager)
    mgr._plugins = {"appish": _AppOnly()}
    vault_page = MagicMock()
    nav_menu = MagicMock()

    mgr.discover_and_initialize_vault_ui(vault_page, nav_menu)

    nav_menu.register_plugin_section.assert_not_called()
    vault_page.register_page.assert_not_called()


def test_vault_ui_init_swallows_plugin_registration_error(caplog):
    from locksmith.plugins.base import VaultPlugin

    class _Boom(VaultPlugin):
        plugin_id = "boom"
        required_credential = None

        def initialize(self, app): ...
        def on_vault_opened(self, vault): ...
        def on_vault_closed(self, vault, *, clear=False): ...
        def get_menu_entry(self): return MagicMock()
        def get_menu_section(self): return []
        def get_pages(self): raise RuntimeError("kaboom")

    mgr = object.__new__(m.PluginManager)
    mgr._plugins = {"boom": _Boom()}
    vault_page = MagicMock()
    nav_menu = MagicMock()

    # Must not propagate — a misbehaving plugin can't break vault-UI init.
    mgr.discover_and_initialize_vault_ui(vault_page, nav_menu)
    nav_menu.register_plugin_section.assert_not_called()


def test_vault_ui_none_menu_entry_skips_nav_registration():
    """A shell-style plugin (HOA #4) that registers its own menu entries
    directly (or none at all) returns None from get_menu_entry() -- the
    manager must still register its static pages, but skip the nav-menu
    registration call entirely rather than passing None through."""
    from locksmith.plugins.base import VaultPlugin

    class _NoMenuEntry(VaultPlugin):
        plugin_id = "shell"
        required_credential = None

        def initialize(self, app): ...
        def on_vault_opened(self, vault): ...
        def on_vault_closed(self, vault, *, clear=False): ...
        def get_menu_entry(self): return None
        def get_menu_section(self): return []
        def get_pages(self): return {"shell": MagicMock()}

    mgr = object.__new__(m.PluginManager)
    mgr._plugins = {"shell": _NoMenuEntry()}
    vault_page = MagicMock()
    nav_menu = MagicMock()

    mgr.discover_and_initialize_vault_ui(vault_page, nav_menu)

    vault_page.register_page.assert_called_once()
    nav_menu.register_plugin_section.assert_not_called()


def test_vault_ui_ready_fanned_out_after_registration():
    """After the registration loop, every VaultPlugin's on_vault_ui_ready
    hook is fanned out exactly once with the vault_page host (HOA #4 shell
    seam) -- this is what lets a shell plugin register conditional surfaces
    (multiple pages/menu entries, error fallbacks) directly."""
    from locksmith.plugins.base import VaultPlugin

    class _Shell(VaultPlugin):
        plugin_id = "shell"
        required_credential = None

        def initialize(self, app): ...
        def on_vault_opened(self, vault): ...
        def on_vault_closed(self, vault, *, clear=False): ...
        def get_menu_entry(self): return None
        def get_menu_section(self): return []
        def get_pages(self): return {}

    shell = _Shell()
    shell.on_vault_ui_ready = MagicMock()
    mgr = object.__new__(m.PluginManager)
    mgr._plugins = {"shell": shell}
    vault_page = MagicMock()
    nav_menu = MagicMock()

    mgr.discover_and_initialize_vault_ui(vault_page, nav_menu)

    shell.on_vault_ui_ready.assert_called_once_with(vault_page)


# --------------------------------------------------------------------------
# Real HoaVaultPage host methods (offscreen UI) — page + menu add/remove
# --------------------------------------------------------------------------

def test_hoa_page_host_register_and_unregister_surface(qtbot):
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QPushButton, QWidget

    from locksmith.ui.vault.hoa_page import HoaVaultPage
    from locksmith.ui.vault.menu import MenuButton

    parent = QWidget()
    pm = MagicMock()
    pm.all_states.return_value = []
    parent.app = SimpleNamespace(config=SimpleNamespace(), vault=None, plugin_manager=pm)
    qtbot.addWidget(parent)
    page = HoaVaultPage(parent)
    qtbot.addWidget(page)

    entry = MenuButton(icon=QIcon())
    entry.setObjectName("vaultNavMenu.carrierEntryButton")
    plugin = SimpleNamespace(
        plugin_id="carrier",
        get_pages=lambda: {"carrier": QWidget()},
        get_menu_entry=lambda: entry,
        get_menu_section=lambda: [],
    )

    strategy = RevealBundledSurface()
    strategy.activate(plugin, object(), page)

    assert "carrier" in page.registered_page_keys()
    names = {b.objectName() for b in page.nav_menu.findChildren(QPushButton) if b.objectName()}
    assert "vaultNavMenu.carrierEntryButton" in names

    strategy.deactivate(plugin, page)

    assert "carrier" not in page.registered_page_keys()
    names_after = {b.objectName() for b in page.nav_menu.findChildren(QPushButton) if b.objectName()}
    assert "vaultNavMenu.carrierEntryButton" not in names_after


def test_hoa_page_unregister_unknown_page_is_safe(qtbot):
    from PySide6.QtWidgets import QWidget

    from locksmith.ui.vault.hoa_page import HoaVaultPage

    parent = QWidget()
    pm = MagicMock()
    pm.all_states.return_value = []
    parent.app = SimpleNamespace(config=SimpleNamespace(), vault=None, plugin_manager=pm)
    qtbot.addWidget(parent)
    page = HoaVaultPage(parent)
    qtbot.addWidget(page)

    # No-op, must not raise.
    page.unregister_page("does-not-exist")
    page.remove_menu_entry("does-not-exist")
