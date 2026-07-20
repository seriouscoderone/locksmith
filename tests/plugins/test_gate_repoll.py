# -*- encoding: utf-8 -*-
"""Tests for PluginManager._repoll_after_admit — bounded escrow re-poll after IPEX admit."""
from unittest.mock import MagicMock, patch

from locksmith.plugins.manager import PluginManager


def _mgr_with_gated_plugin(schema_said="E" + "L" * 43):
    mgr = PluginManager.__new__(PluginManager)   # bypass full init
    plugin = MagicMock()
    plugin.plugin_id = "carrier"
    plugin.required_credential.schema_said = schema_said
    mgr._plugins = {"carrier": plugin}
    mgr._active_roles = set()
    mgr._current_vault = MagicMock()
    mgr._repoll_timer = None
    mgr._gated_plugins = lambda: [plugin]
    return mgr


def test_repoll_stops_when_gate_activates():
    mgr = _mgr_with_gated_plugin()
    creder = MagicMock(); creder.schema = "E" + "L" * 43
    mgr._current_vault.rgy.reger.creds.get.return_value = creder
    calls = []
    def fake_reeval(vault):
        calls.append(1)
        if len(calls) >= 3:                    # satisfied on 3rd pass
            mgr._active_roles.add("carrier")
    mgr.reevaluate_role_gates = fake_reeval
    with patch("locksmith.plugins.manager.QTimer") as qt:
        # drive synchronously: singleShot(ms, cb) -> cb() immediately
        qt.singleShot.side_effect = lambda ms, cb: cb()
        mgr._repoll_after_admit("Ecred")
    assert len(calls) == 3                     # stopped early, not 10


def test_repoll_noop_when_no_schema_match():
    mgr = _mgr_with_gated_plugin(schema_said="E" + "Z" * 43)
    creder = MagicMock(); creder.schema = "E" + "L" * 43
    mgr._current_vault.rgy.reger.creds.get.return_value = creder
    mgr.reevaluate_role_gates = MagicMock()
    mgr._repoll_after_admit("Ecred")
    mgr.reevaluate_role_gates.assert_not_called()


def test_repoll_exhausts_boundedly():
    mgr = _mgr_with_gated_plugin()
    creder = MagicMock(); creder.schema = "E" + "L" * 43
    mgr._current_vault.rgy.reger.creds.get.return_value = creder
    calls = []
    mgr.reevaluate_role_gates = lambda v: calls.append(1)   # never satisfies
    with patch("locksmith.plugins.manager.QTimer") as qt:
        qt.singleShot.side_effect = lambda ms, cb: cb()
        mgr._repoll_after_admit("Ecred")
    assert len(calls) == 10


def test_repoll_aborts_when_vault_switches_mid_window():
    mgr = _mgr_with_gated_plugin()
    creder = MagicMock(); creder.schema = "E" + "L" * 43
    vault_a = mgr._current_vault
    vault_a.rgy.reger.creds.get.return_value = creder
    ticks = []
    def fake_reeval(v):
        ticks.append(v)
        mgr._current_vault = MagicMock()   # simulate a vault switch on the first tick
    mgr.reevaluate_role_gates = fake_reeval
    with patch("locksmith.plugins.manager.QTimer") as qt:
        qt.singleShot.side_effect = lambda ms, cb: cb()   # drive synchronously
        mgr._repoll_after_admit("ECRED", attempts=5, interval_ms=1)
    assert ticks == [vault_a], "re-poll must run against the pinned vault, then abort when it changes"
