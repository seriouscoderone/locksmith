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
from locksmith.ui.vault.shared.witness_auth_mixin import (
    WitnessAuthenticationPanel,
    witness_auth_dialog_height
)
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
        self._auth_panel = None
        self._workflow_mode = "rotate"
        self._signals_connected = False

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
        self._rotation_content_widget = content_widget
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
        self.rotate_button.clicked.connect(self._on_primary_clicked)

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
            self._signals_connected = True
            logger.info("RotateIdentifierDialog: Connected to vault signal bridge")
        self.finished.connect(self._on_dialog_finished)

    def _cleanup_signal_connection(self):
        if not self._signals_connected:
            return

        if self.app and hasattr(self.app, 'vault') and self.app.vault and hasattr(self.app.vault, 'signals'):
            try:
                self.app.vault.signals.doer_event.disconnect(self._on_doer_event)
            except RuntimeError:
                pass
        self._signals_connected = False

    def _on_dialog_finished(self, _result):
        self._cleanup_signal_connection()

    def closeEvent(self, event):
        self._cleanup_signal_connection()
        super().closeEvent(event)

    def _on_primary_clicked(self):
        if self._workflow_mode == "auth":
            self._submit_auth_step()
        else:
            self.rotate_identifier()

    def _show_auth_step(self, witness_ids: list[str]):
        self.clear_error()
        self.clear_success()

        if self._auth_panel is not None:
            self.content_layout.removeWidget(self._auth_panel)
            self._auth_panel.setParent(None)
            self._auth_panel.deleteLater()

        self._rotation_content_widget.hide()
        self._auth_panel = WitnessAuthenticationPanel(
            app=self.app,
            hab=self.hab,
            witness_ids=witness_ids,
            parent=self
        )
        self.content_layout.addWidget(self._auth_panel)

        self._workflow_mode = "auth"
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.close_button.setText("Close")
        self.close_button.setEnabled(True)
        self.rotate_button.setText("Authenticate")
        self.rotate_button.setEnabled(True)
        self.setFixedSize(700, self._auth_step_height())
        self.center_on_parent()

    def _auth_step_height(self) -> int:
        if self._auth_panel is None:
            return 440

        return witness_auth_dialog_height(
            self._auth_panel.individual_witnesses,
            self._auth_panel.batch_groups
        )

    def _submit_auth_step(self):
        if self._auth_panel is None:
            self.close()
            return

        self.clear_error()
        valid, codes, error_message = self._auth_panel.validate_authentication_codes()
        if not valid:
            self.show_error(error_message)
            return

        self.rotate_button.setEnabled(False)
        self.rotate_button.setText("Authenticating...")
        self.close_button.setEnabled(False)
        rotating.authenticate_witnesses(self.app, self.hab, codes)

    def _set_auth_button_idle(self):
        self.close_button.setEnabled(True)
        self.rotate_button.setEnabled(True)
        self.rotate_button.setText("Authenticate")

    async def _check_and_spawn_keystate_update(self):
        if hasattr(self.app, 'plugin_manager') and self.app.plugin_manager:
            await self.app.plugin_manager.after_identifier_authenticated(self.app.vault, self.hab)

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
        self.rotate_button.setText("Rotating...")
        self.rotate_button.setEnabled(False)
        self.close_button.setEnabled(False)
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
            if data.get('pre') != self.hab.pre:
                return

            if event_type == "rotation_complete":
                logger.info(f"Rotation complete: {data.get('alias')} ({data.get('pre')})")

                # Three outcomes after RotateDoer's bare-receipt attempt:
                #   needs_auth=True  → a plugin holds TOTP material for at
                #                      least one witness; show the modal
                #                      so the user can satisfy it.
                #   receipts_collected=True → pure-KERI witnesses returned
                #                      enough wigs; rotation is complete
                #                      end-to-end; close cleanly.
                #   neither → rotation landed locally but the witness
                #             rejected the bare event AND no plugin has
                #             auth material to retry with (a TOTP modal
                #             would just prompt for a code the user
                #             can't provide). Warn the user and close so
                #             they don't see a misleading prompt.
                needs_auth = data.get('needs_auth')
                receipts_collected = data.get('receipts_collected', True)
                if needs_auth is None:
                    # Legacy code path didn't carry needs_auth; fall back
                    # to the old has_witnesses heuristic so we don't
                    # silently regress to "no auth ever."
                    needs_auth = data.get('has_witnesses', False)

                if needs_auth:
                    logger.info("Showing witness authentication step")
                    self._show_auth_step(list(self.hab.kever.wits))
                elif receipts_collected:
                    logger.info("Pure-KERI receipts collected; rotation complete")
                    import asyncio
                    asyncio.ensure_future(self._check_and_spawn_keystate_update())
                    self.accept()
                else:
                    logger.warning(
                        "Rotation complete locally but witness(es) did not "
                        "issue receipts and no plugin holds auth material "
                        "to retry — closing dialog without TOTP prompt."
                    )
                    self.show_error(
                        "Rotation completed locally, but the witness did "
                        "not issue a receipt. The new key state is in "
                        "your KEL; remote parties may not be able to "
                        "verify it until the witness side is fixed (see "
                        "kerihost issue #6)."
                    )
                    import asyncio
                    asyncio.ensure_future(self._check_and_spawn_keystate_update())
                    # Don't auto-close on this path — let the user read
                    # the message and click Close themselves.

            elif event_type == "rotation_failed":
                logger.error(f"Rotation failed: {data.get('error')}")
                self.rotate_button.setText("Rotate")
                self.rotate_button.setEnabled(True)
                self.close_button.setEnabled(True)
                self.show_error(f"Rotation failed: {data.get('error')}")

        elif doer_name == "AuthenticateWitnessesDoer":
            if data.get('pre') != self.hab.pre:
                return

            if event_type == "witness_authentication_success":
                logger.info(f"Witness authentication succeeded for {data.get('alias')}")
                import asyncio
                asyncio.ensure_future(self._check_and_spawn_keystate_update())
                self.accept()

            elif event_type == "witness_authentication_failed":
                error_msg = data.get('error', 'Authentication failed')
                logger.error(f"Witness authentication failed: {error_msg}")
                self._set_auth_button_idle()
                self.show_error(error_msg)
