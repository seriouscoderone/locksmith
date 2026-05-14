# -*- encoding: utf-8 -*-
"""KebabButton: flat three-dot button. Phase 1 ships display-only; the menu
that opens on click is wired in Phase 2 (Save/Finalize/Export/Duplicate/Delete).
"""
from __future__ import annotations

from PySide6.QtWidgets import QPushButton


class KebabButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__("⋯", parent=parent)
        self.setFlat(True)
        self.setFixedSize(28, 28)
        self.setStyleSheet(
            "QPushButton{color:#666;font-size:18px;border:0;border-radius:4px;}"
            "QPushButton:hover{background:#f6f7f9;color:#1A1C20;}"
        )
