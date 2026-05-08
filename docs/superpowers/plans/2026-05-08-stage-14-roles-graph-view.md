# Stage 14 — Roles + Qualification Edges in the Graph View

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface ecosystem `RoleRecord`s and their schema-qualification rules as first-class graphics in `EcosystemGraphView` — role nodes alongside issuer-AID nodes, qualification edges schema→role, drag-to-create, removal, and a side-panel for roles.

**Architecture:** Two new `QGraphicsItem` subclasses (`RoleNode`, `QualificationEdge`) live in `graph_items.py`. `layout.py` learns about a separate "role row" between the schema layers and the issuer-AID bottom row so roles cluster near their qualification schemas (via barycenter ordering). `EcosystemGraphView` instantiates both new item types when the ecosystem has roles / `issuer_qualification_rules`, wires their signals, and extends the existing drag-to-create flow to accept `RoleNode → SchemaNode` drops. `side_panel.py` gains a `show_role()` method. Plugin layer (`plugin.py`) handles the new `add_qualification_rule_requested` / `remove_qualification_rule_requested` signals by writing to `EcosystemRecord.issuer_qualification_rules` and persisting via `EcosystemBaser.put_ecosystem`.

**Tech Stack:** PySide6 (Qt 6), Python 3.13, pytest with `QT_QPA_PLATFORM=offscreen`. Visual smoke tests follow `tests/test_create_role_dialog_visual.py`.

---

## File Structure

| File | Purpose | Change |
|------|---------|--------|
| `src/locksmith/plugins/ecosystem_viewer/graph_items.py` | All `QGraphicsItem` subclasses | Add `RoleNode` (~80 LOC), `QualificationEdge` (~70 LOC) |
| `src/locksmith/plugins/ecosystem_viewer/layout.py` | Layered layout helper | Add `role_row_nodes` + `role_row_ordering_edges` params, position role row between schema layers and issuer row |
| `src/locksmith/plugins/ecosystem_viewer/graph_view.py` | `EcosystemGraphView` widget | Build role nodes + qualification edges, wire signals, extend drag-to-create, route to side panel |
| `src/locksmith/plugins/ecosystem_viewer/side_panel.py` | Side panel for selected items | Add `show_role(role, members, qualification_schema_title, issuer_role_label)` |
| `src/locksmith/plugins/ecosystem_viewer/plugin.py` | Plugin wiring | New handlers `_on_add_qualification_rule_via_graph` / `_on_remove_qualification_rule_via_graph` |
| `tests/test_layout_role_row.py` | New | Pure-Python layout assertions for the role row ordering |
| `tests/test_role_node_visual.py` | New | Visual smoke test — render `RoleNode` + `QualificationEdge`, structural asserts + screenshot |
| `tests/test_graph_view_roles.py` | New | Builds an `EcosystemRecord` with roles, instantiates `EcosystemGraphView`, asserts scene contents and screenshot |

Total: ~600-700 LOC across 5 source files + 3 new test files.

---

## Task 1: `RoleNode` graphics item

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/graph_items.py:643-825` (add `RoleNode` after `IssuerNode`)
- Test: `tests/test_role_node_visual.py` (new)

**Visual spec:** A 64×64 hexagon outlined in teal (`#0ABFB0`, the same teal used by `PermittedIssuerEdge` line 868) with the role name inside (truncated to ~12 chars with ellipsis), a small badge below showing "N members" (resolved member count, set by the parent), and a hover/selected halo. Hexagon (not circle) deliberately says "category" rather than "individual AID". `RoleNode.role_name` is the canonical id; the hex shape is purely a visual differentiator.

**Signals:**
- `clicked = Signal()` — left-click for selection (parent populates side panel)
- `double_clicked = Signal()` — opens role detail (defer wiring to T6, just emit)

- [ ] **Step 1: Write the failing visual smoke test**

```python
# tests/test_role_node_visual.py
from __future__ import annotations
from pathlib import Path
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView

from locksmith.plugins.ecosystem_viewer.graph_items import RoleNode

SHOTS_DIR = Path(__file__).parent / "_screenshots"


def _grab(widget, name):
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = SHOTS_DIR / f"{name}.png"
    pixmap = widget.grab()
    assert pixmap.save(str(path))
    return path


def test_role_node_renders_hexagon_with_label_and_member_count(qapp):
    scene = QGraphicsScene()
    view = QGraphicsView(scene)
    view.resize(360, 200)

    node = RoleNode(role_name="state-doi", member_count=3)
    node.setPos(QPointF(40, 40))
    scene.addItem(node)

    other = RoleNode(role_name="aggregator", member_count=0)
    other.setPos(QPointF(180, 40))
    scene.addItem(other)

    view.show()
    QTest.qWait(200)
    qapp.processEvents()

    # Structural assertions
    assert node.role_name == "state-doi"
    assert node.member_count == 3
    assert node.boundingRect().width() == 64
    assert node.boundingRect().height() == 64
    items = scene.items()
    assert len(items) == 2

    shot = _grab(view, "role_node_two_hexagons")
    assert shot.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/test_role_node_visual.py::test_role_node_renders_hexagon_with_label_and_member_count -v`
