# -*- encoding: utf-8 -*-
"""
locksmith.plugins.kerifoundation.witnesses.widgets module

Custom widgets for the KERI Foundation witness provisioning flow.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from locksmith.plugins.kerifoundation.core.configing import WitnessServerConfig
from locksmith.ui import colors
from locksmith.ui.styles import get_monospace_font_family
from locksmith.ui.toolkit.widgets.buttons import LocksmithCheckbox


class WitnessServerCard(QFrame):
    """Selectable card representing a witness server.

    Displays a checkbox, the server hostname (monospace), and an
    optional region label.  The entire card is clickable to toggle the
    checkbox.  When checked, the border and background change to the
    standard Locksmith blue-selection style.
    """

    checked_changed = Signal(bool)

    # Match LocksmithRadioPanel selected colours
    BORDER_NORMAL = colors.BORDER          # #D0D5DD
    BORDER_CHECKED = colors.BLUE_SELECTION  # #2196F3
    BG_CHECKED = colors.BLUE_SELECTION_BG   # #E3F2FD

    def __init__(self, server: WitnessServerConfig, parent=None):
        super().__init__(parent)
        self._server = server
        self._region_text = server.label or server.region or ""
        self._status = "available"

        self.setFixedWidth(300)
        self.setFixedHeight(80)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        self._checkbox = LocksmithCheckbox()
        self._checkbox.toggled.connect(self._on_toggled)
        layout.addWidget(self._checkbox, alignment=Qt.AlignmentFlag.AlignVCenter)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)

        mono = get_monospace_font_family()
        self._host_label = QLabel(server.witness_url)
        self._host_label.setStyleSheet(
            f"font-family: {mono}; font-size: 13px; color: {colors.TEXT_PRIMARY}; border: none;"
        )
        self._host_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        text_layout.addWidget(self._host_label)

        self._region_label = QLabel(self._region_text)
        self._region_label.setStyleSheet(
            f"font-size: 12px; color: {colors.TEXT_SECONDARY}; border: none;"
        )
        self._region_label.setVisible(bool(self._region_text))
        text_layout.addWidget(self._region_label)

        layout.addLayout(text_layout, 1)

        self._update_frame_style()

    @property
    def server_config(self) -> WitnessServerConfig:
        return self._server

    @property
    def status(self) -> str:
        return self._status

    def is_checked(self) -> bool:
        return self._checkbox.isChecked()

    def set_checked(self, checked: bool):
        self._checkbox.setChecked(checked)

    def is_available(self) -> bool:
        return self._status == "available"

    def set_status(self, status: str):
        self._status = status
        self._checkbox.setChecked(False)

        parts = [self._region_text] if self._region_text else []
        if status == "registered":
            parts.append("Registered")
        elif status == "pending":
            parts.append("Pending")

        secondary = " • ".join(part for part in parts if part)
        self._region_label.setText(secondary)
        self._region_label.setVisible(bool(secondary))
        self.set_interactive(True)

    def set_interactive(self, enabled: bool):
        is_enabled = enabled and self.is_available()
        self._checkbox.setEnabled(is_enabled)
        self.setEnabled(is_enabled)
        self.setCursor(
            Qt.CursorShape.PointingHandCursor
            if is_enabled
            else Qt.CursorShape.ArrowCursor
        )
        self._update_frame_style()

    def _on_toggled(self, checked: bool):
        self._update_frame_style()
        self.checked_changed.emit(checked)

    def _update_frame_style(self):
        if not self.isEnabled():
            self.setStyleSheet(f"""
                WitnessServerCard {{
                    border: 1px solid {self.BORDER_NORMAL};
                    border-radius: 8px;
                    background-color: {colors.BACKGROUND_CONTENT};
                }}
            """)
        elif self._checkbox.isChecked():
            self.setStyleSheet(f"""
                WitnessServerCard {{
                    border: 1px solid {self.BORDER_CHECKED};
                    border-radius: 8px;
                    background-color: {self.BG_CHECKED};
                }}
            """)
        else:
            self.setStyleSheet(f"""
                WitnessServerCard {{
                    border: 1px solid {self.BORDER_NORMAL};
                    border-radius: 8px;
                    background-color: {colors.WHITE};
                }}
            """)

    def mousePressEvent(self, event):
        if self.isEnabled() and event.button() == Qt.MouseButton.LeftButton:
            self._checkbox.setChecked(not self._checkbox.isChecked())
        super().mousePressEvent(event)
