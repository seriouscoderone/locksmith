# -*- encoding: utf-8 -*-
"""
locksmith.plugins.kerifoundation.watchers.list module

Stub page for KERI Foundation watcher pool — displays empty state.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy, QLabel

from locksmith.ui.toolkit.tables.paginated import PaginatedTableWidget


def _shrink_empty_state_title(table: PaginatedTableWidget, font_size: int = 20):
    """Reduce the plugin empty-state title size without changing shared table code."""
    target_text = f"NO {table.title.upper()}"
    for label in table.empty_state.findChildren(QLabel):
        if label.text() != target_text:
            continue
        label.setStyleSheet(
            label.styleSheet().replace("font-size: 24px;", f"font-size: {font_size}px;")
        )
        break


class WatcherListPage(QWidget):
    """Placeholder for the watcher list page."""

    def __init__(self, app=None, parent=None):
        super().__init__(parent)
        self._app = app
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._setup_ui()

    def set_app(self, app):
        self._app = app

    def set_db(self, db):
        self._db = db

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._table = PaginatedTableWidget(
            columns=["Watcher", "Status"],
            title="KERI Foundation Watchers",
            icon_path=":/assets/material-icons/watcher.svg",
            show_search=False,
            show_add_button=False,
            items_per_page=10,
        )
        _shrink_empty_state_title(self._table)
        self._table.set_static_data([])
        layout.addWidget(self._table)

    def on_show(self):
        pass
