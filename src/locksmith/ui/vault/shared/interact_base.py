# -*- encoding: utf-8 -*-
"""
locksmith.ui.vault.shared.interact_base module

Base dialog for creating KERI interaction events with arbitrary JSON data
"""
import json
from typing import TYPE_CHECKING

from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout
from keri import help

from locksmith.ui import colors
from locksmith.ui.toolkit.widgets import (
    LocksmithDialog,
    LocksmithButton,
    LocksmithInvertedButton
)
from locksmith.ui.toolkit.widgets.dividers import LocksmithDivider
from locksmith.ui.toolkit.widgets.fields import LocksmithPlainTextEdit

if TYPE_CHECKING:
    from locksmith.ui.vault.page import VaultPage

logger = help.ogler.getLogger(__name__)


class BaseInteractDialog(LocksmithDialog):
    """Base dialog for creating interaction events with arbitrary JSON data."""

    def __init__(self, identifier_alias: str, icon_path: str, app, parent: "VaultPage" = None):
        """
        Initialize the BaseInteractDialog.

        Args:
            identifier_alias: The alias of the identifier
            icon_path: Path to the icon for the dialog title
            app: Application instance
            parent: Parent widget (VaultPage container)
        """
        self.app = app
        self.identifier_alias = identifier_alias

        # Get the hab (identifier)
        try:
            self.hab = self.app.vault.hby.habByName(identifier_alias)
            if not self.hab:
                raise ValueError(f"Identifier '{identifier_alias}' not found")
        except Exception as e:
            logger.error(f"Error loading identifier: {e}")
            raise

        # Create content widget
        content_widget = QWidget()
        content_widget.setStyleSheet(f"background-color: {colors.BACKGROUND_CONTENT};")
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(15)

        # Build content sections
        self._build_info_section(layout)
        self._build_json_input_section(layout)

        layout.addStretch()

        # Create button row
        button_row = QHBoxLayout()
        self.cancel_button = LocksmithInvertedButton("Cancel")
        button_row.addWidget(self.cancel_button)
        button_row.addSpacing(10)
        self.interact_button = LocksmithButton("Create Interaction")
        button_row.addWidget(self.interact_button)

        # Create title content with icon
        title_content_widget = QWidget()
        title_content = QHBoxLayout()
        icon = QIcon(icon_path)
        icon_label = QLabel()
        icon_label.setPixmap(icon.pixmap(32, 32))
        icon_label.setFixedSize(32, 32)
        title_content.addWidget(icon_label)

        title_label = QLabel(f"  {identifier_alias}")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        title_content.addWidget(title_label)
        title_content_widget.setLayout(title_content)

        # Initialize parent dialog
        super().__init__(
            parent=parent,
            title_content=title_content_widget,
            show_close_button=True,
            content=content_widget,
            buttons=button_row,
            show_overlay=False
        )

        # Set initial size
        self.setFixedSize(530, 620)

        # Connect buttons
        self.cancel_button.clicked.connect(self.close)
        self.interact_button.clicked.connect(self._create_interaction)

        logger.info(f"{self.__class__.__name__} initialized for '{identifier_alias}'")

    def _build_info_section(self, layout):
        """Build the info section with prefix and instructions."""
        layout.addSpacing(5)

        # Prefix row
        prefix_row = QHBoxLayout()
        prefix_label = QLabel("Prefix:")
        prefix_label.setStyleSheet("font-weight: bold; font-size: 15px;")
        prefix_row.addWidget(prefix_label)
        prefix_value = QLabel(self.hab.pre)
        prefix_value.setStyleSheet("font-size: 13px; font-weight: 50; "
                                   "font-family: 'Menlo', 'SF Mono', monospace;"
                                   f"color: {colors.TEXT_DARK}")
        prefix_row.addWidget(prefix_value)
        prefix_row.addStretch()
        layout.addLayout(prefix_row)

        layout.addSpacing(10)

        sequence_number_row = QHBoxLayout()
        sequence_number_label = QLabel("Sequence Number:")
        sequence_number_label.setStyleSheet("font-weight: bold; font-size: 15px;")
        sequence_number_row.addWidget(sequence_number_label)

        sequence_number_row.addStretch()
        current_sequence_number_value = QLabel(str(self.hab.kever.sn))
        current_sequence_number_value.setStyleSheet("font-size: 14px; font-weight: 50; font-family: 'Menlo', 'SF Mono', monospace;")
        sequence_number_row.addWidget(current_sequence_number_value)

        arrow_icon_label = QLabel()
        arrow_icon_label.setPixmap(QPixmap(":/assets/material-icons/arrow_right.svg"))
        arrow_icon_label.setFixedSize(20, 20)
        sequence_number_row.addWidget(arrow_icon_label)

        sequence_number_row.addSpacing(5)

        next_sequence_number_value = QLabel(str(self.hab.kever.sn + 1))
        next_sequence_number_value.setStyleSheet("font-size: 14px; font-weight: 50; font-family: 'Menlo', 'SF Mono', monospace;")
        sequence_number_row.addWidget(next_sequence_number_value)
        sequence_number_row.addSpacing(40)

        layout.addLayout(sequence_number_row)
        layout.addSpacing(5)
        top_divider = LocksmithDivider()
        layout.addWidget(top_divider)
        layout.addSpacing(15)


        # Instructions
        instructions = QLabel(
            "Enter JSON data to include in the interaction event. "
            "The data will be placed in the 'a' (anchor) field of the event."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet(f"font-size: 13px; color: {colors.TEXT_SECONDARY};")
        layout.addWidget(instructions)

        layout.addSpacing(10)

    def _build_json_input_section(self, layout):
        """Build the JSON input section."""
        # Label
        json_label = QLabel("JSON Data")
        json_label.setStyleSheet("font-weight: bold; font-size: 15px;")
        layout.addWidget(json_label)

        # Multiline text edit for JSON input
        self.json_input = LocksmithPlainTextEdit("Enter JSON data (e.g., {\"key\": \"value\"})")
        self.json_input.setMinimumHeight(200)
        self.json_input.setMaximumHeight(250)
        self.json_input.setProperty("class", "monospace")
        self.json_input._update_styling()  # Force style refresh with monospace
        layout.addWidget(self.json_input)

        layout.addSpacing(5)

        # Helper text
        helper = QLabel("Example: {\"message\": \"Hello World\", \"timestamp\": 1234567890}")
        helper.setStyleSheet(f"font-size: 12px; color: {colors.TEXT_MUTED};")
        layout.addWidget(helper)

    def _create_interaction(self):
        """Handle the interact button click and create interaction event."""
        logger.info(f"Attempting to create interaction for identifier '{self.identifier_alias}'")

        # Get JSON input
        json_text = self.json_input.toPlainText().strip()

        # Validate not empty
        if not json_text:
            self.show_error("JSON data is required")
            return

        # Parse and validate JSON
        try:
            parsed_data = json.loads(json_text)
        except json.JSONDecodeError as e:
            self.show_error(f"Invalid JSON: {str(e)}")
            return

        # Validate that parsed data is a dict or list
        if not isinstance(parsed_data, (dict, list)):
            self.show_error("JSON data must be an object or array")
            return

        # Create interaction event
        try:
            # Call KERI interact API
            # The data parameter accepts arbitrary JSON that goes into the 'a' field
            self.hab.interact(data=[parsed_data])

            logger.info(f"Interaction event created successfully for '{self.identifier_alias}'")
            if hasattr(self.app.vault, 'signals') and self.app.vault.signals:
                self.app.vault.signals.emit_doer_event(
                    doer_name="InteractDoer",
                    event_type="interaction_complete",
                    data={
                        'alias': self.identifier_alias,
                        'success': True
                    }
                )

            # Close dialog on success
            self.accept()

        except Exception as e:
            logger.exception(f"Error creating interaction event: {e}")
            self.show_error(f"Failed to create interaction: {str(e)}")
