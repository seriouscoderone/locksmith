# -*- encoding: utf-8 -*-
"""
locksmith.ui.onboarding.home_page module

``OnboardingHomePage`` — the "Who are you?" persona picker and the
vault-derived onboarding state machine (design spec §7.4, Task 6).

Renders one clickable card per onboardable role (an EGF ``Role`` with an
``onboarding`` block — see ``EgfDocument.personas()``). Picking a card
builds that role's application form (Task 5's ``SchemaFormBuilder``) from
its micro-app's ``request_command_id`` command, plus a per-issuer
context-selection control (design spec §7.4 "context binding") so the
holder also picks WHICH authority (e.g. which state regulator) they're
applying to.

**State derivation is pure** (``derive_state``, no Qt): it reads the
vault's held-credential views (the credential gate's ``HeldCredential``
shape — see ``plugins/manager.py``'s ``_held_credentials``) against the
EGF document to decide which of PICKER/FORM/PENDING/LICENSED/REVOKED to
show. Precedence is LICENSED > REVOKED > PENDING > FORM > PICKER:

- LICENSED — a held, chain-verified, ``state == "active"`` credential
  whose schema matches ANY onboardable role's grant credential
  (``egf.credential(role.onboarding.grant_credential_id).schema_said``).
  Checked independent of the chosen ``role_id`` (a returning, already-
  licensed holder should land here even before picking a persona card).
  A REVOKED grant does not count — it simply fails this check and falls
  through to the next precedence level.
- REVOKED — a held, chain-verified credential whose schema matches ANY
  onboardable role's grant credential and whose ``state`` is exactly
  ``"revoked"``. Checked role-agnostically, same as LICENSED, and
  independent of the chosen ``role_id`` — a returning holder whose
  license was revoked sees the revocation treatment even before picking
  a persona card, and even if their own (now superseded) application
  credential is still held (REVOKED wins over PENDING). An ACTIVE grant
  elsewhere still wins LICENSED first (checked one precedence level
  above), and a credential that was never chain-verified (still escrowed)
  does NOT count as a revocation — it falls through same as before.
- PENDING — the chosen role's application credential (the credential the
  grant chains FROM: ``credential(grant.chained_from)``) is held and
  chain-verified (and not itself revoked). Requires a chosen ``role_id``
  (there is no single, role-agnostic "application" credential to check).
- FORM — a ``role_id`` has been chosen and none of the above applied.
- PICKER — nothing chosen yet (the default landing state).

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

from keri_serviceaid.egf.documents import EgfDocument, Role

from locksmith.ui import colors
from locksmith.ui.onboarding.form_builder import SchemaFormBuilder
from locksmith.ui.toolkit.pages.base import BasePage
from locksmith.ui.toolkit.widgets import LocksmithButton

from enum import Enum


class OnboardingState(Enum):
    """The onboarding home page's five possible views."""

    PICKER = "picker"
    FORM = "form"
    PENDING = "pending"
    LICENSED = "licensed"
    REVOKED = "revoked"


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


def _held_matches(held: Iterable[Any], schema_said: str, *, require_active: bool) -> bool:
    """True iff any held-credential view matches ``schema_said`` and is
    chain-verified. When ``require_active`` the view's ``state`` must be
    exactly ``"active"`` (the LICENSED check); otherwise only a
    ``"revoked"`` state disqualifies it (the PENDING check — application
    credentials aren't necessarily TEL-backed the same way a license is,
    so their state vocabulary isn't pinned to "active")."""
    for h in held:
        if h.schema_said != schema_said or not h.chain_verified:
            continue
        if require_active:
            if h.state == "active":
                return True
        else:
            if h.state != "revoked":
                return True
    return False


def _held_revoked(held: Iterable[Any], schema_said: str) -> bool:
    """True iff a chain-verified held credential of ``schema_said`` is in the
    revoked TEL state. Requires chain_verified (same as ``_held_matches``): a
    revoked credential stays in ``reger.saved``, so a genuinely-granted-then-
    revoked license still reads chain_verified=True — only an escrowed, never-
    verified credential fails this, which must NOT read as a revocation."""
    for h in held:
        if h.schema_said == schema_said and h.chain_verified and h.state == "revoked":
            return True
    return False


