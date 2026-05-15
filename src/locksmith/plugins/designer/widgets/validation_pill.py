# -*- encoding: utf-8 -*-
"""ValidationPill: tri-state validation status chip."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QLabel


class ValidationPill(QLabel):
    def __init__(self, *, error_count: int, warning_count: int, parent=None):
        super().__init__(parent=parent)
        # Capsule pill rendered by a custom paintEvent so the
        # background is always a perfect rounded rect at half-height
        # radius. Qt QSS `border-radius` was rendering as a softly
        # rounded rectangle rather than a true capsule on macOS.
        if error_count > 0:
            text = "Invalid"
            self._bg = "#fce8ea"
            color = "#a52a2a"
        elif warning_count > 0:
            text = "Warning"
            self._bg = "#fdf3e7"
            color = "#a5641a"
        else:
            text = "Valid"
            self._bg = "#eafaf0"
            color = "#2a8a4a"
        self.setText(text)
        self.setStyleSheet(
            f"color:{color};background:transparent;"
            "padding:4px 12px;font-size:11px;font-weight:600;"
        )

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(self._bg))
        p.setPen(Qt.NoPen)
        radius = self.height() / 2
        p.drawRoundedRect(self.rect(), radius, radius)
        p.end()
        super().paintEvent(event)
