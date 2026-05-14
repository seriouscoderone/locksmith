# -*- encoding: utf-8 -*-
"""CommandsEditorPage: 'I do …' surface.

Right-pane sections (canonical schema):
  Identity · Route + counterparty_role · Preconditions counts ·
  Emissions list · Entry JSON · Used-by.
"""
from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget,
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


def _emission_summary(em: dict[str, Any]) -> str:
    kind = em.get("kind", "?")
    if kind == "exchange":
        ex = em.get("exchange", {})
        ek = ex.get("kind", "?")
        if ek == "credential":
            verb = ex.get("verb", "?")
            imp = ex.get("imported_credential_id")
            exp = ex.get("exported_credential_id")
            target = f"imp:{imp}" if imp else (f"exp:{exp}" if exp else "")
            return f"exchange/credential {verb} {target}".strip()
        if ek == "message":
            return f"exchange/message {ex.get('pattern', '?')} {ex.get('route', '?')}"
        return f"exchange/{ek}"
    if kind == "lifecycle_advance":
        return (f"lifecycle_advance: "
                f"{em.get('exported_credential_id', '?')} → "
                f"{em.get('to_state', '?')}")
    if kind == "aggregate_event":
        return (f"aggregate_event: {em.get('aggregate_id', '?')} ← "
                f"{em.get('event_type', '?')}")
    return f"{kind} (unknown)"


