# Designer Plugin — V1 Fidelity Phase 3b (Commands + Exports content) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the Commands editor and the Exports (Issued credentials) editor to v1 mock parity. Commands gains a payload-schema table + targets section + Auth/State/Temporal preconditions with "+ Pick rule" affordances. Exports gains a tab strip (Envelope/Schema/Lifecycle/Rules/Value flow), a colored TEL state-machine, and a transitions list. Both editors gain per-item rail subtitles. **Still no inline editing** — chip × and "+ Pick rule" affordances are visually present but display-only; clicking them is a no-op in Phase 1–3. Inline editing lands in Phase 2.

**Architecture:** Add three small new widgets (`EditorTabBar`, `RuleChipStrip`, `PayloadSchemaTable`). Enhance the existing `StateMachineDiagram` with TEL-colored node fills + chip-style transition labels. Rewrite the right-pane construction in `commands.py` and `exports.py` to use the v1 mock section ordering, leveraging `make_section()` for the flat-theme look from Phase 1.

**Tech Stack:** PySide6, pytest with `QT_QPA_PLATFORM=offscreen`, existing `TemplateModel`, `CrossRefIndex`, `make_section()`, `StateMachineDiagram` (enhanced), all the shared widgets from Phase 1 + 3a.

---

## File Structure

**Created in this plan:**

```
src/locksmith/plugins/designer/widgets/
├── editor_tab_bar.py             # tab strip (used in Exports right pane)
├── rule_chip_strip.py            # existing rule chips + "+ Pick rule" button (display-only)
└── payload_schema_table.py       # JSON-Schema → Field/Type/Constraint table

tests/plugins/designer/
├── test_editor_tab_bar_visual.py
├── test_rule_chip_strip_visual.py
├── test_payload_schema_table_visual.py
├── test_state_machine_diagram_v2.py
├── test_commands_editor_v1_visual.py
└── test_exports_editor_v1_visual.py
```

**Modified in this plan:**

```
src/locksmith/plugins/designer/widgets/
└── state_machine_diagram.py     # node fills tinted by terminal TEL primitive; chip-style transition labels

src/locksmith/plugins/designer/editors/
├── commands.py                   # rail subtitles; right-pane restructure
└── exports.py                    # rail subtitle+SAID; tab strip; lifecycle tab content
```

**Out of scope (Phase 2 / later):** clickable chip × removal, clickable "+ Pick rule" popup with model write-back, clickable "+ Add field" wizard, "+ Add state" / "+ Add transition" affordances, the Value-flow tab content (just a placeholder pane).

---

## Task 1: EditorTabBar widget

**Files:**
- Create: `src/locksmith/plugins/designer/widgets/editor_tab_bar.py`
- Test: `tests/plugins/designer/test_editor_tab_bar_visual.py`

A flat tab strip with N tabs. Clicking a tab emits `tab_changed(name)`. The active tab gets a teal underline.

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/designer/test_editor_tab_bar_visual.py
from locksmith.plugins.designer.widgets.editor_tab_bar import EditorTabBar


def test_renders_supplied_tabs(qapp):
    bar = EditorTabBar(["Envelope", "Schema", "Lifecycle"])
    assert bar.tab_names() == ["Envelope", "Schema", "Lifecycle"]


def test_active_tab_defaults_to_first(qapp):
    bar = EditorTabBar(["A", "B", "C"])
    assert bar.active_tab() == "A"


def test_set_active_changes_state(qapp):
    bar = EditorTabBar(["A", "B", "C"])
    bar.set_active("B")
    assert bar.active_tab() == "B"


def test_clicking_tab_emits_changed_signal(qapp):
    bar = EditorTabBar(["A", "B"])
    received: list[str] = []
    bar.tab_changed.connect(lambda name: received.append(name))
    bar._buttons["B"].click()
    assert received == ["B"]
    assert bar.active_tab() == "B"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_editor_tab_bar_visual.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement EditorTabBar**

```python
# src/locksmith/plugins/designer/widgets/editor_tab_bar.py
# -*- encoding: utf-8 -*-
"""EditorTabBar: flat tab strip used inside an editor's right pane.

Phase 1 / 3a used a single right-pane container per editor. Some editors
(Exports) want to split their content into multiple tabs (Envelope /
Schema / Lifecycle / Rules / Value flow). This is the tab strip; the
host swaps the pane content based on `tab_changed(name)`.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton


class EditorTabBar(QFrame):
    tab_changed = Signal(str)

    def __init__(self, tabs: list[str], parent=None):
        super().__init__(parent=parent)
        self._tabs = list(tabs)
        self._active: str = tabs[0] if tabs else ""
        self._buttons: dict[str, QPushButton] = {}
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 8)
        lay.setSpacing(0)
        for name in self._tabs:
            btn = QPushButton(name)
            btn.setFlat(True)
            btn.clicked.connect(lambda _checked=False, n=name: self.set_active(n))
            self._buttons[name] = btn
            lay.addWidget(btn)
        lay.addStretch(1)
        self._restyle()

    def tab_names(self) -> list[str]:
        return list(self._tabs)

    def active_tab(self) -> str:
        return self._active

    def set_active(self, name: str) -> None:
        if name not in self._buttons:
            return
        if name == self._active:
            return
        self._active = name
        self._restyle()
        self.tab_changed.emit(name)

    def _restyle(self) -> None:
        for name, btn in self._buttons.items():
            if name == self._active:
                btn.setStyleSheet(
                    "QPushButton{color:#0ABFB0;font-weight:600;font-size:12px;"
                    "border:0;border-bottom:2px solid #0ABFB0;"
                    "padding:6px 14px;background:transparent;}"
                )
            else:
                btn.setStyleSheet(
                    "QPushButton{color:#666;font-size:12px;border:0;"
                    "border-bottom:2px solid transparent;"
                    "padding:6px 14px;background:transparent;}"
                    "QPushButton:hover{color:#1A1C20;}"
                )
```

- [ ] **Step 4: Run tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_editor_tab_bar_visual.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/widgets/editor_tab_bar.py \
        tests/plugins/designer/test_editor_tab_bar_visual.py
