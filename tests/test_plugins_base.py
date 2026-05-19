"""Contract restructure tests for PluginCore / AppPlugin / VaultPlugin."""
from __future__ import annotations

import pytest

from locksmith.plugins import base as plugins_base
from locksmith.plugins.base import (
    AppPlugin,
    PluginCore,
    VaultPlugin,
)


def test_plugin_core_requires_plugin_id_and_initialize():
    # Cannot instantiate a PluginCore subclass that doesn't implement both abstractmethods.
    class Incomplete(PluginCore):
        pass

    with pytest.raises(TypeError):
        Incomplete()


def test_app_plugin_minimal_subclass_instantiates():
    class MinApp(AppPlugin):
        @property
        def plugin_id(self):
            return "min_app"

        def initialize(self, app):
            pass

    p = MinApp()
    assert p.plugin_id == "min_app"
    assert p.get_app_shortcuts() == []
    assert p.get_app_services() == []
    # Default lifecycle hooks are no-ops.
    p.on_app_started(app=None, window=None)
    p.on_app_stopping(app=None)


def test_vault_plugin_subclass_must_implement_vault_hooks():
    class IncompleteVault(VaultPlugin):
        @property
        def plugin_id(self):
            return "incomplete_vault"

        def initialize(self, app):
            pass
        # Intentionally missing the vault hooks.

    with pytest.raises(TypeError):
        IncompleteVault()


def test_app_and_vault_can_be_combined():
    class Hybrid(AppPlugin, VaultPlugin):
        @property
        def plugin_id(self):
            return "hybrid"

        def initialize(self, app): pass
        def on_vault_opened(self, vault): pass
        def on_vault_closed(self, vault, *, clear=False): pass
        def get_menu_entry(self): return None
        def get_menu_section(self): return []
        def get_pages(self): return {}

    h = Hybrid()
    # isinstance checks drive the PluginManager dispatch later.
    assert isinstance(h, AppPlugin)
    assert isinstance(h, VaultPlugin)


def test_plugin_base_alias_removed():
    # Task 3 removed the PluginBase alias. VaultPlugin is the canonical name.
    assert not hasattr(plugins_base, "PluginBase"), "PluginBase alias should be gone"
    assert hasattr(plugins_base, "VaultPlugin")