Expected: FAIL with `ImportError: cannot import name 'RoleNode'`

- [ ] **Step 3: Implement `RoleNode`**

Insert after the `IssuerNode` class in `graph_items.py` (~line 825). The class follows the same pattern as `IssuerNode` (`graph_items.py:643-825`): inherits `QGraphicsObject`, paints in `paint()`, exposes signals, has `top_anchor()` and `bottom_anchor()` helpers used by edges.

```python
class RoleNode(QGraphicsObject):
    """A role — a credential-qualified class of AIDs.

    Visually a teal-outlined hexagon with the role name inside and a
    member-count badge. Behaves like an IssuerNode for layout / edge
    anchoring purposes, but represents a *category* of issuers rather
    than a specific AID.
    """

    NODE_DIAMETER = 64
    LABEL_FONT_PT = 9
    BADGE_FONT_PT = 8
    OUTLINE_COLOR = QColor("#0ABFB0")  # same teal as PermittedIssuerEdge
    OUTLINE_WIDTH = 2.0
    FILL_COLOR = QColor("#FFFFFF")
    SELECTED_OUTLINE_WIDTH = 3.0
    HOVER_OUTLINE_WIDTH = 2.5

    clicked = Signal()
    double_clicked = Signal()

    def __init__(self, role_name: str, member_count: int = 0,
                 parent: QGraphicsItem | None = None):
        super().__init__(parent)
        self.role_name = role_name
        self.member_count = member_count
        self._is_hovered = False
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

    def boundingRect(self) -> QRectF:
        # Add room for the label below the hexagon
        d = self.NODE_DIAMETER
        return QRectF(0, 0, d, d + 22)

    def _hexagon_path(self) -> QPainterPath:
        d = self.NODE_DIAMETER
        cx, cy, r = d / 2, d / 2, d / 2 - 2
        path = QPainterPath()
        for i in range(6):
            angle = (math.pi / 3) * i - math.pi / 2  # flat-top hex
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        path.closeSubpath()
        return path

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        outline_w = self.OUTLINE_WIDTH
        if self.isSelected():
            outline_w = self.SELECTED_OUTLINE_WIDTH
        elif self._is_hovered:
            outline_w = self.HOVER_OUTLINE_WIDTH
        painter.setPen(QPen(self.OUTLINE_COLOR, outline_w))
        painter.setBrush(self.FILL_COLOR)
        painter.drawPath(self._hexagon_path())

        # Truncated role-name label inside the hex
        font = QFont()
        font.setPointSize(self.LABEL_FONT_PT)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(QColor("#1A1C20")))
        label = self.role_name if len(self.role_name) <= 12 else self.role_name[:11] + "…"
        painter.drawText(
            QRectF(0, 0, self.NODE_DIAMETER, self.NODE_DIAMETER),
            Qt.AlignmentFlag.AlignCenter, label,
        )

        # Member-count badge below
        badge_font = QFont()
        badge_font.setPointSize(self.BADGE_FONT_PT)
        painter.setFont(badge_font)
        painter.setPen(QPen(QColor("#666")))
        badge_text = f"{self.member_count} member{'s' if self.member_count != 1 else ''}"
        painter.drawText(
            QRectF(0, self.NODE_DIAMETER + 2, self.NODE_DIAMETER, 18),
            Qt.AlignmentFlag.AlignCenter, badge_text,
        )

    def top_anchor(self) -> QPointF:
        return self.mapToScene(QPointF(self.NODE_DIAMETER / 2, 0))

    def bottom_anchor(self) -> QPointF:
        return self.mapToScene(QPointF(self.NODE_DIAMETER / 2, self.NODE_DIAMETER))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)

    def hoverEnterEvent(self, event) -> None:
        self._is_hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self._is_hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def set_member_count(self, count: int) -> None:
        if count != self.member_count:
            self.member_count = count
            self.update()
```

