# -*- encoding: utf-8 -*-
"""ValidationPill: tri-state validation status chip."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel


class ValidationPill(QLabel):
    def __init__(self, *, error_count: int, warning_count: int, parent=None):
        super().__init__(parent=parent)
        if error_count > 0:
            noun = "error" if error_count == 1 else "errors"
            text = f"⛔ {error_count} {noun}"
            style = ("color:#a52a2a;background:#fce8ea;border-radius:10px;"
                     "padding:3px 8px;font-size:11px;font-weight:600;")
        elif warning_count > 0:
            noun = "warning" if warning_count == 1 else "warnings"
            text = f"⚠ {warning_count} {noun}"
            style = ("color:#a5641a;background:#fdf3e7;border-radius:10px;"
                     "padding:3px 8px;font-size:11px;font-weight:600;")
        else:
            text = "✓ valid"
            style = ("color:#2a8a4a;background:#eafaf0;border-radius:10px;"
                     "padding:3px 8px;font-size:11px;font-weight:600;")
        self.setText(text)
        self.setStyleSheet(style)
