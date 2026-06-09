# Settings Two-Surface Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split today's single mixed-scope vault Settings page into two separate surfaces: the **toolbar Settings button** opens a new modal **AppSettingsDialog** (app-wide: Updates, Defaults for new vaults, About); the **vault sidebar Settings entry** keeps only **per-vault** concerns (Peer Mode, Danger Zone, Browser Plugin when enabled).

**Architecture:** App-wide concerns move to a new `AppSettingsDialog` (modal `LocksmithDialog`) opened from `Toolbar.show_settings_dialog`. The existing "Configuration" info dialog at that entry point is replaced. Vault-scoped concerns stay in the existing `SettingsPage`, with the General Settings section's app-wide rows (temp / base / tier / algo / salt) extracted into a reusable `DefaultsSettingsWidget` that lives in the new dialog. The `UpdatesSettingsWidget` (Phase 5) is unchanged — only its mount point moves from `SettingsPage` to `AppSettingsDialog`. The `on_settings()` stub in `LocksmithWindow` and its dead signal connection are deleted.

**Tech Stack:** PySide6, `LocksmithDialog` (`locksmith.ui.toolkit.widgets.dialogs`), `LocksmithConfig` singleton (per-OS-user), `UpdatePrefs` (`QSettings`-backed), pytest with `qapp` fixture.

---

## File Structure

**Create:**
- `src/locksmith/ui/dialogs/app_settings.py` — `AppSettingsDialog` class. Composes three section widgets in a scrollable column. Wires `UpdatesSettingsWidget` to the app's `update_controller`.
- `src/locksmith/ui/dialogs/defaults_settings_widget.py` — `DefaultsSettingsWidget` class. Owns the temp / base-dir / tier / algo / salt rows. Binds to `LocksmithConfig.get_instance()`.
- `tests/test_app_settings_dialog.py` — tests for the new dialog + defaults widget.

**Modify:**
- `src/locksmith/ui/toolbar.py:313-407` — replace body of `show_settings_dialog` (and helpers `_create_settings_content` etc.) with `AppSettingsDialog` open call. Delete dead `settings_clicked.emit()` connection at line 172.
- `src/locksmith/ui/vault/settings/page.py` — delete `_create_general_settings_section` and its row helpers (`_create_temp_datastore_row`, `_create_base_dir_row`, `_create_tier_row`, `_create_algo_row`, `_create_salt_row`, `_create_version_section`, `_update_salt_visibility`, `_on_temp_changed`, `_on_base_changed`, `_on_tier_changed`, `_on_algo_changed`, `_on_salt_changed`, `_on_resalt`). Delete `_create_updates_section`. Promote browser-plugin section to a top-level vault section (no longer nested inside General Settings).
- `src/locksmith/ui/window.py:553-557` — delete `on_settings` stub. Delete `self.toolbar.settings_clicked.connect(self.on_settings)` at line 67.

**Keep / unchanged:**
- `src/locksmith/ui/vault/settings/updates_widget.py` — `UpdatesSettingsWidget` is reused as-is.
- `src/locksmith/ui/vault/settings/peer_section.py` — vault Settings still mounts this.
- `src/locksmith/ui/vault/settings/delete_dialog.py` — Danger Zone still uses this.

---

## Task 1: Skeleton `AppSettingsDialog` and toolbar wiring

Goal of this task: clicking the toolbar Settings button opens an empty (header + close button) `AppSettingsDialog` instead of the old Configuration info dialog. No section content yet.

**Files:**
- Create: `src/locksmith/ui/dialogs/app_settings.py`
- Modify: `src/locksmith/ui/toolbar.py:313-407`
- Test: `tests/test_app_settings_dialog.py`

---

- [ ] **Step 1: Write the failing test**

Create `tests/test_app_settings_dialog.py`:

```python
"""Tests for the AppSettingsDialog (toolbar Settings entry)."""
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QLabel

from locksmith.ui.dialogs.app_settings import AppSettingsDialog


def _fake_app():
    """A minimal app stub the dialog can read from without a live controller."""
    return SimpleNamespace(update_controller=None)


def test_app_settings_dialog_constructs(qapp):
    dialog = AppSettingsDialog(app=_fake_app())
    assert dialog.objectName() == "appSettingsDialog"
    # Header label visible at the top of the dialog.
    headers = dialog.findChildren(QLabel, "appSettingsDialog.titleLabel")
    assert len(headers) == 1
    assert headers[0].text() == "Settings"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_app_settings_dialog.py::test_app_settings_dialog_constructs --import-mode=importlib -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'locksmith.ui.dialogs.app_settings'`

- [ ] **Step 3: Write the dialog**

Create `src/locksmith/ui/dialogs/app_settings.py`:

