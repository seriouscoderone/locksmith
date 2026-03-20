# -*- encoding: utf-8 -*-
"""
locksmith.plugins.manager module

Plugin discovery, initialization, and lifecycle management.
"""
from __future__ import annotations

import importlib.metadata
from typing import Any, TYPE_CHECKING

from keri import help

from locksmith.plugins.base import (
    PluginBase,
    AccountProviderPlugin,
)

if TYPE_CHECKING:
    from locksmith.ui.vault.menu import VaultNavMenu
    from locksmith.ui.vault.page import VaultPage

logger = help.ogler.getLogger(__name__)

ENTRY_POINT_GROUP = "locksmith.plugins"


class PluginManager:
    """Discovers, initializes, and manages Locksmith plugins."""

    def __init__(self, app: Any):
        self._app = app
        self._plugins: dict[str, PluginBase] = {}

    def discover_and_initialize(self, vault_page: VaultPage, nav_menu: VaultNavMenu) -> None:
        """Discover plugins via entry points, initialize them, and register pages/menus."""
        eps = importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)
        for ep in eps:
            try:
                plugin_cls = ep.load()
                plugin = plugin_cls()
                plugin.initialize(self._app)

                pid = plugin.plugin_id
                self._plugins[pid] = plugin

                # Register pages
                for key, widget in plugin.get_pages().items():
                    vault_page.register_page(key, widget)

                # Register menu section
                nav_menu.register_plugin_section(
                    pid,
                    plugin.get_menu_entry(),
                    plugin.get_menu_section(),
                )

                logger.info(f"Plugin '{pid}' loaded from entry point '{ep.name}'")
            except Exception:
                logger.exception(f"Failed to load plugin from entry point '{ep.name}'")

    def on_vault_opened(self, vault: Any) -> None:
        """Notify all plugins that a vault has been opened."""
        for plugin in self._plugins.values():
            try:
                plugin.on_vault_opened(vault)
                vault.doers.extend(plugin.get_doers())
            except Exception:
                logger.exception(f"Plugin '{plugin.plugin_id}' failed on_vault_opened")

    def on_vault_closed(self, vault: Any) -> None:
        """Notify all plugins that a vault is being closed."""
        for plugin in self._plugins.values():
            try:
                plugin.on_vault_closed(vault)
            except Exception:
                logger.exception(f"Plugin '{plugin.plugin_id}' failed on_vault_closed")

    def get_plugin(self, plugin_id: str) -> PluginBase | None:
        """Return a plugin by its ID, or None if not found."""
        return self._plugins.get(plugin_id)

    def is_setup_complete(self, plugin_id: str, vault: Any) -> bool:
        """Check if a plugin's setup is complete. Non-account plugins always return True."""
        plugin = self._plugins.get(plugin_id)
        if plugin and isinstance(plugin, AccountProviderPlugin):
            return plugin.is_setup_complete(vault)
        return True

    async def after_identifier_authenticated(self, vault: Any, hab: Any) -> None:
        """Call after_identifier_authenticated on all plugins."""
        for plugin in self._plugins.values():
            try:
                await plugin.after_identifier_authenticated(vault, hab)
            except Exception:
                logger.exception(
                    f"Plugin '{plugin.plugin_id}' failed after_identifier_authenticated"
                )

    def get_witness_batches(self, vault: Any, hab_pre: str) -> Any | None:
        """Query all plugins for witness batch data. First non-None result wins."""
        for plugin in self._plugins.values():
            result = plugin.get_witness_batches(vault, hab_pre)
            if result is not None:
                return result
        return None

    def update_witness_state_after_rotation(self, vault: Any, wit_eid: str) -> None:
        """Notify all plugins to update witness state after rotation."""
        for plugin in self._plugins.values():
            plugin.update_witness_state(vault, wit_eid)

    def update_witness_state_after_auth(self, vault: Any, wit_eid: str) -> None:
        """Notify all plugins to update witness state after authentication."""
        for plugin in self._plugins.values():
            plugin.update_witness_state_after_auth(vault, wit_eid)