# Designer Plugin — V1 Fidelity Phase 3a (Shared infrastructure + Phase 4 toolbar toggles) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the cross-cutting widgets and toolbar toggle infrastructure that Phase 3b/3c/3d will depend on. Specifically: a dark code block for UEL expressions, a type-color badge for rules, and the toggle-on/toggle-off wiring for `ValidationPanel` and `JsonSourceView` on every editor + Overview. **No per-editor content changes** in this plan — those live in 3b/3c/3d. (Per-editor-only widgets like `EditorTabBar` and `RulePicker` move to 3b where they're first used.)

**Architecture:** Add two small new widgets under `widgets/`. Augment `PrimitiveEditorShell` with a toolbar (top-right of the breadcrumb strip) carrying two toggle buttons — `panel` and `JSON` — that show/hide a side panel (right edge) and a bottom drawer respectively. Each editor instantiates its own `ValidationPanel` and `JsonSourceView` and registers them with the shell via `set_side_panel` / `set_bottom_panel`. `TemplateOverviewPage` gains the same two toggles in its header. No model write paths land in this phase.

**Tech Stack:** PySide6, pytest with `QT_QPA_PLATFORM=offscreen`, existing `ValidationPanel` + `JsonSourceView` widgets (already coded — just need instantiation and toggle wiring), `TemplateModel`, `compute_crossrefs`, validation engine.

---

## File Structure

**Created in this plan:**

```
src/locksmith/plugins/designer/widgets/
├── dark_code_block.py        # syntax-friendly dark code block for UEL expressions
└── type_color_badge.py       # colored pill for rule.type / similar typed entities

tests/plugins/designer/
├── test_dark_code_block_visual.py
├── test_type_color_badge_visual.py
├── test_shell_toggles_visual.py
└── test_overview_toggles_visual.py
```

**Modified in this plan:**

```
src/locksmith/plugins/designer/widgets/
└── primitive_editor_shell.py  # adds toolbar with panel/JSON toggles + side/bottom panel slots

src/locksmith/plugins/designer/editors/
├── overview.py                # adds toolbar with same toggles + side/bottom panels
├── commands.py                # instantiates ValidationPanel + JsonSourceView, registers with shell
├── aggregates.py              # same
├── reactions.py               # same
├── workflows.py               # same
├── projections.py             # same
├── rules.py                   # same
├── exports.py                 # same
└── imports.py                 # same
```

**Out of scope (deferred to 3b/3c/3d):** EditorTabBar (only Exports needs it), RulePicker chip picker (only Commands preconditions needs it first), per-editor content restructuring, TEL state-machine revamp, swimlane v2, payload-schema table, etc.

---

## Task 1: DarkCodeBlock widget

**Files:**
- Create: `src/locksmith/plugins/designer/widgets/dark_code_block.py`
- Test: `tests/plugins/designer/test_dark_code_block_visual.py`

A read-only monospace `QPlainTextEdit` with dark background + light text — a code-style display block for UEL expressions, fold expressions, and similar. Differentiates code from prose at a glance.

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/designer/test_dark_code_block_visual.py
from locksmith.plugins.designer.widgets.dark_code_block import DarkCodeBlock


def test_renders_supplied_text(qapp):
    block = DarkCodeBlock("event.attributes.amount > 100")
    assert block.toPlainText() == "event.attributes.amount > 100"


def test_is_read_only(qapp):
    block = DarkCodeBlock("anything")
    assert block.isReadOnly() is True


def test_uses_dark_palette(qapp):
    block = DarkCodeBlock("anything")
    style = block.styleSheet()
    assert "#1A1C20" in style or "#222" in style
    # text color should be light against the dark background
    assert "#E0E0E0" in style or "#fff" in style or "#eaeaea" in style.lower()


