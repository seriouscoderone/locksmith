# Dev-Control Harness

A small, optional control surface for driving the live Locksmith UI from
external tooling — local scripts, integration tests, or an AI dev loop.

## Status

**Dev-only.** Activated by setting `LOCKSMITH_DEV_CONTROL=1` before
launching. **Never enabled in production.** Trust boundary: any local
process that can reach the Unix socket can drive the app.

## Activation

```bash
LOCKSMITH_DEV_CONTROL=1 .venv/bin/python -m locksmith.main
```

The wallet logs `DevControlServer listening on /tmp/locksmith-control.sock`
once it's up. Without the env var, the server is never instantiated.

## Wire protocol

Unix domain socket at `/tmp/locksmith-control.sock`. Each connection is
one-shot: client sends one newline-delimited JSON command, server
replies with one newline-delimited JSON response, both sides disconnect.

```
client → server:   {"op": "<name>", ...args}\n
server → client:   {"ok": true,  ...result}\n
                   {"error": "...", ...details}\n
```

## CLI

`tools/devctl.py` is a small Python wrapper. Run it from the project
root with any Python 3.13 — it has no dependencies beyond stdlib.

```bash
python3 tools/devctl.py ping
python3 tools/devctl.py screenshot
python3 tools/devctl.py tree '{"clickable_only": true}'
python3 tools/devctl.py click '{"target": "Templates"}'
python3 tools/devctl.py current_page
```

## Operations

| `op`           | Args                                | Returns                                      | Notes |
|----------------|-------------------------------------|----------------------------------------------|-------|
| `ping`         | —                                   | `{ok, pong}`                                 | sanity check |
| `screenshot`   | `path?` (default `/tmp/locksmith-screenshot.png`) | `{ok, path, size: [w, h]}` | grabs the main window |
| `tree`         | `visible_only?` (true), `clickable_only?` (false), `text_contains?` | `{ok, count, widgets: [...]}` | each widget: `type`, `objectName`, `text?`, `rect`, `enabled`, `visible` |
| `current_page` | —                                   | `{ok, vault_page, previous_vault_page}`      | VaultPage's `_current_page_key` |
| `click`        | `target` (required)                 | `{ok, clicked: {…widget info…}}`             | resolves target by `objectName` or exact `.text()` match |
| `type`         | `target`, `text`                    | `{ok}`                                       | works on `QLineEdit` and `QPlainTextEdit` |
| `select`       | `target`, `value`                   | `{ok}`                                       | sets a `QComboBox`'s current text |

Unknown `op` returns `{error, available: [...]}` listing valid op names.

## Widget targeting

`click` / `type` / `select` resolve their `target` by walking the visible
widget tree and matching against:

1. **`objectName`** — exact match. Most reliable. Use this when a widget
   has a stable name in code (most plugin widgets do).
2. **`.text()`** — exact match against the trimmed text of any widget
   that has a `text()` method (buttons, labels, line-edits).

The first match in widget-tree order wins. If a target is ambiguous,
use `tree` first to see what's available and pick a more specific
identifier.

## What this does NOT do

- **Modal dialogs.** `QFileDialog` / `QMessageBox` block the Qt main
  thread, which means the control server can't respond while one is
  open. Driving an import flow needs a plugin-specific in-process
  command (e.g. a `designer.import_path` op) that bypasses the dialog.
- **Drag-drop, multi-touch, scroll-into-view.** Deferred to v2.
- **Cross-process discovery.** Socket path is hardcoded to
  `/tmp/locksmith-control.sock`. One wallet instance per machine while
  the harness is active.

## When to use it vs. visual tests

Use the **visual smoke tests** (`tests/_screenshots/`) for regression
coverage that runs in CI: they're cheap, hermetic, and `QT_QPA_PLATFORM=
offscreen` makes them reliable.

Use the **dev-control harness** for live iteration that the offscreen
tests can't catch — full-window-size layout issues, hover/focus state,
real font rendering, multi-page navigation flows.

They are complementary; the harness does not replace the test suite.
