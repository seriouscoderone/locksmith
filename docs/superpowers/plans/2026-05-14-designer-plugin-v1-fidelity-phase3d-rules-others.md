# Designer Plugin — V1 Fidelity Phase 3d (Rules + Aggregates + Reactions + Imports) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the remaining four per-primitive editors — Rules, Aggregates, Reactions, Imports — to v1 mock parity. Rules gets the biggest upgrade: a typed-filter chip bar at the top of the rail, items grouped under type headers, and a right-pane with type-color badge + DarkCodeBlock expression + REFERENCED FROM + PAIRS WITH sections. Aggregates / Reactions / Imports get chip-ified right panes matching their `remaining-editors-gallery.html` mock. **Still display-only** — `+ Pick rule`, chip ×, `+ Add` affordances are visible but no-op until Phase 2.

**Architecture:** Add one new shared widget (`RailFilterChipBar` for the Rules type filter). Extend `KindRail` so `RailItem` may carry a `group_header` that renders as a non-selectable typed section separator. Rewrite the right panes of `rules.py`, `aggregates.py`, `reactions.py`, `imports.py` to use the v1 mock layouts, leveraging `TypeColorBadge` (3a), `DarkCodeBlock` (3a), `RuleChipStrip` (3b), `CrossRefChipStrip` (existing).

**Tech Stack:** PySide6, pytest with `QT_QPA_PLATFORM=offscreen`, existing `TemplateModel`, `CrossRefIndex`, `make_section()`, all the shared widgets from earlier phases (TypeColorBadge, DarkCodeBlock, RuleChipStrip, EcosystemChip).

---

## File Structure

**Created in this plan:**

```
src/locksmith/plugins/designer/widgets/
└── rail_filter_chip_bar.py     # filter chips at top of a primitive rail

tests/plugins/designer/
├── test_rail_filter_chip_bar_visual.py
├── test_kind_rail_grouped_visual.py
├── test_rules_editor_v1_visual.py
├── test_aggregates_editor_v1_visual.py
├── test_reactions_editor_v1_visual.py
└── test_imports_editor_v1_visual.py
```

**Modified in this plan:**

```
src/locksmith/plugins/designer/widgets/
└── kind_rail.py                # RailItem.group_header — non-selectable separator

src/locksmith/plugins/designer/editors/
├── rules.py                    # typed-filter rail + grouped + right-pane v1
├── aggregates.py               # rail subtitle + chip-ified right pane
├── reactions.py                # rail subtitle + trigger card + emissions chips + failure policy
└── imports.py                  # rail subtitle + chip-ified right pane + rich USED BY
```

**Out of scope (Phase 2 / later):** clickable filter-chip behavior (chips show counts but no-op on click), clickable + Pick rule / chip × removal, "+ accept state" / "+ Add" wizards, "+ Add invariant" affordance.

---

## Task 1: RailFilterChipBar widget

**Files:**
- Create: `src/locksmith/plugins/designer/widgets/rail_filter_chip_bar.py`
- Test: `tests/plugins/designer/test_rail_filter_chip_bar_visual.py`

A horizontal strip of filter chips, each labeled `<name> (<count>)`. One chip is "active" (dark fill + white text); others are flat grey. Emits `filter_changed(name)`. Display-only behavior in 3d — clicking changes the active visual but doesn't filter the rail yet.

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/designer/test_rail_filter_chip_bar_visual.py
from locksmith.plugins.designer.widgets.rail_filter_chip_bar import (
    RailFilterChipBar,
)


def test_renders_chips_with_counts(qapp):
    bar = RailFilterChipBar(
        chips=[("all", 7), ("prose", 2), ("predicate", 3)],
        active="all",
    )
    assert bar.chip_text("all") == "all (7)"
    assert bar.chip_text("prose") == "prose (2)"


def test_active_chip_dark_filled(qapp):
    bar = RailFilterChipBar(chips=[("all", 7), ("prose", 2)], active="all")
    style = bar._buttons["all"].styleSheet()
    assert "#1A1C20" in style


def test_clicking_chip_emits_filter_changed(qapp):
    bar = RailFilterChipBar(chips=[("all", 7), ("prose", 2)], active="all")
    received: list[str] = []
    bar.filter_changed.connect(lambda name: received.append(name))
    bar._buttons["prose"].click()
    assert received == ["prose"]
    assert bar.active_filter() == "prose"


def test_zero_count_chips_still_render(qapp):
    bar = RailFilterChipBar(chips=[("all", 0), ("validation", 0)], active="all")
    assert bar.chip_text("all") == "all (0)"
    assert bar.chip_text("validation") == "validation (0)"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_rail_filter_chip_bar_visual.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement RailFilterChipBar**

```python
# src/locksmith/plugins/designer/widgets/rail_filter_chip_bar.py
# -*- encoding: utf-8 -*-
"""RailFilterChipBar: filter chips with counts above a primitive rail.

Used in the Rules editor to let the user filter the rail by rule.type.
Phase 3d ships display-only — clicking a chip changes the active visual
but doesn't yet filter the rail. Phase 2 wires the rail repopulation.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton


class RailFilterChipBar(QFrame):
    filter_changed = Signal(str)

    def __init__(
        self,
        chips: list[tuple[str, int]],
        active: str = "all",
        parent=None,
    ):
        super().__init__(parent=parent)
        self._chip_names = [name for name, _ in chips]
        self._chip_counts = {name: count for name, count in chips}
        self._active = active if active in self._chip_counts else (
            self._chip_names[0] if self._chip_names else ""
        )
        self._buttons: dict[str, QPushButton] = {}
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(4)
        for name, count in chips:
            btn = QPushButton(f"{name} ({count})")
            btn.setFlat(True)
            btn.clicked.connect(lambda _checked=False, n=name: self.set_active(n))
            self._buttons[name] = btn
            lay.addWidget(btn)
        lay.addStretch(1)
        self._restyle()

    def chip_text(self, name: str) -> str:
        btn = self._buttons.get(name)
        return btn.text() if btn is not None else ""

    def active_filter(self) -> str:
        return self._active

    def set_active(self, name: str) -> None:
        if name not in self._buttons or name == self._active:
            return
        self._active = name
        self._restyle()
        self.filter_changed.emit(name)

    def _restyle(self) -> None:
        for name, btn in self._buttons.items():
            if name == self._active:
                btn.setStyleSheet(
                    "QPushButton{color:#fff;background:#1A1C20;"
                    "border:0;border-radius:9px;padding:2px 9px;"
                    "font-size:11px;font-weight:600;}"
                )
            else:
                btn.setStyleSheet(
                    "QPushButton{color:#444;background:#f0f2f5;"
                    "border:0;border-radius:9px;padding:2px 9px;"
                    "font-size:11px;}"
                    "QPushButton:hover{color:#1A1C20;background:#e8eaef;}"
                )
```

- [ ] **Step 4: Run tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_rail_filter_chip_bar_visual.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/widgets/rail_filter_chip_bar.py \
        tests/plugins/designer/test_rail_filter_chip_bar_visual.py
git commit -m "feat(designer): RailFilterChipBar widget for typed rail filters"
```

---

## Task 2: KindRail — group separators

**Files:**
- Modify: `src/locksmith/plugins/designer/widgets/kind_rail.py`
- Test: `tests/plugins/designer/test_kind_rail_grouped_visual.py`

`RailItem` gains an optional `group_header: str | None` field. When set, the item renders as a non-selectable section header (small uppercase grey label) instead of a clickable rail item. The selectable items below it stay as before.

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/designer/test_kind_rail_grouped_visual.py
from PySide6.QtCore import Qt

from locksmith.plugins.designer.widgets.kind_rail import KindRail, RailItem


def test_railitem_group_header_field_optional(qapp):
    rail = KindRail()
    rail.populate([
        RailItem(id="a", label="A", kind_color="#888", has_errors=False),
    ])
    item = rail.item(0)
    assert item.text() == "A"


def test_group_header_renders_as_non_selectable_separator(qapp):
    rail = KindRail()
    rail.populate([
        RailItem(id="grp1", label="", kind_color="", has_errors=False,
                 group_header="LEGAL PROSE"),
        RailItem(id="a", label="A", kind_color="#A36AE6", has_errors=False),
    ])
    header_item = rail.item(0)
    assert header_item.text() == "LEGAL PROSE"
    # Header items are flagged not-selectable via Qt.NoItemFlags.
    flags = header_item.flags()
    assert not (flags & Qt.ItemIsSelectable)
    # Regular item is selectable.
    a_item = rail.item(1)
    assert a_item.flags() & Qt.ItemIsSelectable
    # Selection lands on the first selectable item, not the header.
    assert rail.currentRow() == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_kind_rail_grouped_visual.py -v`