git commit -m "feat(designer): EditorTabBar widget for tabbed right panes"
```

---

## Task 2: RuleChipStrip widget

**Files:**
- Create: `src/locksmith/plugins/designer/widgets/rule_chip_strip.py`
- Test: `tests/plugins/designer/test_rule_chip_strip_visual.py`

Renders a horizontal strip of rule-reference chips (`applicant_provided_all_required_fields ×`) followed by a "+ Pick rule" button. **Display-only in Phase 3b** — the × buttons and "+ Pick rule" don't modify anything yet. Phase 2 wires the click handlers.

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/designer/test_rule_chip_strip_visual.py
from locksmith.plugins.designer.widgets.rule_chip_strip import RuleChipStrip


def test_renders_chips_for_each_rule_ref(qapp):
    strip = RuleChipStrip(rule_refs=["solvency_minimum", "fit_and_proper"])
    assert strip.chip_texts() == ["solvency_minimum", "fit_and_proper"]


def test_pick_button_present_with_correct_label(qapp):
    strip = RuleChipStrip(rule_refs=[])
    assert strip.pick_button.text() == "+ Pick rule"


def test_empty_state_shows_only_pick_button(qapp):
    strip = RuleChipStrip(rule_refs=[])
    assert strip.chip_texts() == []
    assert strip.pick_button is not None


def test_chip_has_remove_x(qapp):
    strip = RuleChipStrip(rule_refs=["a_rule"])
    # The chip text contains "× a_rule" or "a_rule ×" — verify the ×
    # appears as part of the chip's visible content.
    chip = strip._chips[0]
    assert "×" in chip.text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_rule_chip_strip_visual.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement RuleChipStrip**

```python
# src/locksmith/plugins/designer/widgets/rule_chip_strip.py
# -*- encoding: utf-8 -*-
"""RuleChipStrip: chips for a list of rule_refs + a '+ Pick rule' affordance.

Phase 3b ships this display-only — the × and Pick-rule buttons are visible
but clicking them is a no-op. Phase 2 will wire the click handlers to
modify the underlying model.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton,
)


class RuleChipStrip(QFrame):
    pick_clicked = Signal()
    chip_removed = Signal(str)  # rule_ref

    def __init__(self, rule_refs: list[str], parent=None):
        super().__init__(parent=parent)
        self._chips: list[QLabel] = []
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        for ref in rule_refs:
            chip = QLabel(f"{ref} ×")
            chip.setStyleSheet(
                "background:#e8f4f4;color:#0a8a82;border-radius:9px;"
                "padding:2px 9px;font-size:11px;font-weight:600;"
            )
            self._chips.append(chip)
            lay.addWidget(chip)
        self.pick_button = QPushButton("+ Pick rule")
        self.pick_button.setFlat(True)
        self.pick_button.setStyleSheet(
            "QPushButton{color:#0ABFB0;background:transparent;border:0;"
            "padding:2px 9px;font-size:11px;font-weight:600;}"
            "QPushButton:hover{color:#1A1C20;}"
        )
        self.pick_button.clicked.connect(self.pick_clicked.emit)
        lay.addWidget(self.pick_button)
        lay.addStretch(1)

    def chip_texts(self) -> list[str]:
        # Strip the trailing " ×" from each chip label.
        return [c.text().rsplit(" ×", 1)[0] for c in self._chips]
```

- [ ] **Step 4: Run tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_rule_chip_strip_visual.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/widgets/rule_chip_strip.py \
        tests/plugins/designer/test_rule_chip_strip_visual.py
git commit -m "feat(designer): RuleChipStrip widget for rule_refs + Pick affordance"
```

---

## Task 3: PayloadSchemaTable widget

**Files:**
- Create: `src/locksmith/plugins/designer/widgets/payload_schema_table.py`
- Test: `tests/plugins/designer/test_payload_schema_table_visual.py`

Renders a JSON-Schema `payload_schema` object as a 3-column table (Field / Type / Constraint). Used in the Commands editor. Display-only.

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/designer/test_payload_schema_table_visual.py
from locksmith.plugins.designer.widgets.payload_schema_table import (
    PayloadSchemaTable,
)


def test_renders_one_row_per_property(qapp):
    schema = {
        "type": "object",
        "required": ["a"],
        "properties": {
            "a": {"type": "string"},
            "b": {"type": "integer"},
        },
    }
    table = PayloadSchemaTable(schema)
    rows = table.field_rows()
    assert len(rows) == 2
    assert rows[0]["field"] == "a"
    assert rows[1]["field"] == "b"


def test_required_field_is_marked(qapp):
    schema = {
        "type": "object",
        "required": ["a"],
        "properties": {"a": {"type": "string"}, "b": {"type": "integer"}},
    }
    table = PayloadSchemaTable(schema)
    rows = table.field_rows()
    a = next(r for r in rows if r["field"] == "a")
    b = next(r for r in rows if r["field"] == "b")
    assert a["required"] is True
    assert b["required"] is False


def test_pattern_constraint_rendered(qapp):
    schema = {
        "type": "object",
        "properties": {"license_number": {"type": "string", "pattern": "^[A-Z0-9-]+$"}},
    }
    table = PayloadSchemaTable(schema)
    rows = table.field_rows()
    assert "^[A-Z0-9-]+$" in rows[0]["constraint"]


def test_enum_constraint_rendered(qapp):
    schema = {
        "type": "object",
        "properties": {
            "lines": {"type": "array",
                       "items": {"type": "string",
                                 "enum": ["property", "casualty", "life", "health"]}}
        },
    }
    table = PayloadSchemaTable(schema)
    rows = table.field_rows()
    # The enum should show as "enum: property, casualty, …" or similar.
    assert "enum" in rows[0]["constraint"]
    assert "property" in rows[0]["constraint"]


def test_empty_schema_renders_no_rows(qapp):
    table = PayloadSchemaTable({})
    assert table.field_rows() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_payload_schema_table_visual.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement PayloadSchemaTable**

```python
# src/locksmith/plugins/designer/widgets/payload_schema_table.py
# -*- encoding: utf-8 -*-
"""PayloadSchemaTable: render a JSON-Schema object as Field/Type/Constraint rows.

Used by the Commands editor right pane. Display-only — the "+ Add field"
button visible at the bottom is wired in Phase 2.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)


class PayloadSchemaTable(QFrame):
    def __init__(self, schema: dict[str, Any], parent=None):
        super().__init__(parent=parent)
        self._rows: list[dict[str, Any]] = []
        properties = schema.get("properties", {}) or {}
        required_list = schema.get("required", []) or []
        mono = QFont("Menlo")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(10)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header row.
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 4)
        for label, weight in (("FIELD", 4), ("TYPE", 2), ("CONSTRAINT", 6)):
            lbl = QLabel(label)
            lbl.setStyleSheet(
                "font-size:10px;color:#888;font-weight:600;letter-spacing:0.5px;"
            )
            header.addWidget(lbl, weight)
        outer.addLayout(header)

        for name, spec in properties.items():
            field_type = spec.get("type", "")
            constraint = _summarize_constraint(spec)
            is_required = name in required_list
            row_data = {
                "field": name,
                "type": field_type,
                "constraint": constraint,
                "required": is_required,
            }
            self._rows.append(row_data)
            row = QHBoxLayout()
            row.setContentsMargins(0, 2, 0, 2)
            field_lbl = QLabel(name)
            field_lbl.setFont(mono)
            field_lbl.setStyleSheet("color:#1A1C20;")
            row.addWidget(field_lbl, 4)
            type_lbl = QLabel(field_type + ("[]" if field_type == "array" else ""))
            type_lbl.setStyleSheet("color:#666;font-size:11px;")
            row.addWidget(type_lbl, 2)
            cons_lbl = QLabel(constraint)
            cons_lbl.setStyleSheet("color:#666;font-size:11px;")
            cons_lbl.setWordWrap(True)
            row.addWidget(cons_lbl, 6)
            outer.addLayout(row)
            if is_required:
                # Trailing "req" pill at row end.
                req_lbl = QLabel("req")
                req_lbl.setStyleSheet(
                    "color:#0ABFB0;font-size:9px;font-weight:600;"
                    "background:transparent;"
                )
                row.addWidget(req_lbl)

        add_btn = QPushButton("+ Add field")
        add_btn.setFlat(True)
        add_btn.setStyleSheet(
            "QPushButton{color:#0ABFB0;background:transparent;border:0;"
            "padding:6px 0;font-size:11px;font-weight:600;}"
            "QPushButton:hover{color:#1A1C20;}"
        )
        outer.addWidget(add_btn)

    def field_rows(self) -> list[dict[str, Any]]:
        return list(self._rows)