def derive_state(held: list, egf: EgfDocument, role_id: Optional[str]) -> OnboardingState:
    """Pure state derivation — no Qt, no I/O. See module docstring for the
    full precedence rationale (LICENSED > REVOKED > PENDING > FORM > PICKER)."""
    # LICENSED: checked against EVERY onboardable role's grant credential,
    # regardless of role_id — a returning, already-licensed holder should
    # be recognized even before picking a persona card.
    for persona in egf.personas():
        grant = egf.credential(persona.onboarding.grant_credential_id)
        if _held_matches(held, grant.schema_said, require_active=True):
            return OnboardingState.LICENSED

    # REVOKED: a held, chain-verified gating credential in the revoked state,
    # checked role-agnostically (like LICENSED) and BEFORE the PENDING/PICKER
    # fall-through — so a returning holder whose license was revoked sees the
    # revocation treatment rather than silently dropping to PENDING (they still
    # hold their own self-issued application) or PICKER.
    for persona in egf.personas():
        grant = egf.credential(persona.onboarding.grant_credential_id)
        if _held_revoked(held, grant.schema_said):
            return OnboardingState.REVOKED

    if role_id is not None:
        role = egf.role(role_id)
        if role.onboarding is not None:
            grant = egf.credential(role.onboarding.grant_credential_id)
            if grant.chained_from is not None:
                application = egf.credential(grant.chained_from)
                if _held_matches(held, application.schema_said, require_active=False):
                    return OnboardingState.PENDING
        return OnboardingState.FORM

    return OnboardingState.PICKER


class PersonaCard(QFrame):
    """One clickable card in the persona picker — display_name,
    description, and a kind glyph for a single onboardable ``Role``.

    Emits ``selected(role_id)`` on click; ``OnboardingHomePage`` wires
    that to ``select_persona``. Styled following ``LocksmithRadioPanel``'s
    precedent (``ui/toolkit/widgets/buttons.py``) of keying the stylesheet
    off the Python class name rather than an objectName selector.
    """

    selected = Signal(str)

    def __init__(self, role: Role, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.role_id = role.id
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"""
            PersonaCard {{
                border: 1px solid {colors.BORDER};
                border-radius: 8px;
                background-color: {colors.BACKGROUND_CONTENT};
            }}
            PersonaCard:hover {{
                border: 1px solid {colors.PRIMARY};
                background-color: {colors.BACKGROUND_HOVER};
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

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self.role_id)
        super().mousePressEvent(event)


class OnboardingErrorPage(QWidget):
    """Minimal error-state view registered as vault "home" when the
    onboarding brand's pinned EGF bundle fails to resolve/verify (missing,
    tampered, or incomplete `document_said` -- see `EgfResolver`/
    `make_hoa_resolver`). Hardening wave item 1, design spec §4.5: "A
    persona picker over a broken EGF shows an error state, not an empty
    list."

    Deliberately NOT a state machine like ``OnboardingHomePage`` -- there is
    no vault-derived state to react to; the workspace's onboarding surface
    is simply unusable until an administrator fixes the bundle. Follows
    ``OnboardingHomePage``'s message-view house style (see
    ``_build_message_view``) and reuses its ``"form-error"`` objectName
    convention (``_show_form_errors``) for the message label so tests and
    stylesheets can find/style it the same way.
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

        layout.addStretch(2)


