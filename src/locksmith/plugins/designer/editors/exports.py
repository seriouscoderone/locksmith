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
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QStackedWidget, QVBoxLayout, QWidget,
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
        from locksmith.plugins.designer.widgets.editor_tab_bar import (
            EditorTabBar,
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        # Header.
        self._header_frame = QFrame()
        h = QVBoxLayout(self._header_frame)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self._name_label = QLabel("")
        self._name_label.setStyleSheet(
            "font-size:16px;font-weight:600;color:#1A1C20;"
        )
        title_row.addWidget(self._name_label)
        self._id_chip = QLabel("")
        self._id_chip.setStyleSheet(
            "color:#666;background:#f6f7f9;font-family:monospace;"
            "border-radius:6px;padding:2px 8px;font-size:10px;"
        )
        title_row.addWidget(self._id_chip)
        title_row.addStretch(1)
        said_title = QLabel("Schema SAID:")
        said_title.setStyleSheet("font-size:10px;color:#888;")
        title_row.addWidget(said_title)
        self._said_label = QLabel("")
        self._said_label.setStyleSheet(
            "color:#666;font-family:monospace;font-size:10px;"
            "background:#f6f7f9;border-radius:6px;padding:2px 8px;"
        )
        title_row.addWidget(self._said_label)
        h.addLayout(title_row)
        self._description_label = QLabel("")
        self._description_label.setStyleSheet("color:#444;font-size:12px;")
        self._description_label.setWordWrap(True)
        h.addWidget(self._description_label)
        lay.addWidget(self._header_frame)

        self.tab_bar = EditorTabBar(
            ["Envelope", "Schema", "Lifecycle", "Rules", "Value flow"],
        )
        self.tab_bar.set_active("Lifecycle")
        self.tab_bar.tab_changed.connect(self._on_tab_changed)
        lay.addWidget(self.tab_bar)

        self._stack = QStackedWidget()
        lay.addWidget(self._stack, 1)
        self._tab_widgets: dict[str, QWidget] = {}
        for name in self.tab_bar.tab_names():
            w = self._build_tab(name)
            self._tab_widgets[name] = w
            self._stack.addWidget(w)
        # Diagram lives in the Lifecycle tab. Stash a reference; the
        # full Lifecycle content (diagram + transitions list) is rebuilt
        # by _fill_lifecycle_tab each time set_entry runs.
        self.diagram = StateMachineDiagram()
        self.diagram.setFixedHeight(200)
        self._stack.setCurrentWidget(self._tab_widgets["Lifecycle"])

        # Used-by stays outside the tabs.
        self._used_by = make_section("Used by")
        self.chip_strip = CrossRefChipStrip()
        self._used_by.layout().addWidget(self.chip_strip)
        lay.addWidget(self._used_by)

    def _build_tab(self, name: str) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        holder = QFrame()
        holder_lay = QVBoxLayout(holder)
        holder_lay.setContentsMargins(0, 0, 0, 0)
        holder_lay.setSpacing(8)
        w.setProperty("holder", holder)
        lay.addWidget(holder)
        lay.addStretch(1)
        # Non-Lifecycle tabs get a stub placeholder until later phases.
        if name != "Lifecycle":
            stub = QLabel(f"({name} content — Phase 3b/3c follow-up)")
            stub.setStyleSheet("color:#aaa;font-style:italic;font-size:11px;")
            holder_lay.addWidget(stub)
        return w

    def _on_tab_changed(self, name: str) -> None:
        if name in self._tab_widgets:
            self._stack.setCurrentWidget(self._tab_widgets[name])

    def set_entry(self, entry: dict[str, Any]) -> None:
        self._current_entry = entry
        self._name_label.setText(entry.get("name") or entry.get("id") or "(unnamed)")
        self._id_chip.setText(entry.get("id", ""))
        said = (entry.get("schema") or {}).get("schema_said") or ""
        short = said[:4] + "…" + said[-6:] if len(said) > 12 else said
        self._said_label.setText(short)
        self._description_label.setText(entry.get("description", ""))

        # Refresh diagram + Lifecycle tab content.
        lifecycle = entry.get("lifecycle") or {}
        transitions = [
            StateTransition(
                from_state=t.get("from", ""),
                to_state=t.get("to", ""),
                tel_primitive=t.get("tel_primitive", "update"),
            )
            for t in lifecycle.get("transitions", [])
        ]
        self.diagram.render(transitions)

        lifecycle_holder = self._tab_widgets["Lifecycle"].property("holder")
        holder_lay = lifecycle_holder.layout()
        while holder_lay.count():
            old = holder_lay.takeAt(0).widget()
            if old is not None:
                old.setParent(None)
                # Don't deleteLater the diagram — re-add it below.
                if old is not self.diagram:
                    old.deleteLater()
        self._fill_lifecycle_tab(lifecycle_holder, entry)

        self.chip_strip.set_refs(
            self._crossrefs.consumers_of(f"export:{entry.get('id', '')}")
        )

    def _fill_lifecycle_tab(self, holder: QFrame, entry: dict) -> None:
        from locksmith.plugins.designer.widgets.rule_chip_strip import (
            RuleChipStrip,
        )

        lc = entry.get("lifecycle") or {}
        transitions = lc.get("transitions") or []
        initial = lc.get("initial", "")
        n_states = len(lc.get("states") or [])
        n_trans = len(transitions)

        # State-machine title row.
        title_row = QHBoxLayout()
        title = QLabel("State machine")
        title.setStyleSheet("font-size:13px;font-weight:600;color:#1A1C20;")
        title_row.addWidget(title)
        sub = QLabel(
            f"{n_states} states · {n_trans} transitions · "
            f"initial state: <b>{initial}</b>"
        )
        sub.setStyleSheet("color:#888;font-size:11px;")
        title_row.addWidget(sub)
        title_row.addStretch(1)
        holder.layout().addLayout(title_row)
        holder.layout().addWidget(self.diagram)

        # Transitions list.
        trans_section = make_section("Transitions")
        for t in transitions:
            row = QHBoxLayout()
            row.setSpacing(6)
            from_val = t.get("from", "")
            from_text = (
                ", ".join(from_val) if isinstance(from_val, list) else from_val
            )
            to_val = t.get("to", "")
            chip_from = QLabel(from_text)
            chip_from.setStyleSheet(
                "background:#f0f2f5;color:#444;border-radius:9px;"
                "padding:2px 8px;font-size:11px;"
            )
            arrow = QLabel("→")
            arrow.setStyleSheet("color:#888;font-size:12px;")
            chip_to = QLabel(to_val)
            chip_to.setStyleSheet(
                "background:#f0f2f5;color:#444;border-radius:9px;"
                "padding:2px 8px;font-size:11px;"
            )
            row.addWidget(chip_from)
            row.addWidget(arrow)
            row.addWidget(chip_to)
            via = t.get("via_workflow")
            if via:
                via_lbl = QLabel(f"via workflow {via}")
                via_lbl.setStyleSheet("color:#0ABFB0;font-size:11px;")
                row.addWidget(via_lbl)
            requires = [r.get("rule_ref", "") for r in (t.get("requires") or [])
                        if r.get("rule_ref")]
            if requires:
                req_lbl = QLabel("· requires")
                req_lbl.setStyleSheet("color:#888;font-size:11px;")
                row.addWidget(req_lbl)
                row.addWidget(RuleChipStrip(requires))
            row.addStretch(1)
            prim_chip = QLabel(t.get("tel_primitive", ""))
            prim_chip.setStyleSheet(
                f"color:{_tel_color(t.get('tel_primitive', ''))};"
                "font-size:10px;font-weight:600;background:transparent;"
            )
            row.addWidget(prim_chip)
            trans_section.layout().addLayout(row)
        holder.layout().addWidget(trans_section)

    def text_summary(self) -> str:
        return " ".join([
            self._name_label.text(),
            self._id_chip.text(),
            self._said_label.text(),
            self._description_label.text(),
        ])


def _tel_color(prim: str) -> str:
    return {"issue": "#D97757", "update": "#0ABFB0",
            "revoke": "#E94B7B"}.get(prim, "#666")


def _export_subtitle(exp: dict) -> str:
    env = exp.get("envelope") or {}
    lc = exp.get("lifecycle") or {}
    parts: list[str] = []
    if env.get("holder_role"):
        parts.append(f"→ {env['holder_role']}")
    states = lc.get("states") or []
    if states:
        parts.append(f"{len(states)} states")
    rule_count = len(exp.get("rule_refs") or [])
    for t in (lc.get("transitions") or []):
        if t.get("condition_rule_ref"):
            rule_count += 1
        for r in (t.get("requires") or []):
            if r.get("rule_ref"):
                rule_count += 1
    if rule_count:
        parts.append(f"{rule_count} rules")
    return " · ".join(parts) if parts else ""


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
                subtitle=_export_subtitle(exp),
                kind_color=color,
                has_errors=False,
            )
            for exp in model.doc.get("credentials", {}).get("exports", [])
        ]
        self.shell = PrimitiveEditorShell(
            surface_label="Issued credentials",
            template_label=model.doc.get("header", {}).get("display_name", "(untitled)"),
            items=items,
            add_label="+ Add credential to issue",
            item_count=len(items),
            role_label=model.doc.get("role", {}).get("id", ""),
            is_valid=True,
            parent=self,
        )
        self._pane = _ExportSectionPane(crossrefs=crossrefs)
        if items:
            self._pane.set_entry(model.doc["credentials"]["exports"][0])
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
        for exp in self._model.doc.get("credentials", {}).get("exports", []):
            if exp.get("id") == item_id:
                self._pane.set_entry(exp)
                return

    def state_count(self) -> int:
        return self._pane.diagram.state_count