def _summarize_constraint(spec: dict[str, Any]) -> str:
    bits: list[str] = []
    if "pattern" in spec:
        bits.append(spec["pattern"])
    if "format" in spec:
        bits.append(f"format: {spec['format']}")
    if "enum" in spec:
        bits.append("enum: " + ", ".join(spec["enum"][:4])
                    + (", …" if len(spec["enum"]) > 4 else ""))
    if spec.get("type") == "array":
        items = spec.get("items", {})
        if isinstance(items, dict) and "enum" in items:
            bits.append("enum: " + ", ".join(items["enum"][:4])
                        + (", …" if len(items["enum"]) > 4 else ""))
    return " · ".join(bits)
```

- [ ] **Step 4: Run tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_payload_schema_table_visual.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/widgets/payload_schema_table.py \
        tests/plugins/designer/test_payload_schema_table_visual.py
git commit -m "feat(designer): PayloadSchemaTable for JSON-Schema → Field/Type/Constraint"
```

---

## Task 4: StateMachineDiagram — TEL-colored node fills + chip-style transition labels

**Files:**
- Modify: `src/locksmith/plugins/designer/widgets/state_machine_diagram.py`
- Test: `tests/plugins/designer/test_state_machine_diagram_v2.py`

The current widget renders white-filled state nodes with colored arrows. The v1 Exports mock shows nodes tinted by the TEL primitive that produced them (pending=orange/issue, active=teal/update-after-update, suspended=yellow, revoked=pink/revoke), and transition labels as colored pill chips on each edge ("grant · issue", "suspend · update", "revoke · revoke"). This task adds:

1. A node-fill rule: each state is tinted by the **TEL primitive of the transition that produced it** (the `to_state`'s color is the transition's color). Initial state gets a special "pending" orange.
2. Transition labels rendered with a background-pill rect, not bare text.

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/designer/test_state_machine_diagram_v2.py
from locksmith.plugins.designer.widgets.state_machine_diagram import (
    StateMachineDiagram, StateTransition,
)


def test_renders_three_transitions(qapp):
    diag = StateMachineDiagram()
    diag.render([
        StateTransition(from_state="pending", to_state="active",
                        tel_primitive="issue"),
        StateTransition(from_state="active", to_state="suspended",
                        tel_primitive="update"),
        StateTransition(from_state="active", to_state="revoked",
                        tel_primitive="revoke"),
    ])
    assert diag.state_count == 4  # pending, active, suspended, revoked


def test_node_colors_track_arriving_tel_primitive(qapp):
    diag = StateMachineDiagram()
    diag.render([
        StateTransition(from_state="pending", to_state="active",
                        tel_primitive="issue"),
        StateTransition(from_state="active", to_state="revoked",
                        tel_primitive="revoke"),
    ])
    fills = diag.node_fill_map()
    # `pending` is the initial state — orange (issue).
    # `active` is the destination of an "issue" transition — orange.
    # `revoked` is the destination of a "revoke" transition — pink.
    assert fills["pending"] == "#D97757"
    assert fills["revoked"] == "#E94B7B"


def test_transition_labels_are_chip_styled(qapp):
    diag = StateMachineDiagram()
    diag.render([
        StateTransition(from_state="pending", to_state="active",
                        tel_primitive="issue"),
    ])
    labels = diag.transition_label_specs()
    assert len(labels) == 1
    spec = labels[0]
    assert spec["text"] == "issue"
    assert spec["color"] == "#D97757"
    assert spec["chip"] is True


def test_from_state_list_expanded(qapp):
    # Lifecycle transitions can fan-in: from=[active, suspended] → revoked.
    diag = StateMachineDiagram()
    diag.render([
        StateTransition(from_state=["active", "suspended"], to_state="revoked",
                        tel_primitive="revoke"),
    ])
    assert diag.state_count == 3  # active, suspended, revoked
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_state_machine_diagram_v2.py -v`
Expected: FAIL — `node_fill_map`, `transition_label_specs` methods don't exist.

- [ ] **Step 3: Enhance StateMachineDiagram**

Replace the `render` method in `src/locksmith/plugins/designer/widgets/state_machine_diagram.py` to track node fill assignments and chip-style label data, and expose two new public methods:

```python
    def render(self, transitions: list[StateTransition]) -> None:
        self._scene.clear()
        self._node_fills: dict[str, str] = {}
        self._label_specs: list[dict] = []
        expanded = self._expand(transitions)
        seen: list[str] = []
        for src, dst, _ in expanded:
            for s in (src, dst):
                if s and s not in seen:
                    seen.append(s)
        self._state_count = len(seen)

        # First, decide node fills. The first-seen state with no incoming
        # transition is the "initial" — color it as the issue color so the
        # diagram has visual anchor. Other states get the color of their
        # arriving transition.
        has_incoming = {s: False for s in seen}
        for _src, dst, _prim in expanded:
            has_incoming[dst] = True
        for src, dst, prim in expanded:
            color = _TRANSITION_COLOR.get(prim, "#666")
            self._node_fills.setdefault(dst, color)
        for s in seen:
            if s not in self._node_fills:
                # Initial state — use issue color as the anchor.
                self._node_fills[s] = _TRANSITION_COLOR["issue"]

        positions: dict[str, QPointF] = {}
        for i, s in enumerate(seen):
            x = 20 + i * (self.NODE_W + self.H_GAP)
            y = self.BASE_Y
            positions[s] = QPointF(x, y)
            fill_color = self._node_fills[s]
            # Render with a tinted fill — 18% alpha-ish via a light variant.
            tinted = _tint(fill_color, 0.20)
            self._scene.addRect(
                QRectF(x, y, self.NODE_W, self.NODE_H),
                QPen(QColor(fill_color), 1.5),
                QBrush(QColor(tinted)),
            )
            label_font = QFont()
            label_font.setPointSize(10)
            label_font.setBold(True)
            text = self._scene.addText(s, label_font)
            text.setDefaultTextColor(QColor("#1A1C20"))
            text.setPos(x + 8, y + 10)

        for src, dst, prim in expanded:
            if src not in positions or dst not in positions:
                continue
            start = positions[src]
            end = positions[dst]
            color = QColor(_TRANSITION_COLOR.get(prim, "#666"))
            pen = QPen(color, 2)
            if src == dst:
                self._scene.addEllipse(
                    QRectF(start.x() + self.NODE_W / 2 - 18, start.y() - 28, 36, 28),
                    pen,
                    QBrush(Qt.NoBrush),
                )
                continue
            x1 = start.x() + self.NODE_W
            y1 = start.y() + self.NODE_H / 2
            x2 = end.x()
            y2 = end.y() + self.NODE_H / 2
            self._scene.addLine(x1, y1, x2, y2, pen)
            angle = math.atan2(y2 - y1, x2 - x1)
            ahx = x2 - 10 * math.cos(angle - math.pi / 6)
            ahy = y2 - 10 * math.sin(angle - math.pi / 6)
            ahx2 = x2 - 10 * math.cos(angle + math.pi / 6)
            ahy2 = y2 - 10 * math.sin(angle + math.pi / 6)
            poly = QPolygonF(
                [QPointF(x2, y2), QPointF(ahx, ahy), QPointF(ahx2, ahy2)]
            )
            self._scene.addPolygon(poly, pen, QBrush(color))

            # Chip-style label: small rounded rect behind the text.
            label_text = prim
            chip_w = max(34, len(label_text) * 7 + 12)
            chip_h = 16
            mid_x = (x1 + x2) / 2
            mid_y = (y1 + y2) / 2 - chip_h - 4
            tinted_bg = _tint(_TRANSITION_COLOR.get(prim, "#666"), 0.22)
            self._scene.addRect(
                QRectF(mid_x - chip_w / 2, mid_y, chip_w, chip_h),
                QPen(color, 1),
                QBrush(QColor(tinted_bg)),
            )
            label_font = QFont()
            label_font.setPointSize(8)
            label_font.setBold(True)
            text = self._scene.addText(label_text, label_font)
            text.setDefaultTextColor(color)
            text.setPos(mid_x - len(label_text) * 3.2, mid_y - 2)
            self._label_specs.append({
                "text": label_text,
                "color": _TRANSITION_COLOR.get(prim, "#666"),
                "chip": True,
            })

    def node_fill_map(self) -> dict[str, str]:
        return dict(getattr(self, "_node_fills", {}))

    def transition_label_specs(self) -> list[dict]:
        return list(getattr(self, "_label_specs", []))
