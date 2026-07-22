# -*- encoding: utf-8 -*-
"""
locksmith.ui.hoa.notifications_page module

``HoaNotificationsPage`` — the persistent notifications surface for a peeled
HOA build (Task 10, HOA #2 live-demo finding).

The peeled ``HoaVaultPage`` (``locksmith.ui.vault.hoa_page``) registers none
of the stock wallet's core pages, including "notifications" — so the
toolbar bell is hidden AND the 5s ``NotificationToastDoer`` toast
(``locksmith.core.vaulting``) had nowhere to click through to: an inbound
IPEX grant landed nowhere the user could act on. This page is registered as
"notifications" exactly like the onboarding "home" page (see
``locksmith.ui.window._wire_onboarding``) so ``VaultPage.show_notifications``
(the toast-click / nav-menu-entry destination) resolves to something real.

Deliberately a simple durable log, not a design showcase (owner directive,
Task 10 brief) — one row per note, oldest business rendered generically so
nothing is ever silently dropped, and an **Accept** action on `/exn/ipex/
grant` rows wired straight through Task 8's ``make_admit_doer`` envelope
chokepoint (the same routing used by the stock wallet's accept-grant
dialog).
"""
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from keri import help
from keri.peer import exchanging

from locksmith.core.serviceaid_bridge import make_admit_doer
from locksmith.ui import colors
from locksmith.ui.toolkit.pages.base import BasePage
from locksmith.ui.toolkit.widgets import LocksmithButton

logger = help.ogler.getLogger(__name__)


def _title_for_route(route: str) -> str:
    """Generic, route-keyed title — the fallback (and, for non-grant
    routes, the ONLY) source of a row's title. Mirrors the toast's own
    stock copy (``vaulting.NotificationToastDoer._format_notification_message``)
    so the same event reads the same way in both places. Unrecognized
    routes still get a readable label -- never dropped."""
    if "/ipex/grant" in route:
        return "New credential offer"
    if "/ipex/admit" in route:
        return "Credential accepted"
    if "/ipex/spurn" in route:
        return "Credential rejected"
    if "/ipex/apply" in route:
        return "New credential application"
    if "/ipex/offer" in route:
        return "New credential offer"
    if "/multisig" in route:
        return "Multisig notification"
    if "/challenge/response" in route:
        return "Challenge response received"
    if "/keystate/update" in route:
        return "Key state update"
    if route:
        return "Notification"
    return "New notification"


