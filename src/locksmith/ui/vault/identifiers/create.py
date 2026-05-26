# -*- encoding: utf-8 -*-
"""
locksmith.ui.vaults.create module

Dialog for creating new vaults
"""
import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QButtonGroup
from keri import help
from keri.core import signing

from locksmith.core import habbing
from locksmith.ui import colors
from locksmith.ui.toolkit.widgets import (
    LocksmithDialog,
    FloatingLabelLineEdit,
    LocksmithButton,
    LocksmithInvertedButton,
    LocksmithTextListWidget,
)
from locksmith.ui.toolkit.widgets.buttons import LocksmithRadioButton, LocksmithCheckbox
from locksmith.ui.toolkit.widgets.collapsible import CollapsibleSection
from locksmith.ui.toolkit.widgets.fields import FloatingLabelComboBox, LocksmithLineEdit
from locksmith.ui.vault.shared.delegation_mixin import DelegationMixin

logger = help.ogler.getLogger(__name__)

# 44-char base64url AID prefix
AID_PATTERN = re.compile(r'^[A-Za-z0-9_-]{44}$')


class CreateIdentifierDialog(DelegationMixin, LocksmithDialog):
    """Dialog for initializing a new vault."""

    identifier_created = Signal(str, str)
    identifier_creation_failed = Signal(str)

    def __init__(self, icon_path, app, parent=None, config=None):
        """
        Initialize the CreateVaultDialog.

        Args:
            parent: Parent widget (typically main window)
            config: LocksmithConfig instance
        """
        self.config = config
        self.app = app

        # Create content widget
        content_widget = QWidget()
        content_widget.setStyleSheet(f"background-color: {colors.BACKGROUND_CONTENT};")
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addSpacing(10)

        self.name_field = FloatingLabelLineEdit("Alias")
        self.name_field.setFixedWidth(360)
        layout.addWidget(self.name_field)
        layout.addSpacing(15)

        # Create button row
        button_row = QHBoxLayout()
        self.cancel_button = LocksmithInvertedButton("Cancel")
        button_row.addWidget(self.cancel_button)
        button_row.addSpacing(10)
        self.create_button = LocksmithButton("Create")
        button_row.addWidget(self.create_button)

        # Create title content
        title_content_widget = QWidget()
        title_content = QHBoxLayout()
        icon = QIcon(icon_path)
        icon_label = QLabel()
        icon_label.setPixmap(icon.pixmap(32, 32))
        icon_label.setFixedSize(32, 32)
        title_content.addWidget(icon_label)

        title_label = QLabel("  Add a Local Identifier")
        title_label.setStyleSheet("font-size: 16px;")
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

        # Initial size sized for three collapsed section headers + alias + buttons,
        # with no scrollbar. Expands further when a section opens.
        self.setFixedSize(420, 430)

        # Connect buttons
        self.cancel_button.clicked.connect(self.close)
        self.create_button.clicked.connect(self.create_identifier)

        # ── Keys & Signing ───────────────────────────────────────────────
        # QToolButton treats a single `&` as a mnemonic-accelerator marker;
        # double up so it renders literally.
        self.keys_section = CollapsibleSection(title="Keys && Signing", parent=self)
        keys_widget = QWidget()
        keys_layout = QVBoxLayout(keys_widget)
        keys_layout.addSpacing(20)

        key_type_label = QLabel("Key Type")
        key_type_label.setStyleSheet("font-weight: 600; font-size: 15px;")
        keys_layout.addWidget(key_type_label)
        keys_layout.addSpacing(15)

        self.key_chain_radio = LocksmithRadioButton("Key Chain     ")
        self.random_key_radio = LocksmithRadioButton("Random Key    ")
        self.key_chain_radio.setChecked(True)

        self.key_type_button_group = QButtonGroup(self)
        self.key_type_button_group.addButton(self.key_chain_radio)
        self.key_type_button_group.addButton(self.random_key_radio)

        radio_layout = QHBoxLayout()
        radio_layout.setSpacing(10)
        radio_layout.addWidget(self.key_chain_radio)
        radio_layout.addWidget(self.random_key_radio)
        radio_layout.addStretch()
        keys_layout.addLayout(radio_layout)

        default_salt = signing.Salter().qb64[2:23]
        self.key_salt_field = FloatingLabelLineEdit("Key Salt", password_mode=True)
        self.key_salt_field.setText(default_salt)
        keys_layout.addWidget(self.key_salt_field)

        self.key_chain_radio.toggled.connect(self._on_key_type_radio_changed)
        self.random_key_radio.toggled.connect(self._on_key_type_radio_changed)

        keys_layout.addSpacing(15)

        keys_and_thresholds_label = QLabel("Number of Keys / Thresholds")
        keys_and_thresholds_label.setStyleSheet("font-weight: 600; font-size: 15px;")
        keys_layout.addWidget(keys_and_thresholds_label)
        keys_layout.addSpacing(15)

        signing_keys_and_thresholds_layout = QHBoxLayout()
        self.num_signing_keys_field = FloatingLabelLineEdit("Signing Keys")
        self.num_signing_keys_field.setText("1")
        self.signing_threshold_field = FloatingLabelLineEdit("Signing Threshold")
        self.signing_threshold_field.setText("1")
        signing_keys_and_thresholds_layout.addWidget(self.num_signing_keys_field)
        signing_keys_and_thresholds_layout.addWidget(self.signing_threshold_field)
        keys_layout.addLayout(signing_keys_and_thresholds_layout)

        rotation_keys_and_thresholds_layout = QHBoxLayout()
        self.num_rotation_keys_field = FloatingLabelLineEdit("Rotation Keys")
        self.num_rotation_keys_field.setText("1")
        self.rotation_threshold_field = FloatingLabelLineEdit("Rotation Threshold")
        self.rotation_threshold_field.setText("1")
        rotation_keys_and_thresholds_layout.addWidget(self.num_rotation_keys_field)
        rotation_keys_and_thresholds_layout.addWidget(self.rotation_threshold_field)
        keys_layout.addLayout(rotation_keys_and_thresholds_layout)

        # EstOnly is a KEL semantic about establishment vs interaction events,
        # so it belongs with the key/signing controls.
        self.establishment_only_checkbox = LocksmithCheckbox("Establishment Only")
        keys_layout.addWidget(self.establishment_only_checkbox)

        self.keys_section.set_content_layout(keys_layout)
        layout.addWidget(self.keys_section)

        # ── Delegation ───────────────────────────────────────────────────
        self.delegation_section = CollapsibleSection(title="Delegation", parent=self)
        delegation_widget = QWidget()
        delegation_layout = QVBoxLayout(delegation_widget)
        delegation_layout.addSpacing(20)

        delegation_radio_layout = QHBoxLayout()
        self.no_delegation_radio = LocksmithRadioButton("None")
        self.local_delegation_radio = LocksmithRadioButton("Local")
        self.remote_delegation_radio = LocksmithRadioButton("Remote")

        self.delegation_button_group = QButtonGroup(self)
        self.delegation_button_group.addButton(self.no_delegation_radio)
        self.delegation_button_group.addButton(self.local_delegation_radio)
        self.delegation_button_group.addButton(self.remote_delegation_radio)
        self.no_delegation_radio.setChecked(True)

        delegation_radio_layout.addWidget(self.no_delegation_radio)
        delegation_radio_layout.addSpacing(10)
        delegation_radio_layout.addWidget(self.local_delegation_radio)
        delegation_radio_layout.addSpacing(10)
        delegation_radio_layout.addWidget(self.remote_delegation_radio)
        delegation_radio_layout.addStretch()
        delegation_layout.addLayout(delegation_radio_layout)
        delegation_layout.addSpacing(15)

        self.delegator_dropdown = FloatingLabelComboBox("Delegator")
        self.delegator_dropdown.setFixedWidth(360)
        self.delegator_dropdown.addItem("None")
        delegation_layout.addWidget(self.delegator_dropdown)
        self.delegator_dropdown.hide()

        self.delegate_proxy_dropdown = FloatingLabelComboBox("Delegate Proxy")
        self.delegate_proxy_dropdown.setFixedWidth(360)
        self.delegate_proxy_dropdown.addItem("None")
        delegation_layout.addWidget(self.delegate_proxy_dropdown)
        self.delegate_proxy_dropdown.hide()

        self.no_delegation_radio.toggled.connect(self._on_delegation_radio_changed)
        self.local_delegation_radio.toggled.connect(self._on_delegation_radio_changed)
        self.remote_delegation_radio.toggled.connect(self._on_delegation_radio_changed)

        # Do Not Delegate is the inverse delegator role for this AID, so it
        # belongs with the Delegation controls.
        delegation_layout.addSpacing(8)
        self.do_not_delegate_checkbox = LocksmithCheckbox("Do Not Delegate")
        delegation_layout.addWidget(self.do_not_delegate_checkbox)

        self.delegation_section.set_content_layout(delegation_layout)
        layout.addWidget(self.delegation_section)

        # ── Witnesses ────────────────────────────────────────────────────
        self.witnesses_section = CollapsibleSection(title="Witnesses", parent=self)
        witnesses_widget = QWidget()
        witnesses_layout = QVBoxLayout(witnesses_widget)
        witnesses_layout.addSpacing(20)

        witnesses_help = QLabel(
            "Enter witness AID prefixes (44-character base64url). Each witness's "
            "KEL must already be resolved into this wallet via Contacts → Add OOBI; "
            "otherwise inception will fail. Witnesses must be non-transferable AIDs."
        )
        witnesses_help.setWordWrap(True)
        witnesses_help.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px;")
        witnesses_layout.addWidget(witnesses_help)
        witnesses_layout.addSpacing(8)

        self.witnesses_list = LocksmithTextListWidget(
            label="Witness AID prefix",
            parent=self,
            max_height=150,
        )
        witnesses_layout.addWidget(self.witnesses_list)
        witnesses_layout.addSpacing(15)

        toad_layout = QHBoxLayout()
        toad_label = QLabel("Threshold of Acceptable Duplicity:  ")
        toad_label.setStyleSheet("font-weight: 600; font-size: 15px;")
        toad_layout.addWidget(toad_label)
        self.toad_field = LocksmithLineEdit()
        self.toad_field.setText("0")
        self.toad_field.setFixedWidth(50)
        self.toad_field.setAlignment(Qt.AlignmentFlag.AlignCenter)
        toad_layout.addWidget(self.toad_field)
        toad_layout.addStretch()
        witnesses_layout.addLayout(toad_layout)

        self.witnesses_section.set_content_layout(witnesses_layout)
        layout.addWidget(self.witnesses_section)

        layout.addSpacing(10)

        # Link each collapsible section to the dialog so expand/collapse
        # animations resize the dialog height in sync.
        self.keys_section.set_dialog(self)
        self.delegation_section.set_dialog(self)
        self.witnesses_section.set_dialog(self)
        # Same coordination for the witnesses list so add/remove animations resize the dialog
        self.witnesses_list.set_dialog(self)
        layout.addStretch()  # Always add stretch after collapsible sections

        # Connect to vault signal bridge if available
        if self.app and hasattr(self.app, 'vault') and self.app.vault and hasattr(self.app.vault, 'signals'):
            self.app.vault.signals.doer_event.connect(self._on_doer_event)
            logger.info("CreateIdentifierDialog: Connected to vault signal bridge")

    def create_identifier(self):
        """Create a new identifier using the form values."""
        logger.info("Creating new identifier...")

        # Get alias
        alias = self.name_field.text().strip()
        if not alias:
            logger.error("Alias is required")
            # TODO: Show error message to user
            return

        # Determine key type
        if self.key_chain_radio.isChecked():
            key_type = 'salty'
        elif self.random_key_radio.isChecked():
            key_type = 'randy'
        else:
            key_type = 'salty'

        # Collect and validate witnesses. Each entered prefix must:
        #  1. Match the 44-char base64url AID format
        #  2. Already be in this wallet's Habery (KEL resolved via OOBI ahead of time)
        #  3. Be non-transferable (KERI requirement: witnesses cannot rotate)
        wits = self.witnesses_list.get_items()
        if wits:
            invalid: list[str] = []
            kevers = self.app.vault.hby.kevers if self.app and self.app.vault else {}
            for wit_pre in wits:
                if not AID_PATTERN.match(wit_pre):
                    invalid.append(f"{wit_pre} — not a valid 44-char AID prefix")
                    continue
                if wit_pre not in kevers:
                    invalid.append(
                        f"{wit_pre} — KEL not resolved in this wallet "
                        f"(add via Contacts → Add OOBI first)"
                    )
                    continue
                if kevers[wit_pre].transferable:
                    invalid.append(
                        f"{wit_pre} — transferable AID; witnesses must be non-transferable"
                    )
            if invalid:
                msg = "Invalid witnesses:\n  • " + "\n  • ".join(invalid)
                logger.error(msg)
                self.show_error(msg)
                return

        # Sanity-check TOAD against witness count up front; keripy will validate
        # more rigorously, but a clear message here is friendlier than its trace.
        try:
            toad = int(self.toad_field.text() or '0')
        except ValueError:
            self.show_error("Threshold of Acceptable Duplicity must be an integer")
            return
        if toad < 0:
            self.show_error("Threshold of Acceptable Duplicity must be ≥ 0")
            return
        if toad > len(wits):
            self.show_error(
                f"Threshold of Acceptable Duplicity ({toad}) cannot exceed the "
                f"number of witnesses ({len(wits)})"
            )
            return

        # Build parameters
        params = {
            'icount': self.num_signing_keys_field.text() or '1',
            'isith': self.signing_threshold_field.text() or '1',
            'ncount': self.num_rotation_keys_field.text() or '1',
            'nsith': self.rotation_threshold_field.text() or '1',
            'toad': str(toad),
            'wits': wits,
            'estOnly': self.establishment_only_checkbox.isChecked(),
            'DnD': self.do_not_delegate_checkbox.isChecked(),
        }

        # Add salt for key chain type
        if key_type == 'salty':
            params['salt'] = self.key_salt_field.text()

        # Determine delegation type
        if self.no_delegation_radio.isChecked():
            params['delegation_type'] = 'none'
        elif self.local_delegation_radio.isChecked():
            params['delegation_type'] = 'local'
            # Get delegator if selected
            delegator = self.delegator_dropdown.currentText()
            if delegator and delegator != "None":
                params['delpre'] = delegator.split('|')[0].strip() if '|' in delegator else delegator
        elif self.remote_delegation_radio.isChecked():
            params['delegation_type'] = 'remote'
            # Get delegator and proxy if selected
            delegator = self.delegator_dropdown.currentText()
            if delegator and delegator != "None":
                params['delpre'] = delegator.split('|')[0].strip() if '|' in delegator else delegator
            proxy = self.delegate_proxy_dropdown.currentText()
            if proxy and proxy != "None":
                params['proxy_alias'] = proxy.split('|')[0].strip() if '|' in proxy else proxy

        # Call the identifier creation function
        result = habbing.create_identifier(
            app=self.app,
            alias=alias,
            key_type=key_type,
            **params
        )

        # Handle result
        if result['success']:
            logger.info(f"Identifier creation initiated: {result['message']}")
            # Keep dialog open if async operation, it will close when InceptDoer signals completion
            if not result.get('async'):
                self.identifier_created.emit(alias, result.get('pre', ''))
                # Synchronous creation succeeded, close dialog
                self.close()
        else:
            logger.error(f"Identifier creation failed: {result['message']}")
            self.identifier_creation_failed.emit(result['message'])
            # TODO: Show error message to user

    def _on_doer_event(self, doer_name: str, event_type: str, data: dict):
        """
        Handle doer events from the signal bridge.

        Args:
            doer_name: Name of the doer that emitted the event
            event_type: Type of event
            data: Event data dictionary
        """
        # Only handle identifier creation doer events
        if doer_name != "InceptDoer":
            return

        logger.info(f"CreateIdentifierDialog received doer_event: {doer_name} - {event_type} - {data}")

        # Handle identifier creation completion
        if event_type == "identifier_created":
            logger.info(f"Identifier created successfully: {data.get('alias')} ({data.get('pre')})")
            self.identifier_created.emit(data.get('alias', ''), data.get('pre', ''))
            self.close()
        elif event_type == "identifier_creation_failed":
            logger.error(f"Identifier creation failed: {data.get('error')}")
            self.identifier_creation_failed.emit(data.get('error', ''))
            self.show_error(f"Identifier creation failed: {data.get('error')}")
            # Keep dialog open so user can try again

    def _on_key_type_radio_changed(self):
        """Handle key type radio button selection changes."""
        if self.key_chain_radio.isChecked():
            self.key_salt_field.show()
            self.num_signing_keys_field.show()
            self.num_rotation_keys_field.show()
        elif self.random_key_radio.isChecked():
            self.key_salt_field.hide()
            self.num_signing_keys_field.show()
            self.num_rotation_keys_field.show()

        # Salt field show/hide changes the Keys section's content height.
        self.keys_section.update_content_height()

    def _on_delegation_radio_changed(self):
        """Refresh dropdowns and the Delegation section's height."""
        super()._on_delegation_radio_changed()
        self.delegation_section.update_content_height()