```

Add a helper `_tint` at module level:

```python
def _tint(hex_color: str, alpha: float) -> str:
    """Mix a hex color with white at the given alpha — returns hex string."""
    h = hex_color.lstrip("#")
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    r = int(255 - (255 - r) * alpha)
    g = int(255 - (255 - g) * alpha)
    b = int(255 - (255 - b) * alpha)
    return f"#{r:02X}{g:02X}{b:02X}"
```

- [ ] **Step 4: Run tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_state_machine_diagram_v2.py -v`
Expected: 4 PASS.

Also run existing exports tests to ensure no regression:
Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/ -k "exports or state_machine" -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/widgets/state_machine_diagram.py \
        tests/plugins/designer/test_state_machine_diagram_v2.py
git commit -m "feat(designer): TEL state machine — node tints + chip-style labels"
```

---

## Task 5: Commands editor — rail subtitles

**Files:**
- Modify: `src/locksmith/plugins/designer/editors/commands.py`
- Test: `tests/plugins/designer/test_commands_editor_v1_visual.py`

The v1 mock shows each command rail entry with a one-line subtitle like `→ carrier · 2 emissions`. Apply.

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/designer/test_commands_editor_v1_visual.py
import json
from pathlib import Path

import pytest

from locksmith.plugins.designer.crossref import compute_crossrefs
from locksmith.plugins.designer.editors.commands import CommandsEditorPage
from locksmith.plugins.designer.model import TemplateModel


@pytest.fixture
def regulator_model():
    doc = json.loads(
        (Path(__file__).parent / "fixtures"
         / "regulator-grants-carrier-license.json").read_text()
    )
    return TemplateModel(doc=doc)


def test_command_rail_items_have_subtitles(qapp, regulator_model):
    page = CommandsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    rail = page.shell.rail_list
    grant_item = rail.item(0)
    text = grant_item.text()
    # Rail item text now spans two lines: name + subtitle.
    assert "\n" in text
    # The subtitle includes counterparty + emission count.
    subtitle = text.split("\n", 1)[1]
    assert "carrier" in subtitle
    assert "emission" in subtitle
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_commands_editor_v1_visual.py -v`
Expected: FAIL — current rail items have no subtitle.

- [ ] **Step 3: Add subtitle to each command's RailItem**

In `src/locksmith/plugins/designer/editors/commands.py`, find the rail items list comprehension (something like `items = [...]`) and replace it with:

```python
        def _command_subtitle(c: dict) -> str:
            parts: list[str] = []
            cp = c.get("counterparty_role")
            if cp:
                parts.append(f"→ {cp}")
            emissions = c.get("emissions") or []
            n = len(emissions)
            if n:
                parts.append(f"{n} emission{'s' if n != 1 else ''}")
            return " · ".join(parts) if parts else ""

        items = [
            RailItem(
                id=c.get("id", ""),
                label=c.get("name") or c.get("id") or "(unnamed)",
                subtitle=_command_subtitle(c),
                kind_color=color,
                has_errors=False,
            )
            for c in model.doc.get("commands", [])
        ]
```

- [ ] **Step 4: Run tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_commands_editor_v1_visual.py -v`
Expected: 1 PASS.

Run the full designer suite:
Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/editors/commands.py \
        tests/plugins/designer/test_commands_editor_v1_visual.py
git commit -m "feat(designer): command rail items show counterparty + emission count"
```

---

## Task 6: Commands editor — right-pane v1 restructure

**Files:**
- Modify: `src/locksmith/plugins/designer/editors/commands.py`
- Test: `tests/plugins/designer/test_commands_editor_v1_visual.py` (extend)

Replace the right-pane sections to match the v1 mock layout:

1. **Header**: `grant_license` id chip + `/insurance/cmd/grant_license` route + description sentence (in a single header block, not a make_section card).
2. **TARGETS** section (make_section): `Counterparty role:` + chip.
3. **WHAT THE ACTOR SUPPLIES (PAYLOAD)** section: `PayloadSchemaTable(command.payload_schema)`.
4. **PRECONDITIONS** section split into three sub-rows:
   - `Auth — actor must hold credentials matching:` + `RuleChipStrip(auth_preconditions[].rule_ref)`
   - `State — facts that must exist in aggregates:` + `RuleChipStrip(state_preconditions[].rule_ref)` (or "None" message)
   - `Temporal — time bounds:` + `RuleChipStrip(temporal_preconditions[].rule_ref)` (or "None" message)
5. **EMISSIONS** section: existing summary line per emission.
6. **USED BY** section: existing cross-ref chips.

- [ ] **Step 1: Write the failing test**

Append to `tests/plugins/designer/test_commands_editor_v1_visual.py`:

```python
def test_command_right_pane_renders_v1_sections(qapp, regulator_model):
    page = CommandsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    text = page.section_text()
    # Targets section + counterparty chip.
    assert "TARGETS" in text or "Counterparty" in text
    assert "carrier" in text
    # Payload table has the grant_license fields.
    assert "license_number" in text
    assert "jurisdiction" in text
    # Preconditions broken out by Auth/State/Temporal.
    assert "Auth" in text or "AUTH" in text
    assert "applicant_provided_all_required_fields" in text


def test_command_pane_uses_payload_schema_table(qapp, regulator_model):
    from locksmith.plugins.designer.widgets.payload_schema_table import (
        PayloadSchemaTable,
    )
    page = CommandsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    # The pane should contain a PayloadSchemaTable for the selected command.
    table = page._pane.findChild(PayloadSchemaTable)
    assert table is not None
    rows = table.field_rows()
    assert len(rows) == 5  # grant_license has 5 payload fields


def test_command_pane_uses_rule_chip_strip_for_auth_preconditions(
    qapp, regulator_model,
):
    from locksmith.plugins.designer.widgets.rule_chip_strip import (
        RuleChipStrip,
    )
    page = CommandsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    strips = page._pane.findChildren(RuleChipStrip)
    # At least one strip exists (for auth_preconditions), with the
    # applicant_provided_all_required_fields rule_ref.
    assert len(strips) >= 1
    all_chip_texts = []
    for s in strips:
        all_chip_texts.extend(s.chip_texts())
    assert "applicant_provided_all_required_fields" in all_chip_texts
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_commands_editor_v1_visual.py -v`
Expected: 3 FAIL — the right pane doesn't yet contain those sections/widgets.

- [ ] **Step 3: Rewrite the _CommandSectionPane**

In `src/locksmith/plugins/designer/editors/commands.py`, replace the existing `_CommandSectionPane._build` with the v1 layout. The class shape stays the same (`set_entry(entry)`, `text_summary()`, etc.), but the sections it builds change.

Open the file, find the `_CommandSectionPane` class, and replace its `_build` and `set_entry` with:

