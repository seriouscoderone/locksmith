# locksmith-ui-tester — Stage 2 Design

**Status:** Approved 2026-05-18.
**Builds on:** [Stage 1 plugin loader spec](2026-05-16-locksmith-plugin-loader-design.md), branch `pr/dev-control-harness`, issue keri-foundation/locksmith#50, PR keri-foundation/locksmith#48.

## Goal

Relocate the in-core dev-control harness out of Locksmith and into a standalone, publicly-installable plugin (`locksmith-ui-tester`) that uses the `AppPlugin` contract shipped in Stage 1. Validates the contract end-to-end and closes the security feedback on PR #48 by removing the in-core attack surface entirely.

## Non-Goals (v1)

- **No protocol changes.** Lift-and-shift: same 9 ops (`ping`, `screenshot`, `tree`, `current_page`, `click`, `click_list_item`, `type`, `select`, plus the `Type:N` selector form), same wire format, same socket path `/tmp/locksmith-control.sock`. Existing test scripts must keep working unchanged.
- **No new capabilities.** Visual regression diff, structured log waits, batched ops are explicitly out of scope for v1. File for later versions.
- **No runtime permissioning.** The plugin runs with full wallet permissions like any other Locksmith plugin. Install confirmation is the trust gate.
- **No env-var gate.** `LOCKSMITH_DEV_CONTROL` is dropped entirely. Plugin installed and not excluded = harness active.

## Repository