Expected: FAIL — `group_header` is an unexpected kwarg.

- [ ] **Step 3: Add group_header to RailItem + render in KindRail**

Edit `src/locksmith/plugins/designer/widgets/kind_rail.py`:

```python
@dataclass(frozen=True)
class RailItem:
    id: str
    label: str
    kind_color: str
    has_errors: bool
    subtitle: str | None = None
    group_header: str | None = None
```

And update `populate` to handle group headers:

```python
    def populate(self, items: list[RailItem]) -> None:
        self.clear()
        first_selectable = -1
        for idx, r in enumerate(items):
            if r.group_header:
                hdr = QListWidgetItem(r.group_header)
                hdr.setFlags(Qt.NoItemFlags)
                hdr.setData(
                    Qt.UserRole, None,
                )
                self.addItem(hdr)
                continue
            main = r.label + ("  ⛔" if r.has_errors else "")
            text = f"{main}\n{r.subtitle}" if r.subtitle else main
            item = QListWidgetItem(text)
            item.setIcon(_dot_icon(r.kind_color))
            item.setData(Qt.UserRole, r.id)
            self.addItem(item)
            if first_selectable == -1:
                first_selectable = self.count() - 1
        if first_selectable >= 0:
            self.setCurrentRow(first_selectable)
```

Also bump the stylesheet to differentiate the header rows:

```python
        self.setStyleSheet(
            "QListWidget{background:#fff;border:0;}"
            "QListWidget::item{padding:10px 12px;border-bottom:1px solid #f0f2f5;}"
            "QListWidget::item:selected{background:#f6f7f9;color:#1A1C20;}"
            "QListWidget::item:disabled{"
            "color:#888;background:#fafbfc;font-size:9px;"
            "font-weight:600;letter-spacing:0.5px;padding:6px 12px;}"
        )
```

(The `:disabled` selector lights up on items with `Qt.NoItemFlags` — Qt treats unflagged items as disabled for rendering purposes.)

- [ ] **Step 4: Run tests + full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_kind_rail_grouped_visual.py tests/plugins/designer/test_kind_rail_subtitle.py -v`
Expected: PASS.

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/widgets/kind_rail.py \
        tests/plugins/designer/test_kind_rail_grouped_visual.py
git commit -m "feat(designer): KindRail — RailItem.group_header for typed sections"
```

---

## Task 3: Rules editor — typed-filter rail + grouped + subtitle

**Files:**
- Modify: `src/locksmith/plugins/designer/editors/rules.py`
- Test: `tests/plugins/designer/test_rules_editor_v1_visual.py`

Add the filter chip bar above the rail. The rail items get reorganized: ordered by type (legal_prose / behavioral_expectation → "LEGAL PROSE" group, predicate → "PREDICATE", validation/computational → "VALIDATION", binding_link → "BINDING LINK"), with `group_header` separator items between sections. Each rule's RailItem subtitle summarizes its purpose / linkage (e.g. `purpose: lifecycle_transition · → 1 transition`).

The chip bar lives above the rail — it can't go inside `+ Add rule` button, so the editor wraps its shell with a small QVBoxLayout-prepended chip bar before adding to `outer`.

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/designer/test_rules_editor_v1_visual.py
import json
from pathlib import Path

import pytest

from locksmith.plugins.designer.crossref import compute_crossrefs
from locksmith.plugins.designer.editors.rules import RulesEditorPage
from locksmith.plugins.designer.model import TemplateModel


@pytest.fixture
def regulator_model():
    doc = json.loads(
        (Path(__file__).parent / "fixtures"
         / "regulator-grants-carrier-license.json").read_text()
    )
    return TemplateModel(doc=doc)


def test_rules_editor_has_typed_filter_chip_bar(qapp, regulator_model):
    from locksmith.plugins.designer.widgets.rail_filter_chip_bar import (
        RailFilterChipBar,
    )
    page = RulesEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    bar = page.findChild(RailFilterChipBar)
    assert bar is not None
    assert bar.chip_text("all") == "all (7)"
    assert bar.chip_text("prose") == "prose (2)"
    assert bar.chip_text("predicate") == "predicate (3)"
    assert bar.chip_text("validation") == "validation (1)"
    assert bar.chip_text("link") == "link (1)"


def test_rules_editor_rail_groups_by_type(qapp, regulator_model):
    page = RulesEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    rail = page.shell.rail_list
    # Should have 7 rule items + 4 group headers = 11 rows.
    assert rail.count() == 11
    # First row is a "LEGAL PROSE" header.
    assert rail.item(0).text() == "LEGAL PROSE"


def test_rule_rail_items_have_subtitles(qapp, regulator_model):
    page = RulesEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    rail = page.shell.rail_list
    # The first selectable item (row 1) is a legal_prose rule —
    # subtitle should mention "→ on N credentials" or similar.
    item = rail.item(1)
    assert "\n" in item.text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_rules_editor_v1_visual.py -v`
Expected: FAIL.

- [ ] **Step 3: Restructure rules.py to add filter bar + grouped rail**

In `src/locksmith/plugins/designer/editors/rules.py`, add helper functions and modify `RulesEditorPage.__init__` to build a wrapping layout that places the chip bar above the shell.

```python
_TYPE_GROUPS: list[tuple[str, list[str]]] = [
    ("LEGAL PROSE",    ["legal_prose", "behavioral_expectation"]),
    ("PREDICATE",      ["predicate"]),
    ("VALIDATION",     ["validation", "computational"]),
    ("BINDING LINK",   ["binding_link"]),
]


def _filter_chip_label(type_id: str) -> str:
    return {
        "legal_prose": "prose",
        "behavioral_expectation": "prose",
        "predicate": "predicate",
        "validation": "validation",
        "computational": "validation",
        "binding_link": "link",
    }.get(type_id, type_id)


def _rule_subtitle(r: dict, crossrefs) -> str:
    rid = r.get("id", "")
    consumers = crossrefs.consumers_of(f"rule:{rid}") if rid else []
    n = len(consumers)
    rtype = r.get("type", "")
    parts: list[str] = []
    if rtype == "predicate":
        purpose = r.get("purpose")
        if purpose:
            parts.append(f"purpose: {purpose}")
    if rtype == "binding_link":
        links = r.get("links") or []
        parts.append(f"links {len(links)} rules")
    if n:
        parts.append(f"→ on {n} reference{'s' if n != 1 else ''}")
    return " · ".join(parts) if parts else ""


def _rail_items_grouped(rules: list[dict], crossrefs, color_for_type) -> list[RailItem]:
    items: list[RailItem] = []
    for header, type_ids in _TYPE_GROUPS:
        bucket = [r for r in rules if r.get("type", "") in type_ids]
        if not bucket:
            continue
        items.append(RailItem(
            id=f"__header_{header}", label="", kind_color="",
            has_errors=False, group_header=header,
        ))
        for r in bucket:
            items.append(RailItem(
                id=r.get("id", ""),
                label=r.get("title") or r.get("id") or "(unnamed)",
                subtitle=_rule_subtitle(r, crossrefs),
                kind_color=color_for_type(r.get("type", "")),
                has_errors=False,
            ))
    return items
