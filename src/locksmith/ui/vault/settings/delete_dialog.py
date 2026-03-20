from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QVBoxLayout, QLabel, QHBoxLayout, QPushButton, QLineEdit, QWidget
)

from locksmith.ui import colors
from locksmith.ui.toolkit.widgets.dialogs import LocksmithDialog


class DeleteVaultDialog(LocksmithDialog):
    """Dialog for confirming vault deletion with vault name verification."""
    
    vault_deleted = Signal(str)

    def __init__(self, vault_name: str, app, parent=None):
        self.vault_name = vault_name
        self.app = app
        
        # Build content widget
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 10, 0, 10)
        content_layout.setSpacing(16)

        # Warning description
        desc = QLabel(
            f"Are you sure you want to permanently delete the vault "
            f"<b>'{vault_name}'</b>? This action cannot be undone."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"font-size: 14px; color: {colors.TEXT_MENU};")
        content_layout.addWidget(desc)

        # Confirmation instruction
        confirm_label = QLabel(f"Type <b>{vault_name}</b> to confirm:")
        confirm_label.setStyleSheet(f"font-size: 14px; color: {colors.TEXT_MENU};")
        content_layout.addWidget(confirm_label)

        # Vault name input
        self.vault_name_input = QLineEdit()
        self.vault_name_input.setPlaceholderText("Enter vault name")
        self.vault_name_input.setStyleSheet(f"""
            QLineEdit {{
                padding: 10px 12px;
                border: 1px solid {colors.BORDER_NEUTRAL};
                border-radius: 6px;
                font-size: 14px;
                background-color: {colors.WHITE};
                color: {colors.TEXT_MENU};
            }}
            QLineEdit:focus {{
                border-color: {colors.DANGER};
            }}
        """)
        self.vault_name_input.textChanged.connect(self._on_input_changed)
        content_layout.addWidget(self.vault_name_input)

        # Build buttons
        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setStyleSheet(f"""
            QPushButton {{
                padding: 10px 24px;
                background-color: {colors.BACKGROUND_DISABLED};
                color: {colors.TEXT_MENU};
                border: 1px solid {colors.BORDER_NEUTRAL};
                border-radius: 6px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {colors.BACKGROUND_NEUTRAL};
            }}
        """)
        
        self.delete_btn = QPushButton("Confirm Delete")
        self.delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_btn.setEnabled(False)  # Disabled until vault name matches
        self._update_delete_button_style()
        
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.delete_btn)

        # Initialize LocksmithDialog with content and buttons
        super().__init__(
            parent=parent,
            title="Delete Vault",
            show_close_button=True,
            show_title_divider=True,
            content=content,
            buttons=buttons,
            show_overlay=True
        )
        
        # Set fixed size (non-resizable)
        self.setFixedSize(450, 320)
        
        # Style the title with red color for danger
        if self.title_label:
            self.title_label.setStyleSheet(
                f"font-size: 18px; font-weight: bold; color: {colors.DANGER};"
            )

        # Connect button actions
        self.cancel_btn.clicked.connect(self.reject)
        self.delete_btn.clicked.connect(self._do_delete)

    def _on_input_changed(self, text: str):
        """Handle vault name input changes."""
        matches = text == self.vault_name
        self.delete_btn.setEnabled(matches)
        self._update_delete_button_style()
        
        # Clear error when user starts typing correctly
        if matches:
            self.clear_error()

    def _update_delete_button_style(self):
        """Update delete button style based on enabled state."""
        if self.delete_btn.isEnabled():
            self.delete_btn.setStyleSheet(f"""
                QPushButton {{
                    padding: 10px 24px;
                    background-color: {colors.DANGER};
                    color: {colors.WHITE};
                    border: none;
                    border-radius: 6px;
                    font-size: 14px;
                }}
                QPushButton:hover {{
                    background-color: {colors.DANGER_HOVER};
                }}
            """)
        else:
            self.delete_btn.setStyleSheet(f"""
                QPushButton {{
                    padding: 10px 24px;
                    background-color: {colors.DANGER_LIGHT};
                    color: {colors.WHITE};
                    border: none;
                    border-radius: 6px;
                    font-size: 14px;
                }}
            """)

    def _do_delete(self):
        """Handle delete confirmation."""
        if self.vault_name_input.text() != self.vault_name:
            self.show_error(
                f"Vault name does not match. Please type '{self.vault_name}' exactly."
            )
            return
        
        self.vault_deleted.emit(self.vault_name)
        self.accept()
