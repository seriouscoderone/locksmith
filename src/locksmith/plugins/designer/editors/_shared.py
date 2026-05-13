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
    """A right-pane section frame, white card with a title row."""
    frame = QFrame()
    frame.setStyleSheet(
        "QFrame{background:#fff;border:1px solid #e0e3ea;border-radius:6px;}"
    )
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(14, 12, 14, 12)
    lay.setSpacing(8)
    title_label = QLabel(title)
    title_label.setStyleSheet("font-size:12px;font-weight:600;color:#666;")
    lay.addWidget(title_label)
    return frame