```python
class _CommandSectionPane(QWidget):
    def __init__(self, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._crossrefs = crossrefs
        self._build()

    def _build(self) -> None:
        from locksmith.plugins.designer.widgets.payload_schema_table import (
            PayloadSchemaTable,
        )
        from locksmith.plugins.designer.widgets.rule_chip_strip import (
            RuleChipStrip,
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        # Header block (id chip, route, description).
        self._header_frame = QFrame()
        h = QVBoxLayout(self._header_frame)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self._name_label = QLabel("")
        self._name_label.setStyleSheet(
            "font-size:16px;font-weight:600;color:#1A1C20;"
        )
        title_row.addWidget(self._name_label)
        self._id_chip = QLabel("")
        self._id_chip.setStyleSheet(
            "color:#666;background:#f6f7f9;font-family:monospace;"
            "border-radius:6px;padding:2px 8px;font-size:10px;"
        )
        title_row.addWidget(self._id_chip)
        title_row.addStretch(1)
        self._route_label = QLabel("")
        self._route_label.setStyleSheet(
            "color:#0ABFB0;font-family:monospace;font-size:11px;"
        )
        title_row.addWidget(self._route_label)
        h.addLayout(title_row)
        self._description_label = QLabel("")
        self._description_label.setStyleSheet("color:#444;font-size:12px;")
        self._description_label.setWordWrap(True)
        h.addWidget(self._description_label)
        lay.addWidget(self._header_frame)

        # TARGETS
        targets = make_section("Targets")
        self._cp_row = QHBoxLayout()
        cp_lbl = QLabel("Counterparty role:")
        cp_lbl.setStyleSheet("color:#444;font-size:12px;")
        self._cp_row.addWidget(cp_lbl)
        self._cp_chip = QLabel("(none)")
        self._cp_chip.setStyleSheet(
            "background:#e8f4f4;color:#0a8a82;border-radius:9px;"
            "padding:2px 9px;font-size:11px;font-weight:600;"
        )
        self._cp_row.addWidget(self._cp_chip)
        self._cp_row.addStretch(1)
        targets.layout().addLayout(self._cp_row)
        lay.addWidget(targets)

        # PAYLOAD
        self._payload_section = make_section("What the actor supplies (payload)")
        self._payload_holder = QFrame()
        ph = QVBoxLayout(self._payload_holder)
        ph.setContentsMargins(0, 0, 0, 0)
        ph.setSpacing(0)
        self._payload_section.layout().addWidget(self._payload_holder)
        lay.addWidget(self._payload_section)

        # PRECONDITIONS — three sub-rows (Auth/State/Temporal).
        self._precond_section = make_section("Preconditions")
        self._auth_strip_holder = QVBoxLayout()
        self._state_strip_holder = QVBoxLayout()
        self._temporal_strip_holder = QVBoxLayout()
        for label, holder in (
            ("Auth — actor must hold credentials matching:", self._auth_strip_holder),
            ("State — facts that must exist in aggregates:", self._state_strip_holder),
            ("Temporal — time bounds:", self._temporal_strip_holder),
        ):
            lbl = QLabel(label)
            lbl.setStyleSheet("color:#666;font-size:11px;")
            self._precond_section.layout().addWidget(lbl)
            self._precond_section.layout().addLayout(holder)
        lay.addWidget(self._precond_section)

        # EMISSIONS
        self._emissions_section = make_section("Emissions")
        self._emissions_holder = QVBoxLayout()
        self._emissions_section.layout().addLayout(self._emissions_holder)
        lay.addWidget(self._emissions_section)

        # USED BY
        self._used_by = make_section("Used by")
        self.chip_strip = CrossRefChipStrip()
        self._used_by.layout().addWidget(self.chip_strip)
        lay.addWidget(self._used_by)
        lay.addStretch(1)

    def set_entry(self, entry: dict[str, Any]) -> None:
        from locksmith.plugins.designer.widgets.payload_schema_table import (
            PayloadSchemaTable,
        )
        from locksmith.plugins.designer.widgets.rule_chip_strip import (
            RuleChipStrip,
        )

        self._name_label.setText(entry.get("name") or entry.get("id") or "(unnamed)")
        self._id_chip.setText(entry.get("id", ""))
        self._route_label.setText(entry.get("route", ""))
        self._description_label.setText(entry.get("description", ""))
        cp = entry.get("counterparty_role")
        if cp:
            self._cp_chip.setText(cp)
            self._cp_chip.setStyleSheet(
                "background:#e8f4f4;color:#0a8a82;border-radius:9px;"
                "padding:2px 9px;font-size:11px;font-weight:600;"
            )
        else:
            self._cp_chip.setText("(none)")
            self._cp_chip.setStyleSheet(
                "color:#aaa;font-style:italic;font-size:11px;background:transparent;"
            )

        # Swap the payload table.
        ph_layout = self._payload_holder.layout()
        while ph_layout.count():
            old = ph_layout.takeAt(0).widget()
            if old is not None:
                old.setParent(None)
                old.deleteLater()
        ph_layout.addWidget(PayloadSchemaTable(entry.get("payload_schema") or {}))

        # Swap the precondition strips.
        for holder, refs_key in (
            (self._auth_strip_holder, "auth_preconditions"),
            (self._state_strip_holder, "state_preconditions"),
            (self._temporal_strip_holder, "temporal_preconditions"),
        ):
            while holder.count():
                old = holder.takeAt(0).widget()
                if old is not None:
                    old.setParent(None)
                    old.deleteLater()
            refs = [r.get("rule_ref", "") for r in (entry.get(refs_key) or [])
                    if r.get("rule_ref")]
            holder.addWidget(RuleChipStrip(refs))

        # Emissions summary.
        while self._emissions_holder.count():
            old = self._emissions_holder.takeAt(0).widget()
            if old is not None:
                old.setParent(None)
                old.deleteLater()
        emissions = entry.get("emissions") or []
        if not emissions:
            none_lbl = QLabel("(none)")
            none_lbl.setStyleSheet("color:#aaa;font-style:italic;font-size:11px;")
            self._emissions_holder.addWidget(none_lbl)
        else:
            for em in emissions:
                summary = _emission_summary(em)
                lbl = QLabel(f"• {summary}")
                lbl.setStyleSheet("color:#444;font-size:11px;")
                self._emissions_holder.addWidget(lbl)

        # Used-by chips.
        self.chip_strip.set_refs(
            self._crossrefs.consumers_of(f"command:{entry.get('id', '')}")
        )

    def text_summary(self) -> str:
        return " ".join([
            self._name_label.text(),
            self._id_chip.text(),
            self._route_label.text(),
            self._description_label.text(),
            self._cp_chip.text(),
        ])


def _emission_summary(em: dict) -> str:
    k = em.get("kind", "")
    if k == "lifecycle_advance":
        return f"lifecycle_advance: {em.get('exported_credential_id','')} → {em.get('to_state','')}"
    if k == "aggregate_event":
        return f"aggregate_event: {em.get('aggregate_id','')} · {em.get('event_type','')}"
    if k == "exchange":
        ex = em.get("exchange", {}) or {}
        return f"exchange: {ex.get('kind','')} · {ex.get('verb', ex.get('pattern',''))}"
    return k or "(unknown)"
```

Replace the old `_CommandSectionPane` block in the file with the above.

Update the `CommandsEditorPage.section_text()` method to include the new section labels (it currently just delegates to `_pane.text_summary()`). If `section_text` already returns `self._pane.text_summary()`, no change needed — the v1 test reads from `text_summary` indirectly.

Add `from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget` if any are missing in the imports.

