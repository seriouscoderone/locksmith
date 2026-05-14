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
    # (kind, framing, label, doc-path-to-list)
    ("role",        "I am …",          "Role",                   ""),
    ("imports",     "I hold …",        "Imported credentials",   "credentials.imports"),
    ("exports",     "I issue …",       "Issued credentials",     "credentials.exports"),
    ("commands",    "I do …",          "Commands",               "commands"),
    ("reactions",   "I respond to …",  "Reactions",              "reactions"),
    ("workflows",   "I follow …",      "Workflows",              "workflows"),
    ("aggregates",  "I track …",       "Aggregates",             "aggregates"),
    ("projections", "I see …",         "Projections",            "projections"),
    ("rules",       "I'm bound by …",  "Rules",                  "rules"),
]


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

    def __init__(self, *, model: TemplateModel, parent=None):
        super().__init__(parent=parent)
        self._model = model
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

        for idx, (kind, framing, label, dotted) in enumerate(_CARD_SPECS):
            if kind == "role":
                role = self._model.doc.get("role", {})
                entries = [FacetEntry(
                    label=f"{role.get('display_name', '(unnamed)')} ({role.get('kind', '?')})",
                )]
                count = 1
            else:
                items_at = _list_at(self._model.doc, dotted)
                entries = [FacetEntry(label=entry_label(e)) for e in items_at]
                count = len(items_at)
            card = FirstPersonCard(
                framing=framing, kind_label=label,
                count=count, entries=entries,
            )
            card.clicked.connect(lambda k=kind: self.drilldown_requested.emit(k))
            card.add_clicked.connect(lambda k=kind: self.add_requested.emit(k))
            row, col = divmod(idx, 3)
            grid.addWidget(card, row, col)
            self._cards[kind] = card

        scroll.setWidget(host)
        root.addWidget(scroll, 1)

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
