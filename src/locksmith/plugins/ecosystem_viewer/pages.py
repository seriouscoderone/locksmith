# -*- encoding: utf-8 -*-
"""
locksmith.plugins.ecosystem_viewer.pages module

Stages 1-2 viewer pages.

EcosystemViewerPage (stage 1) lists every schema and known issuer AID in
the wallet with their domain-layer classifications from `locksmith.acdc.inspector`.
SchemaDetailPage (stage 2) renders the full inspector output for a single
schema and supports intra-plugin navigation between linked schemas via the
edge-target click-through.

Subsequent commits add ecosystem grouping UI, the directed graph view, etc.
"""
from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from keri import help

from locksmith.acdc import inspect_acdc_schema
from locksmith.ui import colors

logger = help.ogler.getLogger(__name__)

# Page keys registered with VaultPage's content stack. Owned by this plugin.
PAGE_KEY_OVERVIEW = "ecosystem_viewer"
PAGE_KEY_SCHEMA_DETAIL = "ecosystem_viewer.schema_detail"


class EcosystemViewerPage(QWidget):
    """List view: every schema + every known AID + their inspector classifications."""

    show_schema_detail_requested = Signal(str)  # emits schema SAID

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
            "QFrame:hover { background-color: #F0F3FA; }"
        )
        row.setCursor(Qt.CursorShape.PointingHandCursor)
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

        # Click anywhere on the row navigates to the detail page
        said = i.schema_said
        row.mousePressEvent = lambda _event, s=said: self.show_schema_detail_requested.emit(s)

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