```python
"""Application-wide Settings dialog — opened from the toolbar Settings button.

Holds app-wide concerns (Updates, Defaults for new vaults, About). The
per-vault Settings sidebar entry holds per-vault concerns (Peer Mode,
Danger Zone, Browser Plugin). See plan
``docs/superpowers/plans/2026-06-09-settings-two-surface-refactor.md``.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from keri import help

from locksmith.ui import colors
from locksmith.ui.toolkit.widgets.buttons import LocksmithButton
from locksmith.ui.toolkit.widgets.dialogs import LocksmithDialog

logger = help.ogler.getLogger(__name__)


class AppSettingsDialog(LocksmithDialog):
    """Modal app-settings dialog.

    Args:
        app: The LocksmithApplication (or a SimpleNamespace stub in tests).
            ``app.update_controller`` is read when wiring the Updates
            section; ``None`` is tolerated for tests / pre-init states.
        parent: Parent QWidget (the main window).
    """

    def __init__(self, *, app: Any | None = None, parent: QWidget | None = None) -> None:
        self._app = app

        # Title row uses a styled QLabel rather than the dialog's default
        # title bar, matching the existing show_settings_dialog convention.
        title_content = QLabel("Settings")
        title_content.setObjectName("appSettingsDialog.titleLabel")
        title_content.setStyleSheet(f"font-size: 24px; color: {colors.TEXT_DARK};")

        # Body: a scrollable column that section widgets will be added to.
        self._body = QWidget()
        self._body.setObjectName("appSettingsDialog.body")
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(20, 10, 20, 10)
        self._body_layout.setSpacing(20)
        self._body_layout.addStretch()  # bottom spacer; widgets insert above

        scroll = QScrollArea()
        scroll.setObjectName("appSettingsDialog.scroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self._body)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        self._close_button = LocksmithButton("Close")
        self._close_button.setObjectName("appSettingsDialog.closeButton")
        button_layout.addStretch()
        button_layout.addWidget(self._close_button)

        super().__init__(
            parent=parent,
            title="Settings",
            title_content=title_content,
            show_close_button=True,
            show_title_divider=False,
            content=scroll,
            buttons=button_layout,
        )
        self.setObjectName("appSettingsDialog")
        self.setFixedSize(720, 650)

        self._close_button.clicked.connect(self.accept)

    def _insert_section(self, widget: QWidget) -> None:
        """Insert a section widget above the trailing stretch."""
        # stretch is the last item; insert before it
        last_index = self._body_layout.count() - 1
        self._body_layout.insertWidget(last_index, widget)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_app_settings_dialog.py::test_app_settings_dialog_constructs --import-mode=importlib -v`

Expected: PASS

- [ ] **Step 5: Re-wire the toolbar Settings button**

Modify `src/locksmith/ui/toolbar.py`. Replace the body of `show_settings_dialog` (and remove the now-unused `_create_settings_content` helper) with the AppSettingsDialog call.

Find the block at line 313:

```python
    def show_settings_dialog(self):
        """Show the Configuration settings dialog."""
        # Get configuration instance
        config = LocksmithConfig.get_instance()

        # Create content widget with configuration information
        content_widget = self._create_settings_content(config)
        ...
```

Replace it (and delete `_create_settings_content` plus any other private helpers exclusively used by the old Configuration dialog — confirm with `grep -n "_create_settings_content\|_format_config_row" src/locksmith/ui/toolbar.py` before deleting) with:

```python
    def show_settings_dialog(self):
        """Open the application Settings dialog (toolbar entry).

        App-wide settings: Updates, Defaults for new vaults, About.
        Per-vault settings live in the vault sidebar Settings entry.
        """
        from locksmith.ui.dialogs.app_settings import AppSettingsDialog
        dialog = AppSettingsDialog(app=self.app, parent=self.parent())
        dialog.open()
```

Also delete line 172 (the dead `settings_clicked.emit` connection — `on_settings` is being deleted in Task 6):

Find:
```python
        self.settings_button.clicked.connect(self.show_settings_dialog)
        self.settings_button.clicked.connect(self.settings_clicked.emit)
```

Replace with:
```python
        self.settings_button.clicked.connect(self.show_settings_dialog)
```

- [ ] **Step 6: Run the full test file to verify nothing broke**

Run: `.venv/bin/pytest tests/test_app_settings_dialog.py --import-mode=importlib -v`

Expected: PASS (1 test)

Run: `.venv/bin/pytest tests/test_toolbar_vault_name.py --import-mode=importlib -v`

Expected: PASS — verifies toolbar still constructs cleanly after the edit.

- [ ] **Step 7: Commit**

```bash
git add tests/test_app_settings_dialog.py src/locksmith/ui/dialogs/app_settings.py src/locksmith/ui/toolbar.py
git commit -m "feat(settings): introduce AppSettingsDialog (toolbar entry)

Replaces the old Configuration info dialog with an empty
AppSettingsDialog skeleton. Sections (Updates, Defaults, About)
land in subsequent commits."
```

---

## Task 2: Extract `DefaultsSettingsWidget` from vault SettingsPage

Goal of this task: move the temp / base-dir / tier / algo / salt rows out of `SettingsPage._create_general_settings_section` into a self-contained `DefaultsSettingsWidget`. The widget binds to the `LocksmithConfig` singleton. The widget is NOT yet mounted in `AppSettingsDialog` — that's the next task. The vault SettingsPage is NOT yet edited — that's a later task.

**Files:**
- Create: `src/locksmith/ui/dialogs/defaults_settings_widget.py`
- Test: `tests/test_app_settings_dialog.py` (append)

---

- [ ] **Step 1: Write the failing test**

Append to `tests/test_app_settings_dialog.py`:

