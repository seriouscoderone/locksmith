# -*- encoding: utf-8 -*-
"""RoleIconBadge: kind-colored rounded square with role-kind emoji glyph.

Used in templates-browser cards, Overview header, and editor breadcrumbs.
Color + glyph chosen by role.kind. Falls back to neutral grey + ❓ on
unknown kinds.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


_GLYPHS: dict[str, str] = {
    "government":   "🏛️",
    "organization": "🏢",
    "individual":   "👤",
    "system":       "⚙️",
    "device":       "📟",
    "agent":        "🤖",
}

_COLORS: dict[str, str] = {
    "government":   "#0ABFB0",
    "organization": "#0ABFB0",
    "individual":   "#D97757",
    "system":       "#888888",
    "device":       "#888888",
    "agent":        "#A36AE6",
}


class RoleIconBadge(QFrame):
    def __init__(self, *, kind: str, size: int = 52, parent=None):
        super().__init__(parent=parent)
        color = _COLORS.get(kind, "#888888")
        glyph = _GLYPHS.get(kind, "❓")
        self.setFixedSize(size, size)
        self.setStyleSheet(
            f"background:{color};border-radius:8px;"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.glyph_label = QLabel(glyph)
        self.glyph_label.setAlignment(Qt.AlignCenter)
        self.glyph_label.setStyleSheet(
            f"font-size:{int(size * 0.45)}px;background:transparent;"
        )
        lay.addWidget(self.glyph_label)
