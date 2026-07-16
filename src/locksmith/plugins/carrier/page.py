# -*- encoding: utf-8 -*-
"""
locksmith.plugins.carrier.page module

Placeholder persona page for the bundled ``carrier`` role-plugin. Real
persona UX (the Carrier HOA surface) is out of scope for this task — this
is just enough to prove the gate reveals a real widget.
"""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class CarrierPlaceholderPage(QWidget):
    """Minimal placeholder shown once the carrier_license gate is satisfied."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Carrier HOA — licensed. (Persona UX to be designed.)"))
