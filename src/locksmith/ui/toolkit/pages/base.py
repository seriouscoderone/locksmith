# -*- encoding: utf-8 -*-
"""
locksmith.ui.base_page module

Base class for all pages in the Locksmith application.
"""

from abc import ABCMeta, abstractmethod
from typing import Dict, Any, TYPE_CHECKING

from PySide6.QtWidgets import QWidget
from keri import help

if TYPE_CHECKING:
    from locksmith.ui.window import LocksmithWindow

logger = help.ogler.getLogger(__name__)


# Create a combined metaclass that inherits from both Qt's metaclass and ABCMeta
class QABCMeta(type(QWidget), ABCMeta):
    """Combined metaclass for QWidget and ABC."""
    pass

class BasePage(QWidget, metaclass=QABCMeta):
    """
    Abstract base class for all pages in the application.

    All pages should inherit from this class and implement the required methods.
    This ensures consistent lifecycle management and toolbar configuration across pages.
    """

    def __init__(self, parent: "LocksmithWindow | None" = None):
        """
        Initialize the base page.

        Args:
            parent: Parent widget (typically the main window)
        """
        super().__init__(parent)
        self.parent_window = parent

    @abstractmethod
    def get_toolbar_config(self) -> Dict[str, Any]:
        """
        Get the toolbar configuration for this page.

        Returns:
            Dict[str, Any]: Dictionary containing toolbar configuration:
                - show_vaults_button (bool): Show the vaults drawer button
                - show_lock_button (bool): Show the lock button (close vault)
                - show_settings_button (bool): Show the settings button

        Example:
            {
                'show_vaults_button': True,
                'show_lock_button': False,
                'show_settings_button': True,
            }
        """
        pass

    def on_show(self, **params):
        """
        Called when the page becomes visible.

        Override this method to perform actions when navigating to this page.
        Useful for refreshing data, updating UI state, etc.

        Args:
            **params: Parameters passed during navigation (e.g., vault_name="my-vault")
        """
        logger.debug(f"{self.__class__.__name__}.on_show() called with params: {params}")

    def on_hide(self):
        """
        Called when the page is hidden (another page becomes visible).

        Override this method to perform cleanup, save state, etc.
        """
        logger.debug(f"{self.__class__.__name__}.on_hide() called")

    def get_app(self):
        """
        Get the LocksmithApplication instance.

        Returns:
            LocksmithApplication: The application instance
        """
        if self.parent_window:
            return self.parent_window.app
        return None

    def get_navigation_manager(self):
        """
        Get the NavigationManager instance.

        Returns:
            NavigationManager: The navigation manager instance
        """
        if self.parent_window:
            return self.parent_window.nav_manager
        return None

    def navigate_to(self, page, **params):
        """
        Convenience method to navigate to another page.

        Args:
            page: Page enum to navigate to
            **params: Optional parameters for the page
        """
        nav_manager = self.get_navigation_manager()
        if nav_manager:
            nav_manager.navigate_to(page, **params)
        else:
            logger.error("Cannot navigate: NavigationManager not found")