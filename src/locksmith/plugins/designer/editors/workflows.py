# -*- encoding: utf-8 -*-
"""WorkflowsEditorPage: 'I follow …' surface.

V1 right-pane layout:
  Header (id chip + description) · Trigger card · Counterparty card ·
  Flow (full-width swimlane v2) · Step details · Used by.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
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


def _workflow_subtitle(wf: dict) -> str:
    parts: list[str] = []
    cp = wf.get("counterparty_role")
    if cp:
        parts.append(f"↔ {cp}")
    n = len(wf.get("steps") or [])
    if n:
        parts.append(f"{n} step{'s' if n != 1 else ''}")
    return " · ".join(parts) if parts else ""


def _step_subtitle(s: dict) -> str:
    if s.get("command_id"):
        return f"command · {s['command_id']}"
    if s.get("reaction_id"):
        return f"reaction · {s['reaction_id']}"
    adv = s.get("advance_lifecycle") or {}
    if adv.get("credential_id"):
        return f"advance {adv['credential_id']}"
    if s.get("expected_inbound"):
        inb = s["expected_inbound"][0]
        return f"{inb.get('trigger_type','?')} · {inb.get('route', '')}"
    return "internal · no exchange"


class _WorkflowSectionPane(QWidget):
    def __init__(self, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._crossrefs = crossrefs
        self._role_id = "self"
        self._build()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

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
        h.addLayout(title_row)
        self._description_label = QLabel("")
        self._description_label.setStyleSheet("color:#444;font-size:12px;")
        self._description_label.setWordWrap(True)
        h.addWidget(self._description_label)
        lay.addWidget(self._header_frame)

        # Trigger + Counterparty side by side.
        tc_row = QHBoxLayout()
        tc_row.setSpacing(14)
        self._trigger_section = make_section("Trigger")
        self._trigger_holder = QVBoxLayout()
        self._trigger_section.layout().addLayout(self._trigger_holder)
        tc_row.addWidget(self._trigger_section, 1)
        self._counterparty_section = make_section("Counterparty")
        self._cp_chip = QLabel("(none)")
        self._cp_chip.setStyleSheet(
            "background:#e8f4f4;color:#0a8a82;border-radius:9px;"
            "padding:2px 9px;font-size:11px;font-weight:600;"
        )
        self._counterparty_section.layout().addWidget(self._cp_chip)
        tc_row.addWidget(self._counterparty_section, 1)
        lay.addLayout(tc_row)

        # Flow swimlane.
        self._flow_section = make_section("Flow")
        self.swimlane = SwimlaneDiagram()
        self.swimlane.setMinimumHeight(280)
        self._flow_section.layout().addWidget(self.swimlane)
        lay.addWidget(self._flow_section)

        # Step details.
        self._steps_section = make_section("Step details")
        self._steps_holder = QVBoxLayout()
        self._steps_section.layout().addLayout(self._steps_holder)
        lay.addWidget(self._steps_section)

        # Used by.
        self._used_by = make_section("Used by")
        self.chip_strip = CrossRefChipStrip()
        self._used_by.layout().addWidget(self.chip_strip)
        lay.addWidget(self._used_by)
        lay.addStretch(1)

    def set_role_id(self, role_id: str) -> None:
        self._role_id = role_id

    def set_entry(self, entry: dict[str, Any]) -> None:
        self._name_label.setText(entry.get("name") or entry.get("id") or "(unnamed)")
        self._id_chip.setText(entry.get("id", ""))
        self._description_label.setText(entry.get("description", ""))

        # Trigger card content.
        while self._trigger_holder.count():
            old = self._trigger_holder.takeAt(0).widget()
            if old is not None:
                old.setParent(None)
                old.deleteLater()
            else:
                item = self._trigger_holder.takeAt(0)
        trig = entry.get("trigger") or {}
        t_type = trig.get("type", "")
        row_w = QFrame()
        chip_row = QHBoxLayout(row_w)
        chip_row.setContentsMargins(0, 0, 0, 0)
        chip_row.setSpacing(6)
        type_chip = QLabel(t_type or "(none)")
        type_chip.setStyleSheet(
            "background:#e8f4f4;color:#0a8a82;border-radius:9px;"
            "padding:2px 9px;font-size:11px;font-weight:600;"
        )
        chip_row.addWidget(type_chip)
        if trig.get("route"):
            r_lbl = QLabel(trig["route"])
            r_lbl.setStyleSheet(
                "color:#0ABFB0;font-family:monospace;font-size:11px;"
            )
            chip_row.addWidget(r_lbl)
        chip_row.addStretch(1)
        self._trigger_holder.addWidget(row_w)

        # Counterparty chip.
        cp = entry.get("counterparty_role")
        if cp:
            self._cp_chip.setText(cp)
            self._cp_chip.setStyleSheet(
                "background:#e8f4f4;color:#0a8a82;border-radius:9px;"
                "padding:2px 9px;font-size:11px;font-weight:600;"
            )
        else:
            self._cp_chip.setText("(none)")
            self._cp_chip.setStyleSheet(
                "color:#aaa;font-style:italic;font-size:11px;background:transparent;"
            )

        # Swimlane v2.
        steps_raw = entry.get("steps") or []
        actors = sorted({s.get("actor", "self") for s in steps_raw},
                        key=lambda a: 0 if a == "self" else 1)
        if not actors:
            actors = ["self"]
        cp_role = entry.get("counterparty_role", "counterparty")
        lane_labels = [
            f"I ({self._role_id})" if a == "self"
            else f"counterparty ({cp_role})"
            for a in actors
        ]
        actor_to_label = {a: lane_labels[i] for i, a in enumerate(actors)}
        swim_steps: list[SwimlaneStep] = []
        for s in steps_raw:
            actor = s.get("actor", "self")
            is_internal = (
                not s.get("command_id")
                and not s.get("reaction_id")
                and not s.get("advance_lifecycle")
                and not s.get("expected_inbound")
                and not s.get("branches")
            )
            tb = s.get("time_bound") or {}
            tb_text = None
            if isinstance(tb, dict) and tb.get("duration"):
                exp = tb.get("on_expiry") or ""
                tb_text = (f"{tb['duration']} bound"
                           f"{' · on expiry → ' + exp if exp else ''}")
            swim_steps.append(SwimlaneStep(
                step_id=s.get("id", ""),
                label=s.get("name") or s.get("id") or "(unnamed)",
                actor=actor_to_label.get(actor, lane_labels[0]),
                subtitle=_step_subtitle(s),
                branches=s.get("branches"),
                time_bound=tb_text,
                is_internal=is_internal,
            ))
        self.swimlane.render(lanes=lane_labels, steps=swim_steps)

        # Step details rich list.
        while self._steps_holder.count():
            old_item = self._steps_holder.takeAt(0)
            w = old_item.widget() if old_item is not None else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        for s in steps_raw:
            row_w = QFrame()
            row = QHBoxLayout(row_w)
            row.setContentsMargins(0, 2, 0, 2)
            row.setSpacing(8)
            name_lbl = QLabel(s.get("name") or s.get("id", "?"))
            name_lbl.setStyleSheet(
                "font-weight:600;color:#1A1C20;font-size:12px;"
            )
            row.addWidget(name_lbl)
            actor_lbl = QLabel(f"actor: {s.get('actor', '?')}")
            actor_lbl.setStyleSheet("color:#666;font-size:11px;")
            row.addWidget(actor_lbl)
            if s.get("command_id"):
                cmd_lbl = QLabel(f"→ command {s['command_id']}")
                cmd_lbl.setStyleSheet("color:#0ABFB0;font-size:11px;")
                row.addWidget(cmd_lbl)
            if s.get("reaction_id"):
                rx_lbl = QLabel(f"→ reaction {s['reaction_id']}")
                rx_lbl.setStyleSheet("color:#0ABFB0;font-size:11px;")
                row.addWidget(rx_lbl)
            adv = s.get("advance_lifecycle") or {}
            if adv.get("credential_id"):
                a_lbl = QLabel(
                    f"→ advance {adv['credential_id']} to {adv.get('to_state','?')}"
                )
                a_lbl.setStyleSheet("color:#0ABFB0;font-size:11px;")
                row.addWidget(a_lbl)
            row.addStretch(1)
            self._steps_holder.addWidget(row_w)

        self.chip_strip.set_refs(
            self._crossrefs.consumers_of(f"workflow:{entry.get('id', '')}")
        )

    def text_summary(self) -> str:
        parts = [
            self._name_label.text(),
            self._id_chip.text(),
            self._description_label.text(),
            self._cp_chip.text(),
        ]
        for lbl in self._trigger_section.findChildren(QLabel):
            parts.append(lbl.text())
        for lbl in self._steps_section.findChildren(QLabel):
            parts.append(lbl.text())
        return " ".join(parts)


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
                subtitle=_workflow_subtitle(w),
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
        self._pane.set_role_id(model.doc.get("role", {}).get("id", "self"))
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

    def section_text(self) -> str:
        return self._pane.text_summary()

    def swimlane_step_count(self) -> int:
        return self._pane.swimlane.step_count
