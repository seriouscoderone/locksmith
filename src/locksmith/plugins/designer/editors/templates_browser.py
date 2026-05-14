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

    def __init__(self, ref: TemplateRef, doc: dict[str, Any],
                 meta: dict[str, Any] | None = None, parent=None):
        super().__init__(parent=parent)
        self._ref = ref
        self._meta = meta or {}
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
        from locksmith.plugins.designer.widgets.role_icon_badge import (
            RoleIconBadge,
        )
        from locksmith.plugins.designer.widgets.validation_pill import (
            ValidationPill,
        )
        from locksmith.plugins.designer.widgets.ecosystem_chip import (
            CrossTemplateChip, EcosystemChip,
        )

        header = doc.get("header", {})
        role = doc.get("role", {})
        self._title = header.get("display_name", "(untitled)")
        kind = role.get("kind", "")
        meta = self._meta

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(8)

        top = QHBoxLayout()
        self.role_badge = RoleIconBadge(kind=kind, size=44)
        top.addWidget(self.role_badge)

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
        self.validation_pill = ValidationPill(
            error_count=meta.get("error_count", 0),
            warning_count=meta.get("warning_count", 0),
        )
        title_row.addWidget(self.validation_pill)
        text.addLayout(title_row)

        color = _ROLE_KIND_COLOR.get(kind, "#888888")
        subtitle = QLabel(
            f"<span style='color:{color};font-weight:600;'>{role.get('id', '')}</span>"
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

        self.ecosystem_chips: list[QLabel] = []
        chip_row = QHBoxLayout()
        chip_row.setSpacing(6)
        for tag in meta.get("ecosystem_tags", []):
            chip = EcosystemChip(tag)
            self.ecosystem_chips.append(chip)
            chip_row.addWidget(chip)
        forked_from = (header.get("forked_from", {}) or {}).get("template_said")
        if forked_from:
            short = (forked_from[:4] + "…" + forked_from[-6:]
                     if len(forked_from) > 12 else forked_from)
            chip_row.addWidget(
                CrossTemplateChip(kind="forked_from", target=short)
            )
        chip_row.addStretch(1)
        outer.addLayout(chip_row)

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
        self.modified_label = QLabel(self._format_modified(meta.get("modified_at")))
        self.modified_label.setStyleSheet("font-size:10px;color:#888;")
        footer.addWidget(self.modified_label)
        if self._ref.kind == "draft":
            badge = QLabel("DRAFT")
        else:
            said = self._ref.said or ""
            badge = QLabel(f"{said[:4]}…{said[-4:]}" if len(said) >= 8 else said)
        badge.setStyleSheet("font-size:9px;color:#aaa;font-family:monospace;")
        footer.addWidget(badge)
        outer.addLayout(footer)

    @staticmethod
    def _format_modified(ts: str | None) -> str:
        if not ts:
            return "Modified just now"
        try:
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            delta = now - dt
            secs = int(delta.total_seconds())
            if secs < 60:
                return f"Modified {secs}s ago"
            if secs < 3600:
                return f"Modified {secs // 60}m ago"
            if secs < 86400:
                return f"Modified {secs // 3600}h ago"
            return f"Modified {secs // 86400}d ago"
        except (ValueError, TypeError):
            return "Modified just now"

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
        toolbar_lay = QVBoxLayout(toolbar)
        toolbar_lay.setContentsMargins(20, 14, 20, 6)
        toolbar_lay.setSpacing(2)

        top_row = QHBoxLayout()
        title_block = QVBoxLayout()
        title_block.setSpacing(0)
        title = QLabel("Micro-App Templates")
        title.setStyleSheet("font-size:18px;font-weight:600;color:#1A1C20;")
        title_block.addWidget(title)
        self.summary_label = QLabel("0 templates")
        self.summary_label.setStyleSheet("font-size:11px;color:#888;")
        title_block.addWidget(self.summary_label)
        top_row.addLayout(title_block)
        top_row.addStretch(1)

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
            top_row.addWidget(b)
        toolbar_lay.addLayout(top_row)

        # Filter strip — chips are display-only in Phase 1.
        self._filter_strip = QHBoxLayout()
        self._filter_strip.setContentsMargins(0, 6, 0, 8)
        self._filter_strip.setSpacing(8)
        toolbar_lay.addLayout(self._filter_strip)
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
        for r in range(self._grid.rowCount()):
            self._grid.setRowStretch(r, 0)
        refs = self._store.list_templates()
        loaded: list[tuple] = []
        for ref in refs:
            doc, meta = self._store.load(ref)
            loaded.append((ref, doc, meta))
        all_n = len(loaded)
        valid_n = sum(1 for _r, _d, m in loaded
                      if m.get("schema_validated", True))
        draft_n = sum(1 for r, _d, _m in loaded if r.kind == "draft")
        plural = "templates" if all_n != 1 else "template"
        d_plural = "drafts" if draft_n != 1 else "draft"
        self.summary_label.setText(
            f"{all_n} {plural} · {valid_n} valid · {draft_n} {d_plural}"
        )
        self._rebuild_filter_strip(loaded)
        self._is_empty = all_n == 0
        self._empty_label.setVisible(self._is_empty)
        max_row = 0
        for i, (ref, doc, meta) in enumerate(loaded):
            card = _TemplateCard(ref=ref, doc=doc, meta=meta)
            card.clicked.connect(
                lambda r=ref: self.template_open_requested.emit(r)
            )
            row, col = divmod(i, 2)
            self._grid.addWidget(card, row, col)
            self._cards.append(card)
            max_row = max(max_row, row)
        self._grid.setRowStretch(max_row + 1, 1)

    def _rebuild_filter_strip(self, refs_and_docs: list[tuple]) -> None:
        while self._filter_strip.count():
            old = self._filter_strip.takeAt(0)
            w = old.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        all_n = len(refs_and_docs)
        valid_n = sum(1 for _r, _d, m in refs_and_docs
                      if m.get("schema_validated", True))
        draft_n = sum(1 for r, _d, _m in refs_and_docs if r.kind == "draft")
        role_kinds: dict[str, int] = {}
        ecosystems: dict[str, int] = {}
        for _r, doc, meta in refs_and_docs:
            k = doc.get("role", {}).get("kind", "")
            if k:
                role_kinds[k] = role_kinds.get(k, 0) + 1
            for tag in meta.get("ecosystem_tags", []):
                ecosystems[tag] = ecosystems.get(tag, 0) + 1

        def add_label(text: str) -> None:
            lbl = QLabel(text)
            lbl.setStyleSheet("font-size:11px;color:#888;")
            self._filter_strip.addWidget(lbl)

        def add_chip(text: str, active: bool = False) -> None:
            lbl = QLabel(text)
            if active:
                lbl.setStyleSheet(
                    "background:#1A1C20;color:#fff;border-radius:9px;"
                    "padding:2px 9px;font-size:11px;font-weight:600;"
                )
            else:
                lbl.setStyleSheet(
                    "background:#f0f2f5;color:#444;border-radius:9px;"
                    "padding:2px 9px;font-size:11px;"
                )
            self._filter_strip.addWidget(lbl)

        add_label("Filter:")
        add_chip(f"All ({all_n})", active=True)
        add_chip(f"Valid ({valid_n})")
        add_chip(f"Draft ({draft_n})")
        add_label("  |  Role kind:")
        for kind, n in sorted(role_kinds.items()):
            add_chip(f"{kind} ({n})")
        add_label("  |  Ecosystem:")
        for tag, n in sorted(ecosystems.items()):
            add_chip(f"{tag} ({n})")
        self._filter_strip.addStretch(1)

    def filter_chips_text(self) -> str:
        parts: list[str] = []
        for i in range(self._filter_strip.count()):
            item = self._filter_strip.itemAt(i)
            w = item.widget() if item is not None else None
            if isinstance(w, QLabel):
                parts.append(w.text())
        return " ".join(parts)

    def card_count(self) -> int:
        return len(self._cards)

    def card_titles(self) -> list[str]:
        return [c.title for c in self._cards]

    def empty_state_visible(self) -> bool:
        return self._is_empty

    def click_first_card(self) -> None:
        if self._cards:
            self._cards[0].clicked.emit()
