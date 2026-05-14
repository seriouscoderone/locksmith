# -*- encoding: utf-8 -*-
"""WorkflowsEditorPage: 'I follow …' surface.

Right-pane sections (canonical schema): Identity · Trigger · Roles
involved · Steps · SwimlaneDiagram · Entry JSON · Used-by.
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
from locksmith.plugins.designer.widgets.swimlane_diagram import (
    SwimlaneDiagram, SwimlaneStep,
)


def _trigger_summary(trigger: dict[str, Any]) -> str:
    t = trigger.get("type", "?")
    bits = [t]
    for key in ("initiator_role", "cadence", "at", "credential_id",
                "imported_credential_id", "to_state", "route", "ipex_verb"):
        if trigger.get(key):
            bits.append(f"{key}={trigger[key]}")
    return " · ".join(bits)


class _WorkflowSectionPane(QWidget):
    def __init__(self, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._crossrefs = crossrefs
        self._build()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

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

        self._trigger = make_section("Trigger")
        self._trigger_label = QLabel("(unset)")
        self._trigger_label.setStyleSheet("color:#444;font-family:monospace;font-size:11px;")
        self._trigger_label.setWordWrap(True)
        self._trigger.layout().addWidget(self._trigger_label)
        lay.addWidget(self._trigger)

        self._roles = make_section("Roles involved")
        self._roles_label = QLabel("(none)")
        self._roles_label.setStyleSheet("color:#444;")
        self._roles.layout().addWidget(self._roles_label)
        lay.addWidget(self._roles)

        self._diagram_section = make_section("Swimlane diagram")
        self.diagram = SwimlaneDiagram()
        self.diagram.setFixedHeight(200)
        self._diagram_section.layout().addWidget(self.diagram)
        lay.addWidget(self._diagram_section)

        self._steps = make_section("Steps")
        self._steps_list = QLabel("(none)")
        self._steps_list.setStyleSheet("color:#444;")
        self._steps_list.setWordWrap(True)
        self._steps.layout().addWidget(self._steps_list)
        lay.addWidget(self._steps)

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
        self._name.setText(entry.get("name", ""))
        self._id.setText(entry.get("id", ""))
        self._description.setPlainText(entry.get("description", ""))
        self._trigger_label.setText(_trigger_summary(entry.get("trigger", {})))

        steps = entry.get("steps", [])
        actors: list[str] = []
        for s in steps:
            a = s.get("actor")
            if a and a not in actors:
                actors.append(a)
        cp_role = entry.get("counterparty_role")
        roles_text = ", ".join(actors)
        if cp_role:
            roles_text += f" (counterparty = {cp_role})"
        self._roles_label.setText(roles_text or "(none)")

        if steps:
            self._steps_list.setText("\n".join(
                f"{i + 1}. {s.get('name', '?')} ({s.get('actor', '?')})"
                for i, s in enumerate(steps)
            ))
        else:
            self._steps_list.setText("(none)")

        self.diagram.render(
            lanes=actors if actors else ["self"],
            steps=[SwimlaneStep(step_id=s.get("id", f"step{i}"),
                                label=s.get("name", "?"),
                                actor=s.get("actor", "self"))
                   for i, s in enumerate(steps)],
        )
        self._json_view.setPlainText(json.dumps(entry, indent=2, sort_keys=True))
        self.chip_strip.set_refs(
            self._crossrefs.consumers_of(f"workflow:{entry.get('id', '')}")
        )


class WorkflowsEditorPage(QWidget):
    navigated = Signal(str, str)

    def __init__(self, *, model: TemplateModel, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._model = model
        color = kind_color_for(model.doc.get("role", {}).get("kind", ""))
        items = [
            RailItem(
                id=w.get("id", ""),
                label=w.get("name") or w.get("id") or "(unnamed)",
                kind_color=color,
                has_errors=False,
            )
            for w in model.doc.get("workflows", [])
        ]
        self.shell = PrimitiveEditorShell(
            surface_label="Workflows",
            template_label=model.doc.get("header", {}).get("display_name", "(untitled)"),
            items=items,
            add_label="+ Add workflow",
            item_count=len(items),
            role_label=model.doc.get("role", {}).get("id", ""),
            is_valid=True,
            parent=self,
        )
        self._pane = _WorkflowSectionPane(crossrefs=crossrefs)
        if items:
            self._pane.set_entry(model.doc["workflows"][0])
        self.shell.set_right_pane(self._pane)
        from locksmith.plugins.designer.widgets.validation_panel import (
            ValidationPanel,
        )
        from locksmith.plugins.designer.widgets.json_source_view import (
            JsonSourceView,
        )
        self._validation_panel = ValidationPanel()
        self._json_source_view = JsonSourceView()
        self.shell.set_side_panel(self._validation_panel)
        self.shell.set_bottom_panel(self._json_source_view)
        self.shell.item_selected.connect(self._on_select)
        self._pane.chip_strip.navigated.connect(self.navigated.emit)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.shell)

    def _on_select(self, item_id: str) -> None:
        for w in self._model.doc.get("workflows", []):
            if w.get("id") == item_id:
                self._pane.set_entry(w)
                return

    def swimlane_step_count(self) -> int:
        return self._pane.diagram.step_count
