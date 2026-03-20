# -*- encoding: utf-8 -*-
"""
locksmith.ui.vault.remotes.challenge module

Dialog for challenging remote identifiers with challenge-response verification
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QPlainTextEdit
from keri import help

from locksmith.core import remoting
from locksmith.ui.toolkit.widgets import (
    LocksmithDialog,
    LocksmithInvertedButton,
    LocksmithIconButton,
    LocksmithButton
)
from locksmith.ui.toolkit.widgets.fields import (
    FloatingLabelLineEdit,
    FloatingLabelComboBox
)

logger = help.ogler.getLogger(__name__)


class ChallengeRemoteIdentifierDialog(LocksmithDialog):
    """Dialog for challenging remote identifiers."""

    def __init__(
        self,
        app,
        remote_identifier_prefix: str,
        remote_identifier_alias: str = "",
        icon_path: str = ":/assets/material-icons/swords.svg",
        parent = None
    ):
        """
        Initialize the ChallengeRemoteIdentifierDialog.

        Args:
            app: Application instance
            remote_identifier_prefix: Prefix of the remote identifier to challenge
            remote_identifier_alias: Alias of the remote identifier
            icon_path: Path to the challenge icon
            parent: Parent widget (typically VaultPage)
        """
        self.app = app
        self.remote_identifier_prefix = remote_identifier_prefix
        self.remote_identifier_alias = remote_identifier_alias

        # Track generated challenge phrase
        self.current_challenge = None

        # Create tabs
        tab_container = QWidget()
        layout = QVBoxLayout(tab_container)
        layout.addSpacing(10)

        tabs = self._create_styled_tabs()
        layout.addWidget(tabs)

        # Add Generate Challenge tab
        generate_tab = self._create_generate_tab()
        tabs.addTab(generate_tab, "Generate Challenge")

        # Add Respond to Challenge tab
        respond_tab = self._create_respond_tab()
        tabs.addTab(respond_tab, "Respond to Challenge")

        # Button row
        button_row = QHBoxLayout()
        self.close_button = LocksmithInvertedButton("Close")
        button_row.addWidget(self.close_button)

        # Initialize parent dialog
        super().__init__(
            parent=parent,
            title=f"Challenge Remote Identifier: {remote_identifier_alias or remote_identifier_prefix[:15]}",
            title_icon=icon_path,
            show_close_button=True,
            content=tab_container,
            buttons=button_row,
            show_overlay=False
        )

        # Set fixed size
        self.setFixedSize(500, 560)

        # Connect buttons
        self.close_button.clicked.connect(self.close)

    def _create_styled_tabs(self) -> QTabWidget:
        """Create styled tab widget for challenge workflows."""
        from locksmith.ui import colors

        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background-color: transparent;
            }}
            QTabBar::tab {{
                padding: 10px 20px;
                font-size: 14px;
                border: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }}
            QTabBar::tab:selected {{
                border: 2px solid {colors.BORDER_FOCUS};
                border-bottom: none;
                background-color: transparent;
                color: #000;
            }}
            QTabBar::tab:!selected {{
                background-color: transparent;
                color: #666;
                border-bottom: 2px solid {colors.BACKGROUND_NEUTRAL};
            }}
        """)

        return tabs

    def _create_generate_tab(self) -> QWidget:
        """Create the Generate Challenge tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 40, 20, 20)

        # Helper text
        helper_text = QLabel(
            "Generate a 12-word challenge phrase to send to the remote identifier. "
            "They will use this challenge to prove control of their keys by signing it. "
            "Click the Generate Challenge button to create a new challenge phrase."
        )
        helper_text.setWordWrap(True)
        helper_text.setStyleSheet("font-size: 13px; margin-bottom: 10px;")
        layout.addWidget(helper_text)

        # Generate Challenge section
        challenge_label = QLabel("Challenge Phrase")
        challenge_label.setStyleSheet("font-weight: 500; font-size: 13px; margin-top: 10px;")
        layout.addWidget(challenge_label)

        challenge_row = QHBoxLayout()
        self.challenge_field = QPlainTextEdit()
        self.challenge_field.setReadOnly(True)
        self.challenge_field.setPlaceholderText("Click Generate Challenge to create a challenge phrase...")
        self.challenge_field.setFixedHeight(80)
        self.challenge_field.setStyleSheet("""
            QPlainTextEdit {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 8px;
                font-size: 13px;
                background-color: #f9f9f9;
                color: #000;
            }
        """)
        challenge_row.addWidget(self.challenge_field)

        self.copy_challenge_button = LocksmithIconButton(
            icon_path=":/assets/material-icons/content_copy.svg",
            tooltip="Copy challenge to clipboard",
            icon_size=24
        )
        self.copy_challenge_button.setFixedHeight(80)
        self.copy_challenge_button.clicked.connect(self._on_copy_challenge)
        challenge_row.addWidget(self.copy_challenge_button)
        layout.addLayout(challenge_row)

        # Generate Challenge button
        self.generate_challenge_button = LocksmithButton("Generate Challenge")
        self.generate_challenge_button.clicked.connect(self._on_generate_challenge)
        layout.addWidget(self.generate_challenge_button)

        layout.addStretch()

        return tab

    def _create_respond_tab(self) -> QWidget:
        """Create the Respond to Challenge tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Helper text
        helper_text = QLabel(
            "Enter the 12-word challenge response you received from the remote identifier. "
            "Select which of your local identifiers you want to use to verify their response. "
            "The response must match the challenge phrase to successfully verify."
        )
        helper_text.setWordWrap(True)
        helper_text.setStyleSheet("font-size: 13px; margin-bottom: 10px;")
        layout.addWidget(helper_text)

        # Associated Identifier dropdown
        self.associated_identifier_combo = FloatingLabelComboBox("Associated Identifier")
        self._populate_identifier_dropdown()
        layout.addWidget(self.associated_identifier_combo)

        # Respond to Challenge section
        response_label = QLabel("Respond to Challenge")
        response_label.setStyleSheet("font-weight: 500; font-size: 13px; margin-top: 10px;")
        layout.addWidget(response_label)

        response_row = QHBoxLayout()
        self.challenge_response_field = FloatingLabelLineEdit("Response")
        response_row.addWidget(self.challenge_response_field)

        self.verify_challenge_button = LocksmithIconButton(
            icon_path=":/assets/material-icons/check_dark.svg",
            tooltip="Verify challenge response",
            icon_size=24
        )
        self.verify_challenge_button.setFixedHeight(50)
        self.verify_challenge_button.clicked.connect(self._on_verify_challenge)
        response_row.addWidget(self.verify_challenge_button)
        layout.addLayout(response_row)

        layout.addStretch()

        return tab

    def _populate_identifier_dropdown(self):
        """Populate dropdown with all available identifiers from hby.habs."""
        self.associated_identifier_combo.clear()
        self.associated_identifier_combo.addItem("Select an identifier...")

        # Get all identifiers from habery
        hby = self.app.vault.hby
        for hab_pre, hab in hby.habs.items():
            # Format: "Name (prefix...)"
            item_text = f"{hab.name} ({hab_pre[:15]}...)"
            self.associated_identifier_combo.addItem(item_text, userData=hab_pre)

    def _on_generate_challenge(self):
        """Handle generate challenge button click."""
        logger.info("Generate challenge clicked")

        try:
            # Generate new challenge phrase
            self.current_challenge = remoting.generate_challenge()

            # Display in field
            self.challenge_field.setPlainText(self.current_challenge)

            logger.info("Challenge generated successfully")

        except Exception as e:
            logger.exception(f"Error generating challenge: {e}")
            self.show_error(f"Error generating challenge: {str(e)}")

    def _on_copy_challenge(self):
        """Handle copy challenge button click."""
        logger.info("Copy challenge clicked")

        try:
            challenge_text = self.challenge_field.toPlainText().strip()
            if not challenge_text:
                self.show_error("No challenge to copy. Please generate a challenge first.")
                return

            # Copy to clipboard
            from PySide6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            clipboard.setText(challenge_text)
            logger.info(f"Copied to clipboard: {challenge_text[:50]}...")

            self.show_success("Challenge copied to clipboard")

        except Exception as e:
            logger.exception(f"Error copying challenge: {e}")
            self.show_error(f"Error copying challenge: {str(e)}")

    def _on_verify_challenge(self):
        """Handle verify challenge button click."""
        logger.info("Verify challenge clicked")

        # Get the response text
        response = self.challenge_response_field.text().strip()
        if not response:
            self.show_error("Please enter a challenge response")
            return

        # Get selected identifier
        selected_index = self.associated_identifier_combo.currentIndex()
        if selected_index <= 0:  # 0 is "Select an identifier..."
            self.show_error("Please select an identifier to verify with")
            return

        hab_pre = self.associated_identifier_combo.itemData(selected_index)
        if not hab_pre:
            self.show_error("Invalid identifier selected")
            return

        # Disable button during verification
        self.verify_challenge_button.setEnabled(False)

        try:
            # Split response into words
            challenge_words = response.split()

            if len(challenge_words) != 12:
                self.show_error("Challenge response must be exactly 12 words")
                self.verify_challenge_button.setEnabled(True)
                return

            # Create doer for challenge verification
            doer = remoting.ChallengeVerificationDoer(
                app=self.app,
                hab_pre=hab_pre,
                remote_id_pre=self.remote_identifier_prefix,
                challenge_words=challenge_words,
                signal_bridge=self.app.vault.signals if hasattr(self.app.vault, 'signals') else None
            )

            # Add doer to vault
            self.app.vault.extend([doer])

            # Connect to completion signal
            if hasattr(self.app.vault, 'signals') and self.app.vault.signals:
                self.app.vault.signals.doer_event.connect(self._on_challenge_verified)

            logger.info("Challenge verification initiated")

        except Exception as e:
            logger.exception(f"Error verifying challenge: {e}")
            self.show_error(f"Error verifying challenge: {str(e)}")
            self.verify_challenge_button.setEnabled(True)

    def _on_challenge_verified(self, doer_name, event_type, data):
        """Handle challenge verification completion signal."""
        if doer_name != "ChallengeVerificationDoer":
            return

        # Re-enable button
        self.verify_challenge_button.setEnabled(True)

        if event_type == "challenge_response_sent" and data.get('success'):
            # Clear the response field
            self.challenge_response_field.setText("")

            logger.info("Challenge response sent successfully")
            self.show_success("Challenge response sent successfully")

            # Disconnect signal
            if hasattr(self.app.vault, 'signals') and self.app.vault.signals:
                try:
                    self.app.vault.signals.doer_event.disconnect(self._on_challenge_verified)
                except:
                    pass

        elif event_type == "challenge_verification_failed":
            error_msg = data.get('error', 'Unknown error')
            logger.error(f"Challenge verification failed: {error_msg}")
            self.show_error(f"Challenge verification failed: {error_msg}")

            # Disconnect signal
            if hasattr(self.app.vault, 'signals') and self.app.vault.signals:
                try:
                    self.app.vault.signals.doer_event.disconnect(self._on_challenge_verified)
                except:
                    pass
