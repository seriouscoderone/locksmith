# -*- encoding: utf-8 -*-
"""TemplatesBrowserPage: entry surface for the Designer.

Lists every template the workspace knows about as cards in a 2-up grid.
Click a card → emit template_open_requested(ref).

Card content uses canonical meta-schema field names:
  header.display_name (title), role.display_name (subtitle), role.kind
  (chip), credentials.imports/exports counts, commands/workflows counts.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)

from locksmith.plugins.designer.store import TemplateRef, TemplateStore


_ROLE_KIND_COLOR: dict[str, str] = {
    "government": "#0ABFB0",
    "organization": "#0ABFB0",
    "individual": "#D97757",
    "system": "#888888",
    "device": "#888888",
    "agent": "#A36AE6",
}


class _TemplateCard(QFrame):
    clicked = Signal()

    def __init__(self, ref: TemplateRef, doc: dict[str, Any], parent=None):
        super().__init__(parent=parent)
        self._ref = ref
        self.setObjectName("card")
        self.setStyleSheet(
            "#card{background:#fff;border:1px solid #e0e3ea;border-radius:8px;}"
            "#card:hover{border:1px solid #d97757;}"
        )
        # Don't expand vertically — the card sizes to its content, the
        # grid pushes extra space into a trailing stretch row.
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self._build(doc)

    @property
    def ref(self) -> TemplateRef:
        return self._ref

    @property
    def title(self) -> str:
        return self._title

    def _build(self, doc: dict[str, Any]) -> None:
        header = doc.get("header", {})
        role = doc.get("role", {})
        self._title = header.get("display_name", "(untitled)")
        kind = role.get("kind", "")
        role_name = role.get("display_name", "")
        color = _ROLE_KIND_COLOR.get(kind, "#888888")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(8)

        top = QHBoxLayout()
        swatch = QLabel()
        swatch.setFixedSize(44, 44)
        swatch.setStyleSheet(f"background:{color};border-radius:6px;")
        top.addWidget(swatch)

        text = QVBoxLayout()
        title_row = QHBoxLayout()
        title = QLabel(self._title)
        title.setStyleSheet("font-size:15px;font-weight:600;color:#1A1C20;")
        title_row.addWidget(title)
        version = QLabel(f"v{header.get('version', '0.0')}")
        version.setStyleSheet(
            "color:#888;background:#f6f7f9;padding:2px 7px;border-radius:8px;"
            "font-size:10px;"
        )
        title_row.addWidget(version)
        title_row.addStretch(1)
        text.addLayout(title_row)

        subtitle = QLabel(
            f"<span style='color:{color};font-weight:600;'>{role_name}</span>"
            f" · {kind}"
        )
        subtitle.setStyleSheet("font-size:11px;color:#666;")
        text.addWidget(subtitle)
        top.addLayout(text, 1)
        outer.addLayout(top)

        desc = QLabel(header.get("description", ""))
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size:12px;color:#444;")
        outer.addWidget(desc)

        counts = (
            f"{len(doc.get('credentials', {}).get('imports', []))} imports · "
            f"{len(doc.get('credentials', {}).get('exports', []))} exports · "
            f"{len(doc.get('commands', []))} commands · "
            f"{len(doc.get('workflows', []))} workflows"
        )
        footer = QHBoxLayout()
        ftext = QLabel(counts)
        ftext.setStyleSheet("font-size:10px;color:#888;")
        footer.addWidget(ftext)
        footer.addStretch(1)
        if self._ref.kind == "draft":
            badge = QLabel("DRAFT")
        else:
            said = self._ref.said or ""
            badge = QLabel(f"{said[:4]}…{said[-4:]}" if len(said) >= 8 else said)
        badge.setStyleSheet("font-size:9px;color:#aaa;font-family:monospace;")
        footer.addWidget(badge)
        outer.addLayout(footer)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(ev)


class TemplatesBrowserPage(QWidget):
    template_open_requested = Signal(object)  # TemplateRef
    new_template_requested = Signal()
    import_file_requested = Signal()

    def __init__(self, *, store: TemplateStore, parent=None):
        super().__init__(parent=parent)
        self._store = store
        self._cards: list[_TemplateCard] = []
        self._is_empty: bool = True
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        toolbar = QFrame()
        toolbar.setStyleSheet("background:#fff;border-bottom:1px solid #e0e3ea;")
        toolbar_lay = QHBoxLayout(toolbar)
        toolbar_lay.setContentsMargins(20, 14, 20, 14)
        title = QLabel("Micro-App Templates")
        title.setStyleSheet("font-size:18px;font-weight:600;color:#1A1C20;")
        toolbar_lay.addWidget(title)
        toolbar_lay.addStretch(1)

        btn_import_file = QPushButton("⬇ Import file")
        btn_import_file.clicked.connect(self.import_file_requested.emit)
        btn_import_oobi = QPushButton("🌐 Import via OOBI")
        btn_import_oobi.setEnabled(False)
        btn_import_oobi.setToolTip("Coming in a future release")
        btn_new = QPushButton("+ New template")
        btn_new.setStyleSheet(
            "background:#d97757;color:#fff;font-weight:600;"
            "padding:7px 14px;border-radius:4px;"
        )
        btn_new.clicked.connect(self.new_template_requested.emit)
        for b in (btn_import_file, btn_import_oobi, btn_new):
            toolbar_lay.addWidget(b)
        root.addWidget(toolbar)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("border:0;background:#f6f7f9;")
        self._grid_host = QWidget()
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(20, 20, 20, 20)
        self._grid.setSpacing(14)
        self._empty_label = QLabel(
            "No templates yet. Click '+ New template' to author your first one."
        )
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setStyleSheet("color:#888;font-size:14px;padding:60px;")
        self._grid.addWidget(self._empty_label, 0, 0)
        self._scroll.setWidget(self._grid_host)
        root.addWidget(self._scroll, 1)

    def refresh(self) -> None:
        for c in self._cards:
            c.setParent(None)
            c.deleteLater()
        self._cards = []
        # Clear every row stretch the previous refresh set, so cards in a
        # new (potentially smaller) layout don't carry leftover stretchy
        # rows from a bigger one.
        for r in range(self._grid.rowCount()):
            self._grid.setRowStretch(r, 0)
        refs = self._store.list_templates()
        self._is_empty = len(refs) == 0
        self._empty_label.setVisible(self._is_empty)
        max_row = 0
        for i, ref in enumerate(refs):
            doc, _meta = self._store.load(ref)
            card = _TemplateCard(ref=ref, doc=doc)
            card.clicked.connect(
                lambda r=ref: self.template_open_requested.emit(r)
            )
            row, col = divmod(i, 2)
            self._grid.addWidget(card, row, col)
            self._cards.append(card)
            max_row = max(max_row, row)
        # Trailing stretch row absorbs all extra vertical space so cards
        # render at their natural height instead of stretching to fill.
        self._grid.setRowStretch(max_row + 1, 1)

    def card_count(self) -> int:
        return len(self._cards)

    def card_titles(self) -> list[str]:
        return [c.title for c in self._cards]

    def empty_state_visible(self) -> bool:
        return self._is_empty

    def click_first_card(self) -> None:
        if self._cards:
            self._cards[0].clicked.emit()
