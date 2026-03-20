# -*- encoding: utf-8 -*-
"""
locksmith.ui.navigation module

Central navigation management for the Locksmith application.
"""
from enum import Enum
from typing import Optional, Dict, Any

from PySide6.QtCore import QObject, Signal
from keri import help

logger = help.ogler.getLogger(__name__)


class Pages(Enum):
    """Enumeration of available pages in the application."""
    HOME = "home"
    VAULT = "vault"


class NavigationManager(QObject):
    """
    Central navigation manager for the application.

    Manages page transitions, navigation history, and page-specific state.
    Emits signals when pages change to allow UI components to react.
    """

    # Signals
    page_changed = Signal(str, dict)  # Emits (page_name, params)
    navigation_stack_changed = Signal(list)  # Emits navigation stack

    def __init__(self, parent=None):
        """
        Initialize the NavigationManager.

        Args:
            parent: Parent QObject (typically the main window)
        """
        super().__init__(parent)

        self._current_page: Optional[Pages] = None
        self._current_params: Dict[str, Any] = {}
        self._navigation_stack: list = []  # Stack of (page, params) tuples

        logger.info("NavigationManager initialized")

    def navigate_to(self, page: Pages, **params):
        """
        Navigate to a specified page with optional parameters.

        Args:
            page (Pages): The page to navigate to
            **params: Optional parameters for the page (e.g., vault_name="my-vault")
        """
        if not isinstance(page, Pages):
            logger.error(f"Invalid page type: {page}. Must be Pages enum.")
            return

        logger.info(f"Navigating to {page.value} with params: {params}")

        # Add current page to navigation stack (if exists and different from new page)
        if self._current_page is not None and self._current_page != page:
            self._navigation_stack.append((self._current_page, self._current_params.copy()))
            self.navigation_stack_changed.emit(self._navigation_stack)

        # Update current page
        self._current_page = page
        self._current_params = params

        # Emit page changed signal
        self.page_changed.emit(page.value, params)

    def go_back(self) -> bool:
        """
        Navigate to the previous page in the navigation stack.

        Returns:
            bool: True if navigation was successful, False if stack is empty
        """
        if not self._navigation_stack:
            logger.info("Cannot go back: navigation stack is empty")
            return False

        # Pop the last page from stack
        previous_page, previous_params = self._navigation_stack.pop()
        self.navigation_stack_changed.emit(self._navigation_stack)

        logger.info(f"Going back to {previous_page.value}")

        # Navigate without adding to stack
        self._current_page = previous_page
        self._current_params = previous_params

        # Emit page changed signal
        self.page_changed.emit(previous_page.value, previous_params)

        return True

    def can_navigate_back(self) -> bool:
        """
        Check if back navigation is possible.

        Returns:
            bool: True if there are pages in the navigation stack
        """
        return len(self._navigation_stack) > 0

    def get_current_page(self) -> Optional[Pages]:
        """
        Get the current page.

        Returns:
            Optional[Pages]: The current page enum, or None if no page is set
        """
        return self._current_page

    def get_current_params(self) -> Dict[str, Any]:
        """
        Get the parameters for the current page.

        Returns:
            Dict[str, Any]: Dictionary of page parameters
        """
        return self._current_params.copy()

    def clear_navigation_stack(self):
        """Clear the navigation stack (useful when logging out, closing vault, etc.)."""
        logger.info("Clearing navigation stack")
        self._navigation_stack.clear()
        self.navigation_stack_changed.emit(self._navigation_stack)

    def get_navigation_stack_depth(self) -> int:
        """
        Get the depth of the navigation stack.

        Returns:
            int: Number of pages in the navigation stack
        """
        return len(self._navigation_stack)