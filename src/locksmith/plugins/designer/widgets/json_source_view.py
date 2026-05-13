# -*- encoding: utf-8 -*-
"""JsonSourceView: two-way bound JSON editor.

Renders the live template as formatted JSON. User edits are debounced
~300ms, then re-parsed. On successful parse: emits applied(doc). On
failure: emits parse_error(msg). The controller decides what to do
with each.
"""
from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QLabel, QPlainTextEdit, QVBoxLayout, QWidget,
)


class JsonSourceView(QWidget):
    applied = Signal(dict)
    parse_error = Signal(str)

    DEBOUNCE_MS = 300

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.editor = QPlainTextEdit()
        font = QFont("Menlo")
        font.setStyleHint(QFont.Monospace)
        font.setPointSize(11)
        self.editor.setFont(font)
        self.editor.setStyleSheet(
            "background:#1A1C20;color:#e6e6e6;border:0;padding:10px;"
        )
        lay.addWidget(self.editor, 1)

        self._status = QLabel("")
        self._status.setStyleSheet(
            "background:#fff;color:#666;padding:4px 12px;"
            "border-top:1px solid #e0e3ea;font-size:11px;"
        )
        self._status.setVisible(False)
        lay.addWidget(self._status)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._reparse)
        self.editor.textChanged.connect(self._on_text_changed)
        self._suppress_signal = False

    def set_doc(self, doc: dict[str, Any]) -> None:
        self._suppress_signal = True
        self.editor.setPlainText(json.dumps(doc, indent=2, sort_keys=True))
        self._suppress_signal = False
        self._status.setVisible(False)

    def _on_text_changed(self) -> None:
        if self._suppress_signal:
            return
        self._timer.start(self.DEBOUNCE_MS)

    def _reparse(self) -> None:
        text = self.editor.toPlainText()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            self._status.setText(f"Parse error: {e}")
            self._status.setStyleSheet(
                "background:#fce4e4;color:#9b1d1d;padding:4px 12px;"
                "border-top:1px solid #f0c0c0;font-size:11px;"
            )
            self._status.setVisible(True)
            self.parse_error.emit(str(e))
            return
        if not isinstance(parsed, dict):
            msg = "Root must be a JSON object"
            self._status.setText(f"Parse error: {msg}")
            self._status.setVisible(True)
            self.parse_error.emit(msg)
            return
        self._status.setVisible(False)
        self.applied.emit(parsed)