You'll need to add `import math` at the top of `graph_items.py` if it's not already there, and confirm `Signal`, `QGraphicsItem`, `QGraphicsObject`, `QRectF`, `QPainterPath`, `QPainter`, `QPen`, `QFont`, `QColor`, `Qt` are imported (they are — used by `IssuerNode`).

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/test_role_node_visual.py -v`
Expected: PASS, with screenshot at `tests/_screenshots/role_node_two_hexagons.png`

- [ ] **Step 5: Vision-check the screenshot**

Read `tests/_screenshots/role_node_two_hexagons.png` and confirm: two teal-outlined hexagons, "state-doi" and "aggregator" labels visible inside, "3 members" / "0 members" badges below. Adjust sizes/colors if visually off, then re-run.

- [ ] **Step 6: Commit**

```bash
git add src/locksmith/plugins/ecosystem_viewer/graph_items.py tests/test_role_node_visual.py
git commit -m "feat(ecosystem-viewer): RoleNode graphics item (Stage 14 T1)"
```

---

## Task 2: `QualificationEdge` graphics item

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/graph_items.py` (add after `PermittedIssuerEdge`, ~line 1010)
- Test: extend `tests/test_role_node_visual.py`

**Visual spec:** A dashed teal cubic-Bézier from a `SchemaNode.bottom_anchor()` to a `RoleNode.top_anchor()`, with a small "if" badge (white pill, teal text) at the midpoint indicating "members of the role qualify by holding this schema". Right-click → `remove_requested = Signal(str, str)` emitting `(schema_said, role_name)`. Same edge-following behaviour as `PermittedIssuerEdge` (`graph_items.py:917-929`): anchors are recomputed in `refresh()`.

- [ ] **Step 1: Write the failing test**

```python
# Add to tests/test_role_node_visual.py
from locksmith.plugins.ecosystem_viewer.graph_items import (
    RoleNode, QualificationEdge, SchemaNode,
)

def test_qualification_edge_renders_dashed_with_if_badge(qapp):
    scene = QGraphicsScene()
    view = QGraphicsView(scene)
    view.resize(400, 360)

    schema = SchemaNode(
        said="ECmEfS_Producer",
        title="ProducerLicense",
        variant="vc",
        disclosure_tier=None,
        section_fingerprint=None,
        lifecycle="current",
    )
    schema.setPos(QPointF(120, 30))
    scene.addItem(schema)

    role = RoleNode(role_name="state-doi", member_count=2)
    role.setPos(QPointF(150, 220))
    scene.addItem(role)

    edge = QualificationEdge(source_schema=schema, target_role=role)
    scene.addItem(edge)
    edge.refresh()

    view.show()
    QTest.qWait(200)
    qapp.processEvents()

    # Structural assertions
    assert edge.schema_said == "ECmEfS_Producer"
    assert edge.role_name == "state-doi"
    assert not edge.path().isEmpty()

    shot = _grab(view, "qualification_edge_schema_to_role")
    assert shot.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/test_role_node_visual.py::test_qualification_edge_renders_dashed_with_if_badge -v`
Expected: FAIL with `ImportError: cannot import name 'QualificationEdge'`

- [ ] **Step 3: Implement `QualificationEdge`**

Add after `PermittedIssuerEdge` in `graph_items.py`. Mirror the structure of `PermittedIssuerEdge` (`graph_items.py:868-1007`) but with dashed stroke, no arrowhead, and a midpoint "if" badge.

