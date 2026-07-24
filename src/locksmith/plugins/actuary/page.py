# -*- encoding: utf-8 -*-
"""
locksmith.plugins.actuary.page module

Placeholder persona page for the bundled ``actuary`` role-plugin. Real
persona UX (the Actuarial HOA surface) is out of scope for this task — this
is just enough to prove the gate reveals a real widget.
"""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class ActuaryPlaceholderPage(QWidget):
    """Placeholder surface proving the Actuarial role gate (HOA #4)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Actuarial — access granted. (Persona UX to be designed.)"))