```python
from locksmith.core.configing import LocksmithConfig
from locksmith.ui.dialogs.defaults_settings_widget import DefaultsSettingsWidget


def test_defaults_widget_binds_temp_toggle_to_config(qapp):
    config = LocksmithConfig.get_instance()
    original = config.temp
    try:
        config.temp = False
        widget = DefaultsSettingsWidget()
        assert widget.objectName() == "defaultsSettingsWidget"
        assert widget.temp_toggle.isChecked() is False

        widget.temp_toggle.setChecked(True)
        assert config.temp is True
    finally:
        config.temp = original


def test_defaults_widget_binds_tier_radio_to_config(qapp):
    config = LocksmithConfig.get_instance()
    original = config.tier
    try:
        config.tier = "low"
        widget = DefaultsSettingsWidget()
        assert widget.tier_low.isChecked() is True

        widget.tier_high.setChecked(True)
        assert config.tier == "high"
    finally:
        config.tier = original


def test_defaults_widget_hides_salt_row_when_algo_is_randy(qapp):
    config = LocksmithConfig.get_instance()
    original_algo = config.algo
    try:
        config.algo = "randy"
        widget = DefaultsSettingsWidget()
        assert widget.salt_row_widget.isVisible() is False

        widget.algo_salty.setChecked(True)
        assert widget.salt_row_widget.isVisible() is True
    finally:
        config.algo = original_algo
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_app_settings_dialog.py::test_defaults_widget_binds_temp_toggle_to_config --import-mode=importlib -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'locksmith.ui.dialogs.defaults_settings_widget'`

- [ ] **Step 3: Write the widget**

Create `src/locksmith/ui/dialogs/defaults_settings_widget.py`. This is a faithful port of `SettingsPage._create_general_settings_section` and its row helpers — same widget structure, just relocated.

