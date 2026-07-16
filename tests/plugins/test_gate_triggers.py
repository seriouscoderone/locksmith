# -*- encoding: utf-8 -*-
"""Tests for Task 8: trigger wiring for role-gate re-evaluation (Task 7's
``PluginManager.reevaluate_role_gates``).

Covers the two live triggers:
- (a) vault-open: ``on_vault_opened`` records ``_current_vault`` and calls
  ``reevaluate_role_gates`` after the existing per-plugin dispatch, so
  credentials already held on relaunch surface their gated plugin with no
  re-auth.
- (b) live credential admit: the vault's ``DoerSignalBridge.doer_event`` is
  connected to ``_on_doer_event``, which filters for a successful
  ``AdmitDoer``/``admit_complete`` event (the same event the
  received-credentials list page refreshes on) and calls
  ``_on_credential_changed``, which re-evaluates gates against
  ``_current_vault`` with no restart.

Default (ungated) build check: a vault with zero gated plugins still hits
``reevaluate_role_gates`` (a cheap no-op per Task 7's transition logic) but
nothing else about ``on_vault_opened``'s existing per-plugin dispatch changes.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from locksmith.plugins import manager as m
from locksmith.plugins.base import VaultPlugin


def _bare_manager():
    mgr = object.__new__(m.PluginManager)
    mgr._plugins = {}
    mgr.reevaluate_role_gates = MagicMock()
    return mgr


# --------------------------------------------------------------------------
# Trigger (a): vault-open
# --------------------------------------------------------------------------

def test_on_vault_opened_reevaluates_gates():
    mgr = _bare_manager()
    vault = MagicMock()
    vault.signals = None  # no signal bridge on this fake vault

    m.PluginManager.on_vault_opened(mgr, vault)

    mgr.reevaluate_role_gates.assert_called_once_with(vault)


def test_on_vault_opened_records_current_vault():
    mgr = _bare_manager()
    vault = MagicMock()
    vault.signals = None

    m.PluginManager.on_vault_opened(mgr, vault)

    assert mgr._current_vault is vault


def test_on_vault_opened_still_dispatches_to_vault_plugins():
    """Existing per-plugin dispatch is unchanged by the added trigger."""
    mgr = _bare_manager()
    plugin = MagicMock(spec=VaultPlugin)
    plugin.get_doers.return_value = ["doer"]
    mgr._plugins = {"carrier": plugin}
    vault = MagicMock()
    vault.signals = None
    vault.doers = []

    m.PluginManager.on_vault_opened(mgr, vault)

    plugin.on_vault_opened.assert_called_once_with(vault)
    assert vault.doers == ["doer"]


def test_on_vault_opened_connects_doer_event_signal_when_present():
    mgr = _bare_manager()
    vault = MagicMock()

    m.PluginManager.on_vault_opened(mgr, vault)

    vault.signals.doer_event.connect.assert_called_once_with(mgr._on_doer_event)


def test_on_vault_opened_tolerates_vault_without_signals_attr():
    """A vault-shaped object with no ``signals`` attribute at all (e.g. a
    minimal test double) must not blow up on_vault_opened."""
    mgr = _bare_manager()
    vault = SimpleVaultNoSignals()

    m.PluginManager.on_vault_opened(mgr, vault)

    mgr.reevaluate_role_gates.assert_called_once_with(vault)


class SimpleVaultNoSignals:
    """Vault double with no ``signals`` attribute (getattr default path)."""


# --------------------------------------------------------------------------
# Trigger (b): live credential admit
# --------------------------------------------------------------------------

def test_credential_changed_reevaluates_current_vault():
    mgr = object.__new__(m.PluginManager)
    mgr.reevaluate_role_gates = MagicMock()
    mgr._current_vault = MagicMock()

    m.PluginManager._on_credential_changed(mgr)

    mgr.reevaluate_role_gates.assert_called_once_with(mgr._current_vault)


def test_credential_changed_noop_without_current_vault():
    mgr = object.__new__(m.PluginManager)
    mgr.reevaluate_role_gates = MagicMock()
    mgr._current_vault = None

    m.PluginManager._on_credential_changed(mgr)

    mgr.reevaluate_role_gates.assert_not_called()


def test_doer_event_admit_complete_success_triggers_credential_changed():
    mgr = object.__new__(m.PluginManager)
    mgr._on_credential_changed = MagicMock()

    m.PluginManager._on_doer_event(
        mgr, "AdmitDoer", "admit_complete", {"success": True},
    )

    mgr._on_credential_changed.assert_called_once_with()


def test_doer_event_admit_complete_failure_is_ignored():
    mgr = object.__new__(m.PluginManager)
    mgr._on_credential_changed = MagicMock()

    m.PluginManager._on_doer_event(
        mgr, "AdmitDoer", "admit_complete", {"success": False},
    )

    mgr._on_credential_changed.assert_not_called()


def test_doer_event_other_event_types_are_ignored():
    mgr = object.__new__(m.PluginManager)
    mgr._on_credential_changed = MagicMock()

    m.PluginManager._on_doer_event(mgr, "AdmitDoer", "progress", {})
    m.PluginManager._on_doer_event(mgr, "ReceiveCredentialDoer", "credential_received", {"success": True})

    mgr._on_credential_changed.assert_not_called()


def test_live_admit_end_to_end_via_signal_connect():
    """Simulate the real wiring: on_vault_opened connects the vault's
    doer_event signal, and firing the real signal-equivalent callback flows
    through to reevaluate_role_gates against the vault that was opened —
    all without any restart of the manager."""
    mgr = _bare_manager()
    vault = MagicMock()

    m.PluginManager.on_vault_opened(mgr, vault)

    # Grab the connected slot and invoke it, as Qt would on a live admit.
    connected_slot = vault.signals.doer_event.connect.call_args[0][0]
    mgr.reevaluate_role_gates.reset_mock()

    connected_slot("AdmitDoer", "admit_complete", {"success": True})

    mgr.reevaluate_role_gates.assert_called_once_with(vault)