class SchemaDetailPage(QWidget):
    """Per-schema deep-inspect view. Renders inspector output + linked schemas."""

    back_requested = Signal()
    show_schema_detail_requested = Signal(str)  # for clicking edge target schemas

    def __init__(self, app: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self.app = app
        self._current_said: str | None = None

        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(colors.BACKGROUND_CONTENT))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Top bar with back button
        bar = QHBoxLayout()
        bar.setContentsMargins(20, 12, 20, 0)
        back = QLabel('<a href="#back" style="color:#3a5fff;text-decoration:none;">‹ Back to overview</a>')
        back.setOpenExternalLinks(False)
        back.linkActivated.connect(lambda _: self.back_requested.emit())
        back.setStyleSheet("font-size: 13px;")
        bar.addWidget(back)
        bar.addStretch()
        outer.addLayout(bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"background-color: {colors.BACKGROUND_CONTENT}; border: none;")
        scroll.viewport().setStyleSheet(f"background-color: {colors.BACKGROUND_CONTENT};")

        self._content = QWidget()
        self._content.setObjectName("schemaDetailContent")
        self._content.setStyleSheet(
            f"#schemaDetailContent {{ background-color: {colors.BACKGROUND_CONTENT}; }}"
        )
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(20, 16, 20, 30)
        self._content_layout.setSpacing(16)
        self._content_layout.addStretch()
        scroll.setWidget(self._content)
        outer.addWidget(scroll)

    def show_schema(self, schema_said: str) -> None:
        """Load and render the schema with the given SAID. Called by the plugin."""
        self._current_said = schema_said
        self._refresh()

    def _refresh(self) -> None:
        # Clear all widgets in front of the layout's trailing stretch.
        # __init__ leaves the stretch as the sole item; section widgets are
        # then inserted at indices 0..N, pushing the stretch to last position.
        # The `> 1` guard preserves the stretch.
        while self._content_layout.count() > 1:
            item = self._content_layout.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.deleteLater()

        if self._current_said is None:
            self._content_layout.insertWidget(0, QLabel("(no schema selected)"))
            return

        vault = getattr(self.app, "vault", None)
        if vault is None or vault.hby is None:
            self._content_layout.insertWidget(0, QLabel("Vault not open."))
            return

        schemer = vault.hby.db.schema.get(keys=(self._current_said,))
        if schemer is None:
            msg = QLabel(
                f"Schema <code>{self._current_said}</code> not found in this wallet. "
                "It may have been deleted, or never resolved here. "
                "Add it via Credentials → Schemas → Add."
            )
            msg.setWordWrap(True)
            msg.setTextFormat(Qt.TextFormat.RichText)
            self._content_layout.insertWidget(0, msg)
            return

        inspection = inspect_acdc_schema(schemer.sed)
        # Render in the order: header, identity, requirements, sections, edges, raw JSON
        self._content_layout.insertWidget(0, self._build_header(inspection))
        self._content_layout.insertWidget(1, self._build_identity_section(inspection))
        self._content_layout.insertWidget(2, self._build_requirements_section(inspection))
        self._content_layout.insertWidget(3, self._build_sections_section(inspection))
        self._content_layout.insertWidget(4, self._build_edges_section(inspection, vault))
        self._content_layout.insertWidget(5, self._build_raw_json_section(inspection))

    def _build_header(self, i: Any) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        title = QLabel(
            f"{i.title or '(untitled schema)'}"
            + (f"  <span style='color:{colors.TEXT_SECONDARY};font-size:14px;'>v{i.schema_version}</span>"
               if i.schema_version else "")
        )
        title.setStyleSheet("font-size: 22px; font-weight: 600;")
        layout.addWidget(title)
        if i.credential_type:
            ct = QLabel(f"<span style='color:{colors.TEXT_SECONDARY};font-size:12px;'>credentialType: <code>{i.credential_type}</code></span>")
            layout.addWidget(ct)
        if i.description:
            desc = QLabel(i.description)
            desc.setWordWrap(True)
            desc.setStyleSheet(f"color: {colors.TEXT_DARK}; font-size: 13px; margin-top: 6px;")
            layout.addWidget(desc)
        return wrapper

    def _build_identity_section(self, i: Any) -> QWidget:
        frame = self._card("Identity")
        layout: QVBoxLayout = frame.layout()  # type: ignore[assignment]
        meta = QLabel(
            f"<span style='color:{colors.TEXT_SECONDARY}'>Schema SAID:</span> "
            f"<code>{i.schema_said}</code>"
        )
        meta.setStyleSheet("font-size: 12px;")
        meta.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(meta)
        return frame

    def _build_requirements_section(self, i: Any) -> QWidget:
        frame = self._card("Required ACDC variant")
        layout: QVBoxLayout = frame.layout()  # type: ignore[assignment]
        rows = [
            ("Targeted (a.i required)", i.requires_targeted),
            ("Private (u required)", i.requires_nonce),
            ("Has registry (rd/ri required)", i.requires_registry),
            ("Has message type (t required)", i.requires_message_type),
        ]
        for label, value in rows:
            txt = QLabel(f"<b>{'yes' if value else 'no':>4}</b> · {label}")
            txt.setStyleSheet("font-size: 12px;")
            layout.addWidget(txt)
        return frame

    def _build_sections_section(self, i: Any) -> QWidget:
        frame = self._card("Declared sections")
        layout: QVBoxLayout = frame.layout()  # type: ignore[assignment]
        sd = i.declared_sections
        rows = [
            ("a (attribute)", sd.declares_attribute, sd.attribute_required),
            ("A (aggregate, selective disclosure)", sd.declares_aggregate, sd.aggregate_required),
            ("e (edges)", sd.declares_edges, sd.edges_required),
            ("r (rules)", sd.declares_rules, sd.rules_required),
        ]
        for name, declared, required in rows:
            mark = "✓" if declared else "—"
            req = " (required)" if required else ""
            txt = QLabel(f"<code>{mark}</code> {name}{req}")
            txt.setStyleSheet("font-size: 12px;")
            layout.addWidget(txt)
        if i.rule_keys_declared:
            keys = QLabel(
                f"<span style='color:{colors.TEXT_SECONDARY}'>rule keys:</span> "
                + ", ".join(f"<code>{k}</code>" for k in i.rule_keys_declared)
            )
            keys.setStyleSheet("font-size: 12px; margin-top: 6px;")
            layout.addWidget(keys)
        return frame

    def _build_edges_section(self, i: Any, vault: Any) -> QWidget:
        frame = self._card("Edge requirements")
        layout: QVBoxLayout = frame.layout()  # type: ignore[assignment]
        if not i.edge_requirements:
            empty = QLabel("(no edges declared)")
            empty.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px; font-style: italic;")
            layout.addWidget(empty)
            return frame
        for edge in i.edge_requirements:
            row = QWidget()
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(10, 8, 10, 8)
            row_layout.setSpacing(2)
            row.setStyleSheet("QWidget { background: #F8F9FF; border-radius: 4px; }")
            head = QLabel(f"<b>{edge.name}</b>")
            head.setStyleSheet("font-size: 13px;")
            row_layout.addWidget(head)
            if edge.description and edge.description != edge.name:
                desc = QLabel(edge.description)
                desc.setWordWrap(True)
                desc.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px;")
                row_layout.addWidget(desc)
            if edge.target_schema_said:
                # Make the target schema link clickable if it's known to this wallet
                known = vault.hby.db.schema.get(keys=(edge.target_schema_said,)) is not None
                if known:
                    link = QLabel(
                        f"target schema: <a href=\"#nav\" style=\"color:#3a5fff;text-decoration:none;\">"
                        f"<code>{edge.target_schema_said}</code></a>"
                    )
                    link.setOpenExternalLinks(False)
                    link.linkActivated.connect(
                        lambda _l, said=edge.target_schema_said: self.show_schema_detail_requested.emit(said)
                    )
                else:
                    link = QLabel(
                        f"target schema: <code>{edge.target_schema_said}</code> "
                        f"<span style='color:{colors.TEXT_SECONDARY}'>(not in this wallet)</span>"
                    )
                link.setWordWrap(True)
                link.setStyleSheet("font-size: 12px;")
                link.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.LinksAccessibleByMouse)
                row_layout.addWidget(link)
            if edge.operator_locked:
                op = QLabel(f"operator locked: <b>{edge.operator_locked}</b>")
                op.setStyleSheet("font-size: 12px;")
                row_layout.addWidget(op)
            elif edge.operator_constraint:
                op = QLabel(f"operator ∈ {{{', '.join(edge.operator_constraint)}}}")
                op.setStyleSheet("font-size: 12px;")
                row_layout.addWidget(op)
            else:
                op = QLabel(
                    "operator: (none constrained — defaults to <b>I2I</b> for targeted ACDCs)"
                )
                op.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px;")
                row_layout.addWidget(op)
            layout.addWidget(row)
        return frame

    def _build_raw_json_section(self, i: Any) -> QWidget:
        frame = self._card("Raw schema (JSON)")
        layout: QVBoxLayout = frame.layout()  # type: ignore[assignment]
        text = QPlainTextEdit()
        text.setPlainText(json.dumps(i.raw, indent=2))
        text.setReadOnly(True)
        text.setStyleSheet(
            "QPlainTextEdit { font-family: monospace; font-size: 11px; background: #FAFAFA; border: 1px solid #E0E3EA; }"
        )
        text.setMaximumHeight(300)
        layout.addWidget(text)
        return frame

    def _card(self, title: str) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { background-color: white; border: 1px solid #E0E3EA; border-radius: 8px; }"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(title_label)
        return frame
