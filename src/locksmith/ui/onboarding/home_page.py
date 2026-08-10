# -*- encoding: utf-8 -*-
"""
locksmith.ui.onboarding.home_page module

``OnboardingHomePage`` — the roles-overview home surface (HOA #4, Task 10):
one ``RoleCard`` per onboardable persona, each showing that role's OWN
``RoleStatus`` (``locksmith.ui.onboarding.role_states.derive_role_states``,
Task 8) with a Request / Open / Request-again affordance. Replaces the
earlier app-global, single-selected-role state machine (``derive_state`` /
``OnboardingState`` / ``PersonaCard`` / ``select_persona`` — see git history)
whose role-agnostic first-match LICENSED/REVOKED scan could not represent
holding role A while applying for role B (the #2-flagged multi-role
boundary).

Two rendering modes, switched on ``self._role_id``:

- **Overview** (``self._role_id is None``, the default landing view): a
  scrollable row of ``RoleCard`` widgets, one per ``egf.personas()`` entry,
  each showing its current ``RoleStatus`` (AVAILABLE / PENDING / ACTIVE /
  REVOKED) and the matching affordance. Clicking a card's Request button
  calls ``_on_card_request(role_id)``, which routes on the role's onboarding
  mode:

  - **apply-mode** (``role.onboarding.apply_mode``, i.e. no
    ``request_micro_app_said`` — a bare IPEX apply, no form): calls
    ``on_apply(role_id)`` (the shell's ``_request_role`` — derives the
    apply plan, seeds schemas, sends the IPEX apply) and re-derives state.
  - **form-mode** (a micro-app "submit application" command against the
    issuing counterparty): sets ``self._role_id`` and switches to the FORM
    view below.

  A REVOKED role's Request-again click additionally marks the role in
  ``self._reapplying_roles`` (apply-mode only — see ``_on_card_request``),
  passed to ``derive_role_states`` as ``suppress_revoked_roles`` so a TEL
  ``rev`` (which never removes the credential from the holder's store)
  doesn't keep the role stuck at REVOKED after the holder re-applies;
  cleared the moment ``refresh()`` re-derives ACTIVE for that role (a fresh
  grant landed).
- **Form** (``self._role_id is not None``): unchanged FORM machinery (Task
  5/6) — ``SchemaFormBuilder`` renders the role's onboarding command's
  payload schema, plus a per-issuer context-selection control (design spec
  §7.4 "context binding") so the holder also picks WHICH authority (e.g.
  which state regulator) they're applying to.

Task 11: the old ``OnboardingState``/``derive_state`` app-global,
single-selected-role state machine (kept as a TRANSITIONAL shim only for
``locksmith.core.inbound_watch.InboundGrantWatchDoer``'s own import) has
been removed now that that watcher reads ``derive_role_states`` directly
(fed by a new ``applies_provider`` alongside ``held_provider``). Nothing
in the codebase imports ``OnboardingState``/``derive_state`` any longer.

Context binding mechanism (spec §7.4, "one control serves both"): each
``context_dimensions(issuer_role)`` entry is rendered as a combo whose
options are the deduped contexts of ``authorities(issuer_role,
accept_phases=...)`` (bootstrap-phase entries get their option text
suffixed " (pilot)"). **When a dimension's id matches a property name in
the command's payload_schema, no separate combo is created at all** — the
form's own rendered field for that property already IS the control; at
submit time its value is read out of the form and mirrored into BOTH the
payload and the context dict. This is the "overlay after build" option
from the two the brief offered (skip building a duplicate widget,
mirror the value afterward) rather than stripping the property out of
the schema handed to ``SchemaFormBuilder`` — it keeps ``page.form``
addressable by the field's real name for callers/tests (``set_field``,
``widget_for``) exactly as if it weren't dual-purposed at all.
"""
from typing import Any, Callable, Dict, Iterable, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from keri import help
from keri_serviceaid.egf.documents import EgfDocument, Role

from locksmith.ui import colors
from locksmith.ui.onboarding.form_builder import SchemaFormBuilder
from locksmith.ui.onboarding.role_states import RoleStatus, derive_role_states
from locksmith.ui.toolkit.pages.base import BasePage
from locksmith.ui.toolkit.widgets import LocksmithButton
from locksmith.ui.toolkit.widgets.buttons import LocksmithInvertedButton
from locksmith.ui.toolkit.widgets.buttons import LocksmithCopyButton

# Always pass __name__: help.ogler.getLogger() with no argument routes every
# module's lines onto one shared logger, which makes them unfilterable.
logger = help.ogler.getLogger(__name__)


_KIND_GLYPHS = {
    "organization": "\U0001F3E2",  # office building
    "government": "\U0001F3DB",  # classical building
    "individual": "\U0001F464",  # bust silhouette
}
_DEFAULT_GLYPH = "●"  # bullet, used for any unrecognized `kind`

# Acceptance-demo fix wave item 1: same rationale as form_builder.py's own
# copy — QGroupBox gets no color from the app-wide stylesheet, so its title
# renders via the OS's native (dark-under-dark-appearance) palette regardless
# of this app's own light theme. Duplicated rather than imported (house style
# favors small per-file CSS constants over a shared style module — see
# KFOnboardingPage's own `_*_badge_css()` methods).
_GROUP_BOX_QSS = f"""
    QGroupBox {{
        border: 1px solid {colors.BORDER};
        border-radius: 8px;
        margin-top: 14px;
        padding: 12px 8px 8px 8px;
        font-size: 13px;
        font-weight: 600;
        color: {colors.TEXT_PRIMARY};
        background-color: transparent;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 6px;
        padding: 0 4px;
        color: {colors.TEXT_PRIMARY};
    }}
"""


