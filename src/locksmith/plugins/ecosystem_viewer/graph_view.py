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
from typing import Any, Callable

from PySide6.QtCore import Property, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QWheelEvent
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
    PermittedIssuerEdge,
    QualificationEdge,
    RoleNode,
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
    role_nodes: dict = field(default_factory=dict)     # role_name -> RoleNode (Stage 14)
    chain_edges: list = field(default_factory=list)    # EdgeLine instances
    membership_edges: list = field(default_factory=list)
    permitted_issuer_edges: list = field(default_factory=list)  # PermittedIssuerEdge instances
    qualification_edges: list = field(default_factory=list)  # QualificationEdge instances (Stage 14)
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


class GraphCanvasToolbar(QFrame):
    """Floating icon-only toolbar overlaid on the graph canvas (top-left).

    Three buttons for adding ecosystem members directly from the graph
    view: schema, issuer AID, role. Icons only; tooltips identify them.
    """

    add_schema_clicked = Signal()
    add_aid_clicked = Signal()
    add_role_clicked = Signal()

    BUTTON_SIZE = 32
    ICON_SIZE = 20

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("graphCanvasToolbar")
        self.setStyleSheet(
            "QFrame#graphCanvasToolbar {"
            f" background-color: {colors.BACKGROUND_CONTENT};"
            f" border: 1px solid {colors.BORDER_NEUTRAL};"
            " border-radius: 6px;"
            "}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        for icon_path, tooltip, signal in (
            (":/assets/material-icons/schema.svg", "Add schema to ecosystem",
             self.add_schema_clicked),
            (":/assets/material-icons/person_add.svg", "Add issuer AID to ecosystem",
             self.add_aid_clicked),
            (":/assets/material-icons/group_add.svg", "Add role to ecosystem",
             self.add_role_clicked),
        ):
            btn = LocksmithIconButton(icon_path, tooltip=tooltip,
                                      icon_size=self.ICON_SIZE, border=False)
            btn.setFixedSize(self.BUTTON_SIZE, self.BUTTON_SIZE)
            btn.clicked.connect(signal.emit)
            layout.addWidget(btn)


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
    add_permitted_issuer_requested = Signal(str, str)     # (aid, schema_said)
    remove_permitted_issuer_requested = Signal(str, str)  # (aid, schema_said)
    # Stage 14: role + qualification rule signals.
    role_selected = Signal(str)                           # role_name
    add_qualification_rule_requested = Signal(str, str)   # (schema_said, role_name) — T5 will emit
    remove_qualification_rule_requested = Signal(str, str)  # (schema_said, role_name)
    # Floating canvas toolbar — surface "+ Schema" / "+ AID" / "+ Role"
    # entry points so the page can show no top-of-tabs add buttons.
    add_schema_clicked = Signal()
    add_aid_clicked = Signal()
    add_role_clicked = Signal()

    MIN_ZOOM = 0.25
    MAX_ZOOM = 4.0

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._build_chrome()
        self._build_result: GraphBuildResult | None = None
        self._selected_node: Any | None = None  # SchemaNode | IssuerNode | None
        self._eco: Any | None = None  # last-rendered EcosystemRecord
        # Stage 14: cached resolver callables from the most recent
        # render_ecosystem call. _populate_panel_for_role uses them to
        # recompute role membership without a stored EcosystemBaser ref.
        self._get_role: Callable[[str], Any] | None = None
        self._list_roles: Callable[[str], list] | None = None
        self._find_credentials_of_schema: Callable[[str], list] | None = None

        # Snap-target pulse phase (Stage 11). Animated 0.0↔1.0 during
        # drag-to-create; consumed by SchemaNode.paint() to modulate the
        # eligible-ring alpha.
        self._snap_pulse_phase = 0.0
        self._snap_pulse_anim = None  # lazily created in _begin_snap_pulse

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

        # Floating canvas toolbar — top-left overlay, parented to self
        # so it sits above the canvas without affecting layout.
        self._canvas_toolbar = GraphCanvasToolbar(parent=self)
        self._canvas_toolbar.add_schema_clicked.connect(self.add_schema_clicked.emit)
        self._canvas_toolbar.add_aid_clicked.connect(self.add_aid_clicked.emit)
        self._canvas_toolbar.add_role_clicked.connect(self.add_role_clicked.emit)

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

    def render_ecosystem(
        self,
        eco: Any,
        vault: Any,
        *,
        get_role: Callable[[str], Any] | None = None,
        list_roles: Callable[[str], list] | None = None,
        find_credentials_of_schema: Callable[[str], list] | None = None,
    ) -> GraphBuildResult:
        """Rebuild the scene for the given ecosystem record + vault.

        When ``get_role``/``list_roles``/``find_credentials_of_schema``
        are all provided AND the ecosystem has ``role_names`` /
        ``issuer_qualification_rules``, role nodes and qualification
        edges (Stage 14) are rendered in a dedicated row between the
        deepest schema layer and the bottom issuer row.
        """
        self._scene.clear()
        self._selected_node = None
        # Close any open side panel — the previously selected node no
        # longer exists in the new scene.
        self._side_panel.close()
        # Cache the ecosystem record so the side panel can render
        # permitted-issuer info for selected schemas (Stage 9).
        self._eco = eco
        # Cache role resolvers for _populate_panel_for_role (Stage 14 T6).
        self._get_role = get_role
        self._list_roles = list_roles
        self._find_credentials_of_schema = find_credentials_of_schema
        result = self._build_scene(
            eco,
            vault,
            get_role=get_role,
            list_roles=list_roles,
            find_credentials_of_schema=find_credentials_of_schema,
        )
        self._build_result = result
        self._update_stats(result)
        self._update_hint(result)
        # Defer a fit-to-content until the view has a real size; if called
        # before the widget has been shown the fitInView is a no-op.
        self.fit_to_content()
        self._reposition_panel()
        self._reposition_canvas_toolbar()
        return result

    def _update_hint(self, result: GraphBuildResult) -> None:
        """Surface an explainer overlay for empty/sparse ecosystems (§5.9)."""
        n_real_schemas = sum(1 for n in result.schema_nodes.values() if not n.ghost)
        n_issuers = len(result.issuer_nodes)
        n_chain = len(result.chain_edges)
        n_permitted = len(result.permitted_issuer_edges)
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
        elif n_real_schemas >= 1 and n_issuers >= 1 and n_permitted == 0:
            self._hint_label.setText(
                "Tip: drag from an issuer node up to a schema to mark "
                "them as the permitted issuer in this ecosystem."
            )
            self._hint_label.show()
        else:
            self._hint_label.hide()
        self._reposition_hint()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_panel()
        self._reposition_hint()
        self._reposition_canvas_toolbar()

    def _reposition_canvas_toolbar(self) -> None:
        if not hasattr(self, "_canvas_toolbar"):
            return
        margin = 12
        size = self._canvas_toolbar.sizeHint()
        self._canvas_toolbar.setGeometry(
            margin, margin, size.width(), size.height()
        )
        self._canvas_toolbar.raise_()

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

    def _build_scene(
        self,
        eco: Any,
        vault: Any,
        *,
        get_role: Callable[[str], Any] | None = None,
        list_roles: Callable[[str], list] | None = None,
        find_credentials_of_schema: Callable[[str], list] | None = None,
    ) -> GraphBuildResult:
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

        # Step 4b: build RoleNodes for ecosystem-defined roles (Stage 14).
        # Only when all three callables are wired AND the record exposes
        # role_names. The graph view doesn't hold an EcosystemBaser
        # reference, so the resolver behaviour is delegated to the
        # callables provided by the caller (typically the plugin layer).
        if (
            list_roles is not None
            and get_role is not None
            and getattr(eco, "role_names", None)
        ):
            for role in list_roles(eco.name) or []:
                if find_credentials_of_schema is not None:
                    member_count = self._count_role_members(
                        eco, role, get_role, find_credentials_of_schema,
                    )
                else:
                    member_count = len(role.root_issuer_aids or [])
                role_node = RoleNode(
                    role_name=role.name,
                    member_count=member_count,
                )
                role_node.clicked.connect(
                    lambda r=role.name: self._on_role_clicked(r)
                )
                self._scene.addItem(role_node)
                result.role_nodes[role.name] = role_node

        # Step 5: layout. Schema nodes participate in chain-of-authority
        # layering; role nodes (Stage 14) sit in their own row between
        # the deepest schema layer and the bottom issuer row; issuer
        # nodes get pinned to the bottom row, ordered by barycenter of
        # their permitted-issuer edges (design §2.5).
        all_node_ids: list[str] = (
            list(result.schema_nodes.keys())
            + list(result.role_nodes.keys())
            + list(result.issuer_nodes.keys())
        )
        layout_edges: list[tuple[str, str]] = [
            (src, dst) for (src, dst, _op) in chain_edges
        ]
        # Permitted-issuer pairs (issuer_aid, schema_said) drive both the
        # bottom-row ordering AND the runtime PermittedIssuerEdge instances.
        permitted_pairs: list[tuple[str, str]] = []
        for said, aids in (eco.permitted_issuers or {}).items():
            if said not in result.schema_nodes:
                continue
            for aid in aids:
                if aid in result.issuer_nodes:
                    permitted_pairs.append((aid, said))

        # Stage 14: role-row pinning. Only entries pointing at a real
        # role + a real schema in this scene drive barycenter ordering.
        qualification_pairs: list[tuple[str, str]] = []
        for said, role_name in (eco.issuer_qualification_rules or {}).items():
            if said in result.schema_nodes and role_name in result.role_nodes:
                qualification_pairs.append((said, role_name))

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
            bottom_row_ordering_edges=permitted_pairs,
            role_row_nodes=list(result.role_nodes.keys()) or None,
            role_row_ordering_edges=qualification_pairs or None,
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

        # Stage 14: role nodes (RoleNode) are 56px hexagons; centre them
        # within the schema-sized slot the layout reserves.
        for role_name, role_node in result.role_nodes.items():
            x, y = layout_result.positions.get(role_name, (0, 0))
            offset = (NODE_WIDTH + NOTCH_DEPTH - RoleNode.NODE_DIAMETER) / 2
            role_node.setPos(x + offset, y)

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

        # Step 7b: draw permitted-issuer edges (Stage 11).
        # Each (issuer_aid, schema_said) pair in eco.permitted_issuers
        # becomes a teal solid line with a hollow arrowhead, issuer→schema.
        # Per design 2026-05-08-permitted-issuer-edges §2.2.
        for aid, said in permitted_pairs:
            issuer_node = result.issuer_nodes.get(aid)
            schema_node = result.schema_nodes.get(said)
            if issuer_node is None or schema_node is None:
                continue
            edge = PermittedIssuerEdge(
                source=issuer_node, target=schema_node,
            )
            edge.emitter.remove_requested.connect(
                self._on_permitted_issuer_edge_remove_requested
            )
            self._scene.addItem(edge)
            result.permitted_issuer_edges.append(edge)

        # Step 7c: qualification edges (Stage 14) — schema → role dashed
        # teal Bézier with an "if" badge. One per
        # eco.issuer_qualification_rules entry whose schema + role both
        # made it onto the canvas.
        for said, role_name in qualification_pairs:
            schema_node = result.schema_nodes.get(said)
            role_node = result.role_nodes.get(role_name)
            if schema_node is None or role_node is None:
                continue
            qual_edge = QualificationEdge(
                source_schema=schema_node, target_role=role_node,
            )
            qual_edge._emitter.remove_requested.connect(
                self._on_qualification_edge_remove_requested
            )
            self._scene.addItem(qual_edge)
            qual_edge.refresh()
            result.qualification_edges.append(qual_edge)

        # Step 8: membership edges (schema ↔ issuer). With Stage 11's
        # PermittedIssuerEdge instantiation above, mere membership is
        # already conveyed by the issuer node's presence on the canvas
        # (see design 2026-05-08-permitted-issuer-edges §2.4). We keep
        # MembershipEdge as a class for future ecosystems where issuance
        # isn't fully captured, but we no longer instantiate it here.
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

    def _on_permitted_issuer_edge_remove_requested(self, aid: str, said: str) -> None:
        """Forward right-click 'Remove permitted-issuer' from a graph
        edge to the surrounding page via signal."""
        self.remove_permitted_issuer_requested.emit(aid, said)

    def _on_role_clicked(self, role_name: str) -> None:
        """Stage 14 T6: select role node, populate the side panel, emit selection."""
        if self._build_result is None:
            return
        node = self._build_result.role_nodes.get(role_name)
        if node is None:
            return
        self._set_selected_node(node)
        self._populate_panel_for_role(role_name)
        self._reposition_panel()
        self.role_selected.emit(role_name)

    def _on_qualification_edge_remove_requested(
        self, schema_said: str, role_name: str,
    ) -> None:
        """Forward right-click 'Remove qualification rule' from a
        QualificationEdge to the surrounding page via signal."""
        self.remove_qualification_rule_requested.emit(schema_said, role_name)

    @staticmethod
    def _resolve_role_members_in_view(
        eco: Any,
        role: Any,
        get_role: Callable[[str], Any],
        find_credentials_of_schema: Callable[[str], list],
    ) -> set[str]:
        """Resolve `role`'s current membership as a set of AIDs.

        Mirrors EcosystemBaser.resolve_role_members but uses the
        provided ``get_role`` callable rather than holding an
        EcosystemBaser reference (the graph view doesn't take one).
        Cycle protection guards against tampered records."""
        visited: set[str] = set()

        def _resolve(rname: str) -> set[str]:
            if rname in visited:
                return set()
            visited.add(rname)
            r = get_role(rname)
            if r is None:
                return set()
            if not r.issuer_role_name:
                return set(r.root_issuer_aids or [])
            parents = _resolve(r.issuer_role_name)
            if not parents:
                return set()
            members: set[str] = set()
            for cred in find_credentials_of_schema(r.qualification_schema_said) or []:
                if cred.issuer_aid in parents:
                    members.add(cred.holder_aid)
            return members

        try:
            return _resolve(role.name)
        except Exception:
            return set(role.root_issuer_aids or [])

    @classmethod
    def _count_role_members(
        cls,
        eco: Any,
        role: Any,
        get_role: Callable[[str], Any],
        find_credentials_of_schema: Callable[[str], list],
    ) -> int:
        """Size of `role`'s current membership — thin wrapper around the resolver."""
        return len(
            cls._resolve_role_members_in_view(
                eco, role, get_role, find_credentials_of_schema,
            )
        )

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

        # Permitted issuers (Stage 9): pull from cached ecosystem record
        # and resolve each AID's alias / is_self via cached issuer metadata.
        auth_aids: list[str] = []
        ecosystem_has_issuers = False
        if self._eco is not None:
            ecosystem_has_issuers = bool(self._eco.issuer_aids)
            auth_aids = list(
                self._eco.permitted_issuers.get(said, []) or []
            )
        permitted: list[tuple[str, str, bool]] = []
        for aid in auth_aids:
            meta = self._build_result.issuer_meta.get(aid, {})
            alias = meta.get("alias") or _short_aid(aid)
            is_self = bool(meta.get("is_self"))
            permitted.append((aid, alias, is_self))

        self._side_panel.show_schema(
            inspection=inspection,
            edges_out=edges_out,
            edges_in=edges_in,
            schema_titles=titles,
            permitted_issuers=permitted,
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

    def _populate_panel_for_role(self, role_name: str) -> None:
        """Stage 14 T6: render the role-detail mode of the side panel."""
        if self._build_result is None or self._get_role is None:
            return
        role = self._get_role(role_name)
        if role is None:
            self._side_panel.close()
            return

        # Resolve current members (set → list, in stable order).
        if (
            self._eco is not None
            and self._find_credentials_of_schema is not None
        ):
            members_set = self._resolve_role_members_in_view(
                self._eco, role, self._get_role, self._find_credentials_of_schema,
            )
        else:
            members_set = set(role.root_issuer_aids or [])
        members = sorted(members_set)

        # Look up the qualification-schema title from the inspections cache
        # (the same map _populate_panel_for_schema relies on).
        qual_title: str | None = None
        if role.qualification_schema_said:
            insp = self._build_result.inspections.get(role.qualification_schema_said)
            if insp is not None and insp.title:
                qual_title = insp.title

        # Issuer-role label: None for root role, the parent role name otherwise.
        issuer_role_label: str | None = (
            role.issuer_role_name if role.issuer_role_name else None
        )

        self._side_panel.show_role(
            role=role,
            members=members,
            qualification_schema_title=qual_title,
            issuer_role_label=issuer_role_label,
        )

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

    # ------------------------------------------------------------------
    # Snap-target pulse animation (Stage 11)
    # ------------------------------------------------------------------

    def _get_snap_pulse_phase(self) -> float:
        return self._snap_pulse_phase

    def _set_snap_pulse_phase(self, value: float) -> None:
        self._snap_pulse_phase = value
        if self._build_result is not None:
            for schema in self._build_result.schema_nodes.values():
                if getattr(schema, "_snap_state", "off") == "eligible":
                    schema.update()

    snap_pulse_phase = Property(float, _get_snap_pulse_phase, _set_snap_pulse_phase)

    def _begin_snap_pulse(self) -> None:
        if self._snap_pulse_anim is None:
            self._snap_pulse_anim = QPropertyAnimation(self, b"snap_pulse_phase")
            self._snap_pulse_anim.setDuration(1000)
            self._snap_pulse_anim.setStartValue(0.0)
            self._snap_pulse_anim.setKeyValueAt(0.5, 1.0)
            self._snap_pulse_anim.setEndValue(0.0)
            self._snap_pulse_anim.setLoopCount(-1)
        self._snap_pulse_anim.start()

    def _end_snap_pulse(self) -> None:
        if self._snap_pulse_anim is not None:
            self._snap_pulse_anim.stop()
        self._snap_pulse_phase = 0.0
        if self._build_result is not None:
            for schema in self._build_result.schema_nodes.values():
                schema.update()

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
        # Drag-to-create-edge state. Initialized lazily in
        # mousePressEvent when a press lands on an IssuerNode (Stage 11)
        # or a RoleNode (Stage 14 T5).
        # _drag_origin is a (kind, id) tuple where kind is "issuer" or
        # "role"; id is the AID for issuers and the role_name for roles.
        self._drag_origin: tuple[str, str] | None = None
        self._drag_origin_pos = None  # QPointF in scene coords
        self._drag_press_view_pos = None  # QPoint in view coords (for threshold)
        self._drag_rubber_band = None  # QGraphicsLineItem during drag
        self._drag_active = False
        self._current_snap_target_said: str | None = None

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
        # If the press lands on an IssuerNode or RoleNode, capture the
        # press for a potential drag-to-create-edge gesture. Don't enter
        # drag mode until movement exceeds the threshold (Qt's
        # startDragDistance, default 4px on macOS), so a click without
        # move still selects the node and opens the side panel.
        item = self.itemAt(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and isinstance(
            item, (IssuerNode, RoleNode)
        ):
            if isinstance(item, IssuerNode):
                self._drag_origin = ("issuer", item.aid)
            else:
                self._drag_origin = ("role", item.role_name)
            self._drag_origin_pos = item.top_anchor()
            self._drag_press_view_pos = event.position().toPoint()
            # Don't call super here — let the node's own
            # mousePressEvent fire (which emits clicked + accepts).
            super().mousePressEvent(event)
            return

        # Reset any stale drag state and proceed with default behavior.
        self._drag_origin = None
        self._drag_origin_pos = None
        self._drag_press_view_pos = None

        super().mousePressEvent(event)
        if item is None and event.button() == Qt.MouseButton.LeftButton:
            self.background_clicked.emit()

    def mouseMoveEvent(self, event):
        # Entering drag mode: cross the 4px movement threshold while a
        # press is active on an IssuerNode or RoleNode.
        if (
            self._drag_origin is not None
            and not self._drag_active
            and self._drag_press_view_pos is not None
        ):
            delta = (event.position().toPoint() - self._drag_press_view_pos)
            if delta.manhattanLength() >= self._start_drag_distance():
                self._begin_drag()

        if self._drag_active:
            scene_pos = self.mapToScene(event.position().toPoint())
            self._update_snap_targets(scene_pos)
            self._update_rubber_band(scene_pos)
            event.accept()
            return  # don't pan while drawing

        super().mouseMoveEvent(event)

    @staticmethod
    def _start_drag_distance() -> int:
        from PySide6.QtWidgets import QApplication
        return QApplication.startDragDistance() if QApplication.instance() else 4

    def mouseReleaseEvent(self, event):
        if self._drag_active and event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.position().toPoint())
            target = self._snap_target_at(scene_pos)
            self._end_drag(target)
            event.accept()
            return
        # Reset stale press capture (no drag was started).
        self._drag_origin = None
        self._drag_origin_pos = None
        self._drag_press_view_pos = None
        super().mouseReleaseEvent(event)

    def _begin_drag(self) -> None:
        from PySide6.QtWidgets import QGraphicsLineItem
        from PySide6.QtCore import QLineF
        self._drag_active = True
        owner = self.parent()
        if isinstance(owner, EcosystemGraphView):
            owner._begin_snap_pulse()
        self.viewport().setCursor(Qt.CursorShape.CrossCursor)
        # Create rubber band from origin to current scene pos (will be
        # immediately updated on next mouseMoveEvent).
        line = QGraphicsLineItem(QLineF(self._drag_origin_pos, self._drag_origin_pos))
        pen = QPen(QColor("#0D9488"), 1.25)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        line.setPen(pen)
        line.setZValue(10)  # above everything during drag
        line.setEnabled(False)  # don't let it intercept hit-tests
        self.scene().addItem(line)
        self._drag_rubber_band = line

    def _update_rubber_band(self, scene_pos) -> None:
        from PySide6.QtCore import QLineF
        if self._drag_rubber_band is None or self._drag_origin_pos is None:
            return
        # If currently snapped to a schema, terminate at its bottom_anchor.
        if self._current_snap_target_said is not None:
            owner = self.parent()
            if isinstance(owner, EcosystemGraphView) and owner._build_result is not None:
                schema_node = owner._build_result.schema_nodes.get(
                    self._current_snap_target_said
                )
                if schema_node is not None:
                    end = schema_node.bottom_anchor()
                    self._drag_rubber_band.setLine(QLineF(self._drag_origin_pos, end))
                    return
        self._drag_rubber_band.setLine(QLineF(self._drag_origin_pos, scene_pos))

    def _update_snap_targets(self, scene_pos) -> None:
        owner = self.parent()
        if not isinstance(owner, EcosystemGraphView):
            return
        if owner._build_result is None or owner._eco is None:
            return

        target = self._snap_target_at(scene_pos)
        target_said = target.said if target is not None else None

        kind, origin_id = self._drag_origin if self._drag_origin else ("issuer", None)

        # Update per-schema snap states.
        for said, schema in owner._build_result.schema_nodes.items():
            if schema.ghost:
                schema.set_snap_target_state("ineligible")
                continue
            if kind == "role":
                # 'already' when this schema already qualifies into the
                # dragging role.
                if owner._eco.issuer_qualification_rules.get(said) == origin_id:
                    schema.set_snap_target_state("already")
                else:
                    schema.set_snap_target_state("eligible")
            else:
                issued_by = owner._eco.permitted_issuers.get(said, [])
                if origin_id in issued_by:
                    # Already issued by the dragging issuer → 'already'
                    schema.set_snap_target_state("already")
                else:
                    # All non-ghost, not-already-issued schemas glow as 'eligible'
                    # during drag (the actual snap target is the one the cursor
                    # is currently over, but we want all eligible ones to pulse
                    # so the user sees the full target set).
                    schema.set_snap_target_state("eligible")

        self._current_snap_target_said = target_said

    def _snap_target_at(self, scene_pos):
        """Return the SchemaNode at scene_pos that's an eligible drop
        target, or None. Filters out ghost nodes and the rubber-band
        item itself."""
        items = self.scene().items(scene_pos)
        for item in items:
            if isinstance(item, SchemaNode) and not item.ghost:
                # Even already-issued schemas can be 'snap targets'; the
                # release-time logic short-circuits with a no-op for them.
                return item
        return None

    def _end_drag(self, target) -> None:
        owner = self.parent()
        # Remove rubber band.
        if self._drag_rubber_band is not None:
            self.scene().removeItem(self._drag_rubber_band)
            self._drag_rubber_band = None
        # Restore cursor.
        self.viewport().unsetCursor()
        # Clear snap-target overlays.
        if isinstance(owner, EcosystemGraphView) and owner._build_result is not None:
            for schema in owner._build_result.schema_nodes.values():
                schema.set_snap_target_state("off")

        # Commit if release on an eligible schema.
        if (
            target is not None
            and self._drag_origin is not None
            and isinstance(owner, EcosystemGraphView)
            and owner._eco is not None
        ):
            said = target.said
            kind, origin_id = self._drag_origin
            if kind == "issuer":
                already = origin_id in owner._eco.permitted_issuers.get(said, [])
                if not already:
                    owner.add_permitted_issuer_requested.emit(origin_id, said)
                # else: silent no-op (already-issued case). Future polish:
                # show a toast.
            elif kind == "role":
                already = owner._eco.issuer_qualification_rules.get(said) == origin_id
                if not already:
                    owner.add_qualification_rule_requested.emit(said, origin_id)
                # else: silent no-op (already-qualifying case).

        # Reset state.
        if isinstance(owner, EcosystemGraphView):
            owner._end_snap_pulse()
        self._drag_active = False
        self._drag_origin = None
        self._drag_origin_pos = None
        self._drag_press_view_pos = None
        self._current_snap_target_said = None

    def _begin_drag_from(self, node) -> None:
        """Test hook: start a drag from an IssuerNode or RoleNode without
        firing real Qt mouse events. Sets _drag_origin based on node type
        and invokes _begin_drag()."""
        if isinstance(node, IssuerNode):
            self._drag_origin = ("issuer", node.aid)
        elif isinstance(node, RoleNode):
            self._drag_origin = ("role", node.role_name)
        else:
            raise TypeError(f"unsupported drag origin: {type(node).__name__}")
        self._drag_origin_pos = node.top_anchor()
        self._begin_drag()
