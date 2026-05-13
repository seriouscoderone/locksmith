# -*- encoding: utf-8 -*-
"""ValidationBadge: small pill showing error/warning count or "valid"."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel


class ValidationBadge(QLabel):
    """Compact badge: green 'valid', amber 'N warnings', red 'N errors'."""

    def __init__(self, *, errors: int = 0, warnings: int = 0, parent=None):
        super().__init__(parent=parent)
        self.setMargin(0)
        self.set_counts(errors=errors, warnings=warnings)

    def set_counts(self, *, errors: int, warnings: int) -> None:
        if errors > 0:
            text = f"⛔ {errors} error{'s' if errors != 1 else ''}"
            bg = "#fce4e4"
            fg = "#9b1d1d"
        elif warnings > 0:
            text = f"⚠ {warnings} warning{'s' if warnings != 1 else ''}"
            bg = "#fff3cd"
            fg = "#7a5b00"
        else:
            text = "✓ valid"
            bg = "#e8f5e9"
            fg = "#1b5e20"
        self.setText(text)
        self.setStyleSheet(
            f"background:{bg};color:{fg};border-radius:10px;"
            f"padding:3px 8px;font-size:10px;font-weight:600;"
        )
