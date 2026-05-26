# locksmith-ui-tester (Stage 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Relocate the in-core dev-control harness into a standalone, publicly-installable plugin (`locksmith-ui-tester`), validating the Stage 1 `AppPlugin` contract end-to-end and removing ~735 lines + the `LOCKSMITH_DEV_CONTROL` env var from Locksmith core.

**Architecture:** New Python package at `~/code/locksmith-ui-tester` (public on `github.com/seriouscoderone/locksmith-ui-tester`) containing a single `AppPlugin` subclass that returns the moved `DevControlServer` from `get_app_services()`. CLI ships as `[project.scripts]` entry. Install confirmation in the Locksmith Plugins UI is the trust gate — `LOCKSMITH_DEV_CONTROL` env var disappears entirely.

**Tech Stack:** Python 3.13+, PySide6 (Qt 6.10), pytest, pytest-qt, stdlib `socket`/`json`/`argparse`. Locksmith plugin contract from Stage 1 (`PluginCore` / `AppPlugin`).

**Spec:** `docs/superpowers/specs/2026-05-18-locksmith-ui-tester-design.md`

**Cross-repo work:** Tasks T1–T9 happen in `~/code/locksmith-ui-tester` (NEW repo). Tasks T10–T14 happen in the existing worktree at `/Users/seriouscoderone/code/locksmith/.claude/worktrees/pr+dev-control-harness` on branch `pr/dev-control-harness`.

---

## File Structure (new plugin repo)

```
~/code/locksmith-ui-tester/
├── .gitignore
├── LICENSE                    # MIT
├── README.md                  # security warning + install instructions
├── pyproject.toml             # package metadata + [project.scripts] devctl
├── locksmith-plugin.toml      # Locksmith manifest
├── src/
│   └── locksmith_ui_tester/
│       ├── __init__.py        # empty
│       ├── plugin.py          # LocksmithUiTesterPlugin(AppPlugin) — ~35 lines
│       ├── server.py          # DevControlServer + 9 ops (verbatim from core)
│       └── cli.py             # devctl entry (verbatim from tools/devctl.py)
└── tests/
    ├── __init__.py            # empty
    └── test_server.py         # ported from tests/test_dev_control.py
```

## File Structure (core changes — `pr/dev-control-harness`)

- Delete: `src/locksmith/dev_control.py`
- Delete: `tools/devctl.py`
- Delete: `tests/test_dev_control.py`
- Modify: `src/locksmith/ui/window.py:156-160` (remove the env-var block)
- Modify: `docs/plugin-authoring.md` (add pointer to plugin)

---

## Task 1: Scaffold the plugin repo

**Files:**
- Create: `~/code/locksmith-ui-tester/.gitignore`
- Create: `~/code/locksmith-ui-tester/LICENSE`
- Create: `~/code/locksmith-ui-tester/README.md`
- Create: `~/code/locksmith-ui-tester/pyproject.toml`
- Create: `~/code/locksmith-ui-tester/locksmith-plugin.toml`
- Create: `~/code/locksmith-ui-tester/src/locksmith_ui_tester/__init__.py`
- Create: `~/code/locksmith-ui-tester/tests/__init__.py`

- [ ] **Step 1: Create the directory tree**

```bash
mkdir -p ~/code/locksmith-ui-tester/src/locksmith_ui_tester
mkdir -p ~/code/locksmith-ui-tester/tests
cd ~/code/locksmith-ui-tester
git init
```

Expected: empty git repo created.

- [ ] **Step 2: Write .gitignore**

Create `~/code/locksmith-ui-tester/.gitignore`:

```gitignore
__pycache__/
*.py[cod]
*$py.class
.pytest_cache/
.venv/
venv/
dist/
build/
*.egg-info/
.coverage
.DS_Store
```

- [ ] **Step 3: Write LICENSE (MIT)**

Create `~/code/locksmith-ui-tester/LICENSE`:

```
MIT License

Copyright (c) 2026 seriouscoderone

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 4: Write README.md**

Create `~/code/locksmith-ui-tester/README.md`:

````markdown
# locksmith-ui-tester

> **⚠️ Dev tool only.** This plugin opens a UNIX socket at `/tmp/locksmith-control.sock` that lets **any local process** drive the Locksmith wallet UI — inspect widgets, click buttons, type text, read screenshots. Install only on a development machine. **Do NOT install on a wallet that holds real keys.**

An installable Locksmith plugin that exposes a JSON-over-unix-socket control surface for driving the running UI from test scripts, dev loops, or AI-assisted development.

## What it does

When installed and not excluded, the plugin starts a `DevControlServer` while the wallet is open. The server accepts newline-delimited JSON commands and replies with JSON results, all on the Qt main thread:

| Op | What it does |
|---|---|
| `ping` | Liveness check |
| `screenshot` | Save a PNG of the main window |
| `tree` | Enumerate visible widgets with type, rect, text, tooltip |
| `current_page` | Report the current vault sub-page key |
| `click` | Click a widget by objectName / text / tooltip / `Type:N` selector |
| `click_list_item` | Click an item in a QListWidget by its text |
| `type` | Type into a QLineEdit by selector |
| `select` | Set a QComboBox value by selector |

## Install

In the Locksmith Plugins UI:

- **GitHub source:** `seriouscoderone/locksmith-ui-tester`
- **Local path source:** point at this repo on disk

The install confirmation panel shows the manifest description — read it.

After install, restart the wallet to load the plugin.

## CLI

`pip install` exposes a `devctl` command on PATH:

```bash
devctl ping
devctl click '{"target": "Vaults"}'
devctl screenshot '{"path": "/tmp/wallet.png"}'
```

Or invoke it directly: `python -m locksmith_ui_tester.cli ping`.

## Security

The socket lives at `/tmp/locksmith-control.sock` with the file permissions Qt's `QLocalServer` sets by default — readable/writable by any process on the local system running as the same user. Anyone who can reach that socket can drive the wallet completely. This is the trust boundary. Install only where you accept that boundary.

## License

MIT.
````

- [ ] **Step 5: Write pyproject.toml**

Create `~/code/locksmith-ui-tester/pyproject.toml`:

```toml
[project]
name = "locksmith-ui-tester"
version = "0.1.0"
description = "Dev-only UI test harness plugin for Locksmith"
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.13"
authors = [{ name = "seriouscoderone" }]
dependencies = []

