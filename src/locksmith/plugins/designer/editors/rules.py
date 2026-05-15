# -*- encoding: utf-8 -*-
"""RulesEditorPage: 'I'm bound by …' surface.

Rules are color-coded by type in the rail. Right-pane sections vary
per rule type: prose types show body; computational/predicate/validation
types show expression + language. Predicates also surface their purpose.
"""
from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QVBoxLayout, QWidget,
)

from locksmith.plugins.designer.crossref import CrossRefIndex
from locksmith.plugins.designer.editors._shared import make_section
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.widgets.cross_ref_chip import CrossRefChipStrip
from locksmith.plugins.designer.widgets.kind_rail import RailItem
from locksmith.plugins.designer.widgets.primitive_editor_shell import (
    PrimitiveEditorShell,
)


_RULE_TYPE_COLOR: dict[str, str] = {
    "legal_prose": "#4A4FCE",
    "behavioral_expectation": "#A36AE6",
    "business_policy": "#D9A04F",
    "predicate": "#0ABFB0",
    "computational": "#D9A04F",
    "validation": "#E94B4B",
    "binding_link": "#888888",
}


def rule_type_color(rule_type: str) -> str:
    return _RULE_TYPE_COLOR.get(rule_type, "#888888")


_PROSE_TYPES = {"legal_prose", "behavioral_expectation", "business_policy"}
_EXPR_TYPES = {"predicate", "computational", "validation"}


_TYPE_GROUPS: list[tuple[str, list[str]]] = [
    ("LEGAL PROSE",    ["legal_prose", "behavioral_expectation"]),
    ("PREDICATE",      ["predicate"]),
    ("VALIDATION",     ["validation", "computational"]),
    ("BINDING LINK",   ["binding_link"]),
]


def _filter_chip_label(type_id: str) -> str:
    return {
        "legal_prose": "prose",
        "behavioral_expectation": "prose",
        "predicate": "predicate",
        "validation": "validation",
        "computational": "validation",
        "binding_link": "link",
    }.get(type_id, type_id)


def _rule_subtitle(r: dict, crossrefs) -> str:
    rid = r.get("id", "")
    consumers = crossrefs.consumers_of(f"rule:{rid}") if rid else []
    n = len(consumers)
    rtype = r.get("type", "")
    parts: list[str] = []
    if rtype == "predicate":
        purpose = r.get("purpose")
        if purpose:
            parts.append(f"purpose: {purpose}")
    if rtype == "binding_link":
        links = r.get("links") or []
        parts.append(f"links {len(links)} rules")
    if n:
        parts.append(f"→ on {n} reference{'s' if n != 1 else ''}")
    return " · ".join(parts) if parts else ""


def _rail_items_grouped(rules: list[dict], crossrefs, color_for_type) -> list[RailItem]:
    items: list[RailItem] = []
    for header, type_ids in _TYPE_GROUPS:
        bucket = [r for r in rules if r.get("type", "") in type_ids]
        if not bucket:
            continue
        items.append(RailItem(
            id=f"__header_{header}", label="", kind_color="",
            has_errors=False, group_header=header,
        ))
        for r in bucket:
            items.append(RailItem(
                id=r.get("id", ""),
                label=r.get("title") or r.get("id") or "(unnamed)",
                subtitle=_rule_subtitle(r, crossrefs),
                kind_color=color_for_type(r.get("type", "")),
                has_errors=False,
            ))
    return items


class _RuleSectionPane(QWidget):
    def __init__(self, crossrefs: CrossRefIndex, model: TemplateModel = None,
                 parent=None):
        super().__init__(parent=parent)
        self._crossrefs = crossrefs
        self._model = model
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
        self._badge_holder = QHBoxLayout()
        title_row.addLayout(self._badge_holder)
        self._title_label = QLabel("")
        self._title_label.setStyleSheet(
            "font-size:16px;font-weight:600;color:#1A1C20;"
        )
        title_row.addWidget(self._title_label)
        title_row.addStretch(1)
        self._id_chip = QLabel("")
        self._id_chip.setStyleSheet(
            "color:#666;background:#f6f7f9;font-family:monospace;"
            "border-radius:6px;padding:2px 8px;font-size:10px;"
        )
        title_row.addWidget(self._id_chip)
        h.addLayout(title_row)
        self._description_label = QLabel("")
        self._description_label.setStyleSheet("color:#444;font-size:12px;")
        self._description_label.setWordWrap(True)
        h.addWidget(self._description_label)
        lay.addWidget(self._header_frame)

        # Details (type-specific).
        self._details_section = make_section("Details")
        self._details_holder = QVBoxLayout()
        self._details_section.layout().addLayout(self._details_holder)
        lay.addWidget(self._details_section)

        # Referenced from.
        self._references_section = make_section("Referenced from")
        self._references_holder = QVBoxLayout()
        self._references_section.layout().addLayout(self._references_holder)
        lay.addWidget(self._references_section)

        # Pairs with (binding links).
        self._pairs_section = make_section("Pairs with (binding links)")
        self._pairs_holder = QVBoxLayout()
        self._pairs_section.layout().addLayout(self._pairs_holder)
        lay.addWidget(self._pairs_section)

        # Used by (existing chip strip kept for navigation compatibility).
        self._used_by = make_section("Used by")
        self.chip_strip = CrossRefChipStrip()
        self._used_by.layout().addWidget(self.chip_strip)
        lay.addWidget(self._used_by)
        lay.addStretch(1)

    def set_entry(self, entry: dict[str, Any]) -> None:
        from locksmith.plugins.designer.widgets.dark_code_block import (
            DarkCodeBlock,
        )
        from locksmith.plugins.designer.widgets.type_color_badge import (
            TypeColorBadge,
        )

        def _clear(layout) -> None:
            while layout.count():
                item = layout.takeAt(0)
                w = item.widget() if item is not None else None
                if w is not None:
                    w.setParent(None)
                    w.deleteLater()

        self._title_label.setText(entry.get("title") or entry.get("id") or "(unnamed)")
        self._id_chip.setText(entry.get("id", ""))
        self._description_label.setText(entry.get("description") or "")

        _clear(self._badge_holder)
        self._badge_holder.addWidget(TypeColorBadge(entry.get("type", "")))

        _clear(self._details_holder)
        rtype = entry.get("type", "")
        if rtype in _PROSE_TYPES:
            body = entry.get("body", "")
            body_lbl = QLabel(body or "(no body)")
            body_lbl.setStyleSheet("color:#1A1C20;font-size:13px;")
            body_lbl.setWordWrap(True)
            self._details_holder.addWidget(body_lbl)
        elif rtype in _EXPR_TYPES:
            if entry.get("purpose"):
                p_row = QHBoxLayout()
                p_lbl = QLabel("Purpose:")
                p_lbl.setStyleSheet("color:#666;font-size:11px;")
                p_row.addWidget(p_lbl)
                p_chip = QLabel(entry["purpose"])
                p_chip.setStyleSheet(
                    "background:#e8f4f4;color:#0a8a82;border-radius:9px;"
                    "padding:2px 9px;font-size:11px;font-weight:600;"
                )
                p_row.addWidget(p_chip)
                bound_lbl = QLabel("↗ bound context: { state, event, transition }")
                bound_lbl.setStyleSheet("color:#0ABFB0;font-size:10px;")
                p_row.addWidget(bound_lbl)
                p_row.addStretch(1)
                p_w = QFrame()
                p_w.setLayout(p_row)
                self._details_holder.addWidget(p_w)
            if entry.get("language"):
                l_row = QHBoxLayout()
                l_lbl = QLabel("Language:")
                l_lbl.setStyleSheet("color:#666;font-size:11px;")
                l_row.addWidget(l_lbl)
                l_chip = QLabel(entry["language"])
                l_chip.setStyleSheet(
                    "background:#f0f2f5;color:#444;border-radius:9px;"
                    "padding:2px 9px;font-size:11px;"
                )
                l_row.addWidget(l_chip)
                l_row.addStretch(1)
                l_w = QFrame()
                l_w.setLayout(l_row)
                self._details_holder.addWidget(l_w)
            expr = entry.get("expression", "")
            self._details_holder.addWidget(DarkCodeBlock(expr))
            cheat = QLabel("↗ UEL/1.0 cheat-sheet · test expression")
            cheat.setStyleSheet("color:#0ABFB0;font-size:10px;")
            self._details_holder.addWidget(cheat)
        elif rtype == "binding_link":
            links_lbl = QLabel("This rule couples:")
            links_lbl.setStyleSheet("color:#666;font-size:11px;")
            self._details_holder.addWidget(links_lbl)
            for link in entry.get("links") or []:
                rid = link.get("rule_id", "")
                chip = QLabel(rid)
                chip.setStyleSheet(
                    "background:#f3edfb;color:#A36AE6;border-radius:9px;"
                    "padding:2px 9px;font-size:11px;font-weight:600;"
                )
                self._details_holder.addWidget(chip)

        # Referenced from — crossref consumers.
        _clear(self._references_holder)
        rid = entry.get("id", "")
        consumers = self._crossrefs.consumers_of(f"rule:{rid}") if rid else []
        if not consumers:
            none_lbl = QLabel("Not referenced anywhere yet.")
            none_lbl.setStyleSheet("color:#aaa;font-style:italic;font-size:11px;")
            self._references_holder.addWidget(none_lbl)
        else:
            summary = QLabel(
                f"This rule is referenced in {len(consumers)} place"
                f"{'s' if len(consumers) != 1 else ''} across the template:"
            )
            summary.setStyleSheet("color:#444;font-size:11px;")
            self._references_holder.addWidget(summary)
            for ref in consumers:
                row_lbl = QLabel(f"• {ref}")
                row_lbl.setStyleSheet("color:#0ABFB0;font-size:11px;")
                self._references_holder.addWidget(row_lbl)

        # Pairs with — find binding_link rules pointing to this rule.
        _clear(self._pairs_holder)
        all_rules = (self._model.doc.get("rules", []) if self._model else [])
        pairs: list[tuple[dict, dict]] = []
        for r in all_rules:
            if r.get("type") != "binding_link":
                continue
            link_ids = [link.get("rule_id") for link in (r.get("links") or [])]
            if rid in link_ids:
                for partner_id in link_ids:
                    if partner_id == rid:
                        continue
                    partner = next(
                        (rr for rr in all_rules if rr.get("id") == partner_id),
                        None,
                    )
                    if partner is not None:
                        pairs.append((r, partner))
        if not pairs:
            none_lbl = QLabel("Not paired via any binding_link rule.")
            none_lbl.setStyleSheet("color:#aaa;font-style:italic;font-size:11px;")
            self._pairs_holder.addWidget(none_lbl)
        else:
            for link_rule, partner in pairs:
                row_w = QFrame()
                row = QHBoxLayout(row_w)
                row.setContentsMargins(0, 0, 0, 0)
                row.setSpacing(6)
                row.addWidget(TypeColorBadge("binding_link"))
                row.addWidget(QLabel(link_rule.get("id", "")))
                row.addWidget(QLabel("couples with"))
                row.addWidget(TypeColorBadge(partner.get("type", "")))
                pid = QLabel(partner.get("id", ""))
                pid.setStyleSheet(
                    "color:#666;background:#f6f7f9;font-family:monospace;"
                    "border-radius:6px;padding:2px 8px;font-size:10px;"
                )
                row.addWidget(pid)
                row.addStretch(1)
                self._pairs_holder.addWidget(row_w)

        self.chip_strip.set_refs(consumers)

    def text_summary(self) -> str:
        from locksmith.plugins.designer.widgets.dark_code_block import (
            DarkCodeBlock,
        )
        parts = [
            self._title_label.text(),
            self._id_chip.text(),
            self._description_label.text(),
        ]
        for lbl in self.findChildren(QLabel):
            parts.append(lbl.text())
        for block in self.findChildren(DarkCodeBlock):
            parts.append(block.toPlainText())
        return " ".join(parts)


