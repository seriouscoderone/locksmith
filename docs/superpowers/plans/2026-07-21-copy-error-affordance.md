# Copy-to-clipboard for Error Surfaces — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a subtle one-click "copy full error text" affordance to Locksmith's error surfaces, with checkmark confirmation feedback.

**Architecture:** Enhance the shared `LocksmithCopyButton` with checkmark-swap feedback + a `copied` signal (DRY core), then drop a hover-revealed copy button into both shared `show_error` banners, the full-page `OnboardingErrorPage`, and make cryptic `QMessageBox` alerts text-selectable.

**Tech Stack:** Python, PySide6 (Qt Widgets), pytest.

## Global Constraints

- Locksmith UI only. No ServiceAID / micro-app-framework leakage (pure-KERI boundary). Verbatim: "this is locksmith UI only".
- Do NOT change error semantics — copy is purely additive.
- Colors come from `locksmith.ui.colors` tokens only (brand `apply_theme_overrides` correctness). Copy icon tinted `colors.DANGER` (readable on light-red `colors.BACKGROUND_ERROR`); checkmark `colors.SUCCESS`.
- Icon assets (confirmed present): `:/assets/material-icons/content_copy.svg`, `:/assets/material-icons/check.svg`.
- Test env: `QT_QPA_PLATFORM=offscreen` (set by `tests/conftest.py`), `pytest --import-mode=importlib`, focused test files ONLY. NEVER the full suite / `tests/peer` / `tests/integration` / `tests/test_instancing.py` / `tests/test_plugin_installer*|upgrade*|update*` (they crash macOS). `pytest-cov` segfaults on Qt-widget modules — do NOT pass `--cov`; use the coverage.py API if coverage numbers are needed.
- All tests use the session `qapp` fixture from `tests/conftest.py`.
- Branch: `copy-error-affordance` (already created from `development`).

## File Structure

- Modify `src/locksmith/ui/toolkit/widgets/buttons.py` — `LocksmithCopyButton` feedback + `copied` signal.
- Modify `src/locksmith/ui/toolkit/widgets/dialogs.py` — dialog error banner copy button + hover reveal.
- Modify `src/locksmith/ui/toolkit/widgets/page.py` — `LocksmithFormPage` error banner copy button + hover reveal.
- Modify `src/locksmith/ui/onboarding/home_page.py` — `OnboardingErrorPage` copy button.
- Create `src/locksmith/ui/toolkit/widgets/message_box.py` — `build_selectable_message_box()` helper.
- Modify `src/locksmith/ui/window.py` — route `_show_error` through the selectable helper.
- Modify `src/locksmith/ui/plugins/page.py` — route "Upgrade failed" through the selectable helper.
- Create tests: `tests/test_copy_button_feedback.py`, `tests/test_error_banner_copy.py`, `tests/test_onboarding_error_copy.py`, `tests/test_selectable_message_box.py`.

---

### Task 1: `LocksmithCopyButton` checkmark feedback + `copied` signal

**Files:**
- Modify: `src/locksmith/ui/toolkit/widgets/buttons.py:521-577`
- Test: `tests/test_copy_button_feedback.py`

**Interfaces:**
- Consumes: existing `LocksmithIconButton` (`self.icon_path`, `set_icon_color`, `_setup_icon`).
- Produces:
  - `LocksmithCopyButton(copy_content="", tooltip="Copy to clipboard", icon_size=36, parent=None, border=False, icon_color=None)` — new optional `icon_color` kwarg (base tint; `None` = raw icon).
  - `copied = Signal()` — emitted after a successful (non-empty) copy.
  - `_revert_icon()` — restores the base icon (test seam for post-feedback state).
  - Class constant `_FEEDBACK_MS = 1200`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_copy_button_feedback.py
from PySide6.QtWidgets import QApplication

from locksmith.ui.toolkit.widgets.buttons import LocksmithCopyButton

COPY_ICON = ":/assets/material-icons/content_copy.svg"
CHECK_ICON = ":/assets/material-icons/check.svg"


def test_copy_sets_clipboard_and_emits(qapp):
    btn = LocksmithCopyButton(copy_content="invalid literal for int()")
    seen = []
    btn.copied.connect(lambda: seen.append(True))

    btn.click()

    assert QApplication.clipboard().text() == "invalid literal for int()"
    assert seen == [True]


