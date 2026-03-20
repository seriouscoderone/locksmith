# -*- encoding: utf-8 -*-
"""
locksmith.ui.vault.remotes.filter module

Filter dialog for remote identifiers.
"""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QButtonGroup
from keri import help

from locksmith.ui import colors
from locksmith.ui.toolkit.widgets import LocksmithDialog, LocksmithButton, LocksmithInvertedButton
from locksmith.ui.toolkit.widgets.buttons import LocksmithRadioButton

logger = help.ogler.getLogger(__name__)


class FilterRemoteIdentifiersDialog(LocksmithDialog):
    """Dialog for filtering remote identifiers by type."""

    # Signal emitted when filters are applied
    filter_applied = Signal(dict)  # Emits: {"identifier_type": "transferable"|"non-transferable"|"both"}

    def __init__(self, parent=None):
        """
        Initialize the FilterRemoteIdentifiersDialog.

        Args:
            parent: Parent widget (typically VaultPage)
        """
        # Track current filter state
        self.current_filter = "both"

        # Create content widget
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        # Section label
        section_label = QLabel("Identifier Type")
        section_label.setStyleSheet(f"font-weight: 600; font-size: 14px; color: {colors.TEXT_PRIMARY};")
        layout.addWidget(section_label)

        # Create radio buttons
        self.transferable_radio = LocksmithRadioButton("Transferable")
        self.non_transferable_radio = LocksmithRadioButton("Non-Transferable")
        self.both_radio = LocksmithRadioButton("Both")

        # Create button group for mutual exclusivity
        self.type_group = QButtonGroup(content_widget)
        self.type_group.addButton(self.transferable_radio)
        self.type_group.addButton(self.non_transferable_radio)
        self.type_group.addButton(self.both_radio)

        # Set default to "Both"
        self.both_radio.setChecked(True)

        # Add radio buttons to layout
        radio_layout = QVBoxLayout()
        radio_layout.setSpacing(12)
        radio_layout.addWidget(self.transferable_radio)
        radio_layout.addWidget(self.non_transferable_radio)
        radio_layout.addWidget(self.both_radio)
        layout.addLayout(radio_layout)

        # Add stretch to push buttons down
        layout.addStretch()

        # Create button row
        button_row = QHBoxLayout()
        self.reset_button = LocksmithInvertedButton("Reset")
        self.apply_button = LocksmithButton("Apply")
        button_row.addWidget(self.reset_button)
        button_row.addSpacing(10)
        button_row.addWidget(self.apply_button)

        # Initialize parent dialog
        super().__init__(
            parent=parent,
            title="Filter Remote Identifiers",
            title_icon=":/assets/material-icons/tune.svg",
            show_close_button=True,
            content=content_widget,
            buttons=button_row,
            show_overlay=False
        )

        # Set fixed size
        self.setFixedSize(400, 320)

        # Connect signals
        self.reset_button.clicked.connect(self._on_reset)
        self.apply_button.clicked.connect(self._on_apply)

        logger.info("FilterRemoteIdentifiersDialog initialized")

    def _on_reset(self):
        """Reset filters to default (Both)."""
        self.both_radio.setChecked(True)
        logger.debug("Filter reset to default (Both)")

    def _on_apply(self):
        """Apply selected filters and close dialog."""
        # Determine selected filter
        if self.transferable_radio.isChecked():
            filter_type = "transferable"
        elif self.non_transferable_radio.isChecked():
            filter_type = "non-transferable"
        else:
            filter_type = "both"

        # Emit filter data
        filter_data = {"identifier_type": filter_type}
        self.filter_applied.emit(filter_data)

        logger.info(f"Filters applied: {filter_data}")

        # Close dialog
        self.accept()

    def set_current_filter(self, filter_type: str):
        """
        Set the current filter selection.

        Args:
            filter_type: One of "transferable", "non-transferable", or "both"
        """
        self.current_filter = filter_type

        if filter_type == "transferable":
            self.transferable_radio.setChecked(True)
        elif filter_type == "non-transferable":
            self.non_transferable_radio.setChecked(True)
        else:
            self.both_radio.setChecked(True)