```python
class QualificationEdge(QGraphicsPathItem):
    """Edge from a schema to a role: 'members of this role qualify by
    holding this schema'.

    Drawn as a dashed teal cubic Bézier with a small 'if' badge at the
    midpoint. Right-click surfaces a 'Remove qualification rule' menu
    that emits remove_requested(schema_said, role_name).
    """

    EDGE_COLOR = QColor("#0ABFB0")
    BADGE_BG = QColor("#FFFFFF")
    BADGE_TEXT = QColor("#0ABFB0")
    STROKE_WIDTH = 1.6

    def __init__(self, source_schema: SchemaNode, target_role: RoleNode,
                 parent: QGraphicsItem | None = None):
        super().__init__(parent)
        self.source_schema = source_schema
        self.target_role = target_role
        self.schema_said = source_schema.said
        self.role_name = target_role.role_name

        pen = QPen(self.EDGE_COLOR, self.STROKE_WIDTH)
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setDashPattern([4, 3])
        self.setPen(pen)
        self.setBrush(Qt.BrushStyle.NoBrush)
        self.setZValue(-1)
        self.setAcceptHoverEvents(True)
        self._emitter = _QualificationEdgeEmitter(self)

    def refresh(self) -> None:
        src = self.source_schema.bottom_anchor()
        tgt = self.target_role.top_anchor()
        path = QPainterPath()
        path.moveTo(src)
        # Cubic Bézier with vertical-ish control points
        ctrl1 = QPointF(src.x(), src.y() + (tgt.y() - src.y()) * 0.4)
        ctrl2 = QPointF(tgt.x(), src.y() + (tgt.y() - src.y()) * 0.6)
        path.cubicTo(ctrl1, ctrl2, tgt)
        self.setPath(path)

    def paint(self, painter, option, widget=None) -> None:
        super().paint(painter, option, widget)
        # Draw the 'if' badge at the midpoint of the path
        if self.path().isEmpty():
            return
        mid = self.path().pointAtPercent(0.5)
        badge_w, badge_h = 22, 14
        rect = QRectF(mid.x() - badge_w / 2, mid.y() - badge_h / 2, badge_w, badge_h)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(self.BADGE_BG)
        painter.setPen(QPen(self.EDGE_COLOR, 1))
        painter.drawRoundedRect(rect, 4, 4)
        font = QFont()
        font.setPointSize(8)
        font.setItalic(True)
        painter.setFont(font)
        painter.setPen(QPen(self.BADGE_TEXT))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "if")

    def contextMenuEvent(self, event) -> None:
        from PySide6.QtWidgets import QMenu
        menu = QMenu()
        action = menu.addAction("Remove qualification rule")
        chosen = menu.exec(event.screenPos())
        if chosen is action:
            self._emitter.remove_requested.emit(self.schema_said, self.role_name)


class _QualificationEdgeEmitter(QObject):
    """QObject companion to surface signals for QGraphicsPathItem
    (which is not a QObject)."""
    remove_requested = Signal(str, str)

    def __init__(self, parent: QGraphicsItem):
        super().__init__()
        self._parent = parent
```

(`PermittedIssuerEdge` uses the same `_*Emitter` companion-object pattern at `graph_items.py:868-1007` — mirror it.)

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/test_role_node_visual.py -v`
Expected: 2 tests PASS.

- [ ] **Step 5: Vision-check**

Read `tests/_screenshots/qualification_edge_schema_to_role.png`. Confirm: dashed teal Bézier from schema to role, white "if" badge at midpoint, no arrowhead. If the badge sits awkwardly or the dash pattern looks wrong, tweak and re-run.

- [ ] **Step 6: Commit**

```bash
git add src/locksmith/plugins/ecosystem_viewer/graph_items.py tests/test_role_node_visual.py
git commit -m "feat(ecosystem-viewer): QualificationEdge graphics item (Stage 14 T2)"
```

---

## Task 3: Layout — role row between schemas and issuer row

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/layout.py:102-176` (`layout_hierarchical`), `:351-392` (`_order_bottom_row`), `:395-420` (`_assign_coordinates`)
- Test: `tests/test_layout_role_row.py` (new)

**Spec:** `layout_hierarchical` gains two new optional parameters:
- `role_row_nodes: list[str]` — node ids that belong in the role row (between schema layers and issuer row).
- `role_row_ordering_edges: list[tuple[str, str]]` — (schema_id, role_id) pairs that drive barycenter ordering of the role row, analogous to `bottom_row_ordering_edges`.

Roles get their own y-band, ordered by barycenter of their qualification schemas. If `role_row_nodes` is empty the existing layout is unchanged.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_layout_role_row.py
from locksmith.plugins.ecosystem_viewer.layout import (
    LayoutOptions, layout_hierarchical,
)


def test_role_row_orders_by_qualification_schema_barycenter():
    # Schemas A, B, C in one layer. Roles R1 (qualifies via A) and
    # R2 (qualifies via C). Issuers I1, I2 in the bottom row.
    result = layout_hierarchical(
        nodes=["A", "B", "C", "R1", "R2", "I1", "I2"],
        edges=[],
        bottom_row_nodes=["I1", "I2"],
        bottom_row_ordering_edges=[],
        role_row_nodes=["R1", "R2"],
        role_row_ordering_edges=[("A", "R1"), ("C", "R2")],
    )
    # Roles get their own layer between schemas (layer 0) and issuers
    # (last layer)
    role_layer = None
    for i, layer in enumerate(result.layers):
        if "R1" in layer:
            role_layer = i
            break
    assert role_layer is not None
    issuer_layer = next(i for i, layer in enumerate(result.layers) if "I1" in layer)
    assert role_layer < issuer_layer

    # R1 should sort to the LEFT of R2 because A is to the left of C
    role_layer_nodes = result.layers[role_layer]
    assert role_layer_nodes.index("R1") < role_layer_nodes.index("R2")