- [ ] **Step 4: Run tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_commands_editor_v1_visual.py tests/plugins/designer/test_commands_editor_visual.py -v`
Expected: all PASS.

Run the full designer suite:
Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/editors/commands.py \
        tests/plugins/designer/test_commands_editor_v1_visual.py
git commit -m "feat(designer): commands right-pane v1 (header/targets/payload/preconditions/emissions)"
```

---

## Task 7: Exports editor — rail subtitle + SAID

**Files:**
- Modify: `src/locksmith/plugins/designer/editors/exports.py`
- Test: `tests/plugins/designer/test_exports_editor_v1_visual.py`

Each exports rail item gets a subtitle like `→ carrier · 4 states · 5 rules` and (further below per the mock) a SAID prefix. The SAID would crowd the rail item visually, so for now use just the subtitle line via `RailItem.subtitle`; full SAID stays on the right-pane header.

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/designer/test_exports_editor_v1_visual.py
import json
from pathlib import Path

import pytest

from locksmith.plugins.designer.crossref import compute_crossrefs
from locksmith.plugins.designer.editors.exports import ExportsEditorPage
from locksmith.plugins.designer.model import TemplateModel


@pytest.fixture
def regulator_model():
    doc = json.loads(
        (Path(__file__).parent / "fixtures"
         / "regulator-grants-carrier-license.json").read_text()
    )
    return TemplateModel(doc=doc)


def test_export_rail_items_have_subtitles(qapp, regulator_model):
    page = ExportsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    rail = page.shell.rail_list
    item = rail.item(0)
    text = item.text()
    assert "\n" in text
    subtitle = text.split("\n", 1)[1]
    assert "carrier" in subtitle
    assert "4 states" in subtitle
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_exports_editor_v1_visual.py -v`
Expected: FAIL — no subtitle.

- [ ] **Step 3: Compute subtitles in exports.py**

In `src/locksmith/plugins/designer/editors/exports.py`, replace the rail items list comprehension with:

```python
        def _export_subtitle(exp: dict) -> str:
            env = exp.get("envelope") or {}
            lc = exp.get("lifecycle") or {}
            parts: list[str] = []
            if env.get("holder_role"):
                parts.append(f"→ {env['holder_role']}")
            states = lc.get("states") or []
            if states:
                parts.append(f"{len(states)} states")
            # Count rule references threaded through lifecycle.transitions + rule_refs.
            rule_count = len(exp.get("rule_refs") or [])
            for t in (lc.get("transitions") or []):
                if t.get("condition_rule_ref"):
                    rule_count += 1
                for r in (t.get("requires") or []):
                    if r.get("rule_ref"):
                        rule_count += 1
            if rule_count:
                parts.append(f"{rule_count} rules")
            return " · ".join(parts) if parts else ""

        items = [
            RailItem(
                id=exp.get("id", ""),
                label=exp.get("name") or exp.get("id") or "(unnamed)",
                subtitle=_export_subtitle(exp),
                kind_color=color,
                has_errors=False,
            )
            for exp in model.doc.get("credentials", {}).get("exports", [])
        ]
```

- [ ] **Step 4: Run tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_exports_editor_v1_visual.py -v`
Expected: 1 PASS.

Full suite:
Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/editors/exports.py \
        tests/plugins/designer/test_exports_editor_v1_visual.py
git commit -m "feat(designer): exports rail items show holder/state/rule counts"
```

---

## Task 8: Exports editor — tab strip (Envelope / Schema / Lifecycle / Rules / Value flow)

**Files:**
- Modify: `src/locksmith/plugins/designer/editors/exports.py`
- Test: `tests/plugins/designer/test_exports_editor_v1_visual.py` (extend)

Restructure the right pane so it carries a 5-tab strip at top, then a stacked content area below. Each tab's content is a separate `QWidget` swapped in on tab change.

- [ ] **Step 1: Write the failing test**

Append to `tests/plugins/designer/test_exports_editor_v1_visual.py`:

```python
def test_export_pane_has_five_tab_strip(qapp, regulator_model):
    from locksmith.plugins.designer.widgets.editor_tab_bar import EditorTabBar
    page = ExportsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    tab_bar = page._pane.findChild(EditorTabBar)
    assert tab_bar is not None
    assert tab_bar.tab_names() == [
        "Envelope", "Schema", "Lifecycle", "Rules", "Value flow",
    ]


