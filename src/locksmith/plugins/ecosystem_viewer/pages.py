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
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGraphicsScene,
    QGraphicsView,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from keri import help

from locksmith.acdc import inspect_acdc_schema
from locksmith.acdc import icons
from locksmith.plugins.ecosystem_viewer.db import AnnotationKind
from locksmith.plugins.ecosystem_viewer.graph_items import (
    EdgeLine,
    NODE_HEIGHT,
    NODE_WIDTH,
    NOTCH_DEPTH,
    SchemaNode,
)
from locksmith.plugins.ecosystem_viewer.graph_view import EcosystemGraphView
from locksmith.plugins.ecosystem_viewer.overview_cards import (
    CreateEcosystemTile,
    EcosystemTile,
    EmptyStateCard,
    IssuerCard,
    SchemaCard,
)
from locksmith.plugins.ecosystem_viewer.widgets import (
    DisclosureTierWidget,
    LifecycleWidget,
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
    show_ecosystem_detail_requested = Signal(str)  # emits ecosystem name
    show_issuer_requested = Signal(str, bool)   # emits (aid, is_self)
    create_ecosystem_clicked = Signal()

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
            layout = item.layout() if item else None
            if widget is not None:
                widget.deleteLater()
            elif layout is not None:
                # Recursively delete child widgets, then drop the layout.
                self._purge_layout(layout)

        vault = getattr(self.app, "vault", None)
        if vault is None or vault.hby is None:
            empty = EmptyStateCard("Unlock a vault to see your map.")
            self._content_layout.insertWidget(self._sections_anchor_index, empty)
            return

        # Region 1: hero ribbon (My ecosystems)
        ecosystems_section = self._build_ecosystems_section()
        self._content_layout.insertWidget(self._sections_anchor_index, ecosystems_section)

        # Region 2: two-column index (schemas | issuers)
        index_row = QHBoxLayout()
        index_row.setContentsMargins(0, 0, 0, 0)
        index_row.setSpacing(18)
        index_row.addWidget(self._build_schema_section(vault), 1)
        index_row.addWidget(self._build_contacts_section(vault), 1)
        self._content_layout.insertLayout(self._sections_anchor_index + 1, index_row)

    @staticmethod
    def _purge_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget() if item else None
            if w is not None:
                w.deleteLater()
            else:
                child = item.layout() if item else None
                if child is not None:
                    EcosystemViewerPage._purge_layout(child)

    # ------------------------------------------------------------------
    # Static header
    # ------------------------------------------------------------------

    def _build_static_header(self) -> None:
        title = QLabel("Ecosystem Viewer")
        title.setStyleSheet("font-size: 22px; font-weight: 600;")
        self._content_layout.addWidget(title)

        intro = QLabel(
            "Your map of schemas, issuers, and the credentials that flow between them."
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

        if self._db is None:
            ecosystems = []
        else:
            try:
                ecosystems = self._db.list_ecosystems()
            except Exception:
                logger.exception("Failed to list ecosystems")
                ecosystems = []

        # Hero ribbon: horizontally-scrolling row of tiles.
        ribbon_scroll = QScrollArea()
        ribbon_scroll.setWidgetResizable(True)
        ribbon_scroll.setFrameShape(QFrame.Shape.NoFrame)
        ribbon_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        ribbon_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        ribbon_scroll.setStyleSheet("background: transparent; border: none;")
        ribbon_scroll.viewport().setStyleSheet("background: transparent;")
        ribbon_scroll.setFixedHeight(196)  # tile height + scrollbar room

        ribbon_inner = QWidget()
        ribbon_inner.setObjectName("ecoRibbonInner")
        ribbon_inner.setStyleSheet(
            "QWidget#ecoRibbonInner { background: transparent; }"
        )
        ribbon_layout = QHBoxLayout(ribbon_inner)
        ribbon_layout.setContentsMargins(0, 4, 0, 4)
        ribbon_layout.setSpacing(12)
        ribbon_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        for eco in sorted(ecosystems, key=lambda e: e.name):
            tile = EcosystemTile(eco)
            tile.clicked.connect(self.show_ecosystem_detail_requested.emit)
            ribbon_layout.addWidget(tile)

        # "+ Define a new ecosystem" tile — expanded when ribbon is otherwise empty.
        create_tile = CreateEcosystemTile(expanded=not ecosystems)
        create_tile.clicked.connect(self.create_ecosystem_clicked.emit)
        ribbon_layout.addWidget(create_tile)

        ribbon_layout.addStretch()
        ribbon_scroll.setWidget(ribbon_inner)
        layout.addWidget(ribbon_scroll)

        return section

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
            layout.addWidget(EmptyStateCard("Error enumerating schemas (see logs)."))
            return section

        if not schemas:
            layout.addWidget(EmptyStateCard(
                "No schemas yet. Add one via Credentials → Schemas → Add."
            ))
            return section

        for (said,), schemer in schemas:
            try:
                inspection = inspect_acdc_schema(schemer.sed)
                card = SchemaCard(inspection)
                card.clicked.connect(self.show_schema_detail_requested.emit)
                layout.addWidget(card)
            except Exception:
                logger.exception(f"Failed to inspect schema {said}")
                layout.addWidget(EmptyStateCard(
                    f"Failed to classify schema {said[:20]}… (see logs)."
                ))

        layout.addStretch()
        return section

    # ------------------------------------------------------------------
    # Contacts (issuer AIDs)
    # ------------------------------------------------------------------

    def _build_contacts_section(self, vault: Any) -> QWidget:
        section = self._build_card(title="Known issuers")
        layout: QVBoxLayout = section.layout()  # type: ignore[assignment]

        try:
            contacts = list(vault.org.list())
        except Exception:
            logger.exception("Failed to enumerate contacts")
            layout.addWidget(EmptyStateCard("Error enumerating contacts (see logs)."))
            return section

        # Compute the set of self-AIDs once so the sigil ring can highlight them.
        try:
            self_aids = {hab.pre for hab in vault.hby.habs.values()}
        except Exception:
            self_aids = set()

        contact_aids = {c.get("id", "") for c in contacts}
        if not contacts and not (self_aids - contact_aids):
            layout.addWidget(EmptyStateCard(
                "No issuers yet. Add one via Contacts → Add (OOBI or File)."
            ))
            return section

        for contact in contacts:
            pre = contact.get("id", "")
            kever = vault.hby.kevers.get(pre) if pre else None
            is_self = pre in self_aids
            card = IssuerCard(
                contact=contact,
                kever=kever,
                is_self=is_self,
            )
            card.clicked.connect(
                lambda aid, s=is_self: self.show_issuer_requested.emit(aid, s)
            )
            layout.addWidget(card)

        # Surface self-AIDs that aren't already in contacts (otherwise the
        # user can't navigate to them from here). Most own-AIDs aren't
        # registered as contacts; without this they'd be invisible on the
        # overview.
        for aid in sorted(self_aids - contact_aids):
            kever = vault.hby.kevers.get(aid)
            hab = vault.hby.habByPre(aid)
            alias = hab.name if hab is not None else "(self)"
            card = IssuerCard(
                contact={"id": aid, "alias": f"{alias} (mine)"},
                kever=kever,
                is_self=True,
            )
            card.clicked.connect(
                lambda emitted_aid: self.show_issuer_requested.emit(emitted_aid, True)
            )
            layout.addWidget(card)

        layout.addStretch()
        return section

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
    show_issuer_requested = Signal(str, bool)  # (aid, is_self)

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
        self._content_layout.insertWidget(idx, self._build_parties_card(i, vault)); idx += 1
        self._content_layout.insertWidget(idx, self._build_lifecycle_card(i)); idx += 1
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

        # 72px variant glyph + 32px lifecycle glyph (sized for hero presence per design §4.2)
        icon_path = icons.ICON_PRIVACY_PRIVATE if i.requires_nonce else icons.ICON_PRIVACY_PUBLIC
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

        # Stack variant glyph above lifecycle glyph
        glyph_stack = QVBoxLayout()
        glyph_stack.setContentsMargins(0, 0, 0, 0)
        glyph_stack.setSpacing(8)
        glyph_stack.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        glyph_stack.addWidget(glyph_label, 0, Qt.AlignmentFlag.AlignHCenter)

        lifecycle_glyph = LifecycleWidget(revocable=i.requires_registry)
        lifecycle_glyph.setFixedSize(32, 32)
        # Tooltip carries the prose; glyph alone reads at hero scale.
        lifecycle_glyph.setToolTip(
            "Revocable via TEL — registry-backed lifecycle"
            if i.requires_registry
            else "One-shot — no revocation surface"
        )
        glyph_stack.addWidget(lifecycle_glyph, 0, Qt.AlignmentFlag.AlignHCenter)

        glyph_stack_w = QWidget()
        glyph_stack_w.setLayout(glyph_stack)
        outer_layout.addWidget(glyph_stack_w, 0, Qt.AlignmentFlag.AlignTop)

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
            variant_icon_path = icons.ICON_PRIVACY_PRIVATE
            variant_primary = "Private"
            variant_secondary = "Non-correlatable across presentations"
        else:
            variant_icon_path = icons.ICON_PRIVACY_PUBLIC
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
            targeting_secondary = "Each credential commits to an issuee AID"
        else:
            targeting_icon_path = icons.ICON_TARGETING_UNTARGETED
            targeting_primary = "Untargeted attestation"
            targeting_secondary = "No issuee — public attestation"

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
        cell.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        cell.setStyleSheet(
            "QWidget#sdGlanceCell { background: transparent; }"
            "QWidget#sdGlanceCell QLabel { background: transparent; }"
        )
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
    # Parties card + Lifecycle card (Stage 10 — split per design §4.2)
    # ------------------------------------------------------------------

    def _build_parties_card(self, i: Any, vault: Any) -> QWidget:
        """Schema-level Parties card: the people axis.

        Issuer is always present; issuee depends on whether the schema
        requires targeting (a.i). Per design 2026-05-07-acdc-parties-lifecycle
        §4.2. Sigils render as role placeholders (no specific AID), since
        a schema describes potential credentials, not actual ones."""
        frame = QFrame()
        frame.setObjectName("sdPartiesCard")
        frame.setStyleSheet(
            "QFrame#sdPartiesCard { background-color: white;"
            " border: 1px solid #E0E3EA; border-radius: 8px; }"
            "QFrame#sdPartiesCard QLabel { background: transparent; }"
        )
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(10)

        title = QLabel("Parties")
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        outer.addWidget(title)

        # Two-column layout: [issuer] | [issuee]
        cols = QHBoxLayout()
        cols.setContentsMargins(0, 0, 0, 0)
        cols.setSpacing(20)
        cols.setAlignment(Qt.AlignmentFlag.AlignTop)

        cols.addWidget(self._build_party_column(
            role="from",
            heading="Issuer",
            body=(
                "Always present. Every credential of this schema names an "
                "issuer AID. The schema cannot constrain who that is — "
                "that's an ecosystem-governance concern (see "
                "permitted issuers)."
            ),
        ), 1)

        if i.requires_targeted:
            cols.addWidget(self._build_party_column(
                role="to",
                heading="Issuee",
                body=(
                    "Required by this schema — credentials commit to a "
                    "holder AID inside their attribute block. Untargeted "
                    "credentials cannot conform to this schema."
                ),
            ), 1)
        else:
            cols.addWidget(self._build_party_column(
                role=None,  # absent role
                heading="No issuee",
                body=(
                    "This schema declares no issuee — credentials are "
                    "untargeted attestations from the issuer. Any verifier "
                    "can read them by SAID; no specific holder is bound. "
                    "Also called self-attestations."
                ),
                placeholder=True,
            ), 1)

        cols_w = QWidget()
        cols_w.setLayout(cols)
        outer.addWidget(cols_w)

        if i.requires_targeted:
            note = QLabel(
                "ⓘ When the issuer's AID equals the issuee's AID, the "
                "credential is <b>self-issued</b> — a self-attestation by "
                "that AID about itself. (Visible only on actual credentials.)"
            )
            note.setWordWrap(True)
            note.setTextFormat(Qt.TextFormat.RichText)
            note.setStyleSheet(
                f"font-size: 11px; color: {colors.TEXT_SECONDARY}; padding-top: 6px;"
            )
            outer.addWidget(note)

        # Known-issuers chip row (design §7.1) — bridges schema-detail to
        # the ecosystem-graph "who issues" question without requiring a
        # separate page navigation.
        known_aids = self._collect_known_issuer_aids_for_schema(i.schema_said, vault)
        outer.addWidget(self._build_known_issuers_row(known_aids, vault))

        return frame

    def _build_party_column(
        self,
        role: str | None,
        heading: str,
        body: str,
        placeholder: bool = False,
    ) -> QWidget:
        """One column of the Parties card: sigil placeholder + role label
        + body copy. `placeholder=True` renders a dashed-outline circle
        instead of the sigil, used for the 'No issuee' (untargeted) case."""
        from locksmith.plugins.ecosystem_viewer.overview_cards import (
            IssuerSigilCircle,
        )
        col = QFrame()
        col.setObjectName("sdPartyColumn")
        col.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        col.setStyleSheet(
            "QFrame#sdPartyColumn { background: transparent; }"
            "QFrame#sdPartyColumn QLabel { background: transparent; }"
        )
        layout = QVBoxLayout(col)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Header row: sigil + heading
        head_row = QHBoxLayout()
        head_row.setContentsMargins(0, 0, 0, 0)
        head_row.setSpacing(10)
        head_row.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        if placeholder:
            head_row.addWidget(_DashedCircle(diameter=40))
        else:
            sigil = IssuerSigilCircle(is_self=False, role=role)
            head_row.addWidget(sigil)

        heading_lbl = QLabel(heading)
        heading_lbl.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {colors.TEXT_DARK};"
        )
        head_row.addWidget(heading_lbl)
        head_row.addStretch()

        head_w = QWidget()
        head_w.setLayout(head_row)
        layout.addWidget(head_w)

        body_lbl = QLabel(body)
        body_lbl.setWordWrap(True)
        body_lbl.setStyleSheet(f"font-size: 12px; color: {colors.TEXT_SECONDARY};")
        layout.addWidget(body_lbl)

        return col

    def _collect_known_issuer_aids_for_schema(
        self, schema_said: str, vault: Any,
    ) -> list[str]:
        """Return the union of AIDs marked as permitted issuers of
        `schema_said` across every ecosystem that contains this schema.
        Returns at most a handful of AIDs in practice (one schema is
        typically a member of one or two ecosystems)."""
        if self._db is None:
            return []
        try:
            eco_names = self._db.ecosystems_for_schema(schema_said)
        except Exception:
            return []
        aids: list[str] = []
        seen: set[str] = set()
        for name in eco_names:
            try:
                rec = self._db.get_ecosystem(name)
            except Exception:
                continue
            if rec is None:
                continue
            for aid in rec.permitted_issuers.get(schema_said, []):
                if aid not in seen:
                    seen.add(aid)
                    aids.append(aid)
        return aids

    def _build_known_issuers_row(
        self, aids: list[str], vault: Any,
    ) -> QWidget:
        wrap = QFrame()
        wrap.setObjectName("sdKnownIssuersRow")
        wrap.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        wrap.setStyleSheet(
            "QFrame#sdKnownIssuersRow { background: transparent;"
            f" border-top: 1px solid {colors.BORDER}; padding-top: 8px; }}"
            "QFrame#sdKnownIssuersRow QLabel { background: transparent; }"
        )
        layout = QHBoxLayout(wrap)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        prefix = QLabel("Known issuers in your wallet:")
        prefix.setStyleSheet(
            f"font-size: 11px; color: {colors.TEXT_SECONDARY};"
            " font-weight: 600; letter-spacing: 0.04em;"
        )
        layout.addWidget(prefix)

        if not aids:
            empty = QLabel("none yet")
            empty.setStyleSheet(
                f"font-size: 11px; color: {colors.TEXT_SECONDARY}; font-style: italic;"
            )
            layout.addWidget(empty)
            layout.addStretch()
            return wrap

        # Build a small chip per AID — sigil-circle + alias.
        try:
            self_aids = {hab.pre for hab in vault.hby.habs.values()} if vault else set()
        except Exception:
            self_aids = set()

        for aid in aids:
            chip = QFrame()
            chip.setObjectName("sdKnownIssuerChip")
            chip.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setStyleSheet(
                "QFrame#sdKnownIssuerChip {"
                f" background: {colors.BACKGROUND_SELECTION};"
                " border-radius: 12px; padding: 2px 8px 2px 4px;"
                "}"
                "QFrame#sdKnownIssuerChip QLabel { background: transparent; }"
            )
            chip_l = QHBoxLayout(chip)
            chip_l.setContentsMargins(0, 0, 0, 0)
            chip_l.setSpacing(4)
            chip_l.setAlignment(Qt.AlignmentFlag.AlignVCenter)

            is_self = aid in self_aids
            # Small tinted sigil pixmap — IssuerSigilCircle's role
            # decoration isn't readable at chip scale (and its 48px paint
            # rect doesn't fit in a 20px chip), so we render the bare
            # sigil glyph at 14px tinted by self/remote color.
            from locksmith.plugins.ecosystem_viewer.overview_cards import (
                _load_tinted_pixmap,
            )
            from locksmith.acdc import icons as acdc_icons
            sigil_color = colors.PRIMARY if is_self else colors.TEXT_DARK
            sigil_lbl = QLabel()
            sigil_lbl.setPixmap(
                _load_tinted_pixmap(acdc_icons.ICON_ISSUER_SIGIL, 14, sigil_color)
            )
            sigil_lbl.setFixedSize(14, 14)
            chip_l.addWidget(sigil_lbl)

            alias = self._alias_for_aid(aid, vault)
            label = QLabel(alias + (" ★" if is_self else ""))
            label.setStyleSheet(
                f"font-size: 11px; color: {colors.TEXT_DARK};"
                + (f" font-weight: 600;" if is_self else "")
            )
            label.setToolTip(aid)
            chip_l.addWidget(label)

            chip.mousePressEvent = (
                lambda _ev, a=aid, s=is_self:
                    self.show_issuer_requested.emit(a, s)
            )
            layout.addWidget(chip)

        layout.addStretch()
        return wrap

    def _alias_for_aid(self, aid: str, vault: Any) -> str:
        if vault is None or not aid:
            return aid[:14] + "…" if len(aid) > 16 else aid
        try:
            for c in vault.org.list():
                if c.get("id") == aid:
                    a = c.get("alias")
                    if a:
                        return a
        except Exception:
            pass
        try:
            hab = vault.hby.habByPre(aid)
            if hab is not None and hab.name:
                return hab.name
        except Exception:
            pass
        return aid[:14] + "…" if len(aid) > 16 else aid

    def _build_lifecycle_card(self, i: Any) -> QWidget:
        """Schema-level Lifecycle card: the time axis. Single fact —
        does this schema require registry anchoring? Per design
        2026-05-07-acdc-parties-lifecycle §4.2."""
        from locksmith.plugins.ecosystem_viewer.widgets import LifecycleWidget
        frame = QFrame()
        frame.setObjectName("sdLifecycleCard")
        frame.setStyleSheet(
            "QFrame#sdLifecycleCard { background-color: white;"
            " border: 1px solid #E0E3EA; border-radius: 8px; }"
            "QFrame#sdLifecycleCard QLabel { background: transparent; }"
        )
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(10)

        title = QLabel("Lifecycle")
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        outer.addWidget(title)

        # Single row: glyph + heading + body
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        row.setAlignment(Qt.AlignmentFlag.AlignTop)

        glyph = LifecycleWidget(revocable=i.requires_registry)
        # Larger size for hero-card use; resize from default 18px to 32px.
        glyph.setFixedSize(32, 32)
        row.addWidget(glyph, 0, Qt.AlignmentFlag.AlignTop)

        text_block = QVBoxLayout()
        text_block.setContentsMargins(0, 0, 0, 0)
        text_block.setSpacing(4)

        if i.requires_registry:
            heading_text = "Revocable"
            body_text = (
                "This schema requires registry anchoring. Issued credentials "
                "live in a TEL — the issuer can append a revocation event to "
                "mark a specific credential revoked. Verifiers should consult "
                "the TEL state, not just the SAID."
            )
        else:
            heading_text = "One-shot"
            body_text = (
                "No registry. Issued credentials are anchored once and "
                "cannot be revoked. The issuer's signature commits to the "
                "credential as-issued; verifiers trust it on its face. "
                "Appropriate for non-revocable attestations (a measurement, "
                "a transcript) but not for entitlements that must support "
                "withdrawal."
            )

        heading_lbl = QLabel(heading_text)
        heading_lbl.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {colors.TEXT_DARK};"
        )
        text_block.addWidget(heading_lbl)

        body_lbl = QLabel(body_text)
        body_lbl.setWordWrap(True)
        body_lbl.setStyleSheet(f"font-size: 12px; color: {colors.TEXT_SECONDARY};")
        text_block.addWidget(body_lbl)

        row.addLayout(text_block, 1)
        row_w = QWidget()
        row_w.setLayout(row)
        outer.addWidget(row_w)

        return frame

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
            enum_wrapper.setObjectName("sdEnumWrapper")
            enum_wrapper.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            enum_wrapper.setStyleSheet("QWidget#sdEnumWrapper { background: transparent; }")
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
    # §4.4 Chain of authority card (Phase B3b — mini-graph)
    # ------------------------------------------------------------------

    @staticmethod
    def _derive_tier(sd: Any) -> str:
        """Derive disclosure tier string from a SectionsDeclared object."""
        if sd.declares_aggregate:
            return "selective"
        if sd.declares_attribute and sd.declares_edges and sd.declares_rules:
            return "full"
        if sd.declares_attribute:
            return "partial"
        return "metadata"

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

        # --- No edges: "untethered" callout ---
        if not i.edge_requirements:
            untethered_lbl = QLabel(
                f"<b>{i.title or '(unnamed schema)'}</b> stands alone — "
                "this schema declares no edges to other schemas."
            )
            untethered_lbl.setWordWrap(True)
            untethered_lbl.setTextFormat(Qt.TextFormat.RichText)
            untethered_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            untethered_lbl.setStyleSheet(
                f"font-size: 13px; color: {colors.TEXT_SECONDARY}; font-style: italic; padding: 12px 0px;"
            )
            layout.addWidget(untethered_lbl)
            return frame

        # --- Mini-graph via QGraphicsView ---
        sd = i.declared_sections
        central_node = SchemaNode(
            said=i.schema_said,
            title=i.title or "(unnamed)",
            version=i.schema_version,
            is_targeted=i.requires_targeted,
            is_private=i.requires_nonce,
            disclosure_tier=self._derive_tier(sd),
            has_attribute=sd.declares_attribute,
            has_aggregate=sd.declares_aggregate,
            has_edges=sd.declares_edges,
            has_rules=sd.declares_rules,
            requires_registry=i.requires_registry,
            ghost=False,
        )

        scene = QGraphicsScene()
        scene.addItem(central_node)
        central_node.setPos(0, 0)

        # Column layout constants
        x_offset = NODE_WIDTH + NOTCH_DEPTH + 80
        vertical_step = NODE_HEIGHT + 20
        n = len(i.edge_requirements)
        # Center the column vertically with respect to the central node
        total_height = n * NODE_HEIGHT + (n - 1) * 20
        col_top_y = (NODE_HEIGHT - total_height) / 2

        for idx, edge in enumerate(i.edge_requirements):
            target_said = edge.target_schema_said
            target_y = col_top_y + idx * vertical_step

            # Determine if the target schema is in the wallet
            target_schemer = None
            if target_said:
                try:
                    target_schemer = vault.hby.db.schema.get(keys=(target_said,))
                except Exception:
                    target_schemer = None

            if target_schemer is not None and target_said:
                # Build full node from target schema inspection
                try:
                    ti = inspect_acdc_schema(target_schemer.sed)
                    tsd = ti.declared_sections
                    target_node = SchemaNode(
                        said=target_said,
                        title=ti.title or "(unnamed)",
                        version=ti.schema_version,
                        is_targeted=ti.requires_targeted,
                        is_private=ti.requires_nonce,
                        disclosure_tier=self._derive_tier(tsd),
                        has_attribute=tsd.declares_attribute,
                        has_aggregate=tsd.declares_aggregate,
                        has_edges=tsd.declares_edges,
                        has_rules=tsd.declares_rules,
                        requires_registry=ti.requires_registry,
                        ghost=False,
                    )
                except Exception:
                    logger.exception(f"Failed to inspect target schema {target_said}")
                    # Fall through to ghost
                    short_title = (target_said[:18] + "…") if len(target_said) > 20 else target_said
                    target_node = SchemaNode(
                        said=target_said,
                        title=short_title,
                        is_targeted=False,
                        ghost=True,
                    )
            elif target_said:
                # Not in wallet — ghost node
                short_title = (target_said[:18] + "…") if len(target_said) > 20 else target_said
                target_node = SchemaNode(
                    said=target_said,
                    title=short_title,
                    is_targeted=False,
                    ghost=True,
                )
            else:
                # No target SAID known; generic ghost
                target_node = SchemaNode(
                    said="(unknown)",
                    title=edge.name or "(unknown target)",
                    is_targeted=False,
                    ghost=True,
                )

            scene.addItem(target_node)
            target_node.setPos(x_offset, target_y)

            # Connect click to navigation
            _tsaid = target_said or ""
            if _tsaid:
                target_node.clicked.connect(
                    lambda _said=_tsaid: self.show_schema_detail_requested.emit(_said)
                )

            # Determine operator for the edge line
            if edge.operator_locked:
                op_str = edge.operator_locked
            elif edge.operator_constraint and len(edge.operator_constraint) > 0:
                op_str = edge.operator_constraint[0]
            else:
                op_str = "I2I"

            # Normalise to EdgeOperatorVisual literals
            if op_str not in ("I2I", "NI2I", "DI2I", "NOT"):
                op_str = "I2I"

            edge_line = EdgeLine(
                source=central_node,
                target=target_node,
                operator=op_str,  # type: ignore[arg-type]
                label=edge.name or None,
            )
            scene.addItem(edge_line)

        # Build the view
        view = QGraphicsView(scene)
        view.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setFrameShape(QFrame.Shape.NoFrame)
        view.setStyleSheet("background: transparent; border: none;")
        view.setFixedHeight(220)
        view.setMinimumWidth(300)

        # Fit the scene content into the view
        bounding = scene.itemsBoundingRect()
        view.fitInView(
            bounding.adjusted(-20, -20, 20, 20),
            Qt.AspectRatioMode.KeepAspectRatio,
        )

        layout.addWidget(view)
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
            ("Targeted — requires a.i (issuee AID)", i.requires_targeted),
            ("Private — requires u (nonce)", i.requires_nonce),
            ("Registry-backed — requires rd (or legacy ri)", i.requires_registry),
            ("Has message type — requires t", i.requires_message_type),
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
    show_issuer_requested = Signal(str, bool)  # (aid, is_self)
    add_permitted_issuer_clicked = Signal(str, str, str)     # (eco, said, aid)
    remove_permitted_issuer_clicked = Signal(str, str, str)  # (eco, said, aid)
    create_role_clicked = Signal(str)                         # ecosystem name
    delete_role_clicked = Signal(str, str)                    # (eco_name, role_name)
    set_qualification_rule_clicked = Signal(str, str, str)    # (eco, schema, role)
    remove_qualification_rule_clicked = Signal(str, str)      # (eco, schema)

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

        # Back bar
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

        # Header (rebuilt on refresh)
        self._header_holder = QWidget()
        self._header_holder.setObjectName("ecosystemDetailHeader")
        self._header_holder.setStyleSheet(
            f"#ecosystemDetailHeader {{ background-color: {colors.BACKGROUND_CONTENT}; }}"
            "#ecosystemDetailHeader QLabel { background: transparent; }"
        )
        self._header_layout = QVBoxLayout(self._header_holder)
        self._header_layout.setContentsMargins(20, 8, 20, 8)
        self._header_layout.setSpacing(6)
        outer.addWidget(self._header_holder)

        # Tab bar (Graph | List)
        tabs_holder = QWidget()
        tabs_holder.setObjectName("ecosystemDetailTabs")
        tabs_holder.setStyleSheet(
            f"#ecosystemDetailTabs {{ background-color: {colors.BACKGROUND_CONTENT};"
            f" border-bottom: 1px solid {colors.BORDER}; }}"
        )
        tabs_layout = QHBoxLayout(tabs_holder)
        tabs_layout.setContentsMargins(20, 0, 20, 0)
        tabs_layout.setSpacing(2)

        self._tab_btn_graph = QPushButton("Graph")
        self._tab_btn_list = QPushButton("List")
        for btn in (self._tab_btn_graph, self._tab_btn_list):
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(34)
            btn.setStyleSheet(
                "QPushButton {"
                f" background: transparent; border: none; padding: 0 14px;"
                f" font-size: 13px; color: {colors.TEXT_SECONDARY};"
                "}"
                "QPushButton:checked {"
                f" color: {colors.TEXT_DARK}; font-weight: 600;"
                f" border-bottom: 2px solid {colors.PRIMARY};"
                "}"
                "QPushButton:hover { color: " + colors.TEXT_DARK + "; }"
            )

        tab_group = QButtonGroup(self)
        tab_group.addButton(self._tab_btn_graph, 0)
        tab_group.addButton(self._tab_btn_list, 1)
        tab_group.setExclusive(True)
        self._tab_btn_graph.setChecked(True)

        tabs_layout.addWidget(self._tab_btn_graph)
        tabs_layout.addWidget(self._tab_btn_list)
        tabs_layout.addStretch()

        # "+ Add..." action holder (rebuilt on refresh so it can know the
        # current ecosystem name).
        self._add_btn_holder = QWidget()
        self._add_btn_holder_layout = QHBoxLayout(self._add_btn_holder)
        self._add_btn_holder_layout.setContentsMargins(0, 0, 0, 0)
        tabs_layout.addWidget(self._add_btn_holder)

        outer.addWidget(tabs_holder)

        # Content stack: graph view (index 0) | list scroll area (index 1)
        self._content_stack = QStackedWidget()
        outer.addWidget(self._content_stack, 1)

        # Graph tab
        self._graph_view = EcosystemGraphView()
        # Double-click on a node navigates to its detail page (schemas);
        # single-click opens the slide-in side panel (handled inside the
        # graph view). The panel's "Open detail page" / "Open in Contacts"
        # buttons emit these signals up the chain.
        self._graph_view.schema_double_clicked.connect(self.show_schema_detail_requested.emit)
        self._graph_view.open_schema_detail_requested.connect(self.show_schema_detail_requested.emit)
        self._graph_view.open_issuer_requested.connect(self.show_issuer_requested.emit)
        # Forward graph-canvas drag/right-click events to the same
        # signals the List-tab chip row already drives (Stage 11). The
        # graph view emits with (aid, schema_said); page-level signals
        # take (eco_name, schema_said, aid) — fold the eco_name in.
        self._graph_view.add_permitted_issuer_requested.connect(
            self._on_graph_add_permitted_issuer
        )
        self._graph_view.remove_permitted_issuer_requested.connect(
            self._on_graph_remove_permitted_issuer
        )
        self._content_stack.addWidget(self._graph_view)

        # List tab — wraps the previous scrollable layout.
        list_scroll = QScrollArea()
        list_scroll.setWidgetResizable(True)
        list_scroll.setFrameShape(QFrame.Shape.NoFrame)
        list_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        list_scroll.setStyleSheet(f"background-color: {colors.BACKGROUND_CONTENT}; border: none;")
        list_scroll.viewport().setStyleSheet(f"background-color: {colors.BACKGROUND_CONTENT};")

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
        list_scroll.setWidget(self._content)
        self._content_stack.addWidget(list_scroll)

        # Tab switching
        self._tab_btn_graph.clicked.connect(lambda: self._content_stack.setCurrentIndex(0))
        self._tab_btn_list.clicked.connect(lambda: self._content_stack.setCurrentIndex(1))

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

    def _on_graph_add_permitted_issuer(self, aid: str, said: str) -> None:
        if self._current_name is None:
            return
        self.add_permitted_issuer_clicked.emit(self._current_name, said, aid)

    def _on_graph_remove_permitted_issuer(self, aid: str, said: str) -> None:
        if self._current_name is None:
            return
        self.remove_permitted_issuer_clicked.emit(self._current_name, said, aid)

    def _refresh(self) -> None:
        # Clear header, add-button area, and the list tab's section widgets.
        self._purge_layout(self._header_layout)
        self._purge_layout(self._add_btn_holder_layout)
        while self._content_layout.count() > 1:
            item = self._content_layout.takeAt(0)
            w = item.widget() if item else None
            if w is not None:
                w.deleteLater()

        if self._db is None or self._current_name is None:
            self._header_layout.addWidget(QLabel("(no ecosystem loaded)"))
            return

        eco = self._db.get_ecosystem(self._current_name)
        if eco is None:
            self._header_layout.addWidget(
                QLabel(f"Ecosystem '{self._current_name}' not found.")
            )
            return

        # Header
        self._header_layout.addWidget(self._build_header(eco))

        # "+ Add..." action button — for v1 just two simple buttons; can
        # collapse into a dropdown menu later.
        add_schema_btn = LocksmithInvertedButton("+ Add schema")
        add_schema_btn.clicked.connect(lambda: self.add_schema_clicked.emit(eco.name))
        add_aid_btn = LocksmithInvertedButton("+ Add AID")
        add_aid_btn.clicked.connect(lambda: self.add_aid_clicked.emit(eco.name))
        self._add_btn_holder_layout.addWidget(add_schema_btn)
        self._add_btn_holder_layout.addWidget(add_aid_btn)

        # Graph tab — render the graph for this ecosystem.
        vault = getattr(self.app, "vault", None)
        self._graph_view.render_ecosystem(eco, vault)

        # List tab — keep the existing schemas/AIDs/actions sections.
        self._content_layout.insertWidget(0, self._build_schemas_section(eco))
        self._content_layout.insertWidget(1, self._build_roles_section(eco))
        self._content_layout.insertWidget(2, self._build_aids_section(eco))
        self._content_layout.insertWidget(3, self._build_actions_section(eco))

    @staticmethod
    def _purge_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget() if item else None
            if w is not None:
                w.deleteLater()

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
            layout.addWidget(self._build_schema_member_row(eco, said))
        return section

    def _build_schema_member_row(self, eco: Any, said: str) -> QWidget:
        row = QFrame()
        row.setObjectName("edSchemaMemberRow")
        row.setStyleSheet(
            "QFrame#edSchemaMemberRow { background: #F8F9FF; border-radius: 4px; }"
            "QFrame#edSchemaMemberRow QLabel { background: transparent; }"
        )
        rl = QVBoxLayout(row)
        rl.setContentsMargins(10, 6, 10, 6)
        rl.setSpacing(4)

        # Top row: SAID link + remove
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        link = QLabel(
            f'<a href="#nav" style="color:#3a5fff;text-decoration:none;">'
            f'<code>{said}</code></a>'
        )
        link.setOpenExternalLinks(False)
        link.linkActivated.connect(lambda _l, s=said: self.show_schema_detail_requested.emit(s))
        link.setStyleSheet("font-size: 12px;")
        link.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByMouse
            | Qt.TextInteractionFlag.TextSelectableByMouse
        )
        top.addWidget(link, 1)
        remove_btn = LocksmithIconButton(
            ":/assets/material-icons/close.svg",
            tooltip="Remove from ecosystem", icon_size=16,
        )
        remove_btn.clicked.connect(
            lambda _c=False, n=eco.name, s=said: self.remove_schema_clicked.emit(n, s)
        )
        top.addWidget(remove_btn)
        top_w = QWidget()
        top_w.setLayout(top)
        rl.addWidget(top_w)

        # Permitted issuers sub-row (Stage 9)
        rl.addWidget(self._build_permitted_issuers_row(eco, said))

        return row

    def _build_permitted_issuers_row(self, eco: Any, said: str) -> QWidget:
        wrap = QWidget()
        wrap.setObjectName("edAuthRow")
        wrap.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        wrap.setStyleSheet(
            "QWidget#edAuthRow { background: transparent; }"
            "QWidget#edAuthRow QLabel { background: transparent; }"
        )
        row = QHBoxLayout(wrap)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        prefix = QLabel("Permitted issuers:")
        prefix.setStyleSheet(
            f"font-size: 11px; color: {colors.TEXT_SECONDARY}; font-weight: 600;"
            " letter-spacing: 0.02em;"
        )
        row.addWidget(prefix)

        # "(via role: X)" indicator if a qualification rule is set.
        rule_role = eco.issuer_qualification_rules.get(said)
        if rule_role:
            role_lbl = QLabel(f"(via role: <b>{html.escape(rule_role)}</b>)")
            role_lbl.setStyleSheet(
                f"font-size: 11px; color: {colors.TEXT_DARK};"
            )
            row.addWidget(role_lbl)

        permitted = eco.permitted_issuers.get(said, [])
        if not permitted:
            none_lbl = QLabel("any ecosystem issuer accepted")
            none_lbl.setStyleSheet(
                f"font-size: 11px; color: {colors.TEXT_SECONDARY}; font-style: italic;"
            )
            row.addWidget(none_lbl)
        else:
            for aid in permitted:
                row.addWidget(self._build_permitted_chip(eco, said, aid))

        # "+" add button — only enabled when there are eligible AIDs to add.
        eligible = [a for a in eco.issuer_aids if a not in permitted]
        add_btn = QToolButton()
        add_btn.setText("+")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if eligible:
            tip = "Add an permitted issuer for this schema in this ecosystem"
        elif not eco.issuer_aids:
            tip = (
                "Add an issuer AID to this ecosystem first — "
                "use the Issuer AIDs section below."
            )
        else:
            tip = "All ecosystem issuers are already permitted for this schema"
        add_btn.setToolTip(tip)
        add_btn.setEnabled(bool(eligible))
        add_btn.setStyleSheet(
            "QToolButton {"
            f" background: white; border: 1px dashed {colors.BORDER};"
            f" border-radius: 9px; padding: 0px 6px; min-height: 18px;"
            f" font-size: 11px; color: {colors.TEXT_SECONDARY};"
            "}"
            f"QToolButton:hover {{ border-color: {colors.PRIMARY};"
            f" color: {colors.PRIMARY}; }}"
            f"QToolButton:disabled {{ color: {colors.TEXT_MUTED};"
            f" border-color: {colors.BORDER}; }}"
        )
        add_btn.clicked.connect(
            lambda _c=False, e=eco, s=said: self._show_add_permitted_menu(e, s)
        )
        row.addWidget(add_btn)
        row.addStretch()
        return wrap

    def _build_permitted_chip(self, eco: Any, said: str, aid: str) -> QWidget:
        wrap = QFrame()
        wrap.setObjectName("edAuthChip")
        wrap.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        wrap.setStyleSheet(
            "QFrame#edAuthChip {"
            f" background: {colors.BACKGROUND_SELECTION};"
            " border-radius: 9px; padding: 0px 4px 0px 8px; min-height: 18px;"
            "}"
            "QFrame#edAuthChip QLabel { background: transparent; }"
        )
        wrap.setCursor(Qt.CursorShape.PointingHandCursor)
        h = QHBoxLayout(wrap)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(2)
        h.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        alias = self._alias_for_aid(aid)
        is_self = self._is_self_aid(aid)
        label = QLabel(alias)
        label.setStyleSheet(
            f"font-size: 11px; color: {colors.TEXT_DARK};"
            + (f" font-weight: 600;" if is_self else "")
        )
        label.setToolTip(aid)
        h.addWidget(label)

        rm = QToolButton()
        rm.setText("×")
        rm.setCursor(Qt.CursorShape.PointingHandCursor)
        rm.setToolTip("Remove as permitted issuer for this schema")
        rm.setStyleSheet(
            "QToolButton {"
            f" background: transparent; border: none; padding: 0px 4px;"
            f" font-size: 13px; color: {colors.TEXT_SECONDARY};"
            "}"
            f"QToolButton:hover {{ color: {colors.DANGER}; }}"
        )
        rm.clicked.connect(
            lambda _c=False, n=eco.name, s=said, a=aid:
                self.remove_permitted_issuer_clicked.emit(n, s, a)
        )
        h.addWidget(rm)

        # Click anywhere on the chip (except the × button) navigates to the
        # contact / identifier surface.
        wrap.mousePressEvent = (
            lambda _ev, a=aid, s=is_self:
                self.show_issuer_requested.emit(a, s)
        )
        return wrap

    def _show_add_permitted_menu(self, eco: Any, said: str) -> None:
        already = set(eco.permitted_issuers.get(said, []))
        eligible = [a for a in eco.issuer_aids if a not in already]
        if not eligible:
            return
        menu = QMenu(self)
        for aid in eligible:
            alias = self._alias_for_aid(aid)
            action = menu.addAction(f"{alias}  —  {aid[:14]}…")
            action.triggered.connect(
                lambda _c=False, n=eco.name, s=said, a=aid:
                    self.add_permitted_issuer_clicked.emit(n, s, a)
            )
        menu.exec(QCursor.pos())

    def _alias_for_aid(self, aid: str) -> str:
        vault = getattr(self.app, "vault", None)
        if vault is None or not aid:
            return aid[:14] + "…" if len(aid) > 16 else aid
        try:
            for c in vault.org.list():
                if c.get("id") == aid:
                    a = c.get("alias")
                    if a:
                        return a
        except Exception:
            pass
        try:
            hab = vault.hby.habByPre(aid)
            if hab is not None and hab.name:
                return f"{hab.name} (mine)"
        except Exception:
            pass
        return aid[:14] + "…" if len(aid) > 16 else aid

    def _is_self_aid(self, aid: str) -> bool:
        vault = getattr(self.app, "vault", None)
        if vault is None:
            return False
        try:
            return any(hab.pre == aid for hab in vault.hby.habs.values())
        except Exception:
            return False

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

    def _build_roles_section(self, eco: Any) -> QWidget:
        section = QFrame()
        section.setObjectName("edRolesSection")
        section.setStyleSheet(
            "QFrame#edRolesSection { background-color: white;"
            " border: 1px solid #E0E3EA; border-radius: 8px; }"
            "QFrame#edRolesSection QLabel { background: transparent; }"
        )
        layout = QVBoxLayout(section)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        # Header row.
        head = QHBoxLayout()
        title = QLabel(f"Roles ({len(eco.role_names)})")
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        head.addWidget(title)
        head.addStretch()
        add_btn = LocksmithInvertedButton("Add role")
        add_btn.clicked.connect(lambda: self.create_role_clicked.emit(eco.name))
        head.addWidget(add_btn)
        head_w = QWidget()
        head_w.setLayout(head)
        layout.addWidget(head_w)

        # Brief explainer for first-time users.
        explainer = QLabel(
            "A role is a credential-qualified class of AID — anyone holding "
            "the qualification credential automatically qualifies. Roles "
            "replace AID-by-AID enumeration for permitted-issuer policies."
        )
        explainer.setWordWrap(True)
        explainer.setStyleSheet(
            f"color: {colors.TEXT_SECONDARY}; font-size: 12px;"
            " font-style: italic;"
        )
        layout.addWidget(explainer)

        if not eco.role_names:
            layout.addWidget(EmptyStateCard(
                "No roles defined yet. Click 'Add role' to define a "
                "credential-qualified class of AID."
            ))
            return section

        # Role cards. The DB stores roles individually; pull each by name.
        for role_name in eco.role_names:
            if self._db is None:
                continue
            role = self._db.get_role(eco.name, role_name)
            if role is None:
                continue
            layout.addWidget(self._build_role_card(eco, role))
        return section

    def _build_role_card(self, eco: Any, role: Any) -> QWidget:
        """One card per role: name, qualification schema (linked),
        issuer role (linked or "(root)"), root AIDs count, resolved
        member count."""
        card = QFrame()
        card.setObjectName("edRoleCard")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card.setStyleSheet(
            "QFrame#edRoleCard {"
            f" background: {colors.BACKGROUND_SELECTION};"
            " border-radius: 6px; padding: 10px 12px;"
            "}"
            "QFrame#edRoleCard QLabel { background: transparent; }"
        )
        # Right-click context menu wired in Task 3.
        card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        card.customContextMenuRequested.connect(
            lambda pos, n=eco.name, r=role.name: self._show_role_context_menu(n, r, pos, card)
        )

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Top row: name
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        name_lbl = QLabel(f"<b>{html.escape(role.name)}</b>")
        name_lbl.setStyleSheet(f"font-size: 14px; color: {colors.TEXT_DARK};")
        head.addWidget(name_lbl)
        head.addStretch()
        head_w = QWidget()
        head_w.setLayout(head)
        layout.addWidget(head_w)

        if role.description:
            desc = QLabel(html.escape(role.description))
            desc.setStyleSheet(f"font-size: 12px; color: {colors.TEXT_SECONDARY};")
            desc.setWordWrap(True)
            layout.addWidget(desc)

        # Qualification schema (clickable to schema detail).
        if role.qualification_schema_said:
            qual_html = (
                f"<span style='color:{colors.TEXT_SECONDARY}'>"
                f"Qualification credential:</span> "
                f"<a href='#nav' style='color:{colors.BLUE_BORDER};"
                "text-decoration:none;'>"
                f"{html.escape(role.qualification_schema_said[:20])}…</a>"
            )
            qual = QLabel(qual_html)
            qual.setOpenExternalLinks(False)
            qual.setStyleSheet("font-size: 11px;")
            qual.linkActivated.connect(
                lambda _l, s=role.qualification_schema_said:
                    self.show_schema_detail_requested.emit(s)
            )
            layout.addWidget(qual)

        # Issuer role.
        if role.issuer_role_name:
            issuer = QLabel(
                f"<span style='color:{colors.TEXT_SECONDARY}'>"
                f"Issued by role:</span> <b>{html.escape(role.issuer_role_name)}</b>"
            )
        else:
            issuer = QLabel(
                f"<span style='color:{colors.TEXT_SECONDARY}'>"
                f"Trust root:</span> "
                f"<b>{len(role.root_issuer_aids)} AID(s)</b>"
            )
        issuer.setStyleSheet("font-size: 11px;")
        layout.addWidget(issuer)

        # Resolved member count (computes via resolver — vault-dependent).
        member_count = self._resolve_role_member_count(eco.name, role.name)
        if member_count is None:
            count_text = "Members: (vault unavailable)"
        else:
            count_text = f"<b>{member_count}</b> current member{'s' if member_count != 1 else ''}"
        count_lbl = QLabel(count_text)
        count_lbl.setStyleSheet(f"font-size: 11px; color: {colors.TEXT_SECONDARY};")
        layout.addWidget(count_lbl)

        return card

    def _resolve_role_member_count(self, eco_name: str, role_name: str) -> int | None:
        """Resolve current role membership and return the count. Returns
        None if vault is unavailable. Tolerates resolver errors (e.g.,
        cycle detection) by returning 0 with a logged warning."""
        if self._db is None:
            return None
        vault = getattr(self.app, "vault", None)
        if vault is None:
            return None
        try:
            from locksmith.plugins.ecosystem_viewer.plugin import vault_credential_finder
            finder = vault_credential_finder(vault)
            members = self._db.resolve_role_members(eco_name, role_name, finder)
            return len(members)
        except ValueError:
            # Cycle detected — show 0 rather than crashing the page render.
            logger.exception(
                f"Role-chain cycle in '{eco_name}/{role_name}'; rendering 0 members"
            )
            return 0
        except Exception:
            logger.exception("Unexpected resolver error")
            return 0

    def _show_role_context_menu(self, eco_name: str, role_name: str,
                                pos: Any, anchor: QWidget) -> None:
        """Stub — populated in Task 3 with Edit / Delete entries."""
        # Intentionally empty until Task 3.
        return

    def _build_actions_section(self, eco: Any) -> QWidget:
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch()
        delete_btn = LocksmithInvertedButton("Delete ecosystem")
        delete_btn.clicked.connect(lambda: self.delete_ecosystem_clicked.emit(eco.name))
        layout.addWidget(delete_btn)
        return wrapper


class _DashedCircle(QWidget):
    """Painted dashed-outline circle used as the 'absent role'
    placeholder in the Parties card when a schema is untargeted."""

    def __init__(self, diameter: int = 40, parent: QWidget | None = None):
        super().__init__(parent)
        self._diameter = diameter
        self.setFixedSize(diameter, diameter)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor(colors.TEXT_SECONDARY), 1.5)
        pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        d = self._diameter
        p.drawEllipse(2, 2, d - 4, d - 4)
        p.end()