- **Local:** `~/code/locksmith-ui-tester`
- **Remote:** `github.com/seriouscoderone/locksmith-ui-tester` (public)
- **License:** MIT
- **Python:** 3.13+ (matches Locksmith's floor)

## Layout

```
locksmith-ui-tester/
├── pyproject.toml             # package metadata + [project.scripts] devctl entry
├── locksmith-plugin.toml      # manifest read by Locksmith's installer
├── README.md                  # what it does, security warning, install instructions
├── LICENSE                    # MIT
├── src/
│   └── locksmith_ui_tester/
│       ├── __init__.py
│       ├── plugin.py          # LocksmithUiTesterPlugin(AppPlugin) — ~30 lines
│       ├── server.py          # DevControlServer + all 9 ops (verbatim from core)
│       └── cli.py             # devctl main entry (moved from tools/devctl.py)
└── tests/
    └── test_server.py         # moved from tests/test_dev_control.py
```

Single Python package, single plugin manifest, single entry-point. Small enough that one flat namespace is clearer than sub-packages.

## Manifest

`locksmith-plugin.toml`:

```toml
plugin_id = "ui_tester"
entry_point = "locksmith_ui_tester.plugin:LocksmithUiTesterPlugin"
manifest_version = 1
name = "Locksmith UI Tester"
version = "0.1.0"
description = """Dev-only UI test harness. Opens a UNIX socket at \
/tmp/locksmith-control.sock that lets any local process drive the wallet \
UI — inspect widgets, click buttons, type text, read screenshots. Install \
only on a development machine; do NOT install on a wallet holding real \
keys."""
author = "seriouscoderone"
homepage = "https://github.com/seriouscoderone/locksmith-ui-tester"
requires_locksmith = ">=0.0.1"
capabilities = ["app.service"]

[capabilities_detail]
"app.service" = "Runs a local control server while the wallet is open."
```

The description text is the trust-gate copy users see in the install confirmation panel. It must read like a warning, not like marketing.

## pyproject.toml

```toml
[project]
name = "locksmith-ui-tester"
version = "0.1.0"
description = "Dev-only UI test harness plugin for Locksmith"
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.13"
dependencies = []   # PySide6 + keri come from the host wallet's environment

[project.scripts]
devctl = "locksmith_ui_tester.cli:main"

[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"
```

No runtime dependencies — the plugin is loaded inside the wallet's Python process, so PySide6/keri are already available. The CLI uses only stdlib.

## Plugin Glue

```python
from locksmith.plugins.base import AppPlugin
from locksmith_ui_tester.server import DevControlServer, DEFAULT_SOCKET_PATH
from keri import help

logger = help.ogler.getLogger(__name__)


class LocksmithUiTesterPlugin(AppPlugin):
    plugin_id = "ui_tester"

    def __init__(self):
        self._window = None

    def initialize(self, app):
        pass  # nothing to do at discovery

    def on_app_started(self, app, window):
        # Captured for get_app_services() — manager calls that next
        # and constructs the service with the window reference.
        self._window = window
        logger.warning(
            "ui-tester: dev-control socket starting at %s — any local "
            "process can drive this wallet",
            DEFAULT_SOCKET_PATH,
        )

    def get_app_services(self):
        if self._window is None:
            return []
        return [DevControlServer(self._window)]
```

`DevControlServer` already has `.start()` / `.stop()` matching the service contract, so no wrapper class is needed. The PluginManager handles lifecycle: it calls `start()` after `on_app_started`, and `stop()` in reverse order before `on_app_stopping`.

## CLI

`src/locksmith_ui_tester/cli.py` is a verbatim move of `tools/devctl.py` plus a `main()` function the `[project.scripts]` entry point dispatches to. Same socket path default (`/tmp/locksmith-control.sock`), same JSON-over-AF_UNIX protocol, same exit codes (1 on connect failure, 2 on server error).

After `pip install` of the repo, `devctl` is on PATH. Existing test scripts that call `python3 tools/devctl.py ...` continue to work if the user keeps a shim, but the recommended invocation becomes `devctl ...`.

## Core Changes (back on `pr/dev-control-harness`)

After the plugin works end-to-end, a single commit on the harness branch:

- Delete `src/locksmith/dev_control.py` (362 lines)
- Delete `tools/devctl.py` (100 lines)
- Delete `tests/test_dev_control.py` (273 lines)
- Remove the 5-line `LOCKSMITH_DEV_CONTROL` block in `src/locksmith/ui/window.py:156–160`
- Add a short note to `docs/plugin-authoring.md` pointing dev-loop users at `seriouscoderone/locksmith-ui-tester`

Core loses ~735 lines and the `LOCKSMITH_DEV_CONTROL` env var entirely. The `from locksmith.dev_control import DevControlServer` import in `window.py` is the only cross-reference to remove.

## Order of Operations

The local-path → GitHub two-step is the critical validation. It proves both install sources work end-to-end before we strip the in-core fallback.

1. Build the plugin repo locally at `~/code/locksmith-ui-tester`. Initial commit covers everything in the layout above.
2. Install in the test wallet via the local-path source pointing at `~/code/locksmith-ui-tester`. Restart wallet. Confirm `devctl ping` works.
3. Run a representative subset of existing harness ops (`tree`, `click`, `type`, `screenshot`) to confirm parity.
4. Push to `github.com/seriouscoderone/locksmith-ui-tester`. Create the public repo via `gh repo create`.
5. Uninstall the local-path version from the test wallet. Install via GitHub source (`seriouscoderone/locksmith-ui-tester`). Restart. Confirm same behavior.
6. Cut the core changes (above section) as a single commit on `pr/dev-control-harness`. Push.
7. Re-run full test suite + harness smoke from the plugin install.
8. Close PR #48 (or amend its description to point at the new flow).

## Testing

- **Plugin repo:** the moved `test_server.py` runs against a temp socket path using a plain AF_UNIX client (same pattern as today). Add a `pyproject.toml`-driven `pytest` invocation. CI is nice-to-have but not blocking v1.
- **Locksmith side:** the existing harness-driven smoke tests on `pr/dev-control-harness` (already passing) re-run against a wallet that installs `locksmith-ui-tester` via local-path source. That's the integration test.
- **Per the testing memory:** all tests must be fully automated and machine-checkable. The harness itself provides the structured surface — no human-in-the-loop verification.

## Risks

- **PluginManager service-start fails silently.** If the manager swallows exceptions from `DevControlServer.start()`, the user installs the plugin and nothing happens. Mitigation: the existing `start()` already logs failures via `logger.error`. Confirm during smoke test that the log line appears when the socket is already bound.
- **`requires_locksmith` floor.** Set to `>=0.0.1` for now; bump once Locksmith ships a real version. The manifest parser already accepts open-ended ranges.
- **Public repo discoverability.** The plugin's whole purpose is to grant local socket control of the wallet. The manifest description text is the only thing standing between an uninformed user and a foot-gun. README must repeat the warning at the top.

## Out of Scope (Stage 3+)

- New ops (log wait, batched ops, structured event subscriptions)
- Visual regression diffing
- A second plugin to dogfood `VaultPlugin` migration cleanups
- Hardening the install confirmation copy beyond the manifest description
