# -*- encoding: utf-8 -*-
"""AggregatesEditorPage: 'I track …' surface.

V1 right-pane layout: header + inception-event chip + log-scope chip +
state-schema preview + initial-state preview + invariants RuleChipStrip
+ Used by.
"""
from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QVBoxLayout, QWidget,
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


def _aggregate_subtitle(agg: dict) -> str:
    parts: list[str] = []
    scope = agg.get("log_scope")
    if scope:
        parts.append(f"{scope} log")
    invs = agg.get("invariants") or []
    parts.append(f"{len(invs)} invariant{'s' if len(invs) != 1 else ''}")
    return " · ".join(parts)


class _AggregateSectionPane(QWidget):
    def __init__(self, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._crossrefs = crossrefs
        self.setObjectName("designer-section-pane")
        self.setStyleSheet(
            "#designer-section-pane QLabel{background:transparent;}"
        )
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

        # Inception event + log scope side-by-side.
        ic_row = QHBoxLayout()
        ic_row.setSpacing(14)
        self._inception_section = make_section("Inception event")
        self._inception_chip = QLabel("(unset)")
        self._inception_chip.setStyleSheet(
            "background:#f3edfb;color:#A36AE6;border-radius:9px;"
            "padding:2px 9px;font-size:11px;font-weight:600;"
            "font-family:monospace;"
        )
        self._inception_section.layout().addWidget(self._inception_chip)
        ic_row.addWidget(self._inception_section, 1)
        self._scope_section = make_section("Log scope")
        self._scope_chip = QLabel("(unset)")
        self._scope_chip.setStyleSheet(
            "background:#e8f4f4;color:#0a8a82;border-radius:9px;"
            "padding:2px 9px;font-size:11px;font-weight:600;"
        )
        self._scope_section.layout().addWidget(self._scope_chip)
        ic_row.addWidget(self._scope_section, 1)
        lay.addLayout(ic_row)

        # State schema preview.
        self._state_schema_section = make_section("State schema")
        self._state_schema_view = QPlainTextEdit()
        self._state_schema_view.setReadOnly(True)
        self._state_schema_view.setFrameShape(QFrame.NoFrame)
        mono = QFont("Menlo")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(10)
        self._state_schema_view.setFont(mono)
        self._state_schema_view.setFixedHeight(80)
        self._state_schema_section.layout().addWidget(self._state_schema_view)
        lay.addWidget(self._state_schema_section)

        # Initial state preview.
        self._initial_section = make_section("Initial state")
        self._initial_view = QPlainTextEdit()
        self._initial_view.setReadOnly(True)
        self._initial_view.setFrameShape(QFrame.NoFrame)
        self._initial_view.setFont(mono)
        self._initial_view.setFixedHeight(50)
        self._initial_section.layout().addWidget(self._initial_view)
        lay.addWidget(self._initial_section)

        # Invariants.
        self._inv_section = make_section("Invariants")
        self._inv_holder = QVBoxLayout()
        self._inv_section.layout().addLayout(self._inv_holder)
        lay.addWidget(self._inv_section)

        # Used by.
        self._used_by = make_section("Used by")
        self.chip_strip = CrossRefChipStrip()
        self._used_by.layout().addWidget(self.chip_strip)
        lay.addWidget(self._used_by)
        lay.addStretch(1)

    def set_entry(self, entry: dict[str, Any]) -> None:
        from locksmith.plugins.designer.widgets.rule_chip_strip import (
            RuleChipStrip,
        )

        self._name_label.setText(entry.get("name") or entry.get("id") or "(unnamed)")
        self._id_chip.setText(entry.get("id", ""))
        self._description_label.setText(entry.get("description") or "")
        self._inception_chip.setText(
            entry.get("inception_event_type") or "(unset)"
        )
        scope = entry.get("log_scope")
        self._scope_chip.setText(scope or "(unset)")

        self._state_schema_view.setPlainText(
            json.dumps(entry.get("state_schema") or {}, indent=2, sort_keys=True)
        )
        self._initial_view.setPlainText(
            json.dumps(entry.get("initial_state"), indent=2, sort_keys=True)
        )

        while self._inv_holder.count():
            item = self._inv_holder.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        refs = [r.get("rule_ref", "") for r in (entry.get("invariants") or [])
                if r.get("rule_ref")]
        self._inv_holder.addWidget(RuleChipStrip(refs))

        self.chip_strip.set_refs(
            self._crossrefs.consumers_of(f"aggregate:{entry.get('id', '')}")
        )

    def text_summary(self) -> str:
        from locksmith.plugins.designer.widgets.rule_chip_strip import (
            RuleChipStrip,
        )
        parts = [
            self._name_label.text(),
            self._id_chip.text(),
            self._description_label.text(),
            self._inception_chip.text(),
            self._scope_chip.text(),
            self._state_schema_view.toPlainText(),
            self._initial_view.toPlainText(),
        ]
        for strip in self.findChildren(RuleChipStrip):
            parts.extend(strip.chip_texts())
        return " ".join(parts)


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
                subtitle=_aggregate_subtitle(a),
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
            add_label="+ Add aggregate",
            item_count=len(items),
            role_label=model.doc.get("role", {}).get("id", ""),
            is_valid=True,
            parent=self,
        )
        self._pane = _AggregateSectionPane(crossrefs=crossrefs)
        if items:
            self._pane.set_entry(model.doc["aggregates"][0])
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
        for a in self._model.doc.get("aggregates", []):
            if a.get("id") == item_id:
                self._pane.set_entry(a)
                return

    def section_text(self) -> str:
        return self._pane.text_summary()
