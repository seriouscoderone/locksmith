# -*- encoding: utf-8 -*-
"""The read-back shown between filling the form and anchoring the credential.

`ux-patterns.md:439` makes a confirmation modal the platform's irreversibility
pattern, carrying "This cannot be undone" -- literally true here.

It renders the CANONICAL payload, never the raw field text, because the payload
builder rewrites input and the difference is exactly what a reader needs to see. It
holds no rules: whatever it is handed, it shows.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from locksmith.plugins.cuo import mandate_copy as copy
from locksmith.ui import colors
from locksmith.ui.toolkit.widgets.buttons import (
    LocksmithButton,
    LocksmithInvertedButton,
)
from locksmith.ui.toolkit.widgets.dialogs import LocksmithDialog

_ROWS = ("line_of_business", "jurisdiction", "coverages")


def _row(label: str, value: str) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 3, 0, 3)
    name = QLabel(label)
    name.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 14px;")
    name.setFixedWidth(150)
    shown = QLabel(value)
    shown.setWordWrap(True)
    # Defensive, not reactive: today's schema patterns for these fields exclude
    # '<' and '>', but this module owns no rules and must not depend on another
    # layer's patterns holding. Force plain text so a value can never render as
    # markup regardless of what upstream validation does or stops doing.
    shown.setTextFormat(Qt.TextFormat.PlainText)
    shown.setStyleSheet(f"color: {colors.TEXT_PRIMARY}; font-size: 14px;")
    layout.addWidget(name)
    layout.addWidget(shown, 1)
    return row


class MandateReviewDialog(LocksmithDialog):
    """Read back the canonical payload; confirm or go back."""

    confirm = Signal()

    def __init__(self, payload: dict, signer_name: str, parent=None):
        self._confirmed = False
        self._finished = False

        body = QWidget()
        outer = QVBoxLayout(body)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        signer = QLabel(copy.REVIEW_SIGNER.format(cuo_name=signer_name))
        signer.setObjectName("mandateReviewDialog.signer")
        signer.setWordWrap(True)
        signer.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 13px;")
        outer.addWidget(signer)

        summary = QWidget()
        summary.setObjectName("mandateReviewDialog.summary")
        rows = QVBoxLayout(summary)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(0)
        for field in _ROWS:
            value = payload.get(field)
            shown = ", ".join(value) if isinstance(value, list) else str(value or "")
            rows.addWidget(_row(copy.FIELD_LABEL[field], shown))
        # ISO on purpose -- see the module docstring.
        rows.addWidget(_row(copy.REVIEW_IN_FORCE_LABEL, (
            f"{payload.get('window_opens', '')} through "
            f"{payload.get('window_closes', '')}, inclusive")))
        outer.addWidget(summary)

        thesis_label = QLabel(copy.REVIEW_THESIS_LABEL)
        thesis_label.setStyleSheet(
            f"color: {colors.TEXT_SECONDARY}; font-size: 13px;")
        outer.addWidget(thesis_label)
        thesis = QLabel(str(payload.get("thesis") or ""))
        thesis.setObjectName("mandateReviewDialog.thesis")
        thesis.setWordWrap(True)
        # CRITICAL: the thesis is free, unpatterned prose -- the one field most
        # likely to contain '<', '>' or '&'. Left at Qt's default AutoText, a
        # thesis that happens to look like markup renders AS markup: tags vanish
        # and the text restyles, so the CUO would sign a string they cannot see.
        # This dialog's entire reason for existing is showing what will be
        # signed, so this must be plain text, unconditionally.
        thesis.setTextFormat(Qt.TextFormat.PlainText)
        thesis.setStyleSheet(
            f"color: {colors.TEXT_PRIMARY}; font-size: 15px; padding: 10px 12px;"
            f" background: {colors.BACKGROUND_HIGHLIGHT}; border-radius: 4px;")
        outer.addWidget(thesis)

        caution = QLabel(copy.REVIEW_CAUTION)
        caution.setObjectName("mandateReviewDialog.caution")
        caution.setWordWrap(True)
        caution.setStyleSheet(
            f"color: {colors.WARNING_TEXT}; background: {colors.BACKGROUND_HIGHLIGHT};"
            f" border-radius: 4px; padding: 10px 12px; font-size: 13px;")
        outer.addWidget(caution)

        buttons = QHBoxLayout()
        self._back = LocksmithInvertedButton(copy.REVIEW_BACK)
        self._back.setObjectName("mandateReviewDialog.back")
        self._confirm_button = LocksmithButton(copy.REVIEW_CONFIRM)
        self._confirm_button.setObjectName("mandateReviewDialog.confirm")
        buttons.addWidget(self._back)
        buttons.addStretch(1)
        buttons.addWidget(self._confirm_button)

        # No header X. A confirmation modal has exactly two answers and both are
        # buttons; a third, unlabelled way out of the last screen before an
        # irreversible act is not an affordance, it is an accident waiting for a
        # mis-aimed click. It is also the one exit `_on_confirm` cannot disable.
        super().__init__(parent=parent, title=copy.REVIEW_TITLE,
                         content=body, buttons=buttons,
                         show_close_button=False)
        self.setObjectName("mandateReviewDialog")

        # `close()`, not `reject()`. `LocksmithDialog` now releases its class-level
        # `_current_dialog` on every exit path, so this is no longer load-bearing --
        # it stays because `close()` is the one exit that runs `closeEvent`, and any
        # future `closeEvent` cleanup on this dialog should run when the CUO backs
        # out. See `LocksmithDialog._release_current_dialog` for what went wrong
        # when `closeEvent` was the only place the pointer was cleared.
        self._back.clicked.connect(self.close)
        self._confirm_button.clicked.connect(self._on_confirm)

        # A confirmation modal exists to ADD friction, so the irreversible button
        # must be neither the default nor focused.
        # `LocksmithDialog._build_button_section` makes the LAST `LocksmithButton`
        # in the row the default and focuses it, and the primary is last -- which
        # put a single Return keystroke between an unread mandate and a permanent,
        # publicly-readable credential. Measured: one `Key_Return` on the freshly
        # opened dialog anchored.
        self._back.setDefault(True)
        self._back.setAutoDefault(True)
        self._confirm_button.setDefault(False)
        self._confirm_button.setAutoDefault(False)
        self._back.setFocus()

    def finish(self) -> None:
        """The outcome has arrived; release the in-flight guard and close.

        REQUIRED, not a convenience: `reject()` refuses while `_confirmed`, and
        `QWidget.close()` routes through `closeEvent` -> `QDialog::reject`, so a
        plain `close()` on a confirmed dialog is IGNORED. Shipped exactly that
        way for one commit -- the mandate signed, the SAID banner appeared behind
        the modal, and the modal sat on "Signing..." for the life of the process.

        So the guard yields to exactly one caller: the page, once issuance has
        actually resolved. Escape and the header X still cannot reach this.
        """
        self._finished = True
        self.close()

    def reject(self):
        """Escape must not destroy this modal once signing has begun.

        `_on_confirm` disables both buttons, but Escape reaches `QDialog::reject`
        through Qt's own key handling and no `setEnabled(False)` stands in its
        way. The issuance carries on regardless -- destroying the dialog only
        removes the surface that reports the outcome, and leaves `fail()` with
        nothing to re-arm.

        `_finished` is the deliberate exception. Without it this guard also
        blocks the page's own completion path, because `close()` is implemented
        in terms of `reject()`.
        """
        if self._confirmed and not self._finished:
            return
        super().reject()

    def _on_confirm(self) -> None:
        self._confirmed = True
        self._confirm_button.setEnabled(False)
        self._confirm_button.setText(copy.IN_FLIGHT)
        # Nothing can be kept-editing once it is being signed: clicking back
        # mid-flight destroyed the modal while the issuance carried on, leaving
        # no surface to report success or failure on. `fail()` re-arms it.
        self._back.setEnabled(False)
        self.confirm.emit()

    def confirmed(self) -> bool:
        return self._confirmed

    def fail(self, message: str) -> None:
        """Re-enable the primary after a failed anchor, so a retry is possible."""
        self._confirmed = False
        self._confirm_button.setEnabled(True)
        self._confirm_button.setText(copy.REVIEW_CONFIRM)
        self._back.setEnabled(True)
        self.show_error(message)
