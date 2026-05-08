# -*- encoding: utf-8 -*-
"""
locksmith.plugins.ecosystem_viewer.graph_view module

EcosystemGraphView — the QGraphicsView that hosts the full ecosystem
graph (design §5). Renders SchemaNodes (and ghost-schema placeholders),
IssuerNodes, and the chain-of-authority + membership edges between
them, laid out by `layout.layout_hierarchical`.

Concerns:
- Building the scene from inputs (inspector + ecosystem record + vault).
- Pan (ScrollHandDrag), Ctrl+wheel zoom, fit-to-content, relayout.
- Bottom toolbar with stats line, zoom controls, fit/relayout buttons.
- Emitting selection / navigate signals for the surrounding page to
  wire to the side details panel and intra-plugin navigation.

Out of scope here (handled in their own Phase D tasks):
- The slide-in side details panel (Phase D4).
- Tabbed Graph/List view inside EcosystemDetailPage (Phase D5).
- Empty/sparse-state polish + ghost-node "add to wallet" popovers
  (Phase D6).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QWheelEvent
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from keri import help

logger = help.ogler.getLogger(__name__)


def _short_aid(aid: str, head: int = 10, tail: int = 4) -> str:
    if len(aid) <= head + tail + 1:
        return aid
    return f"{aid[:head]}…{aid[-tail:]}"

from locksmith.acdc import icons as acdc_icons
from locksmith.acdc import inspect_acdc_schema
from locksmith.plugins.ecosystem_viewer.graph_items import (
    EdgeLine,
    IssuerNode,
    ISSUER_NODE_DIAMETER,
    ISSUER_TOTAL_HEIGHT,
    MembershipEdge,
    NODE_HEIGHT,
    NODE_WIDTH,
    NOTCH_DEPTH,
    SchemaNode,
)
from locksmith.plugins.ecosystem_viewer.layout import (
    LayoutOptions,
    LayoutResult,
    layout_hierarchical,
)
from locksmith.plugins.ecosystem_viewer.side_panel import PANEL_WIDTH, SidePanel
from locksmith.ui import colors
from locksmith.ui.toolkit.widgets.buttons import LocksmithIconButton


# ---------------------------------------------------------------------------
# Build inputs
# ---------------------------------------------------------------------------


@dataclass
class GraphBuildResult:
    """Bookkeeping returned by _build_scene so the surrounding page can
    show stats, find nodes by id, etc."""

    schema_nodes: dict = field(default_factory=dict)   # said -> SchemaNode
    issuer_nodes: dict = field(default_factory=dict)   # aid -> IssuerNode
    chain_edges: list = field(default_factory=list)    # EdgeLine instances
    membership_edges: list = field(default_factory=list)
    unresolved_count: int = 0
    feedback_edge_count: int = 0
    # Cached domain data so the side panel can render without re-inspecting.
    inspections: dict = field(default_factory=dict)    # said -> ACDCSchemaInspection
    schema_edges_by_src: dict = field(default_factory=dict)  # said -> list[(dst, op)]
    schema_edges_by_dst: dict = field(default_factory=dict)  # said -> list[(src, op)]
    issuer_meta: dict = field(default_factory=dict)    # aid -> {alias, kever, is_self, oobi}


# ---------------------------------------------------------------------------
# EcosystemGraphView
# ---------------------------------------------------------------------------


class EcosystemGraphView(QWidget):
    """Top-level widget holding a QGraphicsView (graph canvas) above a
    bottom toolbar (zoom controls + stats). Signals selection and
    navigate-to-detail events upward."""

    schema_selected = Signal(str)       # emits schema SAID
    issuer_selected = Signal(str)       # emits AID
    schema_double_clicked = Signal(str)
    issuer_double_clicked = Signal(str)
    selection_cleared = Signal()
    relayout_requested = Signal()       # surfaced in case the page wants to react
    open_schema_detail_requested = Signal(str)   # emits SAID — from side panel
    open_issuer_requested = Signal(str, bool)    # emits (aid, is_self) — from side panel

    MIN_ZOOM = 0.25
    MAX_ZOOM = 4.0

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._build_chrome()
        self._build_result: GraphBuildResult | None = None
        self._selected_node: Any | None = None  # SchemaNode | IssuerNode | None
        self._eco: Any | None = None  # last-rendered EcosystemRecord

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    def _build_chrome(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scene = QGraphicsScene(self)
        self._scene.setBackgroundBrush(QColor(colors.BACKGROUND_CONTENT))

        self._view = _GraphView(self._scene, self)
        self._view.setFrameShape(QFrame.Shape.NoFrame)
        self._view.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._view.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        self._view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self._view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self._view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._view.setBackgroundBrush(QColor(colors.BACKGROUND_CONTENT))
        self._view.setStyleSheet(
            f"QGraphicsView {{ background-color: {colors.BACKGROUND_CONTENT}; }}"
        )
        self._view.background_clicked.connect(self._on_background_clicked)
        outer.addWidget(self._view, 1)

        # Bottom toolbar
        bar = QFrame()
        bar.setObjectName("egvBottomBar")
        bar.setFixedHeight(36)
        bar.setStyleSheet(
            "QFrame#egvBottomBar {"
            f" background-color: {colors.BACKGROUND_CONTENT};"
            f" border-top: 1px solid {colors.BORDER};"
            "}"
            "QFrame#egvBottomBar QLabel { background: transparent; }"
        )
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(12, 4, 12, 4)
        bar_layout.setSpacing(10)

        self._stats_lbl = QLabel("0 schemas · 0 chain-edges · 0 unresolved")
        self._stats_lbl.setStyleSheet(f"font-size: 11px; color: {colors.TEXT_SECONDARY};")
        bar_layout.addWidget(self._stats_lbl)

        bar_layout.addStretch()

        zoom_out = QToolButton()
        zoom_out.setText("−")
        zoom_out.setToolTip("Zoom out")
        zoom_out.setCursor(Qt.CursorShape.PointingHandCursor)
        zoom_out.setFixedSize(24, 24)
        zoom_out.clicked.connect(lambda: self._zoom_by(1 / 1.2))
        bar_layout.addWidget(zoom_out)

        self._zoom_lbl = QLabel("100%")
        self._zoom_lbl.setStyleSheet(f"font-size: 11px; color: {colors.TEXT_SECONDARY};")
        self._zoom_lbl.setFixedWidth(40)
        self._zoom_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._zoom_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        # Click resets to 100%.
        self._zoom_lbl.mousePressEvent = lambda _e: self.reset_zoom()
        bar_layout.addWidget(self._zoom_lbl)

        zoom_in = QToolButton()
        zoom_in.setText("+")
        zoom_in.setToolTip("Zoom in")
        zoom_in.setCursor(Qt.CursorShape.PointingHandCursor)
        zoom_in.setFixedSize(24, 24)
        zoom_in.clicked.connect(lambda: self._zoom_by(1.2))
        bar_layout.addWidget(zoom_in)

        fit_btn = LocksmithIconButton(
            acdc_icons.ICON_FIT_TO_CONTENT, tooltip="Fit graph to view", icon_size=16
        )
        fit_btn.clicked.connect(self.fit_to_content)
        bar_layout.addWidget(fit_btn)

        relayout_btn = LocksmithIconButton(
            acdc_icons.ICON_RELAYOUT, tooltip="Re-run layout", icon_size=16
        )
        relayout_btn.clicked.connect(self._on_relayout_clicked)
        bar_layout.addWidget(relayout_btn)

        outer.addWidget(bar, 0)

        # Floating side panel overlay (parent = self so it sits on top
        # of the graph canvas without affecting layout).
        self._side_panel = SidePanel(parent=self)
        self._side_panel.open_schema_detail.connect(self.open_schema_detail_requested.emit)
        self._side_panel.open_issuer.connect(self.open_issuer_requested.emit)
        self._side_panel.schema_link_clicked.connect(self._on_panel_schema_link)

        # Centered overlay hint (empty / sparse states).
        self._hint_label = QLabel("", parent=self)
        self._hint_label.setObjectName("egvHintLabel")
        self._hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint_label.setWordWrap(True)
        self._hint_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._hint_label.setStyleSheet(
            "QLabel#egvHintLabel {"
            f" color: {colors.TEXT_SECONDARY}; font-size: 13px; font-style: italic;"
            " background: transparent;"
            "}"
        )
        self._hint_label.hide()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render_ecosystem(self, eco: Any, vault: Any) -> GraphBuildResult:
        """Rebuild the scene for the given ecosystem record + vault."""
        self._scene.clear()
        self._selected_node = None
        # Close any open side panel — the previously selected node no
        # longer exists in the new scene.
        self._side_panel.close()
        # Cache the ecosystem record so the side panel can render
        # authoritative-issuer info for selected schemas (Stage 9).
        self._eco = eco
        result = self._build_scene(eco, vault)
        self._build_result = result
        self._update_stats(result)
        self._update_hint(result)
        # Defer a fit-to-content until the view has a real size; if called
        # before the widget has been shown the fitInView is a no-op.
        self.fit_to_content()
        self._reposition_panel()
        return result

    def _update_hint(self, result: GraphBuildResult) -> None:
        """Surface an explainer overlay for empty/sparse ecosystems (§5.9)."""
        n_real_schemas = sum(1 for n in result.schema_nodes.values() if not n.ghost)
        n_issuers = len(result.issuer_nodes)
        n_chain = len(result.chain_edges)
        total_members = n_real_schemas + n_issuers

        if total_members == 0:
            self._hint_label.setText(
                "This ecosystem has no members yet.\n"
                "Add a schema or an issuer AID to start mapping it."
            )
            self._hint_label.show()
        elif total_members == 1:
            self._hint_label.setText(
                "This ecosystem has only one member. "
                "Add more to see chain-of-authority."
            )
            self._hint_label.show()
        elif n_real_schemas >= 2 and n_chain == 0:
            self._hint_label.setText(
                "These members declare no chain-of-authority between each other. "
                "Their relationships are flat."
            )
            self._hint_label.show()
        else:
            self._hint_label.hide()
        self._reposition_hint()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_panel()
        self._reposition_hint()

    def _reposition_hint(self) -> None:
        if not hasattr(self, "_hint_label"):
            return
        if not self._hint_label.isVisible():
            return
        # Center horizontally; sit just above the bottom toolbar.
        margin = 24
        max_w = max(0, self.width() - 2 * margin)
        self._hint_label.setMaximumWidth(max_w)
        size = self._hint_label.sizeHint()
        x = (self.width() - size.width()) // 2
        # Above the 36px bottom toolbar with a small gap.
        y = self.height() - 36 - size.height() - 16
        self._hint_label.setGeometry(x, y, size.width(), size.height())
        self._hint_label.raise_()

    def _reposition_panel(self) -> None:
        """Tell the side panel about the new parent geometry — the panel
        anchors its X to the right edge based on its own (animated) width."""
        if not hasattr(self, "_side_panel"):
            return
        self._side_panel.reposition(self.width(), self.height())
        self._side_panel.raise_()

    def fit_to_content(self) -> None:
        """Auto-fit the scene to the viewport with 40px padding.

        Clamps the resulting zoom to at most 1.0 so a single small graph
        doesn't blow up to fill the entire canvas — past 100% the nodes
        look comically large and lose all glyph legibility."""
        rect = self._scene.itemsBoundingRect()
        if rect.isEmpty():
            return
        rect.adjust(-40, -40, 40, 40)
        self._view.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        # If fit zoomed in past 1.0, dial back and re-center.
        cur = self._view.transform().m11()
        if cur > 1.0:
            self._view.resetTransform()
            self._view.centerOn(rect.center())
        self._sync_zoom_label()

    def reset_zoom(self) -> None:
        self._view.resetTransform()
        self._sync_zoom_label()

    def select_schema(self, said: str) -> None:
        """Programmatically select a schema node (e.g., from the side panel)."""
        if self._build_result is None:
            return
        node = self._build_result.schema_nodes.get(said)
        if node is None:
            return
        self._set_selected_node(node)
        self.schema_selected.emit(said)

    # ------------------------------------------------------------------
    # Scene construction
    # ------------------------------------------------------------------

    def _build_scene(self, eco: Any, vault: Any) -> GraphBuildResult:
        result = GraphBuildResult()

        # Step 1: enumerate member schemas (resolved + ghost) and member AIDs.
        resolved_schemas: dict[str, Any] = {}      # said -> inspection
        for said in eco.schema_saids:
            schemer = vault.hby.db.schema.get(keys=(said,)) if vault else None
            if schemer is None:
                continue
            try:
                resolved_schemas[said] = inspect_acdc_schema(schemer.sed)
            except Exception:
                continue
        result.inspections = dict(resolved_schemas)

        # Edges: every chain-of-authority edge declared by member schemas
        # whose target is also a member of this ecosystem (resolved or not).
        member_said_set = set(eco.schema_saids)
        chain_edges: list[tuple[str, str, str]] = []
        # (src_said, dst_said, operator)
        unresolved_targets: set[str] = set()
        for said, insp in resolved_schemas.items():
            for edge in insp.edge_requirements:
                target = edge.target_schema_said
                if not target:
                    continue
                if target in member_said_set:
                    op = edge.operator_locked or (
                        edge.operator_constraint[0]
                        if edge.operator_constraint else "I2I"
                    )
                    chain_edges.append((said, target, op))
                    result.schema_edges_by_src.setdefault(said, []).append((target, op))
                    result.schema_edges_by_dst.setdefault(target, []).append((said, op))
                    if target not in resolved_schemas:
                        unresolved_targets.add(target)

        result.unresolved_count = len(unresolved_targets)

        # Step 2: build SchemaNodes for resolved members.
        for said, insp in resolved_schemas.items():
            sd = insp.declared_sections
            if sd.declares_aggregate:
                tier = "selective"
            elif sd.declares_attribute and sd.declares_edges and sd.declares_rules:
                tier = "full"
            elif sd.declares_attribute:
                tier = "partial"
            else:
                tier = "metadata"
            node = SchemaNode(
                said=said,
                title=insp.title or "(unnamed)",
                version=insp.schema_version,
                is_targeted=insp.requires_targeted,
                is_private=insp.requires_nonce,
                disclosure_tier=tier,
                has_attribute=sd.declares_attribute,
                has_aggregate=sd.declares_aggregate,
                has_edges=sd.declares_edges,
                has_rules=sd.declares_rules,
                requires_registry=insp.requires_registry,
                ghost=False,
            )
            node.clicked.connect(self._on_schema_clicked)
            node.double_clicked.connect(self.schema_double_clicked.emit)
            self._scene.addItem(node)
            result.schema_nodes[said] = node

        # Step 3: build ghost SchemaNodes for unresolved-but-referenced targets.
        for said in unresolved_targets:
            ghost = SchemaNode(
                said=said,
                title="(unresolved)",
                version=None,
                is_targeted=False,
                is_private=False,
                disclosure_tier="metadata",
                has_attribute=False,
                has_aggregate=False,
                has_edges=False,
                has_rules=False,
                ghost=True,
            )
            ghost.clicked.connect(self._on_schema_clicked)
            self._scene.addItem(ghost)
            result.schema_nodes[said] = ghost

        # Step 4: build IssuerNodes for ecosystem-member AIDs.
        try:
            self_aids = {hab.pre for hab in vault.hby.habs.values()}
        except Exception:
            self_aids = set()

        for aid in eco.issuer_aids:
            kever = vault.hby.kevers.get(aid) if vault else None
            alias = self._resolve_alias(vault, aid)
            is_self = aid in self_aids
            issuer = IssuerNode(
                aid=aid,
                alias=alias,
                sn=kever.sn if kever is not None else None,
                is_self=is_self,
            )
            issuer.clicked.connect(self._on_issuer_clicked)
            issuer.double_clicked.connect(self.issuer_double_clicked.emit)
            self._scene.addItem(issuer)
            result.issuer_nodes[aid] = issuer
            result.issuer_meta[aid] = {
                "alias": alias,
                "kever": kever,
                "is_self": is_self,
            }

        # Step 5: layout. Schema nodes participate in chain-of-authority
        # layering; issuer nodes get pinned to the bottom row.
        all_node_ids: list[str] = list(result.schema_nodes.keys()) + list(
            result.issuer_nodes.keys()
        )
        layout_edges: list[tuple[str, str]] = [
            (src, dst) for (src, dst, _op) in chain_edges
        ]
        layout_opts = LayoutOptions(
            node_width=NODE_WIDTH + NOTCH_DEPTH,
            node_height=NODE_HEIGHT,
            layer_spacing=80,
            node_spacing=40,
        )
        layout_result: LayoutResult = layout_hierarchical(
            nodes=all_node_ids,
            edges=layout_edges,
            bottom_row_nodes=list(result.issuer_nodes.keys()),
            options=layout_opts,
        )
        result.feedback_edge_count = len(layout_result.feedback_edges)

        # Step 6: place nodes at their layout coordinates.
        for said, node in result.schema_nodes.items():
            x, y = layout_result.positions.get(said, (0, 0))
            # Anchor at top-left corner; the layout returns positions
            # already centered such that x is the left edge of the slot.
            node.setPos(x, y)

        for aid, issuer in result.issuer_nodes.items():
            x, y = layout_result.positions.get(aid, (0, 0))
            # Issuer nodes are narrower than schema nodes; nudge to center
            # within the slot so the bottom-row alignment looks tidy.
            offset = (NODE_WIDTH + NOTCH_DEPTH - ISSUER_NODE_DIAMETER) / 2
            issuer.setPos(x + offset, y)

        # Step 7: draw chain-of-authority edges.
        for src, dst, op in chain_edges:
            src_node = result.schema_nodes.get(src)
            dst_node = result.schema_nodes.get(dst)
            if src_node is None or dst_node is None:
                continue
            # Map the operator to one of the EdgeLine-supported visuals.
            visual_op = op if op in ("I2I", "NI2I", "DI2I", "NOT") else "I2I"
            edge = EdgeLine(
                source=src_node,
                target=dst_node,
                operator=visual_op,
            )
            self._scene.addItem(edge)
            result.chain_edges.append(edge)

        # Step 8: membership edges (schema → issuer). For v1 we don't have
        # per-schema authoritative-issuer mapping (that's stage 9); draw a
        # membership line from each issuer to every schema in the ecosystem
        # so the user can see the cluster. This will become more meaningful
        # once the EGF overlay lands.
        # NOTE: deliberately commented out — until we have the EGF overlay,
        # all-pairs membership lines turn the canvas into a hairball. Better
        # to omit them entirely and let issuer nodes float as a row.
        # for issuer in result.issuer_nodes.values():
        #     for schema in result.schema_nodes.values():
        #         if schema.ghost:
        #             continue
        #         m = MembershipEdge(source=schema, target=issuer)
        #         self._scene.addItem(m)
        #         result.membership_edges.append(m)

        return result

    @staticmethod
    def _resolve_alias(vault: Any, aid: str) -> str:
        if vault is None or not aid:
            return aid[:14] + "…" if len(aid) > 16 else aid
        # Try contacts first, then habs.
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

    # ------------------------------------------------------------------
    # Selection + zoom plumbing
    # ------------------------------------------------------------------

    def _on_schema_clicked(self, said: str) -> None:
        if self._build_result is None:
            return
        node = self._build_result.schema_nodes.get(said)
        if node is None:
            return
        self._set_selected_node(node)
        self._populate_panel_for_schema(said)
        # Recompute geometry — the panel may have been positioned when
        # the widget hadn't yet received its final size.
        self._reposition_panel()
        self.schema_selected.emit(said)

    def _on_issuer_clicked(self, aid: str) -> None:
        if self._build_result is None:
            return
        node = self._build_result.issuer_nodes.get(aid)
        if node is None:
            return
        self._set_selected_node(node)
        self._populate_panel_for_issuer(aid)
        self.issuer_selected.emit(aid)

    def _on_background_clicked(self) -> None:
        if self._selected_node is None:
            return
        self._set_selected_node(None)
        self._side_panel.close()
        self.selection_cleared.emit()

    def _on_panel_schema_link(self, said: str) -> None:
        """Side panel surfaced an in-graph link to another schema —
        select that node (which repopulates the panel)."""
        self._on_schema_clicked(said)

    def _populate_panel_for_schema(self, said: str) -> None:
        if self._build_result is None:
            return
        inspection = self._build_result.inspections.get(said)
        # Title map for edge link labels.
        titles: dict[str, str] = {}
        for s, insp in self._build_result.inspections.items():
            titles[s] = insp.title or "(unnamed)"

        edges_in = self._build_result.schema_edges_by_dst.get(said, [])
        if inspection is None:
            # Ghost node — render the unresolved-schema panel instead.
            self._side_panel.show_ghost(
                said=said, edges_in=edges_in, schema_titles=titles,
            )
            return
        edges_out = self._build_result.schema_edges_by_src.get(said, [])

        # Authoritative issuers (Stage 9): pull from cached ecosystem record
        # and resolve each AID's alias / is_self via cached issuer metadata.
        auth_aids: list[str] = []
        ecosystem_has_issuers = False
        if self._eco is not None:
            ecosystem_has_issuers = bool(self._eco.issuer_aids)
            auth_aids = list(
                self._eco.authoritative_issuers.get(said, []) or []
            )
        authoritative: list[tuple[str, str, bool]] = []
        for aid in auth_aids:
            meta = self._build_result.issuer_meta.get(aid, {})
            alias = meta.get("alias") or _short_aid(aid)
            is_self = bool(meta.get("is_self"))
            authoritative.append((aid, alias, is_self))

        self._side_panel.show_schema(
            inspection=inspection,
            edges_out=edges_out,
            edges_in=edges_in,
            schema_titles=titles,
            authoritative_issuers=authoritative,
            ecosystem_has_issuers=ecosystem_has_issuers,
        )

    def _populate_panel_for_issuer(self, aid: str) -> None:
        if self._build_result is None:
            return
        meta = self._build_result.issuer_meta.get(aid)
        if meta is None:
            self._side_panel.close()
            return
        self._side_panel.show_issuer(aid=aid, meta=meta)

    def _set_selected_node(self, node: Any | None) -> None:
        if self._selected_node is node:
            return
        if self._selected_node is not None and hasattr(self._selected_node, "set_selected"):
            self._selected_node.set_selected(False)
        self._selected_node = node
        if node is not None and hasattr(node, "set_selected"):
            node.set_selected(True)

    def _zoom_by(self, factor: float) -> None:
        cur = self._view.transform().m11()
        new = cur * factor
        if new < self.MIN_ZOOM:
            factor = self.MIN_ZOOM / cur
        elif new > self.MAX_ZOOM:
            factor = self.MAX_ZOOM / cur
        self._view.scale(factor, factor)
        self._sync_zoom_label()

    def _sync_zoom_label(self) -> None:
        cur = self._view.transform().m11()
        self._zoom_lbl.setText(f"{int(round(cur * 100))}%")

    def _on_relayout_clicked(self) -> None:
        self.relayout_requested.emit()

    def _update_stats(self, result: GraphBuildResult) -> None:
        n_schemas = sum(1 for n in result.schema_nodes.values() if not n.ghost)
        n_chain = len(result.chain_edges)
        n_unres = result.unresolved_count
        feedback = (
            f" · {result.feedback_edge_count} feedback"
            if result.feedback_edge_count else ""
        )
        n_issuers = len(result.issuer_nodes)
        self._stats_lbl.setText(
            f"{n_schemas} schema{'s' if n_schemas != 1 else ''} · "
            f"{n_issuers} issuer{'s' if n_issuers != 1 else ''} · "
            f"{n_chain} chain-edge{'s' if n_chain != 1 else ''} · "
            f"{n_unres} unresolved"
            f"{feedback}"
        )


# ---------------------------------------------------------------------------
# Inner QGraphicsView with Ctrl+wheel zoom + background-click signal
# ---------------------------------------------------------------------------


class _GraphView(QGraphicsView):
    """QGraphicsView subclass exposing Ctrl+wheel zoom and a
    'background_clicked' signal so EcosystemGraphView can clear selection
    when the user clicks empty canvas."""

    background_clicked = Signal()

    def __init__(self, scene: QGraphicsScene, parent: QWidget | None = None):
        super().__init__(scene, parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            angle = event.angleDelta().y()
            if angle == 0:
                return
            factor = 1.15 if angle > 0 else 1 / 1.15
            owner = self.parent()
            if isinstance(owner, EcosystemGraphView):
                owner._zoom_by(factor)
            event.accept()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event):
        # If the press lands on empty scene area (no item under cursor),
        # treat it as a background click after the standard pan handling.
        item = self.itemAt(event.position().toPoint())
        super().mousePressEvent(event)
        if item is None and event.button() == Qt.MouseButton.LeftButton:
            self.background_clicked.emit()
