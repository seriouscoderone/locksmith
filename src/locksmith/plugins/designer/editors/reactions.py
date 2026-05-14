# -*- encoding: utf-8 -*-
"""ReactionsEditorPage: 'I respond to …' surface.

V1 right-pane layout: header + Trigger card with variant chips +
Emissions section with colored kind chips + Failure policy section +
Used by.
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


def _reaction_subtitle(r: dict) -> str:
    parts: list[str] = []
    trig = r.get("trigger") or {}
    t_type = trig.get("type", "")
    if t_type:
        short = t_type.replace("_received", "").replace("_event", "_event")
        parts.append(f"← {short}")
    n = len(r.get("emissions") or [])
    if n:
        parts.append(f"{n} emission{'s' if n != 1 else ''}")
    return " · ".join(parts) if parts else ""


_EMISSION_KIND_COLOR: dict[str, str] = {
    "aggregate_event":   "#A36AE6",
    "lifecycle_advance": "#0ABFB0",
    "exchange":          "#D97757",
}


class _ReactionSectionPane(QWidget):
    def __init__(self, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._crossrefs = crossrefs
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

        # Trigger card.
        self._trigger_section = make_section("Trigger")
        self._trigger_variants_row = QHBoxLayout()
        self._trigger_variants_row.setSpacing(6)
        for v in ("credential_received", "exn_received",
                  "lifecycle_event", "scheduled"):
            chip = QLabel(v)
            chip.setProperty("variant", v)
            chip.setStyleSheet(
                "background:#f0f2f5;color:#444;border-radius:9px;"
                "padding:2px 9px;font-size:11px;"
            )
            self._trigger_variants_row.addWidget(chip)
        self._trigger_variants_row.addStretch(1)
        self._trigger_section.layout().addLayout(self._trigger_variants_row)
        self._trigger_route_row = QHBoxLayout()
        self._trigger_section.layout().addLayout(self._trigger_route_row)
        lay.addWidget(self._trigger_section)

        # Emissions.
        self._emissions_section = make_section("Emissions")
        self._emissions_holder = QVBoxLayout()
        self._emissions_section.layout().addLayout(self._emissions_holder)
        lay.addWidget(self._emissions_section)

        # Failure policy.
        self._failure_section = make_section("Failure policy")
        self._failure_holder = QHBoxLayout()
        self._failure_section.layout().addLayout(self._failure_holder)
        lay.addWidget(self._failure_section)

        # Used by.
        self._used_by = make_section("Used by")
        self.chip_strip = CrossRefChipStrip()
        self._used_by.layout().addWidget(self.chip_strip)
        lay.addWidget(self._used_by)
        lay.addStretch(1)

    def set_entry(self, entry: dict[str, Any]) -> None:
        self._name_label.setText(
            entry.get("name") or entry.get("id") or "(unnamed)"
        )
        self._id_chip.setText(entry.get("id", ""))
        self._description_label.setText(entry.get("description") or "")

        trig = entry.get("trigger") or {}
        active = trig.get("type", "")
        for i in range(self._trigger_variants_row.count()):
            item = self._trigger_variants_row.itemAt(i)
            chip = item.widget() if item is not None else None
            if not isinstance(chip, QLabel):
                continue
            v = chip.property("variant")
            if v == active:
                chip.setStyleSheet(
                    "background:#e8f4f4;color:#0a8a82;border-radius:9px;"
                    "padding:2px 9px;font-size:11px;font-weight:600;"
                )
            else:
                chip.setStyleSheet(
                    "background:#f0f2f5;color:#444;border-radius:9px;"
                    "padding:2px 9px;font-size:11px;"
                )

        while self._trigger_route_row.count():
            item = self._trigger_route_row.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        if trig.get("route"):
            r_lbl = QLabel(f"Route: {trig['route']}")
            r_lbl.setStyleSheet(
                "color:#0ABFB0;font-family:monospace;font-size:11px;"
            )
            self._trigger_route_row.addWidget(r_lbl)
        if trig.get("schema_id"):
            s_lbl = QLabel(f"Schema ID: {trig['schema_id']}")
            s_lbl.setStyleSheet(
                "color:#666;font-family:monospace;font-size:11px;"
            )
            self._trigger_route_row.addWidget(s_lbl)
        self._trigger_route_row.addStretch(1)

        while self._emissions_holder.count():
            item = self._emissions_holder.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        for em in entry.get("emissions") or []:
            row_w = QFrame()
            row = QHBoxLayout(row_w)
            row.setContentsMargins(0, 2, 0, 2)
            row.setSpacing(6)
            kind = em.get("kind", "")
            kind_chip = QLabel(kind)
            color = _EMISSION_KIND_COLOR.get(kind, "#888")
            kind_chip.setStyleSheet(
                f"color:{color};background:#f6f7f9;border-radius:9px;"
                "padding:2px 9px;font-size:11px;font-weight:600;"
            )
            row.addWidget(kind_chip)
            if kind == "aggregate_event":
                row.addWidget(QLabel(
                    f"append to {em.get('aggregate_id','?')} as "
                    f"{em.get('event_type','?')}"
                ))
            elif kind == "lifecycle_advance":
                row.addWidget(QLabel(
                    f"advance {em.get('exported_credential_id','?')} → "
                    f"{em.get('to_state','?')}"
                ))
            elif kind == "exchange":
                ex = em.get("exchange") or {}
                row.addWidget(QLabel(
                    f"exchange: {ex.get('kind','?')} · "
                    f"{ex.get('verb', ex.get('pattern',''))}"
                ))
            row.addStretch(1)
            self._emissions_holder.addWidget(row_w)

        while self._failure_holder.count():
            item = self._failure_holder.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        fp = entry.get("failure_policy") or {}
        on_fail = fp.get("on_validation_failure", "log_and_continue")
        policy_chip = QLabel(on_fail)
        policy_chip.setStyleSheet(
            "background:#e8f4f4;color:#0a8a82;border-radius:9px;"
            "padding:2px 9px;font-size:11px;font-weight:600;"
        )
        self._failure_holder.addWidget(policy_chip)
        timeout = fp.get("timeout_seconds")
        timeout_lbl = QLabel(f"timeout: {timeout if timeout else 'none'}")
        timeout_lbl.setStyleSheet("color:#666;font-size:11px;")
        self._failure_holder.addWidget(timeout_lbl)
        self._failure_holder.addStretch(1)

        self.chip_strip.set_refs(
            self._crossrefs.consumers_of(f"reaction:{entry.get('id', '')}")
        )

    def text_summary(self) -> str:
        parts = [
            self._name_label.text(),
            self._id_chip.text(),
            self._description_label.text(),
        ]
        for lbl in self.findChildren(QLabel):
            parts.append(lbl.text())
        return " ".join(parts)


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
                subtitle=_reaction_subtitle(r),
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
        for r in self._model.doc.get("reactions", []):
            if r.get("id") == item_id:
                self._pane.set_entry(r)
                return

    def section_text(self) -> str:
        return self._pane.text_summary()
