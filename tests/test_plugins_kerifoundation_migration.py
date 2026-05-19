# -*- encoding: utf-8 -*-
"""Thin wiring tests confirming kerifoundation migrated to VaultPlugin cleanly.

The broader regression gate is the full kerifoundation test suite
(`test_kerifoundation_*.py`), which must remain green post-migration.
"""
from __future__ import annotations

from locksmith.plugins.base import VaultPlugin
from locksmith.plugins.kerifoundation.plugin import KeriFoundationPlugin


def test_kerifoundation_is_vault_plugin():
    plugin = KeriFoundationPlugin()
    assert isinstance(plugin, VaultPlugin)


def test_kerifoundation_implements_all_vault_abstractmethods():
    plugin = KeriFoundationPlugin()
    # If any abstractmethod was missed, instantiation would have raised TypeError.
    for name in (
        "on_vault_opened",
        "on_vault_closed",
        "get_menu_entry",
        "get_menu_section",
        "get_pages",
    ):
        assert callable(getattr(plugin, name)), f"missing {name}"


def test_kerifoundation_plugin_id_unchanged():
    assert KeriFoundationPlugin().plugin_id == "kerifoundation"
