"""Verification Log Dialog — shows the KERI trust state of a release.

This is the user's window into the cryptographic verdict produced by
``locksmith.update.verify.verify_artifact()``: which publisher AID
issued the anchor, how many witnesses concurred, what the artifact
hash was, whether the on-disk file matches that hash. Phase 5 §8.6.

The dialog is purely presentational — it consumes a ``VerificationResult``
and renders it. The actual verification logic lives in
``locksmith.update.verify``. Wire-up (auto-open on failed updates,
manual open from the Help menu, etc.) belongs to the controller.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from locksmith.ui import colors
from locksmith.ui.toolkit.widgets.dialogs import LocksmithDialog
from locksmith.update.verify import VerificationResult


def _human_size(n: int) -> str:
    """62934095 → '60.02 MB'. Matches Finder/Explorer sizing convention (1024)."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:,.2f} {unit}" if unit != "B" else f"{n:,} {unit}"
        n /= 1024
    return f"{n:,.2f} GB"


def _row(label: str, value: str, *, value_color: str | None = None, mono: bool = False) -> QWidget:
    """One label/value pair laid out for the verification readout."""
    row = QWidget()
    row.setObjectName(f"verificationLogDialog.row.{label.lower().replace(' ', '_').replace(':', '')}")
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 4, 0, 4)
    layout.setSpacing(16)

    lbl = QLabel(label)
    lbl.setObjectName("verificationLogDialog.label")
    lbl.setFixedWidth(140)
    lbl.setStyleSheet(
        f"color: {colors.TEXT_SECONDARY}; font-size: 13px;"
    )

    val = QLabel(value)
    val.setObjectName("verificationLogDialog.value")
    val.setWordWrap(True)
    val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    style = f"color: {value_color or colors.TEXT_PRIMARY}; font-size: 13px;"
    if mono:
        style += ' font-family: "Source Code Pro", monospace;'
    val.setStyleSheet(style)

    layout.addWidget(lbl)
    layout.addWidget(val, stretch=1)
    return row


def _status_banner(result: VerificationResult, error_message: str | None) -> QWidget:
    """Green 'Verified' or red 'Rejected' banner across the top of the dialog body."""
    banner = QWidget()
    banner.setObjectName("verificationLogDialog.statusBanner")
    layout = QHBoxLayout(banner)
    layout.setContentsMargins(16, 12, 16, 12)
    layout.setSpacing(12)

    if result is not None and result.ok:
        bg, fg, mark, headline = (
            colors.BACKGROUND_SUCCESS,
            "#1B5E20",
            "✓",
            "Verified",
        )
        sub = (
            f"Release v{result.version} was anchored by your trusted publisher "
            f"and confirmed by {result.witness_receipts} witness "
            f"{'receipts' if result.witness_receipts != 1 else 'receipt'}."
        )
    else:
        bg, fg, mark, headline = (
            colors.BACKGROUND_ERROR,
            "#B71C1C",
            "✕",
            "Rejected",
        )
        sub = error_message or "This release failed the trust check and will not be installed."

    banner.setStyleSheet(
        f"#{banner.objectName()} {{ background-color: {bg}; border-radius: 8px; }}"
    )

    mark_lbl = QLabel(mark)
    mark_lbl.setStyleSheet(f"color: {fg}; font-size: 28px; font-weight: bold;")
    mark_lbl.setFixedWidth(36)
    mark_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

    text_col = QVBoxLayout()
    text_col.setSpacing(2)
    headline_lbl = QLabel(headline)
    headline_lbl.setStyleSheet(f"color: {fg}; font-size: 16px; font-weight: 600;")
    sub_lbl = QLabel(sub)
    sub_lbl.setStyleSheet(f"color: {fg}; font-size: 12px;")
    sub_lbl.setWordWrap(True)
    text_col.addWidget(headline_lbl)
    text_col.addWidget(sub_lbl)

    layout.addWidget(mark_lbl)
    layout.addLayout(text_col, stretch=1)
    return banner


class VerificationLogDialog(LocksmithDialog):
    """Dialog showing the cryptographic provenance of a release.

    Use cases:
    - Auto-open after a failed update (verification rejected an artifact)
    - Manual open from Settings → Updates → "View verification log"
    - Open from Help → "Verify the running release"

    Args:
        result: ``VerificationResult`` from ``verify_artifact()``. May be
            ``None`` for a "no verification has run yet" state.
        error_message: Optional typed-error description to show in the
            failed banner. Ignored when ``result.ok`` is True.
        parent: Parent widget (typically the main window).
    """

    def __init__(
        self,
        result: VerificationResult | None,
        error_message: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        content = self._build_content(result, error_message)
        buttons = self._build_buttons()
        super().__init__(
            parent=parent,
            title="Release Verification",
            content=content,
            buttons=buttons,
            show_overlay=True,
        )
        self.setObjectName("verificationLogDialog")
        self.result = result

    # ---- layout ----------------------------------------------------------

    def _build_content(
        self,
        result: VerificationResult | None,
        error_message: str | None,
    ) -> QWidget:
        wrap = QWidget()
        wrap.setMinimumWidth(560)
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(16)

        layout.addWidget(_status_banner(result, error_message))

        if result is None:
            placeholder = QLabel(
                "No verification has run yet. Trigger 'Check for updates' "
                "from the Help menu to see the trust state of a release."
            )
            placeholder.setWordWrap(True)
            placeholder.setStyleSheet(
                f"color: {colors.TEXT_SECONDARY}; font-size: 13px; padding: 8px 0;"
            )
            layout.addWidget(placeholder)
            return wrap

        # Cryptographic-evidence section
        section = QLabel("Cryptographic evidence")
        section.setStyleSheet(
            f"color: {colors.TEXT_DARK}; font-size: 14px; font-weight: 600;"
            f"padding-top: 4px;"
        )
        layout.addWidget(section)

        layout.addWidget(_row("Release version:", f"v{result.version}"))
        layout.addWidget(_row("Platform:", result.platform))
        layout.addWidget(_row(
            "Publisher AID:",
            result.publisher_aid,
            mono=True,
        ))
        layout.addWidget(_row(
            "Anchor SAID:",
            result.anchor_said,
            mono=True,
        ))
        layout.addWidget(_row(
            "KEL sequence:",
            f"sn={result.kel_tip_sn}",
        ))
        layout.addWidget(_row(
            "Witness receipts:",
            f"{result.witness_receipts} concurred",
            value_color="#1B5E20" if result.witness_receipts >= 3 else colors.TEXT_PRIMARY,
        ))
        layout.addWidget(_row(
            "Artifact SHA-256:",
            result.artifact_sha256,
            mono=True,
        ))
        layout.addWidget(_row(
            "Artifact size:",
            f"{_human_size(result.artifact_size)} ({result.artifact_size:,} bytes)",
        ))

        return wrap

    def _build_buttons(self) -> QHBoxLayout:
        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.setObjectName("verificationLogDialog.closeButton")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setStyleSheet(f"""
            QPushButton {{
                padding: 10px 24px;
                background-color: {colors.PRIMARY};
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background-color: {colors.PRIMARY_HOVER}; }}
            QPushButton:pressed {{ background-color: {colors.PRIMARY_PRESSED}; }}
        """)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        return buttons
