# -*- encoding: utf-8 -*-
"""ViewTypeChipPicker: 6 view-type chips, one active.

Used in the Projections editor to choose how the projection renders
(table / list / cards / kanban / timeline / summary). The active chip
is highlighted in orange; others are flat grey. Display-only until
Phase 2 wires the change to the model.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton


_VIEW_TYPES = ["table", "list", "cards", "kanban", "timeline", "summary"]
_VIEW_TYPE_GLYPHS: dict[str, str] = {
    "table":    "▤",
    "list":     "≡",
    "cards":    "▢",
    "kanban":   "▦",
    "timeline": "─",
    "summary":  "Σ",
}


class ViewTypeChipPicker(QFrame):
    view_type_changed = Signal(str)

    def __init__(self, active: str = "table", parent=None):
        super().__init__(parent=parent)
        self._active = active if active in _VIEW_TYPES else "table"
        self._buttons: dict[str, QPushButton] = {}
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        for name in _VIEW_TYPES:
            glyph = _VIEW_TYPE_GLYPHS.get(name, "")
            label = f"{glyph} {name}" if glyph else name
            btn = QPushButton(label)
            btn.setFlat(True)
            btn.clicked.connect(lambda _checked=False, n=name: self.set_active(n))
            self._buttons[name] = btn
            lay.addWidget(btn)
        lay.addStretch(1)
        self._restyle()

    def view_types(self) -> list[str]:
        return list(_VIEW_TYPES)

    def active_view_type(self) -> str:
        return self._active

    def set_active(self, name: str) -> None:
        if name not in self._buttons:
            return
        if name == self._active:
            return
        self._active = name
        self._restyle()
        self.view_type_changed.emit(name)

    def _restyle(self) -> None:
        for name, btn in self._buttons.items():
            if name == self._active:
                btn.setStyleSheet(
                    "QPushButton{color:#fff;background:#D97757;"
                    "border:0;border-radius:6px;padding:4px 10px;"
                    "font-size:11px;font-weight:600;}"
                )
            else:
                btn.setStyleSheet(
                    "QPushButton{color:#666;background:#f0f2f5;"
                    "border:0;border-radius:6px;padding:4px 10px;"
                    "font-size:11px;}"
                    "QPushButton:hover{color:#1A1C20;background:#e8eaef;}"
                )