def test_empty_string_renders_clean(qapp):
    block = DarkCodeBlock("")
    assert block.toPlainText() == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_dark_code_block_visual.py -v`
Expected: `ModuleNotFoundError: No module named '...dark_code_block'`.

- [ ] **Step 3: Implement DarkCodeBlock**

```python
# src/locksmith/plugins/designer/widgets/dark_code_block.py
# -*- encoding: utf-8 -*-
"""DarkCodeBlock: read-only dark-themed code display for UEL/etc.

Differentiates code (expressions, fold formulas, payload schemas) from
prose at a glance. Read-only by design — editing happens via the
JsonSourceView toolbar toggle, never inline.
"""
from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QPlainTextEdit


class DarkCodeBlock(QPlainTextEdit):
    def __init__(self, text: str = "", parent=None):
        super().__init__(parent=parent)
        self.setReadOnly(True)
        self.setPlainText(text)
        mono = QFont("Menlo")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(10)
        self.setFont(mono)
        self.setStyleSheet(
            "QPlainTextEdit{"
            "background:#1A1C20;color:#E0E0E0;"
            "border:1px solid #2a2c30;border-radius:4px;"
            "padding:8px 10px;"
            "}"
        )
        self.setFixedHeight(80)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_dark_code_block_visual.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/widgets/dark_code_block.py \
        tests/plugins/designer/test_dark_code_block_visual.py
git commit -m "feat(designer): DarkCodeBlock widget for UEL expressions"
```

---

## Task 2: TypeColorBadge widget

**Files:**
- Create: `src/locksmith/plugins/designer/widgets/type_color_badge.py`
- Test: `tests/plugins/designer/test_type_color_badge_visual.py`

A colored pill carrying a rule-type name (e.g. `PREDICATE`, `LEGAL PROSE`, `VALIDATION`, `BINDING LINK`). Colors match the existing FacetCard rule-type chip palette so the Overview and Rules editor agree.

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/designer/test_type_color_badge_visual.py
from locksmith.plugins.designer.widgets.type_color_badge import TypeColorBadge


def test_predicate_badge_uses_teal(qapp):
    b = TypeColorBadge("predicate")
    assert b.text() == "PREDICATE"
    assert "#0ABFB0" in b.styleSheet()


def test_legal_prose_renders_two_word_uppercase(qapp):
    b = TypeColorBadge("legal_prose")
    assert b.text() == "LEGAL PROSE"
    assert "#A36AE6" in b.styleSheet()


def test_validation_uses_orange(qapp):
    b = TypeColorBadge("validation")
    assert b.text() == "VALIDATION"
    assert "#D97757" in b.styleSheet()


def test_binding_link_uses_grey(qapp):
    b = TypeColorBadge("binding_link")
    assert b.text() == "BINDING LINK"
    assert "#666" in b.styleSheet() or "#666666" in b.styleSheet()


def test_unknown_type_falls_back_to_neutral(qapp):
    b = TypeColorBadge("mystery_kind")
    assert b.text() == "MYSTERY KIND"
    assert "#888" in b.styleSheet() or "#888888" in b.styleSheet()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_type_color_badge_visual.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement TypeColorBadge**

```python
# src/locksmith/plugins/designer/widgets/type_color_badge.py
# -*- encoding: utf-8 -*-
"""TypeColorBadge: colored pill carrying a typed-entity name.

Used to make rule types (predicate / legal_prose / validation / binding_link)
scannable at a glance in the Rules editor right pane, and reusable for any
other typed primitive whose categories want a consistent color language.
"""
from __future__ import annotations

from PySide6.QtWidgets import QLabel


_COLORS: dict[str, str] = {
    "predicate":              "#0ABFB0",
    "legal_prose":            "#A36AE6",
    "prose":                  "#A36AE6",
    "behavioral_expectation": "#A36AE6",
    "validation":             "#D97757",
    "computational":          "#888888",
    "binding_link":           "#666666",
}


