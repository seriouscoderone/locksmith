# -*- encoding: utf-8 -*-
"""SourceEventChipStrip: event-name chips + '+ Pick event' affordance.

Used in the Projections editor to list the source_events a projection
folds over. Same shape as RuleChipStrip from Phase 3b — display-only
in Phase 3c; Phase 2 wires the × removal and Pick popup to the model.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton


class SourceEventChipStrip(QFrame):
    pick_clicked = Signal()
    chip_removed = Signal(str)

    def __init__(self, events: list[str], parent=None):
        super().__init__(parent=parent)
        self._chips: list[QLabel] = []
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        for ev in events:
            chip = QLabel(f"{ev} ×")
            chip.setStyleSheet(
                "background:#f3edfb;color:#A36AE6;border-radius:9px;"
                "padding:2px 9px;font-size:11px;font-weight:600;"
            )
            self._chips.append(chip)
            lay.addWidget(chip)
        self.pick_button = QPushButton("+ Pick event")
        self.pick_button.setFlat(True)
        self.pick_button.setStyleSheet(
            "QPushButton{color:#A36AE6;background:transparent;border:0;"
            "padding:2px 9px;font-size:11px;font-weight:600;}"
            "QPushButton:hover{color:#1A1C20;}"
        )
        self.pick_button.clicked.connect(self.pick_clicked.emit)
        lay.addWidget(self.pick_button)
        lay.addStretch(1)

    def chip_texts(self) -> list[str]:
        return [c.text().rsplit(" ×", 1)[0] for c in self._chips]
