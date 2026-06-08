"""Settings → Updates widget (Phase 5 §8.6 / Task 14).

A self-contained QWidget that the existing SettingsPage mounts into
its scroll-area. We intentionally do NOT modify SettingsPage here —
the main session wires us in once a vault is open.

Surfaces:
- "Check automatically" toggle (bound to ``UpdatePrefs.check_automatically``)
- "Check now" button (calls the injected ``check_now_callback``)
- "Last checked: …" timestamp display (updated via ``set_last_checked``)
- "View verification log" button (opens VerificationLogDialog via callback)

We accept callables rather than emitting signals because the main
session already has the controller + last verification result in
scope; this keeps the widget thin and free of cross-package imports.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from keri import help

from locksmith.ui import colors
from locksmith.ui.toolkit.widgets.toggle import ToggleSwitch
from locksmith.update.prefs import UpdatePrefs

logger = help.ogler.getLogger(__name__)


_NEVER_CHECKED = "Never"


class UpdatesSettingsWidget(QWidget):
    """Updates section for the SettingsPage.

    Args:
        check_now_callback: Invoked when the user clicks "Check now".
            Typically ``UpdateController.check_now``.
        view_log_callback: Invoked when the user clicks "View verification
            log". Typically a closure that opens VerificationLogDialog
            with the most recent ``VerificationResult``.
        prefs: Override for tests / parallel app instances. Defaults to
            a process-wide ``UpdatePrefs``.
        parent: Parent widget (the SettingsPage container).
    """

    def __init__(
        self,
        *,
        check_now_callback: Callable[[], None] | None = None,
        view_log_callback: Callable[[], None] | None = None,
        prefs: UpdatePrefs | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("updatesSettingsWidget")

        self._prefs = prefs or UpdatePrefs()
        self._check_now_callback = check_now_callback
        self._view_log_callback = view_log_callback

        self._build_layout()

    # ---- layout ------------------------------------------------------

    def _build_layout(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        header = QLabel("Updates")
        header.setObjectName("updatesSettingsWidget.header")
        hf = QFont()
        hf.setBold(True)
        hf.setPointSize(14)
        header.setFont(hf)
        header.setStyleSheet(f"color: {colors.TEXT_PRIMARY};")
        outer.addWidget(header)

        subheader = QLabel(
            "Locksmith verifies every update against the publisher's "
            "KERI key event log before installing."
        )
        subheader.setObjectName("updatesSettingsWidget.subheader")
        subheader.setStyleSheet(
            f"color: {colors.TEXT_SECONDARY}; font-size: 12px; margin-bottom: 10px;"
        )
        subheader.setWordWrap(True)
        outer.addWidget(subheader)

        container = QFrame()
        container.setObjectName("updatesSettingsContainer")
        container.setStyleSheet(f"""
            #updatesSettingsContainer {{
                background-color: {colors.WHITE};
                border: 1px solid {colors.BORDER_TABLE};
                border-radius: 24px;
            }}
            QWidget {{ background-color: transparent; }}
        """)
        body = QVBoxLayout(container)
        body.setContentsMargins(25, 25, 25, 25)
        body.setSpacing(20)

        body.addLayout(self._build_auto_check_row())
        body.addLayout(self._build_check_now_row())
        body.addLayout(self._build_view_log_row())

        outer.addWidget(container)

    def _build_auto_check_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(20)

        label = QLabel("Check for updates automatically")
        label.setObjectName("updatesSettingsWidget.autoCheckLabel")
        label.setFixedWidth(280)
        label.setStyleSheet(f"font-size: 14px; color: {colors.TEXT_PRIMARY};")
        row.addWidget(label)

        self.auto_check_toggle = ToggleSwitch()
        self.auto_check_toggle.setObjectName(
            "updatesSettingsWidget.autoCheckToggle"
        )
        self.auto_check_toggle.setChecked(self._prefs.check_automatically)
        self.auto_check_toggle.toggled.connect(self._on_auto_check_toggled)
        row.addWidget(self.auto_check_toggle)

        row.addStretch()
        return row

    def _build_check_now_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(20)

        label = QLabel("Last checked:")
        label.setObjectName("updatesSettingsWidget.lastCheckedLabel")
        label.setFixedWidth(280)
        label.setStyleSheet(f"font-size: 14px; color: {colors.TEXT_PRIMARY};")
        row.addWidget(label)

        self.last_checked_value = QLabel(_NEVER_CHECKED)
        self.last_checked_value.setObjectName(
            "updatesSettingsWidget.lastCheckedValue"
        )
        self.last_checked_value.setStyleSheet(
            f"color: {colors.TEXT_SECONDARY}; font-size: 13px;"
        )
        row.addWidget(self.last_checked_value, stretch=1)

        self.check_now_button = QPushButton("Check now")
        self.check_now_button.setObjectName(
            "updatesSettingsWidget.checkNowButton"
        )
        self.check_now_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.check_now_button.setStyleSheet(self._secondary_button_qss())
        self.check_now_button.clicked.connect(self._on_check_now_clicked)
        row.addWidget(self.check_now_button)
        return row

    def _build_view_log_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(20)

        label = QLabel("Verification log")
        label.setObjectName("updatesSettingsWidget.viewLogLabel")
        label.setFixedWidth(280)
        label.setStyleSheet(f"font-size: 14px; color: {colors.TEXT_PRIMARY};")
        row.addWidget(label)

        self.view_log_button = QPushButton("View verification log")
        self.view_log_button.setObjectName(
            "updatesSettingsWidget.viewLogButton"
        )
        self.view_log_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.view_log_button.setStyleSheet(self._secondary_button_qss())
        self.view_log_button.clicked.connect(self._on_view_log_clicked)
        row.addWidget(self.view_log_button)

        row.addStretch()
        return row

    @staticmethod
    def _secondary_button_qss() -> str:
        return f"""
            QPushButton {{
                background-color: transparent;
                color: {colors.PRIMARY};
                border: 1px solid {colors.PRIMARY};
                border-radius: 6px;
                padding: 8px 18px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {colors.BACKGROUND_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {colors.BACKGROUND_NEUTRAL};
            }}
        """

    # ---- public mutators (driven by the main session) ----------------

    def set_last_checked(self, when_text: str | None) -> None:
        """Display ``when_text`` (caller formats it) or 'Never' if None."""
        self.last_checked_value.setText(when_text or _NEVER_CHECKED)

    def set_auto_check(self, enabled: bool) -> None:
        """Programmatic flip of the toggle (without going through prefs)."""
        # blockSignals so we don't double-write to prefs.
        self.auto_check_toggle.blockSignals(True)
        try:
            self.auto_check_toggle.setChecked(bool(enabled))
        finally:
            self.auto_check_toggle.blockSignals(False)

    def set_check_now_callback(self, cb: Callable[[], None] | None) -> None:
        """Late-bind the check-now callback (the controller is wired
        after this widget is constructed in the SettingsPage)."""
        self._check_now_callback = cb

    def set_view_log_callback(self, cb: Callable[[], None] | None) -> None:
        """Late-bind the verification-log callback (depends on the most
        recent VerificationResult, which the controller updates)."""
        self._view_log_callback = cb

    # ---- internal handlers ------------------------------------------

    def _on_auto_check_toggled(self, checked: bool) -> None:
        self._prefs.check_automatically = bool(checked)
        logger.info(
            "[update] settings.check_automatically=%s",
            bool(checked),
        )

    def _on_check_now_clicked(self) -> None:
        logger.info("[update] settings.check_now_clicked")
        if self._check_now_callback is not None:
            self._check_now_callback()

    def _on_view_log_clicked(self) -> None:
        logger.info("[update] settings.view_log_clicked")
        if self._view_log_callback is not None:
            self._view_log_callback()