def test_role_row_omitted_when_no_role_nodes():
    result = layout_hierarchical(
        nodes=["A", "I1"],
        edges=[],
        bottom_row_nodes=["I1"],
        bottom_row_ordering_edges=[],
    )
    # No role layer should appear; behaviour identical to before.
    layer_count = len(result.layers)
    assert layer_count == 2  # schemas + issuers
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_layout_role_row.py -v`
Expected: FAIL — `layout_hierarchical()` doesn't accept `role_row_nodes` yet.

- [ ] **Step 3: Implement role-row layout**

Update `layout.py`:

1. Add to `LayoutOptions` if any role-row-specific spacing is needed (skip if you can reuse `node_spacing`).
2. Update `layout_hierarchical(...)` signature: add `role_row_nodes: list[str] | None = None, role_row_ordering_edges: list[tuple[str, str]] | None = None`.
3. After `_order_bottom_row` runs, add a parallel `_order_role_row(role_row_nodes, role_row_ordering_edges, schema_layers)` helper that sorts the role row by barycenter of its qualification-edge sources (using the schema layers' x-positions).
4. In `_assign_coordinates`, insert a "role row" layer between the last schema layer and the bottom row when `role_row_nodes` is non-empty. Y-position = `(last_schema_y + bottom_row_y) / 2` for clean visual spacing.
5. Append the role row to `result.layers` at the correct index so subsequent code that iterates `result.layers` sees it naturally.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_layout_role_row.py -v`
Expected: 2 tests PASS.

- [ ] **Step 5: Run the full layout test suite**

Run: `pytest tests/test_layout.py tests/test_layout_role_row.py -v`
Expected: all PASS — old layout tests must keep working since `role_row_nodes` defaults to None.

- [ ] **Step 6: Commit**

```bash
git add src/locksmith/plugins/ecosystem_viewer/layout.py tests/test_layout_role_row.py
git commit -m "feat(ecosystem-viewer): role-row layout between schemas and issuers (Stage 14 T3)"
```

---

## Task 4: `EcosystemGraphView` — render roles + qualification edges

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/graph_view.py:373-576` (the build/layout/render loop)
- Test: `tests/test_graph_view_roles.py` (new)

**Spec:** When the rendered ecosystem has `role_names`, build a `RoleNode` for each. When `issuer_qualification_rules` has entries, build a `QualificationEdge` for each `(schema_said, role_name)` pair. Use the resolver (`EcosystemBaser.resolve_role_members`) to populate `RoleNode.member_count`. Pass `role_row_nodes` + `role_row_ordering_edges` to `layout_hierarchical`. Wire `RoleNode.clicked → _on_role_clicked` (placeholder method that emits a new `role_selected = Signal(str)` upward — side panel wiring is T6). Wire `QualificationEdge._emitter.remove_requested → emit remove_qualification_rule_requested(schema_said, role_name)` at the view level (parallel to the existing `remove_permitted_issuer_requested` at `graph_view.py:638`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_graph_view_roles.py
from __future__ import annotations
from pathlib import Path
import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest

from locksmith.plugins.ecosystem_viewer.db import EcosystemRecord, RoleRecord
from locksmith.plugins.ecosystem_viewer.graph_view import EcosystemGraphView
from locksmith.plugins.ecosystem_viewer.graph_items import RoleNode, QualificationEdge

SHOTS_DIR = Path(__file__).parent / "_screenshots"


def _grab(widget, name):
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = SHOTS_DIR / f"{name}.png"
    pixmap = widget.grab()
    assert pixmap.save(str(path))
    return path


def _stub_inspections():
    # Build a minimal SchemaInspection-like object the graph view consumes.
    # If the real type lives elsewhere, import it. Otherwise build a stub
    # that satisfies the attribute access in EcosystemGraphView._build_scene.
    ...  # implementer fills in based on actual SchemaInspection contract


def test_graph_view_renders_role_node_and_qualification_edge(qapp):
    eco = EcosystemRecord(
        name="Insurance",
        schema_saids=["ECmEfS_Producer"],
        issuer_aids=["EBOG_AID_1"],
        role_names=["state-doi"],
        issuer_qualification_rules={"ECmEfS_Producer": "state-doi"},
    )
    role = RoleRecord(
        ecosystem_name="Insurance",
        name="state-doi",
        qualification_schema_said="ECmEfS_Producer",
        root_issuer_aids=["EBOG_AID_1"],
    )
    # Resolver function — simplest: returns the explicit root list
    def find_credentials_of_schema(said):
        return []  # no qualifying credentials in vault for this test
    def get_role(name):
        return role if name == "state-doi" else None
    def list_roles_for_eco(eco_name):
        return [role] if eco_name == "Insurance" else []

    view = EcosystemGraphView(
        # Adapt to actual constructor signature; pass the role-aware deps.
    )
    view.resize(800, 500)
    view.render_ecosystem(eco, _stub_inspections(), get_role=get_role,
                          list_roles=list_roles_for_eco,
                          find_credentials_of_schema=find_credentials_of_schema)
    view.show()
    QTest.qWait(300)
    qapp.processEvents()

    items = view.scene().items()
    role_nodes = [i for i in items if isinstance(i, RoleNode)]
    qualification_edges = [i for i in items if isinstance(i, QualificationEdge)]
    assert len(role_nodes) == 1
    assert role_nodes[0].role_name == "state-doi"
    assert len(qualification_edges) == 1
    assert qualification_edges[0].schema_said == "ECmEfS_Producer"
    assert qualification_edges[0].role_name == "state-doi"

    shot = _grab(view, "graph_view_one_role_one_qualification_edge")
    assert shot.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/test_graph_view_roles.py -v`