```python
"""Defaults for new vaults — extracted from SettingsPage so the toolbar
Settings dialog (app-wide) and the vault Settings sidebar (per-vault)
hold different concerns. Binds to ``LocksmithConfig.get_instance()``
exactly as the original section did."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)
from keri import help

from locksmith.core.configing import LocksmithConfig
from locksmith.ui import colors
from locksmith.ui.toolkit.widgets.buttons import (
    LocksmithIconButton,
    LocksmithRadioButton,
)
from locksmith.ui.toolkit.widgets.fields import FloatingLabelLineEdit
from locksmith.ui.toolkit.widgets.toggle import ToggleSwitch

logger = help.ogler.getLogger(__name__)


class DefaultsSettingsWidget(QWidget):
    """Default settings for new vaults and identifiers.

    Owns the temp datastore toggle, base-dir field, tier radio group,
    algo radio group, and salt field. Writes through to
    ``LocksmithConfig.get_instance()`` on every change, matching the
    semantics of the original ``SettingsPage._create_general_settings_section``.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("defaultsSettingsWidget")
        self.config: LocksmithConfig = LocksmithConfig.get_instance()
        self._build_layout()

    def _build_layout(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        header = QLabel("Defaults for new vaults")
        header.setObjectName("defaultsSettingsWidget.header")
        header.setStyleSheet(
            f"color: {colors.TEXT_PRIMARY}; font-size: 14px; font-weight: bold;"
        )
        outer.addWidget(header)

        subheader = QLabel("Default settings applied when creating a new vault or identifier")
        subheader.setObjectName("defaultsSettingsWidget.subheader")
        subheader.setStyleSheet(
            f"color: {colors.TEXT_SECONDARY}; font-size: 12px; margin-bottom: 10px;"
        )
        outer.addWidget(subheader)

        container = QFrame()
        container.setObjectName("defaultsSettingsContainer")
        container.setStyleSheet(f"""
            #defaultsSettingsContainer {{
                background-color: {colors.WHITE};
                border: 1px solid {colors.BORDER_TABLE};
                border-radius: 24px;
            }}
            QWidget {{ background-color: transparent; }}
            QRadioButton {{ spacing: 8px; color: {colors.TOGGLE_TRACK_ON}; }}
            QRadioButton::indicator {{
                width: 14px; height: 14px;
                border-radius: 8px;
                border: 2px solid {colors.BLUE_ACCENT};
                background-color: transparent;
            }}
            QRadioButton::indicator:checked {{
                background-color: {colors.BLUE_ACCENT};
            }}
            QLineEdit {{
                border: 2px solid {colors.BORDER_TABLE};
                border-radius: 6px;
                padding: 5px;
                color: {colors.TOGGLE_TRACK_ON};
            }}
            QLineEdit:focus {{
                border: 2px solid {colors.BLUE_ACCENT};
            }}
        """)
        body = QVBoxLayout(container)
        body.setContentsMargins(25, 25, 25, 25)
        body.setSpacing(20)

        self._build_temp_row(body)
        self._build_base_dir_row(body)
        self._build_tier_row(body)
        self._build_algo_row(body)
        self._build_salt_row(body)

        outer.addWidget(container)
        self._update_salt_visibility()

    # ---- rows --------------------------------------------------------

    def _build_temp_row(self, parent_layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setSpacing(20)
        label = QLabel("Temporary Datastore")
        label.setFixedWidth(220)
        label.setStyleSheet(f"font-size: 16px; color: {colors.TEXT_PRIMARY};")
        row.addWidget(label)

        self.temp_toggle = ToggleSwitch()
        self.temp_toggle.setObjectName("defaultsSettingsWidget.tempToggle")
        self.temp_toggle.setChecked(self.config.temp)
        self.temp_toggle.toggled.connect(self._on_temp_changed)
        row.addWidget(self.temp_toggle)

        row.addStretch()
        parent_layout.addLayout(row)

    def _build_base_dir_row(self, parent_layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setSpacing(20)
        label = QLabel("Database Directory Base")
        label.setFixedWidth(220)
        label.setStyleSheet(f"font-size: 16px; color: {colors.TEXT_PRIMARY};")
        row.addWidget(label)

        self.base_dir_field = FloatingLabelLineEdit("Directory")
        self.base_dir_field.setObjectName("defaultsSettingsWidget.baseDirField")
        self.base_dir_field.setText(self.config.base)
        self.base_dir_field.setFixedWidth(300)
        self.base_dir_field.line_edit.textChanged.connect(self._on_base_changed)
        row.addWidget(self.base_dir_field)

        row.addStretch()
        parent_layout.addLayout(row)

    def _build_tier_row(self, parent_layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setSpacing(20)
        label = QLabel("Cryptographic Key Strength")
        label.setFixedWidth(220)
        label.setStyleSheet(f"font-size: 16px; color: {colors.TEXT_PRIMARY};")
        row.addWidget(label)

        self.tier_group = QButtonGroup(self)
        tier_layout = QHBoxLayout()
        tier_layout.setSpacing(15)

        self.tier_low = LocksmithRadioButton("Low")
        self.tier_low.setObjectName("defaultsSettingsWidget.tierLow")
        self.tier_med = LocksmithRadioButton("Medium")
        self.tier_med.setObjectName("defaultsSettingsWidget.tierMedium")
        self.tier_high = LocksmithRadioButton("High")
        self.tier_high.setObjectName("defaultsSettingsWidget.tierHigh")

        self.tier_group.addButton(self.tier_low)
        self.tier_group.addButton(self.tier_med)
        self.tier_group.addButton(self.tier_high)

        if self.config.tier == "med":
            self.tier_med.setChecked(True)
        elif self.config.tier == "high":
            self.tier_high.setChecked(True)
        else:
            self.tier_low.setChecked(True)

        tier_layout.addWidget(self.tier_low)
        tier_layout.addWidget(self.tier_med)
        tier_layout.addWidget(self.tier_high)
        self.tier_group.buttonClicked.connect(self._on_tier_changed)

        row.addLayout(tier_layout)
        row.addStretch()
        parent_layout.addLayout(row)

    def _build_algo_row(self, parent_layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setSpacing(20)
        label = QLabel("Default Key Generation")
        label.setFixedWidth(220)
        label.setStyleSheet(f"font-size: 16px; color: {colors.TEXT_PRIMARY};")
        row.addWidget(label)

        self.algo_group = QButtonGroup(self)
        algo_layout = QHBoxLayout()
        algo_layout.setSpacing(15)

        self.algo_salty = LocksmithRadioButton("Salty")
        self.algo_salty.setObjectName("defaultsSettingsWidget.algoSalty")
        self.algo_randy = LocksmithRadioButton("Randy")
        self.algo_randy.setObjectName("defaultsSettingsWidget.algoRandy")

        self.algo_group.addButton(self.algo_salty)
        self.algo_group.addButton(self.algo_randy)

        if self.config.algo == "salty":
            self.algo_salty.setChecked(True)
        else:
            self.algo_randy.setChecked(True)

        algo_layout.addWidget(self.algo_salty)
        algo_layout.addWidget(self.algo_randy)
        self.algo_group.buttonClicked.connect(self._on_algo_changed)

        row.addLayout(algo_layout)
        row.addStretch()
        parent_layout.addLayout(row)

    def _build_salt_row(self, parent_layout: QVBoxLayout) -> None:
        self.salt_row_widget = QWidget()
        self.salt_row_widget.setObjectName("defaultsSettingsWidget.saltRow")
        self.salt_row_widget.setStyleSheet("background-color: transparent;")
        row = QHBoxLayout(self.salt_row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(20)

        label = QLabel("Key Salt")
        label.setFixedWidth(220)
        label.setStyleSheet(f"font-size: 16px; color: {colors.TEXT_PRIMARY};")
        row.addWidget(label)

        self.salt_field = FloatingLabelLineEdit("Salt", password_mode=True)
        self.salt_field.setObjectName("defaultsSettingsWidget.saltField")
        self.salt_field.setText(self.config.salt)
        self.salt_field.setFixedWidth(300)
        self.salt_field.line_edit.textChanged.connect(self._on_salt_changed)
        row.addWidget(self.salt_field)

        resalt_button = LocksmithIconButton(
            icon_path=":/assets/material-icons/refresh.svg",
            tooltip="Generate new salt",
        )
        resalt_button.setObjectName("defaultsSettingsWidget.resaltButton")
        resalt_button.clicked.connect(self._on_resalt)
        row.addWidget(resalt_button)

        row.addStretch()
        parent_layout.addWidget(self.salt_row_widget)

    # ---- handlers ----------------------------------------------------

    def _on_temp_changed(self, checked: bool) -> None:
        self.config.temp = checked
        logger.info("[defaults] temp=%s", self.config.temp)

    def _on_base_changed(self, text: str) -> None:
        self.config.base = text
        logger.info("[defaults] base=%s", self.config.base)

    def _on_tier_changed(self) -> None:
        if self.tier_low.isChecked():
            self.config.tier = "low"
        elif self.tier_med.isChecked():
            self.config.tier = "med"
        elif self.tier_high.isChecked():
            self.config.tier = "high"
        logger.info("[defaults] tier=%s", self.config.tier)

    def _on_algo_changed(self) -> None:
        if self.algo_salty.isChecked():
            self.config.algo = "salty"
        else:
            self.config.algo = "randy"
        logger.info("[defaults] algo=%s", self.config.algo)
        self._update_salt_visibility()

    def _update_salt_visibility(self) -> None:
        self.salt_row_widget.setVisible(self.config.algo == "salty")

    def _on_salt_changed(self, text: str) -> None:
        self.config.salt = text
        logger.info("[defaults] salt updated")

    def _on_resalt(self) -> None:
        new_salt = self.config.resalt()
        self.salt_field.setText(new_salt)
        logger.info("[defaults] new salt generated")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_app_settings_dialog.py --import-mode=importlib -v`

