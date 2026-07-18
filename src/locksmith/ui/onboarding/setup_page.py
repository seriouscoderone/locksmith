# -*- encoding: utf-8 -*-
"""
locksmith.ui.onboarding.setup_page module

First-run workspace setup for onboarding-enabled HOA brands. Shown instead
of the silent ``bootstrap_default_environment`` call (see
``core/bootstrapping.py``) when ``brand().onboarding_enabled`` is set and no
vault exists yet on disk — the user picks the workspace name and an
optional passcode themselves rather than the brand baking in a fixed
``[bootstrap] default_vault_name``/``default_passcode`` pair.

Field/validation choices mirror ``CreateVaultDialog``
(``ui/vaults/create.py``) — the closest existing "name + passcode" form —
reusing the same toolkit widgets (``FloatingLabelLineEdit``,
``LocksmithButton``, ``LocksmithCheckbox``) rather than inventing new ones.
Unlike that dialog, an empty passcode here requires an explicit
acknowledgment checkbox (a first-run default should not silently produce
an unencrypted vault without the user noticing).
"""
from typing import Any, Dict, TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QVBoxLayout

from locksmith.ui import colors
from locksmith.ui.toolkit.pages.base import BasePage
from locksmith.ui.toolkit.widgets import (
    FloatingLabelLineEdit,
    LocksmithButton,
    LocksmithCheckbox,
)

if TYPE_CHECKING:
    from locksmith.ui.window import LocksmithWindow


class SetupPage(BasePage):
    """First-run "what should we call this workspace" setup screen.

    Signals:
        setup_submitted(str, str): emitted (name, passcode) once the form is
            valid and the user clicks Continue. ``passcode`` is ``""`` when
            the user explicitly acknowledged skipping one — the caller
            (``LocksmithWindow._on_setup_submitted``) passes it straight
            through to ``bootstrap_default_environment``'s ``passcode``
            keyword, where an explicit ``""`` means "unencrypted", distinct
            from the "use brand default" ``None`` sentinel.
    """

    setup_submitted = Signal(str, str)

    def __init__(self, default_name: str = "", parent: "LocksmithWindow | None" = None):
        """
        Args:
            default_name: Prefill for the workspace-name field — the
                brand's ``default_vault_name`` (a suggestion, not a fixed
                value; the user can change it).
            parent: Parent widget (typically the main window).
        """
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 48, 48, 48)
        layout.setSpacing(16)
        layout.addStretch(1)

        heading = QLabel(self._brand_display_name())
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet(
            f"font-size: 28px; font-weight: 600; color: {colors.TEXT_PRIMARY};"
        )
        layout.addWidget(heading)

        name_prompt = QLabel("What should we call this secure workspace?")
        name_prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_prompt.setStyleSheet(f"font-size: 14px; color: {colors.TEXT_SECONDARY};")
        layout.addWidget(name_prompt)

        self.name = FloatingLabelLineEdit("Secure workspace name")
        self.name.setObjectName("setupPage.nameField")
        self.name.setFixedWidth(320)
        if default_name:
            self.name.setText(default_name)
        layout.addWidget(self.name, alignment=Qt.AlignmentFlag.AlignHCenter)

        passcode_prompt = QLabel("Choose a passcode")
        passcode_prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        passcode_prompt.setStyleSheet(
            f"font-size: 14px; color: {colors.TEXT_SECONDARY}; margin-top: 12px;"
        )
        layout.addWidget(passcode_prompt)

        self.passcode = FloatingLabelLineEdit("Passcode", password_mode=True)
        self.passcode.setObjectName("setupPage.passcodeField")
        self.passcode.setFixedWidth(320)
        layout.addWidget(self.passcode, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.confirm = FloatingLabelLineEdit("Confirm passcode", password_mode=True)
        self.confirm.setObjectName("setupPage.confirmField")
        self.confirm.setFixedWidth(320)
        layout.addWidget(self.confirm, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.no_passcode_ack = LocksmithCheckbox(
            "Continue without a passcode (not recommended)"
        )
        self.no_passcode_ack.setObjectName("setupPage.noPasscodeAck")
        layout.addWidget(self.no_passcode_ack, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.submit_btn = LocksmithButton("Continue")
        self.submit_btn.setObjectName("setupPage.submitButton")
        self.submit_btn.setFixedWidth(320)
        layout.addWidget(self.submit_btn, alignment=Qt.AlignmentFlag.AlignHCenter)

        layout.addStretch(2)

        # Wire validation — re-checked on every keystroke/toggle.
        self.name.line_edit.textChanged.connect(self._update_validity)
        self.passcode.line_edit.textChanged.connect(self._update_validity)
        self.confirm.line_edit.textChanged.connect(self._update_validity)
        self.no_passcode_ack.toggled.connect(self._update_validity)
        self.submit_btn.clicked.connect(self._on_submit)

        self._update_validity()

    @staticmethod
    def _brand_display_name() -> str:
        from locksmith.core.branding import brand

        return brand().display_name

    def _update_validity(self) -> None:
        """Submit is enabled only once: name is non-empty, the two passcode
        fields match, AND (a passcode was entered OR the user explicitly
        acknowledged continuing without one)."""
        name_ok = bool(self.name.text().strip())
        passcode_val = self.passcode.text()
        confirm_val = self.confirm.text()
        match_ok = passcode_val == confirm_val
        passcode_ok = bool(passcode_val) or self.no_passcode_ack.isChecked()
        self.submit_btn.setEnabled(name_ok and match_ok and passcode_ok)

    def _on_submit(self) -> None:
        name = self.name.text().strip()
        passcode = self.passcode.text()
        self.setup_submitted.emit(name, passcode)

    def get_toolbar_config(self) -> Dict[str, Any]:
        """First-run setup has no vault yet — hide the vault-drawer and
        lock controls the toolbar would otherwise show."""
        return {
            'show_vaults_button': False,
            'show_lock_button': False,
            'show_settings_button': True,
        }
