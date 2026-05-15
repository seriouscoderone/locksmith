# Designer Plugin — V1 Fidelity Phase 3c (Workflows + Projections content) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the Workflows editor and the Projections editor to v1 mock parity. Workflows gains a full-width swimlane v2 (arrows, step numbers, branch diamonds, time-bound footnotes, legend) plus a trigger/counterparty header. Projections gains a two-column layout — editor controls left, live-preview pane right — with source-event chips, a UEL fold expression in a dark code block, an output-schema table, an access/row-filter section, and a 6-way view-type chip picker. Both editors gain per-item rail subtitles. **Still no inline editing** — chips, pickers, and "+" affordances are visible but display-only; clicks are wired in Phase 2.

**Architecture:** Add two small new widgets (`ViewTypeChipPicker`, `SourceEventChipStrip`). Enhance the existing `SwimlaneDiagram` (currently 91 lines, single-column step boxes) with actor-tinted boxes by tel-style colors, step numbering, branch diamonds, time-bound footnotes, legend, and arrow routing that follows step.branches and step.next_steps. Rewrite the right-pane construction in `workflows.py` and `projections.py` to use these primitives, with Projections shifting to a two-column QHBoxLayout. Reuse `PayloadSchemaTable` from Phase 3b for the projections output-schema table — same JSON-Schema → Field/Type render shape.

**Tech Stack:** PySide6, pytest with `QT_QPA_PLATFORM=offscreen`, existing `TemplateModel`, `CrossRefIndex`, `make_section()`, `SwimlaneDiagram` (enhanced), `DarkCodeBlock` (from 3a, for the fold expression), `PayloadSchemaTable` (from 3b, reused for projections output_schema), all the shared widgets from earlier phases.

---

## File Structure

**Created in this plan:**

```
src/locksmith/plugins/designer/widgets/
├── view_type_chip_picker.py     # 6 view-type chips, one active highlighted
└── source_event_chip_strip.py   # event-name chips + "+ Pick event" affordance

tests/plugins/designer/
├── test_view_type_chip_picker_visual.py
├── test_source_event_chip_strip_visual.py
├── test_swimlane_diagram_v2.py
├── test_workflows_editor_v1_visual.py
└── test_projections_editor_v1_visual.py
```

**Modified in this plan:**

```
src/locksmith/plugins/designer/widgets/
└── swimlane_diagram.py          # step numbers + branches + time bounds + legend

src/locksmith/plugins/designer/editors/
├── workflows.py                  # rail subtitle; right-pane restructure (trigger card + swimlane v2 + step details)
└── projections.py                # rail subtitle; right-pane two-column restructure (editor + preview pane)
```

**Out of scope (Phase 2 / later):** clickable chip × removal, clickable "+ Pick event" / "+ Pick rule" popup; clickable "+ Add step" wizard; the live UEL evaluator (preview stays in "evaluator pending" mode — v2-deferred); sample-event data editor.

---

## Task 1: ViewTypeChipPicker widget

**Files:**
- Create: `src/locksmith/plugins/designer/widgets/view_type_chip_picker.py`
- Test: `tests/plugins/designer/test_view_type_chip_picker_visual.py`

A row of 6 chips: `table · list · cards · kanban · timeline · summary`. Each is a clickable QPushButton; the active one renders in orange (`#D97757`) with white text, others render flat grey. Emits `view_type_changed(name)` when a different chip is clicked.

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/designer/test_view_type_chip_picker_visual.py
from locksmith.plugins.designer.widgets.view_type_chip_picker import (
    ViewTypeChipPicker,
)


_ALL = ["table", "list", "cards", "kanban", "timeline", "summary"]


def test_renders_six_view_types(qapp):
    picker = ViewTypeChipPicker(active="table")
    assert picker.view_types() == _ALL


def test_active_chip_defaults(qapp):
    picker = ViewTypeChipPicker(active="cards")
    assert picker.active_view_type() == "cards"


def test_set_active_changes_state(qapp):
    picker = ViewTypeChipPicker(active="table")
    picker.set_active("kanban")
    assert picker.active_view_type() == "kanban"


def test_clicking_chip_emits_signal(qapp):
    picker = ViewTypeChipPicker(active="table")
    received: list[str] = []
    picker.view_type_changed.connect(lambda name: received.append(name))
    picker._buttons["list"].click()
    assert received == ["list"]
    assert picker.active_view_type() == "list"


def test_active_chip_uses_orange_color(qapp):
    picker = ViewTypeChipPicker(active="table")
    style = picker._buttons["table"].styleSheet()
    assert "#D97757" in style
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_view_type_chip_picker_visual.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement ViewTypeChipPicker**

```python
# src/locksmith/plugins/designer/widgets/view_type_chip_picker.py
# -*- encoding: utf-8 -*-
"""ViewTypeChipPicker: 6 view-type chips, one active.

Used in the Projections editor to choose how the projection renders
(table / list / cards / kanban / timeline / summary). The active chip
is highlighted in orange; others are flat grey. Display-only until
Phase 2 wires the change to the model.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton


_VIEW_TYPES = ["table", "list", "cards", "kanban", "timeline", "summary"]
_VIEW_TYPE_GLYPHS: dict[str, str] = {
    "table":    "▤",
    "list":     "≡",
    "cards":    "▢",
    "kanban":   "▦",
    "timeline": "─",
    "summary":  "Σ",
}


class ViewTypeChipPicker(QFrame):
    view_type_changed = Signal(str)

    def __init__(self, active: str = "table", parent=None):
        super().__init__(parent=parent)
        self._active = active if active in _VIEW_TYPES else "table"
        self._buttons: dict[str, QPushButton] = {}
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        for name in _VIEW_TYPES:
            glyph = _VIEW_TYPE_GLYPHS.get(name, "")
            label = f"{glyph} {name}" if glyph else name
            btn = QPushButton(label)
            btn.setFlat(True)
            btn.clicked.connect(lambda _checked=False, n=name: self.set_active(n))
            self._buttons[name] = btn
            lay.addWidget(btn)
        lay.addStretch(1)
        self._restyle()

    def view_types(self) -> list[str]:
        return list(_VIEW_TYPES)

    def active_view_type(self) -> str:
        return self._active

    def set_active(self, name: str) -> None:
        if name not in self._buttons:
            return
        if name == self._active:
            return
        self._active = name
        self._restyle()
        self.view_type_changed.emit(name)

    def _restyle(self) -> None:
        for name, btn in self._buttons.items():
            if name == self._active:
                btn.setStyleSheet(
                    "QPushButton{color:#fff;background:#D97757;"
                    "border:0;border-radius:6px;padding:4px 10px;"
                    "font-size:11px;font-weight:600;}"
                )
            else:
                btn.setStyleSheet(
                    "QPushButton{color:#666;background:#f0f2f5;"
                    "border:0;border-radius:6px;padding:4px 10px;"
                    "font-size:11px;}"
                    "QPushButton:hover{color:#1A1C20;background:#e8eaef;}"
                )
```