Expected: PASS (4 tests — the 1 from Task 1 + 3 new)

- [ ] **Step 5: Commit**

```bash
git add tests/test_app_settings_dialog.py src/locksmith/ui/dialogs/defaults_settings_widget.py
git commit -m "feat(settings): extract DefaultsSettingsWidget from SettingsPage

Self-contained widget that mirrors the old
SettingsPage._create_general_settings_section behavior, binding to
LocksmithConfig.get_instance(). Not yet mounted anywhere — the
AppSettingsDialog and SettingsPage edits land in follow-up commits."
```

---

## Task 3: Mount `DefaultsSettingsWidget` in `AppSettingsDialog`

**Files:**
- Modify: `src/locksmith/ui/dialogs/app_settings.py`
- Test: `tests/test_app_settings_dialog.py` (append)

---

- [ ] **Step 1: Write the failing test**

Append to `tests/test_app_settings_dialog.py`:

```python
def test_app_settings_dialog_contains_defaults_section(qapp):
    dialog = AppSettingsDialog(app=_fake_app())
    widgets = dialog.findChildren(QWidget, "defaultsSettingsWidget")
    assert len(widgets) == 1
```

Add this import at the top of the file (next to the existing `from PySide6.QtWidgets import QLabel`):

```python
from PySide6.QtWidgets import QLabel, QWidget
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_app_settings_dialog.py::test_app_settings_dialog_contains_defaults_section --import-mode=importlib -v`

Expected: FAIL — `assert 0 == 1`

- [ ] **Step 3: Mount the widget in the dialog**

In `src/locksmith/ui/dialogs/app_settings.py`, at the bottom of `AppSettingsDialog.__init__` (after `self._close_button.clicked.connect(self.accept)`), add:

```python
        self._mount_sections()

    def _mount_sections(self) -> None:
        """Compose the section widgets into the dialog body."""
        from locksmith.ui.dialogs.defaults_settings_widget import (
            DefaultsSettingsWidget,
        )
        self._defaults_widget = DefaultsSettingsWidget()
        self._insert_section(self._defaults_widget)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_app_settings_dialog.py --import-mode=importlib -v`

Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add tests/test_app_settings_dialog.py src/locksmith/ui/dialogs/app_settings.py
git commit -m "feat(settings): mount DefaultsSettingsWidget in AppSettingsDialog"
```

---

## Task 4: Mount `UpdatesSettingsWidget` in `AppSettingsDialog`

Goal: relocate the `UpdatesSettingsWidget` wire-up out of `SettingsPage._create_updates_section` and into `AppSettingsDialog._mount_sections`. The widget itself is unchanged.

**Files:**
- Modify: `src/locksmith/ui/dialogs/app_settings.py`
- Test: `tests/test_app_settings_dialog.py` (append)

---

- [ ] **Step 1: Write the failing test**

Append to `tests/test_app_settings_dialog.py`:

```python
def test_app_settings_dialog_contains_updates_section(qapp):
    dialog = AppSettingsDialog(app=_fake_app())
    widgets = dialog.findChildren(QWidget, "updatesSettingsWidget")
    assert len(widgets) == 1