class TypeColorBadge(QLabel):
    def __init__(self, type_id: str, parent=None):
        super().__init__(parent=parent)
        color = _COLORS.get(type_id, "#888888")
        self.setText(type_id.replace("_", " ").upper())
        self.setStyleSheet(
            f"color:{color};background:transparent;"
            f"border:1px solid {color};border-radius:9px;"
            "padding:2px 8px;font-size:10px;font-weight:600;"
            "letter-spacing:0.5px;"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_type_color_badge_visual.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/widgets/type_color_badge.py \
        tests/plugins/designer/test_type_color_badge_visual.py
git commit -m "feat(designer): TypeColorBadge widget for rule.type / similar"
```

---

## Task 3: PrimitiveEditorShell — toolbar with panel/JSON toggles + side/bottom slots

**Files:**
- Modify: `src/locksmith/plugins/designer/widgets/primitive_editor_shell.py`
- Test: `tests/plugins/designer/test_shell_toggles_visual.py`

Add two icon-style toggle buttons to the right side of the identity strip: a "panel" toggle for the validation side panel, and a "JSON" toggle for the JSON source view bottom drawer. Each toggle shows/hides a widget the editor registered via `set_side_panel(widget)` / `set_bottom_panel(widget)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/designer/test_shell_toggles_visual.py
from PySide6.QtWidgets import QLabel

from locksmith.plugins.designer.widgets.kind_rail import RailItem
from locksmith.plugins.designer.widgets.primitive_editor_shell import (
    PrimitiveEditorShell,
)


def test_panel_and_json_toggle_buttons_exist(qapp):
    shell = PrimitiveEditorShell(
        surface_label="X", template_label="T",
        items=[RailItem(id="a", label="a", kind_color="#888", has_errors=False)],
    )
    assert shell.panel_toggle is not None
    assert shell.json_toggle is not None
    assert "panel" in shell.panel_toggle.toolTip().lower() \
        or "validation" in shell.panel_toggle.toolTip().lower()
    assert "json" in shell.json_toggle.toolTip().lower()


def test_side_panel_hidden_by_default_then_toggles(qapp):
    shell = PrimitiveEditorShell(
        surface_label="X", template_label="T",
        items=[RailItem(id="a", label="a", kind_color="#888", has_errors=False)],
    )
    side = QLabel("validation issues here")
    shell.set_side_panel(side)
    assert shell.side_panel_container.isVisible() is False
    shell.panel_toggle.click()
    assert shell.side_panel_container.isVisible() is True
    shell.panel_toggle.click()
    assert shell.side_panel_container.isVisible() is False


def test_bottom_panel_hidden_by_default_then_toggles(qapp):
    shell = PrimitiveEditorShell(
        surface_label="X", template_label="T",
        items=[RailItem(id="a", label="a", kind_color="#888", has_errors=False)],
    )
    bottom = QLabel("json source view here")
    shell.set_bottom_panel(bottom)
    assert shell.bottom_panel_container.isVisible() is False
    shell.json_toggle.click()
    assert shell.bottom_panel_container.isVisible() is True
    shell.json_toggle.click()
    assert shell.bottom_panel_container.isVisible() is False


def test_set_side_panel_replaces_previous_widget(qapp):
    shell = PrimitiveEditorShell(
        surface_label="X", template_label="T", items=[],
    )
    first = QLabel("first")
    second = QLabel("second")
    shell.set_side_panel(first)
    shell.set_side_panel(second)
    # Only one widget should be inside the side panel container.
    layout = shell.side_panel_container.layout()
    assert layout.count() == 1
    assert layout.itemAt(0).widget() is second
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_shell_toggles_visual.py -v`
Expected: FAIL — `panel_toggle` attribute doesn't exist.

- [ ] **Step 3: Add toolbar + side/bottom slots to PrimitiveEditorShell**

Edit `src/locksmith/plugins/designer/widgets/primitive_editor_shell.py`. In `_build`, after the existing breadcrumb widgets are appended and before `root.addWidget(strip)`, insert the toolbar toggles. Then restructure the body so a side panel sits to the right of the right-pane container and a bottom panel sits below the body, both initially hidden.

Replace the `_build` method's existing strip end and body construction with this shape:

```python
        self.surface_label = QLabel(surface_label)
        self.surface_label.setStyleSheet("color:#666;")
        strip_lay.addWidget(self.surface_label)

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

        # Toolbar: validation panel + JSON source toggles.
        sep = QLabel(" ")
        sep.setFixedWidth(8)
        strip_lay.addWidget(sep)
        self.panel_toggle = QPushButton("⚠")
        self.panel_toggle.setCheckable(True)
        self.panel_toggle.setToolTip("Validation panel")
        self.panel_toggle.setFixedSize(28, 28)
        self.panel_toggle.setStyleSheet(
            "QPushButton{color:#666;font-size:13px;border:0;border-radius:4px;}"
            "QPushButton:hover{background:#f6f7f9;color:#1A1C20;}"
            "QPushButton:checked{background:#0ABFB0;color:#fff;}"
        )
        self.panel_toggle.toggled.connect(self._on_panel_toggled)
        strip_lay.addWidget(self.panel_toggle)
        self.json_toggle = QPushButton("{ }")
        self.json_toggle.setCheckable(True)
        self.json_toggle.setToolTip("JSON source view")
        self.json_toggle.setFixedSize(36, 28)
        self.json_toggle.setStyleSheet(
            "QPushButton{color:#666;font-size:11px;font-family:monospace;"
            "border:0;border-radius:4px;}"
            "QPushButton:hover{background:#f6f7f9;color:#1A1C20;}"
            "QPushButton:checked{background:#0ABFB0;color:#fff;}"
        )
        self.json_toggle.toggled.connect(self._on_json_toggled)
        strip_lay.addWidget(self.json_toggle)
        root.addWidget(strip)

        # Body: rail + right pane + side panel container.
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

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

        self.right_pane_container = QFrame()
        self.right_pane_container.setStyleSheet("background:#f6f7f9;")
        QVBoxLayout(self.right_pane_container).setContentsMargins(20, 20, 20, 20)
        body.addWidget(self.right_pane_container, 1)

        self.side_panel_container = QFrame()
        self.side_panel_container.setFixedWidth(320)
        self.side_panel_container.setStyleSheet(
            "background:#fff;border-left:1px solid #e0e3ea;"
        )
        side_lay = QVBoxLayout(self.side_panel_container)
        side_lay.setContentsMargins(0, 0, 0, 0)
        side_lay.setSpacing(0)
        self.side_panel_container.setVisible(False)
        body.addWidget(self.side_panel_container)

        # Bottom panel sits below the body.
        body_holder = QFrame()
        body_holder_lay = QVBoxLayout(body_holder)
        body_holder_lay.setContentsMargins(0, 0, 0, 0)
        body_holder_lay.setSpacing(0)
        body_holder_lay.addLayout(body, 1)
        self.bottom_panel_container = QFrame()
        self.bottom_panel_container.setStyleSheet(
            "background:#fff;border-top:1px solid #e0e3ea;"
        )
        self.bottom_panel_container.setFixedHeight(240)
        bottom_lay = QVBoxLayout(self.bottom_panel_container)
        bottom_lay.setContentsMargins(0, 0, 0, 0)
        bottom_lay.setSpacing(0)
        self.bottom_panel_container.setVisible(False)
        body_holder_lay.addWidget(self.bottom_panel_container)

        root.addWidget(body_holder, 1)
```

And append the helper methods near the end of the class:

```python
    def set_side_panel(self, widget: QWidget) -> None:
        layout = self.side_panel_container.layout()
        while layout.count():
            old = layout.takeAt(0).widget()
            if old is not None:
                old.setParent(None)
                old.deleteLater()
        layout.addWidget(widget)

    def set_bottom_panel(self, widget: QWidget) -> None:
        layout = self.bottom_panel_container.layout()
        while layout.count():
            old = layout.takeAt(0).widget()
            if old is not None:
                old.setParent(None)
                old.deleteLater()
        layout.addWidget(widget)

    def _on_panel_toggled(self, checked: bool) -> None:
        self.side_panel_container.setVisible(checked)

    def _on_json_toggled(self, checked: bool) -> None:
        self.bottom_panel_container.setVisible(checked)
```

- [ ] **Step 4: Run shell tests + full designer suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_shell_toggles_visual.py -v`
Expected: 4 PASS.

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/`
Expected: all PASS (existing shell tests must still work — the rail panel structure didn't move).

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/widgets/primitive_editor_shell.py \
        tests/plugins/designer/test_shell_toggles_visual.py
git commit -m "feat(designer): editor shell — toolbar toggles + side/bottom panel slots"
```

---

## Task 4: Wire ValidationPanel + JsonSourceView into every editor

**Files:**
- Modify: `src/locksmith/plugins/designer/editors/{commands,aggregates,reactions,workflows,projections,rules,imports,exports}.py`
- Test: `tests/plugins/designer/test_editor_toggles_wired.py`

Each editor instantiates a `ValidationPanel` and a `JsonSourceView`, then calls `self.shell.set_side_panel(self._validation_panel)` and `self.shell.set_bottom_panel(self._json_source_view)`. Phase 3a does not compute/feed validation reports or JSON updates — that's wired in Phase 2 (write paths) and Phase 4 (panel data binding). The toggles will show the panels but the panels will be empty/initial-state.

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/designer/test_editor_toggles_wired.py
import json
from pathlib import Path

import pytest

from locksmith.plugins.designer.crossref import compute_crossrefs
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.widgets.validation_panel import ValidationPanel
from locksmith.plugins.designer.widgets.json_source_view import JsonSourceView


@pytest.fixture
def regulator_doc():
    return json.loads(
        (Path(__file__).parent / "fixtures"
         / "regulator-grants-carrier-license.json").read_text()
    )


@pytest.mark.parametrize("editor_module,editor_class", [
    ("commands", "CommandsEditorPage"),
    ("aggregates", "AggregatesEditorPage"),
    ("reactions", "ReactionsEditorPage"),
    ("workflows", "WorkflowsEditorPage"),
    ("projections", "ProjectionsEditorPage"),
    ("rules", "RulesEditorPage"),
    ("imports", "ImportsEditorPage"),
    ("exports", "ExportsEditorPage"),
])
def test_editor_wires_validation_panel_and_json_source(
    qapp, regulator_doc, editor_module, editor_class,
):
    mod = __import__(
        f"locksmith.plugins.designer.editors.{editor_module}",
        fromlist=[editor_class],
    )
    cls = getattr(mod, editor_class)
    model = TemplateModel(regulator_doc)
    page = cls(model=model, crossrefs=compute_crossrefs(regulator_doc))
    # The side panel container holds exactly one widget — the ValidationPanel.
    side_layout = page.shell.side_panel_container.layout()
    assert side_layout.count() == 1
    assert isinstance(side_layout.itemAt(0).widget(), ValidationPanel)
    # The bottom panel container holds exactly one widget — the JsonSourceView.
    bottom_layout = page.shell.bottom_panel_container.layout()
    assert bottom_layout.count() == 1
    assert isinstance(bottom_layout.itemAt(0).widget(), JsonSourceView)
```

- [ ] **Step 2: Run test to verify it fails for every editor**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_editor_toggles_wired.py -v`
Expected: 8 FAIL — `count() == 0` (containers empty until editors wire them up).

- [ ] **Step 3: Wire the panels in each editor**

For each of the 8 editor files (`commands.py`, `aggregates.py`, etc.), add after `self.shell.set_right_pane(self._pane)` (or wherever the right pane is set) — two more lines:

```python
        from locksmith.plugins.designer.widgets.validation_panel import (
            ValidationPanel,
        )
        from locksmith.plugins.designer.widgets.json_source_view import (
            JsonSourceView,
        )
        self._validation_panel = ValidationPanel()
        self._json_source_view = JsonSourceView()
        self.shell.set_side_panel(self._validation_panel)
        self.shell.set_bottom_panel(self._json_source_view)
```

For each file, find the exact placement: after the `self.shell.set_right_pane(self._pane)` line, before the existing `self.shell.item_selected.connect(...)` line, insert the panel wiring.

- [ ] **Step 4: Run wiring tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_editor_toggles_wired.py -v`
Expected: 8 PASS.

Run the full designer suite to confirm no regressions:
Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/editors/*.py \
        tests/plugins/designer/test_editor_toggles_wired.py
git commit -m "feat(designer): wire ValidationPanel + JsonSourceView into every editor"
```

---

## Task 5: Toolbar toggles on TemplateOverviewPage

**Files:**
- Modify: `src/locksmith/plugins/designer/editors/overview.py`
- Test: `tests/plugins/designer/test_overview_toggles_visual.py`

Same shape as the editor shell: a `panel_toggle` and `json_toggle` button in the overview header strip, controlling a side panel (ValidationPanel) and a bottom drawer (JsonSourceView).

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/designer/test_overview_toggles_visual.py
import json
from pathlib import Path

import pytest

from locksmith.plugins.designer.editors.overview import TemplateOverviewPage
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.widgets.validation_panel import ValidationPanel
from locksmith.plugins.designer.widgets.json_source_view import JsonSourceView


@pytest.fixture
def regulator_model():
    doc = json.loads(
        (Path(__file__).parent / "fixtures"
         / "regulator-grants-carrier-license.json").read_text()
    )
    return TemplateModel(doc=doc)


def test_overview_has_toolbar_toggles(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    assert page.panel_toggle is not None
    assert page.json_toggle is not None


def test_overview_toggles_show_hide_validation_panel(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    assert page.side_panel_container.isVisible() is False
    page.panel_toggle.click()
    assert page.side_panel_container.isVisible() is True


def test_overview_toggles_show_hide_json_source(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    assert page.bottom_panel_container.isVisible() is False
    page.json_toggle.click()
    assert page.bottom_panel_container.isVisible() is True


def test_overview_panels_are_correct_widget_types(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    side_layout = page.side_panel_container.layout()
    bottom_layout = page.bottom_panel_container.layout()
    assert isinstance(side_layout.itemAt(0).widget(), ValidationPanel)
    assert isinstance(bottom_layout.itemAt(0).widget(), JsonSourceView)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_overview_toggles_visual.py -v`
Expected: 4 FAIL — `panel_toggle` not on the page.

- [ ] **Step 3: Add toolbar toggles + side/bottom containers to Overview**

In `src/locksmith/plugins/designer/editors/overview.py`:

1. Replace the existing header strip's right column construction to add the two toggle buttons between the SAID block and the Walk-me-through CTA. After the line `top_right_row.addWidget(self.kebab_button)` and before closing the row, insert the toggle row:

```python
        self.panel_toggle = QPushButton("⚠")
        self.panel_toggle.setCheckable(True)
        self.panel_toggle.setToolTip("Validation panel")
        self.panel_toggle.setFixedSize(28, 28)
        self.panel_toggle.setStyleSheet(
            "QPushButton{color:#666;font-size:13px;border:0;border-radius:4px;}"
            "QPushButton:hover{background:#f6f7f9;color:#1A1C20;}"
            "QPushButton:checked{background:#0ABFB0;color:#fff;}"
        )
        self.panel_toggle.toggled.connect(self._on_panel_toggled)
        top_right_row.addWidget(self.panel_toggle)
        self.json_toggle = QPushButton("{ }")
        self.json_toggle.setCheckable(True)
        self.json_toggle.setToolTip("JSON source view")
        self.json_toggle.setFixedSize(36, 28)
        self.json_toggle.setStyleSheet(
            "QPushButton{color:#666;font-size:11px;font-family:monospace;"
            "border:0;border-radius:4px;}"
            "QPushButton:hover{background:#f6f7f9;color:#1A1C20;}"
            "QPushButton:checked{background:#0ABFB0;color:#fff;}"
        )
        self.json_toggle.toggled.connect(self._on_json_toggled)
        top_right_row.addWidget(self.json_toggle)
```

2. After `root.addWidget(bottom)` (the bottom strip from Task 15 in Phase 1), restructure: wrap the existing root layout's scroll+bottom in a horizontal-layout that has a side-panel container next to it. The cleanest move is to swap the linear root for a body+sides+bottom structure. Replace the existing post-header construction (from `scroll = QScrollArea()` through `root.addWidget(bottom)`) with:

```python
        from locksmith.plugins.designer.widgets.validation_panel import (
            ValidationPanel,
        )
        from locksmith.plugins.designer.widgets.json_source_view import (
            JsonSourceView,
        )

        body_row = QHBoxLayout()
        body_row.setContentsMargins(0, 0, 0, 0)
        body_row.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border:0;background:#f6f7f9;")
        host = QWidget()
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
        body_row.addWidget(scroll, 1)

        self.side_panel_container = QFrame()
        self.side_panel_container.setFixedWidth(320)
        self.side_panel_container.setStyleSheet(
            "background:#fff;border-left:1px solid #e0e3ea;"
        )
        side_lay = QVBoxLayout(self.side_panel_container)
        side_lay.setContentsMargins(0, 0, 0, 0)
        side_lay.setSpacing(0)
        self._validation_panel = ValidationPanel()
        side_lay.addWidget(self._validation_panel)
        self.side_panel_container.setVisible(False)
        body_row.addWidget(self.side_panel_container)

        root.addLayout(body_row, 1)

        # Bottom strip + collapsible JSON source view.
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

        self.bottom_panel_container = QFrame()
        self.bottom_panel_container.setStyleSheet(
            "background:#fff;border-top:1px solid #e0e3ea;"
        )
        self.bottom_panel_container.setFixedHeight(240)
        bottom_lay = QVBoxLayout(self.bottom_panel_container)
        bottom_lay.setContentsMargins(0, 0, 0, 0)
        bottom_lay.setSpacing(0)
        self._json_source_view = JsonSourceView()
        bottom_lay.addWidget(self._json_source_view)
        self.bottom_panel_container.setVisible(False)
        root.addWidget(self.bottom_panel_container)
```

3. Add the toggle handlers at the end of the class:

```python
    def _on_panel_toggled(self, checked: bool) -> None:
        self.side_panel_container.setVisible(checked)

    def _on_json_toggled(self, checked: bool) -> None:
        self.bottom_panel_container.setVisible(checked)
```

- [ ] **Step 4: Run overview tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/test_overview_toggles_visual.py tests/plugins/designer/test_overview_v1_visual.py tests/plugins/designer/test_overview_visual.py -v`
Expected: all PASS (existing v1 + visual tests must keep working; the bottom strip + 4×2 grid logic is preserved).

Then run the full suite:
Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/plugins/designer/`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/editors/overview.py \
        tests/plugins/designer/test_overview_toggles_visual.py
git commit -m "feat(designer): overview toolbar toggles for validation/JSON panels"
```

---

## Task 6: Final live verification

**Files:**
- (No code changes — verification only)

Drive the wallet via the harness and confirm: editor toolbar shows two new toggle buttons, clicking ⚠ slides in a side panel from the right, clicking { } slides up a bottom drawer, and the overview header has the same two toggles.

- [ ] **Step 1: Restart wallet with seeded fixtures**

```bash
LOCKSMITH_DEV_CONTROL=1 LOCKSMITH_DESIGNER_SEED_FIXTURES=1 \
    .venv/bin/python -m locksmith.main
```

Or use the harness to kill the old one and relaunch.

- [ ] **Step 2: Unlock and navigate to Designer → Templates → Regulator → Commands**

```bash
.venv/bin/python tools/devctl.py click '{"target": "Vaults"}'
.venv/bin/python tools/devctl.py click_list_item '{"text": "joe"}'
.venv/bin/python tools/devctl.py click '{"target": "Vaults"}'
.venv/bin/python tools/devctl.py type \
    '{"target": "FloatingLabelLineEdit:0", "text": "noble"}'
.venv/bin/python tools/devctl.py click '{"target": "Open"}'
.venv/bin/python tools/devctl.py click '{"target": "Micro App Designer"}'
.venv/bin/python tools/devctl.py click '{"target": "Templates"}'
.venv/bin/python tools/devctl.py click '{"target": "Regulator Grants Carrier License"}'
.venv/bin/python tools/devctl.py click '{"target": "Commands"}'
```

- [ ] **Step 3: Screenshot the Commands editor — confirm toolbar toggle buttons exist**

```bash
.venv/bin/python tools/devctl.py screenshot \
    '{"path": "/tmp/locksmith-3a-commands.png"}'
```

Read the image. Expected: identity strip ends with the role + valid pills and **two new toggle buttons** (⚠ + `{ }`) on the right.

- [ ] **Step 4: Toggle the panels and screenshot each state**

```bash
.venv/bin/python tools/devctl.py click '{"target": "Validation panel"}'
sleep 0.4
.venv/bin/python tools/devctl.py screenshot \
    '{"path": "/tmp/locksmith-3a-commands-panel.png"}'
.venv/bin/python tools/devctl.py click '{"target": "Validation panel"}'
sleep 0.4
.venv/bin/python tools/devctl.py click '{"target": "JSON source view"}'
sleep 0.4
.venv/bin/python tools/devctl.py screenshot \
    '{"path": "/tmp/locksmith-3a-commands-json.png"}'
```

Expected: side panel appears on the right when ⚠ is checked; bottom drawer appears below the body when `{ }` is checked.

- [ ] **Step 5: Go back to overview, verify the same toggles work there**

```bash
.venv/bin/python tools/devctl.py click '{"target": "Templates"}'
.venv/bin/python tools/devctl.py click '{"target": "Regulator Grants Carrier License"}'
.venv/bin/python tools/devctl.py click '{"target": "Validation panel"}'
sleep 0.4
.venv/bin/python tools/devctl.py screenshot \
    '{"path": "/tmp/locksmith-3a-overview-panel.png"}'
```

Expected: overview header carries the toggles; clicking ⚠ slides in the side panel without disturbing the 4×2 facet grid.

- [ ] **Step 6: Milestone commit**

```bash
git commit --allow-empty -m "milestone(designer): Phase 3a (shared infra + toolbar toggles) complete

DarkCodeBlock and TypeColorBadge widgets land. PrimitiveEditorShell and
TemplateOverviewPage gain a toolbar with panel + JSON toggles that show/
hide a side panel (ValidationPanel) and bottom drawer (JsonSourceView)
respectively. Wired into every editor + the Overview. No model write
paths land yet — panels currently render the initial state of empty
validation report + initial doc JSON. Phase 3b/3c/3d will hook these
toggles to live data as each editor's content gets richer.
"
```

---

## Self-review checklist

1. **Spec coverage** — what Phase 3a was supposed to deliver:
   - Cross-cutting widgets used by Phase 3b/3c/3d (DarkCodeBlock for Rules expression + Projections fold; TypeColorBadge for Rules right-pane header). ✓ Tasks 1 + 2.
   - Toolbar toggles for ValidationPanel + JsonSourceView (Phase 4 promise — toolbar toggle in every editor + Overview). ✓ Tasks 3 + 4 + 5.
   - Live verification. ✓ Task 6.

2. **Explicitly deferred to 3b/3c/3d** (no task here, by design):
   - `EditorTabBar` widget (only Exports uses it — lands in 3b).
   - `RulePicker` chip-picker (Commands preconditions — 3b).
   - Type-grouped rail (Rules — 3d).
   - Filter chip bar (Rules — 3d).
   - Live panel data binding (Validation report content + JSON source view content from current model) — Phase 4 / Phase 2 will hook these up.

3. **Placeholder scan:** no TODO / "implement later" / "similar to Task N" anywhere. Every code block contains full code; every command is runnable.

4. **Type consistency:**
   - `DarkCodeBlock(text: str = "")` — text in constructor, `toPlainText()` reads back.
   - `TypeColorBadge(type_id: str)` — string in, text via `.text()` reads uppercase form.
   - `PrimitiveEditorShell.set_side_panel(widget)` / `set_bottom_panel(widget)` — replaces the panel; layout has exactly 1 child after the call.
   - `panel_toggle` / `json_toggle` — QPushButton, checkable, `toggled(bool)` connected to internal `_on_*` handlers.
   - `side_panel_container` / `bottom_panel_container` — QFrame, both initially `setVisible(False)`.