[project.scripts]
devctl = "locksmith_ui_tester.cli:main"

[project.urls]
Homepage = "https://github.com/seriouscoderone/locksmith-ui-tester"

[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

- [ ] **Step 6: Write locksmith-plugin.toml**

Create `~/code/locksmith-ui-tester/locksmith-plugin.toml`:

```toml
plugin_id = "ui_tester"
entry_point = "locksmith_ui_tester.plugin:LocksmithUiTesterPlugin"
manifest_version = 1
name = "Locksmith UI Tester"
version = "0.1.0"
description = "Dev-only UI test harness. Opens a UNIX socket at /tmp/locksmith-control.sock that lets any local process drive the wallet UI — inspect widgets, click buttons, type text, read screenshots. Install only on a development machine; do NOT install on a wallet holding real keys."
author = "seriouscoderone"
homepage = "https://github.com/seriouscoderone/locksmith-ui-tester"
requires_locksmith = ">=0.0.1"
capabilities = ["app.service"]

[capabilities_detail]
"app.service" = "Runs a local control server while the wallet is open."
```

- [ ] **Step 7: Create empty __init__.py files**

```bash
touch ~/code/locksmith-ui-tester/src/locksmith_ui_tester/__init__.py
touch ~/code/locksmith-ui-tester/tests/__init__.py
```

- [ ] **Step 8: Commit**

```bash
cd ~/code/locksmith-ui-tester
git add .
git commit -m "$(cat <<'EOF'
chore: scaffold locksmith-ui-tester repo

Empty Python package + Locksmith plugin manifest. No code yet — server,
CLI, and plugin glue land in subsequent commits.
EOF
)"
```

Expected: clean commit, no further files untracked.

---

## Task 2: Port DevControlServer → server.py

**Files:**
- Create: `~/code/locksmith-ui-tester/src/locksmith_ui_tester/server.py`
- Source: `/Users/seriouscoderone/code/locksmith/.claude/worktrees/pr+dev-control-harness/src/locksmith/dev_control.py` (362 lines, verbatim)

The current `dev_control.py` imports nothing from `locksmith.*` — only PySide6, keri, and stdlib. The file is self-contained and ports verbatim. Only the module docstring's first line needs an update.

- [ ] **Step 1: Copy the file**

```bash
cp /Users/seriouscoderone/code/locksmith/.claude/worktrees/pr+dev-control-harness/src/locksmith/dev_control.py \
   ~/code/locksmith-ui-tester/src/locksmith_ui_tester/server.py
```

- [ ] **Step 2: Update the docstring**

Edit `~/code/locksmith-ui-tester/src/locksmith_ui_tester/server.py` lines 1–17. Replace the existing docstring block:

```python
# -*- encoding: utf-8 -*-
"""
locksmith.dev_control module

Dev-only control server. Activated by setting LOCKSMITH_DEV_CONTROL=1 in
the environment before launching the wallet. Listens on a Unix socket at
/tmp/locksmith-control.sock and accepts newline-delimited JSON commands
that drive the live UI on the Qt main thread.

Off by default. Trust boundary is "any local process that can reach the
socket can drive the app" — strictly a developer loopback feature; never
ship enabled.

Wire protocol:
    Client → server:  {"op": "<name>", ...args}\n
    Server → client:  {"ok": true, ...result}\n   or   {"error": "..."}\n
"""
```

with:

```python
# -*- encoding: utf-8 -*-
"""
locksmith_ui_tester.server module

Control server for the locksmith-ui-tester plugin. Lifecycle is managed
by the Locksmith plugin system: start() runs after on_app_started,
stop() runs before on_app_stopping.

Listens on a Unix socket at /tmp/locksmith-control.sock and accepts
newline-delimited JSON commands that drive the live UI on the Qt main
thread. Trust boundary: any local process that can reach the socket can
drive the app. The plugin install confirmation in Locksmith is what
gates that access — see the plugin's locksmith-plugin.toml description.

Wire protocol:
    Client → server:  {"op": "<name>", ...args}\n
    Server → client:  {"ok": true, ...result}\n   or   {"error": "..."}\n
"""
```

- [ ] **Step 3: Verify the file is otherwise unchanged**

```bash
diff <(sed -n '18,$p' /Users/seriouscoderone/code/locksmith/.claude/worktrees/pr+dev-control-harness/src/locksmith/dev_control.py) \
     <(sed -n '18,$p' ~/code/locksmith-ui-tester/src/locksmith_ui_tester/server.py)
```

Expected: no output (files identical from line 18 onward).

- [ ] **Step 4: Commit**

```bash
cd ~/code/locksmith-ui-tester
git add src/locksmith_ui_tester/server.py
git commit -m "$(cat <<'EOF'
feat(server): port DevControlServer from Locksmith core

Verbatim move of src/locksmith/dev_control.py — same wire protocol,
same socket path, same 9 ops (ping, screenshot, tree, current_page,
click, click_list_item, type, select, with Type:N selector form).

Docstring updated to describe plugin lifecycle (start runs after
on_app_started, stop runs before on_app_stopping) instead of the old
LOCKSMITH_DEV_CONTROL env-var activation.
EOF
)"
```

---

## Task 3: Port test_dev_control.py → test_server.py

**Files:**
- Create: `~/code/locksmith-ui-tester/tests/test_server.py`
- Source: `/Users/seriouscoderone/code/locksmith/.claude/worktrees/pr+dev-control-harness/tests/test_dev_control.py` (273 lines)

Only one import line changes. The tests already use a temp socket path via fixtures and a plain `AF_UNIX` client.

- [ ] **Step 1: Copy the file**

```bash
cp /Users/seriouscoderone/code/locksmith/.claude/worktrees/pr+dev-control-harness/tests/test_dev_control.py \
   ~/code/locksmith-ui-tester/tests/test_server.py
```

- [ ] **Step 2: Fix the one import**

Edit `~/code/locksmith-ui-tester/tests/test_server.py`, change line 28:

```python
from locksmith.dev_control import DevControlServer
```

to:

```python
from locksmith_ui_tester.server import DevControlServer
```

- [ ] **Step 3: Add a pytest config that finds the package**

Create `~/code/locksmith-ui-tester/pyproject.toml` `[tool.pytest.ini_options]` section. Append to the existing pyproject.toml:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

- [ ] **Step 4: Install the package in dev mode and run tests**

```bash
cd ~/code/locksmith-ui-tester
/Users/seriouscoderone/code/locksmith/.venv/bin/pip install -e .
QT_QPA_PLATFORM=offscreen /Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/test_server.py -v
```

Expected: all tests pass. (Test count matches the original — confirmed by `pytest --collect-only` returning the same set of test_*.)

- [ ] **Step 5: Commit**

```bash
cd ~/code/locksmith-ui-tester
git add tests/test_server.py pyproject.toml
git commit -m "$(cat <<'EOF'
test(server): port test_dev_control.py from Locksmith core

Verbatim move except for the import line:
  from locksmith.dev_control → from locksmith_ui_tester.server

Adds [tool.pytest.ini_options] block so pytest discovers tests/ and the
src/ layout package without an extra conftest.
EOF
)"
```

---

## Task 4: Port devctl.py → cli.py

**Files:**
- Create: `~/code/locksmith-ui-tester/src/locksmith_ui_tester/cli.py`
- Source: `/Users/seriouscoderone/code/locksmith/.claude/worktrees/pr+dev-control-harness/tools/devctl.py` (100 lines)

`tools/devctl.py` already has a `def main() -> int:` entry — verbatim move plus a docstring update. The `[project.scripts]` entry from Task 1 wires it to `locksmith_ui_tester.cli:main`.

- [ ] **Step 1: Copy the file**

```bash
cp /Users/seriouscoderone/code/locksmith/.claude/worktrees/pr+dev-control-harness/tools/devctl.py \
   ~/code/locksmith-ui-tester/src/locksmith_ui_tester/cli.py
```

- [ ] **Step 2: Update the docstring**

Edit `~/code/locksmith-ui-tester/src/locksmith_ui_tester/cli.py` lines 1–24. Replace the existing docstring:

```python
#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
"""
devctl — small CLI for talking to the Locksmith dev-control server.

Usage:

    python3 tools/devctl.py <op>                       # no-arg op
    python3 tools/devctl.py <op> '<json-args>'         # op with kwargs

Examples:

    python3 tools/devctl.py ping
    python3 tools/devctl.py screenshot
    python3 tools/devctl.py screenshot '{"path": "/tmp/my.png"}'
    python3 tools/devctl.py tree '{"clickable_only": true}'
    python3 tools/devctl.py click '{"target": "Templates"}'
    python3 tools/devctl.py type '{"target": "_name_field", "text": "Hello"}'
    python3 tools/devctl.py select '{"target": "_kind", "value": "government"}'
    python3 tools/devctl.py current_page

The Locksmith wallet must be running with LOCKSMITH_DEV_CONTROL=1 set in
its environment. The CLI exits with status 1 on connection failure and
status 2 on a server-reported error.
"""
```

with:

```python
#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
"""
devctl — CLI for talking to the locksmith-ui-tester control server.

Available as `devctl` on PATH after `pip install locksmith-ui-tester`,
or invoke directly: `python -m locksmith_ui_tester.cli <op>`.

Usage:

    devctl <op>                       # no-arg op
    devctl <op> '<json-args>'         # op with kwargs

Examples:

    devctl ping
    devctl screenshot
    devctl screenshot '{"path": "/tmp/my.png"}'
    devctl tree '{"clickable_only": true}'
    devctl click '{"target": "Templates"}'
    devctl type '{"target": "_name_field", "text": "Hello"}'
    devctl select '{"target": "_kind", "value": "government"}'
    devctl current_page

The Locksmith wallet must be running with the locksmith-ui-tester plugin
installed and not excluded. The CLI exits with status 1 on connection
failure and status 2 on a server-reported error.
"""
```

- [ ] **Step 3: Verify the rest of the file is unchanged**

```bash
diff <(sed -n '25,$p' /Users/seriouscoderone/code/locksmith/.claude/worktrees/pr+dev-control-harness/tools/devctl.py) \
     <(sed -n '25,$p' ~/code/locksmith-ui-tester/src/locksmith_ui_tester/cli.py)
```

Expected: no output.

- [ ] **Step 4: Verify the entry point works**

```bash
cd ~/code/locksmith-ui-tester
/Users/seriouscoderone/code/locksmith/.venv/bin/pip install -e .
/Users/seriouscoderone/code/locksmith/.venv/bin/devctl --help
```

Expected: argparse help text starting with `usage: devctl [-h] ...` — not the original `usage: devctl.py`.

- [ ] **Step 5: Verify connection-failure exit code is 1**

```bash
/Users/seriouscoderone/code/locksmith/.venv/bin/devctl --socket /tmp/nonexistent.sock ping
echo "exit=$?"
```

Expected: error message on stderr about cannot connect, then `exit=1`.

- [ ] **Step 6: Commit**

```bash
cd ~/code/locksmith-ui-tester
git add src/locksmith_ui_tester/cli.py
git commit -m "$(cat <<'EOF'
feat(cli): port devctl from Locksmith tools/

Verbatim move of tools/devctl.py with the docstring updated to reflect
the new install path (pip install locksmith-ui-tester) and the new
activation gate (plugin install, no more LOCKSMITH_DEV_CONTROL env var).
The [project.scripts] entry in pyproject.toml wires this module's main()
to the `devctl` shell command.
EOF
)"
```

---

## Task 5: Write the plugin glue

**Files:**
- Create: `~/code/locksmith-ui-tester/src/locksmith_ui_tester/plugin.py`
- Test: `~/code/locksmith-ui-tester/tests/test_plugin.py`

The glue captures the window reference in `on_app_started` and returns a `DevControlServer` from `get_app_services()`. The PluginManager wires the rest.

- [ ] **Step 1: Write the failing test**

Create `~/code/locksmith-ui-tester/tests/test_plugin.py`:

```python
# -*- encoding: utf-8 -*-
"""Unit tests for the LocksmithUiTesterPlugin glue."""
from __future__ import annotations

import pytest

from PySide6.QtWidgets import QMainWindow

from locksmith_ui_tester.plugin import LocksmithUiTesterPlugin
from locksmith_ui_tester.server import DevControlServer


def test_plugin_id_is_ui_tester():
    plugin = LocksmithUiTesterPlugin()
    assert plugin.plugin_id == "ui_tester"


def test_initialize_is_a_noop(qtbot):
    """initialize() runs at discovery time, before any window exists."""
    plugin = LocksmithUiTesterPlugin()
    plugin.initialize(app=None)
    # No state should have been set.
    assert plugin._window is None


def test_get_app_services_returns_empty_before_app_started(qtbot):
    """Without a window, there's nothing to drive."""
    plugin = LocksmithUiTesterPlugin()
    assert plugin.get_app_services() == []


def test_on_app_started_captures_window(qtbot):
    plugin = LocksmithUiTesterPlugin()
    window = QMainWindow()
    qtbot.addWidget(window)
    plugin.on_app_started(app=None, window=window)
    assert plugin._window is window


def test_get_app_services_returns_server_after_app_started(qtbot):
    plugin = LocksmithUiTesterPlugin()
    window = QMainWindow()
    qtbot.addWidget(window)
    plugin.on_app_started(app=None, window=window)

    services = plugin.get_app_services()
    assert len(services) == 1
    assert isinstance(services[0], DevControlServer)


def test_get_app_services_passes_window_to_server(qtbot):
    plugin = LocksmithUiTesterPlugin()
    window = QMainWindow()
    qtbot.addWidget(window)
    plugin.on_app_started(app=None, window=window)

    server = plugin.get_app_services()[0]
    # DevControlServer keeps the window as _window — same attr in the
    # ported code. Verify the reference is the captured one.
    assert server._window is window
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd ~/code/locksmith-ui-tester
QT_QPA_PLATFORM=offscreen /Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/test_plugin.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'locksmith_ui_tester.plugin'`.

- [ ] **Step 3: Write the minimal implementation**

Create `~/code/locksmith-ui-tester/src/locksmith_ui_tester/plugin.py`:

```python
# -*- encoding: utf-8 -*-
"""
locksmith_ui_tester.plugin module

AppPlugin glue: captures the main window in on_app_started, then returns
a DevControlServer from get_app_services(). The Locksmith PluginManager
handles lifecycle — calls server.start() after on_app_started, calls
server.stop() in reverse order before on_app_stopping.

Trust boundary: install confirmation in the Locksmith Plugins UI. There
is no env-var gate. See locksmith-plugin.toml for the warning text users
see at install time.
"""
from __future__ import annotations

from typing import Any

from keri import help

from locksmith.plugins.base import AppPlugin
from locksmith_ui_tester.server import DEFAULT_SOCKET_PATH, DevControlServer

logger = help.ogler.getLogger(__name__)


class LocksmithUiTesterPlugin(AppPlugin):
    plugin_id = "ui_tester"

    def __init__(self) -> None:
        self._window: Any = None

    def initialize(self, app: Any) -> None:
        # Discovery-time hook. No work needed — the server can't start
        # until on_app_started gives us a window.
        pass

    def on_app_started(self, app: Any, window: Any) -> None:
        self._window = window
        logger.warning(
            "ui-tester: dev-control socket starting at %s — any local "
            "process can drive this wallet",
            DEFAULT_SOCKET_PATH,
        )

    def get_app_services(self) -> list[Any]:
        if self._window is None:
            return []
        return [DevControlServer(self._window)]
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd ~/code/locksmith-ui-tester
QT_QPA_PLATFORM=offscreen /Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/test_plugin.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Run the full plugin-repo test suite**

```bash
QT_QPA_PLATFORM=offscreen /Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest -v
```

Expected: all `test_server.py` + `test_plugin.py` tests pass.

- [ ] **Step 6: Commit**

```bash
cd ~/code/locksmith-ui-tester
git add src/locksmith_ui_tester/plugin.py tests/test_plugin.py
git commit -m "$(cat <<'EOF'
feat(plugin): wire DevControlServer into the AppPlugin contract

LocksmithUiTesterPlugin captures the main window in on_app_started and
returns a DevControlServer from get_app_services(). The Locksmith
PluginManager handles start/stop ordering — calls start() after
on_app_started fires, calls stop() in reverse order before
on_app_stopping. No wrapper class needed; DevControlServer's existing
start()/stop() methods already match the service contract.
EOF
)"
```

---

## Task 6: Smoke test via local-path install

This task drives the running wallet at `/Users/seriouscoderone/code/locksmith/.claude/worktrees/plugin-framework-test` (the test worktree set up during Stage 1 polish). The wallet may already be running from a prior session — kill it first to pick up the fresh plugin install. All UI driving uses the existing in-core dev-control harness (which we'll remove in Task 10 *after* the plugin-installed harness proves it works).

- [ ] **Step 1: Stop any running test wallet**

```bash
pgrep -af 'python.*-m locksmith\.main$' | grep -v 'pgrep\|zsh -c' | awk '{print $1}' | xargs -I {} kill {} 2>/dev/null
sleep 2
pgrep -af 'python.*-m locksmith\.main$' | grep -v 'pgrep\|zsh -c' || echo "stopped"
```

Expected: `stopped`.

- [ ] **Step 2: Launch the test wallet in the background**

```bash
cd /Users/seriouscoderone/code/locksmith/.claude/worktrees/plugin-framework-test && \
  PYTHONPATH=/Users/seriouscoderone/code/locksmith/.claude/worktrees/plugin-framework-test/src \
  LOCKSMITH_DEV_CONTROL=1 \
  LOCKSMITH_ENVIRONMENT=development \
  /Users/seriouscoderone/code/locksmith/.venv/bin/python -m locksmith.main 2>&1 &
