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

import html
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from locksmith.plugins.ecosystem_viewer.db import EcosystemBaser

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPalette, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from keri import help

from locksmith.acdc import inspect_acdc_schema
from locksmith.acdc import icons
from locksmith.plugins.ecosystem_viewer.db import AnnotationKind
from locksmith.plugins.ecosystem_viewer.widgets import (
    DisclosureTierWidget,
    SectionFingerprintWidget,
)
from locksmith.ui import colors
from locksmith.ui.toolkit.widgets import LocksmithButton, LocksmithInvertedButton
from locksmith.ui.toolkit.widgets.buttons import LocksmithIconButton

logger = help.ogler.getLogger(__name__)

# Page keys registered with VaultPage's content stack. Owned by this plugin.
PAGE_KEY_OVERVIEW = "ecosystem_viewer"
PAGE_KEY_SCHEMA_DETAIL = "ecosystem_viewer.schema_detail"
PAGE_KEY_ECOSYSTEM_DETAIL = "ecosystem_viewer.ecosystem_detail"


class EcosystemViewerPage(QWidget):
    """List view: every schema + every known AID + their inspector classifications."""

    show_schema_detail_requested = Signal(str)  # emits schema SAID
    show_ecosystem_detail_requested = Signal(str)  # emits ecosystem name (NEW)
    create_ecosystem_clicked = Signal()             # NEW: from "Create" button

    def __init__(self, app: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self.app = app
        self._db: EcosystemBaser | None = None

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
            "#ecosystemViewerContent QLabel { background: transparent; }"
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

    def set_db(self, db: "EcosystemBaser | None") -> None:
        """Receive (or release) the plugin's EcosystemBaser. Called by plugin lifecycle."""
        self._db = db

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

        ecosystems_section = self._build_ecosystems_section()
        self._content_layout.insertWidget(self._sections_anchor_index, ecosystems_section)

        schema_section = self._build_schema_section(vault)
        self._content_layout.insertWidget(self._sections_anchor_index + 1, schema_section)

        contacts_section = self._build_contacts_section(vault)
        self._content_layout.insertWidget(self._sections_anchor_index + 2, contacts_section)

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
    # Ecosystems
    # ------------------------------------------------------------------

    def _build_ecosystems_section(self) -> QWidget:
        section = self._build_card(title="My ecosystems")
        layout: QVBoxLayout = section.layout()  # type: ignore[assignment]

        # Top row: count + Create button
        header_row = QWidget()
        header_layout = QHBoxLayout(header_row)
        header_layout.setContentsMargins(0, 0, 0, 0)

        if self._db is None:
            ecosystems = []
        else:
            try:
                ecosystems = self._db.list_ecosystems()
            except Exception:
                logger.exception("Failed to list ecosystems")
                ecosystems = []

        count_label = QLabel(f"{len(ecosystems)} ecosystem(s) defined")
        count_label.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px;")
        header_layout.addWidget(count_label)
        header_layout.addStretch()

        create_btn = LocksmithButton("Create ecosystem")
        create_btn.clicked.connect(self.create_ecosystem_clicked.emit)
        header_layout.addWidget(create_btn)

        layout.addWidget(header_row)

        if not ecosystems:
            layout.addWidget(self._build_status_message(
                "No ecosystems yet. Click 'Create ecosystem' to define a grouping of "
                "schemas and issuer AIDs that work together."
            ))
            return section

        for eco in sorted(ecosystems, key=lambda e: e.name):
            layout.addWidget(self._build_ecosystem_row(eco))
        return section

    def _build_ecosystem_row(self, eco: Any) -> QWidget:
        row = QFrame()
        row.setObjectName("evEcosystemRow")
        row.setStyleSheet(
            "QFrame#evEcosystemRow { background-color: white; border: 1px solid #E0E3EA; border-radius: 6px; }"
            "QFrame#evEcosystemRow:hover { background-color: #F0F3FA; }"
            "QFrame#evEcosystemRow QLabel { background: transparent; }"
        )
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        rl = QVBoxLayout(row)
        rl.setContentsMargins(14, 12, 14, 12)
        rl.setSpacing(4)

        title = QLabel(f"<b>{eco.name}</b>")
        title.setStyleSheet("font-size: 14px;")
        rl.addWidget(title)

        if eco.description:
            desc = QLabel(eco.description)
            desc.setWordWrap(True)
            desc.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px;")
            rl.addWidget(desc)

        counts = QLabel(
            f"<span style='color:{colors.TEXT_SECONDARY}'>"
            f"{len(eco.schema_saids)} schema(s) · {len(eco.issuer_aids)} AID(s)</span>"
        )
        counts.setStyleSheet("font-size: 11px;")
        rl.addWidget(counts)

        name = eco.name
        row.mousePressEvent = lambda _e, n=name: self.show_ecosystem_detail_requested.emit(n)
        return row

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
        row.setObjectName("evSchemaRow")
        row.setStyleSheet(
            "QFrame#evSchemaRow { background-color: white; border: 1px solid #E0E3EA; border-radius: 6px; }"
            "QFrame#evSchemaRow:hover { background-color: #F0F3FA; }"
            "QFrame#evSchemaRow QLabel { background: transparent; }"
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
        row.setObjectName("evContactRow")
        row.setStyleSheet(
            "QFrame#evContactRow { background-color: white; border: 1px solid #E0E3EA; border-radius: 6px; }"
            "QFrame#evContactRow QLabel { background: transparent; }"
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
        frame.setObjectName("evCard")
        frame.setStyleSheet(
            "QFrame#evCard { background-color: white; border: 1px solid #E0E3EA; border-radius: 8px; }"
            "QFrame#evCard QLabel { background: transparent; }"
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


class _DeveloperDisclosure(QWidget):
    """Collapsible disclosure widget that holds developer-detail sub-cards (§4.6).

    Usage:
        disc = _DeveloperDisclosure(parent, expanded=False)
        disc.add_section(requirements_card)
        disc.add_section(sections_card)
        disc.add_section(raw_json_card)
        disc.set_expanded(True)
    """

    def __init__(self, parent: QWidget | None = None, *, expanded: bool = False):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Clickable header
        self._header = QLabel()
        self._header.setStyleSheet(
            f"font-size: 13px; color: {colors.TEXT_SECONDARY}; padding: 6px 0px; cursor: pointer;"
        )
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.mousePressEvent = lambda _e: self.set_expanded(not self._expanded)
        outer.addWidget(self._header)

        # Container for the sub-cards
        self._container = QWidget()
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(0, 8, 0, 0)
        self._container_layout.setSpacing(12)
        outer.addWidget(self._container)

        self._expanded = False
        self.set_expanded(expanded)

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        arrow = "▲" if expanded else "▼"
        self._header.setText(
            f"{arrow} Developer details (raw schema, field-level structure, JSON)"
        )
        self._container.setVisible(expanded)

    def add_section(self, widget: QWidget) -> None:
        self._container_layout.addWidget(widget)


class SchemaDetailPage(QWidget):
    """Per-schema deep-inspect view — redesigned per design doc §4 (Phase B3a).

    Public surface (signals + methods) is UNCHANGED from the prior implementation
    so the plugin can connect/disconnect without modification.
    """

    back_requested = Signal()
    show_schema_detail_requested = Signal(str)  # for clicking edge target schemas
    edit_annotation_clicked = Signal(str, str, str)  # (kind, target, target_label)

    def __init__(self, app: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self.app = app
        self._current_said: str | None = None
        self._db: EcosystemBaser | None = None

        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(colors.BACKGROUND_CONTENT))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ------------------------------------------------------------------
        # Top bar: Back link (left) + Developer-mode toggle (right)
        # ------------------------------------------------------------------
        bar_widget = QWidget()
        bar_widget.setObjectName("schemaDetailBackBar")
        bar_widget.setStyleSheet(
            f"#schemaDetailBackBar {{ background-color: {colors.BACKGROUND_CONTENT}; }}"
            "#schemaDetailBackBar QLabel { background: transparent; }"
        )
        bar = QHBoxLayout(bar_widget)
        bar.setContentsMargins(20, 12, 20, 8)

        back = QLabel('<a href="#back" style="color:#3a5fff;text-decoration:none;">‹ Back to overview</a>')
        back.setOpenExternalLinks(False)
        back.linkActivated.connect(lambda _: self.back_requested.emit())
        back.setStyleSheet("font-size: 13px;")
        bar.addWidget(back)
        bar.addStretch()

        # Developer-mode toggle — checkable QToolButton with icon
        self._dev_toggle = QToolButton()
        self._dev_toggle.setCheckable(True)
        self._dev_toggle.setToolTip("Toggle developer details")
        self._dev_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        _dev_px = QPixmap(icons.ICON_DEVELOPER_MODE)
        if not _dev_px.isNull():
            from PySide6.QtGui import QIcon
            self._dev_toggle.setIcon(QIcon(_dev_px.scaled(
                20, 20,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )))
            self._dev_toggle.setIconSize(
                __import__("PySide6.QtCore", fromlist=["QSize"]).QSize(20, 20)
            )
        self._dev_toggle.setStyleSheet(
            f"QToolButton {{ background: transparent; border: 1px solid {colors.BACKGROUND_NEUTRAL};"
            f" border-radius: 4px; padding: 3px; }}"
            f"QToolButton:checked {{ background: {colors.BACKGROUND_NEUTRAL}; }}"
            f"QToolButton:hover {{ background: {colors.BACKGROUND_NEUTRAL}; }}"
        )
        # Read persisted state
        dev_mode = self._read_dev_mode()
        self._dev_toggle.setChecked(dev_mode)
        self._dev_toggle.toggled.connect(self._on_developer_mode_toggled)
        bar.addWidget(self._dev_toggle)

        outer.addWidget(bar_widget)

        # ------------------------------------------------------------------
        # Scroll area + content
        # ------------------------------------------------------------------
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
            "#schemaDetailContent QLabel { background: transparent; }"
        )
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(20, 16, 20, 30)
        self._content_layout.setSpacing(16)
        self._content_layout.addStretch()
        scroll.setWidget(self._content)
        outer.addWidget(scroll)

    # ------------------------------------------------------------------
    # Public interface (UNCHANGED)
    # ------------------------------------------------------------------

    def set_db(self, db: "EcosystemBaser | None") -> None:
        """Receive (or release) the plugin's EcosystemBaser. Called by plugin lifecycle."""
        self._db = db

    @property
    def current_said(self) -> str | None:
        """The schema SAID currently being shown, or None if nothing loaded."""
        return self._current_said

    def show_schema(self, schema_said: str) -> None:
        """Load and render the schema with the given SAID. Called by the plugin."""
        self._current_said = schema_said
        self._refresh()

    # ------------------------------------------------------------------
    # Developer-mode persistence
    # ------------------------------------------------------------------

    def _read_dev_mode(self) -> bool:
        try:
            cfg = getattr(self.app, "config", None)
            if cfg is None:
                return False
            plugin_cfg = cfg.plugin_configs.get("ecosystem_viewer", {})
            return bool(plugin_cfg.get("developer_mode", False))
        except Exception:
            logger.warning("Could not read developer_mode from plugin_configs; defaulting to False")
            return False

    def _on_developer_mode_toggled(self, checked: bool) -> None:
        try:
            cfg = getattr(self.app, "config", None)
            if cfg is None:
                return
            cur = dict(cfg.plugin_configs.get("ecosystem_viewer", {}))
            cur["developer_mode"] = checked
            cfg.plugin_configs["ecosystem_viewer"] = cur
        except Exception:
            logger.warning("Could not persist developer_mode to plugin_configs")
        # Propagate to the disclosure widget if it exists
        if hasattr(self, "_dev_disclosure") and self._dev_disclosure is not None:
            self._dev_disclosure.set_expanded(checked)

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

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

        self._dev_disclosure: _DeveloperDisclosure | None = None

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

        i = inspect_acdc_schema(schemer.sed)
        dev_mode = self._dev_toggle.isChecked()

        # Build developer disclosure first (added last; holds old cards)
        self._dev_disclosure = _DeveloperDisclosure(expanded=dev_mode)
        self._dev_disclosure.add_section(self._build_requirements_section(i))
        self._dev_disclosure.add_section(self._build_sections_section(i))
        self._dev_disclosure.add_section(self._build_raw_json_section(i))

        # Insert cards in order: hero, at-a-glance, attributes, chain-of-auth,
        # annotation, developer disclosure
        idx = 0
        self._content_layout.insertWidget(idx, self._build_hero_card(i)); idx += 1
        self._content_layout.insertWidget(idx, self._build_at_a_glance_card(i)); idx += 1
        self._content_layout.insertWidget(idx, self._build_attributes_card(i)); idx += 1
        self._content_layout.insertWidget(idx, self._build_chain_of_authority_card(i, vault)); idx += 1
        self._content_layout.insertWidget(idx, self._build_annotation_card(i)); idx += 1
        self._content_layout.insertWidget(idx, self._dev_disclosure); idx += 1

    # ------------------------------------------------------------------
    # §4.2 Hero header card
    # ------------------------------------------------------------------

    def _build_hero_card(self, i: Any) -> QWidget:
        frame = QFrame()
        frame.setObjectName("sdHeroCard")
        frame.setStyleSheet(
            "QFrame#sdHeroCard { background-color: white; border: 1px solid #E0E3EA; border-radius: 8px; }"
            "QFrame#sdHeroCard QLabel { background: transparent; }"
        )
        outer_layout = QHBoxLayout(frame)
        outer_layout.setContentsMargins(20, 20, 20, 20)
        outer_layout.setSpacing(16)
        outer_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # 72px variant glyph (sized for hero presence per design §4.2)
        icon_path = icons.ICON_VARIANT_PRIVATE if i.requires_nonce else icons.ICON_VARIANT_PUBLIC
        glyph_label = QLabel()
        px = QPixmap(icon_path)
        if not px.isNull():
            glyph_label.setPixmap(px.scaled(
                72, 72,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        glyph_label.setFixedSize(72, 72)
        glyph_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        outer_layout.addWidget(glyph_label, 0, Qt.AlignmentFlag.AlignTop)

        # Text block
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(6)

        # Title + version row
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(10)
        title_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        title_lbl = QLabel(i.title or "(untitled schema)")
        title_lbl.setStyleSheet("font-size: 32px; font-weight: 600;")
        title_row.addWidget(title_lbl)

        if i.schema_version:
            ver_lbl = QLabel(f"v{i.schema_version}")
            ver_lbl.setStyleSheet(f"font-size: 16px; color: {colors.TEXT_SECONDARY};")
            title_row.addWidget(ver_lbl)

        title_row.addStretch()
        text_layout.addLayout(title_row)

        # Description
        if i.description:
            desc_lbl = QLabel(i.description)
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet(f"font-size: 14px; color: {colors.TEXT_DARK};")
            text_layout.addWidget(desc_lbl)

        # SAID chip row: fingerprint icon + SAID text + copy button
        said_row = QHBoxLayout()
        said_row.setContentsMargins(0, 4, 0, 0)
        said_row.setSpacing(6)
        said_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        fp_lbl = QLabel()
        fp_px = QPixmap(icons.ICON_SAID_FINGERPRINT)
        if not fp_px.isNull():
            fp_lbl.setPixmap(fp_px.scaled(
                16, 16,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))

        said_lbl = QLabel(i.schema_said)
        said_lbl.setStyleSheet(
            "font-family: monospace; font-size: 12px;"
            f" color: {colors.TEXT_SECONDARY};"
        )
        said_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        copy_btn = LocksmithIconButton(
            icons.ICON_COPY, tooltip="Copy SAID to clipboard", icon_size=16
        )
        _said = i.schema_said
        copy_btn.clicked.connect(
            lambda _c=False, s=_said: QGuiApplication.clipboard().setText(s)
        )

        said_row.addWidget(fp_lbl)
        said_row.addWidget(said_lbl)
        said_row.addWidget(copy_btn)
        said_row.addStretch()
        text_layout.addLayout(said_row)

        outer_layout.addLayout(text_layout, 1)
        return frame

    # ------------------------------------------------------------------
    # §4.3 At-a-glance card
    # ------------------------------------------------------------------

    def _build_at_a_glance_card(self, i: Any) -> QWidget:
        frame = QFrame()
        frame.setObjectName("sdAtAGlanceCard")
        frame.setStyleSheet(
            "QFrame#sdAtAGlanceCard { background-color: white; border: 1px solid #E0E3EA; border-radius: 8px; }"
            "QFrame#sdAtAGlanceCard QLabel { background: transparent; }"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title_lbl = QLabel("At a glance")
        title_lbl.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(title_lbl)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(16)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        # --- Cell 1: Variant (top-left) ---
        if i.requires_nonce:
            variant_icon_path = icons.ICON_VARIANT_PRIVATE
            variant_primary = "Private"
            variant_secondary = "Non-correlatable across presentations"
        else:
            variant_icon_path = icons.ICON_VARIANT_PUBLIC
            variant_primary = "Public"
            variant_secondary = "Correlatable by SAID across presentations"

        variant_px = QPixmap(variant_icon_path)
        variant_icon_lbl = QLabel()
        if not variant_px.isNull():
            variant_icon_lbl.setPixmap(variant_px.scaled(
                32, 32,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        grid.addWidget(
            self._glance_cell(variant_icon_lbl, variant_primary, variant_secondary),
            0, 0,
        )

        # --- Cell 2: Targeting (top-right) ---
        if i.requires_targeted:
            targeting_icon_path = icons.ICON_TARGETING_TARGETED
            targeting_primary = "Targeted to a holder"
            targeting_secondary = "Commits to a specific issuee AID"
        else:
            targeting_icon_path = icons.ICON_TARGETING_UNTARGETED
            targeting_primary = "Untargeted attestation"
            targeting_secondary = "Public attestation; no specific holder"

        targeting_px = QPixmap(targeting_icon_path)
        targeting_icon_lbl = QLabel()
        if not targeting_px.isNull():
            targeting_icon_lbl.setPixmap(targeting_px.scaled(
                32, 32,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        grid.addWidget(
            self._glance_cell(targeting_icon_lbl, targeting_primary, targeting_secondary),
            0, 1,
        )

        # --- Cell 3: Disclosure tier (bottom-left) ---
        sd = i.declared_sections
        if sd.declares_aggregate:
            tier = "selective"
        elif sd.declares_attribute and sd.declares_edges and sd.declares_rules:
            tier = "full"
        elif sd.declares_attribute:
            tier = "partial"
        else:
            tier = "metadata"

        tier_descriptions = {
            "metadata": "Identity-only references",
            "partial": "Some attributes redactable in presentations",
            "selective": "Individual attributes can be disclosed independently",
            "full": "Every section disclosed in full form",
        }
        tier_widget = DisclosureTierWidget(tier=tier)
        grid.addWidget(
            self._glance_cell(tier_widget, tier.capitalize() + " disclosure", tier_descriptions[tier]),
            1, 0,
        )

        # --- Cell 4: Section fingerprint (bottom-right) ---
        fp_widget = SectionFingerprintWidget(
            has_attribute=sd.declares_attribute,
            has_aggregate=sd.declares_aggregate,
            has_edges=sd.declares_edges,
            has_rules=sd.declares_rules,
        )
        # Build primary label (what's declared)
        declared_parts = []
        if sd.declares_attribute:
            declared_parts.append("Attribute")
        if sd.declares_aggregate:
            declared_parts.append("Aggregate")
        if sd.declares_edges:
            declared_parts.append("Edges")
        if sd.declares_rules:
            declared_parts.append("Rules")
        fp_primary = " + ".join(declared_parts) if declared_parts else "No sections declared"

        # Build secondary label (what's missing)
        missing_parts = []
        if not sd.declares_attribute and not sd.declares_aggregate:
            missing_parts.append("no attribute")
        if not sd.declares_aggregate:
            missing_parts.append("no aggregate")
        if not sd.declares_edges:
            missing_parts.append("no edges")
        if not sd.declares_rules:
            missing_parts.append("no rules")
        if missing_parts:
            fp_secondary = "; ".join(part.capitalize() for part in missing_parts)
        else:
            fp_secondary = "All sections declared"

        grid.addWidget(
            self._glance_cell(fp_widget, fp_primary, fp_secondary),
            1, 1,
        )

        layout.addLayout(grid)
        return frame

    def _glance_cell(self, icon_widget: QWidget, primary: str, secondary: str) -> QWidget:
        """Build a single at-a-glance cell: [icon][text_block]."""
        cell = QWidget()
        cell.setObjectName("sdGlanceCell")
        cell.setStyleSheet("QWidget#sdGlanceCell QLabel { background: transparent; }")
        row = QHBoxLayout(cell)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(icon_widget, 0, Qt.AlignmentFlag.AlignTop)

        text_block = QVBoxLayout()
        text_block.setContentsMargins(0, 0, 0, 0)
        text_block.setSpacing(2)

        primary_lbl = QLabel(primary)
        primary_lbl.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {colors.TEXT_DARK};")
        text_block.addWidget(primary_lbl)

        secondary_lbl = QLabel(secondary)
        secondary_lbl.setWordWrap(True)
        secondary_lbl.setStyleSheet(f"font-size: 11px; color: {colors.TEXT_SECONDARY};")
        text_block.addWidget(secondary_lbl)

        row.addLayout(text_block, 1)
        return cell

    # ------------------------------------------------------------------
    # Attributes card (NEW — user's correction)
    # ------------------------------------------------------------------

    def _build_attributes_card(self, i: Any) -> QWidget:
        frame = QFrame()
        frame.setObjectName("sdAttributesCard")
        frame.setStyleSheet(
            "QFrame#sdAttributesCard { background-color: white; border: 1px solid #E0E3EA; border-radius: 8px; }"
            "QFrame#sdAttributesCard QLabel { background: transparent; }"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        title_lbl = QLabel("Attributes")
        title_lbl.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(title_lbl)

        if not i.attribute_fields:
            empty = QLabel("This schema declares no attribute fields.")
            empty.setStyleSheet(f"font-size: 13px; color: {colors.TEXT_SECONDARY}; font-style: italic;")
            layout.addWidget(empty)
            return frame

        for field in i.attribute_fields:
            layout.addWidget(self._build_attribute_field_row(field))

        return frame

    def _build_attribute_field_row(self, field: Any) -> QWidget:
        """Render a single attribute field row with name, type chip, required indicator,
        description, enum pills, and constraint summary."""
        row = QFrame()
        row.setObjectName("sdAttrRow")
        row.setStyleSheet(
            "QFrame#sdAttrRow { background: transparent; }"
            "QFrame#sdAttrRow QLabel { background: transparent; }"
        )
        layout = QVBoxLayout(row)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(4)

        # Top row: name + type chip + required indicator
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(6)
        top_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        name_lbl = QLabel(field.name)
        name_lbl.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {colors.TEXT_DARK};")
        top_row.addWidget(name_lbl)

        # Type chip
        type_chip = QLabel(field.type_label)
        type_chip.setStyleSheet(
            f"font-size: 11px; color: {colors.TEXT_DARK};"
            f" background-color: {colors.BACKGROUND_NEUTRAL}; border-radius: 10px;"
            f" padding: 1px 6px;"
        )
        top_row.addWidget(type_chip)

        # Required indicator
        if field.required:
            req_chip = QLabel("required")
            req_chip.setStyleSheet(
                f"font-size: 11px; color: {colors.DANGER};"
                f" background-color: transparent;"
                f" font-weight: 600; padding: 0px 2px;"
            )
            top_row.addWidget(req_chip)

        top_row.addStretch()
        layout.addLayout(top_row)

        # Description
        if field.description:
            desc_lbl = QLabel(field.description)
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet(f"font-size: 12px; color: {colors.TEXT_SECONDARY};")
            layout.addWidget(desc_lbl)

        # Enum values as pills (max 6 visible; overflow shows "+N more")
        if field.enum_values:
            enum_row = QHBoxLayout()
            enum_row.setContentsMargins(0, 2, 0, 0)
            enum_row.setSpacing(4)
            enum_row.setAlignment(Qt.AlignmentFlag.AlignLeft)
            visible = field.enum_values[:6]
            overflow = len(field.enum_values) - len(visible)
            for val in visible:
                chip = QLabel(val)
                chip.setTextFormat(Qt.TextFormat.PlainText)
                chip.setStyleSheet(
                    f"font-size: 11px; color: {colors.TEXT_DARK};"
                    f" background-color: {colors.BACKGROUND_SELECTION}; border-radius: 8px;"
                    f" padding: 1px 6px;"
                )
                enum_row.addWidget(chip)
            if overflow > 0:
                more_lbl = QLabel(f"+{overflow} more")
                more_lbl.setStyleSheet(f"font-size: 11px; color: {colors.TEXT_SECONDARY};")
                enum_row.addWidget(more_lbl)
            enum_row.addStretch()
            enum_wrapper = QWidget()
            enum_wrapper.setLayout(enum_row)
            layout.addWidget(enum_wrapper)

        # Constraint summary (with pluralization)
        def _plural(n: int, singular: str, plural: str) -> str:
            return singular if n == 1 else plural

        constraints: list[str] = []
        if field.min_length is not None and field.max_length is not None and field.min_length == field.max_length:
            n = field.min_length
            constraints.append(f"{n} {_plural(n, 'character', 'characters')}")
        elif field.min_length is not None:
            n = field.min_length
            constraints.append(f"min {n} {_plural(n, 'character', 'characters')}")
        elif field.max_length is not None:
            n = field.max_length
            constraints.append(f"max {n} {_plural(n, 'character', 'characters')}")
        if field.min_items is not None:
            n = field.min_items
            constraints.append(f"at least {n} {_plural(n, 'item', 'items')}")
        if field.max_items is not None:
            n = field.max_items
            constraints.append(f"at most {n} {_plural(n, 'item', 'items')}")
        # Include format only if it didn't feed into type_label
        fmt = field.format
        if fmt and field.type_label not in ("date", "datetime", "URL"):
            constraints.append(f"format: {fmt}")

        if constraints:
            constraint_lbl = QLabel(", ".join(constraints))
            constraint_lbl.setStyleSheet(
                f"font-size: 11px; color: {colors.TEXT_SECONDARY}; font-style: italic;"
            )
            layout.addWidget(constraint_lbl)

        return row

    # ------------------------------------------------------------------
    # §4.4 Chain of authority card (stub for B3b)
    # ------------------------------------------------------------------

    def _build_chain_of_authority_card(self, i: Any, vault: Any) -> QWidget:
        frame = QFrame()
        frame.setObjectName("sdChainCard")
        frame.setStyleSheet(
            "QFrame#sdChainCard { background-color: white; border: 1px solid #E0E3EA; border-radius: 8px; }"
            "QFrame#sdChainCard QLabel { background: transparent; }"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        title_lbl = QLabel("Chain of authority")
        title_lbl.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(title_lbl)

        n = len(i.edge_requirements)
        if n == 0:
            status_lbl = QLabel("This schema declares no edges to other schemas.")
        else:
            status_lbl = QLabel(
                f"This schema declares {n} edge requirement(s)."
            )
        status_lbl.setStyleSheet(f"font-size: 13px; color: {colors.TEXT_SECONDARY};")
        layout.addWidget(status_lbl)

        # Render existing edge-requirement list (B3b will replace with mini-graph)
        if i.edge_requirements:
            for edge in i.edge_requirements:
                layout.addWidget(self._build_edge_row(edge, vault))

        return frame

    def _build_edge_row(self, edge: Any, vault: Any) -> QWidget:
        """Render a single edge requirement row (shared between chain card and old edges section)."""
        row = QWidget()
        row.setObjectName("sdEdgeRow")
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(0, 6, 0, 6)
        row_layout.setSpacing(2)
        row.setStyleSheet(
            "QWidget#sdEdgeRow { background: transparent; }"
            "QWidget#sdEdgeRow QLabel { background: transparent; }"
        )
        head = QLabel(f"<b>{edge.name}</b>")
        head.setStyleSheet("font-size: 13px;")
        row_layout.addWidget(head)
        if edge.description and edge.description != edge.name:
            desc = QLabel(edge.description)
            desc.setWordWrap(True)
            desc.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px;")
            row_layout.addWidget(desc)
        if edge.target_schema_said:
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
            link.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
                | Qt.TextInteractionFlag.LinksAccessibleByMouse
            )
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
        return row

    # ------------------------------------------------------------------
    # §4.5 My note annotation card
    # ------------------------------------------------------------------

    def _build_annotation_card(self, i: Any) -> QWidget:
        frame = QFrame()
        frame.setObjectName("sdAnnotationCard")
        frame.setStyleSheet(
            "QFrame#sdAnnotationCard { background-color: white; border: 1px solid #E0E3EA; border-radius: 8px; }"
            "QFrame#sdAnnotationCard QLabel { background: transparent; }"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        # Title row: "My note" on left, "Edit annotation" button on right
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(10)

        title_lbl = QLabel("My note")
        title_lbl.setStyleSheet("font-size: 14px; font-weight: 600;")
        title_row.addWidget(title_lbl)
        title_row.addStretch()

        target_label = i.title or i.schema_said[:24]
        edit_btn = LocksmithInvertedButton("Edit annotation")
        edit_btn.clicked.connect(
            lambda: self.edit_annotation_clicked.emit("schema", i.schema_said, target_label)
        )
        title_row.addWidget(edit_btn)
        layout.addLayout(title_row)

        # Load annotation
        ann = None
        if self._db is not None:
            try:
                ann = self._db.get_annotation(AnnotationKind.SCHEMA, i.schema_said)
            except Exception:
                logger.exception("Failed to load annotation")

        if ann is None or not ann.note:
            empty = QLabel("Add a note about how you use this schema")
            empty.setStyleSheet(f"font-size: 13px; color: {colors.TEXT_DARK};")
            layout.addWidget(empty)
        else:
            note = QLabel(ann.note)
            note.setTextFormat(Qt.TextFormat.PlainText)
            note.setWordWrap(True)
            note.setStyleSheet("font-size: 13px;")
            note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(note)
            if ann.tags:
                tags_row = QHBoxLayout()
                tags_row.setContentsMargins(0, 2, 0, 0)
                tags_row.setSpacing(4)
                tags_row.setAlignment(Qt.AlignmentFlag.AlignLeft)
                for tag in ann.tags:
                    chip = QLabel(tag)
                    chip.setTextFormat(Qt.TextFormat.PlainText)
                    chip.setStyleSheet(
                        f"font-size: 11px; color: {colors.TEXT_DARK};"
                        f" background-color: {colors.BACKGROUND_SELECTION}; border-radius: 8px;"
                        f" padding: 1px 6px;"
                    )
                    tags_row.addWidget(chip)
                tags_row.addStretch()
                tags_wrapper = QWidget()
                tags_wrapper.setLayout(tags_row)
                layout.addWidget(tags_wrapper)

        return frame

    # ------------------------------------------------------------------
    # §4.6 Developer details — old section builders (used inside disclosure)
    # ------------------------------------------------------------------

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
        frame.setObjectName("sdCard")
        frame.setStyleSheet(
            "QFrame#sdCard { background-color: white; border: 1px solid #E0E3EA; border-radius: 8px; }"
            "QFrame#sdCard QLabel { background: transparent; }"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(title_label)
        return frame


class EcosystemDetailPage(QWidget):
    """View + edit a single ecosystem: members, annotations."""

    back_requested = Signal()
    add_schema_clicked = Signal(str)        # emits ecosystem name
    add_aid_clicked = Signal(str)
    remove_schema_clicked = Signal(str, str)  # (ecosystem name, schema_said)
    remove_aid_clicked = Signal(str, str)
    delete_ecosystem_clicked = Signal(str)
    show_schema_detail_requested = Signal(str)

    def __init__(self, app: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self.app = app
        self._db: EcosystemBaser | None = None
        self._current_name: str | None = None

        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(colors.BACKGROUND_CONTENT))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        bar_widget = QWidget()
        bar_widget.setObjectName("ecosystemDetailBackBar")
        bar_widget.setStyleSheet(
            f"#ecosystemDetailBackBar {{ background-color: {colors.BACKGROUND_CONTENT}; }}"
            "#ecosystemDetailBackBar QLabel { background: transparent; }"
        )
        bar = QHBoxLayout(bar_widget)
        bar.setContentsMargins(20, 12, 20, 0)
        back = QLabel('<a href="#back" style="color:#3a5fff;text-decoration:none;">‹ Back to overview</a>')
        back.setOpenExternalLinks(False)
        back.linkActivated.connect(lambda _: self.back_requested.emit())
        back.setStyleSheet("font-size: 13px;")
        bar.addWidget(back)
        bar.addStretch()
        outer.addWidget(bar_widget)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"background-color: {colors.BACKGROUND_CONTENT}; border: none;")
        scroll.viewport().setStyleSheet(f"background-color: {colors.BACKGROUND_CONTENT};")

        self._content = QWidget()
        self._content.setObjectName("ecosystemDetailContent")
        self._content.setStyleSheet(
            f"#ecosystemDetailContent {{ background-color: {colors.BACKGROUND_CONTENT}; }}"
            "#ecosystemDetailContent QLabel { background: transparent; }"
        )
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(20, 16, 20, 30)
        self._content_layout.setSpacing(16)
        self._content_layout.addStretch()
        scroll.setWidget(self._content)
        outer.addWidget(scroll)

    def set_db(self, db: "EcosystemBaser | None") -> None:
        """Receive (or release) the plugin's EcosystemBaser. Called by plugin lifecycle."""
        self._db = db

    @property
    def current_name(self) -> str | None:
        """The ecosystem name currently being shown, or None if nothing loaded."""
        return self._current_name

    def show_ecosystem(self, name: str) -> None:
        self._current_name = name
        self._refresh()

    def _refresh(self) -> None:
        # Clear all widgets in front of the layout's trailing stretch.
        # __init__ leaves the stretch as the sole item; section widgets are
        # then inserted at indices 0..N, pushing the stretch to last position.
        # The `> 1` guard preserves the stretch.
        while self._content_layout.count() > 1:
            item = self._content_layout.takeAt(0)
            w = item.widget() if item else None
            if w is not None:
                w.deleteLater()

        if self._db is None or self._current_name is None:
            self._content_layout.insertWidget(0, QLabel("(no ecosystem loaded)"))
            return

        eco = self._db.get_ecosystem(self._current_name)
        if eco is None:
            self._content_layout.insertWidget(0, QLabel(
                f"Ecosystem '{self._current_name}' not found."
            ))
            return

        self._content_layout.insertWidget(0, self._build_header(eco))
        self._content_layout.insertWidget(1, self._build_schemas_section(eco))
        self._content_layout.insertWidget(2, self._build_aids_section(eco))
        self._content_layout.insertWidget(3, self._build_actions_section(eco))

    def _build_header(self, eco: Any) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        title = QLabel(f"<b>{eco.name}</b>")
        title.setStyleSheet("font-size: 22px;")
        layout.addWidget(title)
        if eco.description:
            desc = QLabel(eco.description)
            desc.setWordWrap(True)
            desc.setStyleSheet(f"color: {colors.TEXT_DARK}; font-size: 13px;")
            layout.addWidget(desc)
        meta = QLabel(
            f"<span style='color:{colors.TEXT_SECONDARY};font-size:11px;'>"
            f"created {eco.created_at} · updated {eco.updated_at} · source {eco.source_kind}</span>"
        )
        layout.addWidget(meta)
        return wrapper

    def _build_schemas_section(self, eco: Any) -> QWidget:
        section = QFrame()
        section.setObjectName("edSchemasSection")
        section.setStyleSheet(
            "QFrame#edSchemasSection { background-color: white; border: 1px solid #E0E3EA; border-radius: 8px; }"
            "QFrame#edSchemasSection QLabel { background: transparent; }"
        )
        layout = QVBoxLayout(section)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel(f"Schemas ({len(eco.schema_saids)})")
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        head.addWidget(title)
        head.addStretch()
        add_btn = LocksmithInvertedButton("Add schema")
        add_btn.clicked.connect(lambda: self.add_schema_clicked.emit(eco.name))
        head.addWidget(add_btn)
        head_w = QWidget()
        head_w.setLayout(head)
        layout.addWidget(head_w)

        if not eco.schema_saids:
            empty = QLabel("(no schemas yet)")
            empty.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px; font-style: italic;")
            layout.addWidget(empty)
            return section

        for said in eco.schema_saids:
            row = QFrame()
            row.setObjectName("edSchemaMemberRow")
            row.setStyleSheet(
                "QFrame#edSchemaMemberRow { background: #F8F9FF; border-radius: 4px; }"
                "QFrame#edSchemaMemberRow QLabel { background: transparent; }"
            )
            r = QHBoxLayout(row)
            r.setContentsMargins(10, 6, 10, 6)
            link = QLabel(
                f'<a href="#nav" style="color:#3a5fff;text-decoration:none;">'
                f'<code>{said}</code></a>'
            )
            link.setOpenExternalLinks(False)
            link.linkActivated.connect(lambda _l, s=said: self.show_schema_detail_requested.emit(s))
            link.setStyleSheet("font-size: 12px;")
            link.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse | Qt.TextInteractionFlag.TextSelectableByMouse)
            r.addWidget(link, 1)
            remove_btn = LocksmithIconButton(":/assets/material-icons/close.svg", tooltip="Remove from ecosystem", icon_size=16)
            remove_btn.clicked.connect(lambda _c=False, n=eco.name, s=said: self.remove_schema_clicked.emit(n, s))
            r.addWidget(remove_btn)
            layout.addWidget(row)
        return section

    def _build_aids_section(self, eco: Any) -> QWidget:
        section = QFrame()
        section.setObjectName("edAidsSection")
        section.setStyleSheet(
            "QFrame#edAidsSection { background-color: white; border: 1px solid #E0E3EA; border-radius: 8px; }"
            "QFrame#edAidsSection QLabel { background: transparent; }"
        )
        layout = QVBoxLayout(section)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel(f"Issuer AIDs ({len(eco.issuer_aids)})")
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        head.addWidget(title)
        head.addStretch()
        add_btn = LocksmithInvertedButton("Add AID")
        add_btn.clicked.connect(lambda: self.add_aid_clicked.emit(eco.name))
        head.addWidget(add_btn)
        head_w = QWidget()
        head_w.setLayout(head)
        layout.addWidget(head_w)

        if not eco.issuer_aids:
            empty = QLabel("(no issuer AIDs yet)")
            empty.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px; font-style: italic;")
            layout.addWidget(empty)
            return section

        for aid in eco.issuer_aids:
            row = QFrame()
            row.setObjectName("edAidMemberRow")
            row.setStyleSheet(
                "QFrame#edAidMemberRow { background: #F8F9FF; border-radius: 4px; }"
                "QFrame#edAidMemberRow QLabel { background: transparent; }"
            )
            r = QHBoxLayout(row)
            r.setContentsMargins(10, 6, 10, 6)
            label = QLabel(f"<code>{aid}</code>")
            label.setStyleSheet("font-size: 12px;")
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            r.addWidget(label, 1)
            remove_btn = LocksmithIconButton(":/assets/material-icons/close.svg", tooltip="Remove from ecosystem", icon_size=16)
            remove_btn.clicked.connect(lambda _c=False, n=eco.name, a=aid: self.remove_aid_clicked.emit(n, a))
            r.addWidget(remove_btn)
            layout.addWidget(row)
        return section

    def _build_actions_section(self, eco: Any) -> QWidget:
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch()
        delete_btn = LocksmithInvertedButton("Delete ecosystem")
        delete_btn.clicked.connect(lambda: self.delete_ecosystem_clicked.emit(eco.name))
        layout.addWidget(delete_btn)
        return wrapper
