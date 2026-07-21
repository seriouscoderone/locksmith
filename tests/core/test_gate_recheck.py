from types import SimpleNamespace
from unittest.mock import MagicMock

from locksmith.core.inbound_watch import GateRecheckDoer


def test_recheck_once_calls_manager():
    pm = MagicMock()
    doer = GateRecheckDoer(SimpleNamespace(plugin_manager=pm))
    doer.recheck_once()
    pm.recheck_gates.assert_called_once()


def test_recheck_once_noop_without_manager():
    doer = GateRecheckDoer(SimpleNamespace())   # no plugin_manager attr
    doer.recheck_once()   # must not raise


def test_recheck_once_swallows_manager_error():
    pm = MagicMock()
    pm.recheck_gates.side_effect = RuntimeError("boom")
    doer = GateRecheckDoer(SimpleNamespace(plugin_manager=pm))
    doer.recheck_once()   # must not raise


def test_recheck_gates_reevaluates_current_vault():
    from locksmith.plugins.manager import PluginManager
    mgr = PluginManager.__new__(PluginManager)
    mgr._current_vault = object()
    calls = []
    mgr.reevaluate_role_gates = lambda v: calls.append(v)
    mgr.recheck_gates()
    assert calls == [mgr._current_vault]
    mgr._current_vault = None
    calls.clear()
    mgr.recheck_gates()   # no vault -> no-op
    assert calls == []