class HoaNotificationsPage(BasePage):
    """Durable notifications log for a peeled HOA build.

    Args:
        app: The ``LocksmithApplication`` — reads ``app.vault.notifier`` on
            every ``refresh()`` and ``app.vault.hby`` / ``app.vault.extend``
            on ``_accept()``.
        egf_doc: Optional typed ``EgfDocument`` (Task 6) — when provided, a
            `/exn/ipex/grant` row's title is upgraded from the generic
            "New credential offer" to the actual credential's ``name`` when
            the grant's embedded schema resolves against the EGF's
            credential catalog. Best-effort: any failure to resolve (no
            ``egf_doc``, unreadable exn, no matching schema) falls back to
            the generic per-route copy — never raises, never drops the row.
        held_provider: Optional zero-arg callable returning the current
            iterable of held-credential views (``HeldCredential``-shaped:
            ``schema_said``, ``state``, ``chain_verified``, ``said``, ...).
            When provided alongside ``egf_doc``, a durable "access revoked"
            row is synthesized on every ``refresh()`` for each held gating
            credential whose schema matches a persona's onboarding grant
            credential and whose state is ``"revoked"`` — a raw TEL ``rev``
            produces no notifier note of its own, so this is the only way
            such a row is ever surfaced. Best-effort: any failure yields no
            synthesized rows rather than dropping the whole log.
        parent: Parent widget (the ``VaultPage``/``HoaVaultPage``).
    """

    def __init__(
        self,
        app: Any,
        egf_doc: Optional[Any] = None,
        held_provider: Optional[Any] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.app = app
        self._egf_doc = egf_doc
        self._held_provider = held_provider
        self._rows: List[Dict[str, Any]] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 32, 32, 32)
        outer.setSpacing(12)

        heading = QLabel("Notifications")
        heading.setStyleSheet(
            f"font-size: 20px; font-weight: 600; color: {colors.TEXT_PRIMARY};"
        )
        outer.addWidget(heading)

        self._empty_label = QLabel("No notifications yet.")
        self._empty_label.setObjectName("hoaNotifications.emptyLabel")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(
            f"color: {colors.TEXT_SECONDARY}; font-size: 13px; background: transparent;"
        )
        outer.addWidget(self._empty_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        self._rows_layout = QVBoxLayout(inner)
        self._rows_layout.setSpacing(8)
        self._rows_layout.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

        # Deliberately NOT auto-refreshed here: unlike ``OnboardingHomePage``
        # (whose ``held_provider`` is a cheap idempotent re-read), this
        # page's data source is the notifier's note iterator, which is
        # consumed once per read. Refresh happens on demand: the window
        # wires ``doer_event -> refresh()`` (mirroring the onboarding home
        # page) and ``show_notifications()`` calls ``on_show()`` -> refresh
        # on every navigation into the page.
        self._render()

    # -- data ---------------------------------------------------------------

    def refresh(self) -> None:
        """Re-read notes from the vault notifier and re-render rows."""
        self._rows = self._read_rows()
        self._render()

    def _read_rows(self) -> List[Dict[str, Any]]:
        notifier = getattr(getattr(self.app, "vault", None), "notifier", None)
        if notifier is None:
            return []

        try:
            items = list(notifier.noter.notes.getTopItemIter())
        except Exception:
            logger.exception("HoaNotificationsPage: failed reading notifier notes")
            return []

        hby = getattr(getattr(self.app, "vault", None), "hby", None)
        rows: List[Dict[str, Any]] = []
        for (_dt, rid), note in items:
            pad = getattr(note, "pad", None) or {}
            attrs = pad.get("a", {}) or {}
            route = attrs.get("r", "") or ""
            said = attrs.get("d", "") or ""
            rows.append({
                "rid": rid,
                "route": route,
                "said": said,
                "title": self._resolve_title(route, said),
                "read": bool(getattr(note, "read", False)),
                "inbound": self._is_inbound_grant(hby, route, said),
            })

        rows.extend(self._revoked_rows())

        # Most-recent-first, mirroring the stock NotificationsListPage's own
        # "loaded oldest-to-newest via getTopItemIter, then reverse()" convention.
        rows.reverse()
        return rows

    def _revoked_rows(self) -> List[Dict[str, Any]]:
        """Synthesize a durable 'access revoked' row per held-and-revoked
        gating credential. Derived from live held TEL state (not a notifier
        note — a raw TEL `rev` produces none), so it is re-derived on every
        refresh and needs no synthetic-note storage. Best-effort: any
        failure yields no rows rather than dropping the whole notifications
        list. ``has_accept_action`` already returns False for non-`/ipex/
        grant` routes, so a "revoked" row never offers Accept."""
        if self._egf_doc is None or self._held_provider is None:
            return []
        try:
            held = self._held_provider()
            grant_schemas: Dict[str, Any] = {}
            for persona in self._egf_doc.personas():
                grant = self._egf_doc.credential(persona.onboarding.grant_credential_id)
                grant_schemas[grant.schema_said] = grant

            out: List[Dict[str, Any]] = []
            for h in held:
                grant = grant_schemas.get(getattr(h, "schema_said", None))
                if grant is None:
                    continue
                if not getattr(h, "chain_verified", False):
                    continue
                if getattr(h, "state", None) != "revoked":
                    continue
                said = getattr(h, "said", "")
                out.append({
                    "rid": f"revoked:{said}",
                    "route": "revoked",
                    "said": said,
                    "title": f"{grant.name} access revoked",
                    "read": True,
                })
            return out
        except Exception:
            logger.exception("HoaNotificationsPage: revoked-row synthesis failed")
            return []

    def rows(self) -> List[Dict[str, Any]]:
        """The rows built by the most recent ``refresh()``."""
        return list(self._rows)

    def unread_count(self) -> int:
        return sum(1 for row in self._rows if not row["read"])

    @staticmethod
    def has_accept_action(row: Dict[str, Any]) -> bool:
        """True iff this row is an unread, INBOUND IPEX grant addressed to a
        local hab.

        Route-only would still offer Accept on an already-admitted row --
        e.g. one auto-admitted by ``InboundGrantWatchDoer`` and marked read
        -- which could schedule a second admit for a grant that already
        landed. Requiring ``not row["read"]`` closes that window: once a row
        is marked read (auto-admit, or a prior manual Accept), the action is
        gone.

        Route-only would ALSO offer Accept on the wallet's OWN outbound,
        self-issued grant: a grant this wallet sent is parsed into the local
        exchanger exactly like one it received, so it surfaces here as if it
        were an inbound offer -- but accepting your own grant is meaningless
        (HOA #3 two-app demo, 2026-07-20: the carrier's "Carrier License
        Application" row wrongly showed Accept). The ``inbound`` flag,
        resolved at row-build time from the grant exn's recipient/sender
        (``_is_inbound_grant``), closes that window. It defaults to True so
        a row built without it -- or a grant whose exn couldn't be resolved
        -- falls back to the prior route+read behavior."""
        return (
            "/ipex/grant" in row.get("route", "")
            and not row.get("read", False)
            and row.get("inbound", True)
        )

    @staticmethod
    def _is_inbound_grant(hby, route: str, said: str) -> bool:
        """Whether grant ``said`` is an INBOUND offer this wallet may Accept:
        a LOCAL hab is the grant exn's recipient (its ``a.i`` attribute, the
        same field ``_resolve_admit_hab`` and ``PeerExchangerShim`` read as
        the destination) and NO local hab is its sender (``i``). A grant this
        wallet SENT -- e.g. a carrier self-issuing and presenting its own
        ``carrier_license_application`` -- has a local sender and is not an
        offer to act on.

        Best-effort, matching ``_resolve_admit_hab``: any failure to resolve
        the exn (no ``hby``, no ``said``, unparseable/absent exn) falls back
        to ``True`` -- the prior route-only behavior -- never raising, never
        dropping the row. Non-grant routes short-circuit to ``True`` (the
        flag is only ever consulted for grant rows)."""
        if hby is None or not said or "/ipex/grant" not in (route or ""):
            return True
        try:
            exn, _pathed = exchanging.cloneMessage(hby, said)
            if exn is None:
                return True
            recipient = exn.ked.get("a", {}).get("i", "")
            sender = exn.ked.get("i", "")
        except Exception:
            logger.exception(
                "HoaNotificationsPage: grant-direction resolution failed for said=%s",
                said,
            )
            return True
        return recipient in hby.habs and sender not in hby.habs

    # -- title resolution -----------------------------------------------------

    def _resolve_title(self, route: str, said: str) -> str:
        if self._egf_doc is not None and said and "/ipex/grant" in route:
            try:
                name = self._grant_credential_name(said)
                if name:
                    return name
            except Exception:
                logger.exception(
                    "HoaNotificationsPage: credential-name resolution failed for said=%s",
                    said,
                )
        return _title_for_route(route)

    def _grant_credential_name(self, said: str) -> Optional[str]:
        """The granted credential's EGF-catalog ``name``, resolved by
        cloning the grant exn (``said`` is its own SAID) and matching its
        embedded ACDC's schema against ``egf_doc``'s credential catalog.
        Returns ``None`` when anything along that path doesn't resolve —
        callers fall back to generic copy."""
        hby = getattr(getattr(self.app, "vault", None), "hby", None)
        if hby is None:
            return None
        exn, _pathed = exchanging.cloneMessage(hby, said)
        if exn is None:
            return None
        schema_said = exn.ked.get("e", {}).get("acdc", {}).get("s")
        if not schema_said:
            return None
        entry = self._egf_doc.credential_by_schema(schema_said)
        return entry.name if entry is not None else None

    # -- actions --------------------------------------------------------------

    def _accept(self, row: Dict[str, Any]) -> None:
        """Accept action for a `/exn/ipex/grant` row: schedule the admit
        (Task 8's ``make_admit_doer`` envelope chokepoint — eligible habs
        get the serverless serviceaid bridge, everyone else the legacy
        doer) on the vault's doer runner, then mark the note read.

        Admits with the grant's OWN recipient hab when it resolves in this
        Habery (``_resolve_admit_hab``), rather than unconditionally the
        first hab -- a multi-hab wallet could otherwise schedule the admit
        under the wrong identifier."""
        hby = self.app.vault.hby
        hab = self._resolve_admit_hab(hby, row["said"])
        doer = make_admit_doer(self.app, hab, grant_said=row["said"])
        self.app.vault.extend([doer])
        self.app.vault.notifier.mar(row["rid"])
        self.refresh()

    @staticmethod
    def _resolve_admit_hab(hby, said: str):
        """The hab that should admit grant ``said``: the grant exn's own
        recipient -- its ``a.i`` attribute, the same field
        ``PeerExchangerShim.processEvent`` reads as the message's
        destination -- when that AID resolves in ``hby.habs``, else the
        first hab (the previous, unconditional behavior). Any failure
        resolving the grant (unparseable exn, missing from storage) falls
        back the same way -- this is a best-effort refinement, never a
        harder requirement than the admit itself."""
        try:
            exn, _pathed = exchanging.cloneMessage(hby, said)
            recipient = exn.ked.get("a", {}).get("i", "") if exn is not None else ""
        except Exception:
            logger.exception(
                "HoaNotificationsPage: grant-recipient resolution failed for said=%s",
                said,
            )
            recipient = ""
        hab = hby.habs.get(recipient) if recipient else None
        if hab is not None:
            return hab
        return next(iter(hby.habs.values()))

    # -- rendering --------------------------------------------------------------

    def _render(self) -> None:
        self._clear_row_widgets()
        self._empty_label.setVisible(not self._rows)
        for row in self._rows:
            self._rows_layout.insertWidget(
                self._rows_layout.count() - 1, self._build_row_widget(row)
            )

    def _clear_row_widgets(self) -> None:
        # Leave the trailing stretch (last item) in place.
        while self._rows_layout.count() > 1:
            item = self._rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _build_row_widget(self, row: Dict[str, Any]) -> QWidget:
        frame = QFrame()
        frame.setObjectName("hoaNotifications.row")
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        # Type selector (not an objectName "#" selector — house style avoids
        # dotted objectName selectors in QSS, see RoleCard/_GROUP_BOX_QSS
        # in onboarding/home_page.py), applied via setStyleSheet directly on
        # this instance so it never leaks to sibling QFrames elsewhere.
        background = colors.BACKGROUND_CONTENT if row["read"] else colors.BACKGROUND_HOVER
        frame.setStyleSheet(f"""
            QFrame {{
                border: 1px solid {colors.BORDER};
                border-radius: 8px;
                background-color: {background};
            }}
        """)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title_label = QLabel(row["title"])
        title_label.setWordWrap(True)
        title_label.setStyleSheet(
            f"font-weight: 600; color: {colors.TEXT_PRIMARY}; background: transparent;"
        )
        text_col.addWidget(title_label)
        if row["said"]:
            said_label = QLabel(row["said"])
            said_label.setWordWrap(True)
            said_label.setStyleSheet(
                f"font-size: 11px; color: {colors.TEXT_SECONDARY}; background: transparent;"
            )
            text_col.addWidget(said_label)
        layout.addLayout(text_col, 1)

        if self.has_accept_action(row):
            accept_btn = LocksmithButton("Accept")
            accept_btn.setObjectName("hoaNotifications.acceptButton")
            accept_btn.clicked.connect(lambda _checked=False, r=row: self._accept(r))
            layout.addWidget(accept_btn)

        return frame

    # -- BasePage ---------------------------------------------------------------

    def on_show(self, **params) -> None:
        """Refresh on every navigation into the page (nav-menu entry and
        toast-click alike), same convention as ``PluginsContent.on_show``."""
        self.refresh()

    def get_toolbar_config(self) -> Dict[str, Any]:
        """Same lock/vaults affordances as the onboarding home page — this
        surface only ever exists inside an already-open, onboarding-enabled
        HOA vault."""
        return {
            "show_vaults_button": True,
            "show_lock_button": True,
            "show_settings_button": True,
        }
