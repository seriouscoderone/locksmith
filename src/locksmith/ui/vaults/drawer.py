# -*- encoding: utf-8 -*-
"""
locksmith.ui.home.vaults module

This module contains the VaultDrawer component for managing vaults.
"""
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, QRect, QSize
from PySide6.QtGui import QIcon, QFont
from PySide6.QtWidgets import QWidget, QFrame, QVBoxLayout, QLabel, QGraphicsOpacityEffect, QHBoxLayout, \
    QListWidgetItem, QListWidget
from keri import help

from locksmith.ui import colors
from locksmith.ui.toolkit.utils import load_scaled_pixmap, create_spacer
from locksmith.ui.vaults.create import CreateVaultDialog
from locksmith.ui.vaults.open import OpenVaultDialog

if TYPE_CHECKING:
    from locksmith.ui.window import LocksmithWindow

logger = help.ogler.getLogger(__name__)

class VaultDrawer(QWidget):
    """
    Vault drawer that slides in from the right with overlay.
    Manages its own animation and state.
    """

    # Signals
    drawer_opened = Signal()
    drawer_closed = Signal()

    def __init__(self, parent: "LocksmithWindow", toolbar_ref):
        """
        Initialize the VaultDrawer.

        Args:
            parent: Parent window (needed for positioning).
            toolbar_ref: Reference to toolbar (needed for height calculations).
        """
        super().__init__(parent)

        self.parent = parent
        self.toolbar_ref = toolbar_ref
        self.drawer_visible = False
        self.drawer_width = 330
        self.app = self.parent.app
        self._overlay_animation_connected = False  # Track connection state

        # Create components
        self._create_overlay()
        self._create_drawer_widget()

    def _create_overlay(self):
        """Create a semi-transparent overlay that appears behind the drawer."""
        self.drawer_overlay = QFrame(self.parent)
        self.drawer_overlay.setStyleSheet("""
            QFrame {
                background-color: rgba(0, 0, 0, 150);
            }
        """)
        self.drawer_overlay.hide()

        # Ensure overlay stays below toolbar
        self.drawer_overlay.setWindowFlag(Qt.WindowType.SubWindow)

        # Make overlay clickable to close drawer
        self.drawer_overlay.mousePressEvent = lambda event: self.toggle()

        # Position overlay to cover everything except toolbar
        toolbar_height = self.toolbar_ref.height()
        self.drawer_overlay.setGeometry(
            0,
            toolbar_height,
            self.parent.width(),
            self.parent.height() - toolbar_height
        )

        # Create opacity effect for fade animation
        self.overlay_opacity = QGraphicsOpacityEffect(self.drawer_overlay)
        self.drawer_overlay.setGraphicsEffect(self.overlay_opacity)

        # Create fade animation
        self.overlay_animation = QPropertyAnimation(self.overlay_opacity, b"opacity")
        self.overlay_animation.setDuration(300)  # Match drawer animation duration
        self.overlay_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _create_drawer_widget(self):
        """Create the vault drawer that slides in from the right."""
        # Create drawer widget
        self.vault_drawer = QFrame(self.parent)
        self.vault_drawer.setStyleSheet(f"""
            QFrame {{
                background-color: {colors.BACKGROUND_WINDOW};
                border-top-left-radius: 16px;
                border-bottom-left-radius: 16px;
            }}
            QFrame#vault-header-divider {{
                background-color: {colors.DIVIDER};
                max-height: 3px;
            }}
        """)

        # Drawer layout
        drawer_layout = QVBoxLayout(self.vault_drawer)
        drawer_layout.setContentsMargins(0, 16, 0, 16)
        drawer_layout.setSpacing(0)

        # Title
        drawer_header_layout = QHBoxLayout()
        drawer_header_layout.addWidget(create_spacer(12))
        drawer_header_layout.setContentsMargins(10, 10, 16, 10)
        drawer_header_layout.setSpacing(10)


        favicon_label = QLabel()
        favicon_pixmap = load_scaled_pixmap(":/assets/custom/SymbolLogo.svg", 36, 36)
        favicon_label.setPixmap(favicon_pixmap)
        drawer_header_layout.addWidget(favicon_label)

        title_label = QLabel("Vaults")
        title_label.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {colors.TEXT_PRIMARY};")
        drawer_header_layout.addWidget(title_label)
        drawer_header_layout.addStretch()
        drawer_layout.addLayout(drawer_header_layout)

        # Add a horizontal divider
        divider = QFrame()
        divider.setObjectName("vault-header-divider")
        divider.setFrameShape(QFrame.Shape.HLine)
        drawer_layout.addWidget(divider)

        # New vault button in its own list widget with custom styling
        new_vault_button_container = QListWidget()
        new_vault_button_container.setObjectName("new-vault-button-container")
        new_vault_button_container.setIconSize(QSize(30, 30))
        new_vault_button_container.setStyleSheet(f"""
            QListWidget {{
                border: none;
                background: transparent;
            }}
            QListWidget::item {{
                border-radius: 8px;
                padding: 10px;
                padding-left: 6px;
            }}
            QListWidget::item:hover {{
                background-color: {colors.BACKGROUND_COLLAPSIBLE_HOVER};
            }}

        """)
        new_vault_button = QListWidgetItem(QIcon(":/assets/material-icons/add.svg"), "Initialize New Vault")
        new_vault_button_font = QFont()
        new_vault_button_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1)
        new_vault_button_font.setPointSize(16)
        new_vault_button.setFont(new_vault_button_font)
        new_vault_button_container.addItem(new_vault_button)
        new_vault_button_container.setFixedHeight(54)  # icon(36) + padding(24*2) + spacing(10)
        new_vault_button_container.setCursor(Qt.CursorShape.PointingHandCursor)
        new_vault_button_container.clicked.connect(self.show_create_vault_dialog)
        drawer_layout.addWidget(new_vault_button_container)


        # Create vault list widget (store as instance variable for refreshing)
        self.vault_list = QListWidget()
        self.vault_list.setIconSize(QSize(36, 36))
        self.vault_list.setCursor(Qt.CursorShape.PointingHandCursor)
        self.vault_list.setStyleSheet(f"""
            QListWidget {{
                border: none;
                background: transparent;
            }}
            QListWidget::item {{
                padding: 12px;
                padding-left: 24px;
                border-radius: 8px;
            }}
            QListWidget::item:hover {{
                background-color: {colors.BACKGROUND_COLLAPSIBLE_HOVER};
            }}
        """)

        self.vault_list.itemClicked.connect(self._on_vault_item_clicked)

        # Populate vault list
        self._refresh_vault_list()

        drawer_layout.addWidget(self.vault_list)


        # Set drawer dimensions
        self.vault_drawer.setFixedWidth(self.drawer_width)

        # Position drawer off-screen to the right initially
        window_width = self.parent.width()
        window_height = self.parent.height()
        toolbar_height = self.toolbar_ref.height()

        self.vault_drawer.setGeometry(
            window_width,  # Start off-screen to the right
            toolbar_height,
            self.drawer_width,
            window_height - toolbar_height
        )

        # Create animation for sliding
        self.drawer_animation = QPropertyAnimation(self.vault_drawer, b"geometry")
        self.drawer_animation.setDuration(300)  # 300ms animation
        self.drawer_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Show the drawer widget (but positioned off-screen)
        self.vault_drawer.show()

    def toggle(self):
        """Toggle drawer open/closed with animations."""
        window_width = self.parent.width()
        window_height = self.parent.height()
        toolbar_height = self.toolbar_ref.height()

        # Disconnect previous animation handler if connected
        if self._overlay_animation_connected:
            self.overlay_animation.finished.disconnect()
            self._overlay_animation_connected = False

        if self.drawer_visible:
            # Slide out (hide)
            start_rect = QRect(
                window_width - self.drawer_width,
                toolbar_height,
                self.drawer_width,
                window_height - toolbar_height
            )
            end_rect = QRect(
                window_width,  # Off screen to the right
                toolbar_height,
                self.drawer_width,
                window_height - toolbar_height
            )
            self.drawer_visible = False

            # Fade out overlay
            self.overlay_animation.setStartValue(1.0)
            self.overlay_animation.setEndValue(0.0)

            # Hide overlay after animation completes
            self.overlay_animation.finished.connect(self.drawer_overlay.hide)
            self._overlay_animation_connected = True
            self.overlay_animation.start()

            # Emit signal
            self.drawer_closed.emit()
        else:
            # Slide in (show)
            start_rect = QRect(
                window_width,
                toolbar_height,
                self.drawer_width,
                window_height - toolbar_height
            )
            end_rect = QRect(
                window_width - self.drawer_width,  # On screen
                toolbar_height,
                self.drawer_width,
                window_height - toolbar_height
            )
            self.drawer_visible = True

            # Show overlay and fade in
            self.drawer_overlay.show()
            self.drawer_overlay.raise_()  # Bring overlay to front

            # Ensure toolbar stays on top
            self.toolbar_ref.raise_()

            self.vault_drawer.raise_()    # Bring drawer above overlay

            self.overlay_animation.setStartValue(0.0)
            self.overlay_animation.setEndValue(1.0)
            self.overlay_animation.start()

            # Emit signal
            self.drawer_opened.emit()

        self.drawer_animation.setStartValue(start_rect)
        self.drawer_animation.setEndValue(end_rect)
        self.drawer_animation.start()

    def handle_resize(self, window_width: int, window_height: int, toolbar_height: int):
        """
        Reposition drawer and overlay on window resize.

        Args:
            window_width: Current window width.
            window_height: Current window height.
            toolbar_height: Current toolbar height.
        """
        # Update overlay size
        self.drawer_overlay.setGeometry(
            0,
            toolbar_height,
            window_width,
            window_height - toolbar_height
        )

        if self.drawer_visible:
            # Drawer is visible, keep it on screen
            self.vault_drawer.setGeometry(
                window_width - self.drawer_width,
                toolbar_height,
                self.drawer_width,
                window_height - toolbar_height
            )
        else:
            # Drawer is hidden, keep it off screen
            self.vault_drawer.setGeometry(
                window_width,
                toolbar_height,
                self.drawer_width,
                window_height - toolbar_height
            )

    def is_visible(self) -> bool:
        """
        Check if drawer is currently visible.

        Returns:
            True if drawer is visible, False otherwise.
        """
        return self.drawer_visible

    def hide_drawer_widgets(self):
        """
        Hide the drawer and overlay widgets completely.
        Used when navigating away from pages that use the drawer.
        """
        # Close the drawer if it's open
        if self.drawer_visible:
            self.toggle()

        # Explicitly hide the drawer widgets
        self.drawer_overlay.hide()
        self.vault_drawer.hide()

    def show_drawer_widgets(self):
        """
        Show the drawer widgets (but keep drawer closed).
        Used when navigating to pages that use the drawer.
        """
        # Refresh the vault list to pick up any changes (e.g., deleted vaults)
        self._refresh_vault_list()
        
        # Don't show overlay (it's only shown when drawer is toggled open)
        # But show the drawer frame (positioned off-screen, ready to slide in)
        self.vault_drawer.show()

    def _refresh_vault_list(self):
        """Refresh the list of vaults."""
        self.vault_list.clear()

        vault_font = QFont()
        vault_font.setPointSize(15)

        for vault_name in self.app.environments():
            vault_item = QListWidgetItem(QIcon(":/assets/custom/vault.png"), vault_name)
            vault_item.setFont(vault_font)
            self.vault_list.addItem(vault_item)


    def show_create_vault_dialog(self):
        """Show the vault creation dialog."""
        dialog = CreateVaultDialog(parent=self.parent, config=self.app.config, app=self.app)

        # Connect the vault_created signal to refresh the list (persistent vaults)
        dialog.vault_created.connect(self._on_vault_created)
        # Connect the vault_opened signal for temp vaults (auto-navigate)
        dialog.vault_opened.connect(self._on_vault_opened)

        dialog.show()

    def _on_vault_item_clicked(self, item: QListWidgetItem):
        """
        Handle vault item click.

        Args:
            item: The clicked QListWidgetItem
        """
        vault_name = item.text()
        logger.info(f"Vault item clicked: {vault_name}")
        self.show_open_vault_dialog(vault_name)

    def show_open_vault_dialog(self, vault_name: str):
        """
        Show the open vault dialog.

        Args:
            vault_name: Name of the vault to open
        """
        dialog = OpenVaultDialog(
            vault_name=vault_name,
            parent=self.parent,
            config=self.app.config,
        )

        # Connect vault_opened signal to close drawer and navigate
        dialog.vault_opened.connect(self._on_vault_opened)

        dialog.show() # Using show here to avoid overlay

    def _on_vault_opened(self, vault_name: str):
        """
        Handle vault opening completion.

        Args:
            vault_name (str): Name of the opened vault
        """

        # Close the drawer
        if self.is_visible():
            self.toggle()

        self.parent.setWindowTitle(f"Locksmith | {vault_name}")

        # Navigate to vault page
        from locksmith.ui.navigation import Pages
        self.parent.nav_manager.navigate_to(Pages.VAULT, vault_name=vault_name)

    def _on_vault_created(self, vault_name: str):
        """
        Handle vault creation completion.

        Args:
            vault_name (str): Name of the newly created vault
        """
        # Refresh the vault list
        self._refresh_vault_list()

        # Automatically open the login dialog for the newly created vault
        self.show_open_vault_dialog(vault_name)