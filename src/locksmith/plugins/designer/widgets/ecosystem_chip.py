# -*- encoding: utf-8 -*-
"""Small rounded chip widgets used in templates-browser cards and Overview."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel


_CROSS_TEMPLATE_PREFIX: dict[str, str] = {
    "pairs_with":  "↔ pairs with",
    "forked_from": "↪ forked from",
}


class EcosystemChip(QLabel):
    def __init__(self, tag: str, parent=None):
        super().__init__(tag, parent=parent)
        self.setStyleSheet(
            "background:#f0f2f5;color:#444;border-radius:9px;"
            "padding:2px 9px;font-size:11px;"
        )


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