class _CommandSectionPane(QWidget):
    def __init__(self, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._crossrefs = crossrefs
        self._build()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        # Header (id + name + route + description).
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
        self._route_label = QLabel("")
        self._route_label.setStyleSheet(
            "color:#0ABFB0;font-family:monospace;font-size:11px;"
        )
        title_row.addWidget(self._route_label)
        h.addLayout(title_row)
        self._description_label = QLabel("")
        self._description_label.setStyleSheet("color:#444;font-size:12px;")
        self._description_label.setWordWrap(True)
        h.addWidget(self._description_label)
        lay.addWidget(self._header_frame)

        # TARGETS
        targets = make_section("Targets")
        self._cp_row = QHBoxLayout()
        cp_lbl = QLabel("Counterparty role:")
        cp_lbl.setStyleSheet("color:#444;font-size:12px;")
        self._cp_row.addWidget(cp_lbl)
        self._cp_chip = QLabel("(none)")
        self._cp_chip.setStyleSheet(
            "background:#e8f4f4;color:#0a8a82;border-radius:9px;"
            "padding:2px 9px;font-size:11px;font-weight:600;"
        )
        self._cp_row.addWidget(self._cp_chip)
        self._cp_row.addStretch(1)
        targets.layout().addLayout(self._cp_row)
        lay.addWidget(targets)

        # PAYLOAD
        self._payload_section = make_section("What the actor supplies (payload)")
        self._payload_holder = QFrame()
        ph = QVBoxLayout(self._payload_holder)
        ph.setContentsMargins(0, 0, 0, 0)
        ph.setSpacing(0)
        self._payload_section.layout().addWidget(self._payload_holder)
        lay.addWidget(self._payload_section)

        # PRECONDITIONS — three sub-rows.
        self._precond_section = make_section("Preconditions")
        self._auth_strip_holder = QVBoxLayout()
        self._state_strip_holder = QVBoxLayout()
        self._temporal_strip_holder = QVBoxLayout()
        for label, holder in (
            ("Auth — actor must hold credentials matching:", self._auth_strip_holder),
            ("State — facts that must exist in aggregates:", self._state_strip_holder),
            ("Temporal — time bounds:", self._temporal_strip_holder),
        ):
            lbl = QLabel(label)
            lbl.setStyleSheet("color:#666;font-size:11px;")
            self._precond_section.layout().addWidget(lbl)
            self._precond_section.layout().addLayout(holder)
        lay.addWidget(self._precond_section)

        # EMISSIONS
        self._emissions_section = make_section("Emissions")
        self._emissions_holder = QVBoxLayout()
        self._emissions_section.layout().addLayout(self._emissions_holder)
        lay.addWidget(self._emissions_section)

        # USED BY
        self._used_by = make_section("Used by")
        self.chip_strip = CrossRefChipStrip()
        self._used_by.layout().addWidget(self.chip_strip)
        lay.addWidget(self._used_by)
        lay.addStretch(1)

    def set_entry(self, entry: dict[str, Any]) -> None:
        from locksmith.plugins.designer.widgets.payload_schema_table import (
            PayloadSchemaTable,
        )
        from locksmith.plugins.designer.widgets.rule_chip_strip import (
            RuleChipStrip,
        )

        self._name_label.setText(entry.get("name") or entry.get("id") or "(unnamed)")
        self._id_chip.setText(entry.get("id", ""))
        self._route_label.setText(entry.get("route", ""))
        self._description_label.setText(entry.get("description", ""))
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

        ph_layout = self._payload_holder.layout()
        while ph_layout.count():
            old = ph_layout.takeAt(0).widget()
            if old is not None:
                old.setParent(None)
                old.deleteLater()
        ph_layout.addWidget(PayloadSchemaTable(entry.get("payload_schema") or {}))

        for holder, refs_key in (
            (self._auth_strip_holder, "auth_preconditions"),
            (self._state_strip_holder, "state_preconditions"),
            (self._temporal_strip_holder, "temporal_preconditions"),
        ):
            while holder.count():
                old = holder.takeAt(0).widget()
                if old is not None:
                    old.setParent(None)
                    old.deleteLater()
            refs = [r.get("rule_ref", "") for r in (entry.get(refs_key) or [])
                    if r.get("rule_ref")]
            holder.addWidget(RuleChipStrip(refs))

        while self._emissions_holder.count():
            old = self._emissions_holder.takeAt(0).widget()
            if old is not None:
                old.setParent(None)
                old.deleteLater()
        emissions = entry.get("emissions") or []
        if not emissions:
            none_lbl = QLabel("(none)")
            none_lbl.setStyleSheet("color:#aaa;font-style:italic;font-size:11px;")
            self._emissions_holder.addWidget(none_lbl)
        else:
            for em in emissions:
                summary = _emission_summary(em)
                lbl = QLabel(f"• {summary}")
                lbl.setStyleSheet("color:#444;font-size:11px;")
                self._emissions_holder.addWidget(lbl)

        key = f"command:{entry.get('id', '')}"
        self.chip_strip.set_refs(self._crossrefs.consumers_of(key))

    def text_summary(self) -> str:
        from locksmith.plugins.designer.widgets.payload_schema_table import (
            PayloadSchemaTable,
        )
        from locksmith.plugins.designer.widgets.rule_chip_strip import (
            RuleChipStrip,
        )

        parts = [
            self._name_label.text(),
            self._id_chip.text(),
            self._route_label.text(),
            self._description_label.text(),
            "Auth State Temporal",
            self._cp_chip.text(),
        ]
        for table in self.findChildren(PayloadSchemaTable):
            for row in table.field_rows():
                parts.append(row.get("field", ""))
                parts.append(row.get("constraint", ""))
        for strip in self.findChildren(RuleChipStrip):
            parts.extend(strip.chip_texts())
        return " ".join(parts)


def _command_subtitle(c: dict) -> str:
    parts: list[str] = []
    cp = c.get("counterparty_role")
    if cp:
        parts.append(f"→ {cp}")
    emissions = c.get("emissions") or []
    n = len(emissions)
    if n:
        parts.append(f"{n} emission{'s' if n != 1 else ''}")
    return " · ".join(parts) if parts else ""


class CommandsEditorPage(QWidget):
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
        items = self._rail_items()
        template_label = model.doc.get("header", {}).get("display_name", "(untitled)")
        self.shell = PrimitiveEditorShell(
            surface_label="Commands",
            template_label=template_label,
            items=items,
            add_label="+ Add command",
            item_count=len(items),
            role_label=model.doc.get("role", {}).get("id", ""),
            is_valid=True,
            parent=self,
        )
        self._pane = _CommandSectionPane(crossrefs=crossrefs)
        if items:
            self._pane.set_entry(model.doc.get("commands", [{}])[0])
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

    def _rail_items(self) -> list[RailItem]:
        color = kind_color_for(self._model.doc.get("role", {}).get("kind", ""))
        items = []
        for c in self._model.doc.get("commands", []):
            items.append(RailItem(
                id=c.get("id", ""),
                label=c.get("name") or c.get("id") or "(unnamed)",
                subtitle=_command_subtitle(c),
                kind_color=color,
                has_errors=False,
            ))
        return items

    def _on_select(self, item_id: str) -> None:
        for c in self._model.doc.get("commands", []):
            if c.get("id") == item_id:
                self._pane.set_entry(c)
                return

    def section_text(self) -> str:
        return self._pane.text_summary()