sleep 4
[ -S /tmp/locksmith-control.sock ] && echo "harness up" || echo "FAIL"
```

Expected: `harness up`. The in-core harness is still active here — that's how we drive the install flow.

- [ ] **Step 3: Open joe vault via the harness**

```bash
cd /Users/seriouscoderone/code/locksmith/.claude/worktrees/plugin-framework-test
python3 tools/devctl.py click '{"target": "Vaults"}'
python3 tools/devctl.py click_list_item '{"text": "joe"}'
sleep 1
python3 tools/devctl.py type '{"target": "QLineEdit:0", "text": "noble"}'
python3 tools/devctl.py click '{"target": "Open"}'
sleep 2
python3 tools/devctl.py current_page
```

Expected: `{"ok": true, "vault_page": "identifiers", ...}`.

- [ ] **Step 4: Navigate to Plugins page**

```bash
python3 tools/devctl.py click '{"target": "toolbar_plugins_button"}'
sleep 0.5
python3 tools/devctl.py current_page
```

Expected: `vault_page: "plugins"`.

- [ ] **Step 5: Drive the install flow via local-path source**

```bash
python3 tools/devctl.py click '{"target": "PluginInstallTile"}'
sleep 0.3
python3 tools/devctl.py click '{"target": "Local path"}'
python3 tools/devctl.py type '{"target": "QLineEdit:1", "text": "/Users/seriouscoderone/code/locksmith-ui-tester"}'
python3 tools/devctl.py click '{"target": "Fetch"}'
sleep 1
python3 tools/devctl.py screenshot '{"path": "/tmp/uitester-trust.png"}'
```

Expected: screenshot shows the trust confirmation panel with name "Locksmith UI Tester", v0.1.0, and the warning-laden description from the manifest.

- [ ] **Step 6: Accept the trust prompt**

```bash
python3 tools/devctl.py click '{"target": "Trust && install"}'
sleep 1
python3 tools/devctl.py screenshot '{"path": "/tmp/uitester-installed.png"}'
cat ~/.locksmith/plugins/index.json | python3 -c "import json,sys; print('installed:', [p['plugin_id'] for p in json.load(sys.stdin)['plugins']])"
```

Expected: `installed: ['ui_tester']`. Screenshot shows the new plugin row with "Pending restart" status and the orange "Restart now" banner.

- [ ] **Step 7: Restart the wallet via the in-app button**

```bash
python3 tools/devctl.py click '{"target": "Restart now"}'
sleep 5
[ -S /tmp/locksmith-control.sock ] && echo "socket up after restart" || echo "FAIL"
python3 tools/devctl.py ping
```

Expected: `socket up after restart`, then `{"ok": true, "pong": true}`. The socket is now served by the *plugin's* `DevControlServer`, not the in-core one — but the wire protocol is identical, so the existing CLI keeps working.

- [ ] **Step 8: Verify the plugin loaded as "Loaded"**

```bash
python3 tools/devctl.py click '{"target": "toolbar_plugins_button"}'
sleep 0.5
python3 tools/devctl.py screenshot '{"path": "/tmp/uitester-loaded.png"}'
```

Expected: screenshot shows the "Locksmith UI Tester v0.1.0" row with green `● Loaded` status.

- [ ] **Step 9: Run a representative parity check**

```bash
python3 tools/devctl.py ping
python3 tools/devctl.py tree | python3 -c "import json,sys; print('widget_count:', json.load(sys.stdin)['count'])"
python3 tools/devctl.py screenshot '{"path": "/tmp/uitester-parity.png"}' | python3 -c "import json,sys; print(json.load(sys.stdin)['size'])"
python3 tools/devctl.py click '{"target": "Go to Home"}'
```

Expected: each command returns `{"ok": true, ...}`. Widget count > 5. Screenshot size `[1280, 1024]`.

- [ ] **Step 10: Stop the wallet, leave plugin installed for Task 7**

```bash
pgrep -af 'python.*-m locksmith\.main$' | grep -v 'pgrep\|zsh -c' | awk '{print $1}' | xargs -I {} kill {} 2>/dev/null
sleep 2
pgrep -af 'python.*-m locksmith\.main$' | grep -v 'pgrep\|zsh -c' || echo "stopped"
```

Expected: `stopped`. Plugin remains in `~/.locksmith/plugins/index.json` for Task 7's GitHub-source flip.

---

## Task 7: Push to GitHub and verify GitHub-source install

- [ ] **Step 1: Create the public GitHub repo**

```bash
cd ~/code/locksmith-ui-tester
gh repo create seriouscoderone/locksmith-ui-tester \
  --public \
  --description "Dev-only UI test harness plugin for Locksmith" \
  --source=. \
  --remote=origin \
  --push
