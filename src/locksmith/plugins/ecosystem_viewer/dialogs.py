# -*- encoding: utf-8 -*-
"""
locksmith.plugins.ecosystem_viewer.dialogs module

Modal dialogs used by the ecosystem viewer pages.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from locksmith.ui import colors
from locksmith.ui.toolkit.widgets import (
    FloatingLabelLineEdit,
    LocksmithButton,
    LocksmithDialog,
    LocksmithInvertedButton,
)


class CreateEcosystemDialog(LocksmithDialog):
    """Modal for creating a new ecosystem grouping."""

    ecosystem_create_requested = Signal(str, str)  # (name, description)

    def __init__(self, app: Any, parent: QWidget | None = None):
        self.app = app

        content = QWidget()
        content.setStyleSheet(f"background-color: {colors.BACKGROUND_CONTENT};")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addSpacing(12)

        intro = QLabel(
            "An ecosystem is a user-defined grouping of schemas and issuer "
            "AIDs that work together. Pick a short, recognizable name."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px;")
        layout.addWidget(intro)

        layout.addSpacing(12)

        self._name_field = FloatingLabelLineEdit("Ecosystem name")
        self._name_field.setFixedWidth(360)
        layout.addWidget(self._name_field)

        layout.addSpacing(12)

        self._desc_field = FloatingLabelLineEdit("Description (optional)")
        self._desc_field.setFixedWidth(360)
        layout.addWidget(self._desc_field)

        layout.addSpacing(12)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        self._cancel_button = LocksmithInvertedButton("Cancel")
        self._cancel_button.clicked.connect(self.close)
        self._create_button = LocksmithButton("Create")
        self._create_button.clicked.connect(self._on_create)
        button_row.addStretch()
        button_row.addWidget(self._cancel_button)
        button_row.addWidget(self._create_button)

        super().__init__(
            parent=parent,
            title="Create ecosystem",
            content=content,
            buttons=button_row,
            show_close_button=True,
        )

    def _on_create(self) -> None:
        name = self._name_field.text().strip()
        if not name:
            self.show_error("Ecosystem name is required.")
            return
        desc = self._desc_field.text().strip()
        self.ecosystem_create_requested.emit(name, desc)
        self.close()
