# -*- encoding: utf-8 -*-
"""The read-back shown between filling the form and anchoring the credential.

`ux-patterns.md:439` makes a confirmation modal the platform's irreversibility
pattern, carrying "This cannot be undone" -- literally true here.

It renders the CANONICAL payload, never the raw field text, because the payload
builder rewrites input and the difference is exactly what a reader needs to see. It
holds no rules: whatever it is handed, it shows.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
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
    shown.setStyleSheet(f"color: {colors.TEXT_PRIMARY}; font-size: 14px;")
    layout.addWidget(name)
    layout.addWidget(shown, 1)
    return row


class MandateReviewDialog(LocksmithDialog):
    """Read back the canonical payload; confirm or go back."""

    confirm = Signal()

    def __init__(self, payload: dict, signer_name: str, parent=None):
        self._confirmed = False

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
        rows.addWidget(_row("In force", (
            f"{payload.get('window_opens', '')} through "
            f"{payload.get('window_closes', '')}, inclusive")))
        outer.addWidget(summary)

        thesis_label = QLabel("Thesis, published in full")
        thesis_label.setStyleSheet(
            f"color: {colors.TEXT_SECONDARY}; font-size: 13px;")
        outer.addWidget(thesis_label)
        thesis = QLabel(str(payload.get("thesis") or ""))
        thesis.setObjectName("mandateReviewDialog.thesis")
        thesis.setWordWrap(True)
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

        super().__init__(parent=parent, title=copy.REVIEW_TITLE,
                         content=body, buttons=buttons)
        self.setObjectName("mandateReviewDialog")

        self._back.clicked.connect(self.reject)
        self._confirm_button.clicked.connect(self._on_confirm)

    def _on_confirm(self) -> None:
        self._confirmed = True
        self._confirm_button.setEnabled(False)
        self._confirm_button.setText(copy.IN_FLIGHT)
        self.confirm.emit()

    def confirmed(self) -> bool:
        return self._confirmed

    def fail(self, message: str) -> None:
        """Re-enable the primary after a failed anchor, so a retry is possible."""
        self._confirmed = False
        self._confirm_button.setEnabled(True)
        self._confirm_button.setText(copy.REVIEW_CONFIRM)
        self.show_error(message)
