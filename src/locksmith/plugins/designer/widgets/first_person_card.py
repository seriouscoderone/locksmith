# -*- encoding: utf-8 -*-
"""FirstPersonCard: Overview card framed in first person.

Two layout variants:

* default: "I HOLD"-style facet label + count badge + entry list with
  optional per-entry qualifier sublines + "+ Add" link.
* rule-type-chip: same shell but renders type-count chips in place of
  entries. Used for "I'M BOUND BY" where listing individual rule names
  is less useful than seeing the type distribution.

Card density target: matches the v1 mock at .superpowers/brainstorm/
69587-1778622927/content/overview-page.html — facet label + count on
one line, then entries directly beneath (no secondary "kind label"
row), up to 4 entries with optional small grey qualifier line, then
"+ Add". The `kind_label` constructor arg is retained for API
compatibility but no longer rendered; the framing label carries the
identity.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout,
)


_RULE_TYPE_COLORS: dict[str, str] = {
    "prose":              "#A36AE6",
    "legal_prose":        "#A36AE6",
    "behavioral_expectation": "#A36AE6",
    "predicate":          "#0ABFB0",
    "validation":         "#D97757",
    "computational":      "#888888",
    "binding_link":       "#666666",
}

_RULE_TYPE_LABEL: dict[str, str] = {
    "prose":              "prose",
    "legal_prose":        "prose",
    "behavioral_expectation": "prose",
    "predicate":          "predicates",
    "validation":         "validation",
    "computational":      "computational",
    "binding_link":       "link",
}


@dataclass(frozen=True)
class FacetEntry:
    label: str
    qualifier: str | None = None


class FirstPersonCard(QFrame):
    clicked = Signal()
    add_clicked = Signal()

    def __init__(
        self,
        *,
        framing: str,
        kind_label: str,
        count: int,
        entries: list[FacetEntry] | None = None,
        rule_type_counts: dict[str, int] | None = None,
        empty_message: str | None = None,
        parent=None,
    ):
        super().__init__(parent=parent)
        self.setObjectName("fpcard")
        self.setStyleSheet(
            "#fpcard{background:#fff;border:1px solid #e0e3ea;border-radius:8px;}"
            "#fpcard:hover{border:1px solid #d97757;}"
        )
        # Expand to fill the grid cell so cards in the same row line up
        # vertically (matching their row's max-content height). The
        # overview grid uses a trailing stretch row to keep the cards
        # parked at the top of the viewport instead of growing to fill
        # the whole window.
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Retain kind_label on the instance for callers that introspect,
        # but do not render it — mock parity.
        self._kind_label = kind_label
        self._entries_text_cache = ""
        self._chips_text_cache = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(6)
        self.framing_label = QLabel(framing)
        self.framing_label.setStyleSheet(
            "color:#0ABFB0;font-size:11px;font-weight:600;"
            "letter-spacing:0.5px;text-transform:uppercase;"
        )
        header.addWidget(self.framing_label)
        header.addStretch(1)
        count_label = QLabel(str(count))
        count_label.setStyleSheet(
            "background:#f6f7f9;color:#666;border-radius:10px;"
            "padding:1px 8px;font-size:10px;font-weight:600;"
        )
        header.addWidget(count_label)
        outer.addLayout(header)

        if rule_type_counts:
            chip_row = QHBoxLayout()
            chip_row.setSpacing(6)
            chips_parts: list[str] = []
            for type_id, n in rule_type_counts.items():
                if n <= 0:
                    continue
                label = _RULE_TYPE_LABEL.get(type_id, type_id)
                color = _RULE_TYPE_COLORS.get(type_id, "#888888")
                chip = QLabel(f"{n} {label}")
                chip.setStyleSheet(
                    f"color:{color};background:#f6f7f9;border-radius:9px;"
                    "padding:2px 8px;font-size:11px;font-weight:600;"
                )
                chip_row.addWidget(chip)
                chips_parts.append(f"{n} {label}")
            chip_row.addStretch(1)
            outer.addLayout(chip_row)
            self._chips_text_cache = " ".join(chips_parts)
        elif entries:
            parts: list[str] = []
            for entry in entries[:4]:
                main = QLabel(entry.label)
                main.setStyleSheet("font-size:12px;color:#1A1C20;")
                main.setWordWrap(True)
                outer.addWidget(main)
                parts.append(entry.label)
                if entry.qualifier:
                    sub = QLabel(entry.qualifier)
                    sub.setStyleSheet(
                        "font-size:10px;color:#888;margin-left:8px;"
                    )
                    sub.setWordWrap(True)
                    outer.addWidget(sub)
                    parts.append(entry.qualifier)
            self._entries_text_cache = " ".join(parts)
        else:
            msg = empty_message or "(none yet)"
            empty = QLabel(msg)
            empty.setStyleSheet("font-size:11px;color:#aaa;font-style:italic;")
            empty.setWordWrap(True)
            outer.addWidget(empty)
            self._entries_text_cache = msg

        add = QPushButton("+ Add")
        add.setFlat(True)
        add.setStyleSheet(
            "QPushButton{color:#666;text-align:left;border:0;padding:0;font-size:11px;}"
            "QPushButton:hover{color:#d97757;}"
        )
        add.clicked.connect(self.add_clicked.emit)
        outer.addWidget(add)

    def entries_text(self) -> str:
        return self._entries_text_cache

    def chips_text(self) -> str:
        return self._chips_text_cache

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(ev)
