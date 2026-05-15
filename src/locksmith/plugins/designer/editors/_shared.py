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
    """A right-pane section: uppercase teal label + content, no card chrome.

    Earlier iterations wrapped every section in its own white-bordered
    card, which produced a "every text in a grey box" effect (8 boxes
    stacked vertically per editor). The v1 mocks instead use flat
    sections — a small uppercase teal section header with content
    flowing beneath on the page's shared surface. This shape matches.

    The descendant-selector stylesheet on QLineEdit/QPlainTextEdit/
    QComboBox remains: macOS Qt paints the default field background
    dark unless we force light, so input widgets inside the section
    still need the explicit white-fill rule. Caught via the dev-control
    screenshot loop on the Commands editor.
    """
    frame = QFrame()
    frame.setObjectName("editor-section")
    frame.setStyleSheet(
        "#editor-section QLineEdit, #editor-section QPlainTextEdit, "
        "#editor-section QComboBox{"
        "background:#fff;color:#1A1C20;border:1px solid #e0e3ea;"
        "border-radius:4px;padding:6px 8px;}"
        "#editor-section QLineEdit:read-only, "
        "#editor-section QPlainTextEdit:read-only{"
        "background:#f6f7f9;color:#444;border:0;}"
    )
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(0, 0, 0, 4)
    lay.setSpacing(6)
    title_label = QLabel(title.upper())
    title_label.setStyleSheet(
        "font-size:10px;font-weight:600;color:#0ABFB0;"
        "letter-spacing:0.5px;background:transparent;"
    )
    lay.addWidget(title_label)
    return frame
