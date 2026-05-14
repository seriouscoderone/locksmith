# -*- encoding: utf-8 -*-
"""Editor-side shared helpers reused across per-primitive editor pages."""
from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


_ROLE_KIND_COLORS: dict[str, str] = {
    "government": "#0ABFB0",
    "organization": "#0ABFB0",
    "individual": "#D97757",
    "system": "#888888",
    "device": "#888888",
    "agent": "#A36AE6",
}


def kind_color_for(role_kind: str) -> str:
    """CSS hex color for a role kind. Falls back to neutral grey."""
    return _ROLE_KIND_COLORS.get(role_kind, "#888888")


def make_section(title: str) -> QFrame:
    """A right-pane section frame, white card with a title row.

    Stylesheet also explicitly forces light-themed inputs on every
    QLineEdit / QPlainTextEdit / QComboBox inside the frame. Without
    this, the global Locksmith QSS sets only `color: TEXT_PRIMARY`
    on QLineEdit and Qt's macOS-side default for the background
    paints the field opaque dark — making dark-text-on-dark-fill
    invisible at full window size. Caught via the dev-control
    screenshot loop on the Commands editor; cascades fix every
    editor.
    """
    frame = QFrame()
    frame.setObjectName("editor-section")
    frame.setStyleSheet(
        "#editor-section{background:#fff;border:1px solid #e0e3ea;"
        "border-radius:6px;}"
        "#editor-section QLineEdit, #editor-section QPlainTextEdit, "
        "#editor-section QComboBox{"
        "background:#fff;color:#1A1C20;border:1px solid #e0e3ea;"
        "border-radius:4px;padding:6px 8px;}"
        "#editor-section QLineEdit:read-only, "
        "#editor-section QPlainTextEdit:read-only{"
        "background:#f6f7f9;color:#444;}"
    )
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(14, 12, 14, 12)
    lay.setSpacing(8)
    title_label = QLabel(title)
    title_label.setStyleSheet("font-size:12px;font-weight:600;color:#666;")
    lay.addWidget(title_label)
    return frame
