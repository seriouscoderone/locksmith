# -*- encoding: utf-8 -*-
"""
locksmith.ui.vault.identifiers.identifier_sections module

Shared mixin providing reusable section builders for identifier view dialogs.
Used by both local vault ViewIdentifierDialog and plugin-specific ViewAccountIdentifierDialog.
"""
import base64
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QHBoxLayout, QCheckBox, QFrame
)
from keri import help

from locksmith.core import habbing
from locksmith.ui import colors
from locksmith.ui.toolkit.widgets import LocksmithButton
from locksmith.ui.toolkit.widgets.buttons import LocksmithCheckbox, LocksmithCopyButton, LocksmithIconButton
from locksmith.ui.toolkit.widgets.fields import FloatingLabelComboBox, LocksmithLineEdit, LocksmithPlainTextEdit
from locksmith.ui.vault.identifiers.authenticate import WitnessAuthenticationDialog

logger = help.ogler.getLogger(__name__)


class IdentifierViewSectionsMixin:
    """
    Mixin providing shared section builders for identifier view dialogs.
    
    Subclasses must provide:
        - self.app: LocksmithApplication instance
        - self.hab: Habery instance (identifier)
        - self.details: dict from habbing.get_identifier_details()
    """
    
    # Required attributes (type hints for IDE support)
    app: Any
    hab: Any
    details: dict[str, Any]
    identifier_alias: str

    # Optional attributes that may be set by build methods
    resubmit_button: LocksmithButton | None = None
    oobi_role_dropdown: FloatingLabelComboBox | None = None
    oobi_display_container: QWidget | None = None
    oobi_display_layout: QVBoxLayout | None = None
    delegate_checkboxes: list[QCheckBox] | None = None
    confirm_delegates_button: LocksmithButton | None = None

    def _build_aid_section(self, layout):
        """Build the AID section with copy button."""
        aid_section = QVBoxLayout()

        aid_label_row = QHBoxLayout()
        aid_label_row.setSpacing(5)
        aid_label = QLabel("AID")
        aid_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        aid_label_row.addWidget(aid_label)
        copy_aid_button = LocksmithIconButton(":/assets/material-icons/content_copy.svg", tooltip="Copy AID")
        copy_aid_button.setFixedHeight(36)
        copy_aid_button.clicked.connect(lambda: self._copy_to_clipboard(self.details['pre']))
        aid_label_row.addWidget(copy_aid_button)
        aid_label_row.addStretch()
        layout.addLayout(aid_label_row)

        aid_field = LocksmithLineEdit("AID")
        aid_field.setText(self.details['pre'])
        aid_field.setReadOnly(True)
        aid_field.setCursorPosition(0)
        aid_field.setMinimumWidth(360)
        aid_field.setProperty("class", "monospace")
        aid_field._update_styling()  # Force style refresh
        aid_section.addWidget(aid_field)

        layout.addLayout(aid_section)

    def _build_kel_section(self, layout):
        """Build the KEL section with copy button."""
        kel_label_row = QHBoxLayout()
        kel_label_row.setSpacing(5)
        kel_label = QLabel("Key Event Log")
        kel_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        kel_label_row.addWidget(kel_label)

        # Copy button
        copy_kel_button = LocksmithIconButton(":/assets/material-icons/content_copy.svg", tooltip="Copy KEL")
        copy_kel_button.setFixedHeight(36)
        copy_kel_button.clicked.connect(lambda: self._copy_to_clipboard(self.details['kel']))
        kel_label_row.addWidget(copy_kel_button)
        kel_label_row.addStretch()
        layout.addLayout(kel_label_row)

        # KEL value (multiline, read-only)
        kel_field = LocksmithPlainTextEdit()
        kel_field.setPlainText(self.details['pretty_kel'])
        kel_field.setReadOnly(True)
        kel_field.setMinimumHeight(60)
        kel_field.setMaximumHeight(320)
        # kel_field.setMaximumWidth(470)
        kel_field.setProperty("class", "monospace")
        kel_field._update_styling()  # Force style refresh
        layout.addWidget(kel_field)

    def _build_key_type_section(self, layout):
        """Build the key type section."""
        key_type_row = QHBoxLayout()
        key_type_label = QLabel("Key Type:")
        key_type_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        key_type_row.addWidget(key_type_label)

        key_type_value = QLabel(self.details['key_type'])
        key_type_value.setStyleSheet("font-size: 14px;")
        key_type_row.addWidget(key_type_value)
        key_type_row.addStretch()
        layout.addLayout(key_type_row)

    def _copy_to_clipboard(self, text):
        """Copy text to clipboard."""
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        logger.info(f"Copied to clipboard: {text[:50]}...")

    def _on_doer_event(self, doer_name: str, event_type: str, data: dict):
        """
        Handle doer events from the signal bridge.

        Args:
            doer_name: Name of the doer that emitted the event
            event_type: Type of event
            data: Event data dictionary
        """
        logger.debug(f"{self.__class__.__name__} received doer_event: {doer_name} - {event_type}")

        # Handle witness receipt completion
        if doer_name == "WitnessReceipt" and event_type == "receipts_complete":
            if data.get('pre') == self.hab.pre:
                logger.info(f"Witness receipts complete for {self.identifier_alias}")
                # Re-enable resubmit button if it exists
                if hasattr(self, 'resubmit_button'):
                    self.resubmit_button.setEnabled(False)
                    self.resubmit_button.setText("Receipts Complete")

    @staticmethod
    def _build_kel_info_section(layout: QVBoxLayout, details: dict[str, Any]) -> None:
        """
        Build the KEL information section.

        Args:
            layout: Parent layout to add section to
            details: Identifier details dict from habbing.get_identifier_details()
        """
        # Container frame
        info_frame = QFrame()
        info_frame.setStyleSheet(f"""
            QFrame {{
                border: 2px solid {colors.BORDER};
                border-radius: 8px;
                background-color: {colors.BACKGROUND_CONTENT};
            }}
        """)
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(10, 10, 10, 10)
        info_layout.setSpacing(10)

        # Title
        info_title = QLabel("Key Event Log Information")
        info_title.setStyleSheet("font-weight: bold; font-size: 14px; border: none;")
        info_layout.addWidget(info_title)

        # Do Not Delegate checkbox (if applicable)
        if details.get('do_not_delegate'):
            dnd_row = QHBoxLayout()
            dnd_label = QLabel("Do Not Delegate:")
            dnd_label.setStyleSheet("font-weight: 500; font-size: 13px; border: none;")
            dnd_row.addWidget(dnd_label)

            dnd_checkbox = LocksmithCheckbox()
            dnd_checkbox.setChecked(True)
            dnd_checkbox.setEnabled(False)
            dnd_row.addWidget(dnd_checkbox)
            dnd_row.addStretch()
            info_layout.addLayout(dnd_row)

        # Sequence Number
        sn_row = QHBoxLayout()
        sn_label = QLabel("Sequence Number:")
        sn_label.setStyleSheet("font-weight: 500; font-size: 13px; border: none;")
        sn_row.addWidget(sn_label)

        sn_value = QLabel(str(details.get('sequence_number', 0)))
        sn_value.setStyleSheet("font-size: 13px; border: none;")
        sn_row.addWidget(sn_value)
        sn_row.addStretch()
        info_layout.addLayout(sn_row)

        # Witnesses section
        witnesses_label = QLabel("Witnesses")
        witnesses_label.setStyleSheet("font-weight: bold; font-size: 14px; border: none; margin-top: 10px;")
        info_layout.addWidget(witnesses_label)

        # Witness details in indented container
        witnesses_container = QWidget()
        witnesses_container.setStyleSheet("border: none;")
        witnesses_layout = QVBoxLayout(witnesses_container)
        witnesses_layout.setContentsMargins(20, 0, 0, 0)
        witnesses_layout.setSpacing(5)

        # Count
        count_row = QHBoxLayout()
        count_label = QLabel("Count:")
        count_label.setStyleSheet("font-weight: 500; font-size: 13px; border: none;")
        count_row.addWidget(count_label)

        count_value = QLabel(str(details.get('witness_count', 0)))
        count_value.setStyleSheet("font-size: 13px; border: none;")
        count_row.addWidget(count_value)
        count_row.addStretch()
        witnesses_layout.addLayout(count_row)

        # Receipt
        receipt_row = QHBoxLayout()
        receipt_label = QLabel("Receipt:")
        receipt_label.setStyleSheet("font-weight: 500; font-size: 13px; border: none;")
        receipt_row.addWidget(receipt_label)

        receipt_value = QLabel(str(details.get('witness_receipts', 0)))
        receipt_value.setStyleSheet("font-size: 13px; border: none;")
        receipt_row.addWidget(receipt_value)
        receipt_row.addStretch()
        witnesses_layout.addLayout(receipt_row)

        # Threshold
        threshold_row = QHBoxLayout()
        threshold_label = QLabel("Threshold:")
        threshold_label.setStyleSheet("font-weight: 500; font-size: 13px; border: none;")
        threshold_row.addWidget(threshold_label)

        threshold_value = QLabel(str(details.get('witness_threshold', 0)))
        threshold_value.setStyleSheet("font-size: 13px; border: none;")
        threshold_row.addWidget(threshold_value)
        threshold_row.addStretch()
        witnesses_layout.addLayout(threshold_row)

        info_layout.addWidget(witnesses_container)

        # Public keys section
        keys_label = QLabel("Public Keys")
        keys_label.setStyleSheet("font-weight: bold; font-size: 14px; border: none; margin-top: 10px;")
        info_layout.addWidget(keys_label)

        # Keys container
        keys_container = QWidget()
        keys_container.setStyleSheet("border: none;")
        keys_layout = QVBoxLayout(keys_container)
        keys_layout.setContentsMargins(20, 0, 0, 0)
        keys_layout.setSpacing(5)

        for key in details.get('public_keys', []):
            key_label = QLabel(key)
            key_label.setStyleSheet("font-family: monospace; font-size: 11px; border: none;")
            key_label.setWordWrap(True)
            keys_layout.addWidget(key_label)

        info_layout.addWidget(keys_container)

        layout.addWidget(info_frame)

    def _build_resubmit_section(self, layout: QVBoxLayout, details: dict[str, Any]) -> None:
        """
        Build the resubmit section if witness receipts are missing.
        
        Args:
            layout: Parent layout to add section to
            details: Identifier details dict
        """
        if details.get('needs_resubmit'):
            resubmit_row = QHBoxLayout()
            self.resubmit_button = LocksmithButton("Resubmit")
            self.resubmit_button.clicked.connect(self._on_resubmit)  # type: ignore
            resubmit_row.addWidget(self.resubmit_button)
            resubmit_row.addStretch()
            layout.addLayout(resubmit_row)

    def _build_oobi_section(self, layout: QVBoxLayout) -> None:
        """Build the OOBI generation section with role dropdown and QR code."""
        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet(f"background-color: {colors.DIVIDER};")
        layout.addWidget(divider)

        role_row = QHBoxLayout()
        oobi_label = QLabel("Generate OOBI with role:")
        oobi_label.setStyleSheet("font-weight: bold; font-size: 14px;")

        role_row.addWidget(oobi_label)

        self.oobi_role_dropdown = FloatingLabelComboBox("Role")
        self.oobi_role_dropdown.addItems(["Witness", "Controller", "Mailbox"])
        self.oobi_role_dropdown.setCurrentText("Witness")
        self.oobi_role_dropdown.currentTextChanged.connect(self._on_oobi_role_changed)
        role_row.addWidget(self.oobi_role_dropdown)
        role_row.addStretch()
        layout.addLayout(role_row)

        # OOBI display container
        self.oobi_display_container = QWidget()
        self.oobi_display_layout = QVBoxLayout(self.oobi_display_container)
        self.oobi_display_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.oobi_display_container)

        # Generate initial OOBI
        self._generate_oobi("witness")

    def _build_refresh_keystate_section(self, layout: QVBoxLayout) -> None:
        """Build the refresh key state section for group multisig."""
        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet(f"background-color: {colors.DIVIDER};")
        layout.addWidget(divider)

        refresh_row = QHBoxLayout()
        refresh_label = QLabel("Refresh Key State:")
        refresh_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        refresh_row.addWidget(refresh_label)

        refresh_button = LocksmithButton("Refresh")
        refresh_button.clicked.connect(self._on_refresh_keystate)
        refresh_row.addWidget(refresh_button)
        refresh_row.addStretch()
        layout.addLayout(refresh_row)

    # --- Helper methods ---

    def _on_resubmit(self) -> None:
        """Handle resubmit button click."""
        auth_dialog = WitnessAuthenticationDialog(
            app=self.app,
            hab=self.hab,
            witness_ids=list(self.hab.kever.wits),
            auth_only=True,  # This is initial authentication after rotation
        )
        auth_dialog.open()

    def _on_oobi_role_changed(self, role_text: str) -> None:
        """Handle OOBI role dropdown change."""
        role_map = {
            "Witness": "witness",
            "Controller": "controller",
            "Mailbox": "mailbox"
        }
        role = role_map.get(role_text, "witness")
        self._generate_oobi(role)

    def _generate_oobi(self, role: str) -> None:
        """Generate and display OOBI for the selected role."""
        if not self.oobi_display_layout:
            return
            
        # Clear existing display
        while self.oobi_display_layout.count():
            child = self.oobi_display_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Get OOBI
        oobi_result = habbing.generate_oobi(self.app, self.hab, role)

        if not oobi_result['success'] or not oobi_result['oobi']:
            error_label = QLabel(f"No {role} OOBIs available")
            error_label.setStyleSheet(f"color: {colors.TEXT_MUTED}; font-style: italic;")
            self.oobi_display_layout.addWidget(error_label)
            return

        oobi_url = oobi_result['oobi']

        # URL with copy button
        url_row = QHBoxLayout()
        url_label = QLabel(oobi_url)
        url_label.setStyleSheet("font-size: 11px;")
        url_label.setWordWrap(True)
        url_row.addWidget(url_label)

        copy_button = LocksmithCopyButton()
        copy_button.set_copy_content(oobi_url)
        url_row.addWidget(copy_button)

        self.oobi_display_layout.addLayout(url_row)
        self.oobi_display_layout.addSpacing(10)

        # QR Code
        if oobi_result.get('qr_code'):
            qr_label = QLabel()
            pixmap = QPixmap()
            pixmap.loadFromData(base64.b64decode(oobi_result['qr_code']))
            qr_label.setPixmap(pixmap.scaled(330, 330, Qt.AspectRatioMode.KeepAspectRatio))
            qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.oobi_display_layout.addWidget(qr_label)

    def _on_confirm_delegates(self) -> None:
        """Handle confirm delegates button click."""
        if not self.delegate_checkboxes:
            return

        # Get selected delegates
        selected_delegates = []
        for checkbox in self.delegate_checkboxes:
            if checkbox.isChecked():
                delegate_data = checkbox.property('delegate_data')
                selected_delegates.append(delegate_data)

        if not selected_delegates:
            logger.info("No delegates selected for confirmation")
            return

        # Confirm delegates
        result = habbing.confirm_delegates(self.app, self.hab, selected_delegates)
        if result['success']:
            logger.info(f"Confirmed {len(selected_delegates)} delegate(s)")
            # TODO: Refresh the delegates section
        else:
            logger.error(f"Delegate confirmation failed: {result.get('message', 'Unknown error')}")

    def _on_refresh_keystate(self) -> None:
        """Handle refresh key state button click."""
        result = habbing.refresh_keystate(self.app, self.hab)
        if result['success']:
            logger.info(f"Refreshed key state for {self.hab.name}")
        else:
            logger.error(f"Refresh key state failed: {result.get('message', 'Unknown error')}")