class OnboardingHomePage(BasePage):
    """The onboarding home screen: persona picker + role application form,
    driven by ``derive_state``.

    Args:
        egf_doc: The ecosystem's typed ``EgfDocument`` (source of
            personas, roles, credentials, authorities, context
            dimensions).
        held_provider: Zero-arg callable returning the current list of
            held-credential views (the gate's ``HeldCredential`` shape).
            Called fresh on every ``refresh()``.
        on_submit: ``(role_id, payload, context) -> None`` invoked once
            the chosen role's form validates cleanly.
        micro_app_resolver: ``(said) -> dict`` resolving a micro-app
            template (its ``commands`` list, each with an ``id`` and
            ``payload_schema``) — e.g. B8's ``resolver.resolve_micro_app``.
            Only required once a persona is actually selected; may be
            omitted while the page is only ever shown in PICKER/LICENSED
            states (as in tests that don't select a persona).
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
        micro_app_resolver: Optional[Callable[[str], dict]] = None,
        accept_phases: Iterable[str] = ("production",),
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._egf = egf_doc
        self._held_provider = held_provider
        self._on_submit = on_submit
        self._micro_app_resolver = micro_app_resolver
        self._accept_phases = tuple(accept_phases)

        self._role_id: Optional[str] = None
        self.state: OnboardingState = OnboardingState.PICKER
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
        self._persona_cards: List[PersonaCard] = []
        self._error_labels: List[QLabel] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._stack = QStackedWidget(self)
        outer.addWidget(self._stack)

        self._picker_widget = self._build_picker_view()
        self._pending_widget = self._build_pending_view()
        self._licensed_widget = self._build_message_view(
            "You're all set", "A valid license was found in your vault."
        )
        self._revoked_widget = self._build_revoked_view()
        self._form_container, self._form_layout, self._error_layout = self._build_form_shell()

        self._stack.addWidget(self._picker_widget)
        self._stack.addWidget(self._pending_widget)
        self._stack.addWidget(self._licensed_widget)
        self._stack.addWidget(self._revoked_widget)
        self._stack.addWidget(self._form_container)

        self.refresh()

    # -- construction: static views ---------------------------------------

    def _build_picker_view(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        # Acceptance-demo fix wave item 1: QAbstractScrollArea's viewport
        # paints from its OWN palette, not the app-wide QSS cascade (see
        # KFOnboardingPage's identical treatment) — without this, an
        # unstyled scroll area shows the OS's native (dark, under a dark
        # system appearance) background regardless of this app's own light
        # theme, which is exactly what made the "Who are you?" heading
        # below (styled in TEXT_PRIMARY, meant for a LIGHT background)
        # unreadable on a black page.
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(48, 48, 48, 48)
        layout.setSpacing(16)

        heading = QLabel("Who are you?")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet(f"font-size: 24px; font-weight: 600; color: {colors.TEXT_PRIMARY};")
        layout.addWidget(heading)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(16)
        for role in self._egf.personas():
            card = PersonaCard(role)
            card.selected.connect(self.select_persona)
            self._persona_cards.append(card)
            cards_row.addWidget(card)
        layout.addLayout(cards_row)
        layout.addStretch(1)

        scroll.setWidget(inner)
        return scroll

    def _build_message_view(self, heading_text: str, body_text: str) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(48, 48, 48, 48)
        layout.addStretch(1)

        heading = QLabel(heading_text)
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet(f"font-size: 22px; font-weight: 600; color: {colors.TEXT_PRIMARY};")
        layout.addWidget(heading)

        body = QLabel(body_text)
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.setWordWrap(True)
        body.setStyleSheet(f"font-size: 14px; color: {colors.TEXT_SECONDARY};")
        layout.addWidget(body)

        layout.addStretch(2)
        return widget

    def _build_revoked_view(self) -> QWidget:
        """The REVOKED view — "your access was revoked", issuer + revocation
        time, and a re-apply affordance back into the persona flow. Widgets are
        populated per-render by ``_update_revoked_view`` (the revoked role /
        issuer / time are read from EGF + the current held snapshot)."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(48, 48, 48, 48)
        layout.addStretch(1)

        self._revoked_heading = QLabel("Your access was revoked")
        self._revoked_heading.setObjectName("onboarding.revokedHeading")
        self._revoked_heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._revoked_heading.setStyleSheet(
            f"font-size: 22px; font-weight: 600; color: {colors.TEXT_PRIMARY};")
        layout.addWidget(self._revoked_heading)

        self._revoked_detail = QLabel("")
        self._revoked_detail.setObjectName("onboarding.revokedDetail")
        self._revoked_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._revoked_detail.setWordWrap(True)
        self._revoked_detail.setStyleSheet(
            f"font-size: 14px; color: {colors.TEXT_SECONDARY}; background: transparent;")
        layout.addWidget(self._revoked_detail)

        reapply_btn = LocksmithButton("Apply again")
        reapply_btn.setObjectName("onboarding.reapplyButton")
        reapply_btn.clicked.connect(self._reapply)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(reapply_btn)
        row.addStretch(1)
        layout.addLayout(row)

        layout.addStretch(2)
        return widget

    def _revoked_role(self):
        """The onboardable ``Role`` whose grant credential is currently held-
        and-revoked, or ``None``. Mirrors ``derive_state``'s REVOKED scan so
        the two never disagree on WHICH role was revoked."""
        held = self._held_provider()
        for persona in self._egf.personas():
            grant = self._egf.credential(persona.onboarding.grant_credential_id)
            if _held_revoked(held, grant.schema_said):
                return persona
        return None

    def _revoked_at_for(self, grant) -> str:
        for h in self._held_provider():
            if (h.schema_said == grant.schema_said and h.chain_verified
                    and h.state == "revoked"):
                return getattr(h, "revoked_at", "") or ""
        return ""

    def _update_revoked_view(self) -> None:
        role = self._revoked_role()
        if role is None:
            # Shouldn't happen once derive_state returned REVOKED, but stay
            # defensive: generic copy rather than a crash.
            self._revoked_heading.setText("Your access was revoked")
            self._revoked_detail.setText("")
            return
        grant = self._egf.credential(role.onboarding.grant_credential_id)
        self._revoked_heading.setText(f"Your {role.display_name} access was revoked")

        authorities = self._egf.authorities(
            grant.issuer_role, accept_phases=self._accept_phases)
        issuer = authorities[0] if len(authorities) == 1 else None
        revoked_at = self._revoked_at_for(grant)
        parts = []
        if issuer is not None:
            parts.append(f"{grant.name} issued by {issuer.display_name} was revoked.")
        else:
            parts.append(f"Your {grant.name} was revoked.")
        if revoked_at:
            parts.append(f"Revoked {revoked_at}.")
        parts.append("You can apply again below.")
        self._revoked_detail.setText(" ".join(parts))

    def _reapply(self) -> None:
        """Re-apply affordance: clear the chosen role and re-derive. With the
        gating credential gone (or the holder starting over), this lands on the
        persona picker; the normal apply flow proceeds from there."""
        self._role_id = None
        self.refresh()

    def _build_pending_view(self) -> QWidget:
        """The PENDING view — dedicated (no longer ``_build_message_view``)
        so it can carry EGF-derived context instead of a static "awaiting
        approval" dead end (owner live-demo finding, hoa-onboarding
        branch). Widgets built here are populated per-render by
        ``_update_pending_view`` (called from ``_render``, since
        ``select_persona``/``refresh`` may switch to a different role
        between PENDING renders) with two pieces:

        1. WHO it went to — the accepted authority's display_name +
           truncated AID + phase badge, formatted the same way as the
           form's "applying to" header (``_applying_to_text_for``, verb
           "Submitted to"). Honest-data-path note: the vault's
           held-credential view (``HeldCredential`` in
           ``plugins/manager.py`` — schema_said/issuer_aid/state/
           chain_verified) carries no ACDC attributes, so the jurisdiction
           actually chosen at submission time can't be read back off it.
           ``_pending_authority`` therefore falls back to the grant
           credential's issuer_role's full accepted-authorities list and
           shows it only when that narrows to exactly one authority (true
           today — the pilot has a single bootstrap-phase regulator);
           otherwise this row stays hidden rather than guessing among
           several.
        2. WHAT HAPPENS NEXT — a fixed sentence template
           (``_pending_next_steps_text``) with the authority's
           display_name (when resolved), the grant credential's ``name``,
           and the onboarded role's ``display_name`` interpolated in — no
           other hard-coded strings.
        3. A NOTIFICATION HINT (Task 10, HOA #2 live-demo finding) — a
           fixed line pointing at the new persistent Notifications surface
           (``locksmith.ui.hoa.notifications_page.HoaNotificationsPage``),
           so the PENDING view doesn't read as a dead end with no
           indication anything will ever happen.
        4. AN APPLICATION ID ROW — the held application credential's own
           SAID (Task 9 grew ``HeldCredential.said`` for exactly this).
           Previously deliberately absent (see history: ``HeldCredential``
           used to expose no per-instance identifier, only the type-
           identifying ``schema_said``, and labeling that as the
           application's instance SAID would have been mislabeled
           identifier data on a trust surface). Resolved via
           ``_pending_application_said`` against the CURRENT
           ``held_provider()`` snapshot; hidden (not shown blank) when it
           can't be resolved — e.g. no matching held view, or (back-compat)
           a held-credential view that predates Task 9's ``said`` field.
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(48, 48, 48, 48)
        layout.addStretch(1)

        heading = QLabel("Application pending")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet(f"font-size: 22px; font-weight: 600; color: {colors.TEXT_PRIMARY};")
        layout.addWidget(heading)

        # WHO (item 1): same row styling as the form's "applying to"
        # header (_build_form_shell) — reused rather than re-invented so
        # the two authority call-outs read as the same UI element.
        authority_row = QHBoxLayout()
        authority_row.setSpacing(8)
        authority_row.addStretch(1)
        self._pending_authority_text = QLabel("")
        self._pending_authority_text.setObjectName("onboarding.pendingAuthorityText")
        self._pending_authority_text.setStyleSheet(
            f"font-size: 14px; color: {colors.TEXT_SECONDARY}; background: transparent;"
        )
        self._pending_authority_badge = QLabel("")
        self._pending_authority_badge.setObjectName("onboarding.pendingAuthorityPhaseBadge")
        self._pending_authority_badge.setStyleSheet(
            f"background-color: {colors.BACKGROUND_HOVER}; color: {colors.TEXT_SECONDARY}; "
            "border-radius: 8px; font-size: 11px; font-weight: 600; padding: 1px 8px;"
        )
        authority_row.addWidget(self._pending_authority_text)
        authority_row.addWidget(self._pending_authority_badge)
        authority_row.addStretch(1)
        self._pending_authority_row_widget = QWidget()
        self._pending_authority_row_widget.setStyleSheet("background: transparent;")
        self._pending_authority_row_widget.setLayout(authority_row)
        self._pending_authority_row_widget.setVisible(False)
        layout.addWidget(self._pending_authority_row_widget)

        # WHAT HAPPENS NEXT (item 2).
        self._pending_next_steps_label = QLabel("")
        self._pending_next_steps_label.setObjectName("onboarding.pendingNextSteps")
        self._pending_next_steps_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pending_next_steps_label.setWordWrap(True)
        self._pending_next_steps_label.setStyleSheet(
            f"font-size: 14px; color: {colors.TEXT_SECONDARY}; background: transparent;"
        )
        layout.addWidget(self._pending_next_steps_label)

        # NOTIFICATION HINT (item 3) — fixed copy, always shown while
        # PENDING; a separate label from the next-steps sentence above so
        # neither ever bleeds into the other's exact text.
        self._pending_notification_hint_label = QLabel(
            "You'll be notified here the moment your license arrives."
        )
        self._pending_notification_hint_label.setObjectName("onboarding.pendingNotificationHint")
        self._pending_notification_hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pending_notification_hint_label.setWordWrap(True)
        self._pending_notification_hint_label.setStyleSheet(
            f"font-size: 13px; color: {colors.TEXT_SECONDARY}; background: transparent;"
        )
        layout.addWidget(self._pending_notification_hint_label)

        # APPLICATION ID ROW (item 4) — populated/shown only when
        # _pending_application_said resolves one; hidden (not blank) when
        # it can't (see _update_pending_view).
        self._pending_application_said_label = QLabel("")
        self._pending_application_said_label.setObjectName("onboarding.pendingApplicationSaid")
        self._pending_application_said_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pending_application_said_label.setWordWrap(True)
        self._pending_application_said_label.setStyleSheet(
            f"font-size: 12px; color: {colors.TEXT_SECONDARY}; background: transparent;"
        )
        self._pending_application_said_label.setVisible(False)
        layout.addWidget(self._pending_application_said_label)

        layout.addStretch(2)
        return widget

    def _build_form_shell(self):
        # Acceptance-demo fix wave item 1: same QScrollArea-viewport
        # background fix as `_build_picker_view` (see its comment) — the
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

    def persona_cards(self) -> List[PersonaCard]:
        """The rendered persona cards — one per onboardable role."""
        return list(self._persona_cards)

    # -- state machine ------------------------------------------------------

    def select_persona(self, role_id: str) -> None:
        """Programmatic equivalent of clicking a persona card."""
        self._role_id = role_id
        self.refresh()

    def refresh(self) -> None:
        """Recompute state from ``held_provider()`` and re-render.
        Callers (B8) connect this to ``doer_event`` so a newly-issued or
        revoked credential is reflected without reconstructing the page."""
        held = self._held_provider()
        self.state = derive_state(held, self._egf, self._role_id)
        self._render()

    def on_doer_event(self, doer_name: str, event_type: str, data: dict) -> None:
        """Wired (by the window, alongside ``refresh``) to the vault's
        ``doer_event`` signal bridge — surfaces ``RequestFlow``'s OWN
        ``request_failed`` emissions (``NoAuthorityError``,
        ``EgfDocumentError``, the envelope self-enforcement guard, etc. —
        see ``request_flow.py``'s ``submit()``) as a visible inline banner
        on the form view (acceptance-demo item 2). Distinct from
        ``refresh()``: that one re-derives PICKER/FORM/PENDING/LICENSED
        state from ANY event (cheap, idempotent); this one reacts
        specifically to ``RequestFlow``'s failure event, which carries a
        human-readable message ``refresh()`` has no use for. Ignores every
        other ``(doer_name, event_type)`` combination."""
        if doer_name != "RequestFlow" or event_type != "request_failed":
            return
        self._clear_form_errors()
        self._show_form_errors([str(data.get("message", ""))])

    def _render(self) -> None:
        if self.state is OnboardingState.PICKER:
            self._stack.setCurrentWidget(self._picker_widget)
        elif self.state is OnboardingState.PENDING:
            self._update_pending_view(self._role_id)
            self._stack.setCurrentWidget(self._pending_widget)
        elif self.state is OnboardingState.LICENSED:
            self._stack.setCurrentWidget(self._licensed_widget)
        elif self.state is OnboardingState.REVOKED:
            self._update_revoked_view()
            self._stack.setCurrentWidget(self._revoked_widget)
        elif self.state is OnboardingState.FORM:
            if self._built_form_role_id != self._role_id:
                self._build_form_view(self._role_id)
            self._stack.setCurrentWidget(self._form_container)

    # -- FORM construction ---------------------------------------------------

    def _build_form_view(self, role_id: str) -> None:
        role = self._egf.role(role_id)
        onboarding = role.onboarding
        if onboarding is None:
            raise ValueError(f"role {role_id!r} has no onboarding block — not a persona")
        if self._micro_app_resolver is None:
            raise ValueError(
                "micro_app_resolver is required once a persona is selected "
                "(the page only defers it while showing PICKER/LICENSED)"
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
        by ``_update_applying_to_header`` (renders it), ``applying_to_summary``
        (a test/inspection seam), and ``_update_pending_view`` (verb
        "Submitted to", past-tense phrasing for a WHO-it-went-to callout on
        an already-submitted application), so all three can never drift
        apart on the display_name/AID/phase-badge formatting itself."""
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

    # -- PENDING view (WHO / WHAT / WHAT'S NEXT) ------------------------------

    def _pending_authority(self, grant: Any):
        """The single ``Authority`` the pending application is best-guessed
        to have gone to, or ``None`` when that can't be narrowed to exactly
        one. See ``_build_pending_view``'s docstring item 1 for why this is
        a fallback (the held-credential view carries no ACDC attributes,
        so the actual jurisdiction chosen at submission time isn't
        recoverable) rather than an exact lookup."""
        authorities = self._egf.authorities(grant.issuer_role, accept_phases=self._accept_phases)
        return authorities[0] if len(authorities) == 1 else None

    @staticmethod
    def _pending_next_steps_text(role: Role, grant: Any, authority: Optional[Any]) -> str:
        """WHAT HAPPENS NEXT copy (item 3) — a fixed sentence template with
        only EGF-sourced names interpolated in: the authority's
        display_name (omitted from the sentence when unresolved — see
        ``_pending_authority``), the grant credential's ``name``, and the
        onboarded role's ``display_name``."""
        if authority is not None:
            reviewer = f"The {authority.display_name} will review your application."
        else:
            reviewer = "Your application will be reviewed."
        return (
            f"{reviewer} When your {grant.name} is granted and accepted, "
            f"the {role.display_name} workspace unlocks here automatically."
        )

    def _pending_application_said(self, grant: Any) -> Optional[str]:
        """The held application credential's own SAID (Task 9's
        ``HeldCredential.said``), sourced from the CURRENT
        ``held_provider()`` snapshot, or ``None`` when it can't be
        resolved. Mirrors ``_held_matches``'s own filter (matching
        ``schema_said``, chain-verified, not revoked) rather than reusing
        it directly, since that helper returns a bool and this needs the
        matching view itself. Returns ``None`` (never raises) when: the
        grant has no ``chained_from`` application credential (shouldn't
        happen once ``derive_state`` has already returned PENDING, but
        defensive regardless); no held view matches; or a matching view
        predates Task 9 and carries no ``said`` attribute at all
        (``getattr`` default, not a hard requirement — back-compat for
        any caller still using the older gate-shaped view)."""
        if grant.chained_from is None:
            return None
        application = self._egf.credential(grant.chained_from)
        for h in self._held_provider():
            if h.schema_said != application.schema_said or not h.chain_verified:
                continue
            if h.state == "revoked":
                continue
            said = getattr(h, "said", None)
            if said:
                return said
        return None

    def _update_pending_view(self, role_id: str) -> None:
        """Populate the PENDING view's EGF-derived pieces (WHO / WHAT'S
        NEXT / the notification hint / the application ID row — see
        ``_build_pending_view``'s docstring) for ``role_id``. Called from
        ``_render`` on every PENDING render (not cached like
        ``_build_form_view``) since ``select_persona``/``refresh`` may
        switch to a different pending role between renders and the work
        here is cheap label updates, not a rebuild. Reachable only once
        ``derive_state`` has already returned PENDING, which guarantees
        ``role.onboarding`` is set (see ``derive_state``'s PENDING
        branch) — no extra None-guard needed here."""
        role = self._egf.role(role_id)
        grant = self._egf.credential(role.onboarding.grant_credential_id)
        authority = self._pending_authority(grant)

        if authority is not None:
            text, badge = self._applying_to_text_for(authority, verb="Submitted to")
            self._pending_authority_text.setText(text)
            self._pending_authority_badge.setText(badge)
            self._pending_authority_row_widget.setVisible(True)
        else:
            # Cleared, not just hidden -- a stale display_name/AID from a
            # previously-resolved role must never linger if this render's
            # role resolves ambiguously (see _pending_authority).
            self._pending_authority_text.setText("")
            self._pending_authority_badge.setText("")
            self._pending_authority_row_widget.setVisible(False)

        self._pending_next_steps_label.setText(
            self._pending_next_steps_text(role, grant, authority)
        )

        application_said = self._pending_application_said(grant)
        if application_said:
            self._pending_application_said_label.setText(f"Application ID: {application_said}")
            self._pending_application_said_label.setVisible(True)
        else:
            # Cleared, not just hidden -- same stale-leftover rationale as
            # the WHO row above.
            self._pending_application_said_label.setText("")
            self._pending_application_said_label.setVisible(False)

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

        # Item 2: a freshly-rendered error (validation OR a request_failed
        # banner) must actually be seen, not just exist below the fold on a
        # long form — scroll the form's QScrollArea (see _build_form_shell)
        # so the newest error row is visible.
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