def test_app_settings_dialog_wires_check_now_to_controller(qapp):
    called = []
    fake_controller = SimpleNamespace(
        prefs=None,
        check_now=lambda: called.append("check_now"),
    )
    app = SimpleNamespace(update_controller=fake_controller)
    dialog = AppSettingsDialog(app=app)

    btn = dialog.findChild(
        QWidget, "updatesSettingsWidget.checkNowButton"
    )
    assert btn is not None
    btn.click()
    assert called == ["check_now"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_app_settings_dialog.py::test_app_settings_dialog_contains_updates_section --import-mode=importlib -v`

Expected: FAIL — `assert 0 == 1`

- [ ] **Step 3: Mount the Updates widget**

In `src/locksmith/ui/dialogs/app_settings.py`, extend `_mount_sections`:

```python
    def _mount_sections(self) -> None:
        """Compose the section widgets into the dialog body."""
        from locksmith.ui.dialogs.defaults_settings_widget import (
            DefaultsSettingsWidget,
        )
        from locksmith.ui.vault.settings.updates_widget import (
            UpdatesSettingsWidget,
        )

        self._defaults_widget = DefaultsSettingsWidget()
        self._insert_section(self._defaults_widget)

        ctrl = getattr(self._app, "update_controller", None) if self._app else None
        self._updates_widget = UpdatesSettingsWidget(
            prefs=ctrl.prefs if ctrl else None,
        )
        if ctrl is not None:
            self._updates_widget.set_check_now_callback(ctrl.check_now)

        def _on_view_log() -> None:
            # Walk up to the top-level LocksmithWindow and open its
            # dialog via the same handler the Help menu uses.
            top = self.window()
            handler = getattr(top, "_on_show_verification_log_clicked", None)
            if handler is not None:
                handler()
        self._updates_widget.set_view_log_callback(_on_view_log)
        self._insert_section(self._updates_widget)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_app_settings_dialog.py --import-mode=importlib -v`

Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add tests/test_app_settings_dialog.py src/locksmith/ui/dialogs/app_settings.py
git commit -m "feat(settings): mount UpdatesSettingsWidget in AppSettingsDialog

Wires check-now to app.update_controller.check_now and view-log to
the main window's _on_show_verification_log_clicked handler. The
SettingsPage still mounts this widget too — Task 6 removes it from
there."
```

---

## Task 5: Add About section to `AppSettingsDialog`

Goal: third section showing the app version (`LOCKSMITH_VERSION` from `locksmith.build_info`).

**Files:**
- Modify: `src/locksmith/ui/dialogs/app_settings.py`
- Test: `tests/test_app_settings_dialog.py` (append)

---

- [ ] **Step 1: Write the failing test**

Append to `tests/test_app_settings_dialog.py`:

```python
def test_app_settings_dialog_contains_about_section(qapp):
    dialog = AppSettingsDialog(app=_fake_app())
    labels = dialog.findChildren(QLabel, "appSettingsDialog.aboutVersionLabel")
    assert len(labels) == 1
    # Version string format: "Version: <something non-empty>"
    assert labels[0].text().startswith("Version: ")
    assert labels[0].text() != "Version: "
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_app_settings_dialog.py::test_app_settings_dialog_contains_about_section --import-mode=importlib -v`

Expected: FAIL — `assert 0 == 1`

- [ ] **Step 3: Add About section**

In `src/locksmith/ui/dialogs/app_settings.py`, extend `_mount_sections`:

```python
        # About section (last)
        about_container = QFrame()
        about_container.setObjectName("appSettingsDialog.aboutContainer")
        about_container.setStyleSheet(f"""
            #appSettingsDialog\\.aboutContainer {{
                background-color: {colors.WHITE};
                border: 1px solid {colors.BORDER_TABLE};
                border-radius: 24px;
            }}
            QWidget {{ background-color: transparent; }}
        """)
        about_layout = QVBoxLayout(about_container)
        about_layout.setContentsMargins(25, 25, 25, 25)
        about_layout.setSpacing(8)

        about_header = QLabel("About")
        about_header.setObjectName("appSettingsDialog.aboutHeader")
        about_header.setStyleSheet(
            f"color: {colors.TEXT_PRIMARY}; font-size: 14px; font-weight: bold;"
        )
        about_layout.addWidget(about_header)

        try:
            from locksmith.build_info import LOCKSMITH_VERSION
        except Exception:
            LOCKSMITH_VERSION = "dev"
        version_label = QLabel(f"Version: {LOCKSMITH_VERSION}")
        version_label.setObjectName("appSettingsDialog.aboutVersionLabel")
        version_label.setStyleSheet(
            f"font-size: 13px; color: {colors.TEXT_SECONDARY};"
        )
        about_layout.addWidget(version_label)

        self._insert_section(about_container)
```

Note the QSS selector escape: `appSettingsDialog\\.aboutContainer` — the literal dot in the objectName must be escaped in the Qt stylesheet selector.

- [ ] **Step 4: Run tests to verify all pass**

Run: `.venv/bin/pytest tests/test_app_settings_dialog.py --import-mode=importlib -v`

Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add tests/test_app_settings_dialog.py src/locksmith/ui/dialogs/app_settings.py
git commit -m "feat(settings): add About section to AppSettingsDialog"
```

---

## Task 6: Strip app-wide sections out of vault `SettingsPage`

Goal: delete `_create_general_settings_section`, `_create_updates_section`, `_create_version_section`, and all row helpers/handlers that only the general-settings section used. Keep peer mode, danger zone, and the browser plugin section (promote browser plugin to a top-level vault section rather than nested inside general settings). After this task, vault Settings contains only per-vault concerns.

**Files:**
- Modify: `src/locksmith/ui/vault/settings/page.py`
- Test: `tests/test_app_settings_dialog.py` (append — verify SettingsPage no longer mounts the moved widgets)

---

- [ ] **Step 1: Write the failing test**

Append to `tests/test_app_settings_dialog.py`:

```python
def test_vault_settings_page_no_longer_mounts_updates_widget(qapp):
    """The vault sidebar Settings entry must not double-mount Updates;
    that section lives in the toolbar AppSettingsDialog now."""
    # Build a minimal VaultPage-like parent for SettingsPage construction.
    fake_app = SimpleNamespace(
        vault=None,
        config=LocksmithConfig.get_instance(),
        update_controller=None,
        is_vault_open=False,
    )
    parent = QWidget()
    parent.app = fake_app  # SettingsPage reads `parent.app`

    from locksmith.ui.vault.settings.page import SettingsPage
    page = SettingsPage(parent=parent)

    assert page.findChild(QWidget, "updatesSettingsWidget") is None
    # Sanity: the per-vault Peer Mode placeholder still exists.
    assert page._peer_section_placeholder is not None


def test_vault_settings_page_no_longer_mounts_defaults_widget(qapp):
    fake_app = SimpleNamespace(
        vault=None,
        config=LocksmithConfig.get_instance(),
        update_controller=None,
        is_vault_open=False,
    )
    parent = QWidget()
    parent.app = fake_app

    from locksmith.ui.vault.settings.page import SettingsPage
    page = SettingsPage(parent=parent)

    assert page.findChild(QWidget, "defaultsSettingsWidget") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_app_settings_dialog.py::test_vault_settings_page_no_longer_mounts_updates_widget --import-mode=importlib -v`

Expected: FAIL — `updatesSettingsWidget` still found in the vault SettingsPage.

- [ ] **Step 3: Strip SettingsPage**

Edit `src/locksmith/ui/vault/settings/page.py`:

**a. Update the imports block** — remove now-unused imports:

Find:
```python
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QFrame, QButtonGroup
)
from keri import help
from keri.core import coring
from keri import kering