def test_copy_swaps_to_checkmark_then_reverts(qapp):
    btn = LocksmithCopyButton(copy_content="boom")

    btn.click()
    assert btn.icon_path == CHECK_ICON

    btn._revert_icon()
    assert btn.icon_path == COPY_ICON


def test_empty_content_is_a_noop(qapp):
    btn = LocksmithCopyButton(copy_content="")
    seen = []
    btn.copied.connect(lambda: seen.append(True))

    btn.click()

    assert seen == []
    assert btn.icon_path == COPY_ICON


def test_icon_color_kwarg_reverts_to_tint_not_raw(qapp):
    # A tinted copy button reverts to its base tint, not the raw icon.
    btn = LocksmithCopyButton(copy_content="x", icon_color="#DC2626")
    btn.click()
    assert btn.icon_path == CHECK_ICON
    btn._revert_icon()
    assert btn.icon_path == COPY_ICON  # base icon path restored
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest --import-mode=importlib tests/test_copy_button_feedback.py -v`
Expected: FAIL — `AttributeError: 'LocksmithCopyButton' object has no attribute 'copied'`.

- [ ] **Step 3: Add `QTimer` import**

At the top of `buttons.py`, add `QTimer` to the `PySide6.QtCore` import (currently `from PySide6.QtCore import Qt, QSize, Signal, QPoint`):

```python
from PySide6.QtCore import Qt, QSize, Signal, QPoint, QTimer
```

- [ ] **Step 4: Rewrite `LocksmithCopyButton` (lines 521-577)**

```python
class LocksmithCopyButton(LocksmithIconButton):
    """
    A copy button that copies content to the clipboard when clicked.

    On copy it briefly swaps its icon to a green checkmark as confirmation,
    then reverts, and emits ``copied``. Inherits Locksmith styling from
    LocksmithIconButton.
    """

    copied = Signal()

    _COPY_ICON = ":/assets/material-icons/content_copy.svg"
    _CHECK_ICON = ":/assets/material-icons/check.svg"
    _FEEDBACK_MS = 1200

    def __init__(self, copy_content: str = "", tooltip: str = "Copy to clipboard",
                 icon_size: int = 36, parent=None, border=False, icon_color=None):
        """
        Args:
            copy_content: Text copied to clipboard on click.
            tooltip: Tooltip text (default: "Copy to clipboard").
            icon_size: Icon size in pixels (default: 36).
            parent: Optional parent widget.
            border: Whether to show a border (default: False).
            icon_color: Optional base tint for the copy icon (``None`` = raw
                icon). The checkmark feedback always reverts back to this base.
        """
        super().__init__(
            icon_path=self._COPY_ICON,
            tooltip=tooltip,
            icon_size=icon_size,
            parent=parent,
            border=border
        )

        self._copy_content = copy_content
        self._base_color = icon_color
        if icon_color:
            self.set_icon_color(icon_color)

        self._feedback_timer = QTimer(self)
        self._feedback_timer.setSingleShot(True)
        self._feedback_timer.timeout.connect(self._revert_icon)

        self.clicked.connect(self._copy_to_clipboard)

    def _copy_to_clipboard(self):
        """Copy the content to the clipboard and flash the checkmark."""
        if not self._copy_content:
            return
        QApplication.clipboard().setText(self._copy_content)
        self._show_copied_feedback()
        self.copied.emit()

    def _show_copied_feedback(self):
        """Swap to a green checkmark for ``_FEEDBACK_MS`` then revert."""
        self.icon_path = self._CHECK_ICON
        self.set_icon_color(colors.SUCCESS)
        self._feedback_timer.start(self._FEEDBACK_MS)

    def _revert_icon(self):
        """Restore the base copy icon (tinted if a base color was set)."""
        self.icon_path = self._COPY_ICON
        if self._base_color:
            self.set_icon_color(self._base_color)
        else:
            self._setup_icon()

    def set_copy_content(self, content: str):
        """Update the text that will be copied to clipboard."""
        self._copy_content = content

    def get_copy_content(self) -> str:
        """Return the current copy content."""
        return self._copy_content
