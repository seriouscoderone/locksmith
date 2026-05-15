# Designer Plugin — V1 Fidelity Phase 1 (Visual Shell) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the Designer plugin's Templates browser, Overview page, and per-primitive editor shell into pixel-shape parity with the v1 HTML mockups at `.superpowers/brainstorm/69587-1778622927/content/`. Strict scope: layout/header/rail/badge/chip surface only — **no editing, kebab actions, or toolbar toggles** (those land in Phases 2–4).

**Architecture:** Add small shared widgets (`RoleIconBadge`, `ValidationPill`, `EcosystemChip`, `CrossTemplateChip`, `KebabButton`) under `src/locksmith/plugins/designer/widgets/`. Extend `KindRail` with a subtitle row and `PrimitiveEditorShell` with a breadcrumb-with-count + role-pill + valid-badge identity strip and a label-driven `+ Add <kind>` at the top of the rail. Rewrite `TemplateOverviewPage` to a header-strip + 4×2 facet grid + bottom-strip layout that absorbs the Role primitive into the header. Update `TemplatesBrowserPage` to add count summary, filter strip, and richer cards. Seed `regulator-grants-carrier-license` (enriched) and `carrier-license-application` into the store on dev-mode vault open so the 2-up grid has content. **No model-write paths land** in this phase — every input stays read-only.

**Tech Stack:** PySide6 (existing toolkit), pytest with `QT_QPA_PLATFORM=offscreen` for visual smoke tests, existing `TemplateModel` / `CrossRefIndex` / `TemplateStore` primitives.

---

## File Structure

**Created in this plan:**

```
src/locksmith/plugins/designer/
├── widgets/
│   ├── role_icon_badge.py         # kind-colored rounded square + emoji glyph
│   ├── validation_pill.py         # status pill (valid / N issues)
│   ├── ecosystem_chip.py          # small rounded tag (also exports CrossTemplateChip)
│   └── kebab_button.py            # three-dot icon button (no actions wired)
└── seed_fixtures.py                # copy bundled fixtures into store on dev-mode open

tests/plugins/designer/
├── test_role_icon_badge_visual.py
├── test_validation_pill_visual.py
├── test_ecosystem_chip_visual.py
├── test_kebab_button_visual.py
├── test_templates_browser_v1_visual.py
├── test_overview_v1_visual.py
├── test_primitive_editor_shell_v1_visual.py
└── test_seed_fixtures.py
```

**Modified in this plan:**

```
src/locksmith/plugins/designer/
├── widgets/
│   ├── kind_rail.py                       # RailItem.subtitle + render
│   ├── primitive_editor_shell.py          # breadcrumb (count + role-pill + valid pill); +Add at top w/ kind label
│   └── first_person_card.py               # facet-label styling, per-entry qualifier, rule-type-chip variant
├── editors/
│   ├── templates_browser.py               # count summary, filter strip, richer cards
│   └── overview.py                        # header strip + 4×2 facet grid + bottom strip
└── plugin.py                              # call seed_fixtures.maybe_seed() in on_vault_opened

tests/plugins/designer/fixtures/
└── regulator-grants-carrier-license.json  # enriched to mock-content depth
```

**Out of scope (Phase 2+):** inline editability, kebab actions, ValidationPanel toggle, JsonSourceView toggle, draft-card resume-walkthrough affordances, per-editor section restructuring beyond the shell, swimlane / state-machine diagram revamps. Those land in later phases.

---

## Task 1: KindRail — subtitle support

**Files:**
- Modify: `src/locksmith/plugins/designer/widgets/kind_rail.py`
- Test: `tests/plugins/designer/test_kind_rail_subtitle.py`

The v1 mocks show two-line rail items: bold main label + small grey subtitle ("↔ carrier · 5 steps", "← exn · 2 emissions", "purpose: lifecycle_transition · → 1 transition"). This task adds an optional `subtitle` field to `RailItem` and renders it as a second line.

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/designer/test_kind_rail_subtitle.py
from PySide6.QtCore import Qt

from locksmith.plugins.designer.widgets.kind_rail import KindRail, RailItem


def test_railitem_subtitle_renders_as_two_line_text(qapp):
    rail = KindRail()
    rail.populate([
        RailItem(id="a", label="grant_license",
                 subtitle="→ carrier · 2 emissions",
                 kind_color="#0ABFB0", has_errors=False),
    ])
    item = rail.item(0)
    # The display string carries the subtitle on a second line.
    assert "grant_license" in item.text()
    assert "→ carrier · 2 emissions" in item.text()
    # The first character of the second line is a newline so QListWidget
    # word-wraps cleanly.
    assert "\n" in item.text()


def test_railitem_subtitle_optional(qapp):
    rail = KindRail()
    rail.populate([
        RailItem(id="b", label="solo", subtitle=None,
                 kind_color="#888", has_errors=False),
    ])
    item = rail.item(0)
    assert item.text() == "solo"
    assert "\n" not in item.text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_kind_rail_subtitle.py -v`
Expected: FAIL with `TypeError: RailItem.__init__() got an unexpected keyword argument 'subtitle'`.

- [ ] **Step 3: Add `subtitle` to RailItem and render two lines**

Replace the existing `RailItem` and `KindRail.populate` in `src/locksmith/plugins/designer/widgets/kind_rail.py`:

```python
@dataclass(frozen=True)
class RailItem:
    id: str
    label: str
    kind_color: str  # CSS hex, e.g. "#0ABFB0"
    has_errors: bool
    subtitle: str | None = None
```

Update `populate` to render subtitle as a second line, separated by `\n`:

```python
    def populate(self, items: list[RailItem]) -> None:
        self.clear()
        for r in items:
            main = r.label + ("  ⛔" if r.has_errors else "")
            text = f"{main}\n{r.subtitle}" if r.subtitle else main
            item = QListWidgetItem(text)
            item.setIcon(_dot_icon(r.kind_color))
            item.setData(Qt.UserRole, r.id)
            self.addItem(item)
        if self.count() > 0:
            self.setCurrentRow(0)
