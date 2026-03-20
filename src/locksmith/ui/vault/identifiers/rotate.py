# -*- encoding: utf-8 -*-
"""
locksmith.ui.vault.identifiers.rotate module

Dialog for rotating identifiers
"""
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout
)
from keri import help

from locksmith.core import habbing, rotating, witnessing
from locksmith.ui import colors
from locksmith.ui.toolkit.widgets import (
    LocksmithDialog,
    LocksmithButton,
    LocksmithInvertedButton
)
from locksmith.ui.toolkit.widgets.dividers import LocksmithDivider
from locksmith.ui.toolkit.widgets.fields import LocksmithLineEdit
from locksmith.ui.vault.identifiers.authenticate import WitnessAuthenticationDialog
from locksmith.ui.vault.shared.witness_rotation_mixin import WitnessRotationMixin


if TYPE_CHECKING:
    pass

logger = help.ogler.getLogger(__name__)


class RotateIdentifierDialog(WitnessRotationMixin, LocksmithDialog):
    """Dialog for rotating identifiers."""

    def __init__(self, icon_path, app, identifier_alias, parent=None, prepopulate_witnesses=None):
        """
        Initialize the ViewIdentifierDialog.

        Args:
            icon_path: Path to the identifier icon
            app: Application instance
            identifier_alias: Alias of the identifier to view
            parent: Parent widget (typically VaultPage)
            prepopulate_witnesses: Optional list of witness dicts to prepopulate in the add section
        """
        self.app = app
        self.identifier_alias = identifier_alias
        self.prepopulate_witnesses = prepopulate_witnesses or []

        try:
            self.hab = self.app.vault.hby.habByName(identifier_alias)
            if not self.hab:
                raise ValueError(f"Identifier '{identifier_alias}' not found")
        except Exception as e:
            logger.error(f"Error loading identifier: {e}")
            raise

        # Get identifier details
        self.details = habbing.get_identifier_details(self.app, self.hab)

        content_widget = QWidget()
        content_widget.setStyleSheet(f"background-color: {colors.BACKGROUND_CONTENT};")
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(15)

        self._build_info_section(layout)

        top_divider = LocksmithDivider()
        layout.addWidget(top_divider)

        self._build_rotation_params_section(layout)

        # Build witness sections conditionally
        self._unused_witnesses = witnessing.get_unused_witnesses_for_rotation(self.app, self.hab)
        self._current_witnesses = witnessing.get_current_witnesses_for_rotation(self.app, self.hab)

        # Initialize selectors as None
        self.add_witness_selector = None
        self.remove_witness_selector = None

        if self._unused_witnesses:
            middle_divider = LocksmithDivider()
            layout.addSpacing(10)
            layout.addWidget(middle_divider)
            layout.addSpacing(10)
            self._build_witness_add_section(layout)

        if self._current_witnesses:
            bottom_divider = LocksmithDivider()
            layout.addSpacing(10)
            layout.addWidget(bottom_divider)
            layout.addSpacing(10)
            self._build_witness_remove_section(layout)

        layout.addSpacing(10)

        button_divider = LocksmithDivider()

        layout.addWidget(button_divider)

        layout.addStretch()
        # Create button row
        button_row = QHBoxLayout()
        self.close_button = LocksmithInvertedButton("Cancel")
        self.rotate_button = LocksmithButton("Rotate")
        button_row.addWidget(self.close_button)
        button_row.addSpacing(10)
        button_row.addWidget(self.rotate_button)


        # Create title content
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

        super().__init__(
            parent=parent,
            title_content=title_content_widget,
            show_close_button=True,
            content=content_widget,
            buttons=button_row
        )

        # Set initial size
        self.setFixedSize(530, 880)

        # Connect buttons
        self.close_button.clicked.connect(self.close)
        self.rotate_button.clicked.connect(self.rotate_identifier)

        # Calculate dialog height based on visible sections
        # Base height without witness sections
        base_height = 580
        witness_section_height = 150  # Height per witness section (label + dropdown + spacing + divider)

        dialog_height = base_height
        if self._unused_witnesses:
            dialog_height += witness_section_height
        if self._current_witnesses:
            dialog_height += witness_section_height

        self.setFixedSize(530, dialog_height)

        # Connect to vault signal bridge if available
        if self.app and hasattr(self.app, 'vault') and self.app.vault and hasattr(self.app.vault, 'signals'):
            self.app.vault.signals.doer_event.connect(self._on_doer_event)
            logger.info("RotateIdentifierDialog: Connected to vault signal bridge")

    def closeEvent(self, event):
        if self.app and hasattr(self.app, 'vault') and self.app.vault and hasattr(self.app.vault, 'signals'):
            try:
                self.app.vault.signals.doer_event.disconnect(self._on_doer_event)
            except RuntimeError:
                pass
        super().closeEvent(event)

    def _build_info_section(self, layout):
        """Build the info section with prefix and SN."""
        layout.addSpacing(5)

        info_section = QVBoxLayout()
        info_section.setSpacing(10)
        prefix_row = QHBoxLayout()
        prefix_label = QLabel("Prefix:")
        prefix_label.setStyleSheet("font-weight: bold; font-size: 15px;")
        prefix_row.addWidget(prefix_label)
        prefix_value = QLabel(self.details['pre'])
        prefix_value.setStyleSheet("font-size: 13px; font-weight: 50; "
                                   "font-family: 'Menlo', 'SF Mono', monospace;"
                                   f"color: {colors.TEXT_DARK}")
        prefix_row.addWidget(prefix_value)
        prefix_row.addSpacing(30)
        info_section.addLayout(prefix_row)
        info_section.addSpacing(10)


        sequence_number_row = QHBoxLayout()
        sequence_number_label = QLabel("Sequence Number:")
        sequence_number_label.setStyleSheet("font-weight: bold; font-size: 15px;")
        sequence_number_row.addWidget(sequence_number_label)

        sequence_number_row.addStretch()
        current_sequence_number_value = QLabel(str(self.details['sequence_number']))
        current_sequence_number_value.setStyleSheet("font-size: 14px; font-weight: 50; font-family: 'Menlo', 'SF Mono', monospace;")
        sequence_number_row.addWidget(current_sequence_number_value)

        arrow_icon_label = QLabel()
        arrow_icon_label.setPixmap(QPixmap(":/assets/material-icons/arrow_right.svg"))
        arrow_icon_label.setFixedSize(20, 20)
        sequence_number_row.addWidget(arrow_icon_label)

        sequence_number_row.addSpacing(5)

        next_sequence_number_value = QLabel(str(self.details['sequence_number'] + 1))
        next_sequence_number_value.setStyleSheet("font-size: 14px; font-weight: 50; font-family: 'Menlo', 'SF Mono', monospace;")
        sequence_number_row.addWidget(next_sequence_number_value)
        sequence_number_row.addSpacing(40)

        info_section.addLayout(sequence_number_row)


        layout.addLayout(info_section)

    def _build_rotation_params_section(self, layout):
        """Build the rotation parameters section, excluding witnesses to add or drop."""
        rotation_params_section = QVBoxLayout()
        rotation_params_section.setSpacing(15)
        rotation_params_section.addSpacing(10)

        # New signing threshold
        row = QHBoxLayout()
        label = QLabel("New signing threshold")
        label.setStyleSheet("font-weight: bold; font-size: 15px;")
        row.addWidget(label)
        row.addStretch()
        self.new_signing_threshold_field = LocksmithLineEdit()
        self.new_signing_threshold_field.setFixedWidth(50)
        self.new_signing_threshold_field.setText("1")
        self.new_signing_threshold_field.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.new_signing_threshold_field)
        row.addSpacing(48)
        rotation_params_section.addLayout(row)

        # Next signing threshold
        row = QHBoxLayout()
        label = QLabel("Next signing threshold")
        label.setStyleSheet("font-weight: bold; font-size: 15px;")
        row.addWidget(label)
        row.addStretch()
        self.next_signing_threshold_field = LocksmithLineEdit()
        self.next_signing_threshold_field.setFixedWidth(50)
        self.next_signing_threshold_field.setText("1")
        self.next_signing_threshold_field.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.next_signing_threshold_field)
        row.addSpacing(48)
        rotation_params_section.addLayout(row)

        # Key count
        row = QHBoxLayout()
        label = QLabel("Key Count")
        label.setStyleSheet("font-weight: bold; font-size: 15px;")
        row.addWidget(label)
        row.addStretch()
        self.key_count_field = LocksmithLineEdit()
        self.key_count_field.setFixedWidth(50)
        self.key_count_field.setText("1")
        self.key_count_field.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.key_count_field)
        row.addSpacing(48)
        rotation_params_section.addLayout(row)

        # TOAD - prepopulate with recommended value based on current witnesses
        current_witness_count = len(self.hab.kever.wits)
        recommended_toad = rotating.recommend_toad(current_witness_count)

        row = QHBoxLayout()
        label = QLabel("TOAD")
        label.setStyleSheet("font-weight: bold; font-size: 15px;")
        row.addWidget(label)
        row.addStretch()
        self.toad_field = LocksmithLineEdit()
        self.toad_field.setFixedWidth(50)
        self.toad_field.setText(str(recommended_toad))
        self.toad_field.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.toad_field)
        row.addSpacing(48)
        rotation_params_section.addLayout(row)

        layout.addLayout(rotation_params_section)

    def showEvent(self, event):
        """Override showEvent to connect the witness selectors to the dialog after it's shown."""
        super().showEvent(event)

        # Connect both witness selectors to dialog for height animation coordination
        if hasattr(self, 'add_witness_selector') and self.add_witness_selector:
            self.add_witness_selector.set_dialog(self)
        if hasattr(self, 'remove_witness_selector') and self.remove_witness_selector:
            self.remove_witness_selector.set_dialog(self)

        # Prepopulate witnesses if provided
        if self.prepopulate_witnesses and self.add_witness_selector:
            self._prepopulate_witnesses()

    def rotate_identifier(self):
        """Rotate the identifier."""
        # Validate required fields
        if not self.new_signing_threshold_field.text().strip():
            self.show_error("New signing threshold is required")
            return

        if not self.next_signing_threshold_field.text().strip():
            self.show_error("Next signing threshold is required")
            return

        if not self.key_count_field.text().strip():
            self.show_error("Key count is required")
            return

        if not self.toad_field.text().strip():
            self.show_error("TOAD is required")
            return

        # Parse values
        try:
            new_signing_threshold = int(self.new_signing_threshold_field.text())
        except ValueError:
            self.show_error("New signing threshold must be a valid number")
            return

        try:
            next_signing_threshold = int(self.next_signing_threshold_field.text())
        except ValueError:
            self.show_error("Next signing threshold must be a valid number")
            return

        try:
            key_count = int(self.key_count_field.text())
        except ValueError:
            self.show_error("Key count must be a valid number")
            return

        try:
            toad = int(self.toad_field.text())
        except ValueError:
            self.show_error("TOAD must be a valid number")
            return

        # Collect witness changes from selectors
        adds = []
        cuts = []

        if self.add_witness_selector:
            for _text, data in self.add_witness_selector.get_selected_items():
                if isinstance(data, dict) and data.get("id"):
                    adds.append(data["id"])

        if self.remove_witness_selector:
            for _text, data in self.remove_witness_selector.get_selected_items():
                if isinstance(data, dict) and data.get("id"):
                    cuts.append(data["id"])

        # Validate TOAD
        resulting_witness_count = self._get_resulting_witness_count()
        is_valid, error_message = rotating.validate_toad(toad, resulting_witness_count)

        if not is_valid:
            self.show_error(error_message)
            return

        # Clear any previous error before proceeding
        self.clear_error()

        # Execute rotation immediately (without authentication)
        logger.info(f"Executing rotation for {self.hab.name}")
        rotating.rotate_identifier(
            self.app,
            self.hab,
            new_signing_threshold,
            next_signing_threshold,
            key_count,
            toad,
            cuts=cuts,
            adds=adds
        )

    def _on_doer_event(self, doer_name: str, event_type: str, data: dict):
        """
        Handle doer events from the signal bridge.

        Args:
            doer_name: Name of the doer that emitted the event
            event_type: Type of event
            data: Event data dictionary
        """
        logger.info(f"RotateIdentifierDialog received doer_event: {doer_name} - {event_type}")

        if doer_name == "RotateDoer":
            if event_type == "rotation_complete":
                logger.info(f"Rotation complete: {data.get('alias')} ({data.get('pre')})")

                # Close the rotate dialog
                self.close()

                # Check if witnesses need authentication
                if data.get('has_witnesses'):
                    logger.info("Opening authentication dialog for witnesses")
                    # Open authentication dialog
                    auth_dialog = WitnessAuthenticationDialog(
                        app=self.app,
                        hab=self.hab,
                        witness_ids=list(self.hab.kever.wits),
                        auth_only=False,  # This is initial authentication after rotation
                        parent=self.parent()
                    )
                    auth_dialog.open()
                else:
                    logger.info("No witnesses to authenticate, rotation complete")
                    if hasattr(self.app, 'plugin_manager') and self.app.plugin_manager:
                        import asyncio
                        asyncio.ensure_future(self.app.plugin_manager.after_identifier_authenticated(self.app.vault, self.hab))

            elif event_type == "rotation_failed":
                logger.error(f"Rotation failed: {data.get('error')}")
                self.show_error(f"Rotation failed: {data.get('error')}")