# -*- encoding: utf-8 -*-
"""TemplateOverviewPage: first-person mental-model card grid.

Renders the open TemplateModel as 9 first-person cards (one per primitive
group, with `role` having its own card). Field paths use canonical
meta-schema names; `entry_label` provides a uniform fallback chain.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.widgets.first_person_card import (
    FacetEntry, FirstPersonCard,
)


_CARD_SPECS: list[tuple[str, str, str, str]] = [
    # (kind, framing, secondary-label, doc-path)
    ("imports",     "I HOLD",         "Imported credentials",   "credentials.imports"),
    ("exports",     "I ISSUE",        "Issued credentials",     "credentials.exports"),
    ("commands",    "I DO",           "Commands",               "commands"),
    ("reactions",   "I RESPOND TO",   "Reactions",              "reactions"),
    ("workflows",   "I FOLLOW",       "Workflows",              "workflows"),
    ("aggregates",  "I TRACK",        "Aggregates",             "aggregates"),
    ("projections", "I SEE",          "Projections",            "projections"),
    ("rules",       "I'M BOUND BY",   "Rules",                  "rules"),
]


_EMPTY_MESSAGES: dict[str, str] = {
    "imports":     "No imports — this role is the root authority for licenses",
    "exports":     "No issued credentials yet",
    "commands":    "No commands yet",
    "reactions":   "No reactions yet",
    "workflows":   "No workflows yet",
    "aggregates":  "No aggregates yet",
    "projections": "No projections yet",
    "rules":       "No rules yet",
}


def _qualifier_for_export(entry: dict) -> str | None:
    env = entry.get("envelope", {})
    lc = entry.get("lifecycle", {})
    bits: list[str] = []
    if env.get("holder_role"):
        bits.append(f"to {env['holder_role']}")
    if lc.get("states"):
        bits.append(f"{len(lc['states'])} states")
    if entry.get("schema"):
        bits.append("1 schema")
    return " · ".join(bits) if bits else None


def _qualifier_for_aggregate(entry: dict) -> str | None:
    bits: list[str] = []
    scope = entry.get("log_scope")
    if scope:
        bits.append(f"{scope} log")
    invs = entry.get("invariants") or []
    if invs:
        bits.append(f"{len(invs)} invariant{'s' if len(invs) != 1 else ''}")
    return " · ".join(bits) if bits else None


def _qualifier_for_reaction(entry: dict) -> str | None:
    trig = entry.get("trigger", {})
    n = len(entry.get("emissions") or [])
    parts: list[str] = []
    t_type = trig.get("type")
    if t_type:
        parts.append(f"← {t_type}")
    if n:
        parts.append(f"{n} emission{'s' if n != 1 else ''}")
    return " · ".join(parts) if parts else None


def _qualifier_for_workflow(entry: dict) -> str | None:
    cp = entry.get("counterparty_role")
    steps = entry.get("steps") or []
    parts: list[str] = []
    if cp:
        parts.append(f"↔ {cp}")
    if steps:
        parts.append(f"{len(steps)} steps")
    return " · ".join(parts) if parts else None


def _entry_label_for(kind: str, entry: dict) -> str:
    # Credentials are user-facing ACDC labels — prefer the human name.
    # All other primitives are protocol-internal identifiers — show the
    # raw id verbatim so what the SME sees matches what gets serialized.
    if kind in ("imports", "exports"):
        return (entry.get("name") or entry.get("display_name")
                or entry.get("id") or entry.get("title") or "(unnamed)")
    return (entry.get("id") or entry.get("name")
            or entry.get("display_name") or entry.get("title") or "(unnamed)")


def _entries_for(kind: str, items: list[dict]) -> list:
    # Show up to 4 entries per card (matches v1 mock's "I DO" with 4
    # commands). Per-entry qualifier sublines only fire for the
    # primitives where the mock surfaces extra metadata: exports
    # ("to carrier · 4 states · 1 schema") and aggregates
    # ("witnessed log · 3 invariants"). Workflows / reactions /
    # commands / projections list just the entry names, matching
    # mock density.
    out = []
    for e in items[:4]:
        label = _entry_label_for(kind, e)
        if kind == "exports":
            q = _qualifier_for_export(e)
        elif kind == "aggregates":
            q = _qualifier_for_aggregate(e)
        else:
            q = None
        out.append(FacetEntry(label=label, qualifier=q))
    return out


def _rule_type_counts(rules: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rules:
        t = r.get("type", "")
        out[t] = out.get(t, 0) + 1
    return out


def entry_label(entry: dict, fallback: str = "(unnamed)") -> str:
    return (entry.get("display_name") or entry.get("name")
            or entry.get("title") or entry.get("id") or fallback)


def _list_at(doc: dict[str, Any], dotted_path: str) -> list[dict[str, Any]]:
    if not dotted_path:
        return []
    cur: Any = doc
    for part in dotted_path.split("."):
        if not isinstance(cur, dict):
            return []
        cur = cur.get(part)
        if cur is None:
            return []
    return cur if isinstance(cur, list) else []


class TemplateOverviewPage(QWidget):
    drilldown_requested = Signal(str)
    add_requested = Signal(str)
    edit_header_requested = Signal()
    edit_role_requested = Signal()

    def __init__(
        self,
        *,
        model: TemplateModel,
        ecosystem_tags: list[str] | None = None,
        parent=None,
    ):
        super().__init__(parent=parent)
        self._model = model
        self._ecosystem_tags = ecosystem_tags or []
        self._cards: dict[str, FirstPersonCard] = {}
        self._build()
        self._model.changed.connect(lambda _path: self._refresh())

    def _build(self) -> None:
        from locksmith.plugins.designer.widgets.role_icon_badge import (
            RoleIconBadge,
        )
        from locksmith.plugins.designer.widgets.kebab_button import KebabButton

        header = self._model.doc.get("header", {})
        role = self._model.doc.get("role", {})
        said = self._model.doc.get("d", "")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Slim page-chrome strip above the header card holds the global
        # utility toggles (validation panel, JSON source, kebab) so they
        # don't crowd the header card's SAID/CTA column.
        chrome_strip = QFrame()
        chrome_strip.setObjectName("overview-chrome-strip")
        chrome_strip.setStyleSheet(
            "#overview-chrome-strip{background:#fff;}"
            "#overview-chrome-strip QPushButton{background:transparent;}"
        )
        chrome_lay = QHBoxLayout(chrome_strip)
        chrome_lay.setContentsMargins(20, 6, 20, 0)
        chrome_lay.setSpacing(6)
        chrome_lay.addStretch(1)
        self.panel_toggle = QPushButton("⚠")
        self.panel_toggle.setCheckable(True)
        self.panel_toggle.setToolTip("Validation panel")
        self.panel_toggle.setFixedSize(28, 28)
        self.panel_toggle.setStyleSheet(
            "QPushButton{color:#666;font-size:13px;border:0;border-radius:4px;}"
            "QPushButton:hover{background:#f6f7f9;color:#1A1C20;}"
            "QPushButton:checked{background:#0ABFB0;color:#fff;}"
        )
        self.panel_toggle.toggled.connect(self._on_panel_toggled)
        chrome_lay.addWidget(self.panel_toggle)
        self.json_toggle = QPushButton("{ }")
        self.json_toggle.setCheckable(True)
        self.json_toggle.setToolTip("JSON source view")
        self.json_toggle.setFixedSize(36, 28)
        self.json_toggle.setStyleSheet(
            "QPushButton{color:#666;font-size:11px;font-family:monospace;"
            "border:0;border-radius:4px;}"
            "QPushButton:hover{background:#f6f7f9;color:#1A1C20;}"
            "QPushButton:checked{background:#0ABFB0;color:#fff;}"
        )
        self.json_toggle.toggled.connect(self._on_json_toggled)
        chrome_lay.addWidget(self.json_toggle)
        self.kebab_button = KebabButton()
        chrome_lay.addWidget(self.kebab_button)
        root.addWidget(chrome_strip)

        header_strip = QFrame()
        header_strip.setObjectName("overview-header-strip")
        header_strip.setStyleSheet(
            "#overview-header-strip{background:#fff;}"
            "#overview-header-strip QLabel{background:transparent;}"
            "#overview-header-strip QPushButton{background:transparent;}"
        )
        h = QHBoxLayout(header_strip)
        h.setContentsMargins(20, 8, 20, 14)
        h.setSpacing(14)

        self.role_badge = RoleIconBadge(kind=role.get("kind", ""), size=52)
        h.addWidget(self.role_badge)

        center = QVBoxLayout()
        center.setSpacing(3)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self._header_label = QLabel(header.get("display_name", ""))
        self._header_label.setStyleSheet(
            "font-size:18px;font-weight:600;color:#1A1C20;"
        )
        title_row.addWidget(self._header_label)
        self.version_chip = QLabel(f"v{header.get('version', '0.0')}")
        self.version_chip.setStyleSheet(
            "color:#888;background:#f6f7f9;padding:2px 8px;border-radius:10px;"
            "font-size:11px;"
        )
        title_row.addWidget(self.version_chip)
        title_row.addStretch(1)
        center.addLayout(title_row)

        role_kind = role.get("kind", "")
        keri_infra = role.get("keri_infrastructure", {})
        infra_count = sum(1 for v in keri_infra.values() if v)
        self.role_subtitle = QLabel(
            f"<span style='color:#0ABFB0;font-weight:600;'>I am</span>"
            f" · {role.get('display_name', '')}"
            f" · {role_kind} · {infra_count} KERI services"
        )
        self.role_subtitle.setStyleSheet("font-size:12px;color:#444;")
        self.role_subtitle.setTextFormat(Qt.RichText)
        center.addWidget(self.role_subtitle)

        self.description_label = QLabel(header.get("description", ""))
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet("font-size:12px;color:#444;")
        center.addWidget(self.description_label)

        h.addLayout(center, 1)

        right_col = QVBoxLayout()
        right_col.setSpacing(6)
        right_col.setAlignment(Qt.AlignTop)

        said_block = QVBoxLayout()
        said_block.setSpacing(0)
        said_block.setAlignment(Qt.AlignRight)
        said_title = QLabel("SAID")
        said_title.setStyleSheet(
            "font-size:9px;color:#888;font-weight:600;letter-spacing:0.5px;"
        )
        said_title.setAlignment(Qt.AlignRight)
        said_block.addWidget(said_title)
        short = (said[:4] + "…" + said[-4:]) if len(said) >= 8 else said
        self.said_label = QLabel(short)
        self.said_label.setStyleSheet(
            "color:#666;background:#f6f7f9;padding:2px 8px;border-radius:6px;"
            "font-size:10px;font-family:monospace;"
        )
        self.said_label.setAlignment(Qt.AlignRight)
        said_block.addWidget(self.said_label)
        right_col.addLayout(said_block)

        self.walkthrough_button = QPushButton("Walk me through it")
        # Explicit QPushButton selector so the strip's descendant
        # transparent rule doesn't override the orange fill.
        self.walkthrough_button.setStyleSheet(
            "QPushButton{background:#d97757;color:#fff;font-weight:600;"
            "padding:6px 12px;border-radius:4px;}"
        )
        right_col.addWidget(self.walkthrough_button)

        h.addLayout(right_col)
        root.addWidget(header_strip)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border:0;background:#f6f7f9;")
        host = QWidget()
        host_lay = QVBoxLayout(host)
        host_lay.setContentsMargins(0, 0, 0, 0)
        host_lay.setSpacing(0)
        grid_container = QWidget()
        grid = QGridLayout(grid_container)
        grid.setContentsMargins(20, 20, 20, 8)
        grid.setSpacing(14)
        self._grid = grid

        for idx, (kind, framing, label, dotted) in enumerate(_CARD_SPECS):
            items_at = _list_at(self._model.doc, dotted)
            count = len(items_at)
            if kind == "rules":
                card = FirstPersonCard(
                    framing=framing, kind_label=label,
                    count=count, entries=[],
                    rule_type_counts=_rule_type_counts(items_at),
                    empty_message=_EMPTY_MESSAGES[kind],
                )
            else:
                card = FirstPersonCard(
                    framing=framing, kind_label=label,
                    count=count,
                    entries=_entries_for(kind, items_at),
                    empty_message=_EMPTY_MESSAGES[kind],
                )
            card.clicked.connect(lambda k=kind: self.drilldown_requested.emit(k))
            card.add_clicked.connect(lambda k=kind: self.add_requested.emit(k))
            row, col = divmod(idx, 4)
            grid.addWidget(card, row, col)
            self._cards[kind] = card

        # Equal column widths so cards in the same row align in width.
        for c in range(4):
            grid.setColumnStretch(c, 1)

        host_lay.addWidget(grid_container)

        scroll.setWidget(host)

        from locksmith.plugins.designer.widgets.validation_panel import (
            ValidationPanel,
        )
        from locksmith.plugins.designer.widgets.json_source_view import (
            JsonSourceView,
        )

        body_row = QHBoxLayout()
        body_row.setContentsMargins(0, 0, 0, 0)
        body_row.setSpacing(0)
        body_row.addWidget(scroll, 1)
        self.side_panel_container = QFrame()
        self.side_panel_container.setFixedWidth(320)
        self.side_panel_container.setStyleSheet(
            "background:#fff;border-left:1px solid #e0e3ea;"
        )
        side_lay = QVBoxLayout(self.side_panel_container)
        side_lay.setContentsMargins(0, 0, 0, 0)
        side_lay.setSpacing(0)
        self._validation_panel = ValidationPanel()
        # Initial population — without this the panel renders just its
        # "Validation" header on first open. set_report covers both the
        # populated and empty-state ("No issues — template is valid.")
        # paths.
        from locksmith.plugins.designer.validation import ValidationReport
        report = (
            getattr(self._model, "last_validation_report", lambda: None)()
            or ValidationReport(errors=(), warnings=())
        )
        self._validation_panel.set_report(report)
        side_lay.addWidget(self._validation_panel)
        self.side_panel_container.setVisible(False)
        body_row.addWidget(self.side_panel_container)
        root.addLayout(body_row, 1)

        from locksmith.plugins.designer.widgets.ecosystem_chip import (
            EcosystemChip,
        )
        from locksmith.plugins.designer.widgets.validation_pill import (
            ValidationPill,
        )

        # Bottom metadata strip lives INSIDE the scroll host so it sits
        # flush below the card grid (mock parity) rather than docking to
        # the viewport bottom and leaving a vertical dead-zone above it.
        bottom = QFrame()
        bottom.setObjectName("overview-bottom-strip")
        bottom.setStyleSheet(
            "#overview-bottom-strip{background:#f6f7f9;}"
            "#overview-bottom-strip QLabel{background:transparent;}"
        )
        b = QHBoxLayout(bottom)
        b.setContentsMargins(20, 6, 20, 20)
        b.setSpacing(10)

        # Eco affinity cell — white card.
        eco_cell = QFrame()
        eco_cell.setObjectName("overview-eco-cell")
        eco_cell.setStyleSheet(
            "#overview-eco-cell{background:#fff;border:1px solid #e0e3ea;"
            "border-radius:6px;}"
            "#overview-eco-cell QLabel{background:transparent;}"
        )
        eco = QVBoxLayout(eco_cell)
        eco.setContentsMargins(14, 10, 14, 10)
        eco.setSpacing(4)
        eco_title = QLabel("ECOSYSTEM AFFINITY")
        eco_title.setStyleSheet(
            "font-size:10px;color:#0ABFB0;font-weight:600;letter-spacing:0.5px;"
        )
        eco.addWidget(eco_title)
        eco_chips_row = QHBoxLayout()
        eco_chips_row.setSpacing(6)
        self.ecosystem_chips: list[QLabel] = []
        for tag in self._ecosystem_tags:
            chip = EcosystemChip(tag)
            self.ecosystem_chips.append(chip)
            eco_chips_row.addWidget(chip)
        if not self._ecosystem_tags:
            none_chip = QLabel("(none)")
            none_chip.setStyleSheet("font-size:11px;color:#aaa;")
            eco_chips_row.addWidget(none_chip)
        eco_chips_row.addStretch(1)
        eco.addLayout(eco_chips_row)
        b.addWidget(eco_cell, 1)

        # Lineage cell — white card.
        lin_cell = QFrame()
        lin_cell.setObjectName("overview-lin-cell")
        lin_cell.setStyleSheet(
            "#overview-lin-cell{background:#fff;border:1px solid #e0e3ea;"
            "border-radius:6px;}"
            "#overview-lin-cell QLabel{background:transparent;}"
        )
        lin = QVBoxLayout(lin_cell)
        lin.setContentsMargins(14, 10, 14, 10)
        lin.setSpacing(4)
        lin_title = QLabel("LINEAGE")
        lin_title.setStyleSheet(
            "font-size:10px;color:#0ABFB0;font-weight:600;letter-spacing:0.5px;"
        )
        lin.addWidget(lin_title)
        forked = (self._model.doc.get("header", {})
                                  .get("forked_from", {}) or {})
        if forked.get("template_said"):
            ft = forked["template_said"]
            short = ft[:4] + "…" + ft[-6:] if len(ft) > 12 else ft
            self.lineage_label = QLabel(f"↪ forked from {short}")
        else:
            self.lineage_label = QLabel("No parent template")
        self.lineage_label.setStyleSheet("font-size:11px;color:#666;")
        lin.addWidget(self.lineage_label)
        b.addWidget(lin_cell, 1)

        # Validation cell — tinted by severity. Whole card carries the
        # color so a valid template visually celebrates; warning/invalid
        # surface their state at the same grain.
        report = getattr(self._model, "last_validation_report", lambda: None)()
        if report is None:
            err = warn = 0
        else:
            err = len(report.errors)
            warn = len(report.warnings)
        if err > 0:
            val_bg, val_border, val_title_color = "#fce8ea", "#f5c6c1", "#a52a2a"
            val_title_text = "VALIDATION"
        elif warn > 0:
            val_bg, val_border, val_title_color = "#fdf3e7", "#ffe0b2", "#a5641a"
            val_title_text = "VALIDATION"
        else:
            val_bg, val_border, val_title_color = "#e8f5e9", "#c8e6c9", "#1b5e20"
            val_title_text = "✓ VALIDATION"
        val_cell = QFrame()
        val_cell.setObjectName("overview-val-cell")
        val_cell.setStyleSheet(
            f"#overview-val-cell{{background:{val_bg};border:1px solid {val_border};"
            "border-radius:6px;}"
            "#overview-val-cell QLabel{background:transparent;}"
        )
        val = QVBoxLayout(val_cell)
        val.setContentsMargins(14, 10, 14, 10)
        val.setSpacing(4)
        val_title = QLabel(val_title_text)
        val_title.setStyleSheet(
            f"font-size:10px;color:{val_title_color};font-weight:600;"
            "letter-spacing:0.5px;"
        )
        val.addWidget(val_title)
        self.bottom_validation_pill = ValidationPill(
            error_count=err, warning_count=warn,
        )
        val.addWidget(self.bottom_validation_pill)
        b.addWidget(val_cell, 1)

        host_lay.addWidget(bottom)
        host_lay.addStretch(1)

        self.bottom_panel_container = QFrame()
        self.bottom_panel_container.setStyleSheet(
            "background:#fff;border-top:1px solid #e0e3ea;"
        )
        self.bottom_panel_container.setFixedHeight(240)
        bottom_lay = QVBoxLayout(self.bottom_panel_container)
        bottom_lay.setContentsMargins(0, 0, 0, 0)
        bottom_lay.setSpacing(0)
        self._json_source_view = JsonSourceView()
        # Populate so the editor isn't a blank dark slab on first open.
        self._json_source_view.set_doc(self._model.doc)
        bottom_lay.addWidget(self._json_source_view)
        self.bottom_panel_container.setVisible(False)
        root.addWidget(self.bottom_panel_container)

    def _on_panel_toggled(self, checked: bool) -> None:
        self.side_panel_container.setVisible(checked)

    def _on_json_toggled(self, checked: bool) -> None:
        self.bottom_panel_container.setVisible(checked)

    def _refresh(self) -> None:
        # Tear down + rebuild — templates are small enough this is cheap.
        layout = self.layout()
        while layout.count():
            old = layout.takeAt(0).widget()
            if old is not None:
                old.setParent(None)
                old.deleteLater()
        self._cards = {}
        self._build()

    def card_kinds(self) -> list[str]:
        return list(self._cards.keys())

    def click_card(self, kind: str) -> None:
        if kind in self._cards:
            self._cards[kind].clicked.emit()

    def header_label_text(self) -> str:
        return self._header_label.text()

    def role_chip_text(self) -> str:
        # Compatibility shim — older tests asserted against a chip text.
        # The role moved into a richer subtitle; return its plain text.
        return self.role_subtitle.text()
