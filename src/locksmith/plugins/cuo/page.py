# -*- encoding: utf-8 -*-
"""locksmith.plugins.cuo.page module — the CUO mandate-declaration surface."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class CuoMandatePage(QWidget):
    """The CUO's surface. Task 4 replaces this body with the real declaration form."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Underwriting — access granted."))
