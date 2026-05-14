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
    QLabel, QLineEdit, QPlainTextEdit, QScrollArea, QVBoxLayout, QWidget,
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
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        # ---- Identity ----
        self._identity = make_section("Identity")
        self._id = QLineEdit()
        self._id.setReadOnly(True)
        self._name = QLineEdit()
        self._name.setReadOnly(True)
        self._description = QPlainTextEdit()
        self._description.setReadOnly(True)
        self._description.setFixedHeight(60)
        self._identity.layout().addWidget(QLabel("ID"))
        self._identity.layout().addWidget(self._id)
        self._identity.layout().addWidget(QLabel("Name"))
        self._identity.layout().addWidget(self._name)
        self._identity.layout().addWidget(QLabel("Description"))
        self._identity.layout().addWidget(self._description)
        lay.addWidget(self._identity)

        # ---- Source events ----
        self._source_events_section = make_section("Source events")
        self._source_events_label = QLabel("(none)")
        self._source_events_label.setStyleSheet(
            "color:#444;font-family:monospace;font-size:11px;"
        )
        self._source_events_label.setWordWrap(True)
        self._source_events_section.layout().addWidget(self._source_events_label)
        lay.addWidget(self._source_events_section)

        # ---- Fold expression (read-only) ----
        self._fold_section = make_section("Fold expression (read-only)")
        self._fold_view = QPlainTextEdit()
        self._fold_view.setReadOnly(True)
        mono = QFont("Menlo")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(10)
        self._fold_view.setFont(mono)
        self._fold_view.setFixedHeight(60)
        self._fold_section.layout().addWidget(self._fold_view)
        lay.addWidget(self._fold_section)

        # ---- Display ----
        self._display_section = make_section("Display")
        self._view_type_label = QLabel("(not set)")
        self._view_type_label.setStyleSheet("color:#444;font-weight:600;")
        self._display_section.layout().addWidget(QLabel("View type"))
        self._display_section.layout().addWidget(self._view_type_label)
        lay.addWidget(self._display_section)

        # ---- Live preview ----
        self._preview_section = make_section("Live preview")
        self._preview_label = QLabel("(select a projection to preview)")
        self._preview_label.setStyleSheet(
            "color:#555;font-size:12px;padding:4px;"
        )
        self._preview_label.setWordWrap(True)
        self._preview_label.setTextFormat(
            # Qt.RichText so we can embed <i> / <code> tags
            __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.RichText
        )
        self._preview_section.layout().addWidget(self._preview_label)
        lay.addWidget(self._preview_section)

        # ---- Entry JSON ----
        self._json_section = make_section("Entry JSON (read-only)")
        self._json_view = QPlainTextEdit()
        self._json_view.setReadOnly(True)
        mono2 = QFont("Menlo")
        mono2.setStyleHint(QFont.StyleHint.Monospace)
        mono2.setPointSize(10)
        self._json_view.setFont(mono2)
        self._json_view.setFixedHeight(120)
        self._json_section.layout().addWidget(self._json_view)
        lay.addWidget(self._json_section)

        # ---- Used by ----
        self._used_by = make_section("Used by")
        self.chip_strip = CrossRefChipStrip()
        self._used_by.layout().addWidget(self.chip_strip)
        lay.addWidget(self._used_by)
        lay.addStretch(1)

    def set_entry(self, entry: dict[str, Any]) -> None:
        self._id.setText(entry.get("id", ""))
        self._name.setText(entry.get("name", ""))
        self._description.setPlainText(entry.get("description", ""))

        source_events = entry.get("source_events", [])
        if source_events:
            self._source_events_label.setText(
                "\n".join(f"• {e}" for e in source_events)
            )
        else:
            self._source_events_label.setText("(none)")

        fold_expr = entry.get("fold_expression", "")
        self._fold_view.setPlainText(fold_expr)

        display = entry.get("display") or {}
        view_type = display.get("view_type")
        self._view_type_label.setText(view_type or "(not set)")

        # Live preview — try UEL evaluator, fall back to raw display
        self._update_preview(fold_expr)

        self._json_view.setPlainText(json.dumps(entry, indent=2, sort_keys=True))

        key = f"projection:{entry.get('id', '')}"
        self.chip_strip.set_refs(self._crossrefs.consumers_of(key))

    def _update_preview(self, expr: str) -> None:
        evaluator = _resolve_uel_evaluator()
        if evaluator is None:
            safe_expr = (
                expr.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            )
            self._preview_label.setText(
                f"<i>evaluator pending — showing raw expression:</i><br>"
                f"<code>{safe_expr}</code>"
            )
        else:
            try:
                result = evaluator(expr)
                self._preview_label.setText(str(result))
            except Exception as exc:
                self._preview_label.setText(
                    f"<i>evaluation error:</i><br><code>{exc}</code>"
                )


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
        """Whether the live preview label widget is currently visible."""
        return self._pane._preview_label.isVisible()

    def preview_text(self) -> str:
        """Current text content of the preview label (HTML stripped for comparison)."""
        return self._pane._preview_label.text()