from locksmith.core.configing import ENABLE_TURRET_BROWSER_PLUGIN, LocksmithConfig
from locksmith.ui import colors
from locksmith.ui.styles import get_monospace_font_family
from locksmith.ui.toolkit.widgets.buttons import LocksmithButton, LocksmithIconButton, LocksmithRadioButton, LocksmithCopyButton
from locksmith.ui.toolkit.widgets.fields import FloatingLabelLineEdit
from locksmith.ui.toolkit.widgets.toggle import ToggleSwitch
from locksmith.ui.vault.settings.delete_dialog import DeleteVaultDialog
from locksmith.ui.vault.settings.peer_section import PeerSettingsSection
```

Replace with:
```python
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QFrame
)
from keri import help
from keri.core import coring
from keri import kering

from locksmith.core.configing import ENABLE_TURRET_BROWSER_PLUGIN, LocksmithConfig
from locksmith.ui import colors
from locksmith.ui.styles import get_monospace_font_family
from locksmith.ui.toolkit.widgets.buttons import LocksmithButton, LocksmithIconButton, LocksmithCopyButton
from locksmith.ui.toolkit.widgets.fields import FloatingLabelLineEdit
from locksmith.ui.vault.settings.delete_dialog import DeleteVaultDialog
from locksmith.ui.vault.settings.peer_section import PeerSettingsSection
```

**b. Replace the section-mounting calls in `__init__`** — find:
```python
        # Add the actual settings content
        self._create_general_settings_section(content_layout)
        self._create_peer_mode_section(content_layout)
        self._create_updates_section(content_layout)
        self._create_danger_zone_section(content_layout)
        
        # Push version to bottom
        content_layout.addStretch()
        self._create_version_section(content_layout)
```

Replace with:
```python
        # Vault-scoped sections only (app-wide settings live in the
        # toolbar AppSettingsDialog — see
        # docs/superpowers/plans/2026-06-09-settings-two-surface-refactor.md).
        self._create_peer_mode_section(content_layout)
        if ENABLE_TURRET_BROWSER_PLUGIN:
            self._create_browser_plugin_section(content_layout)
        self._create_danger_zone_section(content_layout)

        content_layout.addStretch()
```

**c. Delete the now-unused methods.** Remove these blocks in full:
- `_create_general_settings_section`
- `_create_updates_section`
- `_create_temp_datastore_row`
- `_create_base_dir_row`
- `_create_tier_row`
- `_create_algo_row`
- `_create_salt_row`
- `_create_version_section`
- `_update_salt_visibility`
- `_on_temp_changed`
- `_on_base_changed`
- `_on_tier_changed`
- `_on_algo_changed`
- `_on_salt_changed`
- `_on_resalt`

**d. Drop the module-level version constant** (only used by `_create_version_section`). Find:
```python
__version__ = "0.0.1"
```
Delete it.

**e. Sanity-check** `_create_browser_plugin_section` still works as a top-level section (it already builds its own container — no changes needed).

- [ ] **Step 4: Run the SettingsPage tests to verify the cleanup**

Run: `.venv/bin/pytest tests/test_app_settings_dialog.py::test_vault_settings_page_no_longer_mounts_updates_widget tests/test_app_settings_dialog.py::test_vault_settings_page_no_longer_mounts_defaults_widget --import-mode=importlib -v`

Expected: PASS (2 tests)

Then run the broader vault-settings test suite to check nothing else broke:

Run: `.venv/bin/pytest tests/test_delete_vault_dialog.py tests/test_peer_section_port.py --import-mode=importlib -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/ui/vault/settings/page.py tests/test_app_settings_dialog.py
git commit -m "refactor(settings): strip app-wide sections from vault SettingsPage