def test_export_pane_lifecycle_tab_is_active_by_default(qapp, regulator_model):
    from locksmith.plugins.designer.widgets.editor_tab_bar import EditorTabBar
    page = ExportsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    tab_bar = page._pane.findChild(EditorTabBar)
    assert tab_bar.active_tab() == "Lifecycle"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_exports_editor_v1_visual.py -v`
Expected: FAIL — no tab bar.

- [ ] **Step 3: Add tab strip + tab content swap to ExportsEditorPage**

In `src/locksmith/plugins/designer/editors/exports.py`, replace the `_ExportSectionPane._build` method to construct: header + EditorTabBar + QStackedWidget. Each tab gets a child widget.

```python
class _ExportSectionPane(QWidget):
    def __init__(self, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._crossrefs = crossrefs
        self._current_entry: dict[str, Any] = {}
        self._build()

    def _build(self) -> None:
        from locksmith.plugins.designer.widgets.editor_tab_bar import (
            EditorTabBar,
        )
        from PySide6.QtWidgets import QStackedWidget

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        # Header.
        self._header_frame = QFrame()
        h = QVBoxLayout(self._header_frame)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self._name_label = QLabel("")
        self._name_label.setStyleSheet(
            "font-size:16px;font-weight:600;color:#1A1C20;"
        )
        title_row.addWidget(self._name_label)
        self._id_chip = QLabel("")
        self._id_chip.setStyleSheet(
            "color:#666;background:#f6f7f9;font-family:monospace;"
            "border-radius:6px;padding:2px 8px;font-size:10px;"
        )
        title_row.addWidget(self._id_chip)
        title_row.addStretch(1)
        said_title = QLabel("Schema SAID:")
        said_title.setStyleSheet("font-size:10px;color:#888;")
        title_row.addWidget(said_title)
        self._said_label = QLabel("")
        self._said_label.setStyleSheet(
            "color:#666;font-family:monospace;font-size:10px;"
            "background:#f6f7f9;border-radius:6px;padding:2px 8px;"
        )
        title_row.addWidget(self._said_label)
        h.addLayout(title_row)
        self._description_label = QLabel("")
        self._description_label.setStyleSheet("color:#444;font-size:12px;")
        self._description_label.setWordWrap(True)
        h.addWidget(self._description_label)
        lay.addWidget(self._header_frame)

        self.tab_bar = EditorTabBar(
            ["Envelope", "Schema", "Lifecycle", "Rules", "Value flow"],
        )
        self.tab_bar.set_active("Lifecycle")
        self.tab_bar.tab_changed.connect(self._on_tab_changed)
        lay.addWidget(self.tab_bar)

        self._stack = QStackedWidget()
        lay.addWidget(self._stack, 1)
        self._tab_widgets: dict[str, QWidget] = {}
        for name in self.tab_bar.tab_names():
            w = self._build_tab(name)
            self._tab_widgets[name] = w
            self._stack.addWidget(w)
        self._stack.setCurrentWidget(self._tab_widgets["Lifecycle"])

        # Used-by stays outside the tabs.
        self._used_by = make_section("Used by")
        self.chip_strip = CrossRefChipStrip()
        self._used_by.layout().addWidget(self.chip_strip)
        lay.addWidget(self._used_by)

    def _build_tab(self, name: str) -> QWidget:
        # Each tab body is built once and refreshed when set_entry runs.
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        # Tab-specific widgets are filled by set_entry. Each tab keeps a
        # _holder QFrame on the widget so set_entry can rebuild content.
        holder = QFrame()
        holder_lay = QVBoxLayout(holder)
        holder_lay.setContentsMargins(0, 0, 0, 0)
        holder_lay.setSpacing(8)
        w.setProperty("holder", holder)
        lay.addWidget(holder)
        lay.addStretch(1)
        return w

    def _on_tab_changed(self, name: str) -> None:
        if name in self._tab_widgets:
            self._stack.setCurrentWidget(self._tab_widgets[name])

    def set_entry(self, entry: dict[str, Any]) -> None:
        self._current_entry = entry
        self._name_label.setText(entry.get("name") or entry.get("id") or "(unnamed)")
        self._id_chip.setText(entry.get("id", ""))
        said = (entry.get("schema") or {}).get("schema_said") or ""
        short = said[:4] + "…" + said[-6:] if len(said) > 12 else said
        self._said_label.setText(short)
        self._description_label.setText(entry.get("description", ""))
        for name, widget in self._tab_widgets.items():
            holder = widget.property("holder")
            holder_lay = holder.layout()
            while holder_lay.count():
                old = holder_lay.takeAt(0).widget()
                if old is not None:
                    old.setParent(None)
                    old.deleteLater()
            self._fill_tab(name, holder, entry)
        self.chip_strip.set_refs(
            self._crossrefs.consumers_of(f"export:{entry.get('id', '')}")
        )

    def _fill_tab(self, name: str, holder: QFrame, entry: dict) -> None:
        # Lifecycle tab is the only one with rich content in this task;
        # the others (Envelope/Schema/Rules/Value flow) get a one-line
        # summary stub for now — fleshed out in Task 9 and later.
        if name == "Lifecycle":
            self._fill_lifecycle_tab(holder, entry)
        else:
            self._fill_stub_tab(name, holder, entry)

    def _fill_lifecycle_tab(self, holder: QFrame, entry: dict) -> None:
        # Stub for Task 8 — full state-machine + transitions list in Task 9.
        lc = entry.get("lifecycle") or {}
        states_str = ", ".join(lc.get("states") or [])
        lbl = QLabel(f"States: {states_str}")
        lbl.setStyleSheet("color:#444;font-size:12px;")
        holder.layout().addWidget(lbl)

    def _fill_stub_tab(self, name: str, holder: QFrame, entry: dict) -> None:
        stub = QLabel(f"({name} content — Phase 3b/3c follow-up)")
        stub.setStyleSheet("color:#aaa;font-style:italic;font-size:11px;")
        holder.layout().addWidget(stub)

    def text_summary(self) -> str:
        return " ".join([
            self._name_label.text(),
            self._id_chip.text(),
            self._said_label.text(),
            self._description_label.text(),
        ])
```

- [ ] **Step 4: Run tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_exports_editor_v1_visual.py -v`
Expected: 2 PASS for the new tab tests.

Full suite:
Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/`
Expected: all PASS (existing exports test may need adapting if it asserted on a now-removed section).

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/editors/exports.py \
        tests/plugins/designer/test_exports_editor_v1_visual.py
git commit -m "feat(designer): exports tab strip (Envelope/Schema/Lifecycle/Rules/Value-flow)"
```

---

## Task 9: Exports editor — Lifecycle tab (state machine + transitions list)

**Files:**
- Modify: `src/locksmith/plugins/designer/editors/exports.py`
- Test: `tests/plugins/designer/test_exports_editor_v1_visual.py` (extend)

Replace the lifecycle tab's stub with the full state-machine diagram + transitions list. Each transition row shows from-state, to-state, the `via_workflow` link (if any), the requires rule chips (RuleChipStrip), and a right-aligned `tel:<primitive>` chip.

- [ ] **Step 1: Write the failing test**

Append to `tests/plugins/designer/test_exports_editor_v1_visual.py`:

```python
def test_lifecycle_tab_renders_state_machine_diagram(qapp, regulator_model):
    from locksmith.plugins.designer.widgets.state_machine_diagram import (
        StateMachineDiagram,
    )
    page = ExportsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    diag = page._pane.findChild(StateMachineDiagram)
    assert diag is not None
    assert diag.state_count == 4  # pending, active, suspended, revoked


def test_lifecycle_tab_renders_transitions_list_with_rule_refs(qapp, regulator_model):
    page = ExportsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    text = page.section_text()
    # The transitions list should mention via_workflow + the
    # financial_solvency_demonstrated rule for the grant transition.
    assert "license_grant_workflow" in text
    assert "financial_solvency_demonstrated" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_exports_editor_v1_visual.py -v -k "lifecycle"`
Expected: 2 FAIL.

- [ ] **Step 3: Implement `_fill_lifecycle_tab`**

Replace `_fill_lifecycle_tab` in `exports.py`:

```python
    def _fill_lifecycle_tab(self, holder: QFrame, entry: dict) -> None:
        from locksmith.plugins.designer.widgets.state_machine_diagram import (
            StateMachineDiagram, StateTransition,
        )
        from locksmith.plugins.designer.widgets.rule_chip_strip import (
            RuleChipStrip,
        )

        lc = entry.get("lifecycle") or {}
        transitions = lc.get("transitions") or []
        initial = lc.get("initial", "")
        n_states = len(lc.get("states") or [])
        n_trans = len(transitions)

        # State-machine card.
        title_row = QHBoxLayout()
        title = QLabel("State machine")
        title.setStyleSheet("font-size:13px;font-weight:600;color:#1A1C20;")
        title_row.addWidget(title)
        sub = QLabel(
            f"{n_states} states · {n_trans} transitions · "
            f"initial state: <b>{initial}</b>"
        )
        sub.setStyleSheet("color:#888;font-size:11px;")
        title_row.addWidget(sub)
        title_row.addStretch(1)
        holder.layout().addLayout(title_row)

        diag = StateMachineDiagram()
        diag.setMinimumHeight(200)
        diag.render([
            StateTransition(
                from_state=t.get("from", ""),
                to_state=t.get("to", ""),
                tel_primitive=t.get("tel_primitive", ""),
            )
            for t in transitions
        ])
        holder.layout().addWidget(diag)

        # TRANSITIONS list section.
        trans_section = make_section("Transitions")
        for t in transitions:
            row = QHBoxLayout()
            row.setSpacing(6)
            from_val = t.get("from", "")
            from_text = ", ".join(from_val) if isinstance(from_val, list) else from_val
            to_val = t.get("to", "")
            chip_from = QLabel(from_text)
            chip_from.setStyleSheet(
                "background:#f0f2f5;color:#444;border-radius:9px;"
                "padding:2px 8px;font-size:11px;"
            )
            arrow = QLabel("→")
            arrow.setStyleSheet("color:#888;font-size:12px;")
            chip_to = QLabel(to_val)
            chip_to.setStyleSheet(
                "background:#f0f2f5;color:#444;border-radius:9px;"
                "padding:2px 8px;font-size:11px;"
            )
            row.addWidget(chip_from)
            row.addWidget(arrow)
            row.addWidget(chip_to)
            via = t.get("via_workflow")
            if via:
                via_lbl = QLabel(f"via workflow {via}")
                via_lbl.setStyleSheet("color:#0ABFB0;font-size:11px;")
                row.addWidget(via_lbl)
            requires = [r.get("rule_ref", "") for r in (t.get("requires") or [])
                        if r.get("rule_ref")]
            if requires:
                row.addWidget(QLabel("· requires"))
                row.addWidget(RuleChipStrip(requires))
            row.addStretch(1)
            prim_chip = QLabel(t.get("tel_primitive", ""))
            prim_chip.setStyleSheet(
                f"color:{_tel_color(t.get('tel_primitive', ''))};"
                "font-size:10px;font-weight:600;background:transparent;"
            )
            row.addWidget(prim_chip)
            trans_section.layout().addLayout(row)
        holder.layout().addWidget(trans_section)


def _tel_color(prim: str) -> str:
    return {"issue": "#D97757", "update": "#0ABFB0",
            "revoke": "#E94B7B"}.get(prim, "#666")
```

- [ ] **Step 4: Run tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_exports_editor_v1_visual.py -v`
Expected: 4 PASS (subtitle + tab bar + state machine + transitions list tests).

Full suite:
Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/editors/exports.py \
        tests/plugins/designer/test_exports_editor_v1_visual.py
git commit -m "feat(designer): exports lifecycle tab — state machine + transitions list"
```

---

## Task 10: Final live verification

**Files:**
- (No code changes)

Drive the wallet via the harness and confirm the visual output for Commands + Exports matches their respective v1 mocks.

- [ ] **Step 1: Restart wallet**

```bash
ps aux | grep "locksmith.main" | grep -v grep | awk '{print $2}' | head -1 | xargs -r kill
sleep 1
LOCKSMITH_DEV_CONTROL=1 LOCKSMITH_DESIGNER_SEED_FIXTURES=1 \
    nohup .venv/bin/python -m locksmith.main > /tmp/locksmith-wallet.log 2>&1 &
sleep 4
```

- [ ] **Step 2: Unlock + navigate to Commands**

```bash
.venv/bin/python tools/devctl.py click '{"target": "Vaults"}'
.venv/bin/python tools/devctl.py click_list_item '{"text": "joe"}'
.venv/bin/python tools/devctl.py click '{"target": "Vaults"}'
.venv/bin/python tools/devctl.py type \
    '{"target": "FloatingLabelLineEdit:0", "text": "noble"}'
.venv/bin/python tools/devctl.py click '{"target": "Open"}'
sleep 2.5
.venv/bin/python tools/devctl.py click '{"target": "Micro App Designer"}'
.venv/bin/python tools/devctl.py click '{"target": "Templates"}'
.venv/bin/python tools/devctl.py click '{"target": "Regulator Grants Carrier License"}'
.venv/bin/python tools/devctl.py click '{"target": "Commands"}'
.venv/bin/python tools/devctl.py screenshot \
    '{"path": "/tmp/locksmith-3b-commands.png"}'
```

Read `/tmp/locksmith-3b-commands.png`. Expected vs `.superpowers/brainstorm/69587-1778622927/content/commands-editor.html`:
- Rail items each show name + subtitle ("→ carrier · N emissions")
- Right pane: name + id chip on left, route on right
- Description sentence below
- TARGETS section with "Counterparty role: carrier" chip
- WHAT THE ACTOR SUPPLIES (PAYLOAD) section with Field/Type/Constraint table — 5 rows for grant_license
- PRECONDITIONS section with three sub-rows (Auth/State/Temporal); Auth shows `applicant_provided_all_required_fields ×` chip + `+ Pick rule`
- EMISSIONS section listing lifecycle_advance
- Used by chips

- [ ] **Step 3: Navigate to Exports**

```bash
.venv/bin/python tools/devctl.py click '{"target": "Templates"}'
.venv/bin/python tools/devctl.py click '{"target": "Regulator Grants Carrier License"}'
.venv/bin/python tools/devctl.py click '{"target": "Issued credentials"}'
.venv/bin/python tools/devctl.py screenshot \
    '{"path": "/tmp/locksmith-3b-exports.png"}'
```

Read the image. Expected vs `exports-editor.html`:
- Rail item shows "Carrier License" + "→ carrier · 4 states · N rules" subtitle
- Right pane header: Carrier License + carrier_license id chip + Schema SAID block
- Description sentence
- **Tab strip** with: Envelope / Schema / **Lifecycle (active)** / Rules / Value flow
- Lifecycle tab: state machine with 4 nodes (pending/active/suspended/revoked), colored fills, chip-style transition labels
- Transitions list below the diagram: pending → active (via workflow license_grant_workflow · requires financial_solvency_demonstrated) · tel:issue (orange) · etc.

- [ ] **Step 4: Try clicking a different tab**

```bash
.venv/bin/python tools/devctl.py click '{"target": "Envelope"}'
sleep 0.4
.venv/bin/python tools/devctl.py screenshot \
    '{"path": "/tmp/locksmith-3b-exports-envelope.png"}'
```

Expected: Envelope tab is now active (teal underline), content area shows the placeholder text. The other tabs swap accordingly.

- [ ] **Step 5: Run the full test suite**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/ -v
```

Expected: all PASS.

- [ ] **Step 6: Milestone commit**

```bash
git commit --allow-empty -m "milestone(designer): Phase 3b (Commands + Exports content) complete"
```

---

## Self-review checklist

1. **Spec coverage — Commands**:
   - Rail subtitles ✓ Task 5.
   - Header with id chip + route + description ✓ Task 6.
   - TARGETS section with counterparty chip ✓ Task 6.
   - Payload schema table (Visual / JSON-Schema toggle deferred to Phase 2) ✓ Task 6 via Task 3.
   - Preconditions broken out Auth/State/Temporal with rule pickers ✓ Task 6 via Task 2.
   - "+ Pick rule" display-only ✓ Task 2.
   - Emissions list summary ✓ Task 6.
   - Used by chips ✓ Task 6 (unchanged from earlier).

2. **Spec coverage — Exports**:
   - Rail subtitle + SAID ✓ Task 7 (SAID lives in right pane header per the implementation; rail is just subtitle to avoid crowding).
   - Header with id + Schema SAID + description ✓ Task 8.
   - Tab strip (Envelope/Schema/Lifecycle/Rules/Value flow) ✓ Task 8 via Task 1.
   - Lifecycle tab — state machine (colored fills + chip labels) ✓ Task 9 via Task 4.
   - Lifecycle tab — transitions list with via_workflow + requires rule chips ✓ Task 9 via Task 2.
   - Used by chips ✓ Task 8.

3. **Out of scope (Phase 2 / 3c / later):**
   - Envelope / Schema / Rules / Value-flow tab content (only stub labels in 3b).
   - Visual ↔ JSON-Schema toggle in Commands payload.
   - Clicking "+ Pick rule" / chip × / "+ Add field" / "+ Add state" / "+ Add transition" — display-only.
   - Inline editing of any field — Phase 2.

4. **Placeholder scan:** no TBD / "implement later" / "similar to Task N". Every code block carries real code; every command is runnable.

5. **Type consistency:**
   - `EditorTabBar(tabs)` / `tab_names()` / `active_tab()` / `set_active(name)` / `tab_changed(str)` signal. Consistent across tests.
   - `RuleChipStrip(rule_refs)` / `chip_texts()` / `pick_button`.
   - `PayloadSchemaTable(schema)` / `field_rows()` — returns list of `{field, type, constraint, required}` dicts.
   - `StateMachineDiagram.render(transitions)` / `state_count` / `node_fill_map()` / `transition_label_specs()`.
   - `_CommandSectionPane.set_entry(entry)` / `text_summary()` unchanged in shape.
   - `_ExportSectionPane.set_entry(entry)` / `text_summary()` unchanged in shape.