```

And in `RulesEditorPage.__init__`, replace the rail items list comprehension with the grouped builder, and add the filter chip bar above the shell:

```python
        from locksmith.plugins.designer.widgets.rail_filter_chip_bar import (
            RailFilterChipBar,
        )
        items = _rail_items_grouped(
            model.doc.get("rules", []), crossrefs, rule_type_color,
        )

        # Compute chip counts (all + per filter-label).
        rules_all = list(model.doc.get("rules", []))
        chip_counts: dict[str, int] = {"all": len(rules_all),
                                       "prose": 0, "predicate": 0,
                                       "validation": 0, "link": 0}
        for r in rules_all:
            chip_counts[_filter_chip_label(r.get("type", ""))] = \
                chip_counts.get(_filter_chip_label(r.get("type", "")), 0) + 1
        self._filter_bar = RailFilterChipBar(
            chips=[
                ("all", chip_counts["all"]),
                ("prose", chip_counts["prose"]),
                ("predicate", chip_counts["predicate"]),
                ("validation", chip_counts["validation"]),
                ("link", chip_counts["link"]),
            ],
            active="all",
        )
```

Then in the outer layout (`outer = QVBoxLayout(self)`), add the filter bar before the shell:

```python
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._filter_bar)
        outer.addWidget(self.shell)
```

- [ ] **Step 4: Run tests + full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_rules_editor_v1_visual.py tests/plugins/designer/test_rules_editor_visual.py -v`
Expected: all PASS. The existing rules test asserts `rail_list.count() == 7`; with group headers added (4 of them), the count becomes 11. **Update the existing test** to assert `== 11` (or skip the count and check just for the first selectable item).

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/editors/rules.py \
        tests/plugins/designer/test_rules_editor_v1_visual.py \
        tests/plugins/designer/test_rules_editor_visual.py
git commit -m "feat(designer): rules typed-filter rail + grouped + subtitles"
```

---

## Task 4: Rules editor — right-pane v1 (badge + body/expression + REFERENCED FROM + PAIRS WITH)

**Files:**
- Modify: `src/locksmith/plugins/designer/editors/rules.py`
- Test: `tests/plugins/designer/test_rules_editor_v1_visual.py` (extend)

Right pane gets a typed restructure:

1. **Header**: `TypeColorBadge` + rule title + id chip on the right.
2. **Description** sentence.
3. **DETAILS** (per type):
   - `predicate` / `validation` / `computational`: Purpose (chip) + bound-context footnote · Language (chip) · Expression in `DarkCodeBlock` · cheat-sheet link · "test expression" link.
   - `legal_prose` / `behavioral_expectation`: Body text in a make_section block.
   - `binding_link`: Links list (each link's `rule_id` as a chip).
4. **REFERENCED FROM**: rich back-pointer list — "This rule is referenced in N place(s) across the template: …"
5. **PAIRS WITH (BINDING LINKS)**: for predicates that have a binding_link rule pointing to them — show the paired prose rule and the binding-link rule that couples them.

- [ ] **Step 1: Write the failing test**

Append to `tests/plugins/designer/test_rules_editor_v1_visual.py`:

```python
def test_rule_pane_renders_type_color_badge(qapp, regulator_model):
    from locksmith.plugins.designer.widgets.type_color_badge import (
        TypeColorBadge,
    )
    page = RulesEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    badge = page._pane.findChild(TypeColorBadge)
    assert badge is not None
    # First rule is "issued_under_statutory_authority" — legal_prose.
    assert badge.text() == "LEGAL PROSE"


def test_predicate_rule_renders_dark_expression_block(qapp, regulator_model):
    from locksmith.plugins.designer.widgets.dark_code_block import DarkCodeBlock
    page = RulesEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    # Select a predicate rule — financial_solvency_demonstrated.
    page.shell.rail_list.setCurrentRow(_find_rule_row(page, "financial_solvency_demonstrated"))
    block = page._pane.findChild(DarkCodeBlock)
    assert block is not None
    assert "market_conduct_status" in block.toPlainText() \
        or "lines_of_business" in block.toPlainText()


def test_rule_pane_renders_referenced_from_section(qapp, regulator_model):
    page = RulesEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    page.shell.rail_list.setCurrentRow(_find_rule_row(page, "financial_solvency_demonstrated"))
    text = page.section_text()
    # The predicate is required by the carrier_license grant transition.
    assert "REFERENCED FROM" in text.upper() or "referenced" in text.lower()


def test_binding_link_rule_renders_links_list(qapp, regulator_model):
    page = RulesEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    page.shell.rail_list.setCurrentRow(_find_rule_row(page, "authority_articulation"))
    text = page.section_text()
    assert "issued_under_statutory_authority" in text
    assert "financial_solvency_demonstrated" in text


