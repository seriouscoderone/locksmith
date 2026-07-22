# -*- encoding: utf-8 -*-
"""
locksmith.plugins.product_designer.page module

Placeholder persona page for the bundled ``product_designer`` role-plugin. Real
persona UX (the Insurance Product Design HOA surface) is out of scope for this
task — this is just enough to prove the gate reveals a real widget.
"""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class ProductDesignerPlaceholderPage(QWidget):
    """Placeholder surface proving the Insurance Product Design role gate (HOA #4)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Insurance Product Design — access granted. (Persona UX to be designed.)"))
