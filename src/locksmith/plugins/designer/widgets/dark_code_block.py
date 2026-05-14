# -*- encoding: utf-8 -*-
"""DarkCodeBlock: read-only dark-themed code display for UEL/etc.

Differentiates code (expressions, fold formulas, payload schemas) from
prose at a glance. Read-only by design — editing happens via the
JsonSourceView toolbar toggle, never inline.
"""
from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QPlainTextEdit


class DarkCodeBlock(QPlainTextEdit):
    def __init__(self, text: str = "", parent=None):
        super().__init__(parent=parent)
        self.setReadOnly(True)
        self.setPlainText(text)
        mono = QFont("Menlo")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(10)
        self.setFont(mono)
        self.setStyleSheet(
            "QPlainTextEdit{"
            "background:#1A1C20;color:#E0E0E0;"
            "border:1px solid #2a2c30;border-radius:4px;"
            "padding:8px 10px;"
            "}"
        )
        self.setFixedHeight(80)