```

Confirm `colors` is imported in `buttons.py` (it is — used elsewhere in the file). If not, add `from locksmith.ui import colors`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest --import-mode=importlib tests/test_copy_button_feedback.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Regression-check existing copy-button callers compile/import**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest --import-mode=importlib tests/test_open_vault_dialog.py -v`
Expected: PASS (sanity that toolkit import path is intact).

- [ ] **Step 7: Commit**

```bash
git add src/locksmith/ui/toolkit/widgets/buttons.py tests/test_copy_button_feedback.py
git commit -m "feat(ui): LocksmithCopyButton checkmark feedback + copied signal"
```

---

### Task 2: Dialog error banner — hover-revealed copy icon

**Files:**
- Modify: `src/locksmith/ui/toolkit/widgets/dialogs.py` (`_build_error_banner` :265-299, `show_error` :552-599, imports :9-14)
- Test: `tests/test_error_banner_copy.py` (dialog cases)

**Interfaces:**
- Consumes: `LocksmithCopyButton` (Task 1), existing `self.error_banner`, `self.error_label`, `banner_layout`.
- Produces on `LocksmithDialog`:
  - `self.error_copy_button: LocksmithCopyButton`
  - `self._error_copy_opacity: QGraphicsOpacityEffect` (0.0 hidden, 1.0 shown)
  - `eventFilter(self, obj, event)` toggling opacity on `error_banner` Enter/Leave.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_error_banner_copy.py
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication

from locksmith.ui.toolkit.widgets.dialogs import LocksmithDialog


def test_dialog_copy_button_carries_full_message(qapp):
    dlg = LocksmithDialog(title="Test")
    dlg.show_error("invalid literal for int() with base 16: b'xyz'")

    assert dlg.error_copy_button.get_copy_content() == (
        "invalid literal for int() with base 16: b'xyz'"
    )


def test_dialog_copy_button_hidden_until_hover(qapp):
    dlg = LocksmithDialog(title="Test")
    dlg.show_error("boom")

    assert dlg._error_copy_opacity.opacity() == 0.0

    dlg.eventFilter(dlg.error_banner, QEvent(QEvent.Type.Enter))
    assert dlg._error_copy_opacity.opacity() == 1.0

    dlg.eventFilter(dlg.error_banner, QEvent(QEvent.Type.Leave))
    assert dlg._error_copy_opacity.opacity() == 0.0


def test_dialog_copy_click_copies_full_message(qapp):
    dlg = LocksmithDialog(title="Test")
    dlg.show_error("cryptic detail")
    dlg.error_copy_button.click()

    assert QApplication.clipboard().text() == "cryptic detail"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest --import-mode=importlib tests/test_error_banner_copy.py -v`
Expected: FAIL — `AttributeError: 'LocksmithDialog' object has no attribute 'error_copy_button'`.

- [ ] **Step 3: Add imports to `dialogs.py`**

Add `QEvent` to the `PySide6.QtCore` import (line 9) and import the copy button. Line 9 becomes:

```python
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Property, QSize, QEvent
```

Add near the other local imports at the top of the file:

```python
from locksmith.ui.toolkit.widgets.buttons import LocksmithCopyButton
```

(If a circular-import error appears — `buttons.py` importing from this module — instead import lazily inside `_build_error_banner`: `from locksmith.ui.toolkit.widgets.buttons import LocksmithCopyButton`.)

- [ ] **Step 4: Add the copy button in `_build_error_banner` (after the `error_label` block, before `main_layout.addWidget(self.error_banner)` at line 294)**

```python
        # Hover-revealed copy affordance (subtle; occupies a fixed slot so
        # the wrapped message never reflows when it fades in).
        self.error_copy_button = LocksmithCopyButton(
            tooltip="Copy error message",
            icon_size=18,
            icon_color=colors.DANGER,
        )
        self._error_copy_opacity = QGraphicsOpacityEffect(self.error_copy_button)
        self._error_copy_opacity.setOpacity(0.0)
        self.error_copy_button.setGraphicsEffect(self._error_copy_opacity)
        banner_layout.addWidget(self.error_copy_button)

        self.error_banner.installEventFilter(self)