Expected: FAIL — `EcosystemGraphView.render_ecosystem` doesn't accept `get_role` / `list_roles` / `find_credentials_of_schema`, or doesn't build role nodes.

- [ ] **Step 3: Implement role + qualification rendering**

In `graph_view.py`:

1. Extend the `render_ecosystem(...)` (or equivalent build-scene method) to accept role-aware callables. The plugin layer will pass `vault_credential_finder(vault)` (already exists from Stage 13 T1) and `self._db.list_roles(eco.name)` / `self._db.get_role(eco.name, name)`.

2. After issuer nodes are built (around `graph_view.py:466`), build a `dict[str, RoleNode]` keyed by `role_name`. For each `RoleRecord`, compute `member_count = len(self._db.resolve_role_members(eco, role, find_credentials_of_schema))` and pass to the constructor.

3. After permitted-issuer edges are built (around `graph_view.py:550-562`), iterate `eco.issuer_qualification_rules.items()` and instantiate a `QualificationEdge(source_schema=schema_nodes[said], target_role=role_nodes[role_name])` for each. Call `edge.refresh()` after layout.

4. Pass `role_row_nodes=list(role_nodes.keys())` and `role_row_ordering_edges=[(said, role_name) for said, role_name in eco.issuer_qualification_rules.items()]` into `layout_hierarchical(...)` (line 507).

5. Wire `RoleNode.clicked.connect(lambda r=role_name: self._on_role_clicked(r))` and add a `_on_role_clicked(self, role_name: str)` method that emits a new `role_selected = Signal(str)` (T6 will populate the side panel).

6. Add a top-level signal `add_qualification_rule_requested = Signal(str, str)` (schema_said, role_name) and `remove_qualification_rule_requested = Signal(str, str)`. Wire `QualificationEdge._emitter.remove_requested` → `self.remove_qualification_rule_requested.emit(...)` at the equivalent of `graph_view.py:638`.

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/test_graph_view_roles.py -v`
Expected: PASS.

- [ ] **Step 5: Vision-check**

Read `tests/_screenshots/graph_view_one_role_one_qualification_edge.png`. Confirm: ProducerLicense schema at the top, "state-doi" hex node in a row between schemas and the issuer row, dashed teal "if" edge connecting them. No layout collisions.

- [ ] **Step 6: Commit**

```bash
git add src/locksmith/plugins/ecosystem_viewer/graph_view.py tests/test_graph_view_roles.py
git commit -m "feat(ecosystem-viewer): graph view renders roles + qualification edges (Stage 14 T4)"
```

---

## Task 5: Drag-to-create — RoleNode → SchemaNode

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/graph_view.py:812-989` (the inner `_GraphView` drag implementation)

