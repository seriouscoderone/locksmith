# -*- encoding: utf-8 -*-
"""ReactionsEditorPage: 'I respond to …' surface.

Right-pane sections (canonical schema):
  Identity · Trigger summary · Emissions · Failure policy ·
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
from locksmith.plugins.designer.editors.commands import _emission_summary
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.widgets.cross_ref_chip import CrossRefChipStrip
from locksmith.plugins.designer.widgets.kind_rail import RailItem
from locksmith.plugins.designer.widgets.primitive_editor_shell import (
    PrimitiveEditorShell,
)


def _trigger_summary(trigger: dict[str, Any]) -> str:
    t = trigger.get("type", "?")
    if t == "credential_received":
        verb = trigger.get("ipex_verb") or "any"
        return (
            f"credential_received: "
            f"{trigger.get('imported_credential_id', '?')} (verb: {verb})"
        )
    if t == "exn_received":
        return (
            f"exn_received: {trigger.get('route', '?')} "
            f"(schema: {trigger.get('schema_id') or 'any'})"
        )
    if t == "lifecycle_event":
        cid = (
            trigger.get("exported_credential_id")
            or trigger.get("imported_credential_id")
            or "?"
        )
        return f"lifecycle_event: {cid} → {trigger.get('to_state', '?')}"
    if t == "scheduled":
        return f"scheduled: {trigger.get('cadence') or trigger.get('at') or 'unset'}"
    return f"{t} (unknown)"


class _ReactionSectionPane(QWidget):
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

        self._trigger = make_section("Trigger")
        self._trigger_label = QLabel("(unset)")
        self._trigger_label.setStyleSheet(
            "color:#444;font-family:monospace;font-size:11px;"
        )
        self._trigger_label.setWordWrap(True)
        self._trigger.layout().addWidget(self._trigger_label)
        lay.addWidget(self._trigger)

        self._emissions = make_section("Emissions")
        self._emissions_label = QLabel("(none)")
        self._emissions_label.setStyleSheet("color:#444;")
        self._emissions_label.setWordWrap(True)
        self._emissions.layout().addWidget(self._emissions_label)
        lay.addWidget(self._emissions)

        self._failure = make_section("Failure policy")
        self._failure_label = QLabel("(default)")
        self._failure_label.setStyleSheet("color:#666;font-size:11px;")
        self._failure.layout().addWidget(self._failure_label)
        lay.addWidget(self._failure)

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
        self._trigger_label.setText(_trigger_summary(entry.get("trigger", {})))
        emissions = entry.get("emissions", [])
        if emissions:
            self._emissions_label.setText(
                "\n".join(f"• {_emission_summary(e)}" for e in emissions)
            )
        else:
            self._emissions_label.setText("(none)")
        fp = entry.get("failure_policy")
        if fp:
            self._failure_label.setText(
                f"on_validation_failure: {fp.get('on_validation_failure', 'default')} · "
                f"timeout: {fp.get('timeout_seconds', 'none')}"
            )
        else:
            self._failure_label.setText("(default)")
        self._json_view.setPlainText(json.dumps(entry, indent=2, sort_keys=True))
        key = f"reaction:{entry.get('id', '')}"
        self.chip_strip.set_refs(self._crossrefs.consumers_of(key))

    def text_summary(self) -> str:
        return " ".join([
            self._id.text(),
            self._trigger_label.text(),
            self._emissions_label.text(),
        ])


class ReactionsEditorPage(QWidget):
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
                id=r.get("id", ""),
                label=r.get("id") or "(unnamed)",
                kind_color=color,
                has_errors=False,
            )
            for r in model.doc.get("reactions", [])
        ]
        self.shell = PrimitiveEditorShell(
            surface_label="Reactions",
            template_label=model.doc.get("header", {}).get("display_name", "(untitled)"),
            items=items,
            add_label="+ Add reaction",
            item_count=len(items),
            role_label=model.doc.get("role", {}).get("id", ""),
            is_valid=True,
            parent=self,
        )
        self._pane = _ReactionSectionPane(crossrefs=crossrefs)
        if items:
            self._pane.set_entry(model.doc["reactions"][0])
        self.shell.set_right_pane(self._pane)
        self.shell.item_selected.connect(self._on_select)
        self._pane.chip_strip.navigated.connect(self.navigated.emit)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.shell)

    def _on_select(self, item_id: str) -> None:
        for r in self._model.doc.get("reactions", []):
            if r.get("id") == item_id:
                self._pane.set_entry(r)
                return

    def section_text(self) -> str:
        return self._pane.text_summary()