```

- [ ] **Step 5: Add `eventFilter` method to `LocksmithDialog`**

Add as a new method on the class (e.g., directly after `_build_error_banner`):

```python
    def eventFilter(self, obj, event):
        """Fade the error-banner copy button in on hover, out on leave."""
        if obj is getattr(self, "error_banner", None):
            if event.type() == QEvent.Type.Enter:
                self._error_copy_opacity.setOpacity(1.0)
            elif event.type() == QEvent.Type.Leave:
                self._error_copy_opacity.setOpacity(0.0)
        return super().eventFilter(obj, event)
```

- [ ] **Step 6: Set copy content in `show_error` (after `self.error_label.setText(message)` at line 568)**

```python
        self.error_copy_button.set_copy_content(message)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest --import-mode=importlib tests/test_error_banner_copy.py -v`
Expected: PASS (dialog tests).

- [ ] **Step 8: Commit**

```bash
git add src/locksmith/ui/toolkit/widgets/dialogs.py tests/test_error_banner_copy.py
git commit -m "feat(ui): hover-reveal copy button on dialog error banner"
```

---

### Task 3: `LocksmithFormPage` error banner — hover-revealed copy icon

**Files:**
- Modify: `src/locksmith/ui/toolkit/widgets/page.py` (`_build_error_banner` :110-147, `show_error` :205-224, imports :7-11)
- Test: `tests/test_error_banner_copy.py` (page cases — append to the Task 2 file)

**Interfaces:**
- Consumes: `LocksmithCopyButton` (Task 1), existing `self.error_banner`, `self.error_label`, `banner_layout`.
- Produces on `LocksmithFormPage`: `self.error_copy_button`, `self._error_copy_opacity`, `eventFilter`.

- [ ] **Step 1: Append the failing page tests to `tests/test_error_banner_copy.py`**

```python
from locksmith.ui.toolkit.widgets.page import LocksmithFormPage


def _page():
    return LocksmithFormPage(title="Test", icon_path="")


def test_page_copy_button_carries_full_message(qapp):
    page = _page()
    page.show_error("invalid literal for int() with base 16: b'zz'")
    assert page.error_copy_button.get_copy_content() == (
        "invalid literal for int() with base 16: b'zz'"
    )


def test_page_copy_button_hidden_until_hover(qapp):
    page = _page()
    page.show_error("boom")
    assert page._error_copy_opacity.opacity() == 0.0

    page.eventFilter(page.error_banner, QEvent(QEvent.Type.Enter))
    assert page._error_copy_opacity.opacity() == 1.0

    page.eventFilter(page.error_banner, QEvent(QEvent.Type.Leave))
    assert page._error_copy_opacity.opacity() == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest --import-mode=importlib tests/test_error_banner_copy.py -k page -v`
Expected: FAIL — `AttributeError: 'LocksmithFormPage' object has no attribute 'error_copy_button'`.

- [ ] **Step 3: Add imports to `page.py`**

Add `QEvent` to the `PySide6.QtCore` import (line 7) and `QGraphicsOpacityEffect` to the `PySide6.QtWidgets` import (line 9), and import the copy button:

```python
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QSize, QEvent
```

Add `QGraphicsOpacityEffect` to the QtWidgets import list, and near the top add:

```python
from locksmith.ui.toolkit.widgets.buttons import LocksmithCopyButton
```

(Same circular-import fallback as Task 2 — import lazily inside `_build_error_banner` if needed.)

- [ ] **Step 4: Add the copy button in `_build_error_banner` (after the `error_label` block, before `self.main_layout.addWidget(self.error_banner)` at line 142)**

```python
        # Hover-revealed copy affordance (fixed slot; no reflow on fade-in).
        self.error_copy_button = LocksmithCopyButton(
            tooltip="Copy error message",
            icon_size=18,
            icon_color=colors.DANGER,
        )
        self._error_copy_opacity = QGraphicsOpacityEffect(self.error_copy_button)
        self._error_copy_opacity.setOpacity(0.0)
        self.error_copy_button.setGraphicsEffect(self._error_copy_opacity)
        banner_layout.addWidget(self.error_copy_button)

        self.error_banner.installEventFilter(self)