**Spec:** The existing drag flow originates from `IssuerNode` (line 812). Extend it to also fire when the press is on a `RoleNode`. Drop on a `SchemaNode` emits a new top-level signal `add_qualification_rule_requested(schema_said, role_name)` (defined in T4). Snap-target visuals reuse the existing pulse-ring / "eligible/already/ineligible" states. "Already" means `eco.issuer_qualification_rules.get(said) == role_name` for this case.

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_graph_view_roles.py
def test_drag_from_role_to_schema_emits_add_qualification_rule(qapp):
    eco = EcosystemRecord(
        name="Insurance",
        schema_saids=["ECmEfS_Producer"],
        issuer_aids=[],
        role_names=["state-doi"],
        issuer_qualification_rules={},  # rule not yet set
    )
    role = RoleRecord(ecosystem_name="Insurance", name="state-doi",
                      qualification_schema_said="ECmEfS_Producer")
    view = EcosystemGraphView(...)  # adapt
    view.render_ecosystem(eco, _stub_inspections(),
                          get_role=lambda n: role if n == "state-doi" else None,
                          list_roles=lambda eco_name: [role],
                          find_credentials_of_schema=lambda s: [])
    view.show()
    QTest.qWait(200)
    qapp.processEvents()

    # Capture the signal
    captured = []
    view.add_qualification_rule_requested.connect(
        lambda said, rname: captured.append((said, rname))
    )

    # Programmatically simulate the drag
    role_node = next(i for i in view.scene().items() if isinstance(i, RoleNode))
    schema_node = next(
        i for i in view.scene().items()
        if hasattr(i, "said") and getattr(i, "said") == "ECmEfS_Producer"
    )
    view._inner._begin_drag_from(role_node)  # implementer adds this hook
    view._inner._end_drag(schema_node)
    qapp.processEvents()

    assert captured == [("ECmEfS_Producer", "state-doi")]
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL — drag doesn't recognize role nodes as origins.

- [ ] **Step 3: Extend the drag flow**

In `_GraphView.mousePressEvent` (`graph_view.py:812-829`), accept either `IssuerNode` or `RoleNode` as the origin. Generalize the stored origin from `_drag_origin_aid: str` to `_drag_origin: tuple[Literal["issuer", "role"], str]`.

In `_end_drag` (`graph_view.py:955-989`), branch on origin kind:
- `("issuer", aid)` → existing path: `owner.add_permitted_issuer_requested.emit(aid, said)`
- `("role", role_name)` → new path: `owner.add_qualification_rule_requested.emit(said, role_name)`

Update `_snap_target_at` / "already" detection: for role origin, "already" means `owner._eco.issuer_qualification_rules.get(said) == role_name`.

Add a small testable helper `_begin_drag_from(node)` so the test can simulate without full mouse event plumbing.

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/test_graph_view_roles.py -v`
Expected: all 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/ecosystem_viewer/graph_view.py tests/test_graph_view_roles.py
git commit -m "feat(ecosystem-viewer): drag-to-create qualification rules (Stage 14 T5)"
```

---

## Task 6: Side panel — `show_role`

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/side_panel.py` (add `show_role`)
- Modify: `src/locksmith/plugins/ecosystem_viewer/graph_view.py` (wire `role_selected → _populate_panel_for_role → side_panel.show_role`)

**Spec:** A new mode for the side panel. Header: "Role: state-doi". Body sections:
- **Description** (if `role.description`)
- **Qualification credential**: `qualification_schema_title` (clickable, emits `schema_link_clicked`)
- **Issuer role** (if chained): `issuer_role_label` (clickable, emits new `role_link_clicked`); else "Trust roots:" with the list of `root_issuer_aids` (each clickable → `issuer_link_clicked`)
- **Resolved members** (n): scrollable list of AIDs. Empty-state copy: "No qualifying credentials found in this wallet."

- [ ] **Step 1: Write the failing test**

```python
# tests/test_side_panel_role.py
from __future__ import annotations
from pathlib import Path
import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest

from locksmith.plugins.ecosystem_viewer.db import RoleRecord
from locksmith.plugins.ecosystem_viewer.side_panel import EcosystemSidePanel  # actual class name


SHOTS_DIR = Path(__file__).parent / "_screenshots"


def _grab(widget, name):
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = SHOTS_DIR / f"{name}.png"
    pixmap = widget.grab()
    assert pixmap.save(str(path))
    return path


def test_side_panel_show_role_root_with_two_members(qapp):
    panel = EcosystemSidePanel()
    panel.resize(360, 480)
    role = RoleRecord(
        ecosystem_name="Insurance",
        name="state-doi",
        description="State departments of insurance.",
        qualification_schema_said="ECmEfS_Producer",
        root_issuer_aids=["EBOG_DOI_CA", "EBOG_DOI_NY"],
    )
    panel.show_role(
        role=role,
        members=["EAID_1", "EAID_2"],
        qualification_schema_title="ProducerLicense",
        issuer_role_label=None,
    )
    panel.show()
    QTest.qWait(200)
    qapp.processEvents()

    shot = _grab(panel, "side_panel_role_state_doi")
    assert shot.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL — `show_role` doesn't exist.

