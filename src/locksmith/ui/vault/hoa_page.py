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

from keri import help

from locksmith.ui.vault.menu import VaultNavMenu
from locksmith.ui.vault.page import VaultPage

logger = help.ogler.getLogger(__name__)


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

    def pinned_landing_key(self) -> str | None:
        """The page this vault was told to open on, or None.

        Per-vault, read fresh every call: one ``VaultPage`` instance is
        constructed at ``ui/window.py`` and shared across every vault opened in
        the process, so a cached value would carry one vault's choice into the
        next. Reads are cheap and this runs once per show.
        """
        vault = getattr(self.app, "vault", None)
        landing = getattr(getattr(vault, "db", None), "landing", None)
        if landing is None:
            return None
        try:
            prefs = landing.get(keys=("landing",))
        except Exception:               # noqa: BLE001 -- a preference, not state
            logger.debug("hoa.landing.unreadable", exc_info=True)
            return None
        return (prefs.pinned_page_key or None) if prefs is not None else None

    def set_pinned_landing_key(self, key: str | None) -> None:
        """Pin (or clear) the page this vault opens on. Returns silently with no
        vault, which is the state the Roles surface is built in."""
        vault = getattr(self.app, "vault", None)
        landing = getattr(getattr(vault, "db", None), "landing", None)
        if landing is None:
            return
        from locksmith.db.basing import LandingPrefs
        current = landing.get(keys=("landing",)) or LandingPrefs()
        current.pinned_page_key = key or ""
        landing.pin(keys=("landing",), val=current)
        logger.info("hoa.landing.pinned key=%s", key or "(cleared)")

    def preferred_default_page_keys(self) -> tuple[str, ...]:
        """Where this vault opens, best first — resolved fresh on every show.

        1. the pinned page, if the user chose one;
        2. else the ONE active role surface, when exactly one is revealed. Derived
           every time and never written: a user holding a single role has made no
           choice, and auto-pinning on their behalf is a lock-in they would then
           have to discover in order to undo;
        3. else "home", the Roles overview — which is deliberately where someone
           with several roles and no pin lands, because that is where the control
           to pick one lives;
        4. else "settings", the one page ``_register_core_pages`` always
           registers, so there is always a real destination.

        Nothing here can widen access. ``default_page_key`` filters this to keys
        that are REGISTERED, and a role's page is registered only once its
        credential gate is satisfied — so a pin naming a revoked role degrades to
        the next entry on its own, and the pin is kept rather than cleared
        because revoke -> re-grant is a real arc.

        Neither entry is "identifiers", the stock wallet default, which a peeled
        build never registers.
        """
        keys: list[str] = []
        pinned = self.pinned_landing_key()
        if pinned:
            keys.append(pinned)

        manager = getattr(self.app, "plugin_manager", None)
        if manager is not None and hasattr(manager, "active_role_page_keys"):
            try:
                active = manager.active_role_page_keys()
            except Exception:           # noqa: BLE001 -- landing hint only
                logger.debug("hoa.landing.active_roles_unreadable", exc_info=True)
                active = []
            if len(active) == 1 and active[0] not in keys:
                keys.append(active[0])

        keys += [k for k in ("home", "settings") if k not in keys]
        return tuple(keys)

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