```

- [ ] **Step 5: Add `eventFilter` method to `LocksmithFormPage`**

```python
    def eventFilter(self, obj, event):
        """Fade the error-banner copy button in on hover, out on leave."""
        if obj is getattr(self, "error_banner", None):
            if event.type() == QEvent.Type.Enter:
                self._error_copy_opacity.setOpacity(1.0)
            elif event.type() == QEvent.Type.Leave:
                self._error_copy_opacity.setOpacity(0.0)
        return super().eventFilter(obj, event)
```

- [ ] **Step 6: Set copy content in `show_error` (after `self.error_label.setText(message)` at line 214)**

```python
        self.error_copy_button.set_copy_content(message)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest --import-mode=importlib tests/test_error_banner_copy.py -v`
Expected: PASS (all dialog + page tests).

- [ ] **Step 8: Commit**

```bash
git add src/locksmith/ui/toolkit/widgets/page.py tests/test_error_banner_copy.py
git commit -m "feat(ui): hover-reveal copy button on page error banner"
```

---

### Task 4: `OnboardingErrorPage` copy button

**Files:**
- Modify: `src/locksmith/ui/onboarding/home_page.py:272-310`
- Test: `tests/test_onboarding_error_copy.py`

**Interfaces:**
- Consumes: `LocksmithCopyButton` (Task 1).
- Produces on `OnboardingErrorPage`: `self.copy_button: LocksmithCopyButton` whose content is the full heading + body text.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_onboarding_error_copy.py
from locksmith.ui.onboarding.home_page import OnboardingErrorPage


def test_onboarding_error_copy_has_full_detail(qapp):
    page = OnboardingErrorPage("document_said mismatch on brand bundle")

    content = page.copy_button.get_copy_content()
    assert "document_said mismatch on brand bundle" in content
    assert "isn't available" in content  # heading text included
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest --import-mode=importlib tests/test_onboarding_error_copy.py -v`
Expected: FAIL — `AttributeError: 'OnboardingErrorPage' object has no attribute 'copy_button'`.

- [ ] **Step 3: Confirm imports in `home_page.py`**

`QHBoxLayout` is already imported. Add the copy button import near the other toolkit imports at the top of the file:

```python
from locksmith.ui.toolkit.widgets.buttons import LocksmithCopyButton
```

- [ ] **Step 4: Add the copy button in `OnboardingErrorPage.__init__` (after `layout.addWidget(body)` at line 308, before `layout.addStretch(2)`)**

```python
        # One-click copy of the full error (heading + cryptic detail).
        copy_row = QHBoxLayout()
        copy_row.addStretch()
        self.copy_button = LocksmithCopyButton(
            copy_content=f"{heading.text()}\n\n{body.text()}",
            tooltip="Copy error message",
            icon_size=18,
            icon_color=colors.DANGER,
        )
        copy_row.addWidget(self.copy_button)
        copy_row.addStretch()
        layout.addLayout(copy_row)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest --import-mode=importlib tests/test_onboarding_error_copy.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/locksmith/ui/onboarding/home_page.py tests/test_onboarding_error_copy.py
git commit -m "feat(ui): copy button on OnboardingErrorPage"
```

---

### Task 5: Selectable `QMessageBox` alerts

**Files:**
- Create: `src/locksmith/ui/toolkit/widgets/message_box.py`
- Modify: `src/locksmith/ui/window.py:1131-1133` (`_show_error`)
- Modify: `src/locksmith/ui/plugins/page.py:375-377` ("Upgrade failed")
- Test: `tests/test_selectable_message_box.py`

**Interfaces:**
- Produces: `build_selectable_message_box(parent, title, message, icon=QMessageBox.Icon.Warning) -> QMessageBox` — a warning box whose text is `TextSelectableByMouse`. Caller invokes `.exec()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_selectable_message_box.py
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from locksmith.ui.toolkit.widgets.message_box import build_selectable_message_box


def test_message_box_text_is_selectable(qapp):
    box = build_selectable_message_box(None, "Upgrade failed", "cryptic InstallError text")

    assert box.text() == "cryptic InstallError text"
    assert box.windowTitle() == "Upgrade failed"
    assert box.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse
    assert box.icon() == QMessageBox.Icon.Warning
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest --import-mode=importlib tests/test_selectable_message_box.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'locksmith.ui.toolkit.widgets.message_box'`.

