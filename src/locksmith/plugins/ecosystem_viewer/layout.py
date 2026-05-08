# -*- encoding: utf-8 -*-
"""
locksmith.plugins.ecosystem_viewer.layout module

Pure-Python hierarchical (Sugiyama-style) graph layout for the ecosystem
graph view (design §5.5/§6.3). No external graph-layout dependency —
keripy and Locksmith intentionally avoid graphviz/OGDF, which ship
binaries that complicate macOS notarization.

Algorithm sketch:

1. Layer assignment: longest-path-from-root via topological order.
   Roots (no incoming edges) get layer 0; every other node's layer is
   max(layer(predecessors)) + 1.

2. Cycle handling: graphlib.TopologicalSorter raises CycleError on
   cycles. We detect cycles up front by attempting a topological sort,
   then iteratively remove the highest-out-degree edge participating in
   a cycle (treating it as a "feedback" edge to be rendered separately).
   The removed feedback edges are returned in the result so the caller
   can render them with reverse orientation / red tint.

3. Per-layer ordering: barycentric reordering, two passes (down-up).
   For each layer, sort nodes by the average position of their
   neighbors in the adjacent layer.

4. Coordinate assignment: nodes in a layer are spaced evenly at the
   layer's depth coordinate. Layer spacing and node spacing are
   parameters of the layout call.

5. Issuer-AID nodes (passed via `bottom_row_nodes`) are placed in their
   own row at the maximum-depth + 1 layer, regardless of edges.

The output is a `LayoutResult` with absolute (x, y) coordinates per
node ID and the list of feedback edges. Coordinates are *centers* of
the bounding boxes; the caller knows each node's size and translates
by half-width/half-height.

This layout is read-only: it doesn't mutate the input graph. It's used
by EcosystemGraphView (Phase D3) and is reusable for the schema-detail
mini-graph if we want to replace its hand-placed positions later.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Hashable, Iterable, TypeVar

NodeId = TypeVar("NodeId", bound=Hashable)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LayoutOptions:
    """Tunables for hierarchical layout."""

    layer_spacing: float = 140.0
    """Vertical (or horizontal in LR) gap between adjacent layers, in px."""

    node_spacing: float = 40.0
    """Horizontal gap between sibling nodes within a layer, in px."""

    node_width: float = 140.0
    """Nominal node width, used for x-spacing arithmetic."""

    node_height: float = 80.0
    """Nominal node height, used for y-spacing arithmetic in LR mode."""

    orientation: str = "top-to-bottom"
    """Either 'top-to-bottom' (TB) or 'left-to-right' (LR)."""

    barycenter_passes: int = 2
    """How many barycentric reordering passes to run (1 = down only)."""


@dataclass
class LayoutResult:
    """Output of layout_hierarchical."""

    positions: dict = field(default_factory=dict)
    """Node id → (x, y) center coordinate."""

    feedback_edges: list = field(default_factory=list)
    """(src, dst) edges that were removed to break cycles. Caller can
    render them as reverse arrows or with a tint to call them out."""

    layers: list = field(default_factory=list)
    """List of layers (each a list of node ids in left-to-right order)
    after barycentric reordering. Useful for diagnostics + ghost-node
    placement."""


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------


def layout_hierarchical(
    nodes: Iterable[Hashable],
    edges: Iterable[tuple[Hashable, Hashable]],
    *,
    bottom_row_nodes: Iterable[Hashable] = (),
    bottom_row_ordering_edges: Iterable[tuple[Hashable, Hashable]] = (),
    role_row_nodes: Iterable[Hashable] | None = None,
    role_row_ordering_edges: Iterable[tuple[Hashable, Hashable]] | None = None,
    options: LayoutOptions | None = None,
) -> LayoutResult:
    """Compute (x, y) positions for `nodes` connected by `edges`.

    Parameters
    ----------
    nodes : iterable of hashable
        All node IDs participating in the layout. Isolated nodes (no
        edges) are still laid out — they get their own layer 0 cluster.
    edges : iterable of (src, dst)
        Directed edges. src/dst must be members of `nodes`.
    bottom_row_nodes : iterable of hashable
        Subset of `nodes` to pin in a dedicated final row regardless of
        their actual edge depth. Intended for issuer-AID nodes (per
        design §5.5) which should sit beneath the schema chain rather
        than competing with it for layer assignment.
    bottom_row_ordering_edges : iterable of (src, dst)
        Edges connecting bottom-row nodes to chain nodes, used to reorder
        the bottom row by barycenter (mean x-position of connected upper
        neighbors). Per design §2.5 mitigation 3. Empty default preserves
        prior alphabetical ordering.
    role_row_nodes : iterable of hashable, optional
        Subset of `nodes` to pin in a dedicated row sitting between the
        deepest schema layer and the bottom row. Intended for role nodes
        (Stage 14) which qualify against schemas but should not compete
        with them for layering. None/empty means no role row is created.
    role_row_ordering_edges : iterable of (src, dst), optional
        (schema_node_id, role_node_id) pairs that drive barycenter
        ordering of the role row by mean x-position of qualifying schemas.
        Roles without an ordering edge fall back to alphabetical at the
        end (mirrors bottom-row behaviour).
    options : LayoutOptions
        Spacing + orientation tunables.

    Returns
    -------
    LayoutResult with .positions, .feedback_edges, .layers.
    """
    opts = options or LayoutOptions()
    node_set = set(nodes)
    bottom_set = set(bottom_row_nodes) & node_set
    role_set = set(role_row_nodes or ()) & node_set
    # Roles never overlap the bottom row; bottom-row pinning wins if both
    # are specified for the same id.
    role_set -= bottom_set

    # Filter edges to those within the node set; defensively dedupe.
    edge_set: set[tuple[Hashable, Hashable]] = set()
    for src, dst in edges:
        if src in node_set and dst in node_set and src != dst:
            edge_set.add((src, dst))

    # Bottom-row and role-row nodes are excluded from chain layering —
    # they're placed in dedicated rows regardless. Their incoming/outgoing
    # edges are kept (the caller uses them to draw membership lines), but
    # they don't influence layer depth of other nodes.
    chain_nodes = node_set - bottom_set - role_set
    chain_edges = {(s, d) for (s, d) in edge_set if s in chain_nodes and d in chain_nodes}

    # 1. Cycle removal — peel off feedback edges until acyclic.
    chain_edges, feedback = _break_cycles(chain_nodes, chain_edges)

    # 2. Layer assignment via longest path from any source.
    layer_of = _assign_layers(chain_nodes, chain_edges)

    # 3. Group by layer and apply barycentric reordering.
    layers: list[list[Hashable]] = _group_into_layers(chain_nodes, layer_of)
    for _ in range(opts.barycenter_passes):
        _barycentric_pass(layers, chain_edges, downward=True)
        _barycentric_pass(layers, chain_edges, downward=False)

    # 4. Role-row nodes get a dedicated layer between the schema chain
    # and the bottom row, ordered by barycenter of their qualifying
    # schemas' positions.
    if role_set:
        layers.append(_order_role_row(
            role_set,
            list(role_row_ordering_edges or ()),
            chain_layers=layers,
        ))

    # 5. Bottom-row nodes get a dedicated final layer.
    if bottom_set:
        layers.append(_order_bottom_row(
            bottom_set,
            list(bottom_row_ordering_edges),
            chain_layers=layers,
        ))

    # 6. Coordinate assignment.
    positions = _assign_coordinates(layers, opts)

    return LayoutResult(positions=positions, feedback_edges=feedback, layers=layers)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _break_cycles(
    nodes: set[Hashable],
    edges: set[tuple[Hashable, Hashable]],
) -> tuple[set[tuple[Hashable, Hashable]], list[tuple[Hashable, Hashable]]]:
    """Iteratively remove an edge participating in a cycle until acyclic.

    Strategy: pick the edge whose source has the highest out-degree among
    edges in the cycle; this tends to preserve "tree-like" structure.
    Returns (acyclic_edges, removed_edges).
    """
    feedback: list[tuple[Hashable, Hashable]] = []
    edges = set(edges)

    while True:
        cycle = _find_cycle(nodes, edges)
        if cycle is None:
            return edges, feedback
        # Pick the edge in the cycle whose source has the highest out-degree;
        # ties broken by source then dst lexicographic — deterministic.
        out_deg: dict[Hashable, int] = defaultdict(int)
        for s, _ in edges:
            out_deg[s] += 1

        cycle_edges = list(zip(cycle, cycle[1:] + cycle[:1]))
        cycle_edges = [e for e in cycle_edges if e in edges]
        if not cycle_edges:
            # Defensive: shouldn't happen; bail.
            return edges, feedback
        cycle_edges.sort(key=lambda e: (-out_deg[e[0]], str(e[0]), str(e[1])))
        worst = cycle_edges[0]
        edges.remove(worst)
        feedback.append(worst)


def _find_cycle(
    nodes: set[Hashable],
    edges: set[tuple[Hashable, Hashable]],
) -> list[Hashable] | None:
    """Return one cycle as a list of nodes (in cycle order), or None if acyclic."""
    out: dict[Hashable, list[Hashable]] = defaultdict(list)
    for s, d in edges:
        out[s].append(d)

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[Hashable, int] = {n: WHITE for n in nodes}
    parent: dict[Hashable, Hashable | None] = {n: None for n in nodes}

    for start in nodes:
        if color[start] != WHITE:
            continue
        stack: list[tuple[Hashable, int]] = [(start, 0)]
        color[start] = GRAY
        while stack:
            node, idx = stack[-1]
            successors = out[node]
            if idx < len(successors):
                stack[-1] = (node, idx + 1)
                nxt = successors[idx]
                if color[nxt] == GRAY:
                    # Found cycle. Walk back from `node` to `nxt` via parent.
                    cycle = [nxt]
                    cur = node
                    while cur != nxt and cur is not None:
                        cycle.append(cur)
                        cur = parent.get(cur)
                    cycle.reverse()
                    return cycle
                if color[nxt] == WHITE:
                    color[nxt] = GRAY
                    parent[nxt] = node
                    stack.append((nxt, 0))
            else:
                color[node] = BLACK
                stack.pop()
    return None


def _assign_layers(
    nodes: set[Hashable],
    edges: set[tuple[Hashable, Hashable]],
) -> dict[Hashable, int]:
    """Longest-path layer assignment. Roots = layer 0."""
    preds: dict[Hashable, list[Hashable]] = defaultdict(list)
    for s, d in edges:
        preds[d].append(s)

    layer: dict[Hashable, int] = {}

    def depth(n: Hashable, visiting: set[Hashable]) -> int:
        if n in layer:
            return layer[n]
        if n in visiting:
            # Should never happen — cycles already removed; guard anyway.
            return 0
        visiting.add(n)
        if not preds.get(n):
            layer[n] = 0
        else:
            layer[n] = 1 + max(depth(p, visiting) for p in preds[n])
        visiting.discard(n)
        return layer[n]

    for n in nodes:
        depth(n, set())
    return layer


def _group_into_layers(
    nodes: set[Hashable],
    layer_of: dict[Hashable, int],
) -> list[list[Hashable]]:
    if not nodes:
        return []
    max_layer = max(layer_of.get(n, 0) for n in nodes)
    layers: list[list[Hashable]] = [[] for _ in range(max_layer + 1)]
    for n in sorted(nodes, key=str):
        layers[layer_of.get(n, 0)].append(n)
    return layers


def _barycentric_pass(
    layers: list[list[Hashable]],
    edges: set[tuple[Hashable, Hashable]],
    *,
    downward: bool,
) -> None:
    """Reorder each layer (in place) by barycenter of neighbors in the
    *previous* layer (downward) or *next* layer (upward)."""
    if downward:
        # Build map: dst → list of src indices in dst's layer-1.
        for layer_idx in range(1, len(layers)):
            prev = layers[layer_idx - 1]
            prev_pos = {n: i for i, n in enumerate(prev)}
            cur = layers[layer_idx]
            cur_pos = {n: i for i, n in enumerate(cur)}

            def bary(node: Hashable, _edges=edges, _prev_pos=prev_pos, _cur_pos=cur_pos) -> float:
                positions_ = [
                    _prev_pos[s] for (s, d) in _edges
                    if d == node and s in _prev_pos
                ]
                if not positions_:
                    return float(_cur_pos[node])
                return sum(positions_) / len(positions_)

            cur.sort(key=lambda n, _b=bary: (_b(n), str(n)))
    else:
        for layer_idx in range(len(layers) - 2, -1, -1):
            nxt = layers[layer_idx + 1]
            nxt_pos = {n: i for i, n in enumerate(nxt)}
            cur = layers[layer_idx]
            # Snapshot original positions so the sort key is stable for nodes
            # with no successors in nxt (preserves their current order).
            cur_pos = {n: i for i, n in enumerate(cur)}

            def bary(node: Hashable, _edges=edges, _nxt_pos=nxt_pos, _cur_pos=cur_pos) -> float:
                positions_ = [
                    _nxt_pos[d] for (s, d) in _edges
                    if s == node and d in _nxt_pos
                ]
                if not positions_:
                    return float(_cur_pos[node])
                return sum(positions_) / len(positions_)

            cur.sort(key=lambda n, _b=bary: (_b(n), str(n)))


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


def _order_role_row(
    role_set: set[Hashable],
    ordering_edges: list[tuple[Hashable, Hashable]],
    chain_layers: list[list[Hashable]],
) -> list[Hashable]:
    """Order role-row nodes by barycenter of their qualifying-schema x-positions."""
    chain_pos: dict[Hashable, float] = {}
    for layer in chain_layers:
        for i, node in enumerate(layer):
            chain_pos[node] = float(i)

    contributions: dict[Hashable, list[float]] = {n: [] for n in role_set}
    for src, dst in ordering_edges:
        if src in role_set and dst in chain_pos:
            contributions[src].append(chain_pos[dst])
        if dst in role_set and src in chain_pos:
            contributions[dst].append(chain_pos[src])

    barycenters: dict[Hashable, float | None] = {
        n: (sum(cs) / len(cs)) if (cs := contributions[n]) else None
        for n in role_set
    }

    with_bary = sorted(
        (n for n in role_set if barycenters[n] is not None),
        key=lambda n: (barycenters[n], str(n)),
    )
    without_bary = sorted(
        (n for n in role_set if barycenters[n] is None),
        key=str,
    )
    return list(with_bary) + list(without_bary)


def _assign_coordinates(
    layers: list[list[Hashable]],
    opts: LayoutOptions,
) -> dict[Hashable, tuple[float, float]]:
    """Centers each layer about x=0 (TB) or y=0 (LR), spaces by node+gap."""
    positions: dict[Hashable, tuple[float, float]] = {}
    if not layers:
        return positions

    if opts.orientation == "top-to-bottom":
        for layer_idx, layer in enumerate(layers):
            y = layer_idx * (opts.node_height + opts.layer_spacing)
            slot = opts.node_width + opts.node_spacing
            total = max(0, len(layer) - 1) * slot
            x_start = -total / 2.0
            for i, node in enumerate(layer):
                positions[node] = (x_start + i * slot, y)
    else:  # left-to-right
        for layer_idx, layer in enumerate(layers):
            x = layer_idx * (opts.node_width + opts.layer_spacing)
            slot = opts.node_height + opts.node_spacing
            total = max(0, len(layer) - 1) * slot
            y_start = -total / 2.0
            for i, node in enumerate(layer):
                positions[node] = (x, y_start + i * slot)
    return positions
