# -*- encoding: utf-8 -*-
"""Small rounded chip widgets used in templates-browser cards and Overview.

EcosystemChip emits `clicked(tag)` when the user presses on it and
accepts the mouse event so it doesn't bubble up to a parent card's
drill-in handler. Consumers that don't want the click-to-filter
behavior simply don't connect the signal.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel


_CROSS_TEMPLATE_PREFIX: dict[str, str] = {
    "pairs_with":  "↔ pairs with",
    "forked_from": "↪ forked from",
}


class EcosystemChip(QLabel):
    clicked = Signal(str)

    def __init__(self, tag: str, parent=None):
        super().__init__(tag, parent=parent)
        self._tag = tag
        # Hand cursor + hover-state QSS so the user can tell their
        # click will hit the chip (filter) and not the card body
        # (drill-in). ``WA_Hover`` is required for QLabel ``:hover``
        # selectors to fire — Qt doesn't track mouse-over on QLabel
        # without it.
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        # Matches the rule-type chip visual weight (bold + colored text
        # on light-grey pill) so "I'M BOUND BY" and "ECOSYSTEM AFFINITY"
        # read as the same chip family. Teal is the taxonomic accent
        # for tag-style chips; rule-type chips keep their per-type
        # semantic colors.
        self.setStyleSheet(
            "EcosystemChip{background:#f6f7f9;color:#0e9488;"
            "border-radius:9px;padding:2px 8px;font-size:11px;"
            "font-weight:600;}"
            "EcosystemChip:hover{background:#e0f7f4;color:#0ABFB0;}"
        )

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.clicked.emit(self._tag)
            ev.accept()
            return
        super().mousePressEvent(ev)


class CrossTemplateChip(QLabel):
    def __init__(self, *, kind: str, target: str, parent=None):
        super().__init__(parent=parent)
        prefix = _CROSS_TEMPLATE_PREFIX.get(kind)
        if prefix is None:
            text = f"· {target}"
        else:
            text = f"{prefix} {target}"
        self.setText(text)
        self.setStyleSheet(
            "background:#fdf3e7;color:#a5641a;border-radius:9px;"
            "padding:2px 9px;font-size:11px;"
        )
