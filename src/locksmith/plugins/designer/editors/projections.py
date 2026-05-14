# -*- encoding: utf-8 -*-
"""ProjectionsEditorPage: 'I see …' surface.

Right-pane sections (canonical schema):
  Identity · Source events · Fold expression (read-only) · Display ·
  Live preview (with 'evaluator pending' fallback) · Entry JSON · Used-by.

Canonical schema fields:
  Required: id, name, description, source_events[], output_schema,
            fold_expression.
  Optional: access.{row_filter_rule_ref, lens_template},
            display.{view_type, columns[], default_sort, empty_state}.

Live preview resolves locksmith.uel.evaluator.evaluate at call time. If
that module is not importable (open spec question §9.2 — no evaluator
exists yet), the preview label shows the raw expression text with an
'evaluator pending' note.
"""
from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QScrollArea,
    QVBoxLayout, QWidget,
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


def _resolve_uel_evaluator():
    try:
        from locksmith.uel.evaluator import evaluate  # type: ignore
        return evaluate
    except Exception:
        return None


class _ProjectionSectionPane(QWidget):
    def __init__(self, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._crossrefs = crossrefs
        self._build()

    def _build(self) -> None:
        from locksmith.plugins.designer.widgets.view_type_chip_picker import (
            ViewTypeChipPicker,
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        # Header block.
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
        outer.addWidget(self._header_frame)

        # Two-column body.
        body = QHBoxLayout()
        body.setSpacing(14)

        # LEFT column.
        left = QVBoxLayout()
        left.setSpacing(14)

        self._sources_section = make_section("Source events · fold from")
        self._sources_holder = QVBoxLayout()
        self._sources_section.layout().addLayout(self._sources_holder)
        left.addWidget(self._sources_section)

        self._fold_section = make_section("Fold expression")
        self._fold_holder = QVBoxLayout()
        self._fold_section.layout().addLayout(self._fold_holder)
        cheat = QLabel("↗ UEL/1.0 cheat-sheet · test expression")
        cheat.setStyleSheet("color:#0ABFB0;font-size:10px;")
        self._fold_section.layout().addWidget(cheat)
        left.addWidget(self._fold_section)

        self._output_section = make_section("Output schema · row shape")
        self._output_holder = QVBoxLayout()
        self._output_section.layout().addLayout(self._output_holder)
        left.addWidget(self._output_section)

        self._access_section = make_section("Access · who can see")
        self._access_label = QLabel(
            "Row filter: None — all rows visible to anyone in role"
        )
        self._access_label.setStyleSheet("color:#444;font-size:11px;")
        self._access_label.setWordWrap(True)
        self._access_section.layout().addWidget(self._access_label)
        self._access_picker_holder = QVBoxLayout()
        self._access_section.layout().addLayout(self._access_picker_holder)
        left.addWidget(self._access_section)

        self._view_type_section = make_section("View type")
        self._view_picker = ViewTypeChipPicker(active="table")
        self._view_type_section.layout().addWidget(self._view_picker)
        left.addWidget(self._view_type_section)

        left.addStretch(1)

        left_w = QWidget()
        left_w.setLayout(left)
        body.addWidget(left_w, 3)

        # RIGHT column — live preview.
        self._preview_section = make_section("Live preview · how Locksmith renders this")
        self._preview_holder = QVBoxLayout()
        self._preview_section.layout().addLayout(self._preview_holder)
        body.addWidget(self._preview_section, 2)

        outer.addLayout(body, 1)

        # Used by.
        self._used_by = make_section("Used by")
        self.chip_strip = CrossRefChipStrip()
        self._used_by.layout().addWidget(self.chip_strip)
        outer.addWidget(self._used_by)

    def set_entry(self, entry: dict[str, Any]) -> None:
        from locksmith.plugins.designer.widgets.dark_code_block import (
            DarkCodeBlock,
        )
        from locksmith.plugins.designer.widgets.source_event_chip_strip import (
            SourceEventChipStrip,
        )
        from locksmith.plugins.designer.widgets.payload_schema_table import (
            PayloadSchemaTable,
        )
        from locksmith.plugins.designer.widgets.rule_chip_strip import (
            RuleChipStrip,
        )

        self._name_label.setText(entry.get("name") or entry.get("id") or "(unnamed)")
        self._id_chip.setText(entry.get("id", ""))
        self._description_label.setText(entry.get("description", ""))

        def _clear(layout) -> None:
            while layout.count():
                item = layout.takeAt(0)
                w = item.widget() if item is not None else None
                if w is not None:
                    w.setParent(None)
                    w.deleteLater()

        _clear(self._sources_holder)
        self._sources_holder.addWidget(
            SourceEventChipStrip(entry.get("source_events") or [])
        )

        _clear(self._fold_holder)
        self._fold_holder.addWidget(
            DarkCodeBlock(entry.get("fold_expression", ""))
        )

        _clear(self._output_holder)
        out = entry.get("output_schema") or {}
        if out.get("type") == "array" and isinstance(out.get("items"), dict):
            row_schema = out["items"]
        else:
            row_schema = out
        self._output_holder.addWidget(PayloadSchemaTable(row_schema))

        _clear(self._access_picker_holder)
        access = entry.get("access") or {}
        rf = access.get("row_filter_rule_ref")
        refs = [rf] if rf else []
        self._access_picker_holder.addWidget(RuleChipStrip(refs))

        view = (entry.get("display") or {}).get("view_type", "table")
        # set_active is a no-op if same; toggle via setting first and
        # then back if we need to force the restyle.
        self._view_picker._active = view
        self._view_picker._restyle()

        # Preview pane.
        _clear(self._preview_holder)
        note = QLabel("evaluator pending — showing raw expression:")
        note.setStyleSheet("color:#aaa;font-style:italic;font-size:11px;")
        self._preview_holder.addWidget(note)
        self._preview_holder.addWidget(
            DarkCodeBlock(entry.get("fold_expression", ""))
        )

        self.chip_strip.set_refs(
            self._crossrefs.consumers_of(f"projection:{entry.get('id', '')}")
        )

    def preview_text(self) -> str:
        from locksmith.plugins.designer.widgets.dark_code_block import (
            DarkCodeBlock,
        )
        parts: list[str] = []
        for lbl in self._preview_section.findChildren(QLabel):
            parts.append(lbl.text())
        for block in self._preview_section.findChildren(DarkCodeBlock):
            parts.append(block.toPlainText())
        return " ".join(parts)

    def preview_visible(self) -> bool:
        return self._preview_section.isVisible()


def _projection_subtitle(p: dict) -> str:
    parts: list[str] = []
    view = (p.get("display") or {}).get("view_type")
    if view:
        parts.append(view)
    n = len(p.get("source_events") or [])
    if n:
        parts.append(f"folds {n} event{'s' if n != 1 else ''}")
    return " · ".join(parts) if parts else ""


class ProjectionsEditorPage(QWidget):
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
                id=p.get("id", ""),
                label=p.get("name") or p.get("id") or "(unnamed)",
                subtitle=_projection_subtitle(p),
                kind_color=color,
                has_errors=False,
            )
            for p in model.doc.get("projections", [])
        ]
        self.shell = PrimitiveEditorShell(
            surface_label="Projections",
            template_label=model.doc.get("header", {}).get("display_name", "(untitled)"),
            items=items,
            add_label="+ Add projection",
            item_count=len(items),
            role_label=model.doc.get("role", {}).get("id", ""),
            is_valid=True,
            parent=self,
        )
        self._pane = _ProjectionSectionPane(crossrefs=crossrefs)
        if items:
            self._pane.set_entry(model.doc["projections"][0])
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
        for p in self._model.doc.get("projections", []):
            if p.get("id") == item_id:
                self._pane.set_entry(p)
                return

    def preview_visible(self) -> bool:
        return self._pane.preview_visible()

    def preview_text(self) -> str:
        return self._pane.preview_text()
