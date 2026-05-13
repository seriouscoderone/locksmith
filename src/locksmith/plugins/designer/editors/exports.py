# -*- encoding: utf-8 -*-
"""ExportsEditorPage: 'I issue …' surface.

Right-pane sections (canonical schema):
  Identity · Envelope summary · Schema SAID · TEL lifecycle (state
  machine diagram color-coded by tel_primitive) · States list ·
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
from locksmith.plugins.designer.widgets.state_machine_diagram import (
    StateMachineDiagram, StateTransition,
)


class _ExportSectionPane(QWidget):
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
        self._name = QLineEdit()
        self._id = QLineEdit()
        self._id.setReadOnly(True)
        self._description = QPlainTextEdit()
        self._description.setReadOnly(True)
        self._description.setFixedHeight(50)
        self._identity.layout().addWidget(QLabel("Name"))
        self._identity.layout().addWidget(self._name)
        self._identity.layout().addWidget(QLabel("ID"))
        self._identity.layout().addWidget(self._id)
        self._identity.layout().addWidget(QLabel("Description"))
        self._identity.layout().addWidget(self._description)
        lay.addWidget(self._identity)

        self._envelope = make_section("Envelope")
        self._envelope_label = QLabel("(unset)")
        self._envelope_label.setStyleSheet("color:#444;font-size:11px;")
        self._envelope.layout().addWidget(self._envelope_label)
        lay.addWidget(self._envelope)

        self._schema = make_section("Schema (SAID)")
        self._schema_label = QLabel("(unset)")
        self._schema_label.setFont(mono)
        self._schema_label.setStyleSheet("color:#444;font-size:10px;")
        self._schema.layout().addWidget(self._schema_label)
        lay.addWidget(self._schema)

        self._lifecycle = make_section("TEL lifecycle")
        self.diagram = StateMachineDiagram()
        self.diagram.setFixedHeight(180)
        self._lifecycle.layout().addWidget(self.diagram)
        lay.addWidget(self._lifecycle)

        self._states = make_section("States")
        self._states_label = QLabel("(none)")
        self._states_label.setStyleSheet("color:#444;")
        self._states_label.setTextFormat(
            # Allow bold HTML for the initial state highlight
            self._states_label.textFormat()
        )
        self._states.layout().addWidget(self._states_label)
        lay.addWidget(self._states)

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
        self._name.setText(entry.get("name", ""))
        self._id.setText(entry.get("id", ""))
        self._description.setPlainText(entry.get("description", ""))

        env = entry.get("envelope", {})
        self._envelope_label.setText(
            f"holder = {env.get('holder_role', '?')} · "
            f"disclosure = {env.get('disclosure_mode', '?')} · "
            f"verifiers = {', '.join(env.get('verifier_roles', [])) or '(none)'}"
        )

        schema = entry.get("schema", {})
        self._schema_label.setText(schema.get("schema_said", "(unset)"))

        lifecycle = entry.get("lifecycle", {})
        transitions = [
            StateTransition(
                from_state=t.get("from", ""),
                to_state=t.get("to", ""),
                tel_primitive=t.get("tel_primitive", "update"),
            )
            for t in lifecycle.get("transitions", [])
        ]
        self.diagram.render(transitions)

        states = lifecycle.get("states", [])
        initial = lifecycle.get("initial", "")
        decorated = [
            f"<b>{s}</b> (initial)" if s == initial else s
            for s in states
        ]
        self._states_label.setText(", ".join(decorated) if decorated else "(none)")

        self._json_view.setPlainText(json.dumps(entry, indent=2, sort_keys=True))
        self.chip_strip.set_refs(
            self._crossrefs.consumers_of(f"export:{entry.get('id', '')}")
        )


class ExportsEditorPage(QWidget):
    navigated = Signal(str, str)

    def __init__(self, *, model: TemplateModel, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._model = model
        color = kind_color_for(model.doc.get("role", {}).get("kind", ""))
        items = [
            RailItem(
                id=exp.get("id", ""),
                label=exp.get("name") or exp.get("id") or "(unnamed)",
                kind_color=color,
                has_errors=False,
            )
            for exp in model.doc.get("credentials", {}).get("exports", [])
        ]
        self.shell = PrimitiveEditorShell(
            surface_label="Issued credentials",
            template_label=model.doc.get("header", {}).get("display_name", "(untitled)"),
            items=items,
            parent=self,
        )
        self._pane = _ExportSectionPane(crossrefs=crossrefs)
        if items:
            self._pane.set_entry(model.doc["credentials"]["exports"][0])
        self.shell.set_right_pane(self._pane)
        self.shell.item_selected.connect(self._on_select)
        self._pane.chip_strip.navigated.connect(self.navigated.emit)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.shell)

    def _on_select(self, item_id: str) -> None:
        for exp in self._model.doc.get("credentials", {}).get("exports", []):
            if exp.get("id") == item_id:
                self._pane.set_entry(exp)
                return

    def state_count(self) -> int:
        return self._pane.diagram.state_count
