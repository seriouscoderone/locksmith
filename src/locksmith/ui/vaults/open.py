# -*- encoding: utf-8 -*-
"""
locksmith.ui.vaults.open module

Dialog for opening existing vaults
"""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout
from keri import help
from keri import kering

from locksmith.core import otping
from locksmith.core.crypto import stretch_password_to_passcode
from locksmith.core.habbing import format_bran, open_hby, keystore_exists, is_vault_encrypted
from locksmith.ui import colors
from locksmith.ui.toolkit.widgets import (
    LocksmithDialog,
    FloatingLabelLineEdit,
    LocksmithButton,
    LocksmithInvertedButton
)

logger = help.ogler.getLogger(__name__)


class OpenVaultDialog(LocksmithDialog):
    """Dialog for opening an existing vault."""

    # Signal emitted when vault is successfully opened
    vault_opened = Signal(str)  # Emits vault name

    # Size constants
    _BASE_HEIGHT = 230
    _OTP_FIELD_HEIGHT = 68  # Height for OTP field including spacing

    def __init__(self, vault_name, parent=None, config=None):
        """
        Initialize the OpenVaultDialog.

        Args:
            vault_name (str): Name of the vault to open
            parent: Parent widget (typically main window)
            config: LocksmithConfig instance
            app: LocksmithApplication instance
        """
        self.vault_name = vault_name
        self._parent_window = parent
        self.app = self._parent_window.app
        self.config = config
        self._has_otp = False
        self._otp_secret = None

        # Create content widget
        content_widget = QWidget()
        content_widget.setStyleSheet(f"background-color: {colors.BACKGROUND_CONTENT};")
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addSpacing(10)
        self.passcode_field = FloatingLabelLineEdit("Passcode", password_mode=True)
        self.passcode_field.setFixedWidth(300)
        layout.addWidget(self.passcode_field)

        # OTP field (initially hidden, shown if vault has 2FA)
        self.otp_field = FloatingLabelLineEdit("2FA Code")
        self.otp_field.setFixedWidth(300)
        self.otp_field.setVisible(False)
        layout.addWidget(self.otp_field)

        layout.addStretch()

        # Create button row
        button_row = QHBoxLayout()
        self.cancel_button = LocksmithInvertedButton("Cancel")
        button_row.addWidget(self.cancel_button)
        button_row.addSpacing(10)
        self.open_button = LocksmithButton("Open")
        button_row.addWidget(self.open_button)

        # Create title content
        title_content = QLabel(f"Open {self.vault_name}")
        title_content.setStyleSheet("font-size: 24px;")

        # Initialize parent dialog
        super().__init__(
            parent=parent,
            title=f"Open {self.vault_name}",
            title_content=title_content,
            show_close_button=True,
            content=content_widget,
            buttons=button_row,
            show_overlay=False
        )

        # Check if vault has OTP configured and adjust UI
        self._check_otp_configured()

        # Set initial size based on OTP status
        if self._has_otp:
            self.setFixedSize(340, self._BASE_HEIGHT + self._OTP_FIELD_HEIGHT)
        else:
            self.setFixedSize(340, self._BASE_HEIGHT)

        # Connect buttons
        self.cancel_button.clicked.connect(self.close)
        self.open_button.clicked.connect(self.open_vault)

    def _check_otp_configured(self):
        """Check if the vault has OTP configured and show OTP field if needed."""
        try:
            if otping.has_otp_configured(self.vault_name):
                self._has_otp = True
                self._otp_secret = otping.get_otp_secret(self.vault_name)
                self.otp_field.setVisible(True)
                logger.info(f"Vault {self.vault_name} has 2FA enabled")
            else:
                self._has_otp = False
                self.otp_field.setVisible(False)
        except Exception as e:
            logger.error(f"Error checking OTP configuration: {e}")
            self._has_otp = False
            self.otp_field.setVisible(False)

    def open_vault(self):
        """
        Open the vault with the provided passcode.
        """
        passcode = self.passcode_field.text()

        # Verify OTP if configured
        if self._has_otp:
            otp_code = self.otp_field.text().strip()
            if not otp_code:
                self.show_error("Please enter your 2FA code.")
                return
            
            if not self._otp_secret:
                self.show_error("2FA configuration error. Please try again.")
                return
            
            if not otping.verify_otp(self._otp_secret, otp_code):
                self.show_error("Invalid 2FA code. Please try again.")
                return

        # Format and stretch passcode using Argon2
        bran = format_bran(passcode)
        if bran:
            bran = stretch_password_to_passcode(bran)

        # if len(bran) < 21:
        #     self.show_error("Passcode is too short.")
        #     return

        try:
            # Clear any previous errors
            self.clear_error()

            logger.info(f"Opening vault: {self.vault_name}")

            # Check if keystore exists
            if not keystore_exists(self.vault_name, self.config.base):
                self.show_error("Vault does not exist.")
                return

            # Check if vault is encrypted
            is_encrypted = is_vault_encrypted(self.vault_name, self.config.base)
            
            # If user provided a password but vault is NOT encrypted, ignore it
            # This prevents accidental encryption of open vaults
            if passcode and not is_encrypted:
                logger.warning(f"Vault {self.vault_name} is unencrypted. Ignoring provided passcode.")
                bran = None
            elif passcode:
                # Use the stretched passcode
                pass  # bran is already set
            else:
                bran = None

            # Open the habery and create vault
            # Pass None for bran when no passcode (KERI treats "" and None differently)
            vault, qtask = open_hby(
                name=self.vault_name,
                base=self.config.base,
                bran=bran,
                app=self.app,
                salt=self.config.salt
            )

            # Store vault in application
            self.app.open_vault(name=self.vault_name, vault=vault, qtask=qtask)

            logger.info(f"Vault opened successfully: {self.vault_name}")

            # Emit signal
            self.vault_opened.emit(self.vault_name)

            # Close dialog
            self.close()

        except kering.AuthError as ex:
            logger.error(f"Authentication error opening vault: {ex}")
            self.show_error(f"Authentication error: {str(ex)}")

        except ValueError as ex:
            logger.error(f"Value error opening vault: {ex}")
            self.show_error(f"Invalid input: {str(ex)}")

        except Exception as ex:
            logger.exception(f"Error opening vault: {ex}")
            self.show_error(f"An unexpected error occurred: {str(ex)}")