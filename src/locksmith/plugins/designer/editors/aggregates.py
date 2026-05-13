# -*- encoding: utf-8 -*-
"""AggregatesEditorPage: 'I track …' surface.

Right-pane sections (canonical schema):
  Identity · Inception event type · Log scope · Invariants ·
  Entry JSON · Used-by.
"""
from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QLabel, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget,
)

from locksmith.plugins.designer.crossref import CrossRefIndex
from locksmith.plugins.designer.editors._shared import (
    kind_color_for, make_section,
)
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.widgets.cross_ref_chip import CrossRefChipStrip
from locksmith.plugins.designer.widgets.kind_rail import RailItem
from locksmith.plugins.designer.widgets.primitive_editor_shell import (
    PrimitiveEditorShell,
)


class _AggregateSectionPane(QWidget):
    def __init__(self, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._crossrefs = crossrefs
        self._build()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        self._identity = make_section("Identity")
        self._id = QLineEdit()
        self._id.setReadOnly(True)
        self._description = QPlainTextEdit()
        self._description.setReadOnly(True)
        self._description.setFixedHeight(60)
        self._identity.layout().addWidget(QLabel("ID"))
        self._identity.layout().addWidget(self._id)
        self._identity.layout().addWidget(QLabel("Description"))
        self._identity.layout().addWidget(self._description)
        lay.addWidget(self._identity)

        self._inception = make_section("Inception event type")
        self._inception_label = QLabel("(unset)")
        self._inception_label.setStyleSheet(
            "color:#444;font-family:monospace;font-size:11px;"
        )
        self._inception.layout().addWidget(self._inception_label)
        lay.addWidget(self._inception)

        self._log = make_section("Log scope")
        self._log_label = QLabel("(unset)")
        self._log_label.setStyleSheet("color:#444;font-weight:600;")
        self._log.layout().addWidget(self._log_label)
        lay.addWidget(self._log)

        self._invariants = make_section("Invariants")
        self._invariants_label = QLabel("(none)")
        self._invariants_label.setStyleSheet("color:#444;")
        self._invariants_label.setWordWrap(True)
        self._invariants.layout().addWidget(self._invariants_label)
        lay.addWidget(self._invariants)

        self._json_section = make_section("Entry JSON (read-only)")
        self._json_view = QPlainTextEdit()
        self._json_view.setReadOnly(True)
        mono = QFont("Menlo")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(10)
        self._json_view.setFont(mono)
        self._json_view.setFixedHeight(120)
        self._json_section.layout().addWidget(self._json_view)
        lay.addWidget(self._json_section)

        self._used_by = make_section("Used by")
        self.chip_strip = CrossRefChipStrip()
        self._used_by.layout().addWidget(self.chip_strip)
        lay.addWidget(self._used_by)
        lay.addStretch(1)

    def set_entry(self, entry: dict[str, Any]) -> None:
        self._id.setText(entry.get("id", ""))
        self._description.setPlainText(entry.get("description", ""))
        self._inception_label.setText(
            entry.get("inception_event_type", "(unset)")
        )
        self._log_label.setText(entry.get("log_scope", "(unset)"))
        invariants = entry.get("invariants", [])
        if invariants:
            refs = [inv.get("rule_ref", "?") for inv in invariants]
            self._invariants_label.setText(
                f"{len(refs)}: " + ", ".join(refs)
            )
        else:
            self._invariants_label.setText("(none)")
        self._json_view.setPlainText(
            json.dumps(entry, indent=2, sort_keys=True)
        )
        key = f"aggregate:{entry.get('id', '')}"
        self.chip_strip.set_refs(self._crossrefs.consumers_of(key))

    def text_summary(self) -> str:
        return " ".join([
            self._id.text(),
            self._inception_label.text(),
            self._log_label.text(),
            self._invariants_label.text(),
        ])


class AggregatesEditorPage(QWidget):
    navigated = Signal(str, str)

    def __init__(
        self,
        *,
        model: TemplateModel,
        crossrefs: CrossRefIndex,
        parent=None,
    ):
        super().__init__(parent=parent)
        self._model = model
        color = kind_color_for(model.doc.get("role", {}).get("kind", ""))
        items = [
            RailItem(
                id=a.get("id", ""),
                label=a.get("name") or a.get("id") or "(unnamed)",
                kind_color=color,
                has_errors=False,
            )
            for a in model.doc.get("aggregates", [])
        ]
        self.shell = PrimitiveEditorShell(
            surface_label="Aggregates",
            template_label=model.doc.get("header", {}).get(
                "display_name", "(untitled)"
            ),
            items=items,
            parent=self,
        )
        self._pane = _AggregateSectionPane(crossrefs=crossrefs)
        if items:
            self._pane.set_entry(model.doc["aggregates"][0])
        self.shell.set_right_pane(self._pane)
        self.shell.item_selected.connect(self._on_select)
        self._pane.chip_strip.navigated.connect(self.navigated.emit)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.shell)

    def _on_select(self, item_id: str) -> None:
        for a in self._model.doc.get("aggregates", []):
            if a.get("id") == item_id:
                self._pane.set_entry(a)
                return

    def section_text(self) -> str:
        return self._pane.text_summary()