class RulesEditorPage(QWidget):
    navigated = Signal(str, str)

    def __init__(self, *, model: TemplateModel, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._model = model
        from locksmith.plugins.designer.widgets.rail_filter_chip_bar import (
            RailFilterChipBar,
        )
        rules_all = list(model.doc.get("rules", []))
        items = _rail_items_grouped(rules_all, crossrefs, rule_type_color)

        chip_counts: dict[str, int] = {
            "all": len(rules_all), "prose": 0, "predicate": 0,
            "validation": 0, "link": 0,
        }
        for r in rules_all:
            label = _filter_chip_label(r.get("type", ""))
            chip_counts[label] = chip_counts.get(label, 0) + 1
        self._filter_bar = RailFilterChipBar(
            chips=[
                ("all", chip_counts["all"]),
                ("prose", chip_counts["prose"]),
                ("predicate", chip_counts["predicate"]),
                ("validation", chip_counts["validation"]),
                ("link", chip_counts["link"]),
            ],
            active="all",
        )
        self.shell = PrimitiveEditorShell(
            surface_label="Rules",
            template_label=model.doc.get("header", {}).get("display_name", "(untitled)"),
            items=items,
            add_label="+ Add rule",
            item_count=len(rules_all),
            role_label=model.doc.get("role", {}).get("id", ""),
            is_valid=True,
            parent=self,
        )
        self._pane = _RuleSectionPane(crossrefs=crossrefs, model=model)
        if rules_all:
            self._pane.set_entry(rules_all[0])
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
        outer.setSpacing(0)
        outer.addWidget(self._filter_bar)
        outer.addWidget(self.shell)

    def _on_select(self, item_id: str) -> None:
        for r in self._model.doc.get("rules", []):
            if r.get("id") == item_id:
                self._pane.set_entry(r)
                return

    def section_text(self) -> str:
        return self._pane.text_summary()