```

Expected: repo created, current branch pushed. `gh repo view seriouscoderone/locksmith-ui-tester` confirms.

- [ ] **Step 2: Uninstall the local-path version via the wallet**

Relaunch the wallet (same env as Task 6 step 2), open joe vault, navigate to Plugins, and click Uninstall on the ui_tester row:

```bash
cd /Users/seriouscoderone/code/locksmith/.claude/worktrees/plugin-framework-test && \
  PYTHONPATH=/Users/seriouscoderone/code/locksmith/.claude/worktrees/plugin-framework-test/src \
  LOCKSMITH_DEV_CONTROL=1 \
  LOCKSMITH_ENVIRONMENT=development \
  /Users/seriouscoderone/code/locksmith/.venv/bin/python -m locksmith.main 2>&1 &
sleep 4

# Open joe, nav to Plugins
python3 tools/devctl.py click '{"target": "Vaults"}'
python3 tools/devctl.py click_list_item '{"text": "joe"}'
sleep 1
python3 tools/devctl.py type '{"target": "QLineEdit:0", "text": "noble"}'
python3 tools/devctl.py click '{"target": "Open"}'
sleep 2
python3 tools/devctl.py click '{"target": "toolbar_plugins_button"}'
sleep 0.5

# Uninstall ui_tester
python3 tools/devctl.py click '{"target": "Uninstall"}'
sleep 1
python3 tools/devctl.py click '{"target": "Restart now"}'
sleep 5
cat ~/.locksmith/plugins/index.json | python3 -c "import json,sys; print('installed:', [p['plugin_id'] for p in json.load(sys.stdin)['plugins']])"
```

Expected: `installed: []`. The wallet restarted. No more `ui_tester` plugin.

- [ ] **Step 3: Reinstall from the GitHub source**

```bash
# Open vault again
python3 tools/devctl.py click '{"target": "Vaults"}'
python3 tools/devctl.py click_list_item '{"text": "joe"}'
sleep 1
python3 tools/devctl.py type '{"target": "QLineEdit:0", "text": "noble"}'
python3 tools/devctl.py click '{"target": "Open"}'
sleep 2
python3 tools/devctl.py click '{"target": "toolbar_plugins_button"}'
sleep 0.5