- [ ] **Step 3: Implement `show_role`**

Mirror the structure of `show_issuer` (`side_panel.py:330-389`). Reuse the helper widgets used by `show_issuer` for the labelled rows. Emit signals already on the panel where possible; add `role_link_clicked = Signal(str)` if there's no equivalent.

- [ ] **Step 4: Wire from graph view**

In `EcosystemGraphView`, replace the placeholder `_on_role_clicked` from T4 with a real `_populate_panel_for_role(role_name)` that:
1. Fetches the `RoleRecord` via the `get_role` callable already passed to `render_ecosystem`.
2. Resolves members via `db.resolve_role_members(eco, role, find_credentials_of_schema)`.
3. Looks up `qualification_schema_title` from the same `schema_titles` dict already used by `_populate_panel_for_schema` (`graph_view.py:645`).
4. Calls `panel.show_role(...)`.

- [ ] **Step 5: Run tests**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/test_side_panel_role.py tests/test_graph_view_roles.py -v`
Expected: all PASS.

- [ ] **Step 6: Vision-check**

Read `tests/_screenshots/side_panel_role_state_doi.png`. Confirm: header "Role: state-doi", description visible, "Qualification credential: ProducerLicense" clickable-styled, two trust-root AIDs listed, two resolved members listed. No clipping.

- [ ] **Step 7: Commit**

```bash
git add src/locksmith/plugins/ecosystem_viewer/side_panel.py src/locksmith/plugins/ecosystem_viewer/graph_view.py tests/test_side_panel_role.py
git commit -m "feat(ecosystem-viewer): side panel show_role + click wiring (Stage 14 T6)"
```

---

## Task 7: Plugin wiring — persist add/remove of qualification rules from the graph

**Files:**
- Modify: `src/locksmith/plugins/ecosystem_viewer/plugin.py` (add handlers, wire signals)

**Spec:** The List-tab handlers from Stage 13 already exist (`_set_qualification_rule`, `_remove_qualification_rule`). The graph emits the same logical events under different signal names. Wire them to the same underlying handlers (or thin shims that call them).

- [ ] **Step 1: Locate the graph-view-construction site in plugin.py**

Find where `EcosystemGraphView` is instantiated (likely in the `EcosystemDetailPage` or directly in `plugin.py`). Look for existing wiring of `add_permitted_issuer_requested` / `remove_permitted_issuer_requested` and add parallel connections.

- [ ] **Step 2: Wire the new signals**

```python
# Where EcosystemGraphView is constructed and signals connected:
graph_view.add_qualification_rule_requested.connect(
    lambda said, role_name: self._set_qualification_rule(eco_name, said, role_name)
)
graph_view.remove_qualification_rule_requested.connect(
    lambda said, role_name: self._remove_qualification_rule(eco_name, said)
)
```

(`_set_qualification_rule` and `_remove_qualification_rule` already exist from Stage 13 T3 — verify their signatures match what we're passing.)

- [ ] **Step 3: Pass role-aware deps to render_ecosystem**

Update the call site of `graph_view.render_ecosystem(...)` to pass `get_role=self._db.get_role`, `list_roles=lambda name: self._db.list_roles(name)`, `find_credentials_of_schema=vault_credential_finder(self._vault)`.

- [ ] **Step 4: Manual smoke**

Launch the wallet (`python -m locksmith.main`), open an ecosystem with at least one role, drag from the role hex to a schema, verify a `QualificationEdge` appears AND that re-opening the ecosystem persists the rule. Right-click a qualification edge → "Remove qualification rule" → verify it disappears and the underlying record updates.

- [ ] **Step 5: Run the full test suite**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/ -v`
Expected: all PASS — no regressions.

- [ ] **Step 6: Commit**

```bash
git add src/locksmith/plugins/ecosystem_viewer/plugin.py
git commit -m "feat(ecosystem-viewer): wire graph qualification add/remove to plugin (Stage 14 T7)"
```

---

## Self-Review Checklist (controller-side)

Before declaring the stage done:

- [ ] All 7 tasks committed as separate commits with `(Stage 14 TN)` suffix
- [ ] `pytest tests/ -v` is green (no regressions in Stages 12/13 test files)
- [ ] Visual smoke screenshots reviewed (T1, T2, T4, T6) — at least one screenshot per new graphics item, all rendering correctly
- [ ] Wallet launches and the role flow works end-to-end (manual smoke from T7 step 4)
- [ ] No new TODO comments left in code; no `pass`-only methods
