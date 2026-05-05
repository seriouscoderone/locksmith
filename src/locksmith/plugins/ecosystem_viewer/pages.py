# -*- encoding: utf-8 -*-
"""
locksmith.plugins.ecosystem_viewer.pages module

Stage-1 viewer page: lists every schema and known issuer AID in the wallet
with their domain-layer classifications from `locksmith.acdc.inspector`.

This is the foundation page the rest of the roadmap builds on. Subsequent
commits add per-schema detail, ecosystem grouping UI, the directed graph
view, etc.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from keri import help

from locksmith.acdc import inspect_acdc_schema
from locksmith.ui import colors

logger = help.ogler.getLogger(__name__)


class EcosystemViewerPage(QWidget):
    """List view: every schema + every known AID + their inspector classifications."""

    def __init__(self, app: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self.app = app

        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(colors.BACKGROUND_CONTENT))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"background-color: {colors.BACKGROUND_CONTENT}; border: none;")
        scroll.viewport().setStyleSheet(f"background-color: {colors.BACKGROUND_CONTENT};")

        self._content = QWidget()
        self._content.setObjectName("ecosystemViewerContent")
        self._content.setStyleSheet(
            f"#ecosystemViewerContent {{ background-color: {colors.BACKGROUND_CONTENT}; }}"
        )
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(30, 30, 30, 30)
        self._content_layout.setSpacing(18)

        self._build_static_header()
        # Sections are rebuilt on each on_show() so stored references aren't needed.
        self._sections_anchor_index = self._content_layout.count()

        self._content_layout.addStretch()
        scroll.setWidget(self._content)
        outer_layout.addWidget(scroll)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_show(self) -> None:
        """Called by VaultPage navigation; rebuild from current wallet state."""
        self._refresh()

    def _refresh(self) -> None:
        # Drop any previously rendered sections (everything after the header,
        # before the trailing stretch).
        while self._content_layout.count() > self._sections_anchor_index + 1:
            item = self._content_layout.takeAt(self._sections_anchor_index)
            widget = item.widget() if item else None
            if widget is not None:
                widget.deleteLater()

        vault = getattr(self.app, "vault", None)
        if vault is None or vault.hby is None:
            empty = self._build_status_message("No vault open. Unlock a vault to begin exploring.")
            self._content_layout.insertWidget(self._sections_anchor_index, empty)
            return

        schema_section = self._build_schema_section(vault)
        self._content_layout.insertWidget(self._sections_anchor_index, schema_section)

        contacts_section = self._build_contacts_section(vault)
        self._content_layout.insertWidget(self._sections_anchor_index + 1, contacts_section)

    # ------------------------------------------------------------------
    # Static header
    # ------------------------------------------------------------------

    def _build_static_header(self) -> None:
        title = QLabel("Ecosystem Viewer")
        title.setStyleSheet("font-size: 22px; font-weight: 600;")
        self._content_layout.addWidget(title)

        intro = QLabel(
            "Domain-layer view of everything this wallet currently knows. "
            "Schemas come from `vault.hby.db.schema` (resolved via OOBI or imported). "
            "Issuer AIDs come from contacts (`vault.org`). Each is classified using "
            "the ACDC spec primitives — variant, targeting, disclosure tier, edge "
            "requirements — via `locksmith.acdc.inspector`. See the plugin README for "
            "the full vision and roadmap."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 13px;")
        self._content_layout.addWidget(intro)

    # ------------------------------------------------------------------
    # Schemas
    # ------------------------------------------------------------------

    def _build_schema_section(self, vault: Any) -> QWidget:
        section = self._build_card(title="Known schemas")
        layout: QVBoxLayout = section.layout()  # type: ignore[assignment]

        try:
            schemas = list(vault.hby.db.schema.getItemIter())
        except Exception:
            logger.exception("Failed to enumerate schemas")
            layout.addWidget(self._build_status_message("Error enumerating schemas (see logs)."))
            return section

        if not schemas:
            layout.addWidget(self._build_status_message(
                "No schemas in this wallet yet. Add one via Credentials → Schemas → Add."
            ))
            return section

        for (said,), schemer in schemas:
            try:
                inspection = inspect_acdc_schema(schemer.sed)
                layout.addWidget(self._build_schema_row(inspection))
            except Exception:
                logger.exception(f"Failed to inspect schema {said}")
                layout.addWidget(self._build_status_message(
                    f"Failed to classify schema {said[:20]}… (see logs)."
                ))

        return section

    def _build_schema_row(self, i: Any) -> QWidget:
        row = QFrame()
        row.setStyleSheet(
            "QFrame { background-color: white; border: 1px solid #E0E3EA; border-radius: 6px; }"
        )
        rl = QVBoxLayout(row)
        rl.setContentsMargins(14, 12, 14, 12)
        rl.setSpacing(4)

        title = QLabel(
            f"<b>{i.title or '(untitled schema)'}</b>"
            + (f" v{i.schema_version}" if i.schema_version else "")
        )
        title.setStyleSheet("font-size: 14px;")
        rl.addWidget(title)

        if i.description:
            desc = QLabel(i.description)
            desc.setWordWrap(True)
            desc.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px;")
            rl.addWidget(desc)

        meta = QLabel(
            f"<span style='color:{colors.TEXT_SECONDARY}'>SAID:</span> "
            f"<code>{i.schema_said}</code>"
        )
        meta.setStyleSheet("font-size: 11px;")
        meta.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        rl.addWidget(meta)

        # Domain classifications row
        chips: list[str] = []
        if i.requires_targeted:
            chips.append("targeted")
        if i.requires_nonce:
            chips.append("private (requires u)")
        if i.requires_registry:
            chips.append("requires registry")
        if i.declared_sections.declares_aggregate:
            chips.append("supports selective disclosure")
        if i.edge_requirements:
            chips.append(f"{len(i.edge_requirements)} edge requirement(s)")

        if chips:
            class_label = QLabel(" · ".join(f"<b>{c}</b>" for c in chips))
            class_label.setWordWrap(True)
            class_label.setStyleSheet(f"color: {colors.TEXT_DARK}; font-size: 12px;")
            rl.addWidget(class_label)

        for edge in i.edge_requirements:
            edge_text = f"&nbsp;&nbsp;↳ edge <b>{edge.name}</b>"
            if edge.target_schema_said:
                edge_text += f" → schema <code>{edge.target_schema_said[:20]}…</code>"
            if edge.operator_locked:
                edge_text += f" (op locked: {edge.operator_locked})"
            elif edge.operator_constraint:
                edge_text += f" (op ∈ {{{', '.join(edge.operator_constraint)}}})"
            edge_label = QLabel(edge_text)
            edge_label.setWordWrap(True)
            edge_label.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px;")
            rl.addWidget(edge_label)

        return row

    # ------------------------------------------------------------------
    # Contacts (issuer AIDs)
    # ------------------------------------------------------------------

    def _build_contacts_section(self, vault: Any) -> QWidget:
        section = self._build_card(title="Known issuer AIDs (contacts)")
        layout: QVBoxLayout = section.layout()  # type: ignore[assignment]

        try:
            contacts = list(vault.org.list())
        except Exception:
            logger.exception("Failed to enumerate contacts")
            layout.addWidget(self._build_status_message("Error enumerating contacts (see logs)."))
            return section

        if not contacts:
            layout.addWidget(self._build_status_message(
                "No remote contacts yet. Add one via Contacts → Add (OOBI or File)."
            ))
            return section

        for c in contacts:
            layout.addWidget(self._build_contact_row(c, vault))

        return section

    def _build_contact_row(self, contact: dict[str, Any], vault: Any) -> QWidget:
        row = QFrame()
        row.setStyleSheet(
            "QFrame { background-color: white; border: 1px solid #E0E3EA; border-radius: 6px; }"
        )
        rl = QVBoxLayout(row)
        rl.setContentsMargins(14, 12, 14, 12)
        rl.setSpacing(4)

        alias = contact.get("alias") or "(no alias)"
        pre = contact.get("id", "")

        title = QLabel(f"<b>{alias}</b>")
        title.setStyleSheet("font-size: 14px;")
        rl.addWidget(title)

        # Domain classification: transferable vs non-transferable (witness role hint)
        kever = vault.hby.kevers.get(pre) if pre else None
        chips: list[str] = []
        if kever is not None:
            chips.append("transferable" if kever.transferable else "non-transferable (witness-shaped)")
            chips.append(f"sn {kever.sn}")
            if kever.wits:
                chips.append(f"{len(kever.wits)} witness(es) · TOAD {kever.toader.num}")
        else:
            chips.append("KEL not in kevers (legacy contact?)")

        meta = QLabel(
            f"<span style='color:{colors.TEXT_SECONDARY}'>AID:</span> <code>{pre}</code>"
        )
        meta.setStyleSheet("font-size: 11px;")
        meta.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        rl.addWidget(meta)

        if chips:
            class_label = QLabel(" · ".join(f"<b>{c}</b>" for c in chips))
            class_label.setWordWrap(True)
            class_label.setStyleSheet(f"color: {colors.TEXT_DARK}; font-size: 12px;")
            rl.addWidget(class_label)

        oobi = contact.get("oobi")
        if oobi:
            oobi_label = QLabel(
                f"<span style='color:{colors.TEXT_SECONDARY}'>OOBI:</span> "
                f"<code>{oobi}</code>"
            )
            oobi_label.setWordWrap(True)
            oobi_label.setStyleSheet("font-size: 11px;")
            oobi_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            rl.addWidget(oobi_label)

        return row

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_card(self, title: str) -> QWidget:
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { background-color: white; border: 1px solid #E0E3EA; border-radius: 8px; }"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(title_label)
        return frame

    def _build_status_message(self, text: str) -> QWidget:
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        msg = QLabel(text)
        msg.setWordWrap(True)
        msg.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 13px; font-style: italic;")
        layout.addWidget(msg)
        return wrapper
