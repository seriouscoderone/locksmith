# -*- encoding: utf-8 -*-
"""TypeColorBadge: colored pill carrying a typed-entity name.

Used to make rule types (predicate / legal_prose / validation / binding_link)
scannable at a glance in the Rules editor right pane, and reusable for any
other typed primitive whose categories want a consistent color language.
"""
from __future__ import annotations

from PySide6.QtWidgets import QLabel


_COLORS: dict[str, str] = {
    "predicate":              "#0ABFB0",
    "legal_prose":            "#A36AE6",
    "prose":                  "#A36AE6",
    "behavioral_expectation": "#A36AE6",
    "validation":             "#D97757",
    "computational":          "#888888",
    "binding_link":           "#666666",
}


class TypeColorBadge(QLabel):
    def __init__(self, type_id: str, parent=None):
        super().__init__(parent=parent)
        color = _COLORS.get(type_id, "#888888")
        self.setText(type_id.replace("_", " ").upper())
        self.setStyleSheet(
            f"color:{color};background:transparent;"
            f"border:1px solid {color};border-radius:9px;"
            "padding:2px 8px;font-size:10px;font-weight:600;"
            "letter-spacing:0.5px;"
        )