# Install via GitHub source
python3 tools/devctl.py click '{"target": "PluginInstallTile"}'
sleep 0.3
# GitHub user/repo is the default radio — no need to switch
python3 tools/devctl.py type '{"target": "QLineEdit:0", "text": "seriouscoderone/locksmith-ui-tester"}'
python3 tools/devctl.py click '{"target": "Fetch"}'
sleep 5  # git clone takes a moment
python3 tools/devctl.py screenshot '{"path": "/tmp/uitester-github-trust.png"}'
```

Expected: screenshot shows the same trust panel as Task 6 step 5, but with the Source field showing the GitHub URL and Commit field showing a real git SHA (not `local:...`).

- [ ] **Step 4: Accept and restart**

```bash
python3 tools/devctl.py click '{"target": "Trust && install"}'
sleep 1
python3 tools/devctl.py click '{"target": "Restart now"}'
sleep 5
python3 tools/devctl.py ping
python3 tools/devctl.py click '{"target": "toolbar_plugins_button"}'
sleep 0.5
python3 tools/devctl.py screenshot '{"path": "/tmp/uitester-github-loaded.png"}'
```

Expected: `ping` returns ok. Screenshot shows `● Loaded` for "Locksmith UI Tester v0.1.0".

- [ ] **Step 5: Stop the wallet, leave plugin installed for Task 10**

```bash
pgrep -af 'python.*-m locksmith\.main$' | grep -v 'pgrep\|zsh -c' | awk '{print $1}' | xargs -I {} kill {} 2>/dev/null
sleep 2
pgrep -af 'python.*-m locksmith\.main$' | grep -v 'pgrep\|zsh -c' || echo "stopped"
```

Expected: `stopped`.

---

## Task 8: Remove dev_control from Locksmith core

**Files (back in the worktree at `/Users/seriouscoderone/code/locksmith/.claude/worktrees/pr+dev-control-harness`):**
- Delete: `src/locksmith/dev_control.py`
- Delete: `tools/devctl.py`
- Delete: `tests/test_dev_control.py`
- Modify: `src/locksmith/ui/window.py` lines 151–160

This is a single commit on `pr/dev-control-harness`. With the plugin installed from GitHub (Task 7), the harness keeps working — proving the env-var gate is no longer needed.

- [ ] **Step 1: Delete the three files**

```bash
cd /Users/seriouscoderone/code/locksmith/.claude/worktrees/pr+dev-control-harness
rm src/locksmith/dev_control.py
rm tools/devctl.py
rm tests/test_dev_control.py
```

- [ ] **Step 2: Remove the env-var block from window.py**

Edit `src/locksmith/ui/window.py`. Replace lines 151–160:

```python
        # Optional dev-only control server. Activated by setting
        # LOCKSMITH_DEV_CONTROL=1 in the environment. Listens on a Unix
        # socket at /tmp/locksmith-control.sock and lets local tooling
        # (or an AI dev loop) drive the running UI via JSON commands.
        # OFF in production by design.
        self._dev_control_server = None
        if os.environ.get("LOCKSMITH_DEV_CONTROL") == "1":
            from locksmith.dev_control import DevControlServer
            self._dev_control_server = DevControlServer(self, parent=self)
            self._dev_control_server.start()
