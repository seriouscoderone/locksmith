# -*- encoding: utf-8 -*-
"""
locksmith.ui.vault.shared.witness_rotation_mixin module

Mixin providing witness rotation UI methods shared between
single identifier and group multisig rotation dialogs.
"""
from PySide6.QtWidgets import QLabel

from keri import help

from locksmith.core import rotating
from locksmith.ui.toolkit.widgets.extensible import ExtensibleSelectorWidget

logger = help.ogler.getLogger(__name__)


class WitnessRotationMixin:
    """
    Mixin for witness rotation UI logic shared across rotation dialogs.

    Subclasses must provide the following attributes:
        - self.app: Application instance
        - self.hab: Habitat (identifier) instance
        - self.add_witness_selector (ExtensibleSelectorWidget): Selector for witnesses to rotate in
        - self.remove_witness_selector (ExtensibleSelectorWidget): Selector for witnesses to rotate out
        - self.toad_field (LocksmithLineEdit): Field displaying the TOAD value
        - self._unused_witnesses (list): Witnesses available to rotate in
        - self._current_witnesses (list): Witnesses currently on the identifier
        - self.prepopulate_witnesses (list): Witnesses to prepopulate in the add section
    """

    def _format_witness_display_name(self, witness: dict) -> str:
        """
        Format a witness for display in dropdowns using alias and full EID.

        Args:
            witness: Witness dict with 'alias' and 'id' keys

        Returns:
            Formatted string like "witnessme-wi-nyc-01 - BB0SSuchr..."
        """
        alias = witness.get('alias', 'Unknown')
        witness_id = witness.get('id', '')
        return f"{alias} - {witness_id}"

    def _build_witness_add_section(self, layout):
        """Build the witness selector section for rotating in witnesses."""
        logger.info(f"Unused witnesses: {self._unused_witnesses}")

        witness_add_label = QLabel("Rotate In Witnesses")
        witness_add_label.setStyleSheet("font-weight: bold; font-size: 15px;")
        layout.addWidget(witness_add_label)

        # Convert witness data to dropdown format: (display_name, data_dict)
        witness_items = [
            (self._format_witness_display_name(witness), witness)
            for witness in self._unused_witnesses
        ]

        self.add_witness_selector = ExtensibleSelectorWidget(
            dropdown_label="Select Witnesses",
            selector_dropdown_items=witness_items,
            max_scrollable_height=160
        )
        self.add_witness_selector.setFixedWidth(450)

        # Connect to update recommended TOAD when witnesses change
        self.add_witness_selector.itemAdded.connect(self._on_witness_selection_changed)
        self.add_witness_selector.itemRemoved.connect(self._on_witness_selection_changed)

        layout.addWidget(self.add_witness_selector)

    def _build_witness_remove_section(self, layout):
        """Build the witness selector section for rotating out witnesses."""
        logger.info(f"Current witnesses: {self._current_witnesses}")

        witness_remove_label = QLabel("Rotate Out Witnesses")
        witness_remove_label.setStyleSheet("font-weight: bold; font-size: 15px;")
        layout.addWidget(witness_remove_label)

        # Convert witness data to dropdown format: (display_name, data_dict)
        witness_items = [
            (self._format_witness_display_name(witness), witness)
            for witness in self._current_witnesses
        ]

        self.remove_witness_selector = ExtensibleSelectorWidget(
            dropdown_label="Select Witnesses",
            selector_dropdown_items=witness_items,
            max_scrollable_height=160
        )

        self.remove_witness_selector.setFixedWidth(450)

        # Connect to update recommended TOAD when witnesses change
        self.remove_witness_selector.itemAdded.connect(self._on_witness_selection_changed)
        self.remove_witness_selector.itemRemoved.connect(self._on_witness_selection_changed)

        layout.addWidget(self.remove_witness_selector)

    def _on_witness_selection_changed(self, _text, _data):
        """Update recommended TOAD when witness selections change."""
        self._update_recommended_toad()

    def _get_resulting_witness_count(self):
        """Calculate the witness count after rotation."""
        current_count = len(self.hab.kever.wits)

        adds_count = 0
        if self.add_witness_selector:
            adds_count = len(self.add_witness_selector.get_selected_items())

        cuts_count = 0
        if self.remove_witness_selector:
            cuts_count = len(self.remove_witness_selector.get_selected_items())

        return current_count + adds_count - cuts_count

    def _update_recommended_toad(self):
        """Update the TOAD field with recommended value based on resulting witness count."""
        resulting_count = self._get_resulting_witness_count()
        recommended_toad = rotating.recommend_toad(resulting_count)
        self.toad_field.setText(str(recommended_toad))
        # Clear any previous error
        self.clear_error()

    def _prepopulate_witnesses(self):
        """Prepopulate the add witness selector with witnesses from create page."""
        logger.info(f"Prepopulating {len(self.prepopulate_witnesses)} witnesses")

        for created_witness in self.prepopulate_witnesses:
            # Match the created witness with unused witnesses by EID
            witness_eid = created_witness.get('eid')

            # Find matching witness in unused witnesses
            matching_witness = None
            for witness in self._unused_witnesses:
                if witness.get('id') == witness_eid:
                    matching_witness = witness
                    break

            if matching_witness:
                # Add the witness to the selector using formatted display name
                display_name = self._format_witness_display_name(matching_witness)
                self.add_witness_selector.add_item_programmatically(display_name, matching_witness)
                logger.info(f"Prepopulated witness: {display_name}")
            else:
                logger.warning(f"Could not find matching witness for EID: {witness_eid}")

        # Update TOAD after prepopulation
        self._update_recommended_toad()
