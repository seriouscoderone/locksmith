# -*- encoding: utf-8 -*-
"""
locksmith.ui.plugins.upgrade_banner module

Global banner shown above the page stack when one or more plugins have
been upgraded in the current session. Clicking "Restart now" emits
`restart_requested`; the LocksmithWindow already has
`_handle_restart_requested` that does the actual relaunch (reused from
the post-uninstall flow).
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QWidget,
)


class UpgradeBanner(QWidget):
    """Restart-prompt banner. Hidden by default; show_banner() reveals it."""

    restart_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self.setObjectName("UpgradeBanner")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(12)

        self._label = QLabel("⟳  Plugin update staged. Restart Locksmith to activate.")
        layout.addWidget(self._label, stretch=1)

        self._restart_button = QPushButton("Restart now")
        self._restart_button.setObjectName("UpgradeBannerRestartButton")
        self._restart_button.clicked.connect(self.restart_requested.emit)
        layout.addWidget(self._restart_button)

        self.hide()

    def show_banner(self) -> None:
        """Reveal the banner. Idempotent."""
        self.show()
