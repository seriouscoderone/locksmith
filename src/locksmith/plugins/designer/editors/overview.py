# -*- encoding: utf-8 -*-
"""TemplateOverviewPage: first-person mental-model card grid.

Renders the open TemplateModel as 9 first-person cards (one per primitive
group, with `role` having its own card). Field paths use canonical
meta-schema names; `entry_label` provides a uniform fallback chain.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
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
        self._header_label = QLabel()
        self._role_chip = QPushButton()
        self._build()
        self._model.changed.connect(lambda _path: self._refresh())

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header_strip = QFrame()
        header_strip.setStyleSheet("background:#fff;border-bottom:1px solid #e0e3ea;")
        h = QHBoxLayout(header_strip)
        h.setContentsMargins(20, 14, 20, 14)
        self._header_label.setText(self._model.doc.get("header", {}).get("display_name", ""))
        self._header_label.setStyleSheet("font-size:18px;font-weight:600;color:#1A1C20;")
        h.addWidget(self._header_label)
        sep = QLabel("·")
        sep.setStyleSheet("color:#ccc;")
        h.addWidget(sep)
        role = self._model.doc.get("role", {})
        self._role_chip.setText(
            f"{role.get('display_name', '')} · {role.get('kind', '')}"
        )
        self._role_chip.setFlat(True)
        self._role_chip.setStyleSheet(
            "background:#0ABFB0;color:#fff;border-radius:10px;"
            "padding:3px 10px;font-size:11px;font-weight:600;"
        )
        self._role_chip.clicked.connect(self.edit_role_requested.emit)
        h.addWidget(self._role_chip)
        h.addStretch(1)
        edit_header_btn = QPushButton("Edit header")
        edit_header_btn.clicked.connect(self.edit_header_requested.emit)
        h.addWidget(edit_header_btn)
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
        self._header_label = QLabel()
        self._role_chip = QPushButton()
        self._build()

    def card_kinds(self) -> list[str]:
        return list(self._cards.keys())

    def click_card(self, kind: str) -> None:
        if kind in self._cards:
            self._cards[kind].clicked.emit()

    def header_label_text(self) -> str:
        return self._header_label.text()

    def role_chip_text(self) -> str:
        return self._role_chip.text()
