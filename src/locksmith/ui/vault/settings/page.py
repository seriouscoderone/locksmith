# -*- encoding: utf-8 -*-
"""
locksmith.ui.vault.settings.page module

Settings content page (displayed within VaultPage container).
"""
import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPalette, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QFrame
)
from keri import help
from keri.core import coring
from keri import kering

from locksmith.core.configing import ENABLE_TURRET_BROWSER_PLUGIN, LocksmithConfig
from locksmith.ui import colors
from locksmith.ui.styles import get_monospace_font_family
from locksmith.ui.toolkit.widgets.buttons import LocksmithButton, LocksmithIconButton, LocksmithCopyButton
from locksmith.ui.toolkit.widgets.fields import FloatingLabelLineEdit
from locksmith.ui.vault.settings.delete_dialog import DeleteVaultDialog
from locksmith.ui.vault.settings.peer_section import PeerSettingsSection

logger = help.ogler.getLogger(__name__)

# AID validation regex (44 character base64url)
AID_PATTERN = re.compile(r'^[A-Za-z0-9_-]{44}$')


class SettingsPage(QWidget):
    """
    Settings content page.

    This is a content-only page that displays within the VaultPage container.
    The VaultPage manages the navigation menu.
    """

    vault_deleted = Signal(str)

    def __init__(self, parent=None):
        """
        Initialize the SettingsPage.

        Args:
            parent: Parent widget (VaultPage container)
        """
        super().__init__(parent)

        self.vault_page = parent
        self.app = parent.app if parent else None
        self.config: LocksmithConfig = self.app.config if self.app else LocksmithConfig.get_instance()
        assert self.config is not None, "SettingsPage requires a valid config"
        self.vault_name = None

        # Create main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Set background
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(colors.BACKGROUND_CONTENT))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        # Create scrollable content area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Force light background for the scroll area and its viewport
        # (overrides system dark mode for consistency with other vault pages)
        scroll_area.setStyleSheet(f"background-color: {colors.BACKGROUND_CONTENT}; border: none;")
        scroll_area.viewport().setStyleSheet(f"background-color: {colors.BACKGROUND_CONTENT};")

        # Content widget inside scroll area
        content_widget = QWidget()
        content_widget.setObjectName("settingsContentWidget")
        content_widget.setStyleSheet(f"#settingsContentWidget {{ background-color: {colors.BACKGROUND_CONTENT}; }}")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(30, 30, 30, 30)
        content_layout.setSpacing(20)

        # Vault-scoped sections only (app-wide settings live in the
        # toolbar AppSettingsDialog — see
        # docs/superpowers/plans/2026-06-09-settings-two-surface-refactor.md).
        self._create_peer_mode_section(content_layout)
        if ENABLE_TURRET_BROWSER_PLUGIN:
            self._create_browser_plugin_section(content_layout)
        self._create_danger_zone_section(content_layout)

        content_layout.addStretch()

        scroll_area.setWidget(content_widget)
        main_layout.addWidget(scroll_area)

        logger.info("SettingsPage initialized")

    def _create_browser_plugin_section(self, parent_layout: QVBoxLayout):
        """Create the Browser Plugin Connection section."""
        # Section header
        header_label = QLabel("Browser Plugin Connection")
        header_font = QFont()
        header_font.setBold(True)
        header_font.setPointSize(14)
        header_label.setFont(header_font)
        header_label.setStyleSheet(f"color: {colors.TEXT_PRIMARY};")
        parent_layout.addWidget(header_label)

        # Subheader
        subheader_label = QLabel("Connect this vault to the Locksmith browser plugin")
        subheader_label.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px; margin-bottom: 10px;")
        parent_layout.addWidget(subheader_label)

        # Container
        plugin_container = QFrame()
        plugin_container.setObjectName("pluginContainer")
        plugin_container.setStyleSheet(f"""
            #pluginContainer {{
                background-color: {colors.WHITE};
                border: 1px solid {colors.BORDER_TABLE};
                border-radius: 24px;
            }}
            QWidget {{ background-color: transparent; }}
        """)
        plugin_layout = QVBoxLayout(plugin_container)
        plugin_layout.setContentsMargins(25, 25, 25, 25)
        plugin_layout.setSpacing(20)

        # Locksmith Identifier row
        self._create_locksmith_identifier_row(plugin_layout)

        # Plugin Identifier row
        self._create_plugin_identifier_row(plugin_layout)

        parent_layout.addWidget(plugin_container)

    def _create_locksmith_identifier_row(self, parent_layout: QVBoxLayout):
        """Create the Locksmith Identifier row with generate and copy buttons."""
        row = QHBoxLayout()
        row.setSpacing(20)

        label = QLabel("Locksmith Identifier")
        label.setFixedWidth(220)
        label.setStyleSheet(f"font-size: 16px; color: {colors.TEXT_PRIMARY};")
        row.addWidget(label)

        # Read-only field for identifier
        self.locksmith_id_field = FloatingLabelLineEdit("Identifier")
        self.locksmith_id_field.setStyleSheet(f'font-family: "{get_monospace_font_family()}", monospace;')
        self.locksmith_id_field.setReadOnly(True)
        self.locksmith_id_field.setFixedWidth(435)

        row.addWidget(self.locksmith_id_field)

        # Copy button
        copy_content = self.locksmith_id_field.text() if self.locksmith_id_field.text() else ""
        self.locksmith_copy_button = LocksmithCopyButton(
            copy_content=copy_content,
            tooltip="Copy Locksmith Identifier"
        )
        row.addWidget(self.locksmith_copy_button)

        row.addStretch()
        parent_layout.addLayout(row)

    def _create_plugin_identifier_row(self, parent_layout: QVBoxLayout):
        """Create the Plugin Identifier editable row."""
        row = QHBoxLayout()
        row.setSpacing(20)

        label = QLabel("Plugin Identifier")
        label.setFixedWidth(220)
        label.setStyleSheet(f"font-size: 16px; color: {colors.TEXT_PRIMARY};")
        row.addWidget(label)

        # Editable field for plugin identifier
        self.plugin_id_field = FloatingLabelLineEdit("Plugin Identifier")
        self.plugin_id_field.setFixedWidth(435)

        self.plugin_id_field.line_edit.textChanged.connect(self._on_plugin_id_changed)
        row.addWidget(self.plugin_id_field)

        row.addStretch()
        parent_layout.addLayout(row)

    def _on_plugin_id_changed(self, text: str):
        """Handle plugin identifier field change with validation."""
        if not self.app or not self.app.vault:
            return

        text = text.strip()

        # Validate AID format if not empty
        if text:
            # Basic regex validation
            if not AID_PATTERN.match(text):
                logger.warning(f"Invalid Plugin Identifier format: {text}")
                self.plugin_id_field.line_edit.setStyleSheet(f"""
                    QLineEdit {{
                        border: 2px solid {colors.DANGER};
                        border-radius: 6px;
                        padding: 12px;
                        font-size: 14px;
                        background-color: {colors.BACKGROUND_CONTENT};
                    }}
                """)
                return

            try:
                coring.Prefixer(qb64=text)
            except (kering.InvalidCodeError, ValueError) as e:
                logger.warning(f"Invalid Plugin Identifier (KERI validation): {e}")
                self.plugin_id_field.line_edit.setStyleSheet(f"""
                    QLineEdit {{
                        border: 2px solid {colors.DANGER};
                        border-radius: 6px;
                        padding: 12px;
                        font-size: 14px;
                        background-color: {colors.BACKGROUND_CONTENT};
                    }}
                """)
                return

            # Clear error styling if valid
            self.plugin_id_field.reset_style()

        # Update vault turret settings
        self.app.vault.update_plugin_identifier(text)
        logger.info(f"Plugin identifier updated: {text}")

    def _create_peer_mode_section(self, parent_layout: QVBoxLayout):
        """Mount the Direct peer mode section.

        The SettingsPage is built once at app startup, before a vault is
        open, so we can't access `self.app.vault` yet. Insert a
        placeholder QFrame here so the layout position is reserved, then
        swap its contents in `set_vault_name` once the vault exists.
        """
        self.peer_section = None
        self._peer_section_placeholder = QFrame()
        self._peer_section_placeholder_layout = QVBoxLayout(self._peer_section_placeholder)
        self._peer_section_placeholder_layout.setContentsMargins(0, 0, 0, 0)
        parent_layout.addWidget(self._peer_section_placeholder)
        self._mount_peer_section_if_ready()

    def _mount_peer_section_if_ready(self):
        if self.peer_section is not None:
            return
        if not self.app or not self.app.vault:
            return
        if self._peer_section_placeholder is None:
            return
        self.peer_section = PeerSettingsSection(vault=self.app.vault)
        self._peer_section_placeholder_layout.addWidget(self.peer_section)

    def _create_danger_zone_section(self, parent_layout: QVBoxLayout):
        """Create the Danger Zone section with delete vault button."""
        # Section header
        header_label = QLabel("Danger Zone")
        header_font = QFont()
        header_font.setBold(True)
        header_font.setPointSize(14)
        header_label.setFont(header_font)
        header_label.setStyleSheet(f"color: {colors.DANGER};")  # Red color
        parent_layout.addWidget(header_label)

        # Container for danger actions
        danger_container = QFrame()
        danger_container.setObjectName("dangerContainer")
        danger_container.setStyleSheet(f"""
            #dangerContainer {{
                background-color: {colors.BACKGROUND_DANGER};
                border: 1px solid {colors.BACKGROUND_DANGER_BORDER};
                border-radius: 24px;
            }}
            QWidget {{ background-color: transparent; }}
        """)
        danger_layout = QVBoxLayout(danger_container)
        danger_layout.setContentsMargins(25, 25, 25, 25)
        danger_layout.setSpacing(20)

        # Delete Vault button
        self._create_delete_vault_row(danger_layout)

        parent_layout.addWidget(danger_container)

    def _create_delete_vault_row(self, parent_layout: QVBoxLayout):
        """Create the delete vault button row."""
        row = QHBoxLayout()
        row.setSpacing(20)

        label = QLabel("Delete Vault")
        label.setFixedWidth(220)
        label.setStyleSheet(f"font-size: 16px; color: {colors.DANGER}; font-weight: 500;")
        row.addWidget(label)

        # Delete button with red styling
        self.delete_button = LocksmithButton("Permanently Delete")
        self.delete_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {colors.DANGER};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {colors.DANGER_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {colors.DANGER_PRESSED};
            }}
        """)
        self.delete_button.clicked.connect(self._on_delete_vault)
        row.addWidget(self.delete_button)

        row.addStretch()
        parent_layout.addLayout(row)

    def _on_delete_vault(self):
        """Handle delete vault button click."""
        if not self.vault_name:
            logger.warning("No vault name set, cannot delete")
            return

        if not self.app:
            logger.warning("No app instance, cannot delete vault")
            return

        dialog = DeleteVaultDialog(
            vault_name=self.vault_name,
            app=self.app,
            parent=self.vault_page
        )
        dialog.vault_deleted.connect(self._handle_vault_deleted)
        dialog.open()

    def _handle_vault_deleted(self, vault_name: str):
        """Handle successful vault deletion and navigate to home."""
        logger.info(f"Vault '{vault_name}' deleted; navigating to home")

        # Find the main window by traversing up the parent chain
        # Widget hierarchy: SettingsPage -> VaultPage -> QStackedWidget -> central_widget -> LocksmithWindow
        widget = self.vault_page
        nav_manager = None
        while widget is not None:
            # Look for LocksmithWindow (has nav_manager attribute)
            nav_manager = getattr(widget, 'nav_manager', None)
            if nav_manager is not None:
                break
            widget = widget.parent()  # type: ignore[assignment]

        if nav_manager is not None:
            # Clear navigation stack and navigate to home
            nav_manager.clear_navigation_stack()
            from locksmith.ui.navigation import Pages
            nav_manager.navigate_to(Pages.HOME)
        else:
            # Fallback: just emit signal for any other handlers
            logger.warning("Could not find main window, emitting vault_deleted signal")
            self.vault_deleted.emit(vault_name)

    def set_vault_name(self, vault_name: str):
        """
        Set the vault name for this page.

        Args:
            vault_name: Name of the open vault
        """
        self.vault_name = vault_name
        logger.info(f"SettingsPage: Set vault name to {vault_name}")

        # Vault is now open — mount the peer-mode section if we haven't yet.
        self._mount_peer_section_if_ready()

        # Load existing browser plugin settings if available
        if ENABLE_TURRET_BROWSER_PLUGIN and self.app and self.app.vault and self.app.vault.pluginSettings:
            self.locksmith_id_field.setText(self.app.vault.pluginSettings.locksmith_identifier)
            self.locksmith_copy_button.set_copy_content(self.app.vault.pluginSettings.locksmith_identifier)
            plugin_id = self.app.vault.pluginSettings.plugin_identifier
            if plugin_id:
                self.plugin_id_field.setText(plugin_id)
            else:
                self.plugin_id_field.setText("")