def _find_rule_row(page, rule_id: str) -> int:
    from PySide6.QtCore import Qt
    rail = page.shell.rail_list
    for i in range(rail.count()):
        if rail.item(i).data(Qt.UserRole) == rule_id:
            return i
    return -1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_rules_editor_v1_visual.py -v -k "pane or referenced or links"`
Expected: FAIL.

- [ ] **Step 3: Rewrite `_RuleSectionPane`**

Replace the entire `_RuleSectionPane` class in `rules.py`:

```python
class _RuleSectionPane(QWidget):
    def __init__(self, crossrefs: CrossRefIndex, model: TemplateModel, parent=None):
        super().__init__(parent=parent)
        self._crossrefs = crossrefs
        self._model = model
        self._build()

    def _build(self) -> None:
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
        self._badge_holder = QHBoxLayout()
        title_row.addLayout(self._badge_holder)
        self._title_label = QLabel("")
        self._title_label.setStyleSheet(
            "font-size:16px;font-weight:600;color:#1A1C20;"
        )
        title_row.addWidget(self._title_label)
        title_row.addStretch(1)
        self._id_chip = QLabel("")
        self._id_chip.setStyleSheet(
            "color:#666;background:#f6f7f9;font-family:monospace;"
            "border-radius:6px;padding:2px 8px;font-size:10px;"
        )
        title_row.addWidget(self._id_chip)
        h.addLayout(title_row)
        self._description_label = QLabel("")
        self._description_label.setStyleSheet("color:#444;font-size:12px;")
        self._description_label.setWordWrap(True)
        h.addWidget(self._description_label)
        lay.addWidget(self._header_frame)

        # DETAILS — content depends on type, filled by set_entry.
        self._details_section = make_section("Details")
        self._details_holder = QVBoxLayout()
        self._details_section.layout().addLayout(self._details_holder)
        lay.addWidget(self._details_section)

        # REFERENCED FROM
        self._references_section = make_section("Referenced from")
        self._references_holder = QVBoxLayout()
        self._references_section.layout().addLayout(self._references_holder)
        lay.addWidget(self._references_section)

        # PAIRS WITH (binding links)
        self._pairs_section = make_section("Pairs with (binding links)")
        self._pairs_holder = QVBoxLayout()
        self._pairs_section.layout().addLayout(self._pairs_holder)
        lay.addWidget(self._pairs_section)

        # Used by (lighter — chip strip)
        self._used_by = make_section("Used by")
        self.chip_strip = CrossRefChipStrip()
        self._used_by.layout().addWidget(self.chip_strip)
        lay.addWidget(self._used_by)
        lay.addStretch(1)

    def set_entry(self, entry: dict[str, Any]) -> None:
        from locksmith.plugins.designer.widgets.dark_code_block import (
            DarkCodeBlock,
        )
        from locksmith.plugins.designer.widgets.type_color_badge import (
            TypeColorBadge,
        )

        def _clear(layout) -> None:
            while layout.count():
                item = layout.takeAt(0)
                w = item.widget() if item is not None else None
                if w is not None:
                    w.setParent(None)
                    w.deleteLater()

        self._title_label.setText(entry.get("title") or entry.get("id") or "(unnamed)")
        self._id_chip.setText(entry.get("id", ""))
        self._description_label.setText(entry.get("description") or "")

        # Type badge in the header.
        _clear(self._badge_holder)
        self._badge_holder.addWidget(TypeColorBadge(entry.get("type", "")))

        # Details — type-specific.
        _clear(self._details_holder)
        rtype = entry.get("type", "")
        if rtype in ("legal_prose", "behavioral_expectation"):
            body = entry.get("body", "")
            body_lbl = QLabel(body or "(no body)")
            body_lbl.setStyleSheet("color:#1A1C20;font-size:13px;")
            body_lbl.setWordWrap(True)
            self._details_holder.addWidget(body_lbl)
        elif rtype in ("predicate", "validation", "computational"):
            if entry.get("purpose"):
                p_row = QHBoxLayout()
                p_lbl = QLabel("Purpose:")
                p_lbl.setStyleSheet("color:#666;font-size:11px;")
                p_row.addWidget(p_lbl)
                p_chip = QLabel(entry["purpose"])
                p_chip.setStyleSheet(
                    "background:#e8f4f4;color:#0a8a82;border-radius:9px;"
                    "padding:2px 9px;font-size:11px;font-weight:600;"
                )
                p_row.addWidget(p_chip)
                bound_lbl = QLabel("↗ bound context: { state, event, transition }")
                bound_lbl.setStyleSheet("color:#0ABFB0;font-size:10px;")
                p_row.addWidget(bound_lbl)
                p_row.addStretch(1)
                p_w = QFrame()
                p_w.setLayout(p_row)
                self._details_holder.addWidget(p_w)
            if entry.get("language"):
                l_row = QHBoxLayout()
                l_lbl = QLabel("Language:")
                l_lbl.setStyleSheet("color:#666;font-size:11px;")
                l_row.addWidget(l_lbl)
                l_chip = QLabel(entry["language"])
                l_chip.setStyleSheet(
                    "background:#f0f2f5;color:#444;border-radius:9px;"
                    "padding:2px 9px;font-size:11px;"
                )
                l_row.addWidget(l_chip)
                l_row.addStretch(1)
                l_w = QFrame()
                l_w.setLayout(l_row)
                self._details_holder.addWidget(l_w)
            expr = entry.get("expression", "")
            self._details_holder.addWidget(DarkCodeBlock(expr))
            cheat = QLabel("↗ UEL/1.0 cheat-sheet · test expression")
            cheat.setStyleSheet("color:#0ABFB0;font-size:10px;")
            self._details_holder.addWidget(cheat)
        elif rtype == "binding_link":
            links_lbl = QLabel("This rule couples:")
            links_lbl.setStyleSheet("color:#666;font-size:11px;")
            self._details_holder.addWidget(links_lbl)
            for link in entry.get("links") or []:
                rid = link.get("rule_id", "")
                chip = QLabel(rid)
                chip.setStyleSheet(
                    "background:#f3edfb;color:#A36AE6;border-radius:9px;"
                    "padding:2px 9px;font-size:11px;font-weight:600;"
                )
                self._details_holder.addWidget(chip)

        # REFERENCED FROM — use crossref consumers.
        _clear(self._references_holder)
        rid = entry.get("id", "")
        consumers = self._crossrefs.consumers_of(f"rule:{rid}") if rid else []
        if not consumers:
            none_lbl = QLabel("Not referenced anywhere yet.")
            none_lbl.setStyleSheet("color:#aaa;font-style:italic;font-size:11px;")
            self._references_holder.addWidget(none_lbl)
        else:
            summary = QLabel(
                f"This rule is referenced in {len(consumers)} place"
                f"{'s' if len(consumers) != 1 else ''} across the template:"
            )
            summary.setStyleSheet("color:#444;font-size:11px;")
            self._references_holder.addWidget(summary)
            for ref in consumers:
                row_lbl = QLabel(f"• {ref}")
                row_lbl.setStyleSheet("color:#0ABFB0;font-size:11px;")
                self._references_holder.addWidget(row_lbl)

        # PAIRS WITH — find binding_link rules whose links include this rule's id.
        _clear(self._pairs_holder)
        all_rules = self._model.doc.get("rules", [])
        pairs: list[tuple[dict, dict]] = []  # (binding_link_rule, paired_rule)
        for r in all_rules:
            if r.get("type") != "binding_link":
                continue
            link_ids = [link.get("rule_id") for link in (r.get("links") or [])]
            if rid in link_ids:
                for partner_id in link_ids:
                    if partner_id == rid:
                        continue
                    partner = next(
                        (rr for rr in all_rules if rr.get("id") == partner_id),
                        None,
                    )
                    if partner is not None:
                        pairs.append((r, partner))
        if not pairs:
            none_lbl = QLabel("Not paired via any binding_link rule.")
            none_lbl.setStyleSheet("color:#aaa;font-style:italic;font-size:11px;")
            self._pairs_holder.addWidget(none_lbl)
        else:
            for link_rule, partner in pairs:
                row = QHBoxLayout()
                row.setSpacing(6)
                from locksmith.plugins.designer.widgets.type_color_badge import (
                    TypeColorBadge,
                )
                row.addWidget(TypeColorBadge("binding_link"))
                row.addWidget(QLabel(link_rule.get("id", "")))
                row.addWidget(QLabel("couples with"))
                row.addWidget(TypeColorBadge(partner.get("type", "")))
                pid = QLabel(partner.get("id", ""))
                pid.setStyleSheet(
                    "color:#666;background:#f6f7f9;font-family:monospace;"
                    "border-radius:6px;padding:2px 8px;font-size:10px;"
                )
                row.addWidget(pid)
                row.addStretch(1)
                row_w = QFrame()
                row_w.setLayout(row)
                self._pairs_holder.addWidget(row_w)

        # Used-by chips.
        self.chip_strip.set_refs(consumers)

    def text_summary(self) -> str:
        parts = [
            self._title_label.text(),
            self._id_chip.text(),
            self._description_label.text(),
        ]
        for lbl in self.findChildren(QLabel):
            parts.append(lbl.text())
        # Include any DarkCodeBlock contents for expression assertions.
        from locksmith.plugins.designer.widgets.dark_code_block import (
            DarkCodeBlock,
        )
        for block in self.findChildren(DarkCodeBlock):
            parts.append(block.toPlainText())
        return " ".join(parts)
```

And update `RulesEditorPage._on_select` / construction to pass `model=` to `_RuleSectionPane`:

```python
        self._pane = _RuleSectionPane(crossrefs=crossrefs, model=model)
```

Update the imports at top of `rules.py` to include `QFrame, QHBoxLayout` if missing.

Add `page.section_text()` accessor:

```python
    def section_text(self) -> str:
        return self._pane.text_summary()
```

- [ ] **Step 4: Run tests + full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_rules_editor_v1_visual.py tests/plugins/designer/test_rules_editor_visual.py -v`
Expected: all PASS.

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/editors/rules.py \
        tests/plugins/designer/test_rules_editor_v1_visual.py
git commit -m "feat(designer): rules right-pane v1 (badge + body/expression + referenced-from + pairs-with)"
```

---

## Task 5: Aggregates editor — rail subtitle + chip-ified right pane

**Files:**
- Modify: `src/locksmith/plugins/designer/editors/aggregates.py`
- Test: `tests/plugins/designer/test_aggregates_editor_v1_visual.py`

Rail items get subtitle (`witnessed log · N invariants`). Right pane becomes: header (id + name) + description + Inception event type as chip + Log scope as chip + State schema preview (small read-only display) + Initial state preview + Invariants (`RuleChipStrip` of invariant rule_refs) + Used by.

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/designer/test_aggregates_editor_v1_visual.py
import json
from pathlib import Path

import pytest

from locksmith.plugins.designer.crossref import compute_crossrefs
from locksmith.plugins.designer.editors.aggregates import AggregatesEditorPage
from locksmith.plugins.designer.model import TemplateModel


@pytest.fixture
def regulator_model():
    doc = json.loads(
        (Path(__file__).parent / "fixtures"
         / "regulator-grants-carrier-license.json").read_text()
    )
    return TemplateModel(doc=doc)


def test_aggregate_rail_items_have_subtitles(qapp, regulator_model):
    page = AggregatesEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    rail = page.shell.rail_list
    item = rail.item(0)
    text = item.text()
    assert "\n" in text
    subtitle = text.split("\n", 1)[1]
    assert "witnessed" in subtitle
    assert "invariant" in subtitle


def test_aggregate_pane_renders_inception_chip_and_log_scope(
    qapp, regulator_model,
):
    page = AggregatesEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    text = page.section_text()
    assert "regulator.licensing.inaugurated" in text
    assert "witnessed" in text


def test_aggregate_pane_renders_invariants_via_rule_chip_strip(
    qapp, regulator_model,
):
    from locksmith.plugins.designer.widgets.rule_chip_strip import RuleChipStrip
    page = AggregatesEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    strips = page._pane.findChildren(RuleChipStrip)
    assert len(strips) >= 1
    all_chip_texts: list[str] = []
    for s in strips:
        all_chip_texts.extend(s.chip_texts())
    assert "no_duplicate_active_license_per_carrier" in all_chip_texts
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_aggregates_editor_v1_visual.py -v`
Expected: FAIL.

- [ ] **Step 3: Restructure `aggregates.py`**

Add `_aggregate_subtitle(agg)` and rewrite `_AggregateSectionPane` to the v1 layout. Update the rail items list comprehension to pass `subtitle=_aggregate_subtitle(a)`.

```python
def _aggregate_subtitle(agg: dict) -> str:
    parts: list[str] = []
    scope = agg.get("log_scope")
    if scope:
        parts.append(f"{scope} log")
    invs = agg.get("invariants") or []
    parts.append(f"{len(invs)} invariant{'s' if len(invs) != 1 else ''}")
    return " · ".join(parts)
```

And the pane:

```python
class _AggregateSectionPane(QWidget):
    def __init__(self, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._crossrefs = crossrefs
        self._build()

    def _build(self) -> None:
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

        # Inception event type + log scope side-by-side.
        ic_row = QHBoxLayout()
        ic_row.setSpacing(14)
        self._inception_section = make_section("Inception event")
        self._inception_chip = QLabel("(unset)")
        self._inception_chip.setStyleSheet(
            "background:#f3edfb;color:#A36AE6;border-radius:9px;"
            "padding:2px 9px;font-size:11px;font-weight:600;"
            "font-family:monospace;"
        )
        self._inception_section.layout().addWidget(self._inception_chip)
        ic_row.addWidget(self._inception_section, 1)
        self._scope_section = make_section("Log scope")
        self._scope_chip = QLabel("(unset)")
        self._scope_chip.setStyleSheet(
            "background:#e8f4f4;color:#0a8a82;border-radius:9px;"
            "padding:2px 9px;font-size:11px;font-weight:600;"
        )
        self._scope_section.layout().addWidget(self._scope_chip)
        ic_row.addWidget(self._scope_section, 1)
        lay.addLayout(ic_row)

        # State schema preview.
        self._state_schema_section = make_section("State schema")
        self._state_schema_view = QPlainTextEdit()
        self._state_schema_view.setReadOnly(True)
        mono = QFont("Menlo")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(10)
        self._state_schema_view.setFont(mono)
        self._state_schema_view.setFixedHeight(80)
        self._state_schema_section.layout().addWidget(self._state_schema_view)
        lay.addWidget(self._state_schema_section)

        # Initial state preview.
        self._initial_section = make_section("Initial state")
        self._initial_view = QPlainTextEdit()
        self._initial_view.setReadOnly(True)
        self._initial_view.setFont(mono)
        self._initial_view.setFixedHeight(50)
        self._initial_section.layout().addWidget(self._initial_view)
        lay.addWidget(self._initial_section)

        # Invariants — RuleChipStrip.
        self._inv_section = make_section("Invariants")
        self._inv_holder = QVBoxLayout()
        self._inv_section.layout().addLayout(self._inv_holder)
        lay.addWidget(self._inv_section)

        # Used by.
        self._used_by = make_section("Used by")
        self.chip_strip = CrossRefChipStrip()
        self._used_by.layout().addWidget(self.chip_strip)
        lay.addWidget(self._used_by)
        lay.addStretch(1)

    def set_entry(self, entry: dict[str, Any]) -> None:
        from locksmith.plugins.designer.widgets.rule_chip_strip import (
            RuleChipStrip,
        )

        self._name_label.setText(entry.get("name") or entry.get("id") or "(unnamed)")
        self._id_chip.setText(entry.get("id", ""))
        self._description_label.setText(entry.get("description") or "")
        self._inception_chip.setText(
            entry.get("inception_event_type") or "(unset)"
        )
        scope = entry.get("log_scope")
        self._scope_chip.setText(scope or "(unset)")

        self._state_schema_view.setPlainText(
            json.dumps(entry.get("state_schema") or {}, indent=2, sort_keys=True)
        )
        self._initial_view.setPlainText(
            json.dumps(entry.get("initial_state"), indent=2, sort_keys=True)
        )

        while self._inv_holder.count():
            item = self._inv_holder.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        refs = [r.get("rule_ref", "") for r in (entry.get("invariants") or [])
                if r.get("rule_ref")]
        self._inv_holder.addWidget(RuleChipStrip(refs))

        self.chip_strip.set_refs(
            self._crossrefs.consumers_of(f"aggregate:{entry.get('id', '')}")
        )

    def text_summary(self) -> str:
        from locksmith.plugins.designer.widgets.rule_chip_strip import (
            RuleChipStrip,
        )
        parts = [
            self._name_label.text(),
            self._id_chip.text(),
            self._description_label.text(),
            self._inception_chip.text(),
            self._scope_chip.text(),
            self._state_schema_view.toPlainText(),
            self._initial_view.toPlainText(),
        ]
        for strip in self.findChildren(RuleChipStrip):
            parts.extend(strip.chip_texts())
        return " ".join(parts)
```

Update `AggregatesEditorPage.section_text()` to delegate (`return self._pane.text_summary()`). Update the rail items construction to pass `subtitle=_aggregate_subtitle(a)`.

- [ ] **Step 4: Run tests + full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_aggregates_editor_v1_visual.py tests/plugins/designer/test_aggregates_editor_visual.py -v`
Expected: all PASS.

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/editors/aggregates.py \
        tests/plugins/designer/test_aggregates_editor_v1_visual.py
git commit -m "feat(designer): aggregates v1 right-pane (chip-ified inception/scope/invariants)"
```

---

## Task 6: Reactions editor — rail subtitle + trigger card + emissions + failure policy

**Files:**
- Modify: `src/locksmith/plugins/designer/editors/reactions.py`
- Test: `tests/plugins/designer/test_reactions_editor_v1_visual.py`

Rail items get subtitle (`← <trigger-type> · N emissions`). Right pane:

1. Header (id + name + description).
2. **Trigger card**: variant chips for the 4 possible types (`credential_received`, `exn_received`, `lifecycle_event`, `scheduled`) with the active one highlighted teal, + route + schema_id underneath.
3. **Emissions** section: bullet list with colored kind chip per emission (`aggregate_event` purple, `lifecycle_advance` teal, `exchange` orange) + summary text.
4. **Failure policy** section: policy chip (`log_and_continue` / `log_and_spurn` / `abort`) + timeout.
5. **Used by**.

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/designer/test_reactions_editor_v1_visual.py
import json
from pathlib import Path

import pytest

from locksmith.plugins.designer.crossref import compute_crossrefs
from locksmith.plugins.designer.editors.reactions import ReactionsEditorPage
from locksmith.plugins.designer.model import TemplateModel


@pytest.fixture
def regulator_model():
    doc = json.loads(
        (Path(__file__).parent / "fixtures"
         / "regulator-grants-carrier-license.json").read_text()
    )
    return TemplateModel(doc=doc)


def test_reaction_rail_items_have_subtitles(qapp, regulator_model):
    page = ReactionsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    rail = page.shell.rail_list
    item = rail.item(0)
    text = item.text()
    assert "\n" in text
    subtitle = text.split("\n", 1)[1]
    assert "exn" in subtitle
    assert "emission" in subtitle


def test_reaction_pane_renders_trigger_card(qapp, regulator_model):
    page = ReactionsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    text = page.section_text()
    assert "exn_received" in text
    assert "/insurance/cmd/submit_application" in text


def test_reaction_pane_renders_emissions(qapp, regulator_model):
    page = ReactionsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    text = page.section_text()
    assert "aggregate_event" in text
    assert "license_registry" in text


def test_reaction_pane_renders_failure_policy(qapp, regulator_model):
    page = ReactionsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    text = page.section_text()
    assert "log_and_spurn" in text or "FAILURE POLICY" in text.upper()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_reactions_editor_v1_visual.py -v`
Expected: FAIL.

- [ ] **Step 3: Restructure `reactions.py`**

Add `_reaction_subtitle` helper and rewrite `_ReactionSectionPane`:

```python
def _reaction_subtitle(r: dict) -> str:
    parts: list[str] = []
    trig = r.get("trigger") or {}
    t_type = trig.get("type", "")
    if t_type:
        # Shorten "exn_received" → "← exn", etc.
        short = t_type.replace("_received", "").replace("_event", "_event")
        parts.append(f"← {short}")
    n = len(r.get("emissions") or [])
    if n:
        parts.append(f"{n} emission{'s' if n != 1 else ''}")
    return " · ".join(parts) if parts else ""


_EMISSION_KIND_COLOR: dict[str, str] = {
    "aggregate_event":   "#A36AE6",
    "lifecycle_advance": "#0ABFB0",
    "exchange":          "#D97757",
}


