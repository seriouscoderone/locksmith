# -*- encoding: utf-8 -*-
"""
locksmith.ui.vault.shared.base_list_page module

Base class for list pages in the vault UI.
"""
from typing import Dict, Any

from PySide6.QtWidgets import QWidget
from keri import help

logger = help.ogler.getLogger(__name__)


class BaseListPage(QWidget):
    """
    Base class for vault list pages.

    Provides shared stub handlers for search, pagination, sorting, and row clicks.
    Subclasses must define ``_on_row_action(self, row_data, action)`` for the
    ``_on_row_clicked`` default behaviour to work.
    """

    def _on_search(self, search_term: str):
        """Handle search input."""
        logger.debug(f"Search changed: '{search_term}'")

    def _on_page_changed(self, page: int):
        """Handle page change."""
        logger.debug(f"Page changed to: {page}")

    def _on_sort_changed(self, column: int, order: str):
        """Handle sort change."""
        logger.debug(f"Sort changed: column={column}, order={order}")

    def _on_row_clicked(self, row_data: object):
        """Handle row click to open View dialog."""
        if isinstance(row_data, dict):
            data: Dict[str, Any] = {str(k): v for k, v in row_data.items()}
            self._on_row_action(data, "View")
