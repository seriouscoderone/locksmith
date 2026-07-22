# -*- encoding: utf-8 -*-
"""
locksmith.plugins.hoa_shell.plugin module

The generic HOA onboarding shell as a bundled plugin (HOA #4).

Moved verbatim (behavior-preserving) from ``LocksmithWindow._wire_onboarding``
/ ``_maybe_wire_onboarding_for_vault`` / ``_bring_up_direct_transport`` /
``_onboarding_held_credentials`` (``locksmith.ui.window``, pre-#4). Domain-
neutral: every specific (personas, issuer, schemas) comes from the brand's
EGF bundle -- this module hardcodes none of it.

``HoaShellPlugin`` is ungated (``required_credential = None``) and
contributes no STATIC surface (``get_pages()`` / ``get_menu_entry()`` are
both empty/None) -- its "home" and "notifications" pages/menu entries are
registered CONDITIONALLY, directly against the ``VaultPage`` host, via the
``on_vault_ui_ready`` seam (HOA #4) once ``PluginManager.
discover_and_initialize_vault_ui`` has captured the surface host. Per-vault
wiring (seeding, doer registration, doer_event connections) happens in
``on_vault_opened``, the standard ``VaultPlugin`` lifecycle hook.
"""
from __future__ import annotations

from typing import Any

from keri import help
from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon

from locksmith.core.branding import brand
from locksmith.core.direct_transport import ensure_direct_transport, make_hoa_oobi_source
from locksmith.core.egf_seeding import EgfSeeder, make_hoa_resolver
from locksmith.core.inbound_watch import GateRecheckDoer, InboundGrantWatchDoer
from locksmith.plugins.base import VaultPlugin
from locksmith.ui.hoa.notifications_page import HoaNotificationsPage
from locksmith.ui.onboarding.home_page import OnboardingErrorPage, OnboardingHomePage
from locksmith.ui.onboarding.request_flow import RequestFlow
from locksmith.ui.vault.hoa_page import HoaVaultPage
from locksmith.ui.vault.menu import MenuButton

logger = help.ogler.getLogger(__name__)


def _held_credentials(app) -> list:
    """The onboarding home/notifications pages' ``held_provider``, extracted
    to module level so the None-guard is directly unit-testable.

    ``OnboardingHomePage.__init__`` calls ``refresh()`` -> this provider
    unconditionally, and that happens at ``on_vault_ui_ready`` time -- before
    any vault has ever been opened (``app.vault is None``) -- so guard
    against ``PluginManager._held_credentials(None)`` crashing on
    ``None.rgy`` by returning "nothing held yet" instead."""
    if app.vault is None:
        return []
    return app.plugin_manager._held_credentials(app.vault)


def _sent_applies(app) -> list:
    """The roles-overview home page's ``applies_provider`` (Task 10, HOA
    #4): the holder's own outstanding ``/ipex/apply`` exns, feeding
    ``derive_role_states``'s PENDING derivation for apply-mode roles.
    Same None-guard rationale as ``_held_credentials`` above --
    ``OnboardingHomePage.__init__`` calls ``refresh()`` (and therefore this
    provider) before any vault is open."""
    if app.vault is None:
        return []
    from keri_serviceaid.providers import list_sent_applies
    hab = app.vault.hby.habByName(brand().default_aid_alias or "default")
    if hab is None:
        return []
    return list_sent_applies(app.vault.hby, hab.pre)


class HoaShellPlugin(VaultPlugin):
    """The generic (domain-neutral) HOA onboarding shell, bundled-only
    (HOA #4 -- see ``PluginManager.BUNDLED_ONLY_PLUGIN_IDS``)."""

    plugin_id = "hoa_shell"
    required_credential = None

    def initialize(self, app: Any) -> None:
        self._app = app
        self._request_flow: RequestFlow | None = None
        self._home_page: OnboardingHomePage | None = None
        self._notifications_page: HoaNotificationsPage | None = None
        self._wired_vault = None
        self._vault_page = None
        self._egf_doc = None
        self._seeder: EgfSeeder | None = None

    # -- construction-time wiring (was window._wire_onboarding) -----------
    def on_vault_ui_ready(self, vault_page) -> None:
        """Onboarding "home" persona-picker wiring (Plan B Task 8).
        RequestFlow drives the EGF request-access pipeline end to end
        (derive -> validate -> attributes -> authority -> seed -> issue ->
        grant). Gated on BOTH brand().onboarding_enabled AND a resolvable
        EGF (make_hoa_resolver returns None for any brand with no [egf]
        table) -- a non-onboarding or non-HOA brand must never construct a
        RequestFlow/OnboardingHomePage at all.

        Hardening wave item 1 (design spec §4.5): "A persona picker over a
        broken EGF shows an error state, not an empty list." A brand that
        DOES pin an EGF but whose bundle is missing/tampered/incomplete
        must not crash vault-UI construction -- make_hoa_resolver and the
        onboarding-page construction that follows are wrapped in
        try/except (EgfError, ValueError); on failure this logs loudly and
        registers a minimal OnboardingErrorPage as "home" instead, leaving
        self._request_flow / self._home_page at None (so on_vault_opened
        stays a no-op for this vault, and the nav menu entry that would
        route into a controller that was never built is never added).
        """
        from keri_serviceaid.egf.errors import EgfError

        if not (brand().onboarding_enabled and isinstance(vault_page, HoaVaultPage)):
            return

        try:
            hoa_egf = make_hoa_resolver(brand())
            if hoa_egf is None:
                return
            resolver, egf_doc = hoa_egf
            self._egf_doc = egf_doc
            # Apply-mode requests (_request_role, below) need their own
            # seeder -- built exactly as RequestFlow.__init__ builds its
            # own (see request_flow.py), rather than reaching into
            # self._request_flow._seeder, so this plugin's apply-mode path
            # doesn't depend on RequestFlow's internals.
            self._seeder = EgfSeeder(self._app, resolver, egf_doc)
            self._request_flow = RequestFlow(
                self._app, resolver, egf_doc, brand().egf_accept_phases,
            )
            self._home_page = OnboardingHomePage(
                egf_doc,
                # None-guarded: refresh() fires during construction,
                # before any vault is open. See _held_credentials.
                held_provider=lambda: _held_credentials(self._app),
                on_submit=self._request_flow.submit,
                applies_provider=lambda: _sent_applies(self._app),
                on_apply=self._request_role,
                open_role=lambda rid: vault_page._show_vault_page(rid),
                page_available=lambda rid: rid in vault_page.registered_page_keys(),
                micro_app_resolver=resolver.resolve_micro_app,
                accept_phases=brand().egf_accept_phases,
                parent=vault_page,
            )
        except (EgfError, ValueError) as exc:
            logger.error("onboarding.egf_broken error=%s", exc)
            self._request_flow = None
            self._home_page = None
            self._notifications_page = None
            error_page = OnboardingErrorPage(str(exc), parent=vault_page)
            vault_page.register_page("home", error_page)
            return

        self._vault_page = vault_page
        vault_page.register_page("home", self._home_page)
        home_entry_btn = MenuButton(icon=QIcon(), label="Home")
        home_entry_btn.setObjectName("vaultNavMenu.homeButton")
        vault_page.add_menu_entry("home", home_entry_btn, [])
        # add_menu_entry's own click wiring (VaultNavMenu.
        # register_plugin_section -> _on_plugin_button_clicked ->
        # plugin_section_clicked -> VaultPage._on_plugin_entry_clicked)
        # looks plugin_id up in plugin_manager -- "home" is not a
        # VaultPlugin, so that path is a harmless no-op (logged
        # warning). The actual navigation is this direct connection,
        # mirroring how the core nav buttons wire straight to
        # _show_vault_page in VaultPage._connect_navigation.
        home_entry_btn.clicked.connect(lambda: vault_page._show_vault_page("home"))

        # Notifications (Task 10, HOA #2 live-demo finding): HoaVaultPage
        # registers none of the stock wallet's core pages (see hoa_page.py),
        # including "notifications" -- so the toolbar bell is hidden AND the
        # 5s NotificationToastDoer toast's click-through
        # (_on_toast_clicked -> vault_page.show_notifications() ->
        # _show_page("notifications")) had nowhere to land. Registered
        # exactly like "home" immediately above: a direct MenuButton click
        # connection, not a VaultPlugin.
        self._notifications_page = HoaNotificationsPage(
            self._app, egf_doc,
            held_provider=lambda: _held_credentials(self._app),
            parent=vault_page,
        )
        vault_page.register_page("notifications", self._notifications_page)
        notifications_entry_btn = MenuButton(icon=QIcon(), label="Notifications")
        notifications_entry_btn.setObjectName("vaultNavMenu.notificationsButton")
        vault_page.add_menu_entry("notifications", notifications_entry_btn, [])
        notifications_entry_btn.clicked.connect(
            lambda: vault_page._show_vault_page("notifications")
        )

    # -- per-vault wiring (was window._maybe_wire_onboarding_for_vault) ---
    def on_vault_opened(self, vault: Any) -> None:
        """Idempotent per-vault-open onboarding hook (Task 8), now the
        standard VaultPlugin.on_vault_opened lifecycle hook (HOA #4) rather
        than a call threaded through the window's page-navigation path.
        Re-wiring is guarded on vault IDENTITY (not "this handler ran")
        so a plugin manager that somehow re-invoked this for the same vault
        instance can't double-connect doer_event or re-schedule the
        deferred refresh below.

        On a genuinely new vault: seeds every onboardable persona's
        schemas/registry (EgfSeeder is idempotent on its own too), connects
        doer_event -> the onboarding home page's refresh() (any event
        cheaply recomputes state), and resets the vault page's restore key
        to "home" so this FRESH vault's first on_show lands on the persona
        picker/state page rather than "identifiers" (HoaVaultPage registers
        no core pages at all, so on_show's own "identifiers" fallback would
        otherwise be a dead no-op for an onboarding HOA build)."""
        if self._request_flow is None or self._app.vault is None:
            return
        if vault is self._wired_vault:
            return
        self._wired_vault = vault

        self._request_flow.seed_all_personas()
        oobi_source = make_hoa_oobi_source()
        if oobi_source is not None:
            self._bring_up_direct_transport(oobi_source)
        # Task 11: auto-admit the explicitly-requested role's expected
        # grant (owner-approved policy -- the user already consented by
        # applying, so the EXACT grant they're waiting on lands without a
        # prompt). Anything else stays unread for HoaNotificationsPage's
        # Accept button (Task 10). One watcher per vault-open, same
        # per-vault-instance lifetime as the rest of this block.
        vault.extend([
            InboundGrantWatchDoer(
                self._app, self._request_flow.egf_doc, brand().egf_accept_phases,
                held_provider=lambda: _held_credentials(self._app),
                applies_provider=lambda: _sent_applies(self._app),
            ),
            GateRecheckDoer(self._app),
        ])
        vault.signals.doer_event.connect(self._home_page.refresh)
        # Acceptance-demo item 2: surface RequestFlow's own request_failed
        # emissions as a visible inline banner on the form view (distinct
        # from refresh() above, which reacts to every event generically).
        vault.signals.doer_event.connect(self._home_page.on_doer_event)
        # Task 10: the notifications page's data source (the notifier's
        # note iterator) isn't itself event-driven, so any doer event
        # (a new inbound note among them) re-reads it, same convention as
        # the onboarding home page's refresh() above.
        if self._notifications_page is not None:
            vault.signals.doer_event.connect(self._notifications_page.refresh)

        # Live-observation fix: the page's __init__ already calls refresh()
        # once, but that happens at CONSTRUCTION time -- for a HOA whose
        # onboarding page is built once and rewired across vault opens, that
        # first refresh() can run before this vault is warm (held_provider()
        # still returning [] for an already-pending application), and only
        # the doer_event connections above trigger any LATER refresh. A
        # reopened vault with a pending application would then sit on the
        # PICKER until some unrelated event happened to fire. Deferring one
        # more refresh() to the next event-loop turn re-derives state once
        # the vault is actually open, landing on PENDING/LICENSED directly
        # when warranted. refresh() is cheap and idempotent, so this is safe
        # even though the vault-identity guard above already keeps this
        # method itself from running twice for the same vault.
        QTimer.singleShot(0, self._home_page.refresh)

        if self._vault_page is not None:
            self._vault_page._current_page_key = "home"

    def _bring_up_direct_transport(self, oobi_source, attempt: int = 0,
                                   max_attempts: int = 40) -> None:
        """Bring up direct-mode peer transport, retrying on a bounded timer
        while the default identifier is still being incepted.

        On a fresh onboarding vault the default AID is created
        asynchronously (``create_identifier`` schedules an ``InceptDoer``
        on the vault's Doist and returns before the hab exists), so the
        first ``ensure_direct_transport`` call at wire time finds no hab and
        defers (returns False). The per-vault wiring guard means this method
        is the ONLY caller, so without a retry transport would never come up
        for the first-run flow and the counterparty could not present.
        Re-attempt every 250 ms (≈10 s budget) until it reports done,
        cancelling if the open vault changes underneath us (vault switch /
        close)."""
        vault = self._app.vault
        if vault is None or vault is not self._wired_vault:
            return  # vault switched/closed mid-retry — abandon this chain
        if ensure_direct_transport(
                self._app, self._request_flow.egf_doc, oobi_source,
                brand().egf_accept_phases):
            return  # brought up (or nothing to do)
        if attempt + 1 >= max_attempts:
            logger.warning(
                "direct_transport.bringup_timeout the default identifier "
                "never appeared; counterparty transport is not up")
            return
        QTimer.singleShot(
            250,
            lambda: self._bring_up_direct_transport(
                oobi_source, attempt + 1, max_attempts),
        )

    def on_vault_closed(self, vault: Any, *, clear: bool = False) -> None:
        if vault is self._wired_vault:
            self._wired_vault = None   # allow re-wire on reopen; doers die with the vault

    # -- apply-mode request wiring (Task 10, HOA #4) -----------------------
    def _request_role(self, role_id: str) -> None:
        """Apply-mode request: derive the plan, pick the single authority,
        seed the grant schema, send the IPEX apply over the peer channel.

        Wired as ``OnboardingHomePage``'s ``on_apply`` -- called when an
        apply-mode role's card Request/Request-again button is clicked
        (form-mode roles never reach here; they route into the FORM view
        instead -- see ``OnboardingHomePage._on_card_request``). Every
        failure path surfaces an ``ApplyFlow``/``apply_failed`` doer_event
        (the page's ``on_doer_event`` renders it as an inline banner) rather
        than raising -- this is a UI click handler, not a call site with a
        try/except of its own.
        """
        from keri_serviceaid.egf.onboarding import derive_apply_request
        from locksmith.core.serviceaid_bridge import make_apply_doer

        if self._app.vault is None or self._egf_doc is None:
            return
        egf = self._egf_doc
        plan = derive_apply_request(egf, role_id)
        authorities = egf.authorities(plan.grant_credential.issuer_role,
                                      accept_phases=brand().egf_accept_phases)
        if len(authorities) != 1:
            self._app.vault.signals.emit_doer_event(
                "ApplyFlow", "apply_failed",
                {"success": False,
                 "error": f"expected exactly one authority for "
                          f"'{plan.grant_credential.issuer_role}', "
                          f"found {len(authorities)}",
                 "schema_said": plan.grant_credential.schema_said})
            return
        self._seeder.seed_for_role(role_id)
        hab = self._app.vault.hby.habByName(
            brand().default_aid_alias or "default")
        doer = make_apply_doer(self._app, hab,
                               schema_said=plan.grant_credential.schema_said,
                               recipient=authorities[0].aid)
        if doer is not None:
            self._app.vault.extend([doer])

    # -- static surface contract ------------------------------------------
    def get_pages(self) -> dict:
        return {}     # pages register conditionally in on_vault_ui_ready

    def get_menu_entry(self):
        return None   # menu entries are registered directly (two of them)

    def get_menu_section(self) -> list:
        return []

    # -- top-toolbar contribution (Task 10, HOA #4) ------------------------
    def get_toolbar_entries(self, window) -> list:
        """An always-accessible "Roles" button on the top toolbar -- unlike
        the "home"/"notifications" nav-menu entries above (which only exist
        once a vault is open and this plugin's ``on_vault_ui_ready`` has
        registered them), the toolbar button is visible regardless of
        vault-open state so a holder can always reach the roles overview.
        Gated on ``brand().onboarding_enabled`` only, matching this
        plugin's own onboarding-enabled gate elsewhere."""
        if not brand().onboarding_enabled:
            return []
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QPushButton
        from locksmith.ui import colors
        btn = QPushButton("Roles")
        btn.setObjectName("toolbar.rolesButton")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"color: {colors.WHITE}; background: transparent; "
                          f"border: none; padding: 4px 8px;")
        btn.clicked.connect(lambda: self._open_roles(window))
        return [("roles", btn, "right")]

    def _open_roles(self, window) -> None:
        """Always-accessible entry to the roles overview: navigate to the
        vault page and show "home" -- mirrors window._on_toast_clicked's
        navigate-then-show idiom (window.py's toast-click handler)."""
        if self._app.vault is None or self._vault_page is None:
            return
        from locksmith.ui.navigation import Pages
        current_page = window.main_stack.currentWidget()
        if current_page is not self._vault_page:
            window.nav_manager.navigate_to(Pages.VAULT)
        self._vault_page._show_vault_page("home")
