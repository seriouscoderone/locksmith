# -*- encoding: utf-8 -*-
"""ImportsEditorPage: 'I hold …' surface.

Right-pane sections (canonical schema):
  Identity · Expected schema SAID · Expected issuer role ·
  Lifecycle acceptance · Attribute constraints · Entry JSON · Used-by.
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


class _ImportSectionPane(QWidget):
    def __init__(self, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._crossrefs = crossrefs
        self._build()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        mono = QFont("Menlo")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(10)

        self._identity = make_section("Identity")
        self._id = QLineEdit()
        self._id.setReadOnly(True)
        self._narrative = QPlainTextEdit()
        self._narrative.setReadOnly(True)
        self._narrative.setFixedHeight(60)
        self._identity.layout().addWidget(QLabel("ID"))
        self._identity.layout().addWidget(self._id)
        self._identity.layout().addWidget(QLabel("Narrative"))
        self._identity.layout().addWidget(self._narrative)
        lay.addWidget(self._identity)

        self._schema = make_section("Expected schema (SAID)")
        self._schema_label = QLabel("(unset)")
        self._schema_label.setFont(mono)
        self._schema_label.setStyleSheet("color:#444;font-size:10px;")
        self._schema.layout().addWidget(self._schema_label)
        lay.addWidget(self._schema)

        self._issuer = make_section("Expected issuer role")
        self._issuer_label = QLabel("(any)")
        self._issuer_label.setStyleSheet("color:#444;")
        self._issuer.layout().addWidget(self._issuer_label)
        lay.addWidget(self._issuer)

        self._lifecycle = make_section("Lifecycle acceptance")
        self._lifecycle_label = QLabel("active")
        self._lifecycle_label.setStyleSheet("color:#444;")
        self._lifecycle.layout().addWidget(self._lifecycle_label)
        lay.addWidget(self._lifecycle)

        self._constraints = make_section("Attribute constraints (read-only)")
        self._constraints_view = QPlainTextEdit()
        self._constraints_view.setReadOnly(True)
        self._constraints_view.setFont(mono)
        self._constraints_view.setFixedHeight(80)
        self._constraints.layout().addWidget(self._constraints_view)
        lay.addWidget(self._constraints)

        self._json_section = make_section("Entry JSON (read-only)")
        self._json_view = QPlainTextEdit()
        self._json_view.setReadOnly(True)
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
        self._narrative.setPlainText(
            entry.get("narrative", "") or "(no narrative)"
        )
        self._schema_label.setText(entry.get("expected_schema_said", "(unset)"))
        self._issuer_label.setText(entry.get("expected_issuer_role", "(any)"))
        lifecycle = entry.get("lifecycle_acceptance", ["active"])
        self._lifecycle_label.setText(", ".join(lifecycle))
        constraints = entry.get("expected_attribute_constraints")
        if constraints:
            self._constraints_view.setPlainText(
                json.dumps(constraints, indent=2, sort_keys=True)
            )
        else:
            self._constraints_view.setPlainText("(none)")
        self._json_view.setPlainText(
            json.dumps(entry, indent=2, sort_keys=True)
        )
        self.chip_strip.set_refs(
            self._crossrefs.consumers_of(f"import:{entry.get('id', '')}")
        )

    def text_summary(self) -> str:
        return " ".join([
            self._id.text(),
            self._schema_label.text(),
            self._issuer_label.text(),
            self._lifecycle_label.text(),
        ])


class ImportsEditorPage(QWidget):
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
                id=imp.get("id", ""),
                label=imp.get("id") or "(unnamed)",
                kind_color=color,
                has_errors=False,
            )
            for imp in model.doc.get("credentials", {}).get("imports", [])
        ]
        self.shell = PrimitiveEditorShell(
            surface_label="Imported credentials",
            template_label=model.doc.get("header", {}).get(
                "display_name", "(untitled)"
            ),
            items=items,
            add_label="+ Add credential to hold",
            item_count=len(items),
            role_label=model.doc.get("role", {}).get("id", ""),
            is_valid=True,
            parent=self,
        )
        self._pane = _ImportSectionPane(crossrefs=crossrefs)
        if items:
            self._pane.set_entry(
                model.doc["credentials"]["imports"][0]
            )
        self.shell.set_right_pane(self._pane)
        self.shell.item_selected.connect(self._on_select)
        self._pane.chip_strip.navigated.connect(self.navigated.emit)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.shell)

    def _on_select(self, item_id: str) -> None:
        for imp in self._model.doc.get("credentials", {}).get("imports", []):
            if imp.get("id") == item_id:
                self._pane.set_entry(imp)
                return

    def section_text(self) -> str:
        return self._pane.text_summary()
