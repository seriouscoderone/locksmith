# -*- encoding: utf-8 -*-
"""
locksmith.ui.home module

This module contains the HomePage component with centered logo.
"""
from typing import Dict, Any, TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel

from locksmith.ui.toolkit.pages.base import BasePage
from locksmith.ui.toolkit.utils import load_scaled_pixmap

if TYPE_CHECKING:
    from locksmith.ui.window import LocksmithWindow


class HomePage(BasePage):
    """
    Homepage view with centered favicon/logo.

    Displays a large centered favicon that serves as the initial landing page.
    Shown when no vault is open.
    """

    def __init__(self, parent: "LocksmithWindow | None" = None):
        """
        Initialize the HomePage.

        Args:
            parent: Optional parent widget (main window).
        """
        super().__init__(parent)

        # Create layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Create and add centered favicon
        self._create_centered_favicon()

    def _create_centered_favicon(self):
        """Create a large centered favicon in the main content area."""
        # Create a container widget to hold the centered favicon
        h_layout = QHBoxLayout()
        h_layout.addStretch(2)  # Top spacer

        # Add large favicon
        large_favicon_label = QLabel()
        large_favicon_pixmap = load_scaled_pixmap(":/assets/custom/SymbolLogo.svg", 256, 256)
        large_favicon_label.setPixmap(large_favicon_pixmap)
        large_favicon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Create vertical centering layout
        v_layout = QVBoxLayout()
        v_layout.addStretch()
        v_layout.addWidget(large_favicon_label)
        v_layout.addStretch()

        self.layout.addLayout(v_layout)

    def get_toolbar_config(self) -> Dict[str, Any]:
        """
        Get toolbar configuration for the home page.

        Returns:
            Dict[str, Any]: Toolbar configuration
        """
        return {
            'show_vaults_button': True,
            'show_lock_button': False,
            'show_settings_button': True,
        }

    def on_show(self, **params):
        """Called when the home page becomes visible."""
        super().on_show(**params)
        # Clear any vault-specific state
        # The VaultDrawer will be managed by LocksmithHome