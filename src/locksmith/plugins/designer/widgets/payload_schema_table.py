# -*- encoding: utf-8 -*-
"""PayloadSchemaTable: render a JSON-Schema object as Field/Type/Constraint rows.

Used by the Commands editor right pane. Display-only — the "+ Add field"
button visible at the bottom is wired in Phase 2.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)


class PayloadSchemaTable(QFrame):
    def __init__(self, schema: dict[str, Any], parent=None):
        super().__init__(parent=parent)
        self._rows: list[dict[str, Any]] = []
        properties = schema.get("properties", {}) or {}
        required_list = schema.get("required", []) or []
        mono = QFont("Menlo")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(10)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 4)
        for label, weight in (("FIELD", 4), ("TYPE", 2), ("CONSTRAINT", 6)):
            lbl = QLabel(label)
            lbl.setStyleSheet(
                "font-size:10px;color:#888;font-weight:600;letter-spacing:0.5px;"
            )
            header.addWidget(lbl, weight)
        outer.addLayout(header)

        for name, spec in properties.items():
            field_type = spec.get("type", "")
            constraint = _summarize_constraint(spec)
            is_required = name in required_list
            row_data = {
                "field": name,
                "type": field_type,
                "constraint": constraint,
                "required": is_required,
            }
            self._rows.append(row_data)
            row = QHBoxLayout()
            row.setContentsMargins(0, 2, 0, 2)
            field_lbl = QLabel(name)
            field_lbl.setFont(mono)
            field_lbl.setStyleSheet("color:#1A1C20;")
            row.addWidget(field_lbl, 4)
            type_lbl = QLabel(field_type + ("[]" if field_type == "array" else ""))
            type_lbl.setStyleSheet("color:#666;font-size:11px;")
            row.addWidget(type_lbl, 2)
            cons_lbl = QLabel(constraint)
            cons_lbl.setStyleSheet("color:#666;font-size:11px;")
            cons_lbl.setWordWrap(True)
            row.addWidget(cons_lbl, 6)
            outer.addLayout(row)
            if is_required:
                req_lbl = QLabel("req")
                req_lbl.setStyleSheet(
                    "color:#0ABFB0;font-size:9px;font-weight:600;"
                    "background:transparent;"
                )
                row.addWidget(req_lbl)

        add_btn = QPushButton("+ Add field")
        add_btn.setFlat(True)
        add_btn.setStyleSheet(
            "QPushButton{color:#0ABFB0;background:transparent;border:0;"
            "padding:6px 0;font-size:11px;font-weight:600;}"
            "QPushButton:hover{color:#1A1C20;}"
        )
        outer.addWidget(add_btn)

    def field_rows(self) -> list[dict[str, Any]]:
        return list(self._rows)


def _summarize_constraint(spec: dict[str, Any]) -> str:
    bits: list[str] = []
    if "pattern" in spec:
        bits.append(spec["pattern"])
    if "format" in spec:
        bits.append(f"format: {spec['format']}")
    if "enum" in spec:
        bits.append("enum: " + ", ".join(spec["enum"][:4])
                    + (", …" if len(spec["enum"]) > 4 else ""))
    if spec.get("type") == "array":
        items = spec.get("items", {})
        if isinstance(items, dict) and "enum" in items:
            bits.append("enum: " + ", ".join(items["enum"][:4])
                        + (", …" if len(items["enum"]) > 4 else ""))
    return " · ".join(bits)