- [ ] **Step 4: Run tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_view_type_chip_picker_visual.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/widgets/view_type_chip_picker.py \
        tests/plugins/designer/test_view_type_chip_picker_visual.py
git commit -m "feat(designer): ViewTypeChipPicker widget (table/list/cards/kanban/timeline/summary)"
```

---

## Task 2: SourceEventChipStrip widget

**Files:**
- Create: `src/locksmith/plugins/designer/widgets/source_event_chip_strip.py`
- Test: `tests/plugins/designer/test_source_event_chip_strip_visual.py`

A horizontal strip of event-name chips (each with × delete affordance) followed by a "+ Pick event" button. Same shape as `RuleChipStrip` from Phase 3b but the event chips use a different color (purple, matching aggregate_event semantics in the FacetCard rule-type colors).

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/designer/test_source_event_chip_strip_visual.py
from locksmith.plugins.designer.widgets.source_event_chip_strip import (
    SourceEventChipStrip,
)


def test_renders_chips_for_each_event(qapp):
    strip = SourceEventChipStrip(events=["license.issued", "license.revoked"])
    assert strip.chip_texts() == ["license.issued", "license.revoked"]


def test_pick_button_present_with_correct_label(qapp):
    strip = SourceEventChipStrip(events=[])
    assert strip.pick_button.text() == "+ Pick event"


def test_chip_has_remove_x(qapp):
    strip = SourceEventChipStrip(events=["license.issued"])
    chip = strip._chips[0]
    assert "×" in chip.text()


def test_chip_uses_purple_for_aggregate_event_semantics(qapp):
    strip = SourceEventChipStrip(events=["application_recorded"])
    chip = strip._chips[0]
    style = chip.styleSheet()
    assert "#A36AE6" in style or "#a36ae6" in style.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_source_event_chip_strip_visual.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement SourceEventChipStrip**

```python
# src/locksmith/plugins/designer/widgets/source_event_chip_strip.py
# -*- encoding: utf-8 -*-
"""SourceEventChipStrip: event-name chips + '+ Pick event' affordance.

Used in the Projections editor to list the source_events a projection
folds over. Same shape as RuleChipStrip from Phase 3b — display-only
in Phase 3c; Phase 2 wires the × removal and Pick popup to the model.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton


class SourceEventChipStrip(QFrame):
    pick_clicked = Signal()
    chip_removed = Signal(str)

    def __init__(self, events: list[str], parent=None):
        super().__init__(parent=parent)
        self._chips: list[QLabel] = []
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        for ev in events:
            chip = QLabel(f"{ev} ×")
            chip.setStyleSheet(
                "background:#f3edfb;color:#A36AE6;border-radius:9px;"
                "padding:2px 9px;font-size:11px;font-weight:600;"
            )
            self._chips.append(chip)
            lay.addWidget(chip)
        self.pick_button = QPushButton("+ Pick event")
        self.pick_button.setFlat(True)
        self.pick_button.setStyleSheet(
            "QPushButton{color:#A36AE6;background:transparent;border:0;"
            "padding:2px 9px;font-size:11px;font-weight:600;}"
            "QPushButton:hover{color:#1A1C20;}"
        )
        self.pick_button.clicked.connect(self.pick_clicked.emit)
        lay.addWidget(self.pick_button)
        lay.addStretch(1)

    def chip_texts(self) -> list[str]:
        return [c.text().rsplit(" ×", 1)[0] for c in self._chips]
```

- [ ] **Step 4: Run tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_source_event_chip_strip_visual.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/widgets/source_event_chip_strip.py \
        tests/plugins/designer/test_source_event_chip_strip_visual.py
git commit -m "feat(designer): SourceEventChipStrip widget for projection source events"
```

---

## Task 3: SwimlaneDiagram v2 — step numbers, branches, time bounds, legend

**Files:**
- Modify: `src/locksmith/plugins/designer/widgets/swimlane_diagram.py`
- Test: `tests/plugins/designer/test_swimlane_diagram_v2.py`

Enhance the existing `SwimlaneDiagram` to render the v1 workflows mock. Changes:

1. `SwimlaneStep` gains: `step_id`, `subtitle`, optional `branches` (each `{rule_ref, next_step_id}`), `time_bound` (string or None), `is_internal` (bool — drawn dashed grey with no exchange).
2. Step numbering: each step prefixed by `1.`, `2.`, `3a.`, `3b.` — letters appended when the step is a branch outcome.
3. Branch diamonds: between a step and its branched next_steps, render a small diamond labelled with the rule_ref and outgoing arrows labelled `approved` / `rejected` (or the rule's outcome semantics). Phase 3c keeps it simple: render the diamond + label, with two outgoing arrows colored green/red.
4. Time-bound footnote: a small "⏱ <text>" label below the step.
5. Legend at the bottom: 4 swatches (self command / counterparty inbound / internal step / branch).
6. Lane labels render larger (style as titles), with "I (state-doi)" / "carrier (counterparty)" formatting.

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/designer/test_swimlane_diagram_v2.py
from locksmith.plugins.designer.widgets.swimlane_diagram import (
    SwimlaneDiagram, SwimlaneStep,
)


def test_renders_basic_lane_and_steps(qapp):
    diag = SwimlaneDiagram()
    diag.render(
        lanes=["self", "counterparty"],
        steps=[
            SwimlaneStep(step_id="a", label="step a", actor="self"),
            SwimlaneStep(step_id="b", label="step b", actor="counterparty"),
        ],
    )
    assert diag.step_count == 2


def test_step_numbers_are_assigned_sequentially(qapp):
    diag = SwimlaneDiagram()
    diag.render(
        lanes=["self"],
        steps=[
            SwimlaneStep(step_id="a", label="A", actor="self"),
            SwimlaneStep(step_id="b", label="B", actor="self"),
            SwimlaneStep(step_id="c", label="C", actor="self"),
        ],
    )
    numbers = diag.step_number_map()
    assert numbers["a"] == "1"
    assert numbers["b"] == "2"
    assert numbers["c"] == "3"


def test_branch_outcomes_get_letter_suffixes(qapp):
    diag = SwimlaneDiagram()
    diag.render(
        lanes=["self"],
        steps=[
            SwimlaneStep(step_id="decide", label="Decide", actor="self",
                          branches=[
                              {"rule_ref": "outcome_a", "next_step": "grant"},
                              {"rule_ref": "outcome_b", "next_step": "deny"},
                          ]),
            SwimlaneStep(step_id="grant", label="Grant", actor="self"),
            SwimlaneStep(step_id="deny", label="Deny", actor="self"),
        ],
    )
    numbers = diag.step_number_map()
    assert numbers["decide"] == "2"
    assert numbers["grant"] == "3a"
    assert numbers["deny"] == "3b"


def test_internal_step_marked(qapp):
    diag = SwimlaneDiagram()
    diag.render(
        lanes=["self"],
        steps=[
            SwimlaneStep(step_id="x", label="X", actor="self",
                          is_internal=True),
        ],
    )
    assert diag.internal_step_ids() == ["x"]


def test_time_bound_string_stored(qapp):
    diag = SwimlaneDiagram()
    diag.render(
        lanes=["self"],
        steps=[
            SwimlaneStep(step_id="x", label="X", actor="self",
                          time_bound="30-day bound · on expiry → terminate"),
        ],
    )
    bounds = diag.time_bound_map()
    assert "30-day" in bounds["x"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_swimlane_diagram_v2.py -v`
Expected: FAIL — `step_id`, `subtitle`, `branches`, `time_bound`, `is_internal` unexpected kwargs; `step_number_map`, `internal_step_ids`, `time_bound_map` methods don't exist.

- [ ] **Step 3: Enhance SwimlaneDiagram**

Replace the SwimlaneStep dataclass and the entire `render` method:

```python
# At top of file, keep existing imports and add:
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPolygonF


_ACTOR_COLOR: dict[str, str] = {
    "self": "#D97757",          # orange — matches v1 mock self-command color
    "counterparty": "#4A90E2",  # blue — matches v1 mock counterparty inbound
    "internal": "#888888",
}


@dataclass
class SwimlaneStep:
    step_id: str
    label: str
    actor: str
    subtitle: str = ""
    branches: list[dict] | None = None
    time_bound: str | None = None
    is_internal: bool = False


class SwimlaneDiagram(QGraphicsView):
    LANE_HEIGHT = 110
    STEP_WIDTH = 170
    STEP_HEIGHT = 60
    STEP_GAP = 50
    LEFT_MARGIN = 130

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setStyleSheet(
            "background:#fff;border:1px solid #e0e3ea;border-radius:6px;"
        )
        self._step_count = 0
        self._step_numbers: dict[str, str] = {}
        self._internal_ids: list[str] = []
        self._time_bounds: dict[str, str] = {}

    @property
    def step_count(self) -> int:
        return self._step_count

    def step_number_map(self) -> dict[str, str]:
        return dict(self._step_numbers)

    def internal_step_ids(self) -> list[str]:
        return list(self._internal_ids)

    def time_bound_map(self) -> dict[str, str]:
        return dict(self._time_bounds)

    def render(self, *, lanes: list[str], steps: list[SwimlaneStep]) -> None:
        self._scene.clear()
        self._step_count = len(steps)
        self._step_numbers = {}
        self._internal_ids = [s.step_id for s in steps if s.is_internal]
        self._time_bounds = {
            s.step_id: s.time_bound for s in steps if s.time_bound
        }
        self._assign_step_numbers(steps)

        total_width = max(
            900,
            self.LEFT_MARGIN + len(steps) * (self.STEP_WIDTH + self.STEP_GAP),
        )
        title_font = QFont()
        title_font.setPointSize(11)
        title_font.setBold(True)
        small_font = QFont()
        small_font.setPointSize(8)

        # Lane stripes + labels.
        for i, lane in enumerate(lanes):
            y = i * self.LANE_HEIGHT
            bg = QColor("#fafbfc") if i % 2 == 0 else QColor("#fff")
            self._scene.addRect(
                QRectF(0, y, total_width, self.LANE_HEIGHT),
                QPen(QColor("#e0e3ea")), QBrush(bg),
            )
            label_text = self._scene.addText(lane, title_font)
            label_text.setDefaultTextColor(QColor("#666"))
            label_text.setPos(8, y + 8)

        lane_index = {lane: i for i, lane in enumerate(lanes)}

        positions: dict[str, tuple[float, float]] = {}
        for j, step in enumerate(steps):
            x = self.LEFT_MARGIN + j * (self.STEP_WIDTH + self.STEP_GAP)
            row = lane_index.get(step.actor, 0)
            y = row * self.LANE_HEIGHT + 22
            positions[step.step_id] = (x, y)

            if step.is_internal:
                color = QColor(_ACTOR_COLOR["internal"])
                pen = QPen(color, 1.5, Qt.DashLine)
                fill = QColor("#fafbfc")
            else:
                color = QColor(_ACTOR_COLOR.get(step.actor, "#888"))
                pen = QPen(color, 2)
                fill = QColor(color.red(), color.green(), color.blue(), 38)
            self._scene.addRect(
                QRectF(x, y, self.STEP_WIDTH, self.STEP_HEIGHT),
                pen, QBrush(fill),
            )

            num = self._step_numbers.get(step.step_id, "")
            label_text = f"{num}. {step.label}" if num else step.label
            t = self._scene.addText(label_text, title_font)
            t.setDefaultTextColor(QColor("#1A1C20"))
            t.setPos(x + 8, y + 6)

            if step.subtitle:
                sub = self._scene.addText(step.subtitle, small_font)
                sub.setDefaultTextColor(QColor("#666"))
                sub.setPos(x + 8, y + 28)

            if step.time_bound:
                tb = self._scene.addText(f"⏱ {step.time_bound}", small_font)
                tb.setDefaultTextColor(QColor("#888"))
                tb.setPos(x + 4, y + self.STEP_HEIGHT + 4)

            # Branch diamond drawn just after a branching step.
            if step.branches:
                self._draw_branch_diamond(step, x, y)

        # Sequential arrows (only for non-branching consecutive steps).
        for j in range(1, len(steps)):
            prev = steps[j - 1]
            cur = steps[j]
            if prev.branches:
                continue  # Branched step has its own arrows.
            self._draw_arrow(positions[prev.step_id], positions[cur.step_id])

        # Legend below the lanes.
        self._draw_legend(total_width, len(lanes))

    def _assign_step_numbers(self, steps: list[SwimlaneStep]) -> None:
        counter = 0
        i = 0
        while i < len(steps):
            counter += 1
            s = steps[i]
            self._step_numbers[s.step_id] = str(counter)
            if s.branches:
                letters = "abcdefghij"
                outs = [b.get("next_step") for b in s.branches]
                # Number the next consecutive steps as `Nx`.
                j = i + 1
                k = 0
                while j < len(steps) and steps[j].step_id in outs and k < len(letters):
                    self._step_numbers[steps[j].step_id] = (
                        f"{counter + 1}{letters[k]}"
                    )
                    j += 1
                    k += 1
                if k > 0:
                    counter += 1
                i = j
            else:
                i += 1

    def _draw_branch_diamond(
        self, step: SwimlaneStep, sx: float, sy: float,
    ) -> None:
        cx = sx + self.STEP_WIDTH + self.STEP_GAP / 2
        cy = sy + self.STEP_HEIGHT / 2
        size = 18
        poly = QPolygonF([
            QPointF(cx, cy - size),
            QPointF(cx + size, cy),
            QPointF(cx, cy + size),
            QPointF(cx - size, cy),
        ])
        self._scene.addPolygon(
            poly,
            QPen(QColor("#A36AE6"), 1.5),
            QBrush(QColor("#f3edfb")),
        )
        # First branch rule_ref above the diamond (small).
        small_font = QFont()
        small_font.setPointSize(7)
        small_font.setBold(True)
        labels: list[str] = []
        for b in step.branches or []:
            if b.get("rule_ref"):
                labels.append(b["rule_ref"])
        if labels:
            t = self._scene.addText(labels[0], small_font)
            t.setDefaultTextColor(QColor("#A36AE6"))
            t.setPos(cx - 40, cy - size - 14)

    def _draw_arrow(
        self, start: tuple[float, float], end: tuple[float, float],
    ) -> None:
        x1 = start[0] + self.STEP_WIDTH
        y1 = start[1] + self.STEP_HEIGHT / 2
        x2 = end[0]
        y2 = end[1] + self.STEP_HEIGHT / 2
        pen = QPen(QColor("#888"), 1)
        self._scene.addLine(x1, y1, x2, y2, pen)
        import math
        angle = math.atan2(y2 - y1, x2 - x1)
        ahx = x2 - 8 * math.cos(angle - math.pi / 6)
        ahy = y2 - 8 * math.sin(angle - math.pi / 6)
        ahx2 = x2 - 8 * math.cos(angle + math.pi / 6)
        ahy2 = y2 - 8 * math.sin(angle + math.pi / 6)
        poly = QPolygonF(
            [QPointF(x2, y2), QPointF(ahx, ahy), QPointF(ahx2, ahy2)]
        )
        self._scene.addPolygon(poly, pen, QBrush(QColor("#888")))

    def _draw_legend(self, total_width: float, n_lanes: int) -> None:
        y = n_lanes * self.LANE_HEIGHT + 12
        small_font = QFont()
        small_font.setPointSize(8)
        items = [
            ("self command", _ACTOR_COLOR["self"], False),
            ("counterparty / inbound", _ACTOR_COLOR["counterparty"], False),
            ("internal step", _ACTOR_COLOR["internal"], True),
            ("branch", "#A36AE6", False),
        ]
        x = 10
        for label, color_hex, dashed in items:
            color = QColor(color_hex)
            pen = QPen(color, 1.5, Qt.DashLine if dashed else Qt.SolidLine)
            fill = QColor(color.red(), color.green(), color.blue(), 38)
            self._scene.addRect(QRectF(x, y, 14, 12), pen, QBrush(fill))
            t = self._scene.addText(label, small_font)
            t.setDefaultTextColor(QColor("#666"))
            t.setPos(x + 18, y - 2)
            x += 18 + max(110, len(label) * 7)
```

- [ ] **Step 4: Run tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_swimlane_diagram_v2.py -v`
Expected: 5 PASS.

Run existing workflows tests to ensure no regression:
Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/ -k "workflow or swimlane" -v`
Expected: all PASS.

If the existing `test_workflows_editor_renders_swimlane` test calls `SwimlaneStep(label=..., actor=...)` (positional), it'll need to be updated to use the new keyword-only fields. Adjust the `workflows.py` callsite (Task 4) accordingly — but if any existing tests still depend on old positional args, those tests need a tiny update too.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/widgets/swimlane_diagram.py \
        tests/plugins/designer/test_swimlane_diagram_v2.py
git commit -m "feat(designer): swimlane v2 — step numbers, branches, time bounds, legend"
```

---

## Task 4: Workflows editor — rail subtitle + right-pane v1

**Files:**
- Modify: `src/locksmith/plugins/designer/editors/workflows.py`
- Test: `tests/plugins/designer/test_workflows_editor_v1_visual.py`

Rail items gain subtitles (`↔ <counterparty_role> · N steps`). Right pane gets the v1 structure: header (id + name + description), trigger card (type chip + route), counterparty card, swimlane (full-width via the enhanced widget), step details list below.

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/designer/test_workflows_editor_v1_visual.py
import json
from pathlib import Path

import pytest

from locksmith.plugins.designer.crossref import compute_crossrefs
from locksmith.plugins.designer.editors.workflows import WorkflowsEditorPage
from locksmith.plugins.designer.model import TemplateModel


@pytest.fixture
def regulator_model():
    doc = json.loads(
        (Path(__file__).parent / "fixtures"
         / "regulator-grants-carrier-license.json").read_text()
    )
    return TemplateModel(doc=doc)


def test_workflow_rail_items_have_subtitles(qapp, regulator_model):
    page = WorkflowsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    rail = page.shell.rail_list
    grant_item = rail.item(0)
    text = grant_item.text()
    assert "\n" in text
    subtitle = text.split("\n", 1)[1]
    assert "carrier" in subtitle
    assert "5 steps" in subtitle


def test_workflow_pane_renders_trigger_card(qapp, regulator_model):
    page = WorkflowsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    text = page.section_text()
    # License Grant Workflow has trigger type="exn_received" + route /submit_application
    assert "exn_received" in text
    assert "/insurance/cmd/submit_application" in text


def test_workflow_pane_renders_step_details(qapp, regulator_model):
    page = WorkflowsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    text = page.section_text()
    # License Grant Workflow has steps: intake / review / decide / grant / deny
    assert "intake" in text or "Carrier submits application" in text
    assert "grant_license" in text or "Grant license" in text


def test_workflow_swimlane_v2_step_count(qapp, regulator_model):
    page = WorkflowsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    # License Grant Workflow has 5 steps.
    assert page.swimlane_step_count() == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_workflows_editor_v1_visual.py -v`
Expected: FAIL — rail has no subtitle; pane text lacks the new content.

- [ ] **Step 3: Restructure workflows.py**

Replace the rail items list comprehension and rewrite `_WorkflowSectionPane` to use the v1 layout. Key parts:

```python
def _workflow_subtitle(wf: dict) -> str:
    parts: list[str] = []
    cp = wf.get("counterparty_role")
    if cp:
        parts.append(f"↔ {cp}")
    n = len(wf.get("steps") or [])
    if n:
        parts.append(f"{n} step{'s' if n != 1 else ''}")
    return " · ".join(parts) if parts else ""
```

And in `WorkflowsEditorPage.__init__` (or wherever rail items are built):

```python
items = [
    RailItem(
        id=w.get("id", ""),
        label=w.get("name") or w.get("id") or "(unnamed)",
        subtitle=_workflow_subtitle(w),
        kind_color=color,
        has_errors=False,
    )
    for w in model.doc.get("workflows", [])
]
```

Rewrite `_WorkflowSectionPane._build` and `set_entry` to render: header block (id chip + name + description), Trigger card with type chip + route, Counterparty card, Flow swimlane (full-width using `SwimlaneDiagram` v2), Step details list, Used by.

```python
class _WorkflowSectionPane(QWidget):
    def __init__(self, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._crossrefs = crossrefs
        self._build()

    def _build(self) -> None:
        from locksmith.plugins.designer.widgets.swimlane_diagram import (
            SwimlaneDiagram,
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

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
        h.addLayout(title_row)
        self._description_label = QLabel("")
        self._description_label.setStyleSheet("color:#444;font-size:12px;")
        self._description_label.setWordWrap(True)
        h.addWidget(self._description_label)
        lay.addWidget(self._header_frame)

        # Trigger + Counterparty row (side by side).
        tc_row = QHBoxLayout()
        tc_row.setSpacing(14)
        self._trigger_section = make_section("Trigger")
        self._trigger_holder = QVBoxLayout()
        self._trigger_section.layout().addLayout(self._trigger_holder)
        tc_row.addWidget(self._trigger_section, 1)
        self._counterparty_section = make_section("Counterparty")
        self._cp_chip = QLabel("(none)")
        self._cp_chip.setStyleSheet(
            "background:#e8f4f4;color:#0a8a82;border-radius:9px;"
            "padding:2px 9px;font-size:11px;font-weight:600;"
        )
        self._counterparty_section.layout().addWidget(self._cp_chip)
        tc_row.addWidget(self._counterparty_section, 1)
        lay.addLayout(tc_row)

        # Flow swimlane.
        self._flow_section = make_section("Flow")
        self.swimlane = SwimlaneDiagram()
        self.swimlane.setMinimumHeight(280)
        self._flow_section.layout().addWidget(self.swimlane)
        lay.addWidget(self._flow_section)

        # Step details.
        self._steps_section = make_section("Step details")
        self._steps_holder = QVBoxLayout()
        self._steps_section.layout().addLayout(self._steps_holder)
        lay.addWidget(self._steps_section)

        # Used by.
        self._used_by = make_section("Used by")
        self.chip_strip = CrossRefChipStrip()
        self._used_by.layout().addWidget(self.chip_strip)
        lay.addWidget(self._used_by)
        lay.addStretch(1)

    def set_entry(self, entry: dict[str, Any]) -> None:
        from locksmith.plugins.designer.widgets.swimlane_diagram import (
            SwimlaneStep,
        )

        self._name_label.setText(entry.get("name") or entry.get("id") or "(unnamed)")
        self._id_chip.setText(entry.get("id", ""))
        self._description_label.setText(entry.get("description", ""))

        # Trigger card content.
        while self._trigger_holder.count():
            old = self._trigger_holder.takeAt(0).widget()
            if old is not None:
                old.setParent(None)
                old.deleteLater()
        trig = entry.get("trigger") or {}
        t_type = trig.get("type", "")
        chip_row = QHBoxLayout()
        type_chip = QLabel(t_type or "(none)")
        type_chip.setStyleSheet(
            "background:#e8f4f4;color:#0a8a82;border-radius:9px;"
            "padding:2px 9px;font-size:11px;font-weight:600;"
        )
        chip_row.addWidget(type_chip)
        if trig.get("route"):
            r_lbl = QLabel(trig["route"])
            r_lbl.setStyleSheet(
                "color:#0ABFB0;font-family:monospace;font-size:11px;"
            )
            chip_row.addWidget(r_lbl)
        chip_row.addStretch(1)
        chip_row_widget = QFrame()
        chip_row_widget.setLayout(chip_row)
        self._trigger_holder.addWidget(chip_row_widget)

        # Counterparty chip.
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

        # Swimlane.
        steps_raw = entry.get("steps") or []
        # Decide lane order: self always first, counterparty second.
        actors = sorted({s.get("actor", "self") for s in steps_raw},
                        key=lambda a: 0 if a == "self" else 1)
        if not actors:
            actors = ["self"]
        lane_labels = [
            f"I ({entry.get('id', '')})" if a == "self"
            else f"counterparty ({entry.get('counterparty_role', 'counterparty')})"
            for a in actors
        ]
        lane_to_index = {a: i for i, a in enumerate(actors)}
        swim_steps: list[SwimlaneStep] = []
        for s in steps_raw:
            actor = s.get("actor", "self")
            is_internal = (
                not s.get("command_id")
                and not s.get("reaction_id")
                and not s.get("advance_lifecycle")
                and not s.get("expected_inbound")
                and not s.get("branches")
            )
            tb = s.get("time_bound") or {}
            tb_text = None
            if isinstance(tb, dict) and tb.get("duration"):
                exp = tb.get("on_expiry") or ""
                tb_text = (f"{tb['duration']} bound"
                           f"{' · on expiry → ' + exp if exp else ''}")
            swim_steps.append(SwimlaneStep(
                step_id=s.get("id", ""),
                label=s.get("name") or s.get("id") or "(unnamed)",
                actor=actor if actor in lane_to_index else "self",
                subtitle=_step_subtitle(s),
                branches=s.get("branches"),
                time_bound=tb_text,
                is_internal=is_internal,
            ))
        # Map our two-lane orientation. The SwimlaneDiagram render needs
        # lanes as a flat list; we already prepared lane_labels in actor
        # order. The step.actor reads the original "self"/"counterparty".
        # Rewrite each step's actor to the lane label so the diagram
        # places them correctly.
        actor_to_label = {a: lane_labels[i] for i, a in enumerate(actors)}
        for s in swim_steps:
            s.actor = actor_to_label.get(s.actor, lane_labels[0])
        self.swimlane.render(lanes=lane_labels, steps=swim_steps)

        # Step details list.
        while self._steps_holder.count():
            old = self._steps_holder.takeAt(0).widget()
            if old is not None:
                old.setParent(None)
                old.deleteLater()
        for s in steps_raw:
            row = QHBoxLayout()
            row.setSpacing(8)
            name_lbl = QLabel(
                f"{s.get('name') or s.get('id', '?')}"
            )
            name_lbl.setStyleSheet("font-weight:600;color:#1A1C20;font-size:12px;")
            row.addWidget(name_lbl)
            actor_lbl = QLabel(f"actor: {s.get('actor', '?')}")
            actor_lbl.setStyleSheet("color:#666;font-size:11px;")
            row.addWidget(actor_lbl)
            if s.get("command_id"):
                cmd_lbl = QLabel(f"→ command {s['command_id']}")
                cmd_lbl.setStyleSheet("color:#0ABFB0;font-size:11px;")
                row.addWidget(cmd_lbl)
            if s.get("reaction_id"):
                rx_lbl = QLabel(f"→ reaction {s['reaction_id']}")
                rx_lbl.setStyleSheet("color:#0ABFB0;font-size:11px;")
                row.addWidget(rx_lbl)
            adv = s.get("advance_lifecycle") or {}
            if adv.get("credential_id"):
                a_lbl = QLabel(
                    f"→ advance {adv['credential_id']} to {adv.get('to_state','?')}"
                )
                a_lbl.setStyleSheet("color:#0ABFB0;font-size:11px;")
                row.addWidget(a_lbl)
            row.addStretch(1)
            row_w = QFrame()
            row_w.setLayout(row)
            self._steps_holder.addWidget(row_w)

        # Used by chips.
        self.chip_strip.set_refs(
            self._crossrefs.consumers_of(f"workflow:{entry.get('id', '')}")
        )

    def text_summary(self) -> str:
        parts = [
            self._name_label.text(),
            self._id_chip.text(),
            self._description_label.text(),
            self._cp_chip.text(),
        ]
        for lbl in self._trigger_section.findChildren(QLabel):
            parts.append(lbl.text())
        for lbl in self._steps_section.findChildren(QLabel):
            parts.append(lbl.text())
        return " ".join(parts)


def _step_subtitle(s: dict) -> str:
    if s.get("command_id"):
        return f"command · {s['command_id']}"
    if s.get("reaction_id"):
        return f"reaction · {s['reaction_id']}"
    adv = s.get("advance_lifecycle") or {}
    if adv.get("credential_id"):
        return f"advance {adv['credential_id']}"
    if s.get("expected_inbound"):
        inb = s["expected_inbound"][0]
        return f"{inb.get('trigger_type','?')} · {inb.get('route', '')}"
    return "internal · no exchange"
```

Replace the existing `_WorkflowSectionPane` class and the rail items construction. Add `_workflow_subtitle` near the bottom of the file. Update `swimlane_step_count` on the page to delegate to `self._pane.swimlane.step_count`.

- [ ] **Step 4: Run tests + full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_workflows_editor_v1_visual.py tests/plugins/designer/test_workflows_editor_visual.py -v`
Expected: all PASS (the existing 5-step test expectation from Phase 1 still holds).

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/editors/workflows.py \
        tests/plugins/designer/test_workflows_editor_v1_visual.py
git commit -m "feat(designer): workflows v1 right-pane (trigger card + swimlane v2 + step details)"
```

---

## Task 5: Projections editor — rail subtitle

**Files:**
- Modify: `src/locksmith/plugins/designer/editors/projections.py`
- Test: `tests/plugins/designer/test_projections_editor_v1_visual.py`

Rail entries get a subtitle showing view-type + source-event count (e.g., `table · folds 2 events`).

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/designer/test_projections_editor_v1_visual.py
import json
from pathlib import Path

import pytest

from locksmith.plugins.designer.crossref import compute_crossrefs
from locksmith.plugins.designer.editors.projections import ProjectionsEditorPage
from locksmith.plugins.designer.model import TemplateModel


@pytest.fixture
def regulator_model():
    doc = json.loads(
        (Path(__file__).parent / "fixtures"
         / "regulator-grants-carrier-license.json").read_text()
    )
    return TemplateModel(doc=doc)


def test_projection_rail_items_have_subtitles(qapp, regulator_model):
    page = ProjectionsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    rail = page.shell.rail_list
    item = rail.item(0)
    text = item.text()
    assert "\n" in text
    subtitle = text.split("\n", 1)[1]
    assert "table" in subtitle
    assert "events" in subtitle
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_projections_editor_v1_visual.py -v`
Expected: FAIL.

- [ ] **Step 3: Add subtitle helper + use in rail items**

Add `_projection_subtitle` near the bottom of `projections.py`:

```python
def _projection_subtitle(p: dict) -> str:
    parts: list[str] = []
    view = (p.get("display") or {}).get("view_type")
    if view:
        parts.append(view)
    n = len(p.get("source_events") or [])
    if n:
        parts.append(f"folds {n} event{'s' if n != 1 else ''}")
    return " · ".join(parts) if parts else ""
```

Update the rail items construction to pass `subtitle=_projection_subtitle(p)` for each projection.

- [ ] **Step 4: Run tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_projections_editor_v1_visual.py -v`
Expected: 1 PASS.

Full suite:
Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/editors/projections.py \
        tests/plugins/designer/test_projections_editor_v1_visual.py
git commit -m "feat(designer): projection rail items show view-type + event count"
```

---

## Task 6: Projections editor — two-column right pane

**Files:**
- Modify: `src/locksmith/plugins/designer/editors/projections.py`
- Test: `tests/plugins/designer/test_projections_editor_v1_visual.py` (extend)

Restructure `_ProjectionSectionPane._build` so the body is a QHBoxLayout: left column = editor controls (header + SOURCE EVENTS chip strip + FOLD EXPRESSION dark code block + OUTPUT SCHEMA · ROW SHAPE table + ACCESS · WHO CAN SEE row-filter section + VIEW TYPE chip picker), right column = live preview pane (placeholder "evaluator pending" until v2 wires the UEL evaluator).

- [ ] **Step 1: Write the failing test**

Append to `tests/plugins/designer/test_projections_editor_v1_visual.py`:

```python
def test_projection_pane_uses_source_event_chip_strip(qapp, regulator_model):
    from locksmith.plugins.designer.widgets.source_event_chip_strip import (
        SourceEventChipStrip,
    )
    page = ProjectionsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    strip = page._pane.findChild(SourceEventChipStrip)
    assert strip is not None
    # First projection is "pending_applications" with two source events.
    assert "application_recorded" in strip.chip_texts()


def test_projection_pane_renders_dark_fold_expression(qapp, regulator_model):
    from locksmith.plugins.designer.widgets.dark_code_block import DarkCodeBlock
    page = ProjectionsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    block = page._pane.findChild(DarkCodeBlock)
    assert block is not None
    assert "application_recorded" in block.toPlainText() \
        or "events.filter" in block.toPlainText()


def test_projection_pane_uses_view_type_picker(qapp, regulator_model):
    from locksmith.plugins.designer.widgets.view_type_chip_picker import (
        ViewTypeChipPicker,
    )
    page = ProjectionsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    picker = page._pane.findChild(ViewTypeChipPicker)
    assert picker is not None
    assert picker.active_view_type() == "table"


def test_projection_pane_renders_output_schema_table(qapp, regulator_model):
    from locksmith.plugins.designer.widgets.payload_schema_table import (
        PayloadSchemaTable,
    )
    page = ProjectionsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    # The first projection's output_schema is an array of objects with
    # applicant_aid / jurisdiction / received_at properties; the table
    # should render those.
    tables = page._pane.findChildren(PayloadSchemaTable)
    assert len(tables) >= 1
    rows = tables[0].field_rows()
    fields = {r["field"] for r in rows}
    assert {"applicant_aid", "jurisdiction", "received_at"}.issubset(fields)


def test_projection_pane_renders_live_preview_pane(qapp, regulator_model):
    page = ProjectionsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    text = page.preview_text().lower()
    # Without an evaluator, the preview shows the "evaluator pending" fallback.
    assert "evaluator pending" in text or "events.filter" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_projections_editor_v1_visual.py -v`
Expected: 5 FAIL.

- [ ] **Step 3: Rewrite _ProjectionSectionPane to use two-column layout**

Replace the entire `_ProjectionSectionPane` class in `projections.py`:

```python
class _ProjectionSectionPane(QWidget):
    def __init__(self, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._crossrefs = crossrefs
        self._build()

    def _build(self) -> None:
        from locksmith.plugins.designer.widgets.dark_code_block import (
            DarkCodeBlock,
        )
        from locksmith.plugins.designer.widgets.source_event_chip_strip import (
            SourceEventChipStrip,
        )
        from locksmith.plugins.designer.widgets.view_type_chip_picker import (
            ViewTypeChipPicker,
        )
        from locksmith.plugins.designer.widgets.payload_schema_table import (
            PayloadSchemaTable,
        )
        from locksmith.plugins.designer.widgets.rule_chip_strip import (
            RuleChipStrip,
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

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
        h.addLayout(title_row)
        self._description_label = QLabel("")
        self._description_label.setStyleSheet("color:#444;font-size:12px;")
        self._description_label.setWordWrap(True)
        h.addWidget(self._description_label)
        outer.addWidget(self._header_frame)

        # Two-column body.
        body = QHBoxLayout()
        body.setSpacing(14)

        # ===== LEFT column (editor) =====
        left = QVBoxLayout()
        left.setSpacing(14)

        # SOURCE EVENTS
        self._sources_section = make_section("Source events · fold from")
        self._sources_holder = QVBoxLayout()
        self._sources_section.layout().addLayout(self._sources_holder)
        left.addWidget(self._sources_section)

        # FOLD EXPRESSION
        self._fold_section = make_section("Fold expression")
        self._fold_holder = QVBoxLayout()
        self._fold_section.layout().addLayout(self._fold_holder)
        cheat = QLabel("↗ UEL/1.0 cheat-sheet · test expression")
        cheat.setStyleSheet("color:#0ABFB0;font-size:10px;")
        self._fold_section.layout().addWidget(cheat)
        left.addWidget(self._fold_section)

        # OUTPUT SCHEMA
        self._output_section = make_section("Output schema · row shape")
        self._output_holder = QVBoxLayout()
        self._output_section.layout().addLayout(self._output_holder)
        left.addWidget(self._output_section)

        # ACCESS
        self._access_section = make_section("Access · who can see")
        self._access_label = QLabel(
            "Row filter: None — all rows visible to anyone in role"
        )
        self._access_label.setStyleSheet("color:#444;font-size:11px;")
        self._access_label.setWordWrap(True)
        self._access_section.layout().addWidget(self._access_label)
        self._access_picker_holder = QVBoxLayout()
        self._access_section.layout().addLayout(self._access_picker_holder)
        left.addWidget(self._access_section)

        # VIEW TYPE
        self._view_type_section = make_section("View type")
        self._view_picker = ViewTypeChipPicker(active="table")
        self._view_type_section.layout().addWidget(self._view_picker)
        left.addWidget(self._view_type_section)

        left.addStretch(1)
        body.addLayout(left, 3)

        # ===== RIGHT column (live preview) =====
        self._preview_section = make_section("Live preview · how Locksmith renders this")
        self._preview_holder = QVBoxLayout()
        self._preview_section.layout().addLayout(self._preview_holder)
        body.addWidget(self._preview_section, 2)

        outer.addLayout(body, 1)

        # Used by below.
        self._used_by = make_section("Used by")
        self.chip_strip = CrossRefChipStrip()
        self._used_by.layout().addWidget(self.chip_strip)
        outer.addWidget(self._used_by)

    def set_entry(self, entry: dict[str, Any]) -> None:
        from locksmith.plugins.designer.widgets.dark_code_block import (
            DarkCodeBlock,
        )
        from locksmith.plugins.designer.widgets.source_event_chip_strip import (
            SourceEventChipStrip,
        )
        from locksmith.plugins.designer.widgets.view_type_chip_picker import (
            ViewTypeChipPicker,
        )
        from locksmith.plugins.designer.widgets.payload_schema_table import (
            PayloadSchemaTable,
        )
        from locksmith.plugins.designer.widgets.rule_chip_strip import (
            RuleChipStrip,
        )

        self._name_label.setText(entry.get("name") or entry.get("id") or "(unnamed)")
        self._id_chip.setText(entry.get("id", ""))
        self._description_label.setText(entry.get("description", ""))

        # Source events.
        while self._sources_holder.count():
            old = self._sources_holder.takeAt(0).widget()
            if old is not None:
                old.setParent(None)
                old.deleteLater()
        self._sources_holder.addWidget(
            SourceEventChipStrip(entry.get("source_events") or [])
        )

        # Fold expression.
        while self._fold_holder.count():
            old = self._fold_holder.takeAt(0).widget()
            if old is not None:
                old.setParent(None)
                old.deleteLater()
        self._fold_holder.addWidget(
            DarkCodeBlock(entry.get("fold_expression", ""))
        )

        # Output schema.
        while self._output_holder.count():
            old = self._output_holder.takeAt(0).widget()
            if old is not None:
                old.setParent(None)
                old.deleteLater()
        out = entry.get("output_schema") or {}
        # If output_schema is array-of-objects, drill into items.
        if out.get("type") == "array" and isinstance(out.get("items"), dict):
            row_schema = out["items"]
        else:
            row_schema = out
        self._output_holder.addWidget(PayloadSchemaTable(row_schema))

        # Access row-filter.
        while self._access_picker_holder.count():
            old = self._access_picker_holder.takeAt(0).widget()
            if old is not None:
                old.setParent(None)
                old.deleteLater()
        access = entry.get("access") or {}
        rf = access.get("row_filter_rule_ref")
        refs = [rf] if rf else []
        self._access_picker_holder.addWidget(RuleChipStrip(refs))

        # View type.
        view = (entry.get("display") or {}).get("view_type", "table")
        self._view_picker.set_active(view)

        # Preview pane — fallback shows the raw fold expression with a note.
        while self._preview_holder.count():
            old = self._preview_holder.takeAt(0).widget()
            if old is not None:
                old.setParent(None)
                old.deleteLater()
        note = QLabel("evaluator pending — showing raw expression:")
        note.setStyleSheet("color:#aaa;font-style:italic;font-size:11px;")
        self._preview_holder.addWidget(note)
        self._preview_holder.addWidget(
            DarkCodeBlock(entry.get("fold_expression", ""))
        )

        # Used-by chips.
        self.chip_strip.set_refs(
            self._crossrefs.consumers_of(f"projection:{entry.get('id', '')}")
        )

    def preview_text(self) -> str:
        from PySide6.QtWidgets import QLabel
        from locksmith.plugins.designer.widgets.dark_code_block import (
            DarkCodeBlock,
        )
        parts: list[str] = []
        for lbl in self._preview_section.findChildren(QLabel):
            parts.append(lbl.text())
        for block in self._preview_section.findChildren(DarkCodeBlock):
            parts.append(block.toPlainText())
        return " ".join(parts)

    def text_summary(self) -> str:
        return " ".join([
            self._name_label.text(),
            self._id_chip.text(),
            self._description_label.text(),
            self._access_label.text(),
        ])

    def preview_visible(self) -> bool:
        return self._preview_section.isVisible()
```

Also expose `page.preview_text()` on `ProjectionsEditorPage`:

```python
    def preview_text(self) -> str:
        return self._pane.preview_text()
```

And keep `page.preview_visible()` if existing test uses it.

- [ ] **Step 4: Run tests + full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_projections_editor_v1_visual.py tests/plugins/designer/test_projections_editor_visual.py -v`
Expected: all PASS. The existing `test_projections_editor_preview_fallback_when_no_evaluator` should still pass since the preview pane shows "evaluator pending" + the raw expression.

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/editors/projections.py \
        tests/plugins/designer/test_projections_editor_v1_visual.py
git commit -m "feat(designer): projections v1 right-pane (two-column with live preview)"
```

---

## Task 7: Final live verification

**Files:**
- (No code changes)

Drive the wallet via the harness and confirm the visual output for Workflows + Projections matches their respective v1 mocks.

- [ ] **Step 1: Restart wallet**

```bash
ps aux | grep "locksmith.main" | grep -v grep | awk '{print $2}' | head -1 | xargs -r kill
sleep 1
LOCKSMITH_DEV_CONTROL=1 LOCKSMITH_DESIGNER_SEED_FIXTURES=1 \
    nohup .venv/bin/python -m locksmith.main > /tmp/locksmith-wallet.log 2>&1 &
sleep 4
```

- [ ] **Step 2: Unlock + navigate to Workflows**

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
.venv/bin/python tools/devctl.py click '{"target": "Workflows"}'
.venv/bin/python tools/devctl.py screenshot \
    '{"path": "/tmp/locksmith-3c-workflows.png"}'
```

Read the image. Expected vs `.superpowers/brainstorm/69587-1778622927/content/workflows-editor.html`:
- Rail items each show name + "↔ carrier · N steps" subtitle
- Right pane header: "License Grant Workflow" + id chip
- Description sentence below
- Trigger card: `exn_received` chip + `/insurance/cmd/submit_application` route
- Counterparty card: `carrier` chip
- **Flow swimlane**: full width, two lanes ("I (license_grant_workflow)" / "carrier (carrier)"), 5 step boxes with numbers, branch diamond after the "decide" step, legend at bottom
- Step details list below the swimlane

- [ ] **Step 3: Navigate to Projections**

```bash
.venv/bin/python tools/devctl.py click '{"target": "Templates"}'
.venv/bin/python tools/devctl.py click '{"target": "Regulator Grants Carrier License"}'
.venv/bin/python tools/devctl.py click '{"target": "Projections"}'
.venv/bin/python tools/devctl.py screenshot \
    '{"path": "/tmp/locksmith-3c-projections.png"}'
```

Read the image. Expected vs `projections-editor.html`:
- Rail items show "table · folds N events" subtitle
- Right pane is split: left column (header + sources + fold + output schema + access + view type) and right column (live preview pane "evaluator pending — showing raw expression")
- Source events strip has chip(s) + "+ Pick event"
- Fold expression renders in dark code block
- Output schema table shows applicant_aid / jurisdiction / received_at
- View type picker shows table active (orange)

- [ ] **Step 4: Run the full test suite**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/ -v
```

Expected: all PASS.

- [ ] **Step 5: Milestone commit**

```bash
git commit --allow-empty -m "milestone(designer): Phase 3c (Workflows + Projections content) complete"
```

---

## Self-review checklist

1. **Spec coverage — Workflows**:
   - Rail subtitles ✓ Task 4 helper.
   - Trigger card with type + route ✓ Task 4.
   - Counterparty card ✓ Task 4.
   - Swimlane v2 (numbers + branches + time bounds + legend) ✓ Tasks 3 + 4.
   - Step details rich list ✓ Task 4.
   - Used by ✓ Task 4.

2. **Spec coverage — Projections**:
   - Rail subtitles ✓ Task 5.
   - Two-column layout ✓ Task 6.
   - Source-event chip strip ✓ Tasks 2 + 6.
   - Fold expression in dark code block ✓ Task 6 (via DarkCodeBlock from 3a).
   - Output schema table ✓ Task 6 (via PayloadSchemaTable from 3b).
   - Access / row-filter section ✓ Task 6 (via RuleChipStrip from 3b).
   - View-type chip picker ✓ Tasks 1 + 6.
   - Live preview pane (fallback) ✓ Task 6.

3. **Out of scope (Phase 2 / later):**
   - Live UEL evaluator (preview shows "evaluator pending" — v2-deferred per spec).
   - Sample-event data editor (Phase 2 / v2).
   - Clickable + Pick event / + Pick rule / chip × / + Add field / + Add step (display-only here).
   - Branch arrow labelling with rule outcome text (approved/rejected) — Phase 3c renders the diamond + rule_ref label; labelled outcomes are a polish item for later.

4. **Placeholder scan:** no TBD / "implement later". Every code block has runnable content.

5. **Type consistency:**
   - `ViewTypeChipPicker(active="table")` / `view_types()` / `active_view_type()` / `set_active(name)` / `view_type_changed(str)` signal.
   - `SourceEventChipStrip(events)` / `chip_texts()` / `pick_button`.
   - `SwimlaneStep(step_id, label, actor, subtitle="", branches=None, time_bound=None, is_internal=False)` — keyword-only.
   - `SwimlaneDiagram.render(lanes, steps)` / `step_count` / `step_number_map()` / `internal_step_ids()` / `time_bound_map()`.
   - `_WorkflowSectionPane.set_entry(entry)` / `text_summary()` / `swimlane.step_count` for the existing test.
   - `_ProjectionSectionPane.set_entry(entry)` / `preview_text()` / `text_summary()` / `preview_visible()`.
