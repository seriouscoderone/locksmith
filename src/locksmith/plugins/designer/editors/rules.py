# -*- encoding: utf-8 -*-
"""RulesEditorPage: 'I'm bound by …' surface.

Rules are color-coded by type in the rail. Right-pane sections vary
per rule type: prose types show body; computational/predicate/validation
types show expression + language. Predicates also surface their purpose.
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
from locksmith.plugins.designer.editors._shared import make_section
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.widgets.cross_ref_chip import CrossRefChipStrip
from locksmith.plugins.designer.widgets.kind_rail import RailItem
from locksmith.plugins.designer.widgets.primitive_editor_shell import (
    PrimitiveEditorShell,
)


_RULE_TYPE_COLOR: dict[str, str] = {
    "legal_prose": "#4A4FCE",
    "behavioral_expectation": "#A36AE6",
    "business_policy": "#D9A04F",
    "predicate": "#0ABFB0",
    "computational": "#D9A04F",
    "validation": "#E94B4B",
    "binding_link": "#888888",
}


def rule_type_color(rule_type: str) -> str:
    return _RULE_TYPE_COLOR.get(rule_type, "#888888")


_PROSE_TYPES = {"legal_prose", "behavioral_expectation", "business_policy"}
_EXPR_TYPES = {"predicate", "computational", "validation"}


class _RuleSectionPane(QWidget):
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
        self._title_field = QLineEdit()
        self._description = QPlainTextEdit()
        self._description.setReadOnly(True)
        self._description.setFixedHeight(50)
        self._identity.layout().addWidget(QLabel("ID"))
        self._identity.layout().addWidget(self._id)
        self._identity.layout().addWidget(QLabel("Title"))
        self._identity.layout().addWidget(self._title_field)
        self._identity.layout().addWidget(QLabel("Description"))
        self._identity.layout().addWidget(self._description)
        lay.addWidget(self._identity)

        self._type_section = make_section("Type")
        self._type_label = QLabel("(unset)")
        self._type_section.layout().addWidget(self._type_label)
        lay.addWidget(self._type_section)

        self._body_section = make_section("Body / Expression")
        self._body_text = QPlainTextEdit()
        self._body_text.setReadOnly(True)
        self._body_text.setFixedHeight(80)
        self._body_section.layout().addWidget(self._body_text)
        lay.addWidget(self._body_section)

        self._extras = make_section("Type-specific fields")
        self._extras_label = QLabel("(none)")
        self._extras_label.setStyleSheet("color:#444;font-size:11px;")
        self._extras_label.setWordWrap(True)
        self._extras.layout().addWidget(self._extras_label)
        lay.addWidget(self._extras)

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
        self._title_field.setText(entry.get("title", ""))
        self._description.setPlainText(entry.get("description", ""))

        rtype = entry.get("type", "")
        color = rule_type_color(rtype)
        self._type_label.setText(f"<b style='color:{color};'>{rtype}</b>")

        if rtype in _PROSE_TYPES:
            self._body_text.setPlainText(entry.get("body", "(no body)"))
        elif rtype in _EXPR_TYPES:
            expr = entry.get("expression", "(no expression)")
            lang = entry.get("language", "?")
            self._body_text.setPlainText(f"# language: {lang}\n{expr}")
        else:
            self._body_text.setPlainText("(no body)")

        extras = []
        if rtype == "predicate" and entry.get("purpose"):
            extras.append(f"purpose: {entry['purpose']}")
        if rtype == "computational" and entry.get("result_attribute"):
            extras.append(f"result_attribute: {entry['result_attribute']}")
        if rtype == "binding_link":
            links = entry.get("links", [])
            extras.append(
                f"links: {', '.join(L.get('rule_id', '?') for L in links)}"
                if links else "links: (none)"
            )
        self._extras_label.setText("\n".join(extras) if extras else "(none)")

        self._json_view.setPlainText(json.dumps(entry, indent=2, sort_keys=True))
        self.chip_strip.set_refs(
            self._crossrefs.consumers_of(f"rule:{entry.get('id', '')}")
        )

    def text_summary(self) -> str:
        return " ".join([
            self._id.text(),
            self._title_field.text(),
            self._type_label.text(),
            self._body_text.toPlainText(),
            self._extras_label.text(),
        ])


class RulesEditorPage(QWidget):
    navigated = Signal(str, str)

    def __init__(self, *, model: TemplateModel, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._model = model
        items = [
            RailItem(
                id=r.get("id", ""),
                label=r.get("title") or r.get("id") or "(unnamed)",
                kind_color=rule_type_color(r.get("type", "")),
                has_errors=False,
            )
            for r in model.doc.get("rules", [])
        ]
        self.shell = PrimitiveEditorShell(
            surface_label="Rules",
            template_label=model.doc.get("header", {}).get("display_name", "(untitled)"),
            items=items,
            parent=self,
        )
        self._pane = _RuleSectionPane(crossrefs=crossrefs)
        if items:
            self._pane.set_entry(model.doc["rules"][0])
        self.shell.set_right_pane(self._pane)
        self.shell.item_selected.connect(self._on_select)
        self._pane.chip_strip.navigated.connect(self.navigated.emit)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.shell)

    def _on_select(self, item_id: str) -> None:
        for r in self._model.doc.get("rules", []):
            if r.get("id") == item_id:
                self._pane.set_entry(r)
                return

    def section_text(self) -> str:
        return self._pane.text_summary()
