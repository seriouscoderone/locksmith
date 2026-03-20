# -*- encoding: utf-8 -*-
"""
locksmith.ui.vault.shared.witness_auth_mixin module

Shared mixin for witness authentication dialogs.
"""
import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QLabel, QHBoxLayout, QFrame
from keri import help

from locksmith.ui import colors
from locksmith.ui.toolkit.widgets.fields import FloatingLabelLineEdit

logger = help.ogler.getLogger(__name__)


class WitnessAuthenticationMixin:
    """
    Mixin providing shared witness authentication methods.

    Subclasses must provide:
        - self.app: LocksmithApplication instance
        - self.hab: Habery instance (identifier)
        - self.witness_ids: list[str] of witness IDs
        - self.auth_only: bool
        - self.passcode_fields: dict
        - self.witness_info: dict
        - self.batch_groups: list
        - self.individual_witnesses: list
    """

    def _load_witness_info(self):
        """Load witness information from org contacts."""
        for wit_id in self.witness_ids:
            # Try to find witness in org contacts
            for remote_id in self.app.vault.org.list():
                if remote_id.get('id') == wit_id:
                    self.witness_info[wit_id] = remote_id
                    break
            else:
                # Witness not found in contacts, create minimal record
                self.witness_info[wit_id] = {
                    'id': wit_id,
                    'alias': wit_id[:12] + '...',  # Truncated ID as fallback alias
                    'oobi': None
                }

    def _organize_witnesses_by_batch(self):
        """
        Organize witnesses into batch groups and individual witnesses.

        Checks the database for witness batches associated with this identifier.
        If witnesses belong to the same batch, they share a single OTP.
        """
        # Get witness batches from plugin manager
        wit_batches = None
        if hasattr(self.app, 'plugin_manager') and self.app.plugin_manager:
            wit_batches = self.app.plugin_manager.get_witness_batches(self.app.vault, self.hab.pre)

        remaining_witnesses = set(self.witness_ids)

        if wit_batches:
            logger.info(f"Found {len(wit_batches.batches)} batch(es) for {self.hab.pre}")

            # Check each batch for witnesses that need authentication
            for batch_index, batch in enumerate(wit_batches.batches):
                # Find witnesses in this batch that need auth
                intersection = remaining_witnesses.intersection(set(batch))

                if intersection:
                    batch_label = f"Witness Batch {batch_index + 1}"
                    self.batch_groups.append((batch_label, list(intersection)))
                    # Remove these witnesses from remaining
                    remaining_witnesses -= intersection
                    logger.info(f"Batch {batch_index + 1}: {len(intersection)} witnesses")

        # Remaining witnesses get individual authentication
        self.individual_witnesses = list(remaining_witnesses)

        logger.info(f"Batch groups: {len(self.batch_groups)}, Individual witnesses: {len(self.individual_witnesses)}")

    def _build_witness_fields(self, layout):
        """Build the witness ID labels and passcode fields, supporting both batch and individual auth."""
        # First, add batch groups
        for batch_label, batch_witness_ids in self.batch_groups:
            batch_layout = QHBoxLayout()

            labels_layout = QVBoxLayout()
            labels_layout.setSpacing(4)

            # Batch label
            batch_label_widget = QLabel(batch_label)
            batch_label_widget.setStyleSheet(
                "font-size: 15px; color: #1A1C20; font-weight: 700;"
            )
            batch_label_widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            labels_layout.addWidget(batch_label_widget)

            # List each witness ID in the batch
            for wit_id in batch_witness_ids:
                witness_record = self.witness_info.get(wit_id, {})
                alias = witness_record.get('alias', wit_id[:12] + '...')

                wit_label = QLabel(f"• {alias} ({wit_id[:16]}...)")
                wit_label.setStyleSheet(
                    "font-size: 12px; color: #666; font-weight: 400;"
                )
                wit_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                labels_layout.addWidget(wit_label)

            batch_layout.addLayout(labels_layout)

            # Add vertical divider
            v_divider = QFrame()
            v_divider.setFrameShape(QFrame.Shape.VLine)
            v_divider.setFrameShadow(QFrame.Shadow.Sunken)
            v_divider.setStyleSheet("color: #D1D5DB;")
            batch_layout.addWidget(v_divider)

            batch_layout.addSpacing(15)

            # Single passcode field for the batch
            passcode_field = FloatingLabelLineEdit(label_text="One Time Passcode")
            passcode_field.setFixedWidth(220)
            batch_layout.addWidget(passcode_field, alignment=Qt.AlignmentFlag.AlignVCenter)


            layout.addLayout(batch_layout)

            # Store reference with batch key (use tuple of witness IDs)
            batch_key = tuple(sorted(batch_witness_ids))
            self.passcode_fields[batch_key] = passcode_field

            layout.addSpacing(15)

        # Then, add individual witnesses
        for witness_id in self.individual_witnesses:
            witness_record = self.witness_info.get(witness_id, {})
            alias = witness_record.get('alias', witness_id[:12] + '...')

            witness_layout = QHBoxLayout()

            labels_layout = QVBoxLayout()

            witness_alias_label = QLabel(alias)
            witness_alias_label.setStyleSheet(
                f"font-size: 15px; color: {colors.TEXT_DARK}; font-weight: 700;"
            )
            witness_alias_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            labels_layout.addWidget(witness_alias_label)

            witness_prefix_label = QLabel(witness_id)
            witness_prefix_label.setStyleSheet(
                f"font-size: 13px; color: {colors.TEXT_DARK}; font-weight: 400;"
            )
            witness_prefix_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            labels_layout.addWidget(witness_prefix_label)

            witness_layout.addLayout(labels_layout)

            # Add vertical divider
            v_divider = QFrame()
            v_divider.setFrameShape(QFrame.Shape.VLine)
            v_divider.setFrameShadow(QFrame.Shadow.Sunken)
            v_divider.setStyleSheet(f"color: {colors.BORDER};")  # Light gray color
            witness_layout.addWidget(v_divider)

            witness_layout.addSpacing(15)

            # Passcode field
            passcode_field = FloatingLabelLineEdit(label_text="One Time Passcode")
            passcode_field.setFixedWidth(180)
            witness_layout.addWidget(passcode_field)

            layout.addLayout(witness_layout)

            # Store reference
            self.passcode_fields[witness_id] = passcode_field

            layout.addSpacing(15)

    def get_authentication_codes(self) -> list[str]:
        """
        Get the authentication codes in format expected by KERI.

        Returns:
            List of "witness_id:passcode" strings for witnesses with codes entered.
            For batch groups, expands to include all witness IDs in the batch.
        """
        codes = []
        for key, field in self.passcode_fields.items():
            passcode = field.text().strip()
            if passcode:
                # Check if key is a batch (tuple) or individual witness (string)
                if isinstance(key, tuple):
                    # Batch: expand to all witnesses in the batch
                    for witness_id in key:
                        codes.append(f"{witness_id}:{passcode}")
                    logger.info(f"Added batch code for {len(key)} witnesses")
                else:
                    # Individual witness
                    codes.append(f"{key}:{passcode}")
        return codes

    def _on_rotate(self):
        """Handle rotate button click - validate and accept."""
        # Clear any previous errors
        self.clear_error()

        # Validate that at least one code is provided
        has_any_code = False
        all_valid = True
        error_messages = []

        for key, field in self.passcode_fields.items():
            passcode = field.text().strip()

            if passcode:
                has_any_code = True
                # Validate 6-digit format
                if not re.match(r'^\d{6}$', passcode):
                    all_valid = False
                    # Handle both batch keys (tuples) and individual witness IDs (strings)
                    if isinstance(key, tuple):
                        # Find the batch label for this key
                        batch_label = next(
                            (label for label, wits in self.batch_groups
                             if tuple(sorted(wits)) == key),
                            "Batch"
                        )
                        error_messages.append(f"{batch_label}: Invalid code (must be 6 digits)")
                    else:
                        witness_record = self.witness_info.get(key, {})
                        alias = witness_record.get('alias', key[:12] + '...')
                        error_messages.append(f"{alias}: Invalid code (must be 6 digits)")

        if not has_any_code:
            self.show_error("Please enter at least one passcode")
            return

        if not all_valid:
            error_message = "Invalid passcode format:\n" + "\n".join(error_messages)
            self.show_error(error_message)
            return

        logger.info(f"Authenticating {len([f for f in self.passcode_fields.values() if f.text().strip()])} witnesses")

        # Get authentication codes
        codes = self.get_authentication_codes()

        # If signals is provided, emit the codes instead of authenticating directly
        if hasattr(self, 'signals') and self.signals:
            logger.info(f"Emitting {len(codes)} auth codes via signals")
            self.signals.auth_codes_entered.emit({'codes': codes})
            self.accept()
            return

        # Import here to avoid circular dependency
        from locksmith.core.rotating import authenticate_witnesses

        # Trigger authentication doer (will emit success/failure events)
        authenticate_witnesses(
            app=self.app,
            hab=self.hab,
            codes=codes,
            proxy=None  # TODO: Add proxy support if needed for delegated identifiers
        )

        # Don't call self.accept() here - wait for authentication result events
