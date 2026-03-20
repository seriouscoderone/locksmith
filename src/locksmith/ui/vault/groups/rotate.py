# -*- encoding: utf-8 -*-
"""
locksmith.ui.vault.groups.rotate module

Dialog for rotating group multisig identifiers.
"""
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout
)
from keri import help

from locksmith.core import habbing, rotating, witnessing
from locksmith.core.grouping import get_contacts_for_multisig, rotate_group_identifier
from locksmith.ui import colors
from locksmith.ui.toolkit.widgets import (
    LocksmithDialog,
    LocksmithButton,
    LocksmithInvertedButton
)
from locksmith.ui.toolkit.widgets.dividers import LocksmithDivider
from locksmith.ui.toolkit.widgets.extensible import ExtensibleSelectorWidget
from locksmith.ui.toolkit.widgets.fields import LocksmithLineEdit
from locksmith.ui.vault.groups.authenticate import GroupWitnessAuthenticationDialog
from locksmith.ui.vault.shared.witness_rotation_mixin import WitnessRotationMixin

if TYPE_CHECKING:
    pass

logger = help.ogler.getLogger(__name__)


class RotateGroupIdentifierDialog(WitnessRotationMixin, LocksmithDialog):
    """Dialog for rotating group multisig identifiers."""

    def __init__(self, icon_path, app, identifier_alias, parent=None, prepopulate_witnesses=None):
        """
        Initialize the RotateGroupIdentifierDialog.

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

        # Build member selection sections
        members_divider = LocksmithDivider()
        layout.addSpacing(10)
        layout.addWidget(members_divider)
        layout.addSpacing(10)
        self._build_members_section(layout)

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
        # Base height includes info, params, members sections
        base_height = 730
        witness_section_height = 150  # Height per witness section

        dialog_height = base_height
        if self._unused_witnesses:
            dialog_height += witness_section_height
        if self._current_witnesses:
            dialog_height += witness_section_height

        self.setFixedSize(530, dialog_height)

        # Connect to vault signal bridge if available
        if self.app and hasattr(self.app, 'vault') and self.app.vault and hasattr(self.app.vault, 'signals'):
            self.app.vault.signals.doer_event.connect(self._on_doer_event)
            logger.info("RotateGroupIdentifierDialog: Connected to vault signal bridge")

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

        # Show local member identifier
        mhab_row = QHBoxLayout()
        mhab_label = QLabel("Local Member:")
        mhab_label.setStyleSheet("font-weight: bold; font-size: 15px;")
        mhab_row.addWidget(mhab_label)
        mhab_value = QLabel(f"{self.hab.mhab.name}")
        mhab_value.setStyleSheet(f"font-size: 14px; color: {colors.TEXT_DARK};")
        mhab_row.addWidget(mhab_value)
        mhab_row.addSpacing(30)
        info_section.addLayout(mhab_row)

        layout.addLayout(info_section)

    def _build_rotation_params_section(self, layout):
        """Build the rotation parameters section."""
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

    def _build_members_section(self, layout):
        """Build the signing and rotation members section."""
        # Signing Members
        smids_label = QLabel("Signing Members")
        smids_label.setStyleSheet("font-weight: bold; font-size: 15px;")
        layout.addWidget(smids_label)

        # Get current smids and build display items
        current_smids = list(self.hab.smids) if hasattr(self.hab, 'smids') and self.hab.smids else []
        contacts = get_contacts_for_multisig(self.app)

        # Build items for smids selector, pre-selecting current members
        smids_items = []
        for contact in contacts:
            display_text = contact.get('alias') or f"{contact['id'][:12]}..."
            smids_items.append((display_text, contact))

        self.smids_selector = ExtensibleSelectorWidget(
            dropdown_label="Select Signing Member",
            selector_dropdown_items=smids_items,
            # parent=self,
            max_scrollable_height=120
        )
        self.smids_selector.setFixedWidth(450)
        layout.addWidget(self.smids_selector)

        # Pre-populate with current signing members
        self._prepopulate_member_selector(self.smids_selector, current_smids, contacts)

        layout.addSpacing(10)

        # Rotation Members
        rmids_label = QLabel("Rotation Members")
        rmids_label.setStyleSheet("font-weight: bold; font-size: 15px;")
        layout.addWidget(rmids_label)

        # Build items for rmids selector
        rmids_items = []
        for contact in contacts:
            display_text = contact.get('alias') or f"{contact['id'][:12]}..."
            rmids_items.append((display_text, contact))

        self.rmids_selector = ExtensibleSelectorWidget(
            dropdown_label="Select Rotation Member",
            selector_dropdown_items=rmids_items,
            # parent=self,
            max_scrollable_height=120
        )
        self.rmids_selector.setFixedWidth(450)
        layout.addWidget(self.rmids_selector)

        # Pre-populate with current rotation members
        current_rmids = list(self.hab.rmids) if hasattr(self.hab, 'rmids') and self.hab.rmids else current_smids
        self._prepopulate_member_selector(self.rmids_selector, current_rmids, contacts)

    def _prepopulate_member_selector(self, selector, member_pres, contacts):
        """
        Pre-populate a member selector with current members.

        Args:
            selector: ExtensibleSelectorWidget to populate
            member_pres: List of member prefix strings
            contacts: List of contact dicts from get_contacts_for_multisig
        """
        # Map contact id to contact dict for fast lookup
        contact_map = {c['id']: c for c in contacts}

        for pre in member_pres:
            # Skip local member (already part of the group, not a remote contact)
            if pre == self.hab.mhab.pre:
                continue

            contact = contact_map.get(pre)
            if contact:
                display_text = contact.get('alias') or f"{contact['id'][:12]}..."
                selector.add_item_programmatically(display_text, contact)
            else:
                logger.warning(f"Could not find contact for member {pre}")

    def showEvent(self, event):
        """Override showEvent to connect the witness selectors to the dialog after it's shown."""
        super().showEvent(event)

        # Connect selectors to dialog for height animation coordination
        if hasattr(self, 'add_witness_selector') and self.add_witness_selector:
            self.add_witness_selector.set_dialog(self)
        if hasattr(self, 'remove_witness_selector') and self.remove_witness_selector:
            self.remove_witness_selector.set_dialog(self)
        if hasattr(self, 'smids_selector') and self.smids_selector:
            self.smids_selector.set_dialog(self)
        if hasattr(self, 'rmids_selector') and self.rmids_selector:
            self.rmids_selector.set_dialog(self)

        # Prepopulate witnesses if provided
        if self.prepopulate_witnesses and self.add_witness_selector:
            self._prepopulate_witnesses()

    def rotate_identifier(self):
        """Initiate group multisig rotation."""
        # Validate required fields
        if not self.new_signing_threshold_field.text().strip():
            self.show_error("New signing threshold is required")
            return

        if not self.next_signing_threshold_field.text().strip():
            self.show_error("Next signing threshold is required")
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

        # Build smids list: local mhab + selected signing members
        smids = [self.hab.mhab.pre]
        for text, data in self.smids_selector.get_selected_items():
            participant_pre = data.get('id')
            if participant_pre and participant_pre not in smids:
                smids.append(participant_pre)

        if len(smids) < 2:
            self.show_error("At least two signing members are required (including your local identifier)")
            return

        # Build rmids list: local mhab + selected rotation members
        rmids = [self.hab.mhab.pre]
        for text, data in self.rmids_selector.get_selected_items():
            participant_pre = data.get('id')
            if participant_pre and participant_pre not in rmids:
                rmids.append(participant_pre)

        if len(rmids) < 2:
            self.show_error("At least two rotation members are required (including your local identifier)")
            return

        # Clear any previous error before proceeding
        self.clear_error()

        # Execute group rotation
        logger.info(f"Initiating group rotation for {self.hab.name} with smids={smids}, rmids={rmids}")

        try:
            rotate_group_identifier(
                self.app,
                self.hab,
                isith=str(new_signing_threshold),
                nsith=str(next_signing_threshold),
                toad=str(toad),
                cuts=cuts,
                adds=adds,
                smids=smids,
                rmids=rmids
            )

            # Disable buttons while waiting
            self.show_success(f"Group Identifier rotation event sent to participants! If your mailbox is not already "
                              f"active, you may close this dialog and activate it now.")
            self.rotate_button.setText("Waiting...")
            self.rotate_button.setEnabled(False)

        except Exception as e:
            logger.exception(f"Failed to initiate group rotation: {e}")
            self.show_error(f"Failed to initiate rotation: {e}")

    def _on_doer_event(self, doer_name: str, event_type: str, data: dict):
        """
        Handle doer events from the signal bridge.

        Args:
            doer_name: Name of the doer that emitted the event
            event_type: Type of event
            data: Event data dictionary
        """
        if doer_name != "GroupMultisigRotateDoer":
            return

        logger.info(f"RotateGroupIdentifierDialog received doer_event: {doer_name} - {event_type}")

        if event_type == "group_rotation_exn_sent":
            logger.info(f"Rotation EXN sent, waiting for participants...")
            self.rotate_button.setText("Waiting...")
            self.rotate_button.setEnabled(False)

        elif event_type == "group_rotation_complete":
            logger.info(f"Group rotation complete: {data.get('alias')} ({data.get('pre')})")

            # Close the rotate dialog
            self.close()

            # Check if witnesses need authentication
            if data.get('needs_witness_auth'):
                shared_witnesses = data.get('shared_witnesses', [])
                logger.info(f"Opening authentication dialog for {len(shared_witnesses)} shared witnesses")
                auth_dialog = GroupWitnessAuthenticationDialog(
                    app=self.app,
                    hab=self.hab,
                    witness_ids=shared_witnesses,
                    auth_only=True,
                    parent=self.parent()
                )
                auth_dialog.open()
            else:
                logger.info("No shared witnesses to authenticate, rotation complete")

        elif event_type == "group_rotation_failed":
            logger.error(f"Group rotation failed: {data.get('error')}")
            self.show_error(f"Rotation failed: {data.get('error')}")
            self.rotate_button.setText("Rotate")
            self.rotate_button.setEnabled(True)
            self.close_button.setEnabled(True)