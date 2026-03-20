# -*- encoding: utf-8 -*-
"""
locksmith.ui.vaults.create module

Dialog for creating new vaults
"""

from PySide6.QtCore import Signal, Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout
from keri import help
from keri import kering
from keri.app import habbing
from keri.core import signing
from keri.db.basing import OobiRecord
from keri.vdr import credentialing

from locksmith.core import otping
from locksmith.core.crypto import stretch_password_to_passcode
from locksmith.core.habbing import format_bran
from locksmith.ui import colors
from locksmith.ui.toolkit.widgets import (
    LocksmithDialog,
    FloatingLabelLineEdit,
    LocksmithButton,
    LocksmithInvertedButton,
    CollapsibleSection
)

logger = help.ogler.getLogger(__name__)


class CreateVaultDialog(LocksmithDialog):
    """Dialog for initializing a new vault."""

    # Signal emitted when vault is successfully created (persistent vaults)
    vault_created = Signal(str)  # Emits vault name
    # Signal emitted when temp vault is created and opened immediately
    vault_opened = Signal(str)  # Emits vault name

    def __init__(self, parent=None, config=None, app=None):
        """
        Initialize the CreateVaultDialog.

        Args:
            parent: Parent widget (typically main window)
            config: LocksmithConfig instance
            app: LocksmithApplication instance (required for temp vaults)
        """
        self.config = config
        self.app = app
        self._otp_enabled = False
        self._otp_secret = None
        self._qr_label = None

        # Create content widget
        content_widget = QWidget()
        content_widget.setStyleSheet(f"background-color: {colors.BACKGROUND_CONTENT};")
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addSpacing(10)
        self.name_field = FloatingLabelLineEdit("Name")
        self.name_field.setFixedWidth(300)
        self.name_field.line_edit.textChanged.connect(self._on_name_changed)
        layout.addWidget(self.name_field)

        self.passcode_field = FloatingLabelLineEdit("Passcode", password_mode=True)
        self.passcode_field.setFixedWidth(300)
        layout.addWidget(self.passcode_field)

        # 2fa button creation
        self.enable_2fa_button = LocksmithButton("Enable 2-Factor Authentication")
        self.enable_2fa_button.setFixedWidth(300)

        self._2fa_section = CollapsibleSection(
            button=self.enable_2fa_button,
            on_expand_changed=self._on_2fa_expand_changed
        )
        self.enable_2fa_button.clicked.connect(self._2fa_section.toggle)

        otp_content_layout = QVBoxLayout()
        otp_content_layout.setContentsMargins(0, 0, 0, 0)

        self._qr_label = QLabel()
        self._qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        otp_content_layout.addWidget(self._qr_label)

        self._2fa_section.set_content_layout(otp_content_layout)

        layout.addWidget(self._2fa_section)

        layout.addStretch()

        # Create button row
        button_row = QHBoxLayout()
        self.cancel_button = LocksmithInvertedButton("Cancel")
        button_row.addWidget(self.cancel_button)
        button_row.addSpacing(10)
        self.create_button = LocksmithButton("Create")
        button_row.addWidget(self.create_button)

        # Create title content
        title_content = QLabel("Vault Initialization")
        title_content.setStyleSheet("font-size: 24px;")

        # Initialize parent dialog
        super().__init__(
            parent=parent,
            title="Vault Initialization",
            title_content=title_content,
            show_close_button=True,
            content=content_widget,
            buttons=button_row,
            show_overlay=False
        )

        # Set initial size
        self.setFixedSize(340, 350)
        self._base_height = 350
        # Note: Not calling self._2fa_section.set_dialog(self) because we handle resizing directly with hardcoded heights

        # Setup 2FA height animation
        self._2fa_height_animation = QPropertyAnimation(self, b"dialogHeight")
        self._2fa_height_animation.setDuration(200)
        self._2fa_height_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Connect buttons
        self.cancel_button.clicked.connect(self.close)
        self.create_button.clicked.connect(self.create_vault)

    def _animate_to_height(self, target_height: int):
        """Animate dialog to target height."""
        self._2fa_height_animation.stop()
        self._2fa_height_animation.setStartValue(self.height())
        self._2fa_height_animation.setEndValue(target_height)
        self._2fa_height_animation.start()

    def create_vault(self):
        """
        Create a new vault with the provided name and passcode.
        """
        name = self.name_field.text().strip()
        passcode = self.passcode_field.text()

        # Validate inputs
        if not name:
            self.show_error("Please enter a vault name.")
            return

        # if not passcode:
        #     self.show_error("Please enter a passcode.")
        #     return

        # Format and stretch passcode using Argon2
        bran = ''
        if passcode:
            formatted = format_bran(passcode)
            bran = stretch_password_to_passcode(formatted)

        try:
            # Clear any previous errors
            self.clear_error()

            # Create habery with passcode
            logger.info(f"Creating vault: {name}")

            # Prepare kwargs for Habery creation
            kwa = dict()
            kwa['salt'] = signing.Salter(raw=self.config.salt.encode('utf-8')).qb64
            kwa['bran'] = bran
            kwa['algo'] = self.config.algo
            kwa['tier'] = self.config.tier

            # Create the Habery
            is_temp = self.config.temp
            hby = habbing.Habery(
                name=name,
                base=self.config.base,
                temp=is_temp,
                **kwa,
            )

            # Add default OOBIs (skip if not yet configured)
            obr = OobiRecord(date=help.nowIso8601())
            if self.config.root_oobi:
                hby.db.oobis.put(keys=(self.config.root_oobi,), val=obr)
            if self.config.api_oobi:
                hby.db.oobis.put(keys=(self.config.api_oobi,), val=obr)

            if is_temp:
                # Temp vaults: immediately open (they can't be found on disk later)
                from locksmith.core.vaulting import run_vault_controller
                rgy = credentialing.Regery(hby=hby, name=hby.name, base=self.config.base, temp=True)
                vault, qtask = run_vault_controller(app=self.app, hby=hby, rgy=rgy)
                self.app.open_vault(name=name, vault=vault, qtask=qtask)
                logger.info(f"Temp vault opened: {name}")
                # Save OTP if enabled
                if self._otp_enabled and self._otp_secret:
                    otping.save_otp_secret(vault_name=name, secret=self._otp_secret)
                self.vault_opened.emit(name)
                self.close()
                return

            # Persistent vaults: close and let user open via drawer
            hby.close()

            # Save OTP secret if enabled
            if self._otp_enabled and self._otp_secret:
                otping.save_otp_secret(
                    vault_name=name,
                    secret=self._otp_secret,
                )

            logger.info(f"Vault created successfully: {name}")

            # Emit signal
            self.vault_created.emit(name)

            # Close dialog
            self.close()

        except kering.AuthError as ex:
            logger.error(f"Authentication error creating vault: {ex}")
            self.show_error(f"Authentication error: {str(ex)}")

        except ValueError as ex:
            logger.error(f"Value error creating vault: {ex}")
            self.show_error(f"Invalid input: {str(ex)}")

        except Exception as ex:
            logger.exception(f"Error creating vault: {ex}")
            self.show_error(f"An unexpected error occurred: {str(ex)}")

    # Constants for 2FA QR code sizing
    _QR_CODE_SIZE = 300
    _2FA_EXPANDED_HEIGHT = 350 + _QR_CODE_SIZE

    def _on_2fa_expand_changed(self, expanded: bool):
        if expanded:
            self.enable_2fa_button.setText("Disable 2-Factor Authentication")
            if not self._otp_secret:
                vault_name = self.name_field.text().strip()
                if not vault_name:
                    self.show_error("Please enter a vault name before enabling 2FA.", extra_height=20)
                    self._2fa_section.toggle()
                    return

                try:
                    self._otp_secret = otping.generate_otp_secret()
                    uri = otping.create_totp_uri(self._otp_secret, vault_name)
                    pixmap = otping.generate_qr_pixmap(uri)
                    self._qr_label.setPixmap(pixmap)
                    self._qr_label.setFixedSize(pixmap.size())
                    
                    self._2fa_section._content_height = self._QR_CODE_SIZE
                    self._2fa_section.content_area.setFixedHeight(self._QR_CODE_SIZE)
                except Exception as e:
                    logger.error(f"Error generating OTP: {e}")
                    self.show_error("Failed to generate 2FA QR code.")
                    self._2fa_section.toggle()
                    return

            self._otp_enabled = True
            self._animate_to_height(self._2FA_EXPANDED_HEIGHT)
            
        else:
            self.enable_2fa_button.setText("Enable 2-Factor Authentication")
            self._otp_enabled = False
            self._otp_secret = None
            self._qr_label.clear()
            self._qr_label.setFixedSize(0, 0)
            self._2fa_section._content_height = 0
            self._2fa_section.content_area.setFixedHeight(0)
            self._animate_to_height(self._base_height)

    def _on_name_changed(self, text):
        """Clear error when name is entered, if an error is currently displayed."""
        if text and self.error_banner.height() > 0:
            self.clear_error()