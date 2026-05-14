# -*- encoding: utf-8 -*-
"""RuleChipStrip: chips for a list of rule_refs + a '+ Pick rule' affordance.

Phase 3b ships this display-only — the × and Pick-rule buttons are visible
but clicking them is a no-op. Phase 2 will wire the click handlers to
modify the underlying model.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton,
)


class RuleChipStrip(QFrame):
    pick_clicked = Signal()
    chip_removed = Signal(str)  # rule_ref

    def __init__(self, rule_refs: list[str], parent=None):
        super().__init__(parent=parent)
        self._chips: list[QLabel] = []
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        for ref in rule_refs:
            chip = QLabel(f"{ref} ×")
            chip.setStyleSheet(
                "background:#e8f4f4;color:#0a8a82;border-radius:9px;"
                "padding:2px 9px;font-size:11px;font-weight:600;"
            )
            self._chips.append(chip)
            lay.addWidget(chip)
        self.pick_button = QPushButton("+ Pick rule")
        self.pick_button.setFlat(True)
        self.pick_button.setStyleSheet(
            "QPushButton{color:#0ABFB0;background:transparent;border:0;"
            "padding:2px 9px;font-size:11px;font-weight:600;}"
            "QPushButton:hover{color:#1A1C20;}"
        )
        self.pick_button.clicked.connect(self.pick_clicked.emit)
        lay.addWidget(self.pick_button)
        lay.addStretch(1)

    def chip_texts(self) -> list[str]:
        return [c.text().rsplit(" ×", 1)[0] for c in self._chips]