class RoleCard(QFrame):
    """One persona's status card on the roles overview (HOA #4).

    Shows the role's display_name/description/kind-glyph (same visual
    house style as the old ``PersonaCard``) plus a status badge and, per
    ``status``, a Request / Request-again button (``request_clicked``) and,
    only once ACTIVE **and** the caller confirms the role's own page is
    actually registered (``page_available``), an Open button
    (``open_clicked``). Convention (see role-plugin docstrings): a
    role-plugin's primary page key == its plugin_id == the EGF role id.
    """

    request_clicked = Signal(str)
    open_clicked = Signal(str)
    default_toggled = Signal(str, bool)

    _STATUS_COPY = {
        RoleStatus.AVAILABLE: ("Available", "Request access to add this role."),
        RoleStatus.PENDING: ("Requested",
                             "Waiting for the administrator to grant this role."),
        RoleStatus.ACTIVE: ("Active", "This role's workspace is loaded."),
        RoleStatus.REVOKED: ("Revoked", "Your access to this role was revoked."),
    }

    def __init__(self, role: Role, status: RoleStatus, *,
                page_available: bool = False, opens_at_startup: bool = False,
                parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.role_id = role.id
        self.status = status
        self.open_button: Optional[LocksmithButton] = None
        self.request_button: Optional[LocksmithButton] = None
        self.default_button: Optional[LocksmithInvertedButton] = None
        self.default_badge: Optional[QLabel] = None

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"""
            RoleCard {{
                border: 1px solid {colors.BORDER};
                border-radius: 8px;
                background-color: {colors.BACKGROUND_CONTENT};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)

        glyph = QLabel(_KIND_GLYPHS.get(role.kind, _DEFAULT_GLYPH))
        glyph.setStyleSheet("font-size: 28px; border: none; background: transparent;")
        layout.addWidget(glyph)

        name = QLabel(role.display_name)
        name.setWordWrap(True)
        name.setStyleSheet(
            f"font-size: 16px; font-weight: 600; color: {colors.TEXT_PRIMARY}; "
            "border: none; background: transparent;"
        )
        layout.addWidget(name)

        description = QLabel(role.description)
        description.setWordWrap(True)
        description.setStyleSheet(
            f"font-size: 12px; color: {colors.TEXT_SECONDARY}; border: none; background: transparent;"
        )
        layout.addWidget(description)

        status_text, status_detail = self._STATUS_COPY[status]
        badge = QLabel(status_text)
        # Two names for one badge is not possible, so this stays keyed by
        # STATUS (what a reader wants to find: "is anything pending?") and the
        # role is carried on the card itself, below.
        badge.setObjectName(f"roleCard.status.{status.value}")
        badge.setStyleSheet(
            f"background-color: {colors.BACKGROUND_HOVER}; color: {colors.TEXT_SECONDARY}; "
            "border-radius: 8px; font-size: 11px; font-weight: 600; padding: 1px 8px;"
        )
        badge_row = QHBoxLayout()
        badge_row.setContentsMargins(0, 0, 0, 0)
        badge_row.setSpacing(6)
        badge_row.addWidget(badge)
        if opens_at_startup:
            # The card says what it is, at a glance. A control alone left the SET
            # state invisible until you went looking for a ticked box -- the owner
            # read the whole affordance as missing.
            self.default_badge = QLabel("DEFAULT")
            self.default_badge.setObjectName(f"roleCard.defaultBadge.{self.role_id}")
            self.default_badge.setStyleSheet(
                f"background-color: {colors.PRIMARY}; color: {colors.WHITE};"
                " border-radius: 8px; font-size: 11px; font-weight: 600;"
                " padding: 1px 8px;")
            badge_row.addWidget(self.default_badge)
        badge_row.addStretch(1)
        layout.addLayout(badge_row)

        detail = QLabel(status_detail)
        detail.setWordWrap(True)
        detail.setStyleSheet(
            f"font-size: 12px; color: {colors.TEXT_SECONDARY}; border: none; background: transparent;"
        )
        layout.addWidget(detail)

        buttons_row = QHBoxLayout()
        if status in (RoleStatus.AVAILABLE, RoleStatus.REVOKED):
            label = "Request" if status is RoleStatus.AVAILABLE else "Request again"
            self.request_button = LocksmithButton(label)
            # Per-role, like the context combos (`onboarding.context.<dim.id>`).
            # Every card carried the SAME name, so with three roles on the page
            # nothing could ask for a PARTICULAR one — neither a test nor any
            # future scripting or accessibility surface. Name lookup returns the
            # first match, so "request the actuary role" was unexpressible.
            self.request_button.setObjectName(
                f"roleCard.requestButton.{self.role_id}")
            self.request_button.clicked.connect(
                lambda: self.request_clicked.emit(self.role_id))
            buttons_row.addWidget(self.request_button)
        if status is RoleStatus.ACTIVE and page_available:
            # Per-role objectName, for the reason the request button's comment
            # above already gives: every Open button carried the SAME name, so
            # with three roles on the page "open the actuary role" was
            # unexpressible to a test, a script or an accessibility client --
            # name lookup returns the first match.
            self.open_button = LocksmithButton("Open")
            self.open_button.setObjectName(f"roleCard.openButton.{self.role_id}")
            self.open_button.clicked.connect(
                lambda: self.open_clicked.emit(self.role_id))
            buttons_row.addWidget(self.open_button)

            # Offered only on a role that is ACTIVE and whose page is really
            # registered -- the same two conditions as Open. Pinning a surface
            # you cannot open would be a preference with nowhere to go.
            #
            # A named action, not a checkbox. The first build put an "Open at
            # startup" checkbox beside Open and the owner reported the affordance
            # as absent: a small box riding a button row does not announce what
            # it does, and the SET state was invisible until you noticed a tick.
            # A button says what will happen, and the DEFAULT badge above says
            # what is true now.
            #
            # "Default" is the owner's word, taken over the design panel's
            # objection that it drifts toward "primary permission" -- their
            # concern is real (a role is not more-granted than another) but the
            # product's voice is the owner's call, and the badge sits beside a
            # status badge that already says what is granted.
            self.default_button = LocksmithInvertedButton(
                "Clear default" if opens_at_startup else "Set as default")
            self.default_button.setObjectName(
                f"roleCard.defaultButton.{self.role_id}")
            self.default_button.setToolTip(
                "Open this role when you unlock this vault."
                if not opens_at_startup else
                "Stop opening this role first; go to Roles instead.")
            self.default_button.clicked.connect(
                lambda: self.default_toggled.emit(
                    self.role_id, not opens_at_startup))
            buttons_row.addWidget(self.default_button)
        if self.request_button is not None or self.open_button is not None:
            layout.addLayout(buttons_row)


class OnboardingErrorPage(QWidget):
    """Minimal error-state view registered as vault "home" when the
    onboarding brand's pinned EGF bundle fails to resolve/verify (missing,
    tampered, or incomplete `document_said` -- see `EgfResolver`/
    `make_hoa_resolver`). Hardening wave item 1, design spec §4.5: "A
    persona picker over a broken EGF shows an error state, not an empty
    list."

    Deliberately NOT a state machine like ``OnboardingHomePage`` -- there is
    no vault-derived state to react to; the workspace's onboarding surface
    is simply unusable until an administrator fixes the bundle.
    """

    def __init__(self, detail: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 48, 48, 48)
        layout.addStretch(1)

        heading = QLabel("This secure workspace isn't available")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet(f"font-size: 22px; font-weight: 600; color: {colors.TEXT_PRIMARY};")
        layout.addWidget(heading)

        body = QLabel(
            "This secure workspace's ecosystem bundle failed verification — "
            f"{detail}. Contact your administrator."
        )
        body.setObjectName("form-error")
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.setWordWrap(True)
        body.setStyleSheet(f"font-size: 14px; color: {colors.DANGER};")
        layout.addWidget(body)

        # One-click copy of the full error (heading + cryptic detail).
        copy_row = QHBoxLayout()
        copy_row.addStretch()
        self.copy_button = LocksmithCopyButton(
            copy_content=f"{heading.text()}\n\n{body.text()}",
            tooltip="Copy error message",
            icon_size=18,
            icon_color=colors.DANGER,
        )
        copy_row.addWidget(self.copy_button)
        copy_row.addStretch()
        layout.addLayout(copy_row)

        layout.addStretch(2)


class OnboardingHomePage(BasePage):
    """The roles-overview home screen: one ``RoleCard`` per onboardable
    persona, plus the (unchanged) role application form, driven by
    ``derive_role_states``.

    Args:
        egf_doc: The ecosystem's typed ``EgfDocument`` (source of
            personas, roles, credentials, authorities, context
            dimensions).
        held_provider: Zero-arg callable returning the current list of
            held-credential views (the gate's ``HeldCredential`` shape).
            Called fresh on every ``refresh()``.
        on_submit: ``(role_id, payload, context) -> None`` invoked once
            the chosen (form-mode) role's form validates cleanly.
        applies_provider: Zero-arg callable returning the holder's own
            currently-sent ``/ipex/apply`` exns (``keri_serviceaid.
            providers.list_sent_applies`` shape) — feeds
            ``derive_role_states``'s PENDING derivation for apply-mode
            roles. Called fresh on every ``refresh()``.
        on_apply: ``(role_id) -> None`` invoked when an apply-mode role's
            Request button is clicked (the shell's ``_request_role`` —
            derives the apply plan, seeds schemas, sends the IPEX apply).
        open_role: ``(role_id) -> None`` invoked when an ACTIVE role's
            Open button is clicked (the shell navigates to that role's own
            page).
        page_available: ``(role_id) -> bool`` — whether that role's own
            page is currently registered (gates the Open button;
            ``RoleCard`` only shows it when ACTIVE **and** this is True).
            Defaults to always-False (no page ever "available") so a
            caller that hasn't wired page discovery yet degrades safely.
        micro_app_resolver: ``(said) -> dict`` resolving a micro-app
            template (its ``commands`` list, each with an ``id`` and
            ``payload_schema``) — e.g. B8's ``resolver.resolve_micro_app``.
            Only required once a form-mode persona is actually selected;
            may be omitted while no role ever reaches the FORM view (as in
            tests that only exercise the overview).
        accept_phases: Governance phases (e.g. ``("bootstrap",
            "production")``) whose authorities are offered as
            context-selection options. Forwarded to
            ``EgfDocument.authorities``.
        parent: Parent widget (typically the main window).
    """

    def __init__(
        self,
        egf_doc: EgfDocument,
        held_provider: Callable[[], list],
        on_submit: Callable[[str, dict, dict], None],
        *,
        applies_provider: Callable[[], list] = lambda: [],
        on_apply: Optional[Callable[[str], None]] = None,
        open_role: Optional[Callable[[str], None]] = None,
        startup_provider: Optional[Callable[[], Optional[str]]] = None,
        on_set_startup: Optional[Callable[[str, bool], None]] = None,
        page_available: Callable[[str], bool] = lambda rid: False,
        micro_app_resolver: Optional[Callable[[str], dict]] = None,
        accept_phases: Iterable[str] = ("production",),
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._egf = egf_doc
        self._held_provider = held_provider
        self._applies_provider = applies_provider
        self._on_submit = on_submit
        self._on_apply = on_apply
        self._open_role_cb = open_role
        self._startup_provider = startup_provider
        self._on_set_startup = on_set_startup
        self._page_available = page_available
        self._micro_app_resolver = micro_app_resolver
        self._accept_phases = tuple(accept_phases)

        self._role_id: Optional[str] = None
        # role_id -> suppressed past the (otherwise-sticky) REVOKED branch
        # for exactly one apply-mode reapply cycle -- see _on_card_request
        # and refresh(). A TEL rev never removes the credential from the
        # holder's store, so without this the role would re-derive REVOKED
        # forever after, and the Request-again button would be a dead end.
        self._reapplying_roles: set = set()
        self.role_states: Dict[str, RoleStatus] = {}
        self.form: Optional[SchemaFormBuilder] = None
        self._context_widgets: Dict[str, QComboBox] = {}
        self._context_prompts: Dict[str, str] = {}
        # dim_id -> whether the SCHEMA marks this shared dimension's payload
        # property required (see _build_context_controls) — requiredness for
        # a shared dim is no longer SchemaFormBuilder's job once its field is
        # replaced with a context combo (see form_builder.py's
        # replace_field_with_combo), so this page tracks it instead.
        self._shared_dims: Dict[str, bool] = {}
        # The authorities considered for the currently-built form (item 5's
        # "applying to" header resolves against this same list — the SAME
        # source the context combo(s) draw their options from).
        self._context_authorities: List[Any] = []
        self._built_form_role_id: Optional[str] = None
        self._role_cards: List[RoleCard] = []
        self._error_labels: List[QLabel] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._stack = QStackedWidget(self)
        outer.addWidget(self._stack)

        self._overview_widget, self._overview_cards_layout = self._build_overview_shell()
        self._form_container, self._form_layout, self._error_layout = self._build_form_shell()

        self._stack.addWidget(self._overview_widget)
        self._stack.addWidget(self._form_container)

        self.refresh()

    # -- construction: static views ---------------------------------------

    def _build_overview_shell(self):
        """The roles-overview scroll area shell: an (initially hidden) error
        banner, a heading, and an (initially empty) horizontal row of
        ``RoleCard`` widgets, rebuilt on every ``refresh()`` by
        ``_rebuild_overview``. Returns ``(scroll_widget, cards_layout)`` so
        the caller can clear/repopulate the row.

        The banner (``self._overview_error_label``) is this view's own
        equivalent of the FORM view's ``_error_layout``/``_show_form_errors``
        — review fix (apply-mode failures are invisible): apply-mode
        requests never leave the overview (``_role_id`` stays ``None``, see
        ``_on_card_request``), so the form's error layout is never the
        widget on screen to show an ``apply_failed`` message. Same DANGER/
        ``BACKGROUND_ERROR`` inline styling as the form's ``"form-error"``
        labels so the visual language matches -- objectName is deliberately
        ``"overview-error"`` (NOT ``"form-error"``), since this label is
        permanent (built once, toggled visible/hidden — never
        detached/re-created the way ``_show_form_errors``/
        ``_clear_form_errors`` churn theirs) and several existing tests
        assert ``findChildren(QLabel, "form-error") == []`` / count exactly
        the transient ones; a shared objectName would make this permanent,
        usually-empty label a phantom match. Lives OUTSIDE ``cards_row`` so
        ``_rebuild_overview`` (which only clears ``cards_row``) never
        touches it. See ``_show_overview_error``/``_clear_overview_error``."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        # Acceptance-demo fix wave item 1: QAbstractScrollArea's viewport
        # paints from its OWN palette, not the app-wide QSS cascade — without
        # this, an unstyled scroll area shows the OS's native (dark, under a
        # dark system appearance) background regardless of this app's own
        # light theme.
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(48, 48, 48, 48)
        layout.setSpacing(16)

        error_label = QLabel("")
        error_label.setObjectName("overview-error")
        error_label.setWordWrap(True)
        error_label.setStyleSheet(
            f"color: {colors.DANGER}; background-color: {colors.BACKGROUND_ERROR}; "
            "border-radius: 6px; padding: 8px 12px;"
        )
        error_label.setVisible(False)
        layout.addWidget(error_label)
        self._overview_error_label = error_label

        heading = QLabel("Your roles")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet(f"font-size: 24px; font-weight: 600; color: {colors.TEXT_PRIMARY};")
        layout.addWidget(heading)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(16)
        layout.addLayout(cards_row)
        layout.addStretch(1)

        scroll.setWidget(inner)
        return scroll, cards_row

    def _build_form_shell(self):
        # Acceptance-demo fix wave item 1: same QScrollArea-viewport
        # background fix as `_build_overview_shell` (see its comment) — the
        # form view is long enough on a real application schema to need
        # scrolling anyway, which item 2 also relies on (scrolling a
        # freshly-rendered error/banner into view).
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        outer = QVBoxLayout(container)
        outer.setContentsMargins(48, 48, 48, 48)
        outer.setSpacing(16)

        # "Applying to" header (item 5): the currently-selected authority's
        # display_name/AID/phase, sourced from the same `egf.authorities(...)`
        # call the context combo(s) use. Populated/updated by
        # `_update_applying_to_header` (see `_build_context_controls`);
        # empty and hidden until a context selection resolves to exactly one
        # authority.
        applying_to_row = QHBoxLayout()
        applying_to_row.setSpacing(8)
        self._applying_to_text = QLabel("")
        self._applying_to_text.setObjectName("onboarding.applyingToText")
        self._applying_to_text.setStyleSheet(
            f"font-size: 13px; color: {colors.TEXT_SECONDARY}; background: transparent;"
        )
        self._applying_to_phase_badge = QLabel("")
        self._applying_to_phase_badge.setObjectName("onboarding.applyingToPhaseBadge")
        self._applying_to_phase_badge.setStyleSheet(
            f"background-color: {colors.BACKGROUND_HOVER}; color: {colors.TEXT_SECONDARY}; "
            "border-radius: 8px; font-size: 11px; font-weight: 600; padding: 1px 8px;"
        )
        applying_to_row.addWidget(self._applying_to_text)
        applying_to_row.addWidget(self._applying_to_phase_badge)
        applying_to_row.addStretch(1)
        self._applying_to_row_widget = QWidget()
        self._applying_to_row_widget.setStyleSheet("background: transparent;")
        self._applying_to_row_widget.setLayout(applying_to_row)
        self._applying_to_row_widget.setVisible(False)
        outer.addWidget(self._applying_to_row_widget)

        form_layout = QVBoxLayout()
        outer.addLayout(form_layout)

        error_layout = QVBoxLayout()
        outer.addLayout(error_layout)

        submit_btn = LocksmithButton("Submit")
        submit_btn.setObjectName("onboarding.submitButton")
        submit_btn.clicked.connect(self.submit)
        outer.addWidget(submit_btn)
        outer.addStretch(1)

        scroll.setWidget(container)
        return scroll, form_layout, error_layout

    # -- accessors (test seams) --------------------------------------------

    def role_cards(self) -> List[RoleCard]:
        """The currently-rendered overview cards — one per onboardable role.
        Rebuilt (see ``_rebuild_overview``) every time ``_render()`` shows
        the overview; empty while the FORM view is showing instead."""
        return list(self._role_cards)

    # -- state machine ------------------------------------------------------

    def refresh(self) -> None:
        """Recompute every persona's ``RoleStatus`` from ``held_provider()``
        + ``applies_provider()`` and re-render. Callers (the shell) connect
        this to ``doer_event`` so a newly-issued/sent/revoked credential is
        reflected without reconstructing the page.

        ``suppress_revoked_roles`` is passed straight through to
        ``derive_role_states`` as the current ``_reapplying_roles`` set (the
        per-role re-apply escape hatch — see ``_on_card_request``); a role
        is dropped from that set the moment THIS refresh re-derives it as
        ACTIVE (a fresh grant landed and was admitted) — the escape hatch is
        no longer needed once the holder is active again.
        """
        held = self._held_provider()
        applies = self._applies_provider()
        self.role_states = derive_role_states(
            held, applies, self._egf,
            suppress_revoked_roles=frozenset(self._reapplying_roles))
        for role_id, status in self.role_states.items():
            if status is RoleStatus.ACTIVE:
                self._reapplying_roles.discard(role_id)
        self._render()

    def on_doer_event(self, doer_name: str, event_type: str, data: dict) -> None:
        """Wired (by the shell, alongside ``refresh``) to the vault's
        ``doer_event`` signal bridge. Three sources surface here:

        - ``("RequestFlow", "request_failed")`` — form-mode submission
          failures (``NoAuthorityError``, ``EgfDocumentError``, the
          envelope self-enforcement guard, etc. — see
          ``request_flow.py``'s ``submit()``), rendered as a visible inline
          banner on the form view (acceptance-demo item 2).
        - ``("ApplyFlow", "apply_failed")`` — apply-mode request failures
          (an ineligible identifier, an ambiguous/missing authority, an
          unreachable issuer — see the shell's ``_request_role``/
          ``make_apply_doer``). Apply-mode requests never leave the
          OVERVIEW (``_role_id`` stays ``None`` — see ``_on_card_request``),
          so this renders on the OVERVIEW's own banner
          (``_show_overview_error``), not the form's ``_error_layout``
          (review fix: rendering it there left it invisible). Also rolls
          back a REVOKED role's speculative ``_reapplying_roles``
          suppression (mapped from ``data["schema_said"]`` via
          ``_role_id_for_schema``) and ``refresh()``es, so a failed
          re-apply reverts the card to REVOKED instead of lying AVAILABLE
          with no visible error.
        - ``("ApplyFlow", "apply_sent")`` — a successful apply send; clears
          the overview banner and triggers ``refresh()`` so the role's card
          picks up its new PENDING status.

        Distinct from ``refresh()``: that one re-derives every role's
        status from ANY event (cheap, idempotent); this one reacts
        specifically to the two failure events (which carry a
        human-readable message ``refresh()`` has no use for) and the
        apply-sent success event. Ignores every other ``(doer_name,
        event_type)`` combination."""
        if doer_name == "RequestFlow" and event_type == "request_failed":
            self._clear_form_errors()
            self._show_form_errors([str(data.get("message", ""))])
            return
        if doer_name == "ApplyFlow" and event_type == "apply_failed":
            message = str(data.get("error", ""))
            if self._role_id is not None:
                # Defensive fallback only: apply-mode requests never set
                # `_role_id` (they never leave the overview -- see
                # `_on_card_request`), so this branch should be dead in
                # practice. Kept so a future change routing apply-mode
                # through the form view doesn't silently regress back to an
                # invisible failure.
                self._clear_form_errors()
                self._show_form_errors([message])
                return
            # Review fix: the OVERVIEW is what's actually on screen for an
            # apply-mode failure, so the banner belongs there, not in the
            # (invisible) form's `_error_layout`.
            self._show_overview_error(message)
            # Suppression rollback: a REVOKED role's Request-again click
            # (`_on_card_request`) speculatively added it to
            # `_reapplying_roles` so the outstanding PENDING wasn't
            # immediately re-masked by the still-held revoked grant. That
            # request just failed, so undo the speculation -- otherwise the
            # card keeps lying AVAILABLE with no visible error instead of
            # reverting to REVOKED.
            role_id = self._role_id_for_schema(data.get("schema_said"))
            if role_id is not None:
                self._reapplying_roles.discard(role_id)
            self.refresh()
            return
        if doer_name == "ApplyFlow" and event_type == "apply_sent":
            self._clear_overview_error()
            self.refresh()

    def _render(self) -> None:
        if self._role_id is not None:          # form-mode flow in progress
            if self._built_form_role_id != self._role_id:
                # A broken/incomplete role config (missing micro_app_resolver,
                # or a resolved template lacking the expected command) must
                # not crash the whole page render -- surface it as the same
                # inline banner request_failed/apply_failed use, mirroring
                # the "never let a page-level render crash" posture the rest
                # of this module already follows (RequestFlow.submit,
                # on_doer_event). _build_form_view's own guard tests call it
                # directly and still observe the raw ValueError.
                try:
                    self._build_form_view(self._role_id)
                except ValueError as exc:
                    self._clear_form_errors()
                    self._show_form_errors([str(exc)])
            self._stack.setCurrentWidget(self._form_container)
            return
        self._rebuild_overview()
        self._stack.setCurrentWidget(self._overview_widget)

    def _rebuild_overview(self) -> None:
        self._clear_layout(self._overview_cards_layout)
        self._role_cards = []
        for role in self._egf.personas():
            status = self.role_states.get(role.id, RoleStatus.AVAILABLE)
            card = RoleCard(role, status,
                            page_available=self._page_available(role.id),
                            opens_at_startup=(self._startup_key() == role.id))
            card.request_clicked.connect(self._on_card_request)
            card.open_clicked.connect(self._open_role)
            card.default_toggled.connect(self._on_default_toggled)
            self._role_cards.append(card)
            self._overview_cards_layout.addWidget(card)

    def _startup_key(self) -> Optional[str]:
        """Which role currently opens at startup, or None. None-guarded like
        every other provider here: this page is constructed before a vault
        exists."""
        if self._startup_provider is None:
            return None
        try:
            return self._startup_provider()
        except Exception:               # noqa: BLE001 -- a preference, not state
            logger.debug("onboarding.startup_pref_unreadable", exc_info=True)
            return None

    def _on_default_toggled(self, role_id: str, on: bool) -> None:
        """Pin or clear the startup page, then rebuild so exactly one card can
        show as ticked -- the preference is single-valued, and two ticked boxes
        would be a lie about what happens next."""
        if self._on_set_startup is None:
            return
        self._on_set_startup(role_id, on)
        self._rebuild_overview()

    def _on_card_request(self, role_id: str) -> None:
        """A card's Request/Request-again button was clicked. Routes on the
        role's onboarding mode: a form-mode role (micro-app application
        form) opens the FORM view exactly like the old ``select_persona``;
        an apply-mode
        role calls ``on_apply`` directly (no form) — marking it in
        ``_reapplying_roles`` first when it was REVOKED, so this apply's
        outstanding-request PENDING status isn't immediately re-masked by
        the still-held revoked grant (see ``refresh()``'s docstring)."""
        # A new request attempt begins -- any stale banner from a PRIOR
        # apply_failed no longer applies (review fix, item 4).
        self._clear_overview_error()
        role = self._egf.role(role_id)
        if role.onboarding is not None and not role.onboarding.apply_mode:
            self._role_id = role_id            # form-mode application flow
            self.refresh()
            return
        if self.role_states.get(role_id) is RoleStatus.REVOKED:
            self._reapplying_roles.add(role_id)
        if self._on_apply is not None:
            self._on_apply(role_id)
        self.refresh()

    def _open_role(self, role_id: str) -> None:
        """An ACTIVE card's Open button was clicked -- hand off to the
        shell's own navigation (e.g. ``vault_page._show_vault_page(role_id)``,
        per the role-plugin-page-key convention documented on ``RoleCard``)."""
        if self._open_role_cb is not None:
            self._open_role_cb(role_id)

    # -- OVERVIEW error banner (review fix: apply-mode failures were invisible) --

    def _show_overview_error(self, message: str) -> None:
        """Render an apply-mode failure on the OVERVIEW's own banner
        (``self._overview_error_label``, built in ``_build_overview_shell``)
        -- apply-mode requests never leave the overview (``_role_id`` stays
        ``None``), so the FORM view's error layout is never the widget
        actually on screen to show it. Scrolls it into view the same way
        ``_show_form_errors`` does for the form banner (item 2's "must
        actually be seen" posture)."""
        self._overview_error_label.setText(message)
        self._overview_error_label.setVisible(bool(message))
        if message:
            self._overview_widget.ensureWidgetVisible(self._overview_error_label)

    def _clear_overview_error(self) -> None:
        self._overview_error_label.setText("")
        self._overview_error_label.setVisible(False)

    def _role_id_for_schema(self, schema_said: Optional[str]) -> Optional[str]:
        """The persona whose grant credential's schema SAID matches
        ``schema_said``, or ``None``. Used by ``on_doer_event``'s
        ``apply_failed`` handler to map the failure (which carries the
        GRANT credential's ``schema_said`` -- see
        ``serviceaid_bridge.ServiceaidApplyDoer``/``make_apply_doer``) back
        to a role id for the reapply-suppression rollback."""
        if not schema_said:
            return None
        for persona in self._egf.personas():
            grant = self._egf.credential(persona.onboarding.grant_credential_id)
            if grant.schema_said == schema_said:
                return persona.id
        return None

    # -- FORM construction ---------------------------------------------------

    def _build_form_view(self, role_id: str) -> None:
        role = self._egf.role(role_id)
        onboarding = role.onboarding
        if onboarding is None:
            raise ValueError(f"role {role_id!r} has no onboarding block — not a persona")
        if self._micro_app_resolver is None:
            raise ValueError(
                "micro_app_resolver is required once a persona is selected "
                "(the page only defers it while showing the overview)"
            )

        template = self._micro_app_resolver(onboarding.request_micro_app_said)
        command = next(
            (c for c in template.get("commands", []) if c["id"] == onboarding.request_command_id),
            None,
        )
        if command is None:
            # Mirrors the library's EgfDocumentError message style ("no X in
            # Y") but stays a plain ValueError — the defect is in the
            # resolved TEMPLATE (or the EGF's pointer into it), not in the
            # EGF document shape, so EgfDocumentError would mislabel it.
            raise ValueError(
                f"no command {onboarding.request_command_id!r} in micro-app template "
                f"{onboarding.request_micro_app_said!r} (role {role_id!r})"
            )
        payload_schema = command["payload_schema"]

        self._clear_layout(self._form_layout)
        self.form = SchemaFormBuilder(payload_schema)
        form_widget = self.form.build(parent=self._form_container)
        self._form_layout.addWidget(form_widget)

        self._build_context_controls(role, payload_schema)
        self._clear_form_errors()
        self._built_form_role_id = role_id

    def _build_context_controls(self, role: Role, payload_schema: Dict[str, Any]) -> None:
        self._context_widgets = {}
        self._context_prompts = {}
        self._shared_dims = {}
        self._context_authorities = []

        grant = self._egf.credential(role.onboarding.grant_credential_id)
        issuer_role = grant.issuer_role
        dims = self._egf.context_dimensions(issuer_role)
        if not dims:
            self._update_applying_to_header()
            return

        properties = (payload_schema or {}).get("properties", {}) or {}
        required_props = set((payload_schema or {}).get("required", []) or [])
        authorities = self._egf.authorities(issuer_role, accept_phases=self._accept_phases)
        self._context_authorities = authorities

        context_group = None
        context_form = None

        for dim in dims:
            options = self._dedup_context_options(authorities, dim.id)
            self._context_prompts[dim.id] = dim.prompt or dim.id

            if dim.id in properties:
                # ONE control serves both, authority-narrowed (spec §7.4):
                # the form's own rendered field for this property is
                # REPLACED with a combo whose options are the available
                # authorities' context values — never a free-text field the
                # user could type an unmatchable value into. No duplicate
                # widget is created; submit() mirrors its (raw) value into
                # the context dict.
                self._shared_dims[dim.id] = dim.id in required_props
                combo = self.form.replace_field_with_combo(dim.id, options)
                combo.setObjectName(f"onboarding.context.{dim.id}")
                if dim.prompt:
                    combo.setToolTip(dim.prompt)
                combo.currentIndexChanged.connect(lambda _i: self._update_applying_to_header())
                continue

            if context_group is None:
                # Built lazily: skip entirely when every dimension for
                # this role turns out to be shared with a payload field.
                context_group = QGroupBox("Issuing authority")
                context_group.setStyleSheet(_GROUP_BOX_QSS)
                context_form = QFormLayout(context_group)

            combo = QComboBox()
            combo.setObjectName(f"onboarding.context.{dim.id}")
            if dim.prompt:
                combo.setToolTip(dim.prompt)
            for raw_value, display_text in options:
                combo.addItem(display_text, raw_value)
            combo.setCurrentIndex(-1)
            combo.currentIndexChanged.connect(lambda _i: self._update_applying_to_header())
            self._context_widgets[dim.id] = combo
            context_form.addRow(dim.prompt or dim.id, combo)

        if context_group is not None:
            self._form_layout.addWidget(context_group)

        self._update_applying_to_header()

    # -- "applying to" header (item 5) ---------------------------------------

    def _selected_context(self) -> Dict[str, Any]:
        """Best-effort CURRENT context selections across both dedicated and
        shared-dim combos, for whichever dimensions are already selected —
        used only to preview the "applying to" authority as the user fills
        the form. ``submit()``'s own validation remains the sole authority
        on what's actually required."""
        result: Dict[str, Any] = {}
        for dim_id, combo in self._context_widgets.items():
            if combo.currentIndex() != -1:
                result[dim_id] = combo.currentData()
        for dim_id in self._shared_dims:
            combo = self.form.widget_for(dim_id) if self.form is not None else None
            if combo is not None and combo.currentIndex() != -1:
                result[dim_id] = combo.currentData()
        return result

    def _resolve_selected_authority(self):
        """The single ``Authority`` matching every CURRENTLY-selected
        context dimension, or ``None`` when nothing is selected yet or the
        selection doesn't narrow to exactly one authority."""
        if not self._context_authorities:
            return None
        context = self._selected_context()
        if not context:
            return None
        matches = [
            a for a in self._context_authorities
            if all(a.context.get(k) == v for k, v in context.items())
        ]
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _applying_to_text_for(authority, *, verb: str = "Applying to") -> "tuple[str, str]":
        """(main_text, phase_badge_text) for a resolved authority — shared
        by ``_update_applying_to_header`` (renders it) and
        ``applying_to_summary`` (a test/inspection seam), so both can never
        drift apart on the display_name/AID/phase-badge formatting itself."""
        aid = authority.aid
        truncated_aid = aid if len(aid) <= 12 else f"{aid[:12]}…"
        phase_label = "pilot" if authority.phase == "bootstrap" else authority.phase
        return f"{verb} {authority.display_name}  ·  {truncated_aid}", phase_label.upper()

    def _update_applying_to_header(self) -> None:
        """Refresh the form view's "applying to" header from the currently
        resolvable authority (see ``_resolve_selected_authority``) — wired
        to fire on every context/shared-dim combo change."""
        authority = self._resolve_selected_authority()
        if authority is None:
            self._applying_to_row_widget.setVisible(False)
            return

        text, badge = self._applying_to_text_for(authority)
        self._applying_to_text.setText(text)
        self._applying_to_phase_badge.setText(badge)
        self._applying_to_row_widget.setVisible(True)

    def applying_to_summary(self) -> str:
        """Test/inspection seam: the current "applying to" header's combined
        text (display name + AID + phase badge), or ``""`` when no context
        selection currently resolves to exactly one authority. Recomputed
        independently of the rendered labels (not a `.isVisible()`/`.text()`
        readback) so it works the same whether or not the page is actually
        shown on screen — real widget visibility depends on the whole
        ancestor chain being shown, which off-screen tests never do."""
        authority = self._resolve_selected_authority()
        if authority is None:
            return ""
        text, badge = self._applying_to_text_for(authority)
        return f"{text}  {badge}"

    @staticmethod
    def _dedup_context_options(authorities, dimension_key: str):
        """Ordered, deduped (raw_value, display_text) pairs for one
        context dimension's combo, sourced from authorities' own context
        dicts. Bootstrap-phase authorities get a " (pilot)" suffix on the
        display text (the raw value used for context/payload is never
        suffixed)."""
        seen: Dict[Any, str] = {}
        for authority in authorities:
            raw_value = authority.context.get(dimension_key)
            if raw_value is None or raw_value in seen:
                continue
            text = f"{raw_value} (pilot)" if authority.phase == "bootstrap" else str(raw_value)
            seen[raw_value] = text
        return list(seen.items())

    # -- submit ---------------------------------------------------------------

    def submit(self) -> None:
        """Validate the current form AND every context combo (dedicated and
        shared-dim alike); if clean, call ``on_submit`` with the role id,
        the payload dict, and the context dict (shared dimensions mirrored
        from the payload; dedicated context combos read via their stored
        raw ``currentData()``).

        Both combo flavors are outside ``SchemaFormBuilder.validate()``'s
        own opinion (a shared dim's field was replaced with a combo via
        ``replace_field_with_combo``, which the builder deliberately treats
        as always "valid" — see its docstring) — they are validated HERE
        instead (an unselected combo blocks submission with an inline error
        named after the dimension's prompt, e.g. "Which state? is
        required"), never passed through as a ``None`` context value. A
        shared dim is only required-gated this way when the ORIGINAL
        payload schema actually required it (``_shared_dims[dim_id]``) —
        an optional shared dim left unselected is not an error."""
        self._clear_form_errors()
        errors = self.form.validate()
        for dim_id, combo in self._context_widgets.items():
            if combo.currentIndex() == -1:
                errors.append(f"{self._context_prompts.get(dim_id, dim_id)} is required")
        for dim_id, required in self._shared_dims.items():
            if required and self.form.widget_for(dim_id).currentIndex() == -1:
                errors.append(f"{self._context_prompts.get(dim_id, dim_id)} is required")
        if errors:
            self._show_form_errors(errors)
            return

        payload = self.form.values()
        context: Dict[str, Any] = {}
        for dim_id, combo in self._context_widgets.items():
            context[dim_id] = combo.currentData()
        for dim_id in self._shared_dims:
            context[dim_id] = self._dotted_get(payload, dim_id)

        self._on_submit(self._role_id, payload, context)

    @staticmethod
    def _dotted_get(payload: Dict[str, Any], dotted_path: str) -> Any:
        node: Any = payload
        for part in dotted_path.split("."):
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        return node

    def _clear_form_errors(self) -> None:
        for label in self._error_labels:
            label.setParent(None)
            label.deleteLater()
        self._error_labels = []

    def _show_form_errors(self, messages: List[str]) -> None:
        for message in messages:
            label = QLabel(message)
            label.setObjectName("form-error")
            label.setWordWrap(True)
            label.setStyleSheet(
                f"color: {colors.DANGER}; background-color: {colors.BACKGROUND_ERROR}; "
                "border-radius: 6px; padding: 8px 12px;"
            )
            self._error_layout.addWidget(label)
            self._error_labels.append(label)

        # Item 2: a freshly-rendered error (validation OR a request_failed/
        # apply_failed banner) must actually be seen, not just exist below
        # the fold on a long form — scroll the form's QScrollArea (see
        # _build_form_shell) so the newest error row is visible.
        if self._error_labels:
            self._form_container.ensureWidgetVisible(self._error_labels[-1])

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    # -- BasePage ---------------------------------------------------------

    def get_toolbar_config(self) -> Dict[str, Any]:
        """Onboarding runs before any role credential is held — no vault
        drawer or lock control applies yet (mirrors ``SetupPage``)."""
        return {
            "show_vaults_button": False,
            "show_lock_button": False,
            "show_settings_button": True,
        }
