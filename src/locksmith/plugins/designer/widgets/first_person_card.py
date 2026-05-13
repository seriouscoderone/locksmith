# -*- encoding: utf-8 -*-
"""FirstPersonCard: an Overview card framed in first person."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)


class FirstPersonCard(QFrame):
    clicked = Signal()
    add_clicked = Signal()

    def __init__(
        self,
        *,
        framing: str,
        kind_label: str,
        count: int,
        preview_entries: list[str],
        parent=None,
    ):
        super().__init__(parent=parent)
        self.setObjectName("fpcard")
        self.setStyleSheet(
            "#fpcard{background:#fff;border:1px solid #e0e3ea;border-radius:8px;}"
            "#fpcard:hover{border:1px solid #d97757;}"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(6)

        header = QHBoxLayout()
        framing_label = QLabel(framing)
        framing_label.setStyleSheet("color:#888;font-size:11px;")
        header.addWidget(framing_label)
        header.addStretch(1)
        count_label = QLabel(str(count))
        count_label.setStyleSheet(
            "background:#f6f7f9;color:#666;border-radius:10px;"
            "padding:1px 8px;font-size:10px;font-weight:600;"
        )
        header.addWidget(count_label)
        outer.addLayout(header)

        kind = QLabel(kind_label)
        kind.setStyleSheet("font-size:15px;font-weight:600;color:#1A1C20;")
        outer.addWidget(kind)

        for entry in preview_entries[:3]:
            row = QLabel(f"• {entry}")
            row.setStyleSheet("font-size:12px;color:#444;")
            row.setWordWrap(True)
            outer.addWidget(row)
        if not preview_entries:
            empty = QLabel("(none yet)")
            empty.setStyleSheet("font-size:12px;color:#aaa;font-style:italic;")
            outer.addWidget(empty)

        add = QPushButton("+ Add")
        add.setFlat(True)
        add.setStyleSheet(
            "QPushButton{color:#666;text-align:left;border:0;padding:0;font-size:11px;}"
            "QPushButton:hover{color:#d97757;}"
        )
        add.clicked.connect(self.add_clicked.emit)
        outer.addWidget(add)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(ev)
