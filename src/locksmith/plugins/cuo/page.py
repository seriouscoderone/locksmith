# -*- encoding: utf-8 -*-
"""
locksmith.plugins.cuo.page module — the CUO mandate-declaration surface.

Design §6's form: line of business / jurisdiction / coverages / effective window /
thesis -> the `declare_product_mandate` command, minting a `product_mandate` ACDC.

**Every control and every rule comes from the EGF.** The form asks
`schema_source.load_mandate_schema` what the command's payload looks like and builds
one control per constraint set (`enum` -> a dropdown, `type: array` -> a token list,
`format: date` -> a date field), and it asks `validation.validate_payload` whether a
payload is acceptable. Nothing about the mandate's shape is written here: no enum, no
pattern, not even the country prefix the jurisdiction demands — that is derived from
the field's own pattern (see `_pattern_prefix`).
`tests/plugins/cuo/test_no_schema_literals.py` enforces that, by grepping this
package for schema values; it reads whole files, so a schema value is banned from a
COMMENT here too, not only from code.

**Validation timing is counter-intuitive and deliberate** (`ux-patterns.md:190-192`):
required errors appear on SUBMIT, format errors on blur and only after a first submit
attempt. That is why the primary stays ENABLED while the form is invalid — a disabled
primary would make the submit that reveals the errors unreachable. The primary
disables for exactly one reason: an issuance in flight.

**Nothing is signed before the read-back is confirmed.** `submit()` validates and
opens `MandateReviewDialog`; only the dialog's `confirm` reaches `_anchor`, and only
once — a mandate is immutable, so a second confirmation must not mint a duplicate.

**Untargeted by construction.** Design spec Amendment C §14.6: "CUO HOA declare_mandate
-> iss(vcdig=mandate SAID) + ixn carrying SealEvent(...) -> (no push)". A mandate is
"addressed to nobody and requesting nothing" (the schema's own description, quoting the
ACDC spec's Untargeted Attribute Section) -- consumers find it by watching this
identifier's own KEL, not by being sent it. `issue_credential`'s `recipient=None` is what
makes the ACDC's `a` block carry no `i` (see `keri.vc.proving.credential`: `if recipient
is not None: subject['i'] = recipient`) -- untargeted is the ABSENCE of a recipient
argument, not a separate code path.

**Issuance mechanic.** Follows the SAME retire-listener / `vault.extend` pattern
`RequestFlow._schedule_issue_then_grant` uses (`ui/onboarding/request_flow.py:319`) for
scheduling a `ServiceaidIssueDoer` and picking up its result off the vault's
`doer_event` bus -- BUT WITHOUT the follow-up `ServiceaidGrantDoer` that flow chains:
that doer frames and delivers an IPEX grant to a specific recipient, and a mandate has
none. Do not add one; an untargeted credential has nothing to grant.

Subscribes to the doer's EMITTED source name, which is the LEGACY one --
`"IssueCredentialDoer"`, not `"ServiceaidIssueDoer"`.
`keri_serviceaid.providers.issue_credential` stamps this name onto every
`sink.on_event` call (both the `credential_issued` success path and the
`credential_issuance_failed` except-path -- `keri_serviceaid/providers/issue.py:151`
and `serviceaid_bridge.py:249-258`) so the pre-existing UI vocabulary
(`IssueCredentialDialog._on_doer_event`) keeps working unmodified. A listener
subscribed to the doer CLASS's real name, `ServiceaidIssueDoer`, receives nothing,
silently.

Widget idiom: `LocksmithFormPage` supplies the sticky header, the animated
error/success banners and the scroll area; one bounded 640px column holds a vertical
group per field with the label ABOVE the control (`ux-patterns.md:300` -- "Always
above the field. Never to the left"), which is why this page uses no `QFormLayout`.

Does not compute or display any premium, and renders no rate table -- out of scope
since the parent design; Excel is the rate UI (owner ruling).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any, Callable, Iterable

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from keri import help

from locksmith.core.branding import brand, egf_local_dir
from locksmith.core.serviceaid_bridge import ServiceaidIssueDoer
from locksmith.plugins.cuo import mandate_copy as copy
from locksmith.plugins.cuo.date_field import MandateDateField
from locksmith.plugins.cuo.review_dialog import MandateReviewDialog
from locksmith.plugins.cuo.schema_source import FieldConstraints, load_mandate_schema
from locksmith.plugins.cuo.validation import FieldError, validate_payload
from locksmith.ui import colors
from locksmith.ui.toolkit.widgets.buttons import (
    LocksmithButton,
    LocksmithCopyButton,
    LocksmithInvertedButton,
)
from locksmith.ui.toolkit.widgets.fields import (
    LocksmithLineEdit,
    LocksmithPlainTextEdit,
)
from locksmith.ui.toolkit.widgets.page import LocksmithFormPage
from locksmith.ui.toolkit.widgets.text_list import LocksmithTextListWidget

logger = help.ogler.getLogger(__name__)

# Registry-name convention: registry_name == schema_said (Amendment C §14.1).
# Pin verified against the bundled schema by
# tests/plugins/roles/test_pin_regression.py; the schema's own $id is the
# source of truth (brands/usurance/egf/EFYdgrOvpXpxTkVSVl6dRs1lueELnH9cqxpctqwqpVr5.json).
PRODUCT_MANDATE_SCHEMA_SAID = "EFYdgrOvpXpxTkVSVl6dRs1lueELnH9cqxpctqwqpVr5"

#: devctl's contract. Every control's objectName is `cuoMandatePage.<camelCase>` of
#: its SCHEMA field name, derived rather than tabulated so a new schema field cannot
#: acquire a hand-written name that drifts from it. Today that yields
#: `cuoMandatePage.lineOfBusiness`, `.jurisdiction`, `.coverages`, `.windowOpens`,
#: `.windowCloses`, `.thesis`.
_PAGE_NAME = "cuoMandatePage"

_COLUMN_WIDTH = 640
_THESIS_ROWS = 3
_ICON = ":/assets/material-icons/balance.svg"

#: Shown in `REVIEW_SIGNER` when no identifier can be resolved (a page built without
#: an open vault -- unit tests, and the defensive path). The mandate schema's own
#: `cuo_role` credential carries protocol fields only, so no personal name exists
#: anywhere in the ecosystem to read; the signer is named by their identifier's
#: local alias.
_UNNAMED_SIGNER = "this identifier"

#: The literal characters a `pattern` demands at the start of a value. The second
#: group is whatever follows, so a quantifier that applies to the last literal
#: character (`^ab?c$` -- "b" is optional) can be dropped from the prefix.
_PATTERN_HEAD = re.compile(r"^\^([A-Za-z0-9-]*)(.?)")


def _pattern_prefix(pattern: str | None) -> str:
    """The fixed characters `pattern` requires at the start of a value, or "".

    This is how the jurisdiction field learns what belongs in front of a bare
    subdivision code without that prefix being written in Python. The design's
    rule is that nothing about the mandate's shape lives in this package, and a
    hand-written prefix is a fragment of the field's pattern -- the guard test
    greps for whole regexes, so such a fragment would slip past the guard and
    still be the defect it exists to prevent.

    Returns "" for a pattern that starts with a character class, which is what
    `coverages`' item pattern does -- so coverage codes get case folding and no
    prefix, from the same code path.
    """
    match = _PATTERN_HEAD.match(pattern or "")
    if match is None:
        return ""
    head, follows = match.group(1), match.group(2)
    if head and follows in ("?", "*", "{"):
        head = head[:-1]
    return head


def _pattern_case(pattern: str | None) -> Callable[[str], str]:
    """The case a `pattern` will accept, read off the pattern itself.

    A pattern that admits `A-Z` and not `a-z` accepts upper case only, so a CUO
    who types `ut` or `bi` should have it folded rather than be told to retype it
    in capitals. A pattern that says neither, or both, gets the value untouched --
    guessing there would be the schema-knowledge-in-Python defect again.
    """
    text = pattern or ""
    upper, lower = "A-Z" in text, "a-z" in text
    if upper and not lower:
        return str.upper
    if lower and not upper:
        return str.lower
    return lambda value: value


def _canonical(value: str, pattern: str | None) -> str:
    """`value` in the form its own pattern asks for. Never rejects; that is
    `validate_payload`'s job, and a form that silently repaired an unacceptable
    value would hide the error the read-back exists to show."""
    folded = _pattern_case(pattern)(value.strip())
    prefix = _pattern_case(pattern)(_pattern_prefix(pattern))
    if folded and prefix and not folded.startswith(prefix):
        folded = f"{prefix}{folded}"
    return folded


def _split_tokens(text: str) -> list[str]:
    return [token.strip() for token in text.split(",") if token.strip()]


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part.capitalize() for part in rest)


def _combo_style(invalid: bool) -> str:
    """`LocksmithLineEdit`'s look, on a `QComboBox`. The toolkit's only combo is
    `FloatingLabelComboBox`, whose label animates INSIDE the control -- the layout
    this form is not allowed to use."""
    border = colors.DANGER if invalid else colors.BORDER
    return (
        f"QComboBox {{ border: 1px solid {border}; border-radius: 6px;"
        f" padding: 12px 32px 12px 12px; font-size: 14px;"
        f" color: {colors.TEXT_PRIMARY};"
        f" background-color: {colors.BACKGROUND_CONTENT}; }}"
        f"QComboBox::drop-down {{ subcontrol-origin: padding;"
        f" subcontrol-position: center right; width: 24px; border: none;"
        f" padding-right: 8px; }}"
        f"QComboBox::down-arrow {{ image:"
        f" url(:/assets/material-icons/chevron_down.svg);"
        f" width: 20px; height: 20px; }}"
        f"QComboBox QAbstractItemView {{ border: 1px solid {colors.BORDER};"
        f" background-color: {colors.BACKGROUND_CONTENT};"
        f" selection-background-color: {colors.BACKGROUND_SELECTION};"
        f" color: {colors.TEXT_MENU}; outline: none; }}"
    )


def _paint_toolkit_field(widget: Any, invalid: bool) -> None:
    """Recolour a toolkit field's border so it SURVIVES a focus change.

    `LocksmithLineEdit`, `LocksmithPlainTextEdit` and `FloatingLabelLineEdit` each
    rebuild their whole stylesheet on focus in and focus out, reading
    `_border_color` / `_focused_border_color` as they go. Calling `setStyleSheet`
    on one of them paints a red border that the next click erases -- measured. So
    set the colours it reads, then ask it to repaint.
    """
    from PySide6.QtGui import QColor

    edge = QColor(colors.DANGER if invalid else colors.BORDER_NEUTRAL)
    focused = QColor(colors.DANGER if invalid else colors.PRIMARY)
    widget._border_color = edge
    widget._focused_border_color = focused
    for repaint in ("_update_styling", "reset_style"):
        method = getattr(widget, repaint, None)
        if callable(method):
            method()
            return
    update_border = getattr(widget, "_update_border_color", None)
    if callable(update_border):
        update_border(bool(getattr(widget, "_is_focused", False)))


@dataclass
class _Control:
    """One schema field's widget, and every operation the page performs on it.

    Deliberately a record of callables rather than a family of `isinstance`
    branches: `build_payload`, `set_field`, `blur_field`, `reset_form` and the
    error painting are then all written ONCE, generically, and adding a control
    type means filling this record in one place instead of extending five branch
    lists that each silently ignore the type they were not taught about.
    """

    name: str
    widget: QWidget
    focus_widget: QWidget
    error: QLabel
    read: Callable[[], Any]
    write: Callable[[Any], None]
    clear: Callable[[], None]
    paint: Callable[[bool], None]
    flush: Callable[[], None]
    changed: tuple = dc_field(default_factory=tuple)


class CuoMandatePage(LocksmithFormPage):
    """The CUO's mandate-declaration surface.

    Args:
        app: the `LocksmithApplication` (needed at submit time for
            `app.vault`); `None` is accepted so the class stays constructible
            in isolation (e.g. a stray `CuoMandatePage()`), but `submit()`
            surfaces a clear error rather than crashing when there is none.
    """

    def __init__(self, app: Any = None, parent=None):
        super().__init__(title=copy.H1, icon_path=_ICON, parent=parent)
        self._app = app
        self._pending_listener = None  # the still-connected _on_issue_event, or None
        self._submitted = False        # has the CUO attempted a submit yet?
        self._anchoring = False        # one-shot guard: an anchor is under way
        self._committing_tokens = False
        self.review_dialog: MandateReviewDialog | None = None
        self._controls: dict[str, _Control] = {}

        self.setObjectName(_PAGE_NAME)
        # The base's banner is the page's error surface; keep the objectName the
        # devctl contract has always used, on the label that carries the text.
        self.error_label.setObjectName(f"{_PAGE_NAME}.errorBanner")

        self._schema = self._load_schema()
        unrendered = set(self._schema.fields) - set(copy.FIELD_ORDER)
        if unrendered:
            # Loud, not silent: a schema field with no control would be dropped
            # from every payload this form builds, and the mint would reject it
            # with a message the CUO cannot act on.
            raise RuntimeError(
                f"the mandate schema declares {sorted(unrendered)}, which "
                f"mandate_copy.FIELD_ORDER does not render")

        column = QWidget()
        column.setMaximumWidth(_COLUMN_WIDTH)
        body = QVBoxLayout(column)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(20)

        for paragraph in copy.PAGE_INTRO:
            intro = QLabel(paragraph)
            intro.setWordWrap(True)
            intro.setStyleSheet(
                f"color: {colors.TEXT_SECONDARY}; font-size: 13px;")
            body.addWidget(intro)

        body.addWidget(self._build_declared_banner())

        pending_row: list[QWidget] = []
        for name in copy.FIELD_ORDER:
            constraints = self._schema.fields.get(name)
            if constraints is None:
                continue
            group = self._build_group(constraints)
            # One decision, two controls: the window's ends share a row.
            if constraints.fmt == "date":
                pending_row.append(group)
                if len(pending_row) < 2:
                    continue
                row = QWidget()
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(16)
                for member in pending_row:
                    row_layout.addWidget(member, 1)
                pending_row = []
                body.addWidget(row)
                continue
            body.addWidget(group)
        for orphan in pending_row:            # an odd number of date fields
            body.addWidget(orphan)

        body.addWidget(self._build_footer())

        self.content_layout.addWidget(column, 0, Qt.AlignmentFlag.AlignLeft)
        self.content_layout.addStretch(1)

        for control in self._controls.values():
            for signal in control.changed:
                signal.connect(
                    lambda *_args, name=control.name: self._on_edited(name))
            control.focus_widget.installEventFilter(self)

    # -- construction -----------------------------------------------------------

    def _load_schema(self):
        """The payload schema, from the active brand's bundled EGF.

        Raises rather than degrading. A form that cannot read its constraints
        would accept anything and let the issuer reject it -- the loop this page
        was rebuilt to remove (see `schema_source`'s module docstring)."""
        egf_dir = egf_local_dir()
        if egf_dir is None:
            raise RuntimeError(
                "no bundled EGF directory for this brand — the mandate form "
                "cannot read the constraints it must enforce")
        return load_mandate_schema(Path(egf_dir))

    def _build_declared_banner(self) -> QWidget:
        """The success surface: the FULL SAID, plus a copy affordance.

        Its own visibility is what a caller synchronizes on (`wait_for
        cuoMandatePage.declaredBanner condition=visible`), so it must be a widget
        that is genuinely hidden until a mandate exists -- mirrors
        `ProductDesignerPage.bundleSaid`. `LocksmithFormPage`'s animated success
        banner is NOT used for this: it collapses to zero height without hiding,
        so `isVisible()` stays true and that wait would return before anything
        was declared.
        """
        self._declared_row = QWidget()
        row = QHBoxLayout(self._declared_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self._declared = QLabel("")
        self._declared.setObjectName(f"{_PAGE_NAME}.declaredBanner")
        self._declared.setWordWrap(True)
        self._declared.setTextFormat(Qt.TextFormat.PlainText)
        self._declared.setStyleSheet(
            f"color: {colors.SUCCESS_TEXT};"
            f" background-color: {colors.BACKGROUND_SUCCESS};"
            f" border-radius: 6px; padding: 8px 12px; font-size: 13px;")
        row.addWidget(self._declared, 1)

        self._declared_copy = LocksmithCopyButton(
            tooltip="Copy the mandate SAID", icon_size=18,
            icon_color=colors.SUCCESS_TEXT)
        self._declared_copy.setObjectName(f"{_PAGE_NAME}.declaredBannerCopy")
        row.addWidget(self._declared_copy)

        self._declared_row.setVisible(False)
        return self._declared_row

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(0, 0, 0, 0)

        self._cancel = LocksmithInvertedButton(copy.FORM_CANCEL)
        self._cancel.setObjectName(f"{_PAGE_NAME}.cancel")
        self._cancel.setFixedHeight(36)
        self._cancel.clicked.connect(self.reset_form)
        layout.addWidget(self._cancel)
        layout.addStretch(1)

        self._submit = LocksmithButton(copy.FORM_PRIMARY)
        self._submit.setObjectName(f"{_PAGE_NAME}.submit")
        self._submit.setFixedHeight(36)
        # Enabled while the form is invalid, on purpose: required errors appear on
        # submit, so a disabled primary would make them unreachable. The ONE
        # reason it disables is an issuance in flight (`_enter_flight`).
        self._submit.setEnabled(True)
        self._submit.clicked.connect(self.submit)
        layout.addWidget(self._submit)
        return footer

    def _build_group(self, constraints: FieldConstraints) -> QWidget:
        """One field: label above, control, help beneath, error beneath that."""
        name = constraints.name
        group = QWidget()
        layout = QVBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        label = QLabel(copy.FIELD_LABEL[name] + (" *" if constraints.required else ""))
        label.setStyleSheet(
            f"color: {colors.TEXT_PRIMARY}; font-size: 14px; font-weight: 500;")
        if constraints.required:
            # The asterisk's tooltip is the field's own required message rather
            # than a generic "this field is required" -- it is already ratified
            # copy, and it names the next action.
            label.setToolTip(copy.required_error(name))
        layout.addWidget(label)

        error = QLabel("")
        error.setObjectName(f"{_PAGE_NAME}.{_camel(name)}Error")
        error.setWordWrap(True)
        error.setVisible(False)
        error.setStyleSheet(f"color: {colors.DANGER}; font-size: 12px;")

        control = self._build_control(constraints, error)
        self._controls[name] = control
        layout.addWidget(control.widget)

        help_text = QLabel(copy.FIELD_HELP[name])
        help_text.setWordWrap(True)
        help_text.setStyleSheet(
            f"color: {colors.TEXT_SECONDARY}; font-size: 12px;")
        layout.addWidget(help_text)
        layout.addWidget(error)
        return group

    def _build_control(self, constraints: FieldConstraints,
                       error: QLabel) -> _Control:
        """The control this field's CONSTRAINTS call for -- never its name.

        A closed `enum` is a dropdown, an array is a token list, `format: date` is
        a date field, and free prose (a string the schema constrains neither by
        pattern, enum nor format) gets a multi-line box. Reading the constraints
        rather than matching on `thesis`/`jurisdiction` is what makes the form
        survive a renamed field.
        """
        name = constraints.name
        object_name = f"{_PAGE_NAME}.{_camel(name)}"
        placeholder = copy.FIELD_PLACEHOLDER[name]

        if constraints.enum:
            combo = QComboBox()
            combo.setObjectName(object_name)
            # `setPlaceholderText` BEFORE the items, and no prompt row: Qt then
            # leaves currentIndex at -1 by itself, and the item count stays equal
            # to the enum's. A prompt inserted as item 0 would be selectable and
            # would make the control claim one more option than the schema has.
            combo.setPlaceholderText(placeholder)
            combo.addItems(list(constraints.enum))
            combo.setCurrentIndex(-1)
            combo.setMinimumHeight(50)
            combo.setStyleSheet(_combo_style(False))

            def write_combo(value: Any) -> None:
                # MatchFixedString is an exact, case-INSENSITIVE compare, so a
                # differently-cased spelling of a member still selects it. A
                # value the enum does not contain yields -1: no selection,
                # which is the honest state.
                combo.setCurrentIndex(combo.findText(
                    str(value or ""), Qt.MatchFlag.MatchFixedString))

            return _Control(
                name=name, widget=combo, focus_widget=combo, error=error,
                # An enum control can only emit a member of the enum, verbatim.
                # That is the whole reason it is a dropdown: there is nothing to
                # canonicalize, and no case rule to guess.
                read=lambda: combo.currentText().strip(),
                write=write_combo,
                clear=lambda: combo.setCurrentIndex(-1),
                paint=lambda invalid: combo.setStyleSheet(_combo_style(invalid)),
                flush=lambda: None,
                changed=(combo.currentIndexChanged,),
            )

        if constraints.type == "array":
            listing = LocksmithTextListWidget(label=placeholder, max_height=120)
            listing.setObjectName(f"{object_name}List")
            # The objectName rides on the INPUT, not the container: the container
            # has no setText, so devctl's `type` cannot drive it, and typing is
            # how the integration harness fills this field.
            listing.text_input.setObjectName(object_name)
            line = listing.text_input.line_edit
            item_pattern = constraints.item_pattern

            def read_tokens() -> list[str]:
                # Committed chips PLUS whatever is still in the input box. A
                # token the CUO typed but did not commit is not silently dropped
                # from a permanent record; `submit` commits it first so the
                # screen and the payload agree.
                raw = list(listing.get_items()) + _split_tokens(
                    listing.text_input.text())
                return [_canonical(token, item_pattern) for token in raw
                        if token.strip()]

            def write_tokens(value: Any) -> None:
                items = (_split_tokens(value) if isinstance(value, str)
                         else [str(item) for item in (value or ())])
                self._commit_tokens(listing, items, tail="")

            def commit_typed(text: str) -> None:
                if self._committing_tokens or "," not in text:
                    return
                head, _, tail = text.rpartition(",")
                self._commit_tokens(listing, _split_tokens(head),
                                    tail=tail.strip())

            def flush_typed() -> None:
                pending = listing.text_input.text()
                if not pending.strip():
                    return
                self._commit_tokens(listing, _split_tokens(pending), tail="")

            line.textChanged.connect(commit_typed)
            return _Control(
                name=name, widget=listing, focus_widget=line, error=error,
                read=read_tokens, write=write_tokens,
                clear=lambda: self._commit_tokens(listing, [], tail=""),
                paint=lambda invalid: _paint_toolkit_field(
                    listing.text_input, invalid),
                flush=flush_typed,
                changed=(listing.itemsChanged, line.textChanged),
            )

        if constraints.fmt == "date":
            date = MandateDateField(placeholder=placeholder)
            date.setObjectName(f"{object_name}Field")
            # `QDateEdit` has no setText, so the name goes on its internal line
            # edit -- writing that field's text really does move the date
            # (measured on PySide6 6.10.3), which keeps the control drivable.
            inner = date.findChild(QLineEdit)
            if inner is not None:
                inner.setObjectName(object_name)
            return _Control(
                name=name, widget=date, focus_widget=inner or date, error=error,
                read=date.iso_value, write=date.set_iso, clear=date.clear,
                paint=date.set_invalid, flush=lambda: None,
                changed=(date.changed,),
            )

        if (constraints.type == "string" and not constraints.pattern
                and not constraints.fmt):
            prose = LocksmithPlainTextEdit(placeholder_text=placeholder)
            prose.setObjectName(object_name)
            metrics = prose.fontMetrics()
            prose.setFixedHeight(_THESIS_ROWS * metrics.lineSpacing() + 28)
            return _Control(
                name=name, widget=prose, focus_widget=prose, error=error,
                read=lambda: prose.toPlainText().strip(),
                write=lambda value: prose.setPlainText(str(value or "")),
                clear=prose.clear,
                paint=lambda invalid: _paint_toolkit_field(prose, invalid),
                flush=lambda: None,
                changed=(prose.textChanged,),
            )

        edit = LocksmithLineEdit(placeholder_text=placeholder)
        edit.setObjectName(object_name)
        pattern = constraints.pattern
        return _Control(
            name=name, widget=edit, focus_widget=edit, error=error,
            read=lambda: _canonical(edit.text(), pattern),
            write=lambda value: edit.setText(str(value or "")),
            clear=edit.clear,
            paint=lambda invalid: _paint_toolkit_field(edit, invalid),
            flush=lambda: None,
            changed=(edit.textChanged,),
        )

    def _commit_tokens(self, listing: LocksmithTextListWidget,
                       tokens: Iterable[str], *, tail: str) -> None:
        """Turn `tokens` into committed chips and leave `tail` in the input.

        `LocksmithTextListWidget` commits on Enter or the add button and knows
        nothing about commas -- measured, and the reason this exists: the
        integration harness fills this field by typing `BI,PD` in one write, and
        a form that swallowed `PD` would publish half a mandate.
        """
        if self._committing_tokens:
            return
        self._committing_tokens = True
        try:
            items = list(listing.get_items())
            for token in tokens:
                if token and token not in items:
                    items.append(token)
            listing.set_items(items)
            listing.text_input.setText(tail)
        finally:
            self._committing_tokens = False

    # -- public control API (tests and devctl drive the same methods) -----------

    def _control(self, name: str) -> _Control:
        try:
            return self._controls[name]
        except KeyError:
            raise KeyError(
                f"{name!r} is not a field on this form; "
                f"have {sorted(self._controls)}") from None

    def set_field(self, name: str, value: Any) -> None:
        """Put `value` into the named field, as a user's edit would."""
        self._control(name).write(value)

    def blur_field(self, name: str) -> None:
        """The named field lost focus.

        Format errors appear here and ONLY after a first submit attempt
        (`ux-patterns.md:190-191`), so nothing is painted before then. Re-runs
        the one validator and keeps only this field's messages -- the page owns
        no rules of its own.
        """
        control = self._control(name)
        if not self._submitted:
            return
        errors = validate_payload(self.build_payload(), self._schema,
                                 self.existing_mandates())
        self._set_field_error(control, [error for error in errors
                                        if error.field == name])

    def field_error(self, name: str) -> str:
        """What the named field is currently telling the CUO. "" when clean."""
        return self._control(name).error.text()

    def reset_form(self, *_qt_args) -> None:
        """Empty the form and forget that a submit was attempted."""
        for control in self._controls.values():
            control.clear()
            self._set_field_error(control, ())
        self._submitted = False
        self.clear_error()
        self._clear_declared()

    # -- payload ----------------------------------------------------------------

    def build_payload(self) -> dict:
        """The `declare_product_mandate` payload this form currently describes.

        Canonical, not raw: each control returns the value in the form its own
        constraints ask for (a dropdown returns an enum member verbatim, a date
        returns ISO, a patterned string is case-folded and prefixed per
        `_canonical`, coverage tokens likewise). The read-back dialog shows THIS,
        because it is what gets signed.

        Key order follows `copy.FIELD_ORDER`, which is also the order the ACDC's
        attribute block is serialized in.
        """
        return {name: control.read() for name, control in self._controls.items()}

    def existing_mandates(self) -> list[dict]:
        """The mandates this vault already holds, for the overlap gate.

        Advisory by construction: the local view can be incomplete, and the
        ledger's own `mandate_scopes_do_not_overlap` invariant is the real
        enforcement. Mirrors how ProductDesignerPage enumerates attestations.
        """
        vault = getattr(self._app, "vault", None)
        if vault is None:
            return []
        out = []
        try:
            reger = vault.rgy.reger
            for saider in reger.schms.get(keys=(PRODUCT_MANDATE_SCHEMA_SAID,)):
                creder = reger.creds.get(keys=(saider.qb64,))
                if creder is None:
                    continue
                attrs = creder.sad.get("a") or {}
                if isinstance(attrs, dict):
                    out.append(attrs)
        except Exception:                   # noqa: BLE001 -- advisory only
            logger.debug("cuo.existing_mandates_unreadable", exc_info=True)
        return out

    # -- lifecycle ---------------------------------------------------------------

    def eventFilter(self, obj, event):
        """Blur handling, on top of the base's error-banner hover filter."""
        if event.type() == QEvent.Type.FocusOut:
            for control in self._controls.values():
                if control.focus_widget is obj:
                    self.blur_field(control.name)
                    break
        return super().eventFilter(obj, event)

    def _on_edited(self, name: str) -> None:
        """Any edit clears that field's error and any stale success."""
        self._set_field_error(self._controls[name], ())
        self._clear_declared()

    def _set_field_error(self, control: _Control,
                         errors: Iterable[FieldError]) -> None:
        message = " ".join(error.message for error in errors)
        control.error.setText(message)
        control.error.setVisible(bool(message))
        control.paint(bool(message))

    def submit(self, *_qt_args) -> None:
        """Validate, then show the read-back. Signs nothing.

        Required errors surface here, all of them at once, with a counted banner
        and focus on the first invalid control (`ux-patterns.md:192`). A clean
        payload opens `MandateReviewDialog`; only its confirmation reaches
        `_anchor`.
        """
        for control in self._controls.values():
            control.flush()
        self.clear_error()
        self._clear_declared()
        self._submitted = True

        payload = self.build_payload()
        errors = validate_payload(payload, self._schema, self.existing_mandates())
        by_field: dict[str, list[FieldError]] = {}
        for error in errors:
            by_field.setdefault(error.field, []).append(error)
        for name, control in self._controls.items():
            self._set_field_error(control, by_field.get(name, ()))

        if errors:
            self.show_error(copy.error_summary(len(errors)))
            first = self._controls.get(errors[0].field)
            if first is not None:
                first.focus_widget.setFocus()
                self.scroll_area.ensureWidgetVisible(first.widget)
            return

        dialog = MandateReviewDialog(payload, signer_name=self._signer_name(),
                                     parent=self)
        self.review_dialog = dialog
        # Connected ONCE, and guarded on the page side as well: the dialog
        # disables its own primary after a click, but nothing stops a second
        # emission from another path, and a duplicate mandate is immutable.
        dialog.confirm.connect(lambda: self._confirm_review(payload))
        dialog.open()

    def _confirm_review(self, payload: dict) -> None:
        if self._anchoring:
            return
        self._anchoring = True
        self._enter_flight()
        self._anchor(payload)

    def _signer_name(self) -> str:
        """Who the read-back says is signing.

        The `cuo_role` credential carries protocol fields only (`d`, `i`, `dt`) --
        there is no personal name anywhere in the ecosystem to read -- so the
        signer is named by their identifier's local alias, falling back to its
        prefix.
        """
        try:
            hab = self._cuo_hab()
        except Exception:                   # noqa: BLE001 -- no vault, no name
            hab = None
        if hab is None:
            return _UNNAMED_SIGNER
        return getattr(hab, "name", None) or getattr(hab, "pre", None) or (
            _UNNAMED_SIGNER)

    def _enter_flight(self) -> None:
        self._submit.setEnabled(False)
        self._submit.setText(copy.IN_FLIGHT)

    def _leave_flight(self) -> None:
        self._submit.setEnabled(True)
        self._submit.setText(copy.FORM_PRIMARY)

    def _close_review(self) -> None:
        dialog, self.review_dialog = self.review_dialog, None
        if dialog is None:
            return
        try:
            dialog.close()
        except RuntimeError:                # already destroyed by Qt
            pass

    def _clear_declared(self) -> None:
        self._declared.setText("")
        self._declared_copy.set_copy_content("")
        self._declared_row.setVisible(False)

    # -- identifier resolution --------------------------------------------------

    def _cuo_hab(self):
        """The identifier that declares this mandate: whichever local hab
        holds this vault's `cuo_role` credential (the same fact the plugin's
        own gate reveals this page on), falling back to the brand's default
        onboarding identifier when none is found (defensive; the gate should
        already guarantee one exists by the time this page is visible at
        all)."""
        from locksmith.plugins.cuo.plugin import CUO_ROLE_SCHEMA_SAID

        vault = self._app.vault
        hby = vault.hby
        reger = vault.rgy.reger
        for pre, hab in hby.habs.items():
            for saider in reger.subjs.get(keys=(pre,)):
                creder = reger.creds.get(keys=(saider.qb64,))
                if creder is not None and creder.schema == CUO_ROLE_SCHEMA_SAID:
                    return hab
        alias = brand().default_aid_alias or "default"
        return hby.habByName(alias)

    def _ensure_mandate_schema_pinned(self, hby) -> None:
        """Pin `product_mandate`'s schema into `hby.db.schema` if it is not
        there already. `Credentialer.validate` (called from `create()`)
        resolves the schema on the ISSUING side too — the same requirement
        the role-gate credentials already satisfy via the EGF bundle; this
        mandate schema is bundled the same way
        (`brands/usurance/egf/<said>.json`), just not needed by any GATE, so
        nothing else in the boot sequence pins it ahead of time."""
        from keri.core import scheming
        from keri.kering import Kinds

        if hby.db.schema.get(keys=(PRODUCT_MANDATE_SCHEMA_SAID,)) is not None:
            return
        egf_dir = egf_local_dir()
        if egf_dir is None:
            raise RuntimeError(
                "no bundled EGF directory for this brand — cannot resolve "
                "the mandate schema")
        schema_path = egf_dir / f"{PRODUCT_MANDATE_SCHEMA_SAID}.json"
        if not schema_path.is_file():
            raise RuntimeError(
                f"mandate schema not bundled at {schema_path}")
        sad = json.loads(schema_path.read_text())
        schemer = scheming.Schemer(sed=sad, kind=Kinds.json)
        if schemer.said != PRODUCT_MANDATE_SCHEMA_SAID:
            raise RuntimeError("bundled mandate schema does not verify")
        hby.db.schema.pin(keys=(schemer.said,), val=schemer)

    # -- anchoring / issuance ------------------------------------------------------

    def _anchor(self, payload: dict) -> None:
        """Issue the `product_mandate` ACDC the read-back was confirmed for. See
        the module docstring for the issuance mechanic and why there is no
        grant step."""
        if self._app is None or getattr(self._app, "vault", None) is None:
            self._fail_anchor("No open vault — cannot declare a mandate.")
            return

        vault = self._app.vault
        hab = self._cuo_hab()
        if hab is None:
            self._fail_anchor("No identifier available to declare a mandate from.")
            return

        try:
            self._ensure_mandate_schema_pinned(vault.hby)
            from keri_serviceaid.providers.issue import ensure_registry
            ensure_registry(vault.hby, hab, vault.rgy,
                            name=PRODUCT_MANDATE_SCHEMA_SAID)
        except Exception as exc:                        # noqa: BLE001
            logger.exception("cuo.mandate.prepare_failed")
            self._fail_anchor(f"Could not prepare to declare the mandate: {exc}")
            return

        signals = vault.signals
        schema_said = PRODUCT_MANDATE_SCHEMA_SAID

        stale = self._pending_listener
        if stale is not None:
            signals.doer_event.disconnect(stale)
            self._pending_listener = None

        def _on_issue_event(doer_name: str, event_type: str, data: dict) -> None:
            if doer_name != "IssueCredentialDoer" or data.get("schema_said") != schema_said:
                return
            if event_type == "credential_issuance_failed":
                self._retire_listener(_on_issue_event)
                self._fail_anchor(data.get("error", "Mandate declaration failed."))
                return
            if event_type != "credential_issued":
                return
            self._retire_listener(_on_issue_event)
            self._show_declared(data.get("said", ""))

        self._pending_listener = _on_issue_event
        signals.doer_event.connect(_on_issue_event)

        issue_doer = ServiceaidIssueDoer(
            self._app,
            schema_said=schema_said,
            recipient=None,             # untargeted — see module docstring
            attributes=payload,
            registry_name=schema_said,
        )
        vault.extend([issue_doer])

    def _retire_listener(self, listener) -> None:
        signals = self._app.vault.signals
        signals.doer_event.disconnect(listener)
        if self._pending_listener is listener:
            self._pending_listener = None

    def _fail_anchor(self, message: str) -> None:
        """The mint refused, or could not be attempted. The modal closes, the
        typed values survive, and the form is editable again (design §4.3)."""
        self._anchoring = False
        self._leave_flight()
        self._close_review()
        self.show_error(message)

    def show_declared(self, said: str) -> None:
        """Report a declared mandate.

        Delegates to `_show_declared`, which the roles integration bootstrap
        wraps at the CLASS level (`tests/integration/roles/_bootstrap/
        sitecustomize.py:315`) to export the delivery artifact. Every
        declaration must pass through that method, so this is a thin front
        door, not a second implementation.
        """
        self._show_declared(said)

    def _show_declared(self, said: str) -> None:
        self._anchoring = False
        self._leave_flight()
        self._close_review()
        self._declared.setText(
            f"Mandate declared. {said}" if said else "Mandate declared.")
        self._declared_copy.set_copy_content(said)
        self._declared_row.setVisible(True)
