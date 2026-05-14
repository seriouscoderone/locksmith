# -*- encoding: utf-8 -*-
"""RailFilterChipBar: filter chips with counts above a primitive rail.

Used in the Rules editor to let the user filter the rail by rule.type.
Phase 3d ships display-only — clicking a chip changes the active visual
but doesn't yet filter the rail. Phase 2 wires the rail repopulation.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton


class RailFilterChipBar(QFrame):
    filter_changed = Signal(str)

    def __init__(
        self,
        chips: list[tuple[str, int]],
        active: str = "all",
        parent=None,
    ):
        super().__init__(parent=parent)
        self._chip_names = [name for name, _ in chips]
        self._chip_counts = {name: count for name, count in chips}
        self._active = active if active in self._chip_counts else (
            self._chip_names[0] if self._chip_names else ""
        )
        self._buttons: dict[str, QPushButton] = {}
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(4)
        for name, count in chips:
            btn = QPushButton(f"{name} ({count})")
            btn.setFlat(True)
            btn.clicked.connect(lambda _checked=False, n=name: self.set_active(n))
            self._buttons[name] = btn
            lay.addWidget(btn)
        lay.addStretch(1)
        self._restyle()

    def chip_text(self, name: str) -> str:
        btn = self._buttons.get(name)
        return btn.text() if btn is not None else ""

    def active_filter(self) -> str:
        return self._active

    def set_active(self, name: str) -> None:
        if name not in self._buttons or name == self._active:
            return
        self._active = name
        self._restyle()
        self.filter_changed.emit(name)

    def _restyle(self) -> None:
        for name, btn in self._buttons.items():
            if name == self._active:
                btn.setStyleSheet(
                    "QPushButton{color:#fff;background:#1A1C20;"
                    "border:0;border-radius:9px;padding:2px 9px;"
                    "font-size:11px;font-weight:600;}"
                )
            else:
                btn.setStyleSheet(
                    "QPushButton{color:#444;background:#f0f2f5;"
                    "border:0;border-radius:9px;padding:2px 9px;"
                    "font-size:11px;}"
                    "QPushButton:hover{color:#1A1C20;background:#e8eaef;}"
                )