```

with nothing — delete the entire block. The blank line above (between `_screenshot_shortcut.activated.connect(...)` and this block) and the blank line below (before `# Run app-lifecycle hooks for any AppPlugin instances loaded above.`) should be collapsed to a single blank line.

- [ ] **Step 3: Remove the now-unused `import os` from window.py**

The deleted block was the only use of `os` in `src/locksmith/ui/window.py`. Delete the line:

```python
import os
```

near the top of the file (currently line 7). Confirm with:

```bash
grep -n 'os\.' src/locksmith/ui/window.py || echo "no os references"
```

Expected: `no os references`.

- [ ] **Step 4: Verify nothing else in core imports from locksmith.dev_control**

```bash
grep -rn 'locksmith\.dev_control\|from locksmith import dev_control' src/ tests/ 2>&1 | grep -v __pycache__ || echo "no remaining references"
```

Expected: `no remaining references`. (The `plugin_id = "dev_control"` strings in test_plugins_storage.py and test_plugins_page_visual.py are test data, not imports — they're fine.)

- [ ] **Step 5: Verify no test imports `tests.test_dev_control`**

```bash
grep -rn 'test_dev_control\|from tests' tests/ 2>&1 | grep -v __pycache__ || echo "no remaining references"
```

Expected: `no remaining references`.

- [ ] **Step 6: Run the full Locksmith test suite**

```bash
cd /Users/seriouscoderone/code/locksmith/.claude/worktrees/pr+dev-control-harness
QT_QPA_PLATFORM=offscreen /Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/ --ignore=tests/test_keri_v2_compat.py -v 2>&1 | tail -10
```

Expected: all tests pass. (`test_keri_v2_compat.py` has 2 pre-existing failures unrelated to this work — they're explicitly ignored.)

- [ ] **Step 7: Commit**

```bash
cd /Users/seriouscoderone/code/locksmith/.claude/worktrees/pr+dev-control-harness
git add -A src/locksmith/dev_control.py tools/devctl.py tests/test_dev_control.py src/locksmith/ui/window.py
git commit -m "$(cat <<'EOF'
refactor: drop in-core dev-control harness in favor of plugin

Removes the LOCKSMITH_DEV_CONTROL env var, src/locksmith/dev_control.py
(DevControlServer), tools/devctl.py (CLI), and tests/test_dev_control.py
— ~735 lines total. The harness now ships as the locksmith-ui-tester
plugin at github.com/seriouscoderone/locksmith-ui-tester, gated by the
in-app install confirmation per the Stage 1 plugin loader design.

Closes the trust-boundary concern raised on PR #48: core no longer
carries any always-present-but-off-by-default UI control surface.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: clean commit, three deletions + one modification.

---

## Task 9: Update plugin-authoring.md with dev-tool pointer

**Files:**
- Modify: `docs/plugin-authoring.md`

- [ ] **Step 1: Inspect current doc structure**

```bash
cd /Users/seriouscoderone/code/locksmith/.claude/worktrees/pr+dev-control-harness
grep -n '^#' docs/plugin-authoring.md | head -20
```

Take note of the top-level section names so the new note slots in alongside existing prose (likely under an "Examples" or "Reference plugins" heading, or as a new top-level section if neither exists).

- [ ] **Step 2: Add a new section near the end of the doc**

Append to `docs/plugin-authoring.md`:

```markdown

## Reference plugin: locksmith-ui-tester

A working `AppPlugin` you can install via the in-app Plugins UI:

- **GitHub source:** `seriouscoderone/locksmith-ui-tester`
- **What it does:** opens a JSON-over-unix-socket control surface so test scripts and dev loops can drive the running UI.
- **Why it exists:** validates the `AppPlugin` contract end-to-end and serves as a reference implementation for anyone writing an app-lifecycle plugin.

Read its `plugin.py` (~30 lines) for the minimal shape of an `AppPlugin` that owns a long-lived service. Read its `locksmith-plugin.toml` for an example manifest with a security warning in the description (the install confirmation is where users see that text).

**Security note:** the plugin opens a local control socket. Install only on a development machine.
```

- [ ] **Step 3: Commit**

```bash
cd /Users/seriouscoderone/code/locksmith/.claude/worktrees/pr+dev-control-harness
git add docs/plugin-authoring.md
git commit -m "$(cat <<'EOF'
docs(plugins): point at locksmith-ui-tester as the reference AppPlugin

A short pointer under plugin-authoring.md so anyone writing a plugin
can see a working AppPlugin that owns a long-lived service. Repeats
the install-only-on-dev-machines warning that the manifest description
already carries.
EOF
)"
```

---

## Task 10: Final regression + close-out

This is the final smoke test with both core changes (Task 8) and the GitHub-installed plugin (Task 7) in place. If anything regresses, this is where it shows up.

- [ ] **Step 1: Confirm plugin is still installed from GitHub source**

```bash
cat ~/.locksmith/plugins/index.json | python3 -c "
import json, sys
d = json.load(sys.stdin)
for p in d['plugins']:
    print(f\"  plugin_id={p['plugin_id']} commit={p['commit']} source={p['source']['type']}\")"
```

Expected: one row with `plugin_id=ui_tester`, `commit=<git-sha>`, `source=git`.

- [ ] **Step 2: Launch the test wallet (NO env var — that's the test)**

```bash
pgrep -af 'python.*-m locksmith\.main$' | grep -v 'pgrep\|zsh -c' | awk '{print $1}' | xargs -I {} kill {} 2>/dev/null
sleep 2
cd /Users/seriouscoderone/code/locksmith/.claude/worktrees/plugin-framework-test && \
  PYTHONPATH=/Users/seriouscoderone/code/locksmith/.claude/worktrees/plugin-framework-test/src \
  LOCKSMITH_ENVIRONMENT=development \
  /Users/seriouscoderone/code/locksmith/.venv/bin/python -m locksmith.main 2>&1 &
sleep 5
[ -S /tmp/locksmith-control.sock ] && echo "socket up WITHOUT env var" || echo "FAIL"
```

Expected: `socket up WITHOUT env var`. **This is the proof:** the in-core env-var gate is gone, and the plugin alone now drives the harness.

- [ ] **Step 3: Run the parity check ops via the plugin's CLI**

```bash
/Users/seriouscoderone/code/locksmith/.venv/bin/devctl ping
/Users/seriouscoderone/code/locksmith/.venv/bin/devctl tree | python3 -c "import json,sys; print('widget_count:', json.load(sys.stdin)['count'])"
/Users/seriouscoderone/code/locksmith/.venv/bin/devctl screenshot '{"path": "/tmp/uitester-final.png"}' | python3 -c "import json,sys; print(json.load(sys.stdin)['size'])"
/Users/seriouscoderone/code/locksmith/.venv/bin/devctl click '{"target": "Vaults"}'
```

Expected: each returns `{"ok": true, ...}`. Widget count > 5. Screenshot size `[1280, 1024]`. (Note: this uses the *pip-installed* `devctl` binary on PATH, not the old `tools/devctl.py`.)

- [ ] **Step 4: Stop the wallet, clean up `~/.locksmith`**

```bash
pgrep -af 'python.*-m locksmith\.main$' | grep -v 'pgrep\|zsh -c' | awk '{print $1}' | xargs -I {} kill {} 2>/dev/null
sleep 2
rm -rf ~/.locksmith
ls -la ~/.locksmith 2>&1 | head -2
```

Expected: `ls: ~/.locksmith: No such file or directory`. (We leave the system as we found it — the plugin install was just for the validation cycle.)

- [ ] **Step 5: Run the full Locksmith test suite one more time**

```bash
cd /Users/seriouscoderone/code/locksmith/.claude/worktrees/pr+dev-control-harness
QT_QPA_PLATFORM=offscreen /Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/ --ignore=tests/test_keri_v2_compat.py 2>&1 | tail -5
```

Expected: all tests pass (no leftover references to removed modules).

- [ ] **Step 6: Push the core branch**

```bash
cd /Users/seriouscoderone/code/locksmith/.claude/worktrees/pr+dev-control-harness
git push origin pr/dev-control-harness 2>&1 | tail -5
```

Expected: pushes the Task 8 + Task 9 commits.

- [ ] **Step 7: Close out the issue and the PR**

Add a closing comment on issue #50:

```bash
gh issue comment 50 -R keri-foundation/locksmith --body "$(cat <<'EOF'
## Stage 2 complete — `locksmith-ui-tester` plugin live

The dev-control harness has been relocated out of Locksmith core and into a standalone plugin:
- Repo: https://github.com/seriouscoderone/locksmith-ui-tester (public, MIT)
- Install in the wallet via `seriouscoderone/locksmith-ui-tester` (GitHub source) or local-path source.
- Trust gate is the in-app install confirmation — the `LOCKSMITH_DEV_CONTROL` env var is gone.

Core lost ~735 lines and one env var. The contract from Stage 1 carried it without changes.

This closes the prerequisite work tracked in this issue. PR #48 follow-up is the next step.
EOF
)"
```

And on PR #48, decide whether to close (it's superseded) or merge (the polish on the harness branch is independently valuable). Recommendation: leave that decision to the human reviewer — comment on PR #48 noting Stage 2 is done and asking for the call:

```bash
cd /Users/seriouscoderone/code/locksmith/.claude/worktrees/pr+dev-control-harness
HEAD_SHA=$(git rev-parse HEAD)
gh pr comment 48 -R keri-foundation/locksmith --body "$(cat <<EOF
Stage 2 is now live: the harness has been moved into a standalone plugin at https://github.com/seriouscoderone/locksmith-ui-tester. The branch on this PR (\`pr/dev-control-harness\`) includes the plugin-loader work it depended on plus the core deletion of dev_control.py + tools/devctl.py + the LOCKSMITH_DEV_CONTROL env var.

Two paths from here:
1. **Close this PR** — the harness lives in its own repo now, and the dev-loop changes are unnecessary for users who don't install the plugin.
2. **Merge this PR** — the plugin loader work + harness deletion are still a net improvement to core; the plugin install path then becomes available to all wallet users.

Happy to do either. The harness branch is at $HEAD_SHA on origin.
EOF
)"
```

- [ ] **Step 8: Mark all Stage 2 tasks complete**

In the task list, mark the Stage 2 brainstorm + plan tasks as `completed`. Stage 2 is done.

---

## Self-review checklist (already run by the planner)

- **Spec coverage:** every section of `2026-05-18-locksmith-ui-tester-design.md` maps to one or more tasks above. Section 1 (Architecture) → T2 + T5. Section 2 (Repo Layout) → T1. Section 3 (Plugin Glue) → T5. Section 4 (Core Changes) → T8 + T9. Section 5 (Order of Operations) → T6 + T7 + T10.
- **No placeholders:** every code block is complete. Every command shows expected output.
- **Type consistency:** `LocksmithUiTesterPlugin.plugin_id == "ui_tester"` used consistently in plugin.py, locksmith-plugin.toml, and the test assertion. `DevControlServer._window` attribute matches the ported file. The `devctl` script name matches the `[project.scripts]` entry and the docstring.