- [ ] **Step 3: Create `message_box.py`**

```python
# -*- encoding: utf-8 -*-
"""Shared QMessageBox builders for Locksmith.

``build_selectable_message_box`` produces a warning box whose text can be
selected with the mouse, so cryptic error detail (e.g. KERI serialization
failures surfaced as ``InstallError``) can be copied out to relay. Callers
own the ``.exec()`` — the builder never blocks, which keeps it unit-testable.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QWidget


def build_selectable_message_box(
    parent: QWidget | None,
    title: str,
    message: str,
    icon: QMessageBox.Icon = QMessageBox.Icon.Warning,
) -> QMessageBox:
    """Build a warning ``QMessageBox`` with selectable/copyable text.

    Args:
        parent: Parent widget (or ``None``).
        title: Window title.
        message: Body text (kept fully selectable).
        icon: Message-box icon (default Warning).

    Returns:
        The configured box. The caller is responsible for ``.exec()``.
    """
    box = QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(title)
    box.setText(message)
    box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return box
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest --import-mode=importlib tests/test_selectable_message_box.py -v`
Expected: PASS.

- [ ] **Step 5: Route `window.py._show_error` through the helper (lines 1131-1133)**

Replace:

```python
    def _show_error(self, title: str, message: str) -> None:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(self, title, message)
```

with:

```python
    def _show_error(self, title: str, message: str) -> None:
        from locksmith.ui.toolkit.widgets.message_box import build_selectable_message_box
        build_selectable_message_box(self, title, message).exec()
```

- [ ] **Step 6: Route the plugins "Upgrade failed" box through the helper (`plugins/page.py:375-377`)**

Replace:

```python
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Upgrade failed", str(e))
```

with:

```python
            from locksmith.ui.toolkit.widgets.message_box import build_selectable_message_box
            build_selectable_message_box(self, "Upgrade failed", str(e)).exec()
```

- [ ] **Step 7: Sanity-check the edited modules import**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -c "import locksmith.ui.window, locksmith.ui.plugins.page; print('ok')"`
Expected: `ok`.

- [ ] **Step 8: Commit**

```bash
git add src/locksmith/ui/toolkit/widgets/message_box.py src/locksmith/ui/window.py src/locksmith/ui/plugins/page.py tests/test_selectable_message_box.py
git commit -m "feat(ui): selectable text on cryptic QMessageBox alerts"
```

---

### Task 6: Full focused-suite pass + audit report

**Files:** none (verification only).

- [ ] **Step 1: Run all new focused test files together**

Run:
```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest --import-mode=importlib \
  tests/test_copy_button_feedback.py \
  tests/test_error_banner_copy.py \
  tests/test_onboarding_error_copy.py \
  tests/test_selectable_message_box.py -v
```
Expected: PASS (all).

- [ ] **Step 2: Regression sanity on a couple of existing dialog/page tests**

Run:
```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest --import-mode=importlib \
  tests/test_open_vault_dialog.py tests/test_delete_vault_dialog.py -v
```
Expected: PASS (unchanged behavior).

- [ ] **Step 3: Write the coverage report to the PR/summary**

Report which surfaces were covered vs intentionally skipped, per the spec's audit table:
- Covered: both `show_error` banners (dialog + page, ~30 call sites), `OnboardingErrorPage`, cryptic `QMessageBox` alerts (`window._show_error`, plugins "Upgrade failed").
- Intentionally skipped (with reason): `UpdateFailedToast` (generic by spec §9.2), "Vault closed" `QMessageBox` (static copy), plugin `set_inline_error` (out of balanced scope).

---

## Self-Review

**Spec coverage:** Component 1 → Task 1; Component 2 (both banners) → Tasks 2 & 3; Component 3 → Task 4; Component 4 → Task 5; audit/report → Task 6. All spec sections mapped.

**Placeholder scan:** No TBD/TODO; every code step shows full code; every command has expected output.

**Type consistency:** `error_copy_button`, `_error_copy_opacity`, `eventFilter`, `set_copy_content`/`get_copy_content`, `copied`, `_revert_icon`, `_FEEDBACK_MS`, `build_selectable_message_box` used identically across tasks. Icon-path constants match (`content_copy.svg`, `check.svg`).