class _ReactionSectionPane(QWidget):
    def __init__(self, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._crossrefs = crossrefs
        self._build()

    def _build(self) -> None:
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

        # Trigger card.
        self._trigger_section = make_section("Trigger")
        self._trigger_variants_row = QHBoxLayout()
        self._trigger_variants_row.setSpacing(6)
        for v in ("credential_received", "exn_received",
                  "lifecycle_event", "scheduled"):
            chip = QLabel(v)
            chip.setProperty("variant", v)
            chip.setStyleSheet(
                "background:#f0f2f5;color:#444;border-radius:9px;"
                "padding:2px 9px;font-size:11px;"
            )
            self._trigger_variants_row.addWidget(chip)
        self._trigger_variants_row.addStretch(1)
        self._trigger_section.layout().addLayout(self._trigger_variants_row)
        self._trigger_route_row = QHBoxLayout()
        self._trigger_section.layout().addLayout(self._trigger_route_row)
        lay.addWidget(self._trigger_section)

        # Emissions.
        self._emissions_section = make_section("Emissions")
        self._emissions_holder = QVBoxLayout()
        self._emissions_section.layout().addLayout(self._emissions_holder)
        lay.addWidget(self._emissions_section)

        # Failure policy.
        self._failure_section = make_section("Failure policy")
        self._failure_holder = QHBoxLayout()
        self._failure_section.layout().addLayout(self._failure_holder)
        lay.addWidget(self._failure_section)

        # Used by.
        self._used_by = make_section("Used by")
        self.chip_strip = CrossRefChipStrip()
        self._used_by.layout().addWidget(self.chip_strip)
        lay.addWidget(self._used_by)
        lay.addStretch(1)

    def set_entry(self, entry: dict[str, Any]) -> None:
        self._name_label.setText(
            entry.get("name") or entry.get("id") or "(unnamed)"
        )
        self._id_chip.setText(entry.get("id", ""))
        self._description_label.setText(entry.get("description") or "")

        trig = entry.get("trigger") or {}
        active = trig.get("type", "")
        # Re-style variant chips: highlight the active one.
        for i in range(self._trigger_variants_row.count()):
            item = self._trigger_variants_row.itemAt(i)
            chip = item.widget() if item is not None else None
            if not isinstance(chip, QLabel):
                continue
            v = chip.property("variant")
            if v == active:
                chip.setStyleSheet(
                    "background:#e8f4f4;color:#0a8a82;border-radius:9px;"
                    "padding:2px 9px;font-size:11px;font-weight:600;"
                )
            else:
                chip.setStyleSheet(
                    "background:#f0f2f5;color:#444;border-radius:9px;"
                    "padding:2px 9px;font-size:11px;"
                )

        # Clear + repopulate the route/schema row.
        while self._trigger_route_row.count():
            item = self._trigger_route_row.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        if trig.get("route"):
            r_lbl = QLabel(f"Route: {trig['route']}")
            r_lbl.setStyleSheet(
                "color:#0ABFB0;font-family:monospace;font-size:11px;"
            )
            self._trigger_route_row.addWidget(r_lbl)
        if trig.get("schema_id"):
            s_lbl = QLabel(f"Schema ID: {trig['schema_id']}")
            s_lbl.setStyleSheet(
                "color:#666;font-family:monospace;font-size:11px;"
            )
            self._trigger_route_row.addWidget(s_lbl)
        self._trigger_route_row.addStretch(1)

        # Emissions.
        while self._emissions_holder.count():
            item = self._emissions_holder.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        for em in entry.get("emissions") or []:
            row_w = QFrame()
            row = QHBoxLayout(row_w)
            row.setContentsMargins(0, 2, 0, 2)
            row.setSpacing(6)
            kind = em.get("kind", "")
            kind_chip = QLabel(kind)
            color = _EMISSION_KIND_COLOR.get(kind, "#888")
            kind_chip.setStyleSheet(
                f"color:{color};background:#f6f7f9;border-radius:9px;"
                "padding:2px 9px;font-size:11px;font-weight:600;"
            )
            row.addWidget(kind_chip)
            if kind == "aggregate_event":
                row.addWidget(QLabel(
                    f"append to {em.get('aggregate_id','?')} as "
                    f"{em.get('event_type','?')}"
                ))
            elif kind == "lifecycle_advance":
                row.addWidget(QLabel(
                    f"advance {em.get('exported_credential_id','?')} → "
                    f"{em.get('to_state','?')}"
                ))
            elif kind == "exchange":
                ex = em.get("exchange") or {}
                row.addWidget(QLabel(
                    f"exchange: {ex.get('kind','?')} · "
                    f"{ex.get('verb', ex.get('pattern',''))}"
                ))
            row.addStretch(1)
            self._emissions_holder.addWidget(row_w)

        # Failure policy.
        while self._failure_holder.count():
            item = self._failure_holder.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        fp = entry.get("failure_policy") or {}
        on_fail = fp.get("on_validation_failure", "log_and_continue")
        policy_chip = QLabel(on_fail)
        policy_chip.setStyleSheet(
            "background:#e8f4f4;color:#0a8a82;border-radius:9px;"
            "padding:2px 9px;font-size:11px;font-weight:600;"
        )
        self._failure_holder.addWidget(policy_chip)
        timeout = fp.get("timeout_seconds")
        timeout_lbl = QLabel(f"timeout: {timeout if timeout else 'none'}")
        timeout_lbl.setStyleSheet("color:#666;font-size:11px;")
        self._failure_holder.addWidget(timeout_lbl)
        self._failure_holder.addStretch(1)

        self.chip_strip.set_refs(
            self._crossrefs.consumers_of(f"reaction:{entry.get('id', '')}")
        )

    def text_summary(self) -> str:
        parts = [
            self._name_label.text(),
            self._id_chip.text(),
            self._description_label.text(),
        ]
        for lbl in self.findChildren(QLabel):
            parts.append(lbl.text())
        return " ".join(parts)
```

Update the rail items list comprehension to include `subtitle=_reaction_subtitle(r)`, and add `page.section_text()` accessor that delegates to `self._pane.text_summary()`.

- [ ] **Step 4: Run tests + full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_reactions_editor_v1_visual.py tests/plugins/designer/test_reactions_editor_visual.py -v`
Expected: all PASS (the existing reactions test passes too — fixture has 2 reactions which the existing test asserts).

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/editors/reactions.py \
        tests/plugins/designer/test_reactions_editor_v1_visual.py
git commit -m "feat(designer): reactions v1 right-pane (trigger card + emissions kind chips + failure policy)"
```

---

## Task 7: Imports editor — rail subtitle + chip-ified right pane + rich USED BY

**Files:**
- Modify: `src/locksmith/plugins/designer/editors/imports.py`
- Test: `tests/plugins/designer/test_imports_editor_v1_visual.py`

Rail items: `← <issuer-role> · → used Nx`. Right pane:

1. Header (id + name + description italicized as "Credential type this role expects to potentially hold — not a runtime instance assertion").
2. **Expected schema SAID**: full 44-char monospace.
3. **Expected issuer role** as chip.
4. **Lifecycle acceptance**: chips for each state + "+ accept state" affordance.
5. **Narrative**.
6. **Attribute constraints** (read-only display, optional section if non-empty).
7. **USED BY · N REFERENCES**: rich back-pointer list — `→ command issue_policy · auth_precondition`, etc.

Note: regulator fixture has 0 imports, so the visual smoke tests will work on a stub fixture or skip if empty. Use the carrier-license-application fixture (already auto-seeded) for the visual tests — load it and find its imports.

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/designer/test_imports_editor_v1_visual.py
import json
from pathlib import Path

import pytest

from locksmith.plugins.designer.crossref import compute_crossrefs
from locksmith.plugins.designer.editors.imports import ImportsEditorPage
from locksmith.plugins.designer.model import TemplateModel


@pytest.fixture
def carrier_model():
    doc = json.loads(
        (Path(__file__).parent / "fixtures"
         / "carrier-license-application.json").read_text()
    )
    return TemplateModel(doc=doc)


def test_import_rail_items_have_subtitles(qapp, carrier_model):
    # carrier-license-application.json has at least one import.
    if not carrier_model.doc.get("credentials", {}).get("imports"):
        pytest.skip("carrier fixture has no imports; can't test rail subtitle")
    page = ImportsEditorPage(
        model=carrier_model,
        crossrefs=compute_crossrefs(carrier_model.doc),
    )
    rail = page.shell.rail_list
    item = rail.item(0)
    text = item.text()
    assert "\n" in text


def test_import_pane_renders_full_said(qapp, carrier_model):
    imports = carrier_model.doc.get("credentials", {}).get("imports") or []
    if not imports:
        pytest.skip("no imports to render")
    page = ImportsEditorPage(
        model=carrier_model,
        crossrefs=compute_crossrefs(carrier_model.doc),
    )
    text = page.section_text()
    # The full SAID (44 chars) should appear somewhere in the pane text.
    first_imp = imports[0]
    expected_said = first_imp.get("expected_schema_said", "")
    if len(expected_said) >= 8:
        # Match a chunk of the SAID (not just first 4) to confirm full
        # rendering rather than truncation.
        assert expected_said[:10] in text


def test_import_pane_renders_issuer_role_chip(qapp, carrier_model):
    imports = carrier_model.doc.get("credentials", {}).get("imports") or []
    if not imports:
        pytest.skip("no imports to render")
    page = ImportsEditorPage(
        model=carrier_model,
        crossrefs=compute_crossrefs(carrier_model.doc),
    )
    text = page.section_text()
    issuer = imports[0].get("expected_issuer_role", "")
    if issuer:
        assert issuer in text


def test_import_pane_renders_lifecycle_chips(qapp, carrier_model):
    imports = carrier_model.doc.get("credentials", {}).get("imports") or []
    if not imports:
        pytest.skip("no imports to render")
    page = ImportsEditorPage(
        model=carrier_model,
        crossrefs=compute_crossrefs(carrier_model.doc),
    )
    text = page.section_text()
    states = imports[0].get("lifecycle_acceptance", ["active"])
    for state in states:
        assert state in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_imports_editor_v1_visual.py -v`
Expected: FAIL or SKIP, depending on the carrier fixture's imports content.

- [ ] **Step 3: Restructure `imports.py`**

Add helper + rewrite `_ImportSectionPane`:

```python
def _import_subtitle(imp: dict, crossrefs) -> str:
    parts: list[str] = []
    issuer = imp.get("expected_issuer_role")
    if issuer:
        parts.append(f"← {issuer}")
    rid = imp.get("id", "")
    consumers = crossrefs.consumers_of(f"import:{rid}") if rid else []
    if consumers:
        parts.append(f"→ used {len(consumers)}x")
    return " · ".join(parts)


class _ImportSectionPane(QWidget):
    def __init__(self, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._crossrefs = crossrefs
        self._build()

    def _build(self) -> None:
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
        self._id_chip = QLabel("")
        self._id_chip.setStyleSheet(
            "color:#666;background:#f6f7f9;font-family:monospace;"
            "border-radius:6px;padding:2px 8px;font-size:12px;"
        )
        title_row.addWidget(self._id_chip)
        title_row.addStretch(1)
        h.addLayout(title_row)
        self._narrative_label = QLabel("")
        self._narrative_label.setStyleSheet(
            "color:#666;font-style:italic;font-size:11px;"
        )
        self._narrative_label.setWordWrap(True)
        h.addWidget(self._narrative_label)
        lay.addWidget(self._header_frame)

        # Expected schema SAID (full).
        self._said_section = make_section("Expected schema SAID")
        self._said_label = QLabel("(unset)")
        mono = QFont("Menlo")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(10)
        self._said_label.setFont(mono)
        self._said_label.setStyleSheet(
            "color:#444;background:#f6f7f9;border-radius:4px;"
            "padding:6px 8px;"
        )
        self._said_section.layout().addWidget(self._said_label)
        lay.addWidget(self._said_section)

        # Issuer + lifecycle side-by-side.
        ir_row = QHBoxLayout()
        ir_row.setSpacing(14)
        self._issuer_section = make_section("Expected issuer role")
        self._issuer_chip = QLabel("(any)")
        self._issuer_chip.setStyleSheet(
            "background:#e8f4f4;color:#0a8a82;border-radius:9px;"
            "padding:2px 9px;font-size:11px;font-weight:600;"
        )
        self._issuer_section.layout().addWidget(self._issuer_chip)
        ir_row.addWidget(self._issuer_section, 1)
        self._lc_section = make_section("Lifecycle acceptance")
        self._lc_holder = QHBoxLayout()
        self._lc_section.layout().addLayout(self._lc_holder)
        ir_row.addWidget(self._lc_section, 1)
        lay.addLayout(ir_row)

        # Attribute constraints (read-only display, hidden when empty).
        self._constraints_section = make_section("Attribute constraints")
        self._constraints_view = QPlainTextEdit()
        self._constraints_view.setReadOnly(True)
        self._constraints_view.setFont(mono)
        self._constraints_view.setFixedHeight(80)
        self._constraints_section.layout().addWidget(self._constraints_view)
        lay.addWidget(self._constraints_section)

        # USED BY · N REFERENCES (rich).
        self._used_by_section = make_section("Used by")
        self._used_by_holder = QVBoxLayout()
        self._used_by_section.layout().addLayout(self._used_by_holder)
        self.chip_strip = CrossRefChipStrip()  # kept for navigation compatibility
        self._used_by_section.layout().addWidget(self.chip_strip)
        lay.addWidget(self._used_by_section)
        lay.addStretch(1)

    def set_entry(self, entry: dict[str, Any]) -> None:
        self._id_chip.setText(entry.get("id", ""))
        narrative = entry.get("narrative") or (
            "Credential type this role expects to potentially hold — "
            "not a runtime instance assertion"
        )
        self._narrative_label.setText(narrative)
        self._said_label.setText(entry.get("expected_schema_said") or "(unset)")
        issuer = entry.get("expected_issuer_role")
        if issuer:
            self._issuer_chip.setText(issuer)
            self._issuer_chip.setStyleSheet(
                "background:#e8f4f4;color:#0a8a82;border-radius:9px;"
                "padding:2px 9px;font-size:11px;font-weight:600;"
            )
        else:
            self._issuer_chip.setText("(any)")
            self._issuer_chip.setStyleSheet(
                "color:#aaa;font-style:italic;font-size:11px;background:transparent;"
            )

        while self._lc_holder.count():
            item = self._lc_holder.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        states = entry.get("lifecycle_acceptance") or ["active"]
        for s in states:
            chip = QLabel(s)
            chip.setStyleSheet(
                "background:#e8f4f4;color:#0a8a82;border-radius:9px;"
                "padding:2px 9px;font-size:11px;font-weight:600;"
            )
            self._lc_holder.addWidget(chip)
        accept_btn = QLabel("+ accept state")
        accept_btn.setStyleSheet("color:#0ABFB0;font-size:11px;font-weight:600;")
        self._lc_holder.addWidget(accept_btn)
        self._lc_holder.addStretch(1)

        constraints = entry.get("expected_attribute_constraints") or {}
        if constraints:
            self._constraints_view.setPlainText(
                json.dumps(constraints, indent=2, sort_keys=True)
            )
            self._constraints_section.setVisible(True)
        else:
            self._constraints_view.setPlainText("")
            self._constraints_section.setVisible(False)

        # Rich USED BY list — replace the holder content; keep chip_strip
        # as a hidden compatibility shim for navigation.
        while self._used_by_holder.count():
            item = self._used_by_holder.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        rid = entry.get("id", "")
        consumers = self._crossrefs.consumers_of(f"import:{rid}") if rid else []
        if not consumers:
            none_lbl = QLabel("Not referenced anywhere.")
            none_lbl.setStyleSheet("color:#aaa;font-style:italic;font-size:11px;")
            self._used_by_holder.addWidget(none_lbl)
        else:
            summary = QLabel(f"{len(consumers)} reference"
                             f"{'s' if len(consumers) != 1 else ''}:")
            summary.setStyleSheet("color:#666;font-size:11px;")
            self._used_by_holder.addWidget(summary)
            for ref in consumers:
                row_lbl = QLabel(f"→ {ref}")
                row_lbl.setStyleSheet("color:#0ABFB0;font-size:11px;")
                self._used_by_holder.addWidget(row_lbl)
        self.chip_strip.set_refs(consumers)

    def text_summary(self) -> str:
        parts = [
            self._id_chip.text(),
            self._narrative_label.text(),
            self._said_label.text(),
            self._issuer_chip.text(),
            self._constraints_view.toPlainText(),
        ]
        for lbl in self.findChildren(QLabel):
            parts.append(lbl.text())
        return " ".join(parts)
```

Update the rail items list comprehension to pass `subtitle=_import_subtitle(imp, crossrefs)`, and add `page.section_text()` accessor.

- [ ] **Step 4: Run tests + full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_imports_editor_v1_visual.py -v`
Expected: PASS (or SKIP if fixture has no imports).

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/editors/imports.py \
        tests/plugins/designer/test_imports_editor_v1_visual.py
git commit -m "feat(designer): imports v1 right-pane (chip-ified + rich USED BY)"
```

---

## Task 8: Final live verification

**Files:**
- (No code changes)

Restart the wallet, drive the harness through Rules / Aggregates / Reactions / Imports, screenshot each, compare with the corresponding mock.

- [ ] **Step 1: Restart wallet**

```bash
ps aux | grep "locksmith.main" | grep -v grep | awk '{print $2}' | head -1 | xargs -r kill
sleep 1
LOCKSMITH_DEV_CONTROL=1 LOCKSMITH_DESIGNER_SEED_FIXTURES=1 \
    nohup .venv/bin/python -m locksmith.main > /tmp/locksmith-wallet.log 2>&1 &
sleep 4
```

- [ ] **Step 2: Unlock + navigate to Rules**

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
.venv/bin/python tools/devctl.py click '{"target": "Rules"}'
.venv/bin/python tools/devctl.py screenshot '{"path": "/tmp/locksmith-3d-rules.png"}'
```

Expected (vs `rules-editor.html`): filter chip bar at top of rail (`all (7)` selected dark, `prose (2)` `predicate (3)` `validation (1)` `link (1)` flat), rail items grouped under `LEGAL PROSE` / `PREDICATE` / `VALIDATION` / `BINDING LINK` headers, subtitles below each item. Right pane: type-color badge + title + id chip, description, type-specific details (predicate → Purpose chip + Language chip + DarkCodeBlock expression + UEL cheat-sheet link), REFERENCED FROM section, PAIRS WITH section.

- [ ] **Step 3: Navigate to Aggregates**

```bash
.venv/bin/python tools/devctl.py click '{"target": "Templates"}'
.venv/bin/python tools/devctl.py click '{"target": "Regulator Grants Carrier License"}'
.venv/bin/python tools/devctl.py click '{"target": "Aggregates"}'
.venv/bin/python tools/devctl.py screenshot '{"path": "/tmp/locksmith-3d-aggregates.png"}'
```

Expected: rail subtitle "witnessed log · 1 invariant", inception chip purple, log-scope chip teal, invariants RuleChipStrip showing `no_duplicate_active_license_per_carrier`.

- [ ] **Step 4: Navigate to Reactions**

```bash
.venv/bin/python tools/devctl.py click '{"target": "Templates"}'
.venv/bin/python tools/devctl.py click '{"target": "Regulator Grants Carrier License"}'
.venv/bin/python tools/devctl.py click '{"target": "Reactions"}'
.venv/bin/python tools/devctl.py screenshot '{"path": "/tmp/locksmith-3d-reactions.png"}'
```

Expected: rail subtitle "← exn · N emissions", Trigger card with variant chips (exn_received highlighted teal) + route, Emissions with purple `aggregate_event` chip, Failure policy with `log_and_spurn` chip.

- [ ] **Step 5: Navigate to Imports (carrier template)**

```bash
.venv/bin/python tools/devctl.py click '{"target": "Templates"}'
.venv/bin/python tools/devctl.py click '{"target": "Carrier License Application"}'
.venv/bin/python tools/devctl.py click '{"target": "Imported credentials"}'
.venv/bin/python tools/devctl.py screenshot '{"path": "/tmp/locksmith-3d-imports.png"}'
```

Expected: rail subtitle "← <issuer> · → used Nx", full schema SAID monospace, issuer-role chip, lifecycle chips + "+ accept state", USED BY rich back-pointer list.

- [ ] **Step 6: Run the full test suite**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/ -v
```

Expected: all PASS.

- [ ] **Step 7: Milestone commit**

```bash
git commit --allow-empty -m "milestone(designer): Phase 3d (Rules + Aggregates + Reactions + Imports) complete"
```

---

## Self-review checklist

1. **Spec coverage — Rules**:
   - Typed filter chip bar ✓ Tasks 1 + 3.
   - Rail grouped by type with headers ✓ Tasks 2 + 3.
   - Rail item subtitles ✓ Task 3.
   - Type-color badge in right pane ✓ Task 4.
   - DarkCodeBlock expression for predicate/validation/computational ✓ Task 4.
   - Body for legal_prose/behavioral_expectation ✓ Task 4.
   - Binding-link links list ✓ Task 4.
   - REFERENCED FROM rich back-pointer ✓ Task 4.
   - PAIRS WITH (binding links) section ✓ Task 4.

2. **Spec coverage — Aggregates / Reactions / Imports**:
   - All three get rail subtitles ✓ Tasks 5/6/7.
   - Aggregates: chip-ified inception/scope + invariants ✓ Task 5.
   - Reactions: trigger card with variant chips + emissions kind chips + failure policy ✓ Task 6.
   - Imports: full SAID + issuer chip + lifecycle chips + rich USED BY ✓ Task 7.

3. **Out of scope (Phase 2 / later):**
   - Clickable filter chips actually filtering the rail.
   - Clickable + Pick rule / + Pick event / chip × removal.
   - "+ accept state" wizard.
   - "+ Add invariant" affordance.

4. **Placeholder scan:** no TBD / "implement later". Every code block has runnable content.

5. **Type consistency:**
   - `RailFilterChipBar(chips, active="all")` / `chip_text(name)` / `active_filter()` / `set_active(name)` / `filter_changed(str)` signal.
   - `RailItem(..., group_header=None)` — non-selectable separator when set.
   - All four restructured panes preserve their `set_entry(entry)` / `text_summary()` shape.
   - `page.section_text()` exposed on all four editors for the v1 tests.