General defaults, Updates, and the version footer move to the new
toolbar AppSettingsDialog. The vault sidebar Settings entry now holds
only per-vault concerns: Peer Mode, Browser Plugin (when enabled),
and the Danger Zone."
```

---

## Task 7: Delete the dead `on_settings` stub and its wiring

Goal: `LocksmithWindow.on_settings` and the `settings_clicked` signal connection are now dead (the toolbar opens the dialog directly). Remove them.

**Files:**
- Modify: `src/locksmith/ui/window.py` (lines 67, 553-557)
- Test: `tests/test_app_settings_dialog.py` (append — grep-style check)

---

- [ ] **Step 1: Write the failing test**

Append to `tests/test_app_settings_dialog.py`:

```python
def test_on_settings_stub_is_gone():
    """The toolbar opens AppSettingsDialog directly; the window-level
    on_settings stub is dead and must not be re-introduced."""
    from pathlib import Path
    import locksmith.ui.window as window_module
    source = Path(window_module.__file__).read_text()
    assert "def on_settings" not in source, (
        "on_settings stub re-introduced — toolbar opens AppSettingsDialog directly"
    )
    assert "settings_clicked.connect(self.on_settings)" not in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_app_settings_dialog.py::test_on_settings_stub_is_gone --import-mode=importlib -v`

Expected: FAIL

- [ ] **Step 3: Delete the stub and the signal connection**

Edit `src/locksmith/ui/window.py`:

**a. Delete the signal connection.** Find line 67:
```python
        self.toolbar.settings_clicked.connect(self.on_settings)
```
Delete that line.

**b. Delete the method body.** Find:
```python
    def on_settings(self):
        """Handle settings button click."""
        logger.info("Settings clicked")
        # Settings dialog is shown by toolbar
        pass

```
Delete those five lines (keep the blank line separation between neighboring methods).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_app_settings_dialog.py::test_on_settings_stub_is_gone --import-mode=importlib -v`

Expected: PASS

Then run the full new test file:

Run: `.venv/bin/pytest tests/test_app_settings_dialog.py --import-mode=importlib -v`

Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/ui/window.py tests/test_app_settings_dialog.py
git commit -m "chore(settings): delete dead on_settings stub and signal hook

Toolbar now opens AppSettingsDialog directly; the
settings_clicked → on_settings round-trip was a no-op."
```

---

## Task 8: End-to-end verification via the UI tester

Goal: confirm with a live Qt event loop that (a) the toolbar Settings button opens `AppSettingsDialog` with Defaults, Updates, and About sections; (b) opening a vault and clicking the sidebar Settings entry shows Peer Mode + Danger Zone (+ Browser Plugin if enabled) and **not** Updates or Defaults.

This is the verification step — no new code, just observation. Use the locksmith-ui-tester per `reference_ui_harness_cypress.md`.

**Files:**
- None (verification only)

---

- [ ] **Step 1: Run the full unit-test suite to confirm green**

Run: `.venv/bin/pytest tests/test_app_settings_dialog.py tests/test_toolbar_vault_name.py tests/test_delete_vault_dialog.py tests/test_peer_section_port.py --import-mode=importlib -v`

Expected: all PASS

- [ ] **Step 2: Launch the app**

Use the project's run pattern (locksmith.main entry point). Start the app via `.venv/bin/python -m locksmith.main` (or the project's preferred launcher) and the ui-tester socket at `~/.locksmith-control.sock`.

- [ ] **Step 3: Click the toolbar Settings button via the harness**

Use the ui-tester's `click` op with the toolbar settings button selector. Take a screenshot. Use the harness `tree` op to inspect for the following objectNames in the resulting dialog:

- `appSettingsDialog`
- `defaultsSettingsWidget`
- `updatesSettingsWidget`
- `appSettingsDialog.aboutVersionLabel`

All four must be present.

- [ ] **Step 4: Close the dialog, open a vault, navigate to vault Settings**

Use the harness to close the dialog (click `appSettingsDialog.closeButton`), open a test vault, and navigate to the vault sidebar Settings entry. Take a screenshot. Inspect the tree for:

- Peer Mode container (existing `peer_section` widget)
- Danger Zone delete button
- (if `ENABLE_TURRET_BROWSER_PLUGIN`) Browser Plugin section

And confirm these are **absent**:
- `updatesSettingsWidget`
- `defaultsSettingsWidget`

- [ ] **Step 5: Update memory**

If the refactor lands cleanly, update the design memo at
`~/.claude/projects/-Users-seriouscoderone-code-locksmith/memory/project_settings_refactor_design.md`
to mark the two-surface design as implemented (replacing the deferred Option-4 note). Then remove the entry from `MEMORY.md` if it no longer needs to be tracked, or shorten its description.

- [ ] **Step 6: Final commit (if any cleanup arose during E2E)**

```bash
git status
# if any uncommitted edits emerged during E2E:
git add -A
git commit -m "chore(settings): minor cleanups from E2E verification"
```

---

## Self-review notes

- **Spec coverage:** every spec line in the task brief maps to a task — AppSettingsDialog (T1), Updates relocation (T4), Defaults extraction (T2-T3), About (T5), vault SettingsPage strip (T6), stub deletion (T7), live verification (T8).
- **Placeholder scan:** no TBDs; every code block is complete.
- **Type consistency:** `LocksmithDialog` constructor params, `UpdatesSettingsWidget` API (`set_check_now_callback`, `set_view_log_callback`, `prefs=`), `LocksmithConfig.get_instance()`, and `BUILD_INFO.LOCKSMITH_VERSION` all match the inspected source.
- **One caveat to watch during execution:** the original `SettingsPage._create_browser_plugin_section` is currently called from inside `_create_general_settings_section`. Step 3b of Task 6 promotes it to a sibling, called from `__init__` directly. Confirm `_create_browser_plugin_section` doesn't reference any state that the general-settings code path initialized — a quick grep should show it only touches `self.locksmith_id_field`, `self.locksmith_copy_button`, `self.plugin_id_field`, all created inside its own helpers.
