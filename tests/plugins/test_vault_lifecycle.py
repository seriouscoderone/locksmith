from unittest.mock import MagicMock

from locksmith.plugins.manager import PluginManager


def _mgr():
    mgr = PluginManager.__new__(PluginManager)
    mgr._plugins = {}
    mgr._current_vault = None
    return mgr


def test_on_vault_closed_clears_current_vault_and_disconnects_slot():
    mgr = _mgr()
    vault = MagicMock()
    mgr._current_vault = vault                       # emulate on_vault_opened having run
    vault.signals.doer_event.connect(mgr._on_doer_event)

    mgr.on_vault_closed(vault)

    assert mgr._current_vault is None
    vault.signals.doer_event.disconnect.assert_called_once_with(mgr._on_doer_event)


def test_on_vault_closed_idempotent_when_never_opened():
    mgr = _mgr()
    vault = MagicMock()
    vault.signals.doer_event.disconnect.side_effect = TypeError   # not connected
    mgr.on_vault_closed(vault)                        # must not raise
    assert mgr._current_vault is None


def test_on_vault_closed_leaves_other_vault_current():
    # closing a DIFFERENT vault than the current one must not clear _current_vault
    mgr = _mgr()
    other = MagicMock()
    mgr._current_vault = other
    closing = MagicMock()
    mgr.on_vault_closed(closing)
    assert mgr._current_vault is other
