# Permitted-Issuer Edges Implementation Plan (Stage 11)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface `EcosystemRecord.permitted_issuers` as visible edges in the ecosystem graph view (issuer→schema, solid teal with hollow arrowhead), and add a drag-from-issuer-to-schema gesture that creates new permitted-issuer assignments via the existing DB CRUD.

**Architecture:** New `PermittedIssuerEdge` class alongside the existing `EdgeLine` and `MembershipEdge` in `graph_items.py`. `EcosystemGraphView._build_scene` instantiates one edge per `(schema, aid)` pair in the ecosystem's `permitted_issuers` mapping. Drag interaction is implemented via `_GraphView.mousePressEvent`/`mouseMoveEvent`/`mouseReleaseEvent` overrides, gated on the press landing on an `IssuerNode`; commit calls `add_permitted_issuer` and a fresh `_build_scene` re-renders the edge. Removal via `contextMenuEvent` on `PermittedIssuerEdge`. Bottom-row issuer ordering uses a small extension to `layout.layout_hierarchical` so vertical issuance lines don't cross unnecessarily.

**Tech Stack:** PySide6 (Qt) — `QGraphicsScene`, `QGraphicsPathItem`, `QGraphicsLineItem` (rubber-band), `QPropertyAnimation` (snap-target pulse), `QMenu` (right-click delete). No new dependencies. Zero schema migrations.

**Design source:** `docs/superpowers/designs/2026-05-08-permitted-issuer-edges.md`. Section references in this plan point at that doc.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `src/locksmith/plugins/ecosystem_viewer/layout.py` | Modify | Add `bottom_row_ordering_edges` parameter to `layout_hierarchical` so the pinned bottom row reorders by mean x of its connected upper-layer nodes |
| `tests/test_layout.py` | Modify | New tests for the bottom-row reordering behavior |
| `src/locksmith/plugins/ecosystem_viewer/graph_items.py` | Modify | New `PermittedIssuerEdge` class; `set_snap_target_state` method on `IssuerNode` and `SchemaNode`; tiny pulse-ring paint pass for snap-target state |
| `src/locksmith/plugins/ecosystem_viewer/graph_view.py` | Modify | Render `PermittedIssuerEdge` instances in `_build_scene`; pass bottom-row ordering edges to `layout_hierarchical`; add the two new signals; drag-to-create state machine in `_GraphView`; third empty-state hint |
| `src/locksmith/plugins/ecosystem_viewer/pages.py` | Modify | Forward the new graph-view signals through `EcosystemDetailPage` to the existing `add_permitted_issuer_clicked` / `remove_permitted_issuer_clicked` signals (zero new plugin handler code) |

No design assets needed — the teal color, hollow arrowhead, and pulse-ring are painted directly.

---

## Task 1: Layout — bottom-row barycentric reordering

Goal: when the layout has pinned bottom-row nodes (issuer AIDs in our case) and you also have a set of edges connecting bottom-row nodes to upper-layer nodes, reorder the bottom row by the mean x of each node's neighbors so vertical issuance lines minimize crossings. Per design §2.5 mitigation 3.

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/layout.py`
- Test: `tests/test_layout.py` (append at end)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_layout.py`:

```python
def test_bottom_row_reorders_by_barycenter_of_connecting_edges():
    # Three schemas at top (after layout: A, B, C left-to-right at layer 0).
    # Three issuers at bottom; without reordering they sort alphabetically.
    # With bottom_row_ordering_edges = [(I1, A), (I2, C), (I3, B)], the
    # bottom row should reorder to I1, I3, I2 (mean-x of neighbors: I1's
    # only neighbor is A=leftmost, I3 connects to B=middle, I2 to
    # C=rightmost).
    result = layout_hierarchical(
        nodes=["A", "B", "C", "I1", "I2", "I3"],
        edges=[],  # no chain-of-authority edges in this test
        bottom_row_nodes=["I1", "I2", "I3"],
        bottom_row_ordering_edges=[("I1", "A"), ("I2", "C"), ("I3", "B")],
    )
    bottom = result.layers[-1]
    assert bottom == ["I1", "I3", "I2"]


def test_bottom_row_ordering_edges_default_no_reorder():
    # Without the new param, behavior is unchanged: bottom row stays in
    # the alphabetical order produced by _group_into_layers + the
    # bottom-row append.
    result = layout_hierarchical(
        nodes=["A", "B", "C", "I1", "I2", "I3"],
        edges=[("A", "B")],
        bottom_row_nodes=["I1", "I2", "I3"],
    )
    bottom = result.layers[-1]
    assert bottom == ["I1", "I2", "I3"]


def test_bottom_row_node_with_no_ordering_edges_keeps_relative_position():
    # If a bottom-row node has zero ordering edges, it should retain its
    # original order relative to other unconnected siblings (stable sort).
    result = layout_hierarchical(
        nodes=["A", "B", "I1", "I2", "I3"],
        edges=[],
        bottom_row_nodes=["I1", "I2", "I3"],
        bottom_row_ordering_edges=[("I2", "A")],
    )
    bottom = result.layers[-1]
    # I2 should land near A (leftmost). I1 and I3 have no ordering edges
    # — they retain their alphabetical order from each other but follow
    # I2 since I2 has the lowest barycenter.
    assert bottom[0] == "I2"
    assert bottom[1:] == ["I1", "I3"]
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv/bin/python -m pytest tests/test_layout.py::test_bottom_row_reorders_by_barycenter_of_connecting_edges tests/test_layout.py::test_bottom_row_ordering_edges_default_no_reorder tests/test_layout.py::test_bottom_row_node_with_no_ordering_edges_keeps_relative_position -v
```

Expected: `TypeError: layout_hierarchical() got an unexpected keyword argument 'bottom_row_ordering_edges'`.

- [ ] **Step 3: Add the new parameter to `layout_hierarchical`**

In `src/locksmith/plugins/ecosystem_viewer/layout.py`, find the `layout_hierarchical` signature:

```python
def layout_hierarchical(
    nodes: Iterable[Hashable],
    edges: Iterable[tuple[Hashable, Hashable]],
    *,
    bottom_row_nodes: Iterable[Hashable] = (),
    options: LayoutOptions | None = None,
) -> LayoutResult:
```

Add `bottom_row_ordering_edges` between `bottom_row_nodes` and `options`:

```python
def layout_hierarchical(
    nodes: Iterable[Hashable],
    edges: Iterable[tuple[Hashable, Hashable]],
    *,
    bottom_row_nodes: Iterable[Hashable] = (),
    bottom_row_ordering_edges: Iterable[tuple[Hashable, Hashable]] = (),
    options: LayoutOptions | None = None,
) -> LayoutResult:
```

In the function body, locate the block that pins bottom-row nodes:

```python
    # 4. Bottom-row nodes get a dedicated final layer.
    if bottom_set:
        layers.append(sorted(bottom_set, key=str))
```

Replace with:

```python
    # 4. Bottom-row nodes get a dedicated final layer.
    if bottom_set:
        layers.append(_order_bottom_row(
            bottom_set,
            list(bottom_row_ordering_edges),
            chain_layers=layers,
        ))
```

Then add the helper function at module level (right above `_assign_coordinates` or wherever fits the file's structure):

```python
def _order_bottom_row(
    bottom_set: set[Hashable],
    ordering_edges: list[tuple[Hashable, Hashable]],
    chain_layers: list[list[Hashable]],
) -> list[Hashable]:
    """Order bottom-row nodes by mean x-position of their neighbors in
    the chain-layer hierarchy (per design §2.5 mitigation 3).

    Each ordering edge (bottom_node, chain_node) contributes the chain
    node's position-in-its-layer to bottom_node's barycenter. Nodes
    with no ordering edges fall back to alphabetical and follow the
    nodes that DO have edges (in their barycenter order).
    """
    # Build chain-node -> position-in-layer for barycenter lookup.
    chain_pos: dict[Hashable, float] = {}
    for layer in chain_layers:
        for i, node in enumerate(layer):
            chain_pos[node] = float(i)

    # Compute barycenter per bottom-row node.
    barycenters: dict[Hashable, float | None] = {}
    contributions: dict[Hashable, list[float]] = {n: [] for n in bottom_set}
    for src, dst in ordering_edges:
        if src in bottom_set and dst in chain_pos:
            contributions[src].append(chain_pos[dst])
        if dst in bottom_set and src in chain_pos:
            contributions[dst].append(chain_pos[src])
    for n in bottom_set:
        cs = contributions[n]
        barycenters[n] = (sum(cs) / len(cs)) if cs else None

    # Sort: nodes with barycenters first (by barycenter, then by str for
    # deterministic ties); nodes without barycenters last (alphabetical).
    with_bary = sorted(
        (n for n in bottom_set if barycenters[n] is not None),
        key=lambda n: (barycenters[n], str(n)),
    )
    without_bary = sorted(
        (n for n in bottom_set if barycenters[n] is None),
        key=str,
    )
    return list(with_bary) + list(without_bary)
```

- [ ] **Step 4: Run tests to verify they pass**

```
.venv/bin/python -m pytest tests/test_layout.py -v
```

Expected: all tests pass (the existing 11 + the 3 new ones = 14 total).

- [ ] **Step 5: Commit**

```bash
cd /Users/seriouscoderone/code/locksmith/.worktrees/ecosystem-viewer
git add src/locksmith/plugins/ecosystem_viewer/layout.py tests/test_layout.py
git commit -m "$(cat <<'EOF'
feat(ecosystem-viewer): bottom-row barycentric reordering in layout

Per design 2026-05-08-permitted-issuer-edges §2.5 mitigation 3: when
permitted-issuer edges connect the pinned bottom row (issuer AIDs)
to upper layers (schemas), reorder the bottom row by mean x of each
node's connected upper-layer neighbors. Each issuer's edges then rise
mostly straight up, minimizing crossings without a new layout
algorithm.

New optional parameter `bottom_row_ordering_edges` on
layout_hierarchical(); empty default preserves prior behavior. 3 new
tests in test_layout.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `PermittedIssuerEdge` class + node `set_snap_target_state`

Goal: a new `QGraphicsPathItem` subclass that paints a solid teal line with a hollow arrowhead at the target end. Plus `set_snap_target_state` methods on `IssuerNode` and `SchemaNode` that paint a pulse ring overlay during drag-to-create (state will be wired in T6).

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/graph_items.py`

- [ ] **Step 1: Add `PermittedIssuerEdge` class**

In `src/locksmith/plugins/ecosystem_viewer/graph_items.py`, after the `MembershipEdge` class (currently the last class in the file), append:

```python
# ---------------------------------------------------------------------------
# PermittedIssuerEdge — issuer → schema solid teal line with hollow arrowhead
# ---------------------------------------------------------------------------


class PermittedIssuerEdge(QGraphicsPathItem):
    """A solid teal line representing 'this AID is permitted to issue
    this schema in this ecosystem' (EGF overlay; not an ACDC spec
    primitive). Per design 2026-05-08-permitted-issuer-edges §2.2.

    Connects issuer.top_anchor() → schema.bottom_anchor(). Hollow
    triangular arrowhead at the schema end signals "capability"
    rather than an actual past issuance event.
    """

    from PySide6.QtCore import QObject, Signal

    LINE_COLOR = "#0D9488"         # teal — same as aggregate-section dot
    LINE_COLOR_HOVER = "#0F766E"   # saturated teal on hover
    LINE_WIDTH = 1.25
    LINE_WIDTH_HOVER = 1.75
    ARROW_LENGTH = 9
    ARROW_WIDTH = 6
    DEFAULT_OPACITY = 0.6

    class _Emitter(QObject):
        """Lightweight QObject for the remove signal — QGraphicsPathItem
        is not a QObject and cannot define signals directly. Stored as
        an instance attribute so the edge can `self.emitter.remove_requested.emit(...)`."""
        remove_requested = Signal(str, str)  # (issuer_aid, schema_said)

    def __init__(
        self,
        source: "IssuerNode",
        target: "SchemaNode",
        parent: QGraphicsItem | None = None,
    ):
        super().__init__(parent)
        self.source = source
        self.target = target
        self.emitter = self._Emitter()
        self._hovered = False
        self.setZValue(-1.5)  # between membership (-2) and chain (-1)
        self.setOpacity(self.DEFAULT_OPACITY)
        self.setAcceptHoverEvents(True)
        self.setToolTip(self._build_tooltip())
        self.refresh()

    def _build_tooltip(self) -> str:
        alias = getattr(self.source, "alias", None) or "(unknown issuer)"
        title = getattr(self.target, "title", None) or "(unknown schema)"
        return f"{alias}  issues  {title}  in this ecosystem"

    def refresh(self) -> None:
        """Recompute the path from issuer top → schema bottom."""
        path = QPainterPath()
        sp = self.source.top_anchor()
        tp = self.target.bottom_anchor()
        # Slight cubic Bézier so multiple edges from one issuer don't
        # overlap straight on top of each other when the schema is in a
        # higher layer.
        ctrl1 = QPointF(sp.x(), sp.y() - 30)
        ctrl2 = QPointF(tp.x(), tp.y() + 30)
        path.moveTo(sp)
        path.cubicTo(ctrl1, ctrl2, tp)
        self.setPath(path)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor(self.LINE_COLOR_HOVER if self._hovered else self.LINE_COLOR)
        width = self.LINE_WIDTH_HOVER if self._hovered else self.LINE_WIDTH

        pen = QPen(color, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self.path())

        # Hollow open arrowhead at the schema end.
        sp = self.source.top_anchor()
        tp = self.target.bottom_anchor()
        self._draw_hollow_arrowhead(painter, sp, tp, color, width)

    def _draw_hollow_arrowhead(
        self,
        painter: QPainter,
        p1: QPointF,
        p2: QPointF,
        color: QColor,
        width: float,
    ) -> None:
        """Hollow triangular arrowhead at p2, oriented from p1→p2."""
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        length = math.hypot(dx, dy) or 1.0
        ux, uy = dx / length, dy / length
        px, py = -uy, ux  # perpendicular
        tip = p2
        base_x = p2.x() - ux * self.ARROW_LENGTH
        base_y = p2.y() - uy * self.ARROW_LENGTH
        left = QPointF(
            base_x + px * (self.ARROW_WIDTH / 2),
            base_y + py * (self.ARROW_WIDTH / 2),
        )
        right = QPointF(
            base_x - px * (self.ARROW_WIDTH / 2),
            base_y - py * (self.ARROW_WIDTH / 2),
        )
        polygon = QPolygonF([tip, left, right])
        pen = QPen(color, width)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)  # hollow
        painter.drawPolygon(polygon)

    def hoverEnterEvent(self, event):
        self._hovered = True
        self.setOpacity(1.0)
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self.setOpacity(self.DEFAULT_OPACITY)
        self.update()
        super().hoverLeaveEvent(event)

    def contextMenuEvent(self, event):
        from PySide6.QtWidgets import QMenu
        menu = QMenu()
        alias = getattr(self.source, "alias", None) or "this issuer"
        action = menu.addAction(f"Remove permitted-issuer ({alias})")
        chosen = menu.exec(event.screenPos())
        if chosen is action:
            self.emitter.remove_requested.emit(
                self.source.aid, self.target.said,
            )
        event.accept()
```

- [ ] **Step 2: Add `set_snap_target_state` to `SchemaNode`**

Find the `SchemaNode.set_selected` method (around line 357 in the existing file). Right after it, add:

```python
    def set_snap_target_state(self, state: str) -> None:
        """During drag-to-create-edge, paint a colored ring around the
        node to signal whether it's a valid drop target.

        state ∈ {'eligible', 'already', 'ineligible', 'off'}. 'eligible'
        pulses teal; 'already' shows a static dim ring + ✓; 'ineligible'
        and 'off' clear the overlay.
        """
        # Store as plain attribute; paint() reads it. Default 'off' if
        # unset (back-compat for code paths that don't manage drag state).
        if getattr(self, "_snap_state", "off") != state:
            self._snap_state = state
            self.update()
```

In `SchemaNode.paint()`, find the END of the method (just before the existing `return` for non-ghost rendering, after the section-fingerprint dots and lifecycle glyph). Append a snap-state overlay block:

```python
        # Snap-target overlay (drag-to-create from an IssuerNode).
        snap_state = getattr(self, "_snap_state", "off")
        if snap_state == "eligible":
            ring_color = QColor("#0D9488")  # teal
            pen = QPen(ring_color, 2)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self._build_outline_path())
        elif snap_state == "already":
            # Dimmed solid ring + small ✓ badge in top-right.
            ring_color = QColor(colors.TEXT_SECONDARY)
            pen = QPen(ring_color, 1.5)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self._build_outline_path())
            painter.setPen(QPen(QColor("#0D9488")))
            font = QFont("Helvetica", 12, QFont.Weight.Bold)
            painter.setFont(font)
            painter.drawText(
                QRectF(NODE_WIDTH - 16, 2, 14, 14),
                Qt.AlignmentFlag.AlignCenter,
                "✓",
            )
```

Place this overlay AFTER the lifecycle-glyph painting block, but BEFORE any final `painter.end()` if present.

- [ ] **Step 3: Add `set_snap_target_state` stub to `IssuerNode`**

Find the `IssuerNode.set_selected` method (around line 739). Right after it, add:

```python
    def set_snap_target_state(self, state: str) -> None:
        """Symmetric API with SchemaNode.set_snap_target_state. For an
        issuer node, snap-target visual is a no-op for now — issuers
        aren't drop targets in v1 (you drag FROM them, not TO them)."""
        # Intentional no-op; method exists so callers can address all
        # nodes uniformly when starting/ending a drag.
        return
```

- [ ] **Step 4: Sanity-check imports**

```bash
cd /Users/seriouscoderone/code/locksmith/.worktrees/ecosystem-viewer
.venv/bin/python -c "from locksmith.plugins.ecosystem_viewer import graph_items; print('ok'); print(graph_items.PermittedIssuerEdge)"
```

Expected output: `ok` and the class repr.

- [ ] **Step 5: Run pre-existing tests for regression**

```
.venv/bin/python -m pytest tests/test_layout.py tests/test_acdc_inspector.py tests/test_lifecycle_widget.py tests/test_ecosystem_baser.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
cd /Users/seriouscoderone/code/locksmith/.worktrees/ecosystem-viewer
git add src/locksmith/plugins/ecosystem_viewer/graph_items.py
git commit -m "$(cat <<'EOF'
feat(ecosystem-viewer): PermittedIssuerEdge graphics item

QGraphicsPathItem subclass painting a solid teal #0D9488 line with a
hollow open triangular arrowhead at the schema end. Issuer top_anchor
→ schema bottom_anchor, slight Bézier curve. Z-value -1.5 (between
membership at -2 and chain at -1). Default 60% opacity, brightens to
100% on hover. Right-click → "Remove permitted-issuer" via emitter
signal (QGraphicsPathItem can't host signals directly, so we store
a small _Emitter QObject).

Adds set_snap_target_state methods on SchemaNode (paints pulse ring
or dimmed-with-✓ overlay during drag-to-create) and IssuerNode
(no-op stub for symmetric calling). Per design
2026-05-08-permitted-issuer-edges §2.2, §3.3, §5.4.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Render PermittedIssuerEdge instances in `_build_scene`

Goal: after the existing chain-of-authority edge construction in `_build_scene`, iterate `eco.permitted_issuers` and instantiate one `PermittedIssuerEdge` per `(schema_said, aid)` pair. Pass the same edges to `layout_hierarchical` as the new bottom-row ordering input. Keep the `MembershipEdge` block commented-out (per design §2.4) but update its comment to reference Stage 11.

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/graph_view.py`

- [ ] **Step 1: Import `PermittedIssuerEdge`**

At the top of `graph_view.py`, find the import block from `graph_items`:

```python
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
```

Add `PermittedIssuerEdge` to that list, alphabetized:

```python
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
    SchemaNode,
)
```

- [ ] **Step 2: Extend `GraphBuildResult` to track issuance edges**

Find the `GraphBuildResult` dataclass (around line 79). Add a `permitted_issuer_edges: list = field(default_factory=list)` field next to `membership_edges`:

```python
@dataclass
class GraphBuildResult:
    # ... existing fields ...
    schema_nodes: dict = field(default_factory=dict)
    issuer_nodes: dict = field(default_factory=dict)
    chain_edges: list = field(default_factory=list)
    membership_edges: list = field(default_factory=list)
    permitted_issuer_edges: list = field(default_factory=list)  # NEW
    unresolved_count: int = 0
    feedback_edge_count: int = 0
    inspections: dict = field(default_factory=dict)
    schema_edges_by_src: dict = field(default_factory=dict)
    schema_edges_by_dst: dict = field(default_factory=dict)
    issuer_meta: dict = field(default_factory=dict)
```

- [ ] **Step 3: Compute permitted-issuer pairs before layout, pass them as `bottom_row_ordering_edges`**

In `_build_scene`, find the layout-options + `layout_hierarchical` block:

```python
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
```

Replace with:

```python
        # Step 5: layout. Schema nodes participate in chain-of-authority
        # layering; issuer nodes get pinned to the bottom row, ordered
        # by barycenter of their permitted-issuer edges (design §2.5).
        all_node_ids: list[str] = list(result.schema_nodes.keys()) + list(
            result.issuer_nodes.keys()
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
            options=layout_opts,
        )
```

- [ ] **Step 4: Build `PermittedIssuerEdge` instances after chain edges**

Find the chain-of-authority edge construction loop:

```python
        # Step 7: draw chain-of-authority edges.
        for src, dst, op in chain_edges:
            ...
            self._scene.addItem(edge)
            result.chain_edges.append(edge)

        # Step 8: membership edges (schema → issuer). For v1 we don't have
        # per-schema permitted-issuer mapping (that's stage 9); draw a
        # membership line from each issuer to every schema in the ecosystem
        # so the user can see the cluster. This will become more meaningful
```

Insert a new step 7b BEFORE the membership-edges (step 8) block:

```python
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
```

Then update the membership-edge comment block (the deferred one). Find:

```python
        # Step 8: membership edges (schema → issuer). For v1 we don't have
        # per-schema permitted-issuer mapping (that's stage 9); draw a
        # membership line from each issuer to every schema in the ecosystem
        # so the user can see the cluster. This will become more meaningful
        # once the EGF overlay lands.
        # NOTE: deliberately commented out — until we have the EGF overlay,
        # all-pairs membership lines turn the canvas into a hairball. Better
        # to omit them entirely and let issuer nodes float as a row.
```

Replace with:

```python
        # Step 8: membership edges (schema ↔ issuer). With Stage 11's
        # PermittedIssuerEdge instantiation above, mere membership is
        # already conveyed by the issuer node's presence on the canvas
        # (see design 2026-05-08-permitted-issuer-edges §2.4). We keep
        # MembershipEdge as a class for future ecosystems where issuance
        # isn't fully captured, but we no longer instantiate it here.
```

- [ ] **Step 5: Add the `_on_permitted_issuer_edge_remove_requested` method stub**

In `EcosystemGraphView` (the class that owns `_build_scene`), add a placeholder method that will be wired to the new `remove_permitted_issuer_requested` signal in Task 4. For now it just calls the signal-emitter stub:

Find the section where signals are declared at the top of `class EcosystemGraphView`. They look like:

```python
    schema_selected = Signal(str)       # emits schema SAID
    issuer_selected = Signal(str)       # emits AID
    schema_double_clicked = Signal(str)
    issuer_double_clicked = Signal(str)
    selection_cleared = Signal()
    relayout_requested = Signal()
    open_schema_detail_requested = Signal(str)
    open_issuer_requested = Signal(str, bool)
```

Add:

```python
    add_permitted_issuer_requested = Signal(str, str)     # (aid, schema_said)
    remove_permitted_issuer_requested = Signal(str, str)  # (aid, schema_said)
```

Then add the slot method anywhere inside `EcosystemGraphView` (e.g., next to `_on_schema_clicked`):

```python
    def _on_permitted_issuer_edge_remove_requested(self, aid: str, said: str) -> None:
        """Forward right-click 'Remove permitted-issuer' from a graph
        edge to the surrounding page via signal."""
        self.remove_permitted_issuer_requested.emit(aid, said)
```

- [ ] **Step 6: Smoke-test (no edges visible yet — drag commits in T5)**

```bash
pgrep -f "locksmith.main" | xargs -r kill -9 2>/dev/null
sleep 1
cd /Users/seriouscoderone/code/locksmith/.worktrees/ecosystem-viewer
.venv/bin/python -m locksmith.main &
WALLET_PID=$!
sleep 6
LOG=$(ls -t /private/tmp/claude-501/*/tasks/*.output 2>/dev/null | head -1)
[ -n "$LOG" ] && tail -10 "$LOG"
kill -9 $WALLET_PID 2>/dev/null
```

Confirm clean startup. To actually see a `PermittedIssuerEdge`, you'd need an ecosystem where you've already added permitted-issuer assignments via the List tab. If you have one, navigate to that ecosystem → Graph tab; you should see teal arrows from issuer nodes to schema nodes.

- [ ] **Step 7: Commit**

```bash
cd /Users/seriouscoderone/code/locksmith/.worktrees/ecosystem-viewer
git add src/locksmith/plugins/ecosystem_viewer/graph_view.py
git commit -m "$(cat <<'EOF'
feat(ecosystem-viewer): render permitted-issuer edges in graph view

Iterate eco.permitted_issuers and instantiate one PermittedIssuerEdge
per (schema_said, aid) pair after the chain-of-authority edges.
Bottom-row issuer ordering now uses the same pairs as
bottom_row_ordering_edges so vertical issuance lines minimize
crossings (design §2.5).

Adds add_permitted_issuer_requested / remove_permitted_issuer_requested
signals on EcosystemGraphView. The remove signal is wired from each
edge's _Emitter on construction; add will be triggered by drag-to-
create in a follow-up task.

Updates the deferred membership-edges comment to reference design §2.4
(permitted-issuer edges subsume membership at runtime; the class is
kept but not instantiated).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Forward graph-view signals through EcosystemDetailPage

Goal: connect `EcosystemGraphView.add_permitted_issuer_requested` / `remove_permitted_issuer_requested` to the existing `EcosystemDetailPage.add_permitted_issuer_clicked` / `remove_permitted_issuer_clicked` signals, which the plugin already wires to `_add_permitted_issuer` / `_remove_permitted_issuer`. Zero new plugin handler code per design §3.2.

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/pages.py` (`EcosystemDetailPage.__init__`)

- [ ] **Step 1: Find where the graph view is instantiated inside `EcosystemDetailPage.__init__`**

In `pages.py`, search for `EcosystemGraphView(` to find where the page constructs its graph. There's typically a `self._graph_view = EcosystemGraphView(...)` line.

- [ ] **Step 2: Add signal forwarding right after construction**

Right after the line that constructs `self._graph_view`, add:

```python
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
```

- [ ] **Step 3: Add the two adapter methods**

Anywhere inside `class EcosystemDetailPage` (e.g., near other internal `_on_*` methods), add:

```python
    def _on_graph_add_permitted_issuer(self, aid: str, said: str) -> None:
        if self._current_name is None:
            return
        self.add_permitted_issuer_clicked.emit(self._current_name, said, aid)

    def _on_graph_remove_permitted_issuer(self, aid: str, said: str) -> None:
        if self._current_name is None:
            return
        self.remove_permitted_issuer_clicked.emit(self._current_name, said, aid)
```

- [ ] **Step 4: Smoke-test**

```bash
pgrep -f "locksmith.main" | xargs -r kill -9 2>/dev/null
sleep 1
cd /Users/seriouscoderone/code/locksmith/.worktrees/ecosystem-viewer
.venv/bin/python -m locksmith.main &
WALLET_PID=$!
sleep 6
LOG=$(ls -t /private/tmp/claude-501/*/tasks/*.output 2>/dev/null | head -1)
[ -n "$LOG" ] && tail -10 "$LOG"
kill -9 $WALLET_PID 2>/dev/null
```

Confirm clean startup. (The signals don't fire until T5/T7 wire the drag and right-click; this task just establishes the plumbing.)

- [ ] **Step 5: Commit**

```bash
cd /Users/seriouscoderone/code/locksmith/.worktrees/ecosystem-viewer
git add src/locksmith/plugins/ecosystem_viewer/pages.py
git commit -m "$(cat <<'EOF'
feat(ecosystem-viewer): forward graph-canvas permitted-issuer signals

EcosystemDetailPage now connects EcosystemGraphView.add_permitted_
issuer_requested / remove_permitted_issuer_requested to the same page-
level signals (add_permitted_issuer_clicked /
remove_permitted_issuer_clicked) that the List tab's chip row already
drives. The plugin's existing handlers (_add_permitted_issuer /
_remove_permitted_issuer) need no changes — both views write through
the same path. Per design §3.2 ("zero new plugin handler code").

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Drag-to-create state machine in `_GraphView`

Goal: pressing on an `IssuerNode` and moving the cursor more than 4px starts drawing a rubber-band line; releasing on a `SchemaNode` commits via `add_permitted_issuer_requested`. Empty-canvas pan continues to work.

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/graph_view.py` (`_GraphView` class at the bottom)

- [ ] **Step 1: Read the existing `_GraphView`**

In `graph_view.py`, find `class _GraphView(QGraphicsView):` near the bottom. Note its `mousePressEvent` is currently:

```python
    def mousePressEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        super().mousePressEvent(event)
        if item is None and event.button() == Qt.MouseButton.LeftButton:
            self.background_clicked.emit()
```

You'll be expanding this class with three event overrides + state.

- [ ] **Step 2: Add drag-state attributes to `__init__`**

Find `_GraphView.__init__` and append after the existing body:

```python
    def __init__(self, scene: QGraphicsScene, parent: QWidget | None = None):
        super().__init__(scene, parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # Drag-to-create-edge state (Stage 11). Initialized lazily in
        # mousePressEvent when a press lands on an IssuerNode.
        self._drag_origin_aid: str | None = None
        self._drag_origin_pos = None  # QPointF in scene coords
        self._drag_press_view_pos = None  # QPoint in view coords (for threshold)
        self._drag_rubber_band = None  # QGraphicsLineItem during drag
        self._drag_active = False
        self._current_snap_target_said: str | None = None
```

- [ ] **Step 3: Override `mousePressEvent` to detect press on IssuerNode**

Replace the existing `mousePressEvent`:

```python
    def mousePressEvent(self, event):
        # If the press lands on an IssuerNode, capture the press for a
        # potential drag-to-create-edge gesture. Don't enter drag mode
        # until movement exceeds the threshold (Qt's startDragDistance,
        # default 4px on macOS), so a click without move still selects
        # the issuer and opens the side panel.
        item = self.itemAt(event.position().toPoint())
        if (
            event.button() == Qt.MouseButton.LeftButton
            and isinstance(item, IssuerNode)
        ):
            self._drag_origin_aid = item.aid
            self._drag_origin_pos = item.top_anchor()
            self._drag_press_view_pos = event.position().toPoint()
            # Don't call super here — let the issuer node's own
            # mousePressEvent fire (which emits clicked + accepts).
            super().mousePressEvent(event)
            return

        # Reset any stale drag state and proceed with default behavior.
        self._drag_origin_aid = None
        self._drag_origin_pos = None
        self._drag_press_view_pos = None

        super().mousePressEvent(event)
        if item is None and event.button() == Qt.MouseButton.LeftButton:
            self.background_clicked.emit()
```

- [ ] **Step 4: Override `mouseMoveEvent` to enter drag mode + update rubber band**

Below `mousePressEvent`, add:

```python
    def mouseMoveEvent(self, event):
        # Entering drag mode: cross the 4px movement threshold while a
        # press is active on an IssuerNode.
        if (
            self._drag_origin_aid is not None
            and not self._drag_active
            and self._drag_press_view_pos is not None
        ):
            delta = (event.position().toPoint() - self._drag_press_view_pos)
            if delta.manhattanLength() >= self._start_drag_distance():
                self._begin_drag()

        if self._drag_active:
            scene_pos = self.mapToScene(event.position().toPoint())
            self._update_rubber_band(scene_pos)
            self._update_snap_targets(scene_pos)
            event.accept()
            return  # don't pan while drawing

        super().mouseMoveEvent(event)

    @staticmethod
    def _start_drag_distance() -> int:
        from PySide6.QtWidgets import QApplication
        return QApplication.startDragDistance() if QApplication.instance() else 4
```

- [ ] **Step 5: Override `mouseReleaseEvent` to commit or cancel**

Below `mouseMoveEvent`, add:

```python
    def mouseReleaseEvent(self, event):
        if self._drag_active and event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.position().toPoint())
            target = self._snap_target_at(scene_pos)
            self._end_drag(target)
            event.accept()
            return
        # Reset stale press capture (no drag was started).
        self._drag_origin_aid = None
        self._drag_origin_pos = None
        self._drag_press_view_pos = None
        super().mouseReleaseEvent(event)
```

- [ ] **Step 6: Add the drag helpers**

Below `mouseReleaseEvent`, add:

```python
    def _begin_drag(self) -> None:
        from PySide6.QtWidgets import QGraphicsLineItem
        from PySide6.QtCore import QLineF
        self._drag_active = True
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

        # Update per-schema snap states.
        already_issued = set(
            owner._eco.permitted_issuers.get(s, [])
            for s in owner._build_result.schema_nodes
        )
        for said, schema in owner._build_result.schema_nodes.items():
            if schema.ghost:
                schema.set_snap_target_state("ineligible")
                continue
            issued_by = owner._eco.permitted_issuers.get(said, [])
            if self._drag_origin_aid in issued_by:
                # Already issued by the dragging issuer → 'already'
                schema.set_snap_target_state("already")
            elif said == target_said:
                schema.set_snap_target_state("eligible")
            else:
                schema.set_snap_target_state("eligible")  # all eligible glow softly during drag

        self._current_snap_target_said = target_said

    def _snap_target_at(self, scene_pos):
        """Return the SchemaNode at scene_pos that's an eligible drop
        target, or None. Filters out ghost nodes and the rubber-band
        item itself."""
        owner = self.parent()
        items = self.scene().items(scene_pos)
        for item in items:
            if isinstance(item, SchemaNode) and not item.ghost:
                # Skip already-issued schemas? No — design says we still
                # snap, but the release shows a 'already' message.
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
            and self._drag_origin_aid is not None
            and isinstance(owner, EcosystemGraphView)
            and owner._eco is not None
        ):
            said = target.said
            already = self._drag_origin_aid in owner._eco.permitted_issuers.get(said, [])
            if not already:
                owner.add_permitted_issuer_requested.emit(self._drag_origin_aid, said)
            # else: silent no-op (already-issued case). Future polish:
            # show a toast.

        # Reset state.
        self._drag_active = False
        self._drag_origin_aid = None
        self._drag_origin_pos = None
        self._drag_press_view_pos = None
        self._current_snap_target_said = None
```

- [ ] **Step 7: Smoke-test the drag manually**

```bash
pgrep -f "locksmith.main" | xargs -r kill -9 2>/dev/null
sleep 1
cd /Users/seriouscoderone/code/locksmith/.worktrees/ecosystem-viewer
.venv/bin/python -m locksmith.main &
WALLET_PID=$!
sleep 6
LOG=$(ls -t /private/tmp/claude-501/*/tasks/*.output 2>/dev/null | head -1)
[ -n "$LOG" ] && tail -10 "$LOG"
```

Then manually navigate to an ecosystem detail page → Graph tab. Drag from an issuer node up to a schema node. Release. The page should refresh with the new permitted-issuer relationship visible as an edge. Stop the wallet:

```bash
pgrep -f "locksmith.main" | xargs -r kill -9
```

- [ ] **Step 8: Commit**

```bash
cd /Users/seriouscoderone/code/locksmith/.worktrees/ecosystem-viewer
git add src/locksmith/plugins/ecosystem_viewer/graph_view.py
git commit -m "$(cat <<'EOF'
feat(ecosystem-viewer): drag-to-create-edge state machine in graph view

Press on an IssuerNode + 4px movement enters drag mode; rubber-band
QGraphicsLineItem follows the cursor in scene coords. Release on a
SchemaNode commits via add_permitted_issuer_requested; release on
empty canvas cancels (rubber-band removed silently). Per design §3.3.

The 4px threshold (Qt's startDragDistance) means clicking an issuer
without moving still selects it and opens the side panel as before.
ScrollHandDrag pan is preserved on empty canvas; only initiates
drag-to-draw when the press lands on an issuer node.

Schema snap-target state is updated on every move so during drag the
node visuals follow the cursor (set_snap_target_state("eligible")
for non-ghost schemas; "ineligible" for ghosts; "already" for
schemas already issued by this issuer in this ecosystem).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Snap-target pulse-ring animation

Goal: when a schema is in `'eligible'` snap state during drag, its dashed teal ring pulses (subtle 1Hz alpha ramp). This is polish that can be skipped without functional impact, but the design calls for it (§3.3 "subtle 1Hz alpha 60%↔100%"). Implementation: a single `QPropertyAnimation` on a custom `QObject` property at the scene/owner level rather than per-node — simpler and avoids 30 simultaneous animations.

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/graph_view.py`

- [ ] **Step 1: Add a single shared pulse phase to `EcosystemGraphView`**

In `EcosystemGraphView.__init__` (in the body of `_build_chrome` or right after — find where `self._eco = None` etc. are set in `__init__`), after the existing `self._eco: Any | None = None` line, add:

```python
        # Snap-target pulse phase (Stage 11). Animated 0.0↔1.0 during
        # drag-to-create; consumed by SchemaNode.paint() to modulate the
        # eligible-ring alpha.
        self._snap_pulse_phase = 0.0
        self._snap_pulse_anim = None  # lazily created in _begin_snap_pulse
```

- [ ] **Step 2: Add the pulse property + animation hooks**

In `EcosystemGraphView` (anywhere, e.g. next to `_zoom_by`), add:

```python
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
```

Add the imports at the top of `graph_view.py` if missing:

```python
from PySide6.QtCore import Property, QPropertyAnimation
```

- [ ] **Step 3: Hook the pulse into the drag lifecycle**

In `_GraphView._begin_drag`, after `self._drag_active = True`, add:

```python
        owner = self.parent()
        if isinstance(owner, EcosystemGraphView):
            owner._begin_snap_pulse()
```

In `_GraphView._end_drag`, after `self._drag_active = False`, add:

```python
        if isinstance(owner, EcosystemGraphView):
            owner._end_snap_pulse()
```

- [ ] **Step 4: Use the pulse phase in `SchemaNode.paint`**

In `graph_items.py`, find the eligible-snap branch in `SchemaNode.paint()` (added in Task 2):

```python
        snap_state = getattr(self, "_snap_state", "off")
        if snap_state == "eligible":
            ring_color = QColor("#0D9488")  # teal
            pen = QPen(ring_color, 2)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self._build_outline_path())
```

Modify to use the owner's pulse phase for alpha:

```python
        snap_state = getattr(self, "_snap_state", "off")
        if snap_state == "eligible":
            # Modulate alpha with the owner-managed pulse phase so all
            # eligible nodes pulse in sync; falls back to constant 1.0
            # if no scene/owner pulse is running.
            phase = 1.0
            scene = self.scene()
            if scene is not None:
                views = scene.views()
                for v in views:
                    owner = v.parent()
                    if hasattr(owner, "_snap_pulse_phase"):
                        phase = 0.6 + 0.4 * owner._snap_pulse_phase
                        break
            ring_color = QColor("#0D9488")
            ring_color.setAlphaF(phase)
            pen = QPen(ring_color, 2)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self._build_outline_path())
```

- [ ] **Step 5: Smoke-test**

```bash
pgrep -f "locksmith.main" | xargs -r kill -9 2>/dev/null
sleep 1
cd /Users/seriouscoderone/code/locksmith/.worktrees/ecosystem-viewer
.venv/bin/python -m locksmith.main &
WALLET_PID=$!
sleep 6
LOG=$(ls -t /private/tmp/claude-501/*/tasks/*.output 2>/dev/null | head -1)
[ -n "$LOG" ] && tail -10 "$LOG"
```

Drag from an issuer; eligible schema rings should pulse. Stop the wallet.

- [ ] **Step 6: Commit**

```bash
cd /Users/seriouscoderone/code/locksmith/.worktrees/ecosystem-viewer
git add src/locksmith/plugins/ecosystem_viewer/graph_view.py src/locksmith/plugins/ecosystem_viewer/graph_items.py
git commit -m "$(cat <<'EOF'
feat(ecosystem-viewer): snap-target pulse-ring during drag-to-create

Per design §3.3: during drag-to-create, eligible SchemaNodes pulse a
dashed teal ring at 1Hz (alpha 60%↔100%). Single QPropertyAnimation
on a snap_pulse_phase property at the EcosystemGraphView level,
consumed by all eligible SchemaNode.paint() calls — avoids spinning
up one animation per node.

Started in _GraphView._begin_drag, stopped in _end_drag. The phase
modulates only the alpha of the dashed-ring stroke; non-eligible
states ('already', 'ineligible', 'off') are unaffected.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Empty-state hint when zero permitted-issuer edges exist

Goal: extend the existing `_update_hint` in `EcosystemGraphView` (which already handles zero-members / one-member / zero-edges cases per design §6.1) with a fourth case: ecosystem has ≥1 schema and ≥1 issuer but zero permitted-issuer edges. Hint: "Tip: drag from an issuer to a schema to mark them as the permitted issuer in this ecosystem."

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/graph_view.py`

- [ ] **Step 1: Find the existing `_update_hint`**

Search for `def _update_hint` in `graph_view.py`. It looks like:

```python
    def _update_hint(self, result: GraphBuildResult) -> None:
        n_real_schemas = sum(1 for n in result.schema_nodes.values() if not n.ghost)
        n_issuers = len(result.issuer_nodes)
        n_chain = len(result.chain_edges)
        total_members = n_real_schemas + n_issuers

        if total_members == 0:
            self._hint_label.setText(...)
            self._hint_label.show()
        elif total_members == 1:
            ...
        elif n_real_schemas >= 2 and n_chain == 0:
            ...
        else:
            self._hint_label.hide()
```

- [ ] **Step 2: Add the new case**

In the `else:` branch (currently just hides the label), add a new condition before the hide:

```python
    def _update_hint(self, result: GraphBuildResult) -> None:
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
```

(The first three branches stay byte-identical — only the new `elif` is inserted.)

- [ ] **Step 3: Smoke-test**

```bash
pgrep -f "locksmith.main" | xargs -r kill -9 2>/dev/null
sleep 1
cd /Users/seriouscoderone/code/locksmith/.worktrees/ecosystem-viewer
.venv/bin/python -m locksmith.main &
WALLET_PID=$!
sleep 6
LOG=$(ls -t /private/tmp/claude-501/*/tasks/*.output 2>/dev/null | head -1)
[ -n "$LOG" ] && tail -10 "$LOG"
```

Open an ecosystem with at least 1 schema + 1 issuer but no permitted-issuer assignments. The drag-tip should appear. Stop the wallet.

- [ ] **Step 4: Commit**

```bash
cd /Users/seriouscoderone/code/locksmith/.worktrees/ecosystem-viewer
git add src/locksmith/plugins/ecosystem_viewer/graph_view.py
git commit -m "$(cat <<'EOF'
feat(ecosystem-viewer): drag-to-create discoverability hint

Per design §6.1: when an ecosystem has ≥1 schema, ≥1 issuer, but no
permitted-issuer edges yet, surface a hint: "Tip: drag from an issuer
node up to a schema to mark them as the permitted issuer in this
ecosystem." Sits in the same overlay slot as the existing zero-
member / one-member / no-chain hints.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-review checklist results

**Spec coverage** — every recommendation in `2026-05-08-permitted-issuer-edges.md` §7 ("Summary of recommended deltas") has a task:

- §7.1 `PermittedIssuerEdge` class + `set_snap_target_state` on nodes → Task 2 ✓
- §7.2 graph_view step 7b + bottom-row barycentric reordering + new signals + drag state machine + empty-state hint → Tasks 1, 3, 5, 7 ✓
- §7.3 wire graph signals to existing handler slots → Task 4 ✓
- §7.4 layout `bottom_row_ordering_edges` ~15 LOC → Task 1 ✓
- §7.5 no asset commissioning → matches plan ✓
- §7.6 no data-model changes → matches plan ✓

**Deferred-from-design (called out in the design itself):**
- Toast/undo on edge removal: design §3.3 mentions a 6s undo toast. Skipped here — the wallet's existing `NotificationToast` infrastructure runs on `vault.signals.doer_event` which is heavier than this feature warrants. Right-click delete remains available; user can drag again to recreate. Note for a future polish task.
- Multi-select drag: rejected for v1 in design §6.4.
- Keyboard-accessible drag: predates this extension; not blocking (§6.3).

**Type consistency:** signal signatures align — `(aid, schema_said)` for graph-view signals, `(eco_name, schema_said, aid)` for page-level signals (the page's adapter folds the eco name in). `PermittedIssuerEdge(source, target)` parallels `MembershipEdge(source, target)`. `set_snap_target_state(state: str)` on both `IssuerNode` (no-op) and `SchemaNode` (active).

**Placeholder scan:** no "TBD", no "implement appropriate", no bare "write tests". Code blocks show actual code. Test cases verify behavior (layer ordering after barycenter pass).

**Type consistency check across tasks:**
- T1 introduces `bottom_row_ordering_edges`; T3 passes it
- T2 introduces `PermittedIssuerEdge.emitter.remove_requested(str, str)` and `set_snap_target_state`; T3 connects the emitter signal; T5 calls `set_snap_target_state`; T6 reads `_snap_state` from inside `SchemaNode.paint()`
- T2's `_Emitter` class lives inside `PermittedIssuerEdge` — verified by reading the class structure
- T3 introduces `permitted_issuer_edges: list` on `GraphBuildResult`; T7 reads `len(result.permitted_issuer_edges)`

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-08-permitted-issuer-edges-implementation.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, two-stage review between each.

**2. Inline Execution** — execute tasks in this session with checkpoints.

Which approach?