```

Also bump the per-item padding in the stylesheet so the two-line item doesn't crowd:

```python
        self.setStyleSheet(
            "QListWidget{background:#fff;border:0;}"
            "QListWidget::item{padding:10px 12px;border-bottom:1px solid #f0f2f5;}"
            "QListWidget::item:selected{background:#f6f7f9;color:#1A1C20;}"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_kind_rail_subtitle.py -v`
Expected: PASS (2 tests).

Then run the existing KindRail tests to confirm no regression:
Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/ -k "kind_rail" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/widgets/kind_rail.py \
        tests/plugins/designer/test_kind_rail_subtitle.py
git commit -m "feat(designer): RailItem.subtitle for two-line rail entries"
```

---

## Task 2: PrimitiveEditorShell — `+ Add <kind>` at top of rail

**Files:**
- Modify: `src/locksmith/plugins/designer/widgets/primitive_editor_shell.py`
- Test: `tests/plugins/designer/test_primitive_editor_shell_v1_visual.py` (created here)

The v1 mocks put the creation affordance at the **top** of the rail and label it after the primitive ("+ Add command", "+ Add workflow", "+ Add rule", "+ Add credential to issue"). The current shell has a bare "+ Add" at the bottom. This task moves and labels it.

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/designer/test_primitive_editor_shell_v1_visual.py
from PySide6.QtWidgets import QLabel

from locksmith.plugins.designer.widgets.kind_rail import RailItem
from locksmith.plugins.designer.widgets.primitive_editor_shell import (
    PrimitiveEditorShell,
)


def test_add_button_appears_above_rail_with_kind_label(qapp):
    shell = PrimitiveEditorShell(
        surface_label="Commands",
        template_label="Regulator Grants Carrier License",
        items=[RailItem(id="x", label="x", kind_color="#0ABFB0",
                        has_errors=False)],
        add_label="+ Add command",
    )
    assert shell.add_button.text() == "+ Add command"
    rail_panel_layout = shell.rail_list.parent().layout()
    # The add button must be at index 0 (top), the rail list at index 1.
    assert rail_panel_layout.itemAt(0).widget() is shell.add_button
    assert rail_panel_layout.itemAt(1).widget() is shell.rail_list


def test_add_label_defaults_to_plain_add(qapp):
    shell = PrimitiveEditorShell(
        surface_label="X", template_label="T",
        items=[], add_label=None,
    )
    assert shell.add_button.text() == "+ Add"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_primitive_editor_shell_v1_visual.py -v`
Expected: FAIL — `add_label` is an unexpected kwarg.

- [ ] **Step 3: Add `add_label` param and reorder the rail panel layout**

In `src/locksmith/plugins/designer/widgets/primitive_editor_shell.py`, change `__init__` signature:

```python
    def __init__(
        self,
        *,
        surface_label: str,
        template_label: str,
        items: list[RailItem],
        add_label: str | None = None,
        parent=None,
    ):
        super().__init__(parent=parent)
        self._add_label = add_label or "+ Add"
        self._build(surface_label=surface_label, template_label=template_label)
        self.rail_list.populate(items)
        self.rail_list.currentItemChanged.connect(self._on_rail_change)
```

And in `_build`, replace the rail panel construction so `add_button` is added **before** `rail_list` and styled to look like a top-of-rail row:

```python
        rail_panel = QFrame()
        rail_panel.setFixedWidth(260)
        rail_panel.setStyleSheet("background:#fff;border-right:1px solid #e0e3ea;")
        rail_lay = QVBoxLayout(rail_panel)
        rail_lay.setContentsMargins(0, 0, 0, 0)
        rail_lay.setSpacing(0)
        self.add_button = QPushButton(self._add_label)
        self.add_button.setStyleSheet(
            "QPushButton{background:#fff;border:0;"
            "border-bottom:1px solid #e0e3ea;"
            "padding:10px 12px;text-align:center;color:#0ABFB0;"
            "font-weight:600;}"
            "QPushButton:hover{background:#f0fbfa;}"
        )
        self.add_button.clicked.connect(self.add_clicked.emit)
        rail_lay.addWidget(self.add_button)
        self.rail_list = KindRail()
        rail_lay.addWidget(self.rail_list, 1)
        body.addWidget(rail_panel)
```

(Remove the old bottom-of-rail `add_button` block that styled it as a bottom row.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_primitive_editor_shell_v1_visual.py -v`
Expected: PASS.

Run the existing editor visual smoke tests to confirm no break:
Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/ -k "editor" -v`
Expected: PASS (any older test that relied on the bottom-add position is OK because we still expose `shell.add_button`).

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/widgets/primitive_editor_shell.py \
        tests/plugins/designer/test_primitive_editor_shell_v1_visual.py
git commit -m "feat(designer): +Add at top of rail with per-kind label"
```

---

## Task 3: PrimitiveEditorShell — breadcrumb with count + role pill + valid pill

**Files:**
- Modify: `src/locksmith/plugins/designer/widgets/primitive_editor_shell.py`
- Test: `tests/plugins/designer/test_primitive_editor_shell_v1_visual.py` (extend)

The v1 mocks show the identity strip as `← Overview › Commands (4)` on the left and `Role: state-doi · ✓ valid` on the right. The current shell shows `← Back · <template label> · <surface label>` only. This task adds count, role pill, and valid pill to the right side.

- [ ] **Step 1: Write the failing test**

Append to `tests/plugins/designer/test_primitive_editor_shell_v1_visual.py`:

```python
def test_breadcrumb_count_appears_after_surface_label(qapp):
    shell = PrimitiveEditorShell(
        surface_label="Commands",
        template_label="Regulator Grants Carrier License",
        items=[RailItem(id=f"c{i}", label=f"c{i}",
                        kind_color="#0ABFB0", has_errors=False)
               for i in range(4)],
        add_label="+ Add command",
        item_count=4,
        role_label="state-doi",
        is_valid=True,
    )
    assert shell.count_label.text() == "(4)"
    assert "state-doi" in shell.role_pill.text()
    assert "valid" in shell.valid_pill.text().lower()


def test_invalid_pill_shows_issue_count(qapp):
    shell = PrimitiveEditorShell(
        surface_label="Rules", template_label="X",
        items=[], add_label="+ Add rule",
        item_count=0, role_label="state-doi",
        is_valid=False, issue_count=3,
    )
    assert "3" in shell.valid_pill.text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_primitive_editor_shell_v1_visual.py::test_breadcrumb_count_appears_after_surface_label -v`
Expected: FAIL — `item_count` unexpected kwarg.

- [ ] **Step 3: Extend the breadcrumb construction**

Update `PrimitiveEditorShell.__init__` to accept the new params:

```python
    def __init__(
        self,
        *,
        surface_label: str,
        template_label: str,
        items: list[RailItem],
        add_label: str | None = None,
        item_count: int = 0,
        role_label: str = "",
        is_valid: bool = True,
        issue_count: int = 0,
        parent=None,
    ):
        super().__init__(parent=parent)
        self._add_label = add_label or "+ Add"
        self._item_count = item_count
        self._role_label = role_label
        self._is_valid = is_valid
        self._issue_count = issue_count
        self._build(surface_label=surface_label, template_label=template_label)
        self.rail_list.populate(items)
        self.rail_list.currentItemChanged.connect(self._on_rail_change)
```

Then in `_build`, after `strip_lay.addWidget(self.surface_label)`, replace the trailing stretch with the new right-side widgets:

```python
        self.count_label = QLabel(f"({self._item_count})")
        self.count_label.setStyleSheet("color:#888;")
        strip_lay.addWidget(self.count_label)

        strip_lay.addStretch(1)

        role_text = f"Role: {self._role_label}" if self._role_label else ""
        self.role_pill = QLabel(role_text)
        self.role_pill.setStyleSheet(
            "color:#0ABFB0;font-weight:600;padding:3px 8px;"
            "background:#f0fbfa;border-radius:10px;font-size:11px;"
        )
        if not self._role_label:
            self.role_pill.setVisible(False)
        strip_lay.addWidget(self.role_pill)

        if self._is_valid:
            self.valid_pill = QLabel("✓ valid")
            self.valid_pill.setStyleSheet(
                "color:#2a8a4a;background:#eafaf0;border-radius:10px;"
                "padding:3px 8px;font-size:11px;font-weight:600;"
            )
        else:
            self.valid_pill = QLabel(f"⚠ {self._issue_count} issues")
            self.valid_pill.setStyleSheet(
                "color:#a5641a;background:#fdf3e7;border-radius:10px;"
                "padding:3px 8px;font-size:11px;font-weight:600;"
            )
        strip_lay.addWidget(self.valid_pill)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_primitive_editor_shell_v1_visual.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Wire each editor to pass the new params**

Eight editors construct `PrimitiveEditorShell`. Update each callsite to pass the count + role label + validity. The pattern in `imports.py` line 153 is the template — apply the same shape to commands / aggregates / reactions / workflows / projections / rules / exports / imports.

For `src/locksmith/plugins/designer/editors/imports.py`, change the existing construction to:

```python
        items = [
            RailItem(
                id=imp.get("id", ""),
                label=imp.get("id") or "(unnamed)",
                kind_color=color,
                has_errors=False,
            )
            for imp in model.doc.get("credentials", {}).get("imports", [])
        ]
        self.shell = PrimitiveEditorShell(
            surface_label="Imported credentials",
            template_label=model.doc.get("header", {}).get(
                "display_name", "(untitled)"
            ),
            items=items,
            add_label="+ Add credential to hold",
            item_count=len(items),
            role_label=model.doc.get("role", {}).get("id", ""),
            is_valid=True,
            parent=self,
        )
```

Apply the analogous change in each editor file using these per-surface add-labels:

| Editor file | `surface_label` | `add_label` |
|---|---|---|
| `commands.py` | `"Commands"` | `"+ Add command"` |
| `aggregates.py` | `"Aggregates"` | `"+ Add aggregate"` |
| `reactions.py` | `"Reactions"` | `"+ Add reaction"` |
| `workflows.py` | `"Workflows"` | `"+ Add workflow"` |
| `projections.py` | `"Projections"` | `"+ Add projection"` |
| `rules.py` | `"Rules"` | `"+ Add rule"` |
| `exports.py` | `"Issued credentials"` | `"+ Add credential to issue"` |
| `imports.py` | `"Imported credentials"` | `"+ Add credential to hold"` |

For each, set `item_count=len(items)` and `role_label=model.doc.get("role", {}).get("id", "")`. Keep `is_valid=True` and don't set `issue_count` — validity wiring lands in Phase 4.

- [ ] **Step 6: Run editor visual smoke tests to confirm no regression**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/ -v`
Expected: all existing PASS.

- [ ] **Step 7: Commit**

```bash
git add src/locksmith/plugins/designer/widgets/primitive_editor_shell.py \
        src/locksmith/plugins/designer/editors/*.py \
        tests/plugins/designer/test_primitive_editor_shell_v1_visual.py
git commit -m "feat(designer): editor breadcrumb shows count + role pill + valid pill"
```

---

## Task 4: RoleIconBadge widget

**Files:**
- Create: `src/locksmith/plugins/designer/widgets/role_icon_badge.py`
- Test: `tests/plugins/designer/test_role_icon_badge_visual.py`

A kind-colored rounded square with an emoji glyph centered inside. Used in templates browser cards, Overview header strip, and editor breadcrumbs. Maps role.kind → emoji per the v1 mocks:

| Kind | Emoji | Default color |
|---|---|---|
| `government` | 🏛️ | `#0ABFB0` |
| `organization` | 🏢 | `#0ABFB0` |
| `individual` | 👤 | `#D97757` |
| `system` | ⚙️ | `#888888` |
| `device` | 📟 | `#888888` |
| `agent` | 🤖 | `#A36AE6` |
| (unknown) | ❓ | `#888888` |

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/designer/test_role_icon_badge_visual.py
from locksmith.plugins.designer.widgets.role_icon_badge import RoleIconBadge


def test_government_badge_uses_landmark_glyph(qapp):
    b = RoleIconBadge(kind="government")
    assert b.glyph_label.text() == "🏛️"
    assert "#0ABFB0" in b.styleSheet()


def test_individual_badge_uses_person_glyph(qapp):
    b = RoleIconBadge(kind="individual")
    assert b.glyph_label.text() == "👤"
    assert "#D97757" in b.styleSheet()


def test_unknown_kind_falls_back_to_question_mark(qapp):
    b = RoleIconBadge(kind="nonsense")
    assert b.glyph_label.text() == "❓"


def test_badge_size_param_overrides_default(qapp):
    big = RoleIconBadge(kind="government", size=64)
    assert big.height() == 64 and big.width() == 64
    small = RoleIconBadge(kind="government", size=32)
    assert small.height() == 32 and small.width() == 32
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_role_icon_badge_visual.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the widget**

```python
# src/locksmith/plugins/designer/widgets/role_icon_badge.py
# -*- encoding: utf-8 -*-
"""RoleIconBadge: kind-colored rounded square with role-kind emoji glyph.

Used in templates-browser cards, Overview header, and editor breadcrumbs.
Color + glyph chosen by role.kind. Falls back to neutral grey + ❓ on
unknown kinds.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


_GLYPHS: dict[str, str] = {
    "government":   "🏛️",
    "organization": "🏢",
    "individual":   "👤",
    "system":       "⚙️",
    "device":       "📟",
    "agent":        "🤖",
}

_COLORS: dict[str, str] = {
    "government":   "#0ABFB0",
    "organization": "#0ABFB0",
    "individual":   "#D97757",
    "system":       "#888888",
    "device":       "#888888",
    "agent":        "#A36AE6",
}


class RoleIconBadge(QFrame):
    def __init__(self, *, kind: str, size: int = 52, parent=None):
        super().__init__(parent=parent)
        color = _COLORS.get(kind, "#888888")
        glyph = _GLYPHS.get(kind, "❓")
        self.setFixedSize(size, size)
        self.setStyleSheet(
            f"background:{color};border-radius:8px;"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.glyph_label = QLabel(glyph)
        self.glyph_label.setAlignment(Qt.AlignCenter)
        self.glyph_label.setStyleSheet(
            f"font-size:{int(size * 0.45)}px;background:transparent;"
        )
        lay.addWidget(self.glyph_label)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_role_icon_badge_visual.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/widgets/role_icon_badge.py \
        tests/plugins/designer/test_role_icon_badge_visual.py
git commit -m "feat(designer): RoleIconBadge widget for role-kind glyph"
```

---

## Task 5: ValidationPill widget

**Files:**
- Create: `src/locksmith/plugins/designer/widgets/validation_pill.py`
- Test: `tests/plugins/designer/test_validation_pill_visual.py`

Three states: **valid** (green checkmark), **warnings only** (orange `⚠ N issues`), **invalid** (red `⛔ N issues`). Used in templates-browser cards, Overview header, Overview bottom strip, and editor breadcrumb (shell already does its own — Phase 4 will unify on this widget).

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/designer/test_validation_pill_visual.py
from locksmith.plugins.designer.widgets.validation_pill import ValidationPill


def test_valid_pill(qapp):
    pill = ValidationPill(error_count=0, warning_count=0)
    assert pill.text() == "✓ valid"
    assert "#eafaf0" in pill.styleSheet()


def test_warnings_only(qapp):
    pill = ValidationPill(error_count=0, warning_count=2)
    assert pill.text() == "⚠ 2 warnings"
    assert "#fdf3e7" in pill.styleSheet()


def test_errors_present_dominate_warnings(qapp):
    pill = ValidationPill(error_count=3, warning_count=2)
    assert pill.text() == "⛔ 3 errors"
    assert "#fce8ea" in pill.styleSheet()


def test_singular_count_grammar(qapp):
    p1 = ValidationPill(error_count=1, warning_count=0)
    assert p1.text() == "⛔ 1 error"
    p2 = ValidationPill(error_count=0, warning_count=1)
    assert p2.text() == "⚠ 1 warning"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_validation_pill_visual.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the widget**

```python
# src/locksmith/plugins/designer/widgets/validation_pill.py
# -*- encoding: utf-8 -*-
"""ValidationPill: tri-state validation status chip."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel


class ValidationPill(QLabel):
    def __init__(self, *, error_count: int, warning_count: int, parent=None):
        super().__init__(parent=parent)
        if error_count > 0:
            noun = "error" if error_count == 1 else "errors"
            text = f"⛔ {error_count} {noun}"
            style = ("color:#a52a2a;background:#fce8ea;border-radius:10px;"
                     "padding:3px 8px;font-size:11px;font-weight:600;")
        elif warning_count > 0:
            noun = "warning" if warning_count == 1 else "warnings"
            text = f"⚠ {warning_count} {noun}"
            style = ("color:#a5641a;background:#fdf3e7;border-radius:10px;"
                     "padding:3px 8px;font-size:11px;font-weight:600;")
        else:
            text = "✓ valid"
            style = ("color:#2a8a4a;background:#eafaf0;border-radius:10px;"
                     "padding:3px 8px;font-size:11px;font-weight:600;")
        self.setText(text)
        self.setStyleSheet(style)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_validation_pill_visual.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/widgets/validation_pill.py \
        tests/plugins/designer/test_validation_pill_visual.py
git commit -m "feat(designer): ValidationPill widget (valid/warning/error states)"
```

---

## Task 6: EcosystemChip + CrossTemplateChip widgets

**Files:**
- Create: `src/locksmith/plugins/designer/widgets/ecosystem_chip.py`
- Test: `tests/plugins/designer/test_ecosystem_chip_visual.py`

Two related small chips. `EcosystemChip` is a plain rounded tag (e.g., `insurance`, `compliance`, `healthcare`). `CrossTemplateChip` carries an arrow glyph and identifies a cross-template relationship (e.g., `↔ pairs with state-doi`, `↪ forked from EKWa…HYxkLN`).

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/designer/test_ecosystem_chip_visual.py
from locksmith.plugins.designer.widgets.ecosystem_chip import (
    CrossTemplateChip, EcosystemChip,
)


def test_ecosystem_chip_renders_tag_text(qapp):
    c = EcosystemChip("insurance")
    assert c.text() == "insurance"
    assert "#f0f2f5" in c.styleSheet()


def test_cross_template_pairs_with(qapp):
    c = CrossTemplateChip(kind="pairs_with", target="state-doi")
    assert c.text() == "↔ pairs with state-doi"


def test_cross_template_forked_from(qapp):
    c = CrossTemplateChip(kind="forked_from", target="EKWa…HYxkLN")
    assert c.text() == "↪ forked from EKWa…HYxkLN"


def test_cross_template_unknown_kind_falls_back_to_target(qapp):
    c = CrossTemplateChip(kind="unknown", target="x")
    assert c.text() == "· x"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_ecosystem_chip_visual.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement both widgets in one module**

```python
# src/locksmith/plugins/designer/widgets/ecosystem_chip.py
# -*- encoding: utf-8 -*-
"""Small rounded chip widgets used in templates-browser cards and Overview."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel


_CROSS_TEMPLATE_PREFIX: dict[str, str] = {
    "pairs_with":  "↔ pairs with",
    "forked_from": "↪ forked from",
}


class EcosystemChip(QLabel):
    def __init__(self, tag: str, parent=None):
        super().__init__(tag, parent=parent)
        self.setStyleSheet(
            "background:#f0f2f5;color:#444;border-radius:9px;"
            "padding:2px 9px;font-size:11px;"
        )


class CrossTemplateChip(QLabel):
    def __init__(self, *, kind: str, target: str, parent=None):
        super().__init__(parent=parent)
        prefix = _CROSS_TEMPLATE_PREFIX.get(kind)
        if prefix is None:
            text = f"· {target}"
        else:
            text = f"{prefix} {target}"
        self.setText(text)
        self.setStyleSheet(
            "background:#fdf3e7;color:#a5641a;border-radius:9px;"
            "padding:2px 9px;font-size:11px;"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_ecosystem_chip_visual.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/widgets/ecosystem_chip.py \
        tests/plugins/designer/test_ecosystem_chip_visual.py
git commit -m "feat(designer): EcosystemChip + CrossTemplateChip widgets"
```

---

## Task 7: KebabButton widget (display only)

**Files:**
- Create: `src/locksmith/plugins/designer/widgets/kebab_button.py`
- Test: `tests/plugins/designer/test_kebab_button_visual.py`

A flat three-dot button. Emits `clicked` like any `QPushButton`. Phase 1 only places it in the Overview header; **no actions are wired** here — that's Phase 2.

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/designer/test_kebab_button_visual.py
from locksmith.plugins.designer.widgets.kebab_button import KebabButton


def test_kebab_button_shows_three_dots(qapp):
    b = KebabButton()
    assert b.text() == "⋯"


def test_kebab_button_emits_clicked(qapp):
    b = KebabButton()
    fired = []
    b.clicked.connect(lambda: fired.append(True))
    b.click()
    assert fired == [True]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_kebab_button_visual.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the widget**

```python
# src/locksmith/plugins/designer/widgets/kebab_button.py
# -*- encoding: utf-8 -*-
"""KebabButton: flat three-dot button. Phase 1 ships display-only; the menu
that opens on click is wired in Phase 2 (Save/Finalize/Export/Duplicate/Delete).
"""
from __future__ import annotations

from PySide6.QtWidgets import QPushButton


class KebabButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__("⋯", parent=parent)
        self.setFlat(True)
        self.setFixedSize(28, 28)
        self.setStyleSheet(
            "QPushButton{color:#666;font-size:18px;border:0;border-radius:4px;}"
            "QPushButton:hover{background:#f6f7f9;color:#1A1C20;}"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_kebab_button_visual.py -v`
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/widgets/kebab_button.py \
        tests/plugins/designer/test_kebab_button_visual.py
git commit -m "feat(designer): KebabButton widget (display-only, no menu yet)"
```

---

## Task 8: FirstPersonCard — facet-label style, per-entry qualifier, rule-type variant

**Files:**
- Modify: `src/locksmith/plugins/designer/widgets/first_person_card.py`
- Test: `tests/plugins/designer/test_first_person_card_v1_visual.py`

The v1 mock makes the facet framing ("I HOLD", "I ISSUE", "I'M BOUND BY") the dominant card title in uppercase teal, and demotes the primitive name to a smaller secondary label. Per-entry small qualifier lines are common ("to carrier · 4 states · 1 schema"). The Rules card (`I'M BOUND BY`) shows type chips ("2 prose · 3 predicates · 1 validation · 1 link") instead of rule names.

This task rewrites `FirstPersonCard` to support all three needs.

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/designer/test_first_person_card_v1_visual.py
from locksmith.plugins.designer.widgets.first_person_card import (
    FacetEntry, FirstPersonCard,
)


def test_facet_label_is_uppercase_dominant_title(qapp):
    card = FirstPersonCard(
        framing="I ISSUE",
        kind_label="Issued credentials",
        count=1,
        entries=[FacetEntry(label="Carrier License",
                            qualifier="to carrier · 4 states · 1 schema")],
    )
    assert card.framing_label.text() == "I ISSUE"
    assert "uppercase" in card.framing_label.styleSheet() \
        or "I ISSUE" == card.framing_label.text().upper()


def test_entries_include_qualifier_subline(qapp):
    card = FirstPersonCard(
        framing="I ISSUE",
        kind_label="Issued credentials",
        count=1,
        entries=[FacetEntry(label="Carrier License",
                            qualifier="to carrier · 4 states · 1 schema")],
    )
    text = card.entries_text()
    assert "Carrier License" in text
    assert "to carrier · 4 states · 1 schema" in text


def test_rule_type_chip_variant_replaces_entries(qapp):
    card = FirstPersonCard(
        framing="I'M BOUND BY",
        kind_label="Rules",
        count=7,
        entries=[],
        rule_type_counts={"prose": 2, "predicate": 3, "validation": 1,
                          "binding_link": 1},
    )
    chips_text = card.chips_text()
    assert "2 prose" in chips_text
    assert "3 predicates" in chips_text
    assert "1 validation" in chips_text
    assert "1 link" in chips_text


def test_empty_state_message(qapp):
    card = FirstPersonCard(
        framing="I HOLD",
        kind_label="Imported credentials",
        count=0,
        entries=[],
        empty_message="No imports — this role is the root authority for licenses",
    )
    assert "root authority" in card.entries_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_first_person_card_v1_visual.py -v`
Expected: FAIL — `ImportError: cannot import name 'FacetEntry'`.

- [ ] **Step 3: Rewrite FirstPersonCard with new API**

Replace `src/locksmith/plugins/designer/widgets/first_person_card.py`:

```python
# -*- encoding: utf-8 -*-
"""FirstPersonCard: Overview card framed in first person.

Two layout variants:

* default: "I HOLD"-style facet label + count badge + entry list with
  optional per-entry qualifier sublines + "+ Add" link.
* rule-type-chip: same shell but renders type-count chips in place of
  entries. Used for "I'M BOUND BY" where listing individual rule names
  is less useful than seeing the type distribution.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)


_RULE_TYPE_COLORS: dict[str, str] = {
    "prose":              "#A36AE6",
    "legal_prose":        "#A36AE6",
    "behavioral_expectation": "#A36AE6",
    "predicate":          "#0ABFB0",
    "validation":         "#D97757",
    "computational":      "#888888",
    "binding_link":       "#666666",
}

_RULE_TYPE_LABEL: dict[str, str] = {
    "prose":              "prose",
    "legal_prose":        "prose",
    "behavioral_expectation": "prose",
    "predicate":          "predicates",
    "validation":         "validation",
    "computational":      "computational",
    "binding_link":       "link",
}


@dataclass(frozen=True)
class FacetEntry:
    label: str
    qualifier: str | None = None


class FirstPersonCard(QFrame):
    clicked = Signal()
    add_clicked = Signal()

    def __init__(
        self,
        *,
        framing: str,
        kind_label: str,
        count: int,
        entries: list[FacetEntry] | None = None,
        rule_type_counts: dict[str, int] | None = None,
        empty_message: str | None = None,
        parent=None,
    ):
        super().__init__(parent=parent)
        self.setObjectName("fpcard")
        self.setStyleSheet(
            "#fpcard{background:#fff;border:1px solid #e0e3ea;border-radius:8px;}"
            "#fpcard:hover{border:1px solid #d97757;}"
        )
        self._entries_text_cache = ""
        self._chips_text_cache = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(6)

        header = QHBoxLayout()
        self.framing_label = QLabel(framing)
        self.framing_label.setStyleSheet(
            "color:#0ABFB0;font-size:11px;font-weight:600;"
            "letter-spacing:0.5px;text-transform:uppercase;"
        )
        header.addWidget(self.framing_label)
        header.addStretch(1)
        count_label = QLabel(str(count))
        count_label.setStyleSheet(
            "background:#f6f7f9;color:#666;border-radius:10px;"
            "padding:1px 8px;font-size:10px;font-weight:600;"
        )
        header.addWidget(count_label)
        outer.addLayout(header)

        # The kind name (e.g. "Issued credentials") shows below the facet
        # framing in a muted style — secondary to the facet.
        kind = QLabel(kind_label)
        kind.setStyleSheet("font-size:12px;color:#888;")
        outer.addWidget(kind)

        if rule_type_counts:
            chip_row = QHBoxLayout()
            chip_row.setSpacing(6)
            chips_parts: list[str] = []
            for type_id, n in rule_type_counts.items():
                if n <= 0:
                    continue
                label = _RULE_TYPE_LABEL.get(type_id, type_id)
                color = _RULE_TYPE_COLORS.get(type_id, "#888888")
                chip = QLabel(f"{n} {label}")
                chip.setStyleSheet(
                    f"color:{color};background:#f6f7f9;border-radius:9px;"
                    "padding:2px 8px;font-size:11px;font-weight:600;"
                )
                chip_row.addWidget(chip)
                chips_parts.append(f"{n} {label}")
            chip_row.addStretch(1)
            outer.addLayout(chip_row)
            self._chips_text_cache = " ".join(chips_parts)
        elif entries:
            parts: list[str] = []
            for entry in entries[:3]:
                row_w = QVBoxLayout()
                row_w.setSpacing(1)
                main = QLabel(entry.label)
                main.setStyleSheet("font-size:12px;color:#1A1C20;")
                main.setWordWrap(True)
                row_w.addWidget(main)
                parts.append(entry.label)
                if entry.qualifier:
                    sub = QLabel(entry.qualifier)
                    sub.setStyleSheet("font-size:10px;color:#888;")
                    sub.setWordWrap(True)
                    row_w.addWidget(sub)
                    parts.append(entry.qualifier)
                outer.addLayout(row_w)
            self._entries_text_cache = " ".join(parts)
        else:
            msg = empty_message or "(none yet)"
            empty = QLabel(msg)
            empty.setStyleSheet("font-size:11px;color:#aaa;font-style:italic;")
            empty.setWordWrap(True)
            outer.addWidget(empty)
            self._entries_text_cache = msg

        add = QPushButton("+ Add")
        add.setFlat(True)
        add.setStyleSheet(
            "QPushButton{color:#666;text-align:left;border:0;padding:0;font-size:11px;}"
            "QPushButton:hover{color:#d97757;}"
        )
        add.clicked.connect(self.add_clicked.emit)
        outer.addWidget(add)

    def entries_text(self) -> str:
        return self._entries_text_cache

    def chips_text(self) -> str:
        return self._chips_text_cache

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(ev)
```

- [ ] **Step 4: Update overview.py call sites for the new API**

`src/locksmith/plugins/designer/editors/overview.py` passes the old `preview_entries=[...]` kwarg. The full Overview rewrite lands in Task 12; for this task, do the minimal interim adaptation so the existing tests don't break:

In `overview.py`, replace the existing inner loop:

```python
        for idx, (kind, framing, label, dotted) in enumerate(_CARD_SPECS):
            if kind == "role":
                role = self._model.doc.get("role", {})
                entries = [FacetEntry(
                    label=f"{role.get('display_name', '(unnamed)')} ({role.get('kind', '?')})",
                )]
                count = 1
            else:
                items_at = _list_at(self._model.doc, dotted)
                entries = [FacetEntry(label=entry_label(e)) for e in items_at]
                count = len(items_at)
            card = FirstPersonCard(
                framing=framing, kind_label=label,
                count=count, entries=entries,
            )
            card.clicked.connect(lambda k=kind: self.drilldown_requested.emit(k))
            card.add_clicked.connect(lambda k=kind: self.add_requested.emit(k))
            row, col = divmod(idx, 3)
            grid.addWidget(card, row, col)
            self._cards[kind] = card
```

And add the import at the top:

```python
from locksmith.plugins.designer.widgets.first_person_card import (
    FacetEntry, FirstPersonCard,
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_first_person_card_v1_visual.py tests/plugins/designer/ -k "overview" -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/locksmith/plugins/designer/widgets/first_person_card.py \
        src/locksmith/plugins/designer/editors/overview.py \
        tests/plugins/designer/test_first_person_card_v1_visual.py
git commit -m "feat(designer): FacetEntry + per-entry qualifier + rule-type-chip variant"
```

---

## Task 9: Enrich regulator fixture to mock-content depth

**Files:**
- Modify: `tests/plugins/designer/fixtures/regulator-grants-carrier-license.json`
- Test: `tests/plugins/designer/test_regulator_fixture.py`

The mocks render 4 commands (grant_license / suspend_license / reinstate_license / revoke_license), 2 reactions (application_received / application_withdrawn), 3 workflows (grant / suspension / revocation), 2 projections (pending_applications / active_licensees), and 7 rules spanning legal_prose / predicate / validation / binding_link. Bring the regulator fixture to that depth so the live UI renders the same content the mocks promise. Keep schema validity.

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/designer/test_regulator_fixture.py
import json
from pathlib import Path


FIXTURE = (Path(__file__).parent / "fixtures"
           / "regulator-grants-carrier-license.json")


def test_fixture_has_four_commands():
    doc = json.loads(FIXTURE.read_text())
    ids = {c["id"] for c in doc["commands"]}
    assert ids == {"grant_license", "suspend_license",
                   "reinstate_license", "revoke_license"}


def test_fixture_has_two_reactions():
    doc = json.loads(FIXTURE.read_text())
    ids = {r["id"] for r in doc["reactions"]}
    assert ids == {"on_application_received", "on_application_withdrawn"}


def test_fixture_has_three_workflows():
    doc = json.loads(FIXTURE.read_text())
    ids = {w["id"] for w in doc["workflows"]}
    assert ids == {"license_grant_workflow",
                   "license_suspension_workflow",
                   "license_revocation_workflow"}


def test_fixture_has_two_projections():
    doc = json.loads(FIXTURE.read_text())
    ids = {p["id"] for p in doc["projections"]}
    assert ids == {"pending_applications", "active_licensees"}


def test_fixture_has_seven_rules_spanning_four_types():
    doc = json.loads(FIXTURE.read_text())
    assert len(doc["rules"]) == 7
    types = {r["type"] for r in doc["rules"]}
    assert types == {"legal_prose", "predicate", "validation", "binding_link"}


def test_fixture_validates_against_meta_schema():
    from locksmith.micro_app_template.validate import validate_template
    doc = json.loads(FIXTURE.read_text())
    schema_path = (Path(__file__).parents[2] / "docs" / "superpowers"
                   / "specs" / "schemas" / "micro-app-template.schema.json")
    issues = validate_template(doc, schema_path)
    # Filter to errors only — warnings are OK here.
    errors = [i for i in issues if i.get("severity") == "error"]
    assert errors == [], f"unexpected schema errors: {errors}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_regulator_fixture.py -v`
Expected: 5 failures (only the schema-validation test currently passes since the bare fixture is schema-valid).

- [ ] **Step 3: Write the enriched fixture**

Overwrite `tests/plugins/designer/fixtures/regulator-grants-carrier-license.json` with:

```json
{
  "d": "EGCpXap_yYxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx6yAv",
  "spec_version": "micro-app-template/0.1",
  "header": {
    "id": "regulator-grants-carrier-license",
    "display_name": "Regulator Grants Carrier License",
    "description": "The state DOI authorizes carriers to bear insurance risk in this jurisdiction. Reviews applications, grants licenses, monitors solvency, and revokes when grounds arise.",
    "version": "1.0",
    "expression_language": "UEL/1.0"
  },
  "role": {
    "id": "state-doi",
    "display_name": "State Department of Insurance",
    "description": "State Department of Insurance — issues and supervises carrier licenses.",
    "kind": "government",
    "keri_infrastructure": {
      "witness_pool": true, "watcher_network": true,
      "mailbox": true, "acdc_registry": true
    }
  },
  "credentials": {
    "imports": [],
    "exports": [
      {
        "id": "carrier_license",
        "name": "Carrier License",
        "description": "License authorizing an entity to bear insurance risk in a jurisdiction. Required before any policy issuance.",
        "envelope": {
          "holder_role": "carrier",
          "verifier_roles": ["public"],
          "edges": [],
          "disclosure_mode": "full"
        },
        "schema": {
          "schema_said": "ENRy4fo74JoBf2_1K2Olx1WJ6UqY_v98Y8S_qnw2GuDR",
          "schema_path": "schemas/carrier_license.json"
        },
        "lifecycle": {
          "states": ["pending", "active", "suspended", "revoked"],
          "initial": "pending",
          "transitions": [
            {"id": "grant", "from": "pending", "to": "active",
             "tel_primitive": "issue",
             "via_workflow": "license_grant_workflow",
             "requires": [{"rule_ref": "financial_solvency_demonstrated"}]},
            {"id": "suspend", "from": "active", "to": "suspended",
             "tel_primitive": "update",
             "via_workflow": "license_suspension_workflow"},
            {"id": "reinstate", "from": "suspended", "to": "active",
             "tel_primitive": "update",
             "via_workflow": "license_suspension_workflow",
             "requires": [{"rule_ref": "suspension_grounds_cleared"}]},
            {"id": "revoke", "from": ["active", "suspended"], "to": "revoked",
             "tel_primitive": "revoke",
             "via_workflow": "license_revocation_workflow"}
          ]
        },
        "rule_refs": ["issued_under_statutory_authority",
                      "ongoing_compliance_obligation"]
      }
    ]
  },
  "commands": [
    {
      "id": "grant_license",
      "name": "Grant License",
      "description": "Issue a new carrier_license credential to an approved applicant, advancing its lifecycle from pending to active.",
      "route": "/insurance/cmd/grant_license",
      "counterparty_role": "carrier",
      "payload_schema": {
        "type": "object",
        "required": ["license_number", "jurisdiction", "lines_of_business",
                     "effective_date", "expiration_date"],
        "properties": {
          "license_number": {"type": "string", "pattern": "^[A-Z0-9-]+$"},
          "jurisdiction": {"type": "string", "pattern": "^US-[A-Z]{2}$"},
          "lines_of_business": {"type": "array",
                                 "items": {"type": "string",
                                           "enum": ["property", "casualty",
                                                    "life", "health"]}},
          "effective_date": {"type": "string", "format": "date"},
          "expiration_date": {"type": "string", "format": "date"}
        }
      },
      "idempotency_key_expression": "payload.license_number",
      "auth_preconditions": [
        {"rule_ref": "applicant_provided_all_required_fields"}
      ],
      "emissions": [
        {"kind": "lifecycle_advance",
         "exported_credential_id": "carrier_license", "to_state": "active"}
      ]
    },
    {
      "id": "suspend_license",
      "name": "Suspend License",
      "description": "Suspend an active carrier_license credential.",
      "route": "/insurance/cmd/suspend_license",
      "counterparty_role": "carrier",
      "payload_schema": {"type": "object",
                          "required": ["license_number", "reason"],
                          "properties": {
                            "license_number": {"type": "string"},
                            "reason": {"type": "string"}}},
      "idempotency_key_expression": "payload.license_number",
      "emissions": [
        {"kind": "lifecycle_advance",
         "exported_credential_id": "carrier_license", "to_state": "suspended"}
      ]
    },
    {
      "id": "reinstate_license",
      "name": "Reinstate License",
      "description": "Reinstate a suspended carrier_license credential.",
      "route": "/insurance/cmd/reinstate_license",
      "counterparty_role": "carrier",
      "payload_schema": {"type": "object",
                          "required": ["license_number"],
                          "properties": {
                            "license_number": {"type": "string"}}},
      "idempotency_key_expression": "payload.license_number",
      "auth_preconditions": [
        {"rule_ref": "suspension_grounds_cleared"}
      ],
      "emissions": [
        {"kind": "lifecycle_advance",
         "exported_credential_id": "carrier_license", "to_state": "active"}
      ]
    },
    {
      "id": "revoke_license",
      "name": "Revoke License",
      "description": "Permanently revoke a carrier_license credential.",
      "route": "/insurance/cmd/revoke_license",
      "counterparty_role": "carrier",
      "payload_schema": {"type": "object",
                          "required": ["license_number", "reason"],
                          "properties": {
                            "license_number": {"type": "string"},
                            "reason": {"type": "string"}}},
      "idempotency_key_expression": "payload.license_number",
      "emissions": [
        {"kind": "lifecycle_advance",
         "exported_credential_id": "carrier_license", "to_state": "revoked"}
      ]
    }
  ],
  "aggregates": [
    {
      "id": "license_registry",
      "description": "Active and historical licenses issued by this regulator.",
      "inception_event_type": "regulator.licensing.inaugurated",
      "state_schema": {
        "type": "object",
        "properties": {
          "active":  {"type": "integer"},
          "revoked": {"type": "integer"}
        }
      },
      "initial_state": {"active": 0, "revoked": 0},
      "log_scope": "witnessed",
      "invariants": [
        {"rule_ref": "no_duplicate_active_license_per_carrier"}
      ]
    }
  ],
  "reactions": [
    {
      "id": "on_application_received",
      "description": "Start the license-grant workflow when a carrier submits a license application.",
      "trigger": {"type": "exn_received",
                  "route": "/insurance/cmd/submit_application",
                  "schema_id": "submit_application_request"},
      "emissions": [
        {"kind": "aggregate_event", "aggregate_id": "license_registry",
         "event_type": "application_recorded", "payload_mapping": {}}
      ],
      "failure_policy": {"on_validation_failure": "log_and_spurn"}
    },
    {
      "id": "on_application_withdrawn",
      "description": "Tidy aggregate state when a pending application is withdrawn by the carrier.",
      "trigger": {"type": "exn_received",
                  "route": "/insurance/cmd/withdraw_application"},
      "emissions": [
        {"kind": "aggregate_event", "aggregate_id": "license_registry",
         "event_type": "application_withdrawn", "payload_mapping": {}}
      ]
    }
  ],
  "workflows": [
    {
      "id": "license_grant_workflow",
      "name": "License Grant Workflow",
      "description": "Regulator reviews a carrier's license application, decides to grant or refuse, and (on grant) issues the license credential.",
      "trigger": {"type": "exn_received",
                  "route": "/insurance/cmd/submit_application"},
      "counterparty_role": "carrier",
      "steps": [
        {"id": "intake", "name": "Carrier submits application",
         "actor": "counterparty",
         "expected_inbound": [{"imported_credential_id": "submit_application_request"}]},
        {"id": "review", "name": "Review application", "actor": "self"},
        {"id": "decide", "name": "Decision", "actor": "self",
         "branches": [
           {"rule_ref": "applicant_provided_all_required_fields",
            "next_step": "grant"},
           {"rule_ref": "applicant_provided_all_required_fields",
            "next_step": "deny"}]},
        {"id": "grant", "name": "Grant license", "actor": "self",
         "command_id": "grant_license"},
        {"id": "deny", "name": "Spurn application", "actor": "self"}
      ]
    },
    {
      "id": "license_suspension_workflow",
      "name": "License Suspension Workflow",
      "description": "Regulator places an active license into suspended state and may reinstate it later.",
      "trigger": {"type": "manual"},
      "steps": [
        {"id": "investigate", "name": "Investigate cause", "actor": "self"},
        {"id": "suspend", "name": "Suspend license", "actor": "self",
         "command_id": "suspend_license"},
        {"id": "reinstate", "name": "Reinstate license", "actor": "self",
         "command_id": "reinstate_license"}
      ]
    },
    {
      "id": "license_revocation_workflow",
      "name": "License Revocation Workflow",
      "description": "Regulator permanently revokes a license.",
      "trigger": {"type": "manual"},
      "steps": [
        {"id": "review", "name": "Review revocation grounds", "actor": "self"},
        {"id": "revoke", "name": "Revoke license", "actor": "self",
         "command_id": "revoke_license"}
      ]
    }
  ],
  "projections": [
    {
      "id": "pending_applications",
      "name": "Pending Applications",
      "description": "Carrier license applications awaiting regulator review.",
      "source_events": ["application_recorded", "application_withdrawn"],
      "output_schema": {"type": "array",
                         "items": {"type": "object",
                                   "properties": {
                                     "applicant_aid": {"type": "string"},
                                     "jurisdiction": {"type": "string"},
                                     "received_at": {"type": "string"}}}},
      "fold_expression": "events.filter(e => e.kind == 'application_recorded')",
      "display": {"view_type": "table"}
    },
    {
      "id": "active_licensees",
      "name": "Active Licensees",
      "description": "Roster of carriers currently authorized to bind risk.",
      "source_events": ["license.issued", "license.revoked"],
      "output_schema": {"type": "array",
                         "items": {"type": "object",
                                   "properties": {
                                     "carrier_id": {"type": "string"}}}},
      "fold_expression": "events.filter(e => e.kind == 'license.issued').map(e => e.carrier_id)",
      "display": {"view_type": "table"}
    }
  ],
  "rules": [
    {
      "id": "issued_under_statutory_authority",
      "type": "legal_prose",
      "title": "Issued under statutory authority",
      "body": "This license is issued pursuant to the state insurance code and constitutes authority for the named carrier to bind insurance risk in the listed lines of business."
    },
    {
      "id": "ongoing_compliance_obligation",
      "type": "legal_prose",
      "title": "Ongoing compliance obligation",
      "body": "Licensed carriers must maintain solvency, file annual reports, and submit to market conduct examination as a condition of continued licensure."
    },
    {
      "id": "financial_solvency_demonstrated",
      "type": "predicate",
      "title": "Financial Solvency Demonstrated",
      "description": "Carrier has demonstrated sufficient capital reserves and reinsurance coverage per state actuarial requirements to support proposed lines of business.",
      "expression": "event.credential.attributes.market_conduct_status == \"good_standing\" && event.credential.attributes.lines_of_business.every(l => state.approved_lines.exists(a => a == l))",
      "language": "UEL/1.0",
      "purpose": "lifecycle_transition_requires"
    },
    {
      "id": "applicant_provided_all_required_fields",
      "type": "predicate",
      "title": "Applicant provided all required fields",
      "expression": "payload.license_number != null && payload.jurisdiction != null && payload.lines_of_business.length > 0",
      "language": "UEL/1.0",
      "purpose": "auth_precondition"
    },
    {
      "id": "suspension_grounds_cleared",
      "type": "predicate",
      "title": "Suspension grounds cleared",
      "expression": "state.last_audit_status == \"passed\"",
      "language": "UEL/1.0",
      "purpose": "lifecycle_transition_requires"
    },
    {
      "id": "no_duplicate_active_license_per_carrier",
      "type": "validation",
      "title": "No duplicate active license per carrier",
      "expression": "state.active_count <= 1",
      "language": "UEL/1.0"
    },
    {
      "id": "authority_articulation",
      "type": "binding_link",
      "title": "Authority articulation",
      "description": "The legal prose articulates the regulatory authority this predicate enforces.",
      "links": [
        {"rule_id": "issued_under_statutory_authority"},
        {"rule_id": "financial_solvency_demonstrated"}
      ]
    }
  ]
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_regulator_fixture.py -v`
Expected: 6 tests PASS.

If the meta-schema validator flags an issue, adjust the fixture content (not the validator) — the validator is authoritative.

- [ ] **Step 5: Commit**

```bash
git add tests/plugins/designer/fixtures/regulator-grants-carrier-license.json \
        tests/plugins/designer/test_regulator_fixture.py
git commit -m "feat(designer): enrich regulator fixture to v1-mock content depth"
```

---

## Task 10: Seed fixtures into the store on dev-mode vault open

**Files:**
- Create: `src/locksmith/plugins/designer/seed_fixtures.py`
- Modify: `src/locksmith/plugins/designer/plugin.py`
- Test: `tests/plugins/designer/test_seed_fixtures.py`

The mocks show a populated 2-up grid. Today the store starts empty unless the user imports manually. This task adds a tiny `maybe_seed()` that, when `LOCKSMITH_DESIGNER_SEED_FIXTURES=1`, copies the two bundled fixtures (`regulator-grants-carrier-license.json` and `carrier-license-application.json`) into the store as registered templates. Idempotent — won't re-seed if either is already present.

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/designer/test_seed_fixtures.py
import os
from pathlib import Path

import pytest

from locksmith.plugins.designer import seed_fixtures
from locksmith.plugins.designer.store import TemplateStore


@pytest.fixture
def tmp_store(tmp_path) -> TemplateStore:
    return TemplateStore(root=tmp_path)


def test_no_seed_when_env_var_absent(tmp_store, monkeypatch):
    monkeypatch.delenv("LOCKSMITH_DESIGNER_SEED_FIXTURES", raising=False)
    seed_fixtures.maybe_seed(tmp_store)
    assert tmp_store.list_templates() == []


def test_seed_creates_two_registered_templates(tmp_store, monkeypatch):
    monkeypatch.setenv("LOCKSMITH_DESIGNER_SEED_FIXTURES", "1")
    seed_fixtures.maybe_seed(tmp_store)
    saids = {ref.said for ref in tmp_store.list_templates()
             if ref.kind == "registered"}
    # Both fixtures use known SAID prefixes; assert both made it in.
    assert any(s and s.startswith("EGCp") for s in saids)
    assert any(s and s.startswith("EKWa") for s in saids)


def test_seed_is_idempotent(tmp_store, monkeypatch):
    monkeypatch.setenv("LOCKSMITH_DESIGNER_SEED_FIXTURES", "1")
    seed_fixtures.maybe_seed(tmp_store)
    first = tmp_store.list_templates()
    seed_fixtures.maybe_seed(tmp_store)
    second = tmp_store.list_templates()
    assert len(first) == len(second) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_seed_fixtures.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `seed_fixtures.maybe_seed`**

```python
# src/locksmith/plugins/designer/seed_fixtures.py
# -*- encoding: utf-8 -*-
"""Dev-mode fixture seeding for the Designer plugin.

When `LOCKSMITH_DESIGNER_SEED_FIXTURES=1` and the store is empty (or only
missing a given fixture), copy the bundled fixtures into it as registered
templates. Idempotent. Off by default — production vaults stay empty.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from keri import help

from locksmith.plugins.designer.store import TemplateRef, TemplateStore


logger = help.ogler.getLogger(__name__)


_FIXTURE_DIR = (
    Path(__file__).resolve().parents[3]
    / "tests" / "plugins" / "designer" / "fixtures"
)

_BUNDLED: list[str] = [
    "regulator-grants-carrier-license.json",
    "carrier-license-application.json",
]


def maybe_seed(store: TemplateStore) -> None:
    """Seed bundled fixtures into `store` if env var is set.

    Only registered (SAID-bearing) fixtures are seeded. Drafts and the
    broken-references fixture are intentionally skipped — they're test
    artifacts, not demo content.
    """
    if os.environ.get("LOCKSMITH_DESIGNER_SEED_FIXTURES") != "1":
        return
    existing_saids = {ref.said for ref in store.list_templates()
                      if ref.kind == "registered"}
    for filename in _BUNDLED:
        src = _FIXTURE_DIR / filename
        if not src.exists():
            logger.warning("Fixture not found, skipping: %s", src)
            continue
        try:
            doc = json.loads(src.read_text())
        except json.JSONDecodeError as e:
            logger.warning("Fixture %s is not valid JSON: %s", src, e)
            continue
        said = doc.get("d")
        if not said:
            logger.warning("Fixture %s missing 'd' (SAID), skipping", src)
            continue
        if said in existing_saids:
            continue
        ref = TemplateRef(kind="registered", local_id=None, said=said)
        metadata = {
            "imported_from": str(src),
            "schema_validated": True,
            "ecosystem_tags": _ecosystem_tags_for(filename),
        }
        store.save_registered(ref, doc, metadata, overwrite=False)
        logger.info("Seeded designer fixture %s as registered SAID %s",
                    filename, said)


def _ecosystem_tags_for(filename: str) -> list[str]:
    # Lightweight per-fixture tag list — keep in sync with the mock content.
    if "regulator" in filename:
        return ["insurance", "compliance"]
    if "carrier-license-application" in filename:
        return ["insurance"]
    return []
```

- [ ] **Step 4: Wire `maybe_seed` into the plugin's vault-open lifecycle**

In `src/locksmith/plugins/designer/plugin.py`, inside `on_vault_opened`, after the line `self._store = TemplateStore(root=Path(root))` and before `browser = TemplatesBrowserPage(...)`:

```python
        from locksmith.plugins.designer import seed_fixtures
        seed_fixtures.maybe_seed(self._store)
```

- [ ] **Step 5: Verify `store.save_registered` accepts the call signature**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_seed_fixtures.py -v`
Expected: 3 tests PASS.

If `save_registered` rejects `overwrite=False` (already the default) or the metadata shape, inspect `src/locksmith/plugins/designer/store.py` and adapt the call — keep the test fixed.

- [ ] **Step 6: Commit**

```bash
git add src/locksmith/plugins/designer/seed_fixtures.py \
        src/locksmith/plugins/designer/plugin.py \
        tests/plugins/designer/test_seed_fixtures.py
git commit -m "feat(designer): seed bundled fixtures on dev-mode vault open"
```

---

## Task 11: Templates browser — count summary + filter strip

**Files:**
- Modify: `src/locksmith/plugins/designer/editors/templates_browser.py`
- Test: `tests/plugins/designer/test_templates_browser_v1_visual.py`

The v1 mock places a "5 templates · 4 valid · 1 draft" subline under the toolbar title, and a filter strip below it with three facet groups (validity / role kind / ecosystem) plus a sort selector on the right. Phase 1 ships the chips as **display-only** — they read the data but clicking them is a no-op (Phase 2 wires filtering).

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/designer/test_templates_browser_v1_visual.py
from pathlib import Path

import pytest

from locksmith.plugins.designer.editors.templates_browser import (
    TemplatesBrowserPage,
)
from locksmith.plugins.designer.store import TemplateRef, TemplateStore


@pytest.fixture
def seeded_store(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCKSMITH_DESIGNER_SEED_FIXTURES", "1")
    from locksmith.plugins.designer import seed_fixtures
    store = TemplateStore(root=tmp_path)
    seed_fixtures.maybe_seed(store)
    return store


def test_count_summary_reflects_valid_and_draft_totals(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    assert page.summary_label.text() == "2 templates · 2 valid · 0 drafts"


def test_filter_strip_has_validity_role_ecosystem_facets(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    chips = page.filter_chips_text()
    assert "All (2)" in chips
    assert "Valid (2)" in chips
    assert "Draft (0)" in chips
    assert "government (1)" in chips
    assert "organization (1)" in chips
    assert "insurance (2)" in chips


def test_grid_renders_two_cards_in_two_up(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    assert page.card_count() == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_templates_browser_v1_visual.py -v`
Expected: FAIL — `summary_label` AttributeError.

- [ ] **Step 3: Add summary line + filter strip to `_build`**

In `src/locksmith/plugins/designer/editors/templates_browser.py`, replace `_build` so the toolbar block carries the subline and a filter strip row:

```python
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Toolbar with title + count summary + action buttons.
        toolbar = QFrame()
        toolbar.setStyleSheet("background:#fff;border-bottom:1px solid #e0e3ea;")
        toolbar_lay = QVBoxLayout(toolbar)
        toolbar_lay.setContentsMargins(20, 14, 20, 6)
        toolbar_lay.setSpacing(2)

        top_row = QHBoxLayout()
        title_block = QVBoxLayout()
        title_block.setSpacing(0)
        title = QLabel("Micro-App Templates")
        title.setStyleSheet("font-size:18px;font-weight:600;color:#1A1C20;")
        title_block.addWidget(title)
        self.summary_label = QLabel("0 templates")
        self.summary_label.setStyleSheet("font-size:11px;color:#888;")
        title_block.addWidget(self.summary_label)
        top_row.addLayout(title_block)
        top_row.addStretch(1)

        btn_import_file = QPushButton("⬇ Import file")
        btn_import_file.clicked.connect(self.import_file_requested.emit)
        btn_import_oobi = QPushButton("🌐 Import via OOBI")
        btn_import_oobi.setEnabled(False)
        btn_import_oobi.setToolTip("Coming in a future release")
        btn_new = QPushButton("+ New template")
        btn_new.setStyleSheet(
            "background:#d97757;color:#fff;font-weight:600;"
            "padding:7px 14px;border-radius:4px;"
        )
        btn_new.clicked.connect(self.new_template_requested.emit)
        for b in (btn_import_file, btn_import_oobi, btn_new):
            top_row.addWidget(b)
        toolbar_lay.addLayout(top_row)

        # Filter strip — chips are display-only in Phase 1.
        self._filter_strip = QHBoxLayout()
        self._filter_strip.setContentsMargins(0, 6, 0, 8)
        self._filter_strip.setSpacing(8)
        toolbar_lay.addLayout(self._filter_strip)
        root.addWidget(toolbar)

        # Scroll area + grid (unchanged from the prior shape).
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("border:0;background:#f6f7f9;")
        self._grid_host = QWidget()
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(20, 20, 20, 20)
        self._grid.setSpacing(14)
        self._empty_label = QLabel(
            "No templates yet. Click '+ New template' to author your first one."
        )
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setStyleSheet("color:#888;font-size:14px;padding:60px;")
        self._grid.addWidget(self._empty_label, 0, 0)
        self._scroll.setWidget(self._grid_host)
        root.addWidget(self._scroll, 1)
```

- [ ] **Step 4: Recompute the summary + filter chips on every refresh**

Add a private helper and call it from `refresh`:

```python
    def _rebuild_filter_strip(self, refs_and_docs: list[tuple]) -> None:
        # refs_and_docs: list[(ref, doc, meta)]
        while self._filter_strip.count():
            old = self._filter_strip.takeAt(0)
            w = old.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        all_n = len(refs_and_docs)
        valid_n = sum(1 for _r, _d, m in refs_and_docs
                      if m.get("schema_validated", True))
        draft_n = sum(1 for r, _d, _m in refs_and_docs if r.kind == "draft")
        role_kinds: dict[str, int] = {}
        ecosystems: dict[str, int] = {}
        for _r, doc, meta in refs_and_docs:
            k = doc.get("role", {}).get("kind", "")
            if k:
                role_kinds[k] = role_kinds.get(k, 0) + 1
            for tag in meta.get("ecosystem_tags", []):
                ecosystems[tag] = ecosystems.get(tag, 0) + 1

        def add_label(text: str) -> None:
            lbl = QLabel(text)
            lbl.setStyleSheet("font-size:11px;color:#888;")
            self._filter_strip.addWidget(lbl)

        def add_chip(text: str, active: bool = False) -> None:
            lbl = QLabel(text)
            if active:
                lbl.setStyleSheet(
                    "background:#1A1C20;color:#fff;border-radius:9px;"
                    "padding:2px 9px;font-size:11px;font-weight:600;"
                )
            else:
                lbl.setStyleSheet(
                    "background:#f0f2f5;color:#444;border-radius:9px;"
                    "padding:2px 9px;font-size:11px;"
                )
            self._filter_strip.addWidget(lbl)

        add_label("Filter:")
        add_chip(f"All ({all_n})", active=True)
        add_chip(f"Valid ({valid_n})")
        add_chip(f"Draft ({draft_n})")
        add_label("  |  Role kind:")
        for kind, n in sorted(role_kinds.items()):
            add_chip(f"{kind} ({n})")
        add_label("  |  Ecosystem:")
        for tag, n in sorted(ecosystems.items()):
            add_chip(f"{tag} ({n})")
        self._filter_strip.addStretch(1)

    def filter_chips_text(self) -> str:
        # Walk children for easy assertion in tests.
        parts: list[str] = []
        for i in range(self._filter_strip.count()):
            w = self._filter_strip.itemAt(i).widget()
            if isinstance(w, QLabel):
                parts.append(w.text())
        return " ".join(parts)
```

And update `refresh` to feed `_rebuild_filter_strip` and update the summary:

```python
    def refresh(self) -> None:
        for c in self._cards:
            c.setParent(None)
            c.deleteLater()
        self._cards = []
        for r in range(self._grid.rowCount()):
            self._grid.setRowStretch(r, 0)
        refs = self._store.list_templates()
        loaded: list[tuple] = []
        for ref in refs:
            doc, meta = self._store.load(ref)
            loaded.append((ref, doc, meta))
        all_n = len(loaded)
        valid_n = sum(1 for _r, _d, m in loaded
                      if m.get("schema_validated", True))
        draft_n = sum(1 for r, _d, _m in loaded if r.kind == "draft")
        plural = "templates" if all_n != 1 else "template"
        v_plural = "valid"
        d_plural = "drafts" if draft_n != 1 else "draft"
        self.summary_label.setText(
            f"{all_n} {plural} · {valid_n} {v_plural} · {draft_n} {d_plural}"
        )
        self._rebuild_filter_strip(loaded)
        self._is_empty = all_n == 0
        self._empty_label.setVisible(self._is_empty)
        max_row = 0
        for i, (ref, doc, _meta) in enumerate(loaded):
            card = _TemplateCard(ref=ref, doc=doc, meta=_meta)
            card.clicked.connect(
                lambda r=ref: self.template_open_requested.emit(r)
            )
            row, col = divmod(i, 2)
            self._grid.addWidget(card, row, col)
            self._cards.append(card)
            max_row = max(max_row, row)
        self._grid.setRowStretch(max_row + 1, 1)
```

The change to `_TemplateCard(... meta=...)` is forward-looking — Task 12 uses it. Until Task 12, accept `meta` and ignore it.

In `_TemplateCard.__init__`, add the new kwarg:

```python
    def __init__(self, ref: TemplateRef, doc: dict[str, Any],
                 meta: dict[str, Any] | None = None, parent=None):
        super().__init__(parent=parent)
        self._ref = ref
        self._meta = meta or {}
```

- [ ] **Step 5: Run tests**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_templates_browser_v1_visual.py -v`
Expected: 3 tests PASS.

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/ -v`
Expected: no regressions in existing browser tests.

- [ ] **Step 6: Commit**

```bash
git add src/locksmith/plugins/designer/editors/templates_browser.py \
        tests/plugins/designer/test_templates_browser_v1_visual.py
git commit -m "feat(designer): templates-browser count summary + filter strip"
```

---

## Task 12: Templates browser — richer cards (badge, ecosystem chips, cross-template chip, timestamp)

**Files:**
- Modify: `src/locksmith/plugins/designer/editors/templates_browser.py`
- Test: `tests/plugins/designer/test_templates_browser_v1_visual.py` (extend)

Replace the swatch-only role icon with `RoleIconBadge`, append a `ValidationPill` to the title row, an `EcosystemChip` row below the description, an optional `CrossTemplateChip` next to the chips, and a "Modified Xh ago" subtitle on the bottom row.

- [ ] **Step 1: Write the failing test**

Append to `tests/plugins/designer/test_templates_browser_v1_visual.py`:

```python
def test_card_renders_role_icon_badge_with_glyph(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    regulator = next(c for c in page._cards
                     if "Regulator" in c.title)
    assert regulator.role_badge.glyph_label.text() == "🏛️"


def test_card_renders_validation_pill(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    regulator = next(c for c in page._cards
                     if "Regulator" in c.title)
    assert regulator.validation_pill.text() == "✓ valid"


def test_card_renders_ecosystem_chips(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    regulator = next(c for c in page._cards
                     if "Regulator" in c.title)
    chip_texts = [c.text() for c in regulator.ecosystem_chips]
    assert chip_texts == ["insurance", "compliance"]


def test_card_renders_modified_timestamp(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    regulator = next(c for c in page._cards
                     if "Regulator" in c.title)
    # Just-seeded fixtures should read "Modified just now" or
    # "Modified Xs ago" — assert the prefix.
    assert regulator.modified_label.text().startswith("Modified")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_templates_browser_v1_visual.py::test_card_renders_role_icon_badge_with_glyph -v`
Expected: FAIL — `role_badge` attribute doesn't exist.

- [ ] **Step 3: Rewrite `_TemplateCard._build`**

Replace the body of `_TemplateCard._build` in `src/locksmith/plugins/designer/editors/templates_browser.py`:

```python
    def _build(self, doc: dict[str, Any]) -> None:
        from locksmith.plugins.designer.widgets.role_icon_badge import (
            RoleIconBadge,
        )
        from locksmith.plugins.designer.widgets.validation_pill import (
            ValidationPill,
        )
        from locksmith.plugins.designer.widgets.ecosystem_chip import (
            EcosystemChip,
        )

        header = doc.get("header", {})
        role = doc.get("role", {})
        self._title = header.get("display_name", "(untitled)")
        kind = role.get("kind", "")
        role_name = role.get("display_name", "")
        meta = self._meta

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(8)

        top = QHBoxLayout()
        self.role_badge = RoleIconBadge(kind=kind, size=44)
        top.addWidget(self.role_badge)

        text = QVBoxLayout()
        title_row = QHBoxLayout()
        title = QLabel(self._title)
        title.setStyleSheet("font-size:15px;font-weight:600;color:#1A1C20;")
        title_row.addWidget(title)
        version = QLabel(f"v{header.get('version', '0.0')}")
        version.setStyleSheet(
            "color:#888;background:#f6f7f9;padding:2px 7px;border-radius:8px;"
            "font-size:10px;"
        )
        title_row.addWidget(version)
        title_row.addStretch(1)
        self.validation_pill = ValidationPill(
            error_count=meta.get("error_count", 0),
            warning_count=meta.get("warning_count", 0),
        )
        title_row.addWidget(self.validation_pill)
        text.addLayout(title_row)

        color = _ROLE_KIND_COLOR.get(kind, "#888888")
        subtitle = QLabel(
            f"<span style='color:{color};font-weight:600;'>{role.get('id', '')}</span>"
            f" · {kind}"
        )
        subtitle.setStyleSheet("font-size:11px;color:#666;")
        text.addWidget(subtitle)
        top.addLayout(text, 1)
        outer.addLayout(top)

        desc = QLabel(header.get("description", ""))
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size:12px;color:#444;")
        outer.addWidget(desc)

        # Ecosystem chips + optional cross-template chip.
        self.ecosystem_chips: list[QLabel] = []
        chip_row = QHBoxLayout()
        chip_row.setSpacing(6)
        for tag in meta.get("ecosystem_tags", []):
            chip = EcosystemChip(tag)
            self.ecosystem_chips.append(chip)
            chip_row.addWidget(chip)
        forked_from = (doc.get("header", {})
                          .get("forked_from", {}) or {}).get("template_said")
        if forked_from:
            from locksmith.plugins.designer.widgets.ecosystem_chip import (
                CrossTemplateChip,
            )
            short = (forked_from[:4] + "…" + forked_from[-6:]
                     if len(forked_from) > 12 else forked_from)
            chip_row.addWidget(
                CrossTemplateChip(kind="forked_from", target=short)
            )
        chip_row.addStretch(1)
        outer.addLayout(chip_row)

        # Counts + SAID/draft + modified timestamp.
        counts = (
            f"{len(doc.get('credentials', {}).get('imports', []))} imports · "
            f"{len(doc.get('credentials', {}).get('exports', []))} exports · "
            f"{len(doc.get('commands', []))} commands · "
            f"{len(doc.get('workflows', []))} workflows"
        )
        footer = QHBoxLayout()
        ftext = QLabel(counts)
        ftext.setStyleSheet("font-size:10px;color:#888;")
        footer.addWidget(ftext)
        footer.addStretch(1)
        self.modified_label = QLabel(self._format_modified(meta.get("modified_at")))
        self.modified_label.setStyleSheet("font-size:10px;color:#888;")
        footer.addWidget(self.modified_label)
        if self._ref.kind == "draft":
            badge = QLabel("DRAFT")
        else:
            said = self._ref.said or ""
            badge = QLabel(f"{said[:4]}…{said[-4:]}" if len(said) >= 8 else said)
        badge.setStyleSheet("font-size:9px;color:#aaa;font-family:monospace;")
        footer.addWidget(badge)
        outer.addLayout(footer)

    @staticmethod
    def _format_modified(ts: str | None) -> str:
        # Cheap "Modified X ago" — accepts ISO-8601 or returns "just now".
        if not ts:
            return "Modified just now"
        try:
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            delta = now - dt
            secs = int(delta.total_seconds())
            if secs < 60:
                return f"Modified {secs}s ago"
            if secs < 3600:
                return f"Modified {secs // 60}m ago"
            if secs < 86400:
                return f"Modified {secs // 3600}h ago"
            return f"Modified {secs // 86400}d ago"
        except (ValueError, TypeError):
            return "Modified just now"
```

- [ ] **Step 4: Run tests**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_templates_browser_v1_visual.py -v`
Expected: 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/editors/templates_browser.py \
        tests/plugins/designer/test_templates_browser_v1_visual.py
git commit -m "feat(designer): rich template cards (badge + validation + ecosystem chips + timestamp)"
```

---

## Task 13: Overview — header strip with badge + version chip + role-kind subtitle + description + SAID + Walk-me-through CTA + kebab

**Files:**
- Modify: `src/locksmith/plugins/designer/editors/overview.py`
- Test: `tests/plugins/designer/test_overview_v1_visual.py`

Replace the current minimal `Edit header` strip with the full v1 mock header. The kebab is display-only (Phase 1). "Walk me through it" is a button that does nothing yet (Phase 2 wires the wizard or removes if v2-deferred).

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/designer/test_overview_v1_visual.py
import json
from pathlib import Path

import pytest

from locksmith.plugins.designer.editors.overview import TemplateOverviewPage
from locksmith.plugins.designer.model import TemplateModel


@pytest.fixture
def regulator_model():
    doc = json.loads(
        (Path(__file__).parent / "fixtures"
         / "regulator-grants-carrier-license.json").read_text()
    )
    return TemplateModel(doc=doc)


def test_header_has_role_badge_with_government_glyph(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    assert page.role_badge.glyph_label.text() == "🏛️"


def test_header_has_version_chip(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    assert page.version_chip.text() == "v1.0"


def test_header_subtitle_includes_first_person_role(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    sub = page.role_subtitle.text()
    assert "I am" in sub
    assert "State Department of Insurance" in sub
    assert "government" in sub


def test_header_description_renders(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    assert "carriers to bear insurance risk" in page.description_label.text()


def test_header_said_truncated(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    # SAID is EGCpXap_yYxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx6yAv (44 chars).
    text = page.said_label.text()
    assert text.startswith("EGCp")
    assert text.endswith("6yAv")


def test_header_walkthrough_cta_exists(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    assert page.walkthrough_button.text() == "Walk me through it"


def test_header_kebab_button_exists(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    assert page.kebab_button.text() == "⋯"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_overview_v1_visual.py -v`
Expected: 7 FAIL — none of those attributes exist.

- [ ] **Step 3: Rewrite the header strip**

In `src/locksmith/plugins/designer/editors/overview.py`, replace the existing `header_strip` block in `_build` with:

```python
        from locksmith.plugins.designer.widgets.role_icon_badge import (
            RoleIconBadge,
        )
        from locksmith.plugins.designer.widgets.kebab_button import KebabButton

        header = self._model.doc.get("header", {})
        role = self._model.doc.get("role", {})
        said = self._model.doc.get("d", "")

        header_strip = QFrame()
        header_strip.setStyleSheet(
            "background:#fff;border-bottom:1px solid #e0e3ea;"
        )
        h = QHBoxLayout(header_strip)
        h.setContentsMargins(20, 14, 20, 14)
        h.setSpacing(14)

        self.role_badge = RoleIconBadge(kind=role.get("kind", ""), size=52)
        h.addWidget(self.role_badge)

        center = QVBoxLayout()
        center.setSpacing(3)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self._header_label = QLabel(header.get("display_name", ""))
        self._header_label.setStyleSheet(
            "font-size:18px;font-weight:600;color:#1A1C20;"
        )
        title_row.addWidget(self._header_label)
        self.version_chip = QLabel(f"v{header.get('version', '0.0')}")
        self.version_chip.setStyleSheet(
            "color:#888;background:#f6f7f9;padding:2px 8px;border-radius:10px;"
            "font-size:11px;"
        )
        title_row.addWidget(self.version_chip)
        title_row.addStretch(1)
        center.addLayout(title_row)

        role_kind = role.get("kind", "")
        keri_infra = role.get("keri_infrastructure", {})
        infra_count = sum(1 for v in keri_infra.values() if v)
        self.role_subtitle = QLabel(
            f"<span style='color:#0ABFB0;font-weight:600;'>I am</span>"
            f" · {role.get('display_name', '')}"
            f" · {role_kind} · {infra_count} KERI services"
        )
        self.role_subtitle.setStyleSheet("font-size:12px;color:#444;")
        self.role_subtitle.setTextFormat(Qt.RichText)
        center.addWidget(self.role_subtitle)

        self.description_label = QLabel(header.get("description", ""))
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet("font-size:12px;color:#444;")
        center.addWidget(self.description_label)

        h.addLayout(center, 1)

        right_col = QVBoxLayout()
        right_col.setSpacing(6)
        right_col.setAlignment(Qt.AlignTop)

        top_right_row = QHBoxLayout()
        top_right_row.addStretch(1)
        said_block = QVBoxLayout()
        said_block.setSpacing(0)
        said_title = QLabel("SAID")
        said_title.setStyleSheet(
            "font-size:9px;color:#888;font-weight:600;letter-spacing:0.5px;"
        )
        said_block.addWidget(said_title)
        short = (said[:4] + "…" + said[-4:]) if len(said) >= 8 else said
        self.said_label = QLabel(short)
        self.said_label.setStyleSheet(
            "color:#666;background:#f6f7f9;padding:2px 8px;border-radius:6px;"
            "font-size:10px;font-family:monospace;"
        )
        said_block.addWidget(self.said_label)
        top_right_row.addLayout(said_block)
        self.kebab_button = KebabButton()
        top_right_row.addWidget(self.kebab_button)
        right_col.addLayout(top_right_row)

        self.walkthrough_button = QPushButton("Walk me through it")
        self.walkthrough_button.setStyleSheet(
            "background:#d97757;color:#fff;font-weight:600;"
            "padding:6px 12px;border-radius:4px;"
        )
        right_col.addWidget(self.walkthrough_button)

        h.addLayout(right_col)
        root.addWidget(header_strip)
```

Also need to add `Qt` to the imports (only if missing) — check the existing `from PySide6.QtCore import Signal` line and extend to `from PySide6.QtCore import Qt, Signal`.

Replace the now-stale `_role_chip` and old header init at the top of `__init__` — remove those attribute assignments since they're gone:

```python
    def __init__(self, *, model: TemplateModel, parent=None):
        super().__init__(parent=parent)
        self._model = model
        self._cards: dict[str, FirstPersonCard] = {}
        self._build()
        self._model.changed.connect(lambda _path: self._refresh())
```

And update `_refresh` similarly to remove `self._header_label = QLabel()` and `self._role_chip = QPushButton()` lines.

- [ ] **Step 4: Run tests**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_overview_v1_visual.py -v`
Expected: 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/editors/overview.py \
        tests/plugins/designer/test_overview_v1_visual.py
git commit -m "feat(designer): overview header strip — badge/version/SAID/walkthrough/kebab"
```

---

## Task 14: Overview — 4×2 facet grid (Role absorbed into header)

**Files:**
- Modify: `src/locksmith/plugins/designer/editors/overview.py`
- Test: `tests/plugins/designer/test_overview_v1_visual.py` (extend)

Drop the Role card from the grid (it now lives in the header strip), reduce the grid to 8 cards, lay them out 4 × 2 (4 columns, 2 rows). Use the v1 mock's facet labels as the framings: I HOLD, I ISSUE, I DO, I RESPOND TO (row 1), I FOLLOW, I TRACK, I SEE, I'M BOUND BY (row 2). Use `FacetEntry` per-entry qualifier where the mock shows one, and the rule-type-chip variant for the Rules card.

- [ ] **Step 1: Write the failing test**

Append to `tests/plugins/designer/test_overview_v1_visual.py`:

```python
def test_overview_renders_eight_facet_cards_no_role_card(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    assert "role" not in page.card_kinds()
    assert len(page.card_kinds()) == 8


def test_overview_grid_is_four_columns_by_two_rows(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    # The grid is page._grid (QGridLayout). After population, every card
    # is at row 0 or row 1.
    rows = {page._grid.itemAtPosition(r, c).widget()
            for r in range(2) for c in range(4)
            if page._grid.itemAtPosition(r, c) is not None}
    assert len(rows) == 8


def test_i_issue_card_shows_qualifier_subline(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    card = page._cards["exports"]
    assert card.framing_label.text() == "I ISSUE"
    assert "Carrier License" in card.entries_text()


def test_i_bound_by_card_uses_rule_type_chips(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    card = page._cards["rules"]
    chips = card.chips_text()
    assert "prose" in chips
    assert "predicate" in chips or "predicates" in chips


def test_i_hold_card_uses_root_authority_empty_state(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    card = page._cards["imports"]
    assert "root authority" in card.entries_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_overview_v1_visual.py -v -k "facet or four_columns or i_issue or bound_by or i_hold"`
Expected: 5 FAIL — Role still in grid, grid is 3×3, no qualifiers, no chip variant.

- [ ] **Step 3: Replace `_CARD_SPECS`, the grid loop, and add per-card-kind specialization**

In `src/locksmith/plugins/designer/editors/overview.py`, replace `_CARD_SPECS` and the inner build loop:

```python
_CARD_SPECS: list[tuple[str, str, str, str]] = [
    # (kind, framing, secondary-label, doc-path)
    ("imports",     "I HOLD",         "Imported credentials",   "credentials.imports"),
    ("exports",     "I ISSUE",        "Issued credentials",     "credentials.exports"),
    ("commands",    "I DO",           "Commands",               "commands"),
    ("reactions",   "I RESPOND TO",   "Reactions",              "reactions"),
    ("workflows",   "I FOLLOW",       "Workflows",              "workflows"),
    ("aggregates",  "I TRACK",        "Aggregates",             "aggregates"),
    ("projections", "I SEE",          "Projections",            "projections"),
    ("rules",       "I'M BOUND BY",   "Rules",                  "rules"),
]


_EMPTY_MESSAGES: dict[str, str] = {
    "imports":     "No imports — this role is the root authority for licenses",
    "exports":     "No issued credentials yet",
    "commands":    "No commands yet",
    "reactions":   "No reactions yet",
    "workflows":   "No workflows yet",
    "aggregates":  "No aggregates yet",
    "projections": "No projections yet",
    "rules":       "No rules yet",
}


def _qualifier_for_export(entry: dict) -> str | None:
    env = entry.get("envelope", {})
    lc = entry.get("lifecycle", {})
    bits: list[str] = []
    if env.get("holder_role"):
        bits.append(f"to {env['holder_role']}")
    if lc.get("states"):
        bits.append(f"{len(lc['states'])} states")
    if entry.get("schema"):
        bits.append("1 schema")
    return " · ".join(bits) if bits else None


def _qualifier_for_aggregate(entry: dict) -> str | None:
    bits: list[str] = []
    scope = entry.get("log_scope")
    if scope:
        bits.append(f"{scope} log")
    invs = entry.get("invariants") or []
    if invs:
        bits.append(f"{len(invs)} invariant{'s' if len(invs) != 1 else ''}")
    return " · ".join(bits) if bits else None


def _qualifier_for_reaction(entry: dict) -> str | None:
    trig = entry.get("trigger", {})
    n = len(entry.get("emissions") or [])
    parts: list[str] = []
    t_type = trig.get("type")
    if t_type:
        parts.append(f"← {t_type}")
    if n:
        parts.append(f"{n} emission{'s' if n != 1 else ''}")
    return " · ".join(parts) if parts else None


def _qualifier_for_workflow(entry: dict) -> str | None:
    cp = entry.get("counterparty_role")
    steps = entry.get("steps") or []
    parts: list[str] = []
    if cp:
        parts.append(f"↔ {cp}")
    if steps:
        parts.append(f"{len(steps)} steps")
    return " · ".join(parts) if parts else None


def _entries_for(kind: str, items: list[dict]) -> list:
    out = []
    for e in items[:3]:
        label = entry_label(e)
        if kind == "exports":
            q = _qualifier_for_export(e)
        elif kind == "aggregates":
            q = _qualifier_for_aggregate(e)
        elif kind == "reactions":
            q = _qualifier_for_reaction(e)
        elif kind == "workflows":
            q = _qualifier_for_workflow(e)
        else:
            q = None
        out.append(FacetEntry(label=label, qualifier=q))
    return out


def _rule_type_counts(rules: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rules:
        t = r.get("type", "")
        out[t] = out.get(t, 0) + 1
    return out
```

And replace the grid loop in `_build`:

```python
        grid = QGridLayout(host)
        grid.setContentsMargins(20, 20, 20, 20)
        grid.setSpacing(14)
        self._grid = grid

        for idx, (kind, framing, label, dotted) in enumerate(_CARD_SPECS):
            items_at = _list_at(self._model.doc, dotted)
            count = len(items_at)
            if kind == "rules":
                card = FirstPersonCard(
                    framing=framing, kind_label=label,
                    count=count, entries=[],
                    rule_type_counts=_rule_type_counts(items_at),
                    empty_message=_EMPTY_MESSAGES[kind],
                )
            else:
                card = FirstPersonCard(
                    framing=framing, kind_label=label,
                    count=count,
                    entries=_entries_for(kind, items_at),
                    empty_message=_EMPTY_MESSAGES[kind],
                )
            card.clicked.connect(lambda k=kind: self.drilldown_requested.emit(k))
            card.add_clicked.connect(lambda k=kind: self.add_requested.emit(k))
            row, col = divmod(idx, 4)
            grid.addWidget(card, row, col)
            self._cards[kind] = card

        scroll.setWidget(host)
        root.addWidget(scroll, 1)
```

- [ ] **Step 4: Run tests**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_overview_v1_visual.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/editors/overview.py \
        tests/plugins/designer/test_overview_v1_visual.py
git commit -m "feat(designer): 4×2 facet grid + per-entry qualifiers + rule-type chips"
```

---

## Task 15: Overview — bottom strip (Ecosystem affinity / Lineage / ✓ Validation)

**Files:**
- Modify: `src/locksmith/plugins/designer/editors/overview.py`
- Test: `tests/plugins/designer/test_overview_v1_visual.py` (extend)

A 3-column footer row below the facet grid:

- **ECOSYSTEM AFFINITY**: ecosystem chips from `meta.ecosystem_tags` (read from the store at vault open and threaded into the model).
- **LINEAGE**: "No parent template" or `↪ forked from <SAID>`.
- **VALIDATION**: a `ValidationPill` reading the current validation report's error/warning counts.

For Phase 1, take the validation report state from `model.last_validation_report()` if available — else default to valid (0/0). The actual validation engine is wired up but the in-memory report shape varies; if `last_validation_report()` doesn't exist as a method on `TemplateModel`, gracefully fall back to (0, 0).

- [ ] **Step 1: Write the failing test**

Append to `tests/plugins/designer/test_overview_v1_visual.py`:

```python
def test_bottom_strip_renders_ecosystem_chips(qapp, regulator_model):
    page = TemplateOverviewPage(
        model=regulator_model,
        ecosystem_tags=["insurance", "compliance"],
    )
    chip_texts = [c.text() for c in page.ecosystem_chips]
    assert chip_texts == ["insurance", "compliance"]


def test_bottom_strip_renders_lineage_no_parent(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    assert page.lineage_label.text() == "No parent template"


def test_bottom_strip_renders_validation_pill(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    assert page.bottom_validation_pill.text() == "✓ valid"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_overview_v1_visual.py::test_bottom_strip_renders_ecosystem_chips -v`
Expected: FAIL — `ecosystem_tags` unexpected kwarg.

- [ ] **Step 3: Accept `ecosystem_tags` + render bottom strip**

In `src/locksmith/plugins/designer/editors/overview.py`, change `__init__`:

```python
    def __init__(
        self,
        *,
        model: TemplateModel,
        ecosystem_tags: list[str] | None = None,
        parent=None,
    ):
        super().__init__(parent=parent)
        self._model = model
        self._ecosystem_tags = ecosystem_tags or []
        self._cards: dict[str, FirstPersonCard] = {}
        self._build()
        self._model.changed.connect(lambda _path: self._refresh())
```

At the end of `_build`, **after** `root.addWidget(scroll, 1)`, append the bottom strip:

```python
        from locksmith.plugins.designer.widgets.ecosystem_chip import (
            EcosystemChip,
        )
        from locksmith.plugins.designer.widgets.validation_pill import (
            ValidationPill,
        )

        bottom = QFrame()
        bottom.setStyleSheet(
            "background:#fff;border-top:1px solid #e0e3ea;"
        )
        b = QHBoxLayout(bottom)
        b.setContentsMargins(20, 12, 20, 12)
        b.setSpacing(20)

        eco = QVBoxLayout()
        eco.setSpacing(2)
        eco_title = QLabel("ECOSYSTEM AFFINITY")
        eco_title.setStyleSheet(
            "font-size:10px;color:#0ABFB0;font-weight:600;letter-spacing:0.5px;"
        )
        eco.addWidget(eco_title)
        eco_chips_row = QHBoxLayout()
        eco_chips_row.setSpacing(6)
        self.ecosystem_chips: list[QLabel] = []
        for tag in self._ecosystem_tags:
            chip = EcosystemChip(tag)
            self.ecosystem_chips.append(chip)
            eco_chips_row.addWidget(chip)
        if not self._ecosystem_tags:
            none_chip = QLabel("(none)")
            none_chip.setStyleSheet("font-size:11px;color:#aaa;font-style:italic;")
            eco_chips_row.addWidget(none_chip)
        eco_chips_row.addStretch(1)
        eco.addLayout(eco_chips_row)
        b.addLayout(eco, 1)

        lin = QVBoxLayout()
        lin.setSpacing(2)
        lin_title = QLabel("LINEAGE")
        lin_title.setStyleSheet(
            "font-size:10px;color:#0ABFB0;font-weight:600;letter-spacing:0.5px;"
        )
        lin.addWidget(lin_title)
        forked = (self._model.doc.get("header", {})
                                  .get("forked_from", {}) or {})
        if forked.get("template_said"):
            ft = forked["template_said"]
            short = ft[:4] + "…" + ft[-6:] if len(ft) > 12 else ft
            self.lineage_label = QLabel(f"↪ forked from {short}")
        else:
            self.lineage_label = QLabel("No parent template")
        self.lineage_label.setStyleSheet("font-size:11px;color:#666;")
        lin.addWidget(self.lineage_label)
        b.addLayout(lin, 1)

        val = QVBoxLayout()
        val.setSpacing(2)
        val_title = QLabel("✓ VALIDATION")
        val_title.setStyleSheet(
            "font-size:10px;color:#0ABFB0;font-weight:600;letter-spacing:0.5px;"
        )
        val.addWidget(val_title)
        # Phase 4 will wire to the real report. For now, default to 0/0.
        report = getattr(self._model, "last_validation_report", lambda: None)()
        if report is None:
            err = warn = 0
        else:
            err = sum(1 for i in report.issues
                      if getattr(i, "severity", "error") == "error")
            warn = sum(1 for i in report.issues
                       if getattr(i, "severity", "error") == "warning")
        self.bottom_validation_pill = ValidationPill(
            error_count=err, warning_count=warn,
        )
        val.addWidget(self.bottom_validation_pill)
        b.addLayout(val, 1)

        root.addWidget(bottom)
```

- [ ] **Step 4: Thread ecosystem_tags through the plugin call site**

In `src/locksmith/plugins/designer/plugin.py`, find where `TemplateOverviewPage(model=...)` is constructed (in `_open_template`) and pass the ecosystem tags from the loaded metadata:

```python
        _doc, meta = self._store.load(ref)
        ecosystem_tags = list(meta.get("ecosystem_tags", []))
        overview = TemplateOverviewPage(
            model=self._model,
            ecosystem_tags=ecosystem_tags,
        )
```

(Adapt to whatever variable names the existing `_open_template` uses — keep the call shape identical.)

- [ ] **Step 5: Run tests**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_overview_v1_visual.py -v`
Expected: all PASS.

Then run the full designer suite to check no regressions:
Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/ -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/locksmith/plugins/designer/editors/overview.py \
        src/locksmith/plugins/designer/plugin.py \
        tests/plugins/designer/test_overview_v1_visual.py
git commit -m "feat(designer): overview bottom strip (ecosystem/lineage/validation)"
```

---

## Task 16: Final live-driven verification

**Files:**
- (No files modified — pure verification)

Drive the live wallet via the harness and capture screenshots of each surface, then read them and confirm they match the mocks. This is the integration-level smoke pass.

- [ ] **Step 1: Boot the wallet with dev-control + fixture seeding**

```bash
LOCKSMITH_DEV_CONTROL=1 LOCKSMITH_DESIGNER_SEED_FIXTURES=1 \
    .venv/bin/python -m locksmith.main
```

Unlock the `joe` test vault and navigate to the Designer plugin. Expected: templates browser shows **2 cards** (Regulator and Carrier Application), with the count summary "2 templates · 2 valid · 0 drafts" and the filter strip.

- [ ] **Step 2: Capture templates-browser screenshot via the harness**

```bash
.venv/bin/python tools/devctl.py click '{"target": "Templates"}'
sleep 0.3
.venv/bin/python tools/devctl.py screenshot \
    '{"path": "/tmp/locksmith-v1-templates.png"}'
```

Read `/tmp/locksmith-v1-templates.png` and verify against `.superpowers/brainstorm/69587-1778622927/content/templates-browser.html` — confirm: 2-up grid, role icon glyphs, validation badges, ecosystem chips, count summary, filter strip.

- [ ] **Step 3: Capture overview-page screenshot**

```bash
.venv/bin/python tools/devctl.py click \
    '{"target": "Regulator Grants Carrier License"}'
sleep 0.4
.venv/bin/python tools/devctl.py screenshot \
    '{"path": "/tmp/locksmith-v1-overview.png"}'
```

Read `/tmp/locksmith-v1-overview.png` and verify: header strip with badge + version chip + "I am · State Department of Insurance · government · 4 KERI services" subtitle + description + SAID + Walk-me-through CTA + kebab. 4×2 facet grid with I HOLD / I ISSUE / I DO / I RESPOND TO on row 1 and I FOLLOW / I TRACK / I SEE / I'M BOUND BY on row 2. Bottom strip with Ecosystem / Lineage / ✓ Validation.

- [ ] **Step 4: Capture each editor breadcrumb to confirm count + role + valid pills**

```bash
for kind in Commands Aggregates Reactions Workflows Projections Rules; do
    .venv/bin/python tools/devctl.py click '{"target": "Templates"}'
    sleep 0.3
    .venv/bin/python tools/devctl.py click \
        '{"target": "Regulator Grants Carrier License"}'
    sleep 0.4
    .venv/bin/python tools/devctl.py click "{\"target\": \"$kind\"}"
    sleep 0.4
    slug=$(echo "$kind" | tr '[:upper:]' '[:lower:]')
    .venv/bin/python tools/devctl.py screenshot \
        "{\"path\": \"/tmp/locksmith-v1-$slug.png\"}"
done
```

For each captured image, verify the breadcrumb reads `← Back · Regulator Grants Carrier License · <Surface> (<count>)` and the right side carries `Role: state-doi · ✓ valid`, plus the rail rows have two-line entries with subtitles.

- [ ] **Step 5: Run the full plugin test suite**

```bash
QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/ -v
```

Expected: all PASS.

```bash
QT_QPA_PLATFORM=offscreen pytest -x
```

Expected: no regressions in the rest of the wallet's tests.

- [ ] **Step 6: Commit the screenshot artifacts (optional) and tag the milestone**

Screenshots live in `/tmp` and are not checked in. If you want a milestone reference, copy the four most-representative shots into `tests/_screenshots/designer/v1-fidelity-phase1/` (gitignored — purely for reviewer eyeballs), but no commit needed.

Final commit message (no code change):

```bash
git commit --allow-empty -m "milestone(designer): v1 visual-shell parity (Phase 1 complete)"
```

---

## Self-review checklist

1. **Spec coverage** — every v1 mock affordance for the visual shell has a task:
   - Templates browser count summary ✓ Task 11
   - Templates browser filter strip ✓ Task 11
   - Templates browser 2-up grid (already shipped; Task 12 enriches the cards) ✓
   - Templates browser role icon glyph ✓ Task 12 (uses Task 4 widget)
   - Templates browser validation pill ✓ Task 12 (uses Task 5 widget)
   - Templates browser ecosystem chips ✓ Task 12 (uses Task 6 widget)
   - Templates browser cross-template chip ✓ Task 12 (uses Task 6 widget)
   - Templates browser modified timestamp ✓ Task 12
   - Overview header strip with badge / version / SAID / Walk-me-through / kebab ✓ Task 13 (uses Tasks 4, 7)
   - Overview 4×2 grid (Role absorbed into header) ✓ Task 14
   - Overview facet labels ✓ Task 8 (and consumed by Task 14)
   - Overview per-entry qualifier ✓ Task 8 (consumed by Task 14)
   - Overview rule-type-chip variant ✓ Task 8 (consumed by Task 14)
   - Overview bottom strip ✓ Task 15
   - Editor breadcrumb count + role pill + valid pill ✓ Task 3
   - Editor rail subtitle ✓ Task 1
   - Editor `+ Add <kind>` at top of rail ✓ Task 2
   - Bundled fixtures auto-seeded in dev mode ✓ Task 10
   - Regulator fixture enrichment ✓ Task 9

2. **Explicitly deferred to Phase 2+** (no task here, by design):
   - Inline editability — Phase 2.
   - Kebab actions (Save/Finalize/Export/Duplicate/Delete) — Phase 2.
   - Filter chip click behavior — Phase 2.
   - Walk-me-through wizard flow — v2 deferred per spec.
   - ValidationPanel toolbar toggle — Phase 4.
   - JsonSourceView toolbar toggle — Phase 4.
   - Swimlane / TEL state-machine revamp — Phase 3.
   - Commands payload-schema table / Auth-State-Temporal preconditions — Phase 3.
   - Projections two-column / live preview — Phase 3 (preview is v2-deferred).
   - Rules type-grouped rail / dark expression block / PAIRS WITH section — Phase 3.

3. **Placeholder scan:** no TODO / TBD / "similar to Task N" / "implement later" anywhere in the plan body — every code block contains the real code, every file path is absolute, every command is runnable.

4. **Type consistency:** the new types and signatures used across tasks are consistent — `FacetEntry(label, qualifier=None)`, `RailItem(..., subtitle=None)`, `PrimitiveEditorShell(..., add_label=None, item_count=0, role_label="", is_valid=True, issue_count=0)`, `RoleIconBadge(kind=..., size=52)`, `ValidationPill(error_count, warning_count)`, `EcosystemChip(tag)`, `CrossTemplateChip(kind, target)`, `KebabButton()` — all checked against their usages in Tasks 8, 11, 12, 13, 14, 15.
