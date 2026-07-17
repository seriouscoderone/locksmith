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
EGF document to decide which of PICKER/FORM/PENDING/LICENSED to show.
Precedence is LICENSED > PENDING > FORM > PICKER:

- LICENSED — a held, chain-verified, ``state == "active"`` credential
  whose schema matches ANY onboardable role's grant credential
  (``egf.credential(role.onboarding.grant_credential_id).schema_said``).
  Checked independent of the chosen ``role_id`` (a returning, already-
  licensed holder should land here even before picking a persona card).
  A REVOKED grant does not count — it simply fails this check and falls
  through to the next precedence level.
- PENDING — the chosen role's application credential (the credential the
  grant chains FROM: ``credential(grant.chained_from)``) is held and
  chain-verified (and not itself revoked). Requires a chosen ``role_id``
  (there is no single, role-agnostic "application" credential to check).
- FORM — a ``role_id`` has been chosen and neither of the above applied.
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
    """The onboarding home page's four possible views."""

    PICKER = "picker"
    FORM = "form"
    PENDING = "pending"
    LICENSED = "licensed"


_KIND_GLYPHS = {
    "organization": "\U0001F3E2",  # office building
    "government": "\U0001F3DB",  # classical building
    "individual": "\U0001F464",  # bust silhouette
}
_DEFAULT_GLYPH = "●"  # bullet, used for any unrecognized `kind`


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


def derive_state(held: list, egf: EgfDocument, role_id: Optional[str]) -> OnboardingState:
    """Pure state derivation — no Qt, no I/O. See module docstring for the
    full precedence rationale (LICENSED > PENDING > FORM > PICKER)."""
    # LICENSED: checked against EVERY onboardable role's grant credential,
    # regardless of role_id — a returning, already-licensed holder should
    # be recognized even before picking a persona card.
    for persona in egf.personas():
        grant = egf.credential(persona.onboarding.grant_credential_id)
        if _held_matches(held, grant.schema_said, require_active=True):
            return OnboardingState.LICENSED

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
        self._shared_dims: List[str] = []
        self._built_form_role_id: Optional[str] = None
        self._persona_cards: List[PersonaCard] = []
        self._error_labels: List[QLabel] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._stack = QStackedWidget(self)
        outer.addWidget(self._stack)

        self._picker_widget = self._build_picker_view()
        self._pending_widget = self._build_message_view(
            "Application pending", "Your application has been submitted and is awaiting approval."
        )
        self._licensed_widget = self._build_message_view(
            "You're all set", "A valid license was found in your vault."
        )
        self._form_container, self._form_layout, self._error_layout = self._build_form_shell()

        self._stack.addWidget(self._picker_widget)
        self._stack.addWidget(self._pending_widget)
        self._stack.addWidget(self._licensed_widget)
        self._stack.addWidget(self._form_container)

        self.refresh()

    # -- construction: static views ---------------------------------------

    def _build_picker_view(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
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

    def _build_form_shell(self):
        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(48, 48, 48, 48)
        outer.setSpacing(16)

        form_layout = QVBoxLayout()
        outer.addLayout(form_layout)

        error_layout = QVBoxLayout()
        outer.addLayout(error_layout)

        submit_btn = LocksmithButton("Submit")
        submit_btn.setObjectName("onboarding.submitButton")
        submit_btn.clicked.connect(self.submit)
        outer.addWidget(submit_btn)
        outer.addStretch(1)

        return container, form_layout, error_layout

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

    def _render(self) -> None:
        if self.state is OnboardingState.PICKER:
            self._stack.setCurrentWidget(self._picker_widget)
        elif self.state is OnboardingState.PENDING:
            self._stack.setCurrentWidget(self._pending_widget)
        elif self.state is OnboardingState.LICENSED:
            self._stack.setCurrentWidget(self._licensed_widget)
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
        self._shared_dims = []

        grant = self._egf.credential(role.onboarding.grant_credential_id)
        issuer_role = grant.issuer_role
        dims = self._egf.context_dimensions(issuer_role)
        if not dims:
            return

        properties = (payload_schema or {}).get("properties", {}) or {}
        authorities = self._egf.authorities(issuer_role, accept_phases=self._accept_phases)

        context_group = None
        context_form = None

        for dim in dims:
            if dim.id in properties:
                # ONE control serves both — the form's own rendered field
                # for this property IS the context control. No duplicate
                # widget is created; submit() mirrors its value into the
                # context dict.
                self._shared_dims.append(dim.id)
                continue

            if context_group is None:
                # Built lazily: skip entirely when every dimension for
                # this role turns out to be shared with a payload field.
                context_group = QGroupBox("Issuing authority")
                context_form = QFormLayout(context_group)

            options = self._dedup_context_options(authorities, dim.id)
            combo = QComboBox()
            combo.setObjectName(f"onboarding.context.{dim.id}")
            if dim.prompt:
                combo.setToolTip(dim.prompt)
            for raw_value, display_text in options:
                combo.addItem(display_text, raw_value)
            combo.setCurrentIndex(-1)
            self._context_widgets[dim.id] = combo
            self._context_prompts[dim.id] = dim.prompt or dim.id
            context_form.addRow(dim.prompt or dim.id, combo)

        if context_group is not None:
            self._form_layout.addWidget(context_group)

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
        """Validate the current form AND the dedicated context combos;
        if clean, call ``on_submit`` with the role id, the payload dict,
        and the context dict (shared dimensions mirrored from the payload;
        dedicated context combos read via their stored raw
        ``currentData()``).

        Dedicated combos are outside ``SchemaFormBuilder``'s schema, so
        ``form.validate()`` knows nothing about them — they are validated
        here (an unselected combo blocks submission with an inline error
        named after the dimension's prompt), never passed through as a
        ``None`` context value."""
        self._clear_form_errors()
        errors = self.form.validate()
        for dim_id, combo in self._context_widgets.items():
            if combo.currentIndex() == -1:
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
            label.setStyleSheet(f"color: {colors.DANGER};")
            self._error_layout.addWidget(label)
            self._error_labels.append(label)

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
