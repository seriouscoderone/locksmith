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
        label = entry_label(e)
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

        header_strip = QFrame()
        header_strip.setStyleSheet(
            "background:#fff;border-bottom:1px solid #e0e3ea;"
        )
        h = QHBoxLayout(header_strip)
        h.setContentsMargins(20, 14, 20, 14)
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

        top_right_row = QHBoxLayout()
        top_right_row.addStretch(1)
        said_block = QVBoxLayout()
        said_block.setSpacing(0)
        said_title = QLabel("SAID")
        said_title.setStyleSheet(
            "font-size:9px;color:#888;font-weight:600;letter-spacing:0.5px;"
        )
        said_block.addWidget(said_title)
        short = (said[:4] + "…" + said[-4:]) if len(said) >= 8 else said
        self.said_label = QLabel(short)
        self.said_label.setStyleSheet(
            "color:#666;background:#f6f7f9;padding:2px 8px;border-radius:6px;"
            "font-size:10px;font-family:monospace;"
        )
        said_block.addWidget(self.said_label)
        top_right_row.addLayout(said_block)
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
        top_right_row.addWidget(self.panel_toggle)
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
        top_right_row.addWidget(self.json_toggle)
        self.kebab_button = KebabButton()
        top_right_row.addWidget(self.kebab_button)
        right_col.addLayout(top_right_row)

        self.walkthrough_button = QPushButton("Walk me through it")
        self.walkthrough_button.setStyleSheet(
            "background:#d97757;color:#fff;font-weight:600;"
            "padding:6px 12px;border-radius:4px;"
        )
        right_col.addWidget(self.walkthrough_button)

        h.addLayout(right_col)
        root.addWidget(header_strip)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border:0;background:#f6f7f9;")
        host = QWidget()
        grid = QGridLayout(host)
        grid.setContentsMargins(20, 20, 20, 20)
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

        # Trailing stretch row absorbs extra vertical space so the 2 card
        # rows sit at the top of the scroll area without stretching to
        # fill the viewport height.
        grid.setRowStretch(2, 1)
        # Equal column widths so cards in the same row align in width.
        for c in range(4):
            grid.setColumnStretch(c, 1)

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

        bottom = QFrame()
        bottom.setStyleSheet(
            "background:#fff;border-top:1px solid #e0e3ea;"
        )
        b = QHBoxLayout(bottom)
        b.setContentsMargins(20, 12, 20, 12)
        b.setSpacing(20)

        eco = QVBoxLayout()
        eco.setSpacing(2)
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
            none_chip.setStyleSheet("font-size:11px;color:#aaa;font-style:italic;")
            eco_chips_row.addWidget(none_chip)
        eco_chips_row.addStretch(1)
        eco.addLayout(eco_chips_row)
        b.addLayout(eco, 1)

        lin = QVBoxLayout()
        lin.setSpacing(2)
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
        b.addLayout(lin, 1)

        val = QVBoxLayout()
        val.setSpacing(2)
        val_title = QLabel("✓ VALIDATION")
        val_title.setStyleSheet(
            "font-size:10px;color:#0ABFB0;font-weight:600;letter-spacing:0.5px;"
        )
        val.addWidget(val_title)
        report = getattr(self._model, "last_validation_report", lambda: None)()
        if report is None:
            err = warn = 0
        else:
            err = sum(1 for i in report.issues
                      if getattr(i, "severity", "error") == "error")
            warn = sum(1 for i in report.issues
                       if getattr(i, "severity", "error") == "warning")
        self.bottom_validation_pill = ValidationPill(
            error_count=err, warning_count=warn,
        )
        val.addWidget(self.bottom_validation_pill)
        b.addLayout(val, 1)

        root.addWidget(bottom)

        self.bottom_panel_container = QFrame()
        self.bottom_panel_container.setStyleSheet(
            "background:#fff;border-top:1px solid #e0e3ea;"
        )
        self.bottom_panel_container.setFixedHeight(240)
        bottom_lay = QVBoxLayout(self.bottom_panel_container)
        bottom_lay.setContentsMargins(0, 0, 0, 0)
        bottom_lay.setSpacing(0)
        self._json_source_view = JsonSourceView()
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
