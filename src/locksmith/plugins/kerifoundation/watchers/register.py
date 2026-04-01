# -*- encoding: utf-8 -*-
"""
locksmith.plugins.kerifoundation.watchers.register module

Stub page for KERI Foundation watcher registration — coming soon.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from locksmith.ui import colors


class WatcherRegisterPage(QWidget):
    """Placeholder for the watcher registration page."""

    def __init__(self, app=None, parent=None):
        super().__init__(parent)
        self._app = app
        self._setup_ui()

    def set_app(self, app):
        self._app = app

    def set_db(self, db):
        self._db = db

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)

        title = QLabel("Register with Watcher")
        title.setStyleSheet(f"""
            font-size: 22px;
            font-weight: 600;
            color: {colors.TEXT_PRIMARY};
        """)
        layout.addWidget(title)

        coming_soon = QLabel("Watcher registration is coming soon.")
        coming_soon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        coming_soon.setStyleSheet(f"""
            font-size: 16px;
            color: {colors.TEXT_MUTED};
            padding: 60px;
        """)
        layout.addWidget(coming_soon)
        layout.addStretch()

    def on_show(self):
        pass
