# -*- encoding: utf-8 -*-
"""
locksmith.ui.vault.hoa_page module

VaultPage variant for an HOA (Higher-Order Application) shell: peel-light.

Keeps VaultPage's string-keyed page registry, plugin surface, and navigation
wiring intact, but does NOT register the built-in wallet pages (identifiers,
credentials, groups, remotes, settings, notifications), and does NOT show
their nav-menu buttons (identifiers/remotes/groups/credentials/settings and
the credentials submenu: issued/received/schema) — with no widget registered
under those page keys, clicking one would hit VaultPage._show_page()'s
``widget is None`` no-op (logs, doesn't crash), but a clean HOA build must
not show dead nav buttons in the first place. This is a subtractive peel —
nothing in VaultPage is deleted or altered, so upstream Locksmith merges
stay clean. Selection between VaultPage and HoaVaultPage happens at the call
site (locksmith.ui.window) based on ``brand().peel_core_pages``.
"""
from locksmith.ui.vault.menu import VaultNavMenu
from locksmith.ui.vault.page import VaultPage


class HoaVaultPage(VaultPage):
    """VaultPage for an HOA shell.

    Overrides ``_register_core_pages()`` to a no-op so none of the built-in
    wallet pages are registered, while the ``_pages`` registry and
    ``register_page()`` remain fully functional for plugin-contributed pages.

    Also overrides ``_create_nav_menu()`` to build the nav menu with
    ``include_core_items=False``, suppressing the core-page nav buttons
    while leaving plugin-contributed menu sections (registered later via
    ``PluginManager.discover_and_initialize_vault_ui``) fully functional.
    """

    def _register_core_pages(self) -> None:
        """Suppress registration of the built-in wallet pages."""
        return

    def _create_nav_menu(self) -> VaultNavMenu:
        """Suppress the built-in wallet nav buttons — no core pages are
        registered for an HOA build, so their nav buttons would be dead."""
        return VaultNavMenu(self, include_core_items=False)

    def registered_page_keys(self) -> list[str]:
        """Expose the current page-registry keys (for tests/inspection)."""
        return list(self._pages.keys())
