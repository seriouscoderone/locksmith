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
from typing import Any

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
        """Suppress the built-in wallet pages — except Settings.

        Settings is the ONE core page a peeled HOA still needs, and the §8.4
        manual demo pass is what proved it: peer transport is configured there
        and nowhere else, so a peeled build could not enable its own listener,
        could not be dialled, and could not reach its own admin. An HOA that
        cannot turn on its transport cannot participate in its ecosystem at all.

        The page itself is narrow — peer settings, update preferences, and
        delete-vault — so this does NOT re-admit the wallet surface the peel
        exists to hide: identifiers, remotes, groups, credentials, schema,
        notifications and plugins all stay peeled.

        This is a stopgap the demo forced, not the settled design. Peer config
        arguably belongs on the HOA's own connection page (today deliberately
        read-only) or should be provisioned by the brand; and the default port
        is 5621 for EVERY vault, so multi-instance HOAs still collide until
        something allocates per-instance ports.
        """
        from locksmith.ui.vault.settings.page import SettingsPage

        self.register_page("settings", SettingsPage(self))

    def _create_nav_menu(self) -> VaultNavMenu:
        """Suppress the built-in wallet nav buttons, except Settings — whose
        page ``_register_core_pages`` above registers, so its button is live
        rather than dead."""
        return VaultNavMenu(self, include_core_items=False,
                            include_settings_item=True)

    def registered_page_keys(self) -> list[str]:
        """Expose the current page-registry keys (for tests/inspection)."""
        return list(self._pages.keys())

    def preferred_default_page_keys(self) -> tuple[str, ...]:
        """"home" first, then "settings".

        "home" is the onboarding persona picker, registered by ``hoa_shell``
        (plugin.py) rather than by this class, so it is present only for an
        onboarding-enabled brand and cannot be assumed. "settings" is the one
        core page ``_register_core_pages`` above always registers, which makes it
        the honest last resort. Neither is "identifiers" — the stock default,
        which a peeled build never registers."""
        return ("home", "settings")

    def get_toolbar_config(self) -> dict[str, Any]:
        """Same as ``VaultPage.get_toolbar_config()``, except the Plugins
        and Notifications toolbar icons are hidden. No "plugins" page is
        ever registered for a peeled HOA build (see ``_register_core_pages``
        above), so clicking that icon would otherwise be a dead click (log:
        "No page registered for key 'plugins'"). The stock "notifications"
        page is likewise never registered here — but for an onboarding-
        enabled brand, the window wiring separately registers an HOA-native
        "notifications" page (``locksmith.ui.hoa.notifications_page.
        HoaNotificationsPage``) under that same key, reached via the nav
        menu / toast click rather than this toolbar bell, which stays
        hidden regardless. Brand-gated by construction (only
        ``HoaVaultPage`` is instantiated when ``brand().peel_core_pages`` —
        see ``locksmith.ui.window``); the stock ``VaultPage`` config is
        untouched."""
        config = super().get_toolbar_config()
        config["show_plugins_button"] = False
        config["show_notifications_button"] = False
        return config
