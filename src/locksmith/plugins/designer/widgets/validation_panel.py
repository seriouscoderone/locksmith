# -*- encoding: utf-8 -*-
"""ValidationPanel: side panel listing all validation issues grouped by surface.

Each issue row is a button that emits issue_clicked(surface, path) on
click. The controller wires this to navigate to the offending editor
and scroll to the field.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from locksmith.plugins.designer.validation import ValidationIssue, ValidationReport


class _IssueRow(QPushButton):
    clicked_with = Signal(str, str)

    def __init__(self, issue: ValidationIssue, parent=None):
        super().__init__(parent=parent)
        glyph = "⛔" if issue.severity == "error" else "⚠"
        self.setText(f"{glyph} {issue.message}\n   → {issue.path or '<root>'}")
        self.setFlat(True)
        color = "#9b1d1d" if issue.severity == "error" else "#7a5b00"
        self.setStyleSheet(
            f"QPushButton{{text-align:left;color:{color};border:0;"
            f"padding:6px 12px;background:transparent;}}"
            f"QPushButton:hover{{background:#fbe9e9;}}"
        )
        self.clicked.connect(lambda: self.clicked_with.emit(issue.surface, issue.path))


class ValidationPanel(QWidget):
    issue_clicked = Signal(str, str)  # surface, path

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setStyleSheet("background:#fff;border-left:1px solid #e0e3ea;")
        self._rows: list[_IssueRow] = []
        self._surface_count = 0
        self._total = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        header = QLabel("Validation")
        header.setStyleSheet(
            "font-size:13px;font-weight:600;color:#1A1C20;"
            "padding:10px 12px;border-bottom:1px solid #e0e3ea;"
        )
        outer.addWidget(header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("border:0;")
        self._host = QWidget()
        self._host_lay = QVBoxLayout(self._host)
        self._host_lay.setContentsMargins(0, 6, 0, 6)
        self._host_lay.setSpacing(0)
        self._scroll.setWidget(self._host)
        outer.addWidget(self._scroll, 1)

    def set_report(self, report: ValidationReport) -> None:
        # Clear existing rows.
        for r in self._rows:
            r.setParent(None)
            r.deleteLater()
        self._rows = []
        while self._host_lay.count():
            item = self._host_lay.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

        self._total = len(report.errors) + len(report.warnings)
        if self._total == 0:
            empty = QLabel("No issues — template is valid.")
            empty.setStyleSheet("color:#1b5e20;padding:20px;")
            self._host_lay.addWidget(empty)
            self._surface_count = 0
            return

        # Group by surface; errors first within each group.
        grouped: dict[str, list[ValidationIssue]] = {}
        for i in report.errors:
            grouped.setdefault(i.surface, []).append(i)
        for i in report.warnings:
            grouped.setdefault(i.surface, []).append(i)
        self._surface_count = len(grouped)

        for surface in sorted(grouped.keys()):
            sh = QLabel(surface.upper())
            sh.setStyleSheet(
                "color:#666;font-size:11px;font-weight:700;"
                "padding:8px 12px 4px;letter-spacing:0.5px;"
            )
            self._host_lay.addWidget(sh)
            for issue in grouped[surface]:
                row = _IssueRow(issue)
                row.clicked_with.connect(self.issue_clicked.emit)
                self._host_lay.addWidget(row)
                self._rows.append(row)
            sep = QFrame()
            sep.setFixedHeight(1)
            sep.setStyleSheet("background:#f0f2f5;")
            self._host_lay.addWidget(sep)
        self._host_lay.addStretch(1)

    def surface_count(self) -> int:
        return self._surface_count

    def total_issue_count(self) -> int:
        return self._total

    def click_first_issue(self) -> None:
        if self._rows:
            self._rows[0].click()
