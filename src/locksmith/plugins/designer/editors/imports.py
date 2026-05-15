# -*- encoding: utf-8 -*-
"""ImportsEditorPage: 'I hold …' surface.

V1 right-pane layout: header with id chip + italic narrative · expected
schema SAID (full) · issuer role chip · lifecycle acceptance chips + +
accept state · attribute constraints (optional) · rich USED BY back-
pointer list.
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


def _import_subtitle(imp: dict, crossrefs) -> str:
    parts: list[str] = []
    issuer = imp.get("expected_issuer_role")
    if issuer:
        parts.append(f"← {issuer}")
    rid = imp.get("id", "")
    consumers = crossrefs.consumers_of(f"import:{rid}") if rid else []
    if consumers:
        parts.append(f"→ used {len(consumers)}x")
    return " · ".join(parts)


class _ImportSectionPane(QWidget):
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
        self._id_chip = QLabel("")
        self._id_chip.setStyleSheet(
            "color:#666;background:#f6f7f9;font-family:monospace;"
            "border-radius:6px;padding:2px 8px;font-size:12px;"
        )
        title_row.addWidget(self._id_chip)
        title_row.addStretch(1)
        h.addLayout(title_row)
        self._narrative_label = QLabel("")
        self._narrative_label.setStyleSheet(
            "color:#666;font-style:italic;font-size:11px;"
        )
        self._narrative_label.setWordWrap(True)
        h.addWidget(self._narrative_label)
        lay.addWidget(self._header_frame)

        # Expected schema SAID (full).
        self._said_section = make_section("Expected schema SAID")
        self._said_label = QLabel("(unset)")
        mono = QFont("Menlo")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(10)
        self._said_label.setFont(mono)
        self._said_label.setStyleSheet(
            "color:#444;background:#f6f7f9;border-radius:4px;"
            "padding:6px 8px;"
        )
        self._said_section.layout().addWidget(self._said_label)
        lay.addWidget(self._said_section)

        # Issuer + lifecycle side-by-side.
        ir_row = QHBoxLayout()
        ir_row.setSpacing(14)
        self._issuer_section = make_section("Expected issuer role")
        self._issuer_chip = QLabel("(any)")
        self._issuer_chip.setStyleSheet(
            "background:#e8f4f4;color:#0a8a82;border-radius:9px;"
            "padding:2px 9px;font-size:11px;font-weight:600;"
        )
        self._issuer_section.layout().addWidget(self._issuer_chip)
        ir_row.addWidget(self._issuer_section, 1)
        self._lc_section = make_section("Lifecycle acceptance")
        self._lc_holder = QHBoxLayout()
        self._lc_section.layout().addLayout(self._lc_holder)
        ir_row.addWidget(self._lc_section, 1)
        lay.addLayout(ir_row)

        # Attribute constraints.
        self._constraints_section = make_section("Attribute constraints")
        self._constraints_view = QPlainTextEdit()
        self._constraints_view.setReadOnly(True)
        self._constraints_view.setFont(mono)
        self._constraints_view.setFixedHeight(80)
        self._constraints_section.layout().addWidget(self._constraints_view)
        lay.addWidget(self._constraints_section)

        # USED BY (rich).
        self._used_by_section = make_section("Used by")
        self._used_by_holder = QVBoxLayout()
        self._used_by_section.layout().addLayout(self._used_by_holder)
        self.chip_strip = CrossRefChipStrip()
        self._used_by_section.layout().addWidget(self.chip_strip)
        lay.addWidget(self._used_by_section)
        lay.addStretch(1)

    def set_entry(self, entry: dict[str, Any]) -> None:
        self._id_chip.setText(entry.get("id", ""))
        narrative = entry.get("narrative") or (
            "Credential type this role expects to potentially hold — "
            "not a runtime instance assertion"
        )
        self._narrative_label.setText(narrative)
        self._said_label.setText(entry.get("expected_schema_said") or "(unset)")
        issuer = entry.get("expected_issuer_role")
        if issuer:
            self._issuer_chip.setText(issuer)
            self._issuer_chip.setStyleSheet(
                "background:#e8f4f4;color:#0a8a82;border-radius:9px;"
                "padding:2px 9px;font-size:11px;font-weight:600;"
            )
        else:
            self._issuer_chip.setText("(any)")
            self._issuer_chip.setStyleSheet(
                "color:#aaa;font-style:italic;font-size:11px;background:transparent;"
            )

        while self._lc_holder.count():
            item = self._lc_holder.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        states = entry.get("lifecycle_acceptance") or ["active"]
        for s in states:
            chip = QLabel(s)
            chip.setStyleSheet(
                "background:#e8f4f4;color:#0a8a82;border-radius:9px;"
                "padding:2px 9px;font-size:11px;font-weight:600;"
            )
            self._lc_holder.addWidget(chip)
        accept_btn = QLabel("+ accept state")
        accept_btn.setStyleSheet("color:#0ABFB0;font-size:11px;font-weight:600;")
        self._lc_holder.addWidget(accept_btn)
        self._lc_holder.addStretch(1)

        constraints = entry.get("expected_attribute_constraints") or {}
        if constraints:
            self._constraints_view.setPlainText(
                json.dumps(constraints, indent=2, sort_keys=True)
            )
            self._constraints_section.setVisible(True)
        else:
            self._constraints_view.setPlainText("")
            self._constraints_section.setVisible(False)

        while self._used_by_holder.count():
            item = self._used_by_holder.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        rid = entry.get("id", "")
        consumers = self._crossrefs.consumers_of(f"import:{rid}") if rid else []
        if not consumers:
            none_lbl = QLabel("Not referenced anywhere.")
            none_lbl.setStyleSheet("color:#aaa;font-style:italic;font-size:11px;")
            self._used_by_holder.addWidget(none_lbl)
        else:
            summary = QLabel(f"{len(consumers)} reference"
                             f"{'s' if len(consumers) != 1 else ''}:")
            summary.setStyleSheet("color:#666;font-size:11px;")
            self._used_by_holder.addWidget(summary)
            for ref in consumers:
                row_lbl = QLabel(f"→ {ref}")
                row_lbl.setStyleSheet("color:#0ABFB0;font-size:11px;")
                self._used_by_holder.addWidget(row_lbl)
        self.chip_strip.set_refs(consumers)

    def text_summary(self) -> str:
        parts = [
            self._id_chip.text(),
            self._narrative_label.text(),
            self._said_label.text(),
            self._issuer_chip.text(),
            self._constraints_view.toPlainText(),
        ]
        for lbl in self.findChildren(QLabel):
            parts.append(lbl.text())
        return " ".join(parts)


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
                subtitle=_import_subtitle(imp, crossrefs),
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
        for imp in self._model.doc.get("credentials", {}).get("imports", []):
            if imp.get("id") == item_id:
                self._pane.set_entry(imp)
                return

    def section_text(self) -> str:
        return self._pane.text_summary()
