# -*- encoding: utf-8 -*-
"""EditorTabBar: flat tab strip used inside an editor's right pane.

Phase 1 / 3a used a single right-pane container per editor. Some editors
(Exports) want to split their content into multiple tabs (Envelope /
Schema / Lifecycle / Rules / Value flow). This is the tab strip; the
host swaps the pane content based on `tab_changed(name)`.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton


class EditorTabBar(QFrame):
    tab_changed = Signal(str)

    def __init__(self, tabs: list[str], parent=None):
        super().__init__(parent=parent)
        self._tabs = list(tabs)
        self._active: str = tabs[0] if tabs else ""
        self._buttons: dict[str, QPushButton] = {}
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 8)
        lay.setSpacing(0)
        for name in self._tabs:
            btn = QPushButton(name)
            btn.setFlat(True)
            btn.clicked.connect(lambda _checked=False, n=name: self.set_active(n))
            self._buttons[name] = btn
            lay.addWidget(btn)
        lay.addStretch(1)
        self._restyle()

    def tab_names(self) -> list[str]:
        return list(self._tabs)

    def active_tab(self) -> str:
        return self._active

    def set_active(self, name: str) -> None:
        if name not in self._buttons:
            return
        if name == self._active:
            return
        self._active = name
        self._restyle()
        self.tab_changed.emit(name)

    def _restyle(self) -> None:
        for name, btn in self._buttons.items():
            if name == self._active:
                btn.setStyleSheet(
                    "QPushButton{color:#0ABFB0;font-weight:600;font-size:12px;"
                    "border:0;border-bottom:2px solid #0ABFB0;"
                    "padding:6px 14px;background:transparent;}"
                )
            else:
                btn.setStyleSheet(
                    "QPushButton{color:#666;font-size:12px;border:0;"
                    "border-bottom:2px solid transparent;"
                    "padding:6px 14px;background:transparent;}"
                    "QPushButton:hover{color:#1A1C20;}"
                )
