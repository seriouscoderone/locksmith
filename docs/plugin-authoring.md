# Authoring a Locksmith Plugin

This guide shows how to write, package, and test a plugin for the
Locksmith wallet. The plugin loader is described in detail in
[`docs/superpowers/specs/2026-05-16-locksmith-plugin-loader-design.md`](superpowers/specs/2026-05-16-locksmith-plugin-loader-design.md);
this guide is the author's-eye view.

## Layout

A plugin is a git repository (or local directory) with:

```
your-plugin/
    locksmith-plugin.toml      # required: manifest
    your_plugin/                # required: Python package matching entry_point
        __init__.py
        plugin.py               # contains your Plugin class
```

## The manifest

`locksmith-plugin.toml` at the repo root:

```toml
plugin_id = "your_plugin"
entry_point = "your_plugin.plugin:YourPlugin"
manifest_version = 1

name = "Your Plugin Name"
version = "0.1.0"
description = "One-sentence summary shown in the install confirmation."

author = "Your Name"
homepage = "https://github.com/your-handle/your-plugin"
license = "Apache-2.0"

requires_locksmith = ">=0.2.0"

capabilities = ["app.shortcut", "app.service"]

[capabilities_detail]
"app.service" = "Runs a background heartbeat every 30 seconds."
```

`plugin_id` must match `^[a-z][a-z0-9_]*$`. `entry_point` must be
`module:Class`. Both fields are validated at install time.

## Which base class?

| If your plugin … | Inherit |
|---|---|
| Needs to install global shortcuts or run a service before any vault is open | `AppPlugin` |
| Adds vault pages, menu entries, or hooks into vault lifecycle | `VaultPlugin` |
| Does both | `AppPlugin, VaultPlugin` |

All plugins also implement `plugin_id` and `initialize(app)`.

## AppPlugin example (matches the in-tree `echo_app` test fixture)

```python
from keri import help
from locksmith.plugins.base import AppPlugin

logger = help.ogler.getLogger(__name__)


class EchoService:
    def start(self) -> None:
        logger.info("plugin.service.started plugin_id=echo_app")

    def stop(self) -> None:
        logger.info("plugin.service.stopped plugin_id=echo_app")


class EchoAppPlugin(AppPlugin):
    @property
    def plugin_id(self) -> str:
        return "echo_app"

    def initialize(self, app) -> None:
        pass

    def on_app_started(self, app, window) -> None:
        # window is the live QMainWindow. Use sparingly.
        pass

    def get_app_services(self):
        return [EchoService()]
```

## VaultPlugin overview

`VaultPlugin` is the contract `kerifoundation` uses today. See its
implementation at `src/locksmith/plugins/kerifoundation/plugin.py` for a
reference. Required methods: `on_vault_opened`, `on_vault_closed`,
`get_menu_entry`, `get_menu_section`, `get_pages`. Optional vault hooks
(witness state, post-auth) default to no-ops.

## Installing your plugin locally during development

1. From the wallet's Plugins page, click **+ Install plugin**.
2. Choose **Local path** and point to your plugin's directory.
3. Confirm the manifest in the trust dialog.
4. Restart Locksmith.

For GitHub-hosted plugins, push the repo and use the `user/repo`
shorthand in the source dialog.

## Testing your plugin

Plugins should ship their own pytest suite. The wallet's test conventions
(see `tests/conftest.py`) use a session-scoped `qapp` fixture; you can
import or replicate that pattern. Add structured `logger.info()` calls
at every state transition so your tests can assert against captured log
output rather than UI state — this is a hard rule for the wallet's own
tests and a strong recommendation for plugins.

## What you cannot do (v1)

- Pull additional Python dependencies. Your plugin must use only what
  the wallet's venv provides (`PySide6`, `keri`, `hio`, `locksmith` and
  Python stdlib). If you need a new dep, file an issue against the
  wallet so the dep can be added to its `pyproject.toml`.
- Run in a sandbox. Once installed, your plugin has full wallet
  permissions. The trust dialog warns the user about this; it is on you
  to deserve the trust.
- Skip restart. Every install, uninstall, exclude, or include change
  requires the user to restart the wallet before it takes effect.

## Capability strings

Capability strings in the manifest are informational only — they
populate the install dialog so the user knows what your plugin does.
The wallet does not enforce them at runtime. Use the recognized set
when applicable so the install dialog renders friendly copy:

| String | Meaning |
|---|---|
| `app.shortcut` | Installs global keyboard shortcuts |
| `app.service` | Runs one or more background services |
| `window.full_access` | Inspects or controls the full main window |
| `vault.full_access` | Accesses vault internals (VaultPlugin only) |
| `fs.write` | Writes to disk |
| `fs.read` | Reads from disk outside the plugin's own dir |
| `net.listen` | Opens a local listening socket |
| `net.connect` | Makes outbound network connections |

Unknown strings are shown verbatim with "(unrecognized)" — feel free to
add new ones; they just don't get pretty copy until the wallet learns
about them.

## Reference plugin: locksmith-ui-tester

A working `AppPlugin` you can install via the in-app Plugins UI:

- **GitHub source:** `seriouscoderone/locksmith-ui-tester`
- **What it does:** opens a JSON-over-unix-socket control surface so test scripts and dev loops can drive the running UI.
- **Why it exists:** validates the `AppPlugin` contract end-to-end and serves as a reference implementation for anyone writing an app-lifecycle plugin.

Read its `plugin.py` (~30 lines) for the minimal shape of an `AppPlugin` that owns a long-lived service. Read its `locksmith-plugin.toml` for an example manifest with a security warning in the description (the install confirmation is where users see that text).

**Security note:** the plugin opens a local control socket. Install only on a development machine.
