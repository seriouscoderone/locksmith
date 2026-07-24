# -*- encoding: utf-8 -*-
"""PluginManager.apply_toolbar_entries: namespaced ids, per-plugin isolation."""
from unittest.mock import MagicMock

from locksmith.plugins.manager import PluginManager


def _bare_manager() -> PluginManager:
    mgr = PluginManager.__new__(PluginManager)
    mgr._plugins = {}
    return mgr


def test_entries_applied_with_namespaced_ids():
    mgr = _bare_manager()
    widget = object()
    plugin = MagicMock()
    plugin.get_toolbar_entries.return_value = [("roles", widget, "right")]
    mgr._plugins = {"hoa_shell": plugin}
    toolbar, window = MagicMock(), MagicMock()

    mgr.apply_toolbar_entries(toolbar, window)

    plugin.get_toolbar_entries.assert_called_once_with(window)
    toolbar.add_action.assert_called_once_with("hoa_shell.roles", widget,
                                               section="right")


def test_default_hook_contributes_nothing():
    from locksmith.plugins.base import PluginCore
    assert PluginCore.get_toolbar_entries(MagicMock(), MagicMock()) == []


def test_failing_plugin_does_not_block_others():
    mgr = _bare_manager()
    bad, good = MagicMock(), MagicMock()
    bad.get_toolbar_entries.side_effect = RuntimeError("boom")
    widget = object()
    good.get_toolbar_entries.return_value = [("ok", widget, "left")]
    mgr._plugins = {"bad": bad, "good": good}
    toolbar = MagicMock()

    mgr.apply_toolbar_entries(toolbar, MagicMock())

    toolbar.add_action.assert_called_once_with("good.ok", widget, section="left")
