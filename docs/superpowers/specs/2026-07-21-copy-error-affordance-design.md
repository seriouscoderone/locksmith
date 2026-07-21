# Copy-to-clipboard for Locksmith error surfaces — Design

**Date:** 2026-07-21
**Status:** Approved (brainstorm)
**Scope:** Locksmith UI only. No ServiceAID / micro-app-framework leakage (pure-KERI boundary).

## Problem

When Locksmith surfaces an error (the red inline banner in dialogs and pages), the
message is often a cryptic KERI serialization failure — e.g.
`invalid literal for int() with base 16: b'…'`. These are painful to relay by hand.
The user wants a **subtle** one-click affordance to copy the **full** error text, with
brief confirmation feedback. Error display is already centralized, so a single change
propagates widely.

## Goals / Non-goals

- **Goal:** subtle, unobtrusive copy affordance on the shared error banner (both
  `show_error` paths), copying the full message, with checkmark confirmation.
- **Goal:** audit every error surface; extend coverage to the balanced set below;
  report what was and wasn't covered.
- **Non-goal:** changing error *semantics*. Copy is purely additive.
- **Non-goal:** touching KERI/ServiceAID/micro-app code.

## Error-surface audit

| Surface | Path | Decision |
|---|---|---|
| `LocksmithDialog.show_error` banner | `ui/toolkit/widgets/dialogs.py:552` (built `_build_error_banner` :265) | **Add** hover-reveal copy icon |
| `Page.show_error` banner | `ui/toolkit/widgets/page.py:205` (built ~:110) | **Add** hover-reveal copy icon |
| `OnboardingErrorPage` | `ui/onboarding/home_page.py:272` | **Add** small copy button (cryptic EGF `detail`) |
| `window.py._show_error` (plugin uninstall) | `ui/window.py:1131` `QMessageBox.warning` | **Make text-selectable** (`TextSelectableByMouse`) |
| `plugins/page.py` "Upgrade failed" | `ui/plugins/page.py:376` `QMessageBox.warning` | **Make text-selectable** |
| `UpdateFailedToast` | `ui/toasts/update_failed.py` | **No change** — deliberately generic per spec §9.2; no cryptic detail on surface, click opens verification log |
| `window.py` "Vault closed" | `ui/window.py:903` `QMessageBox.warning` | **No change** — static friendly copy, nothing to relay |
| `plugins/page.py` `set_inline_error` | `ui/plugins/page.py:423` | **No change** — plugin-domain inline error, out of balanced scope |

~30 files call `show_error`; both banner paths share the same structure (HBox: error icon +
word-wrapping `error_label`), so the banner change reaches nearly all of them at once.

## Design

### Component 1 — `LocksmithCopyButton` checkmark feedback (DRY core)

`ui/toolkit/widgets/buttons.py:521`. Additive enhancement, opt-out-safe (default on):

- New `copied = Signal()` emitted after a successful copy (test seam — no reliance on
  tooltip/QToolTip pixels under offscreen).
- On copy: swap icon `:/assets/material-icons/content_copy.svg` →
  `:/assets/material-icons/check.svg` recolored `colors.SUCCESS`; a single-shot `QTimer`
  (~1200 ms) reverts to the original icon path + original color.
- Rapid re-clicks restart the timer (single pending revert); revert is idempotent.
- Revert logic exposed as a method so tests can trigger it deterministically without
  waiting on the timer.
- **What does it do / how used / depends on:** copies `_copy_content` to the clipboard and
  flashes a checkmark; used anywhere a copy control is wanted; depends only on
  `QApplication.clipboard`, `QTimer`, `colors`, and the two icon assets (both confirmed to
  exist: `check.svg`, `content_copy.svg`).
- All 6 existing usages inherit the confirmation flash — a consistency upgrade, not a
  semantic change.

### Component 2 — Shared error banner, hover-revealed copy icon

Both `_build_error_banner` (dialogs.py) and the page banner builder (page.py):

- Append a small borderless `LocksmithCopyButton(icon_size≈18, tooltip="Copy error message")`
  to the existing `banner_layout` after `error_label`.
- **Hover-reveal without layout jitter:** the button stays in the layout occupying a fixed
  slot; a `QGraphicsOpacityEffect` holds it at opacity 0 by default. An event filter (or
  enter/leave overrides) on `error_banner` fades opacity 0→1 on enter, 1→0 on leave. The
  wrapped `error_label` never reflows because the slot width is reserved.
- In each `show_error(message)`, call `self.error_copy_button.set_copy_content(message)` so
  the button always carries the full current message.
- Icon recolored to a muted tone readable on the light-red `colors.BACKGROUND_ERROR`;
  checkmark uses `colors.SUCCESS`. All colors via `colors.*` tokens so brand
  `apply_theme_overrides` stays correct (no OS light/dark switch exists — the banner
  background is a fixed light-error tint; correctness = readable icon + brand-token colors).

### Component 3 — `OnboardingErrorPage`

Add a small `LocksmithCopyButton` beside or under the body label, `set_copy_content` = the
full body text (heading + detail), so the cryptic EGF `detail` is one click away. Full-page
context; no hover-reveal needed (kept simple and visible-but-subtle).

### Component 4 — Selectable `QMessageBox` text

For `window.py._show_error` and `plugins/page.py` "Upgrade failed": construct the
`QMessageBox` explicitly and set
`msg.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)` so the
(potentially cryptic `InstallError`) text can be selected and copied. Cheap; no new widgets.

## Testing (Principle VII posture; headless/focused only)

Env: `QT_QPA_PLATFORM=offscreen`, `pytest --import-mode=importlib`, focused test files only.
Never the full suite / `tests/peer` / `tests/integration` / `tests/test_instancing.py` /
`tests/test_plugin_installer*|upgrade*|update*` (they crash macOS). `pytest-cov` segfaults on
Qt-widget modules → use the coverage.py API workaround.

- `LocksmithCopyButton`: click sets clipboard to `_copy_content`, emits `copied`, icon in
  checkmark state after click, reverts on the exposed revert method.
- Dialog banner: `show_error(msg)` sets copy content to full `msg`; clicking the button
  copies it; hover enter/leave toggles opacity (call the handlers directly).
- Page banner: same assertions.
- `OnboardingErrorPage`: copy button copies full body text.
- `QMessageBox` builders: assert `TextSelectableByMouse` flag is set.

## Risks

- Layout jitter on hover → mitigated by reserved fixed slot + opacity (no reflow).
- Breaking existing copy buttons → change is additive; existing constructor signature and
  `set_copy_content`/`get_copy_content` preserved; feedback is a visual add-on.
- Offscreen tooltip flakiness → avoided by testing the `copied` signal + icon state, not
  tooltip rendering.
