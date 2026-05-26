# Locksmith Plugin Loader — Stage 1 Design

**Status:** Draft for review
**Date:** 2026-05-16
**Tracking issue:** [keri-foundation/locksmith#50](https://github.com/keri-foundation/locksmith/issues/50)
**Author:** Joseph Hunsaker (brainstormed with Claude via superpowers)

## TL;DR

Today's plugin contract is vault-scoped: every plugin must implement vault hooks, and discovery is limited to Python entry-points wired at install time of the wallet itself. PR #48 ([dev-control harness](https://github.com/keri-foundation/locksmith/pull/48)) attempts to add an in-core UI control surface and is blocked on review for trust-boundary reasons.

Rather than hardening the harness in place, this design extracts dev-control as a future installable plugin by first delivering the prerequisite Stage 1: a small extension to the plugin contract (app-scoped hooks) and a from-scratch in-app plugin loader. Stage 2 (dev-control as a plugin) and closing PR #48 are separate cycles built on Stage 1.

## Goals

1. **Plugin contract supports app-scoped plugins** alongside the existing vault-scoped surface. An app-scoped plugin can run before any vault is opened, install global shortcuts, and own long-lived window-attached services.
2. **In-app install / uninstall / per-wallet exclude.** A new top-level "Plugins" page on the home stack (reachable pre-vault-unlock) is the single surface for managing installed plugins.
3. **Sources:** GitHub `user/repo` shorthand and local filesystem path. Manifest at the plugin repo root: `locksmith-plugin.toml`.
4. **Trust model:** Install-time confirmation. Plugins run with full wallet permissions once installed. Trust dialog lists declared capabilities but enforces none at runtime.
5. **Multi-wallet aware:** Plugin clones are user-scoped (shared across Locksmith instances on the same machine); per-wallet exclude list allows one instance to opt out without affecting others.
6. **Restart-required semantics:** Every install / uninstall / exclude / include change requires restart in v1.

## Non-goals (v1)

- pip / PyPI install
- Plugin Python dependencies beyond the wallet venv (PySide6, keri, hio, locksmith, stdlib)
- Plugin signing, trust store, or sandboxing
- Sources beyond GitHub user/repo + local filesystem
- Auth for private repos
- Plugin update flow beyond uninstall-and-reinstall
- Per-plugin configuration UI
- Plugin marketplace / catalog
- Hot-load or hot-disable
- Cross-plugin communication contracts

These are intentionally out of scope and will be addressed in later cycles if needed.

---

## Section A — Architecture overview

Five components land together in Stage 1:

### A.1 Contract restructure
`src/locksmith/plugins/base.py`. `PluginBase` is replaced by a small `PluginCore` (just `plugin_id` + `initialize`), plus two sibling base classes: `AppPlugin` (lifecycle, shortcuts, services) and `VaultPlugin` (vault hooks, menu, pages). Existing `KeriFoundationPlugin` becomes a `VaultPlugin` subclass; existing tests stay green.

### A.2 Loader rewrite
`src/locksmith/plugins/manager.py`. Drops entry-points as the primary discovery mechanism. Reads `~/.locksmith/plugins/index.json`, importlib-loads each plugin from its clone directory, instantiates the right class, dispatches lifecycle hooks against the right protocol. Entry-points stay supported as a *secondary* discovery path so in-tree plugins like `kerifoundation` keep working without packaging changes.

### A.3 Install / uninstall service
New module `src/locksmith/plugins/installer.py`. Pure Python, no UI. Takes a source descriptor (`{type: "github", user_repo: "..."}` or `{type: "local", path: "..."}`), clones / copies into `~/.locksmith/plugins/<plugin-id>/`, parses the manifest, atomically updates `index.json`. Uninstall is the reverse. Does not import the plugin code.

### A.4 Plugins page
New top-level page `src/locksmith/ui/plugins/page.py` registered as `Pages.PLUGINS` in `src/locksmith/ui/navigation.py`. Lists installed plugins with state badges, install button → two-step wizard (source → trust/confirm), uninstall, per-wallet exclude toggle, "restart required" banner.

### A.5 Window/app integration
`src/locksmith/ui/window.py` + `src/locksmith/core/apping.py`. After `LocksmithWindow` finishes its own init, `PluginManager` walks loaded `AppPlugin` instances and runs each one's `on_app_started(app, window)`, installs declared `QShortcut`s, starts declared `AppService`s. Symmetric teardown on `closeEvent` calls `on_app_stopping` and `AppService.stop()` for each plugin.

---

## Section B — Plugin contract

```python
# src/locksmith/plugins/base.py

class PluginCore(ABC):
    """Shared minimum every plugin must implement."""

    @property
    @abstractmethod
    def plugin_id(self) -> str: ...

    @abstractmethod
    def initialize(self, app: LocksmithApplication) -> None: ...


class AppPlugin(PluginCore):
    """Plugin that hooks into app/window lifecycle (no vault required)."""

    def on_app_started(self, app, window) -> None: pass
    def on_app_stopping(self, app) -> None: pass

    def get_app_shortcuts(self) -> list[tuple[QKeySequence, Callable[[], None]]]:
        return []

    def get_app_services(self) -> list[AppService]:
        return []


class VaultPlugin(PluginCore):
    """Plugin that hooks into vault lifecycle (the existing surface)."""

    @abstractmethod
    def on_vault_opened(self, vault) -> None: ...
    @abstractmethod
    def on_vault_closed(self, vault, *, clear: bool = False) -> None: ...
    @abstractmethod
    def get_menu_entry(self) -> MenuButton: ...
    @abstractmethod
    def get_menu_section(self) -> list[QWidget]: ...
    @abstractmethod
    def get_pages(self) -> dict[str, QWidget]: ...

    def get_doers(self) -> list[doing.Doer]: return []
    def prepare_vault_deletion(self, vault) -> None: pass
    def get_witness_batches(self, vault, hab_pre): return None
    def get_witness_state(self, vault, wit_eid): return None
    def update_witness_state(self, vault, wit_eid): pass
    def update_witness_state_after_auth(self, vault, wit_eid): pass
    async def after_identifier_authenticated(self, vault, hab) -> None: pass


# Existing capability mixins keep their shape; semantics are now scoped to VaultPlugin.
class AccountProviderPlugin(ABC): ...
class IdentifierUploadProviderPlugin(ABC): ...
class WitnessProviderPlugin(ABC): ...
class WatcherProviderPlugin(ABC): ...
class CredentialProviderPlugin(ABC): ...
```

`AppService` is **duck-typed**: any object with `.start() -> None` and `.stop() -> None`. PluginManager owns service lifetimes; start order is plugin discovery order; stop order is reverse.

`PluginManager` dispatch is **type-aware**:
- App-level loop walks plugins where `isinstance(p, AppPlugin)`.
- Vault-level loop walks plugins where `isinstance(p, VaultPlugin)`.
- A plugin may inherit both (`class Hybrid(AppPlugin, VaultPlugin): ...`) and gets both code paths called.

`KeriFoundationPlugin` migration:

```python
# before
class KeriFoundationPlugin(PluginBase, AccountProviderPlugin): ...

# after
class KeriFoundationPlugin(VaultPlugin, AccountProviderPlugin): ...
```

No method renames, no signature changes, no behavior changes. The existing test suite is the regression gate.

---

## Section C — Manifest format

`locksmith-plugin.toml` at the plugin repo root.

```toml
# Required for load — PluginManager fails the plugin if any are missing or malformed.
plugin_id = "dev_control"
entry_point = "locksmith_dev_control.plugin:DevControlPlugin"
manifest_version = 1

# Required for trust dialog — must be present, content non-empty, not otherwise validated.
name = "Dev Control Harness"
version = "0.1.0"
description = "JSON-over-unix-socket harness for driving the live UI"

# Optional metadata.
author = "Joseph Hunsaker"
homepage = "https://github.com/seriouscoderone/locksmith-dev-control"
license = "Apache-2.0"

# Optional version gate. Wallet refuses to load if its version doesn't satisfy.
requires_locksmith = ">=0.2.0"

# Informational capabilities. Populates the trust dialog. NOT enforced at runtime.
# Recognized strings (others rendered verbatim with "(unrecognized)" suffix):
#   app.shortcut         — declares get_app_shortcuts() returns non-empty
#   app.service          — declares get_app_services() returns non-empty
#   window.full_access   — declares it uses on_app_started(window) for raw widget access
#   vault.full_access    — declares VaultPlugin hooks
#   fs.write             — declares it writes to disk
#   net.listen           — declares it opens a local listening socket
#   net.connect          — declares it opens outbound connections
capabilities = [
  "app.shortcut",
  "app.service",
  "window.full_access",
  "fs.write",
  "net.listen",
]

# Optional human-readable per-capability notes. Rendered as indented bullets
# under the matching capability in the trust dialog.
[capabilities_detail]
"fs.write"   = "Writes screenshot PNGs to ~/.locksmith/plugins/dev_control/screenshots/."
"net.listen" = "Unix socket at $XDG_RUNTIME_DIR/locksmith-dev-control/<pid>.sock"
```

Parser: standard library `tomllib` (Python 3.11+).

---

## Section D — Storage layout

```
~/.locksmith/plugins/
    index.json                              # shared registry, atomic writes
    <plugin-id>/                            # one dir per installed plugin (== repo clone)
        locksmith-plugin.toml
        <python_package>/
            __init__.py
            plugin.py
            ...

<keri-base>/locksmith/plugin-enable.json    # per-wallet exclude list
```

### `~/.locksmith/plugins/index.json` (shared across wallet instances)

```json
{
  "format": 1,
  "plugins": [
    {
      "plugin_id": "dev_control",
      "source": {
        "type": "github",
        "user_repo": "seriouscoderone/locksmith-dev-control",
        "ref": null
      },
      "commit": "a3f9c1dabe7c0f5e8b7a2b9d0c4e1f2a3b4c5d6e",
      "installed_at": "2026-05-16T18:21:34Z",
      "manifest_snapshot": { /* parsed manifest, captured at install time */ }
    }
  ]
}
```

`manifest_snapshot` is the parsed `.toml` as JSON. Used by the Plugins page to render rows without re-reading every refresh and to detect "manifest has changed since install" cases (reinstall required to update).

### `<keri-base>/locksmith/plugin-enable.json` (per wallet instance)

```json
{
  "format": 1,
  "excluded": ["plugin_id_a", "plugin_id_b"]
}
```

Empty file or missing file = load all installed plugins. Edited only via the Plugins page UI (no hand-editing expected).

### Atomic write protocol for `index.json`

Write to `index.json.tmp` → `os.replace()` onto `index.json`. POSIX `replace` is atomic, so a wallet reading the index while another is installing either sees the old version or the new one — never a half-written file. Last-writer-wins on collision; each wallet picks up the latest state on next restart.

---

## Section E — UI flow

### Plugins page

`Pages.PLUGINS` — new top-level home-stack entry, reachable from the home toolbar between Home and the settings gear. Always reachable; never gated behind vault unlock.

```
┌─ Plugins ──────────────────────────────────────────────────────────────┐
│  ⚠ Restart required to finish applying changes.    [ Restart now ]    │   ← only when index has changed since boot
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │ KERI Foundation              v0.3.1           [ in-tree ]        │ │   ← entry-point plugin (no Uninstall)
│  │ Onboarding, witnesses, watchers                                  │ │
│  │ ● Loaded                                                          │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │ Dev Control Harness          v0.1.0   from github:.../dev-control │ │
│  │ JSON-over-unix-socket harness for driving the live UI            │ │
│  │ ● Loaded   [ Exclude on this wallet ]  [ Uninstall ]              │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │ Some Other Plugin            v0.2.0                              │ │
│  │ ⚠ Incompatible: requires Locksmith ≥ 0.5 (you have 0.4)          │ │
│  │             [ Exclude on this wallet ]  [ Uninstall ]            │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                                                                        │
│                                              [ + Install plugin ]      │
└────────────────────────────────────────────────────────────────────────┘
```

**Per-plugin states** drive the badge:

| State | Meaning |
|---|---|
| `Loaded` | Plugin imported, lifecycle hooks fired. |
| `Excluded (this wallet)` | In index but in this wallet's `plugin-enable.json.excluded`. Not imported. |
| `Incompatible` | `requires_locksmith` not satisfied. Not imported. |
| `Failed to load` | Import or hook raised. Expandable to show traceback. Not retried until restart. |
| `Files missing` | Index has the plugin but `~/.locksmith/plugins/<plugin-id>/` is gone. Offers Reinstall or Remove from registry. |
| `In-tree` | Loaded via entry-points fallback (e.g., `kerifoundation`). Cannot be uninstalled from the UI. |

### Install flow — Step 1 (source dialog)

```
╔══════════════════════════════════════════════════════════╗
║ Install plugin                                           ║
╠══════════════════════════════════════════════════════════╣
║ Source:                                                  ║
║   ◉ GitHub  user/repo  [______________]                  ║
║   ○ Local path        [______________]                   ║
║                                                          ║
║ Branch/ref (optional): [______________]                  ║
║ (defaults to default branch HEAD)                        ║
║                                                          ║
║                              [ Cancel ]  [ Fetch ]       ║
╚══════════════════════════════════════════════════════════╝
```

Validation:
- `user/repo` must match `^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$`
- Local path must exist and contain `locksmith-plugin.toml`
- Errors render inline under the offending input

**Fetch action:**
1. Resolve target.
   - GitHub: `git clone --depth 1 [--branch <ref>] https://github.com/<user_repo>.git ~/.locksmith/plugins/.tmp-<random>/`
   - Local: `shutil.copytree(<path>, ~/.locksmith/plugins/.tmp-<random>/)`
2. Parse `locksmith-plugin.toml`. Fail with inline error if missing or required fields absent.
3. Capture commit SHA (`git rev-parse HEAD` for github source; for local, captured as the manifest version field plus a timestamp).
4. Open Step 2.

### Install flow — Step 2 (trust dialog)

```
╔══════════════════════════════════════════════════════════╗
║ Trust 'Dev Control Harness' v0.1.0?                     ║
╠══════════════════════════════════════════════════════════╣
║ From:    github.com/seriouscoderone/locksmith-          ║
║          dev-control @ a3f9c1d                          ║
║ Author:  Joseph Hunsaker                                ║
║                                                          ║
║ 'JSON-over-unix-socket harness for driving the          ║
║  live UI'                                                ║
║                                                          ║
║ This plugin declares it will:                            ║
║   • install global keyboard shortcuts                    ║
║   • run background services                              ║
║   • inspect / control the full main window               ║
║   • write to disk                                        ║
║       ↳ Writes screenshot PNGs to                        ║
║         ~/.locksmith/plugins/dev_control/screenshots/    ║
║   • open a local listening socket                        ║
║       ↳ Unix socket at                                   ║
║         $XDG_RUNTIME_DIR/locksmith-dev-control/<pid>.sock║
║                                                          ║
║ Plugins run with full wallet permissions.                ║
║ Only install plugins you trust.                          ║
║                                                          ║
║                  [ Cancel ]  [ Trust & install ]         ║
╚══════════════════════════════════════════════════════════╝
```

Cancel → `shutil.rmtree(.tmp-<random>)`, dismiss.
Install → atomic rename `.tmp-<random>` → `<plugin-id>/`; atomic-update `index.json`; show "Restart required" banner on the Plugins page; close dialog.

### Uninstall flow

Confirmation modal: `Uninstall '<name>'? Files at ~/.locksmith/plugins/<plugin-id>/ will be removed.` → `rmtree` + atomic index update + restart banner.

### Per-wallet exclude / include

Toggle button on each row; updates `<keri-base>/locksmith/plugin-enable.json` atomically; shows restart banner.

---

## Section F — Failure modes & error handling

| Failure | Outcome |
|---|---|
| Manifest missing / malformed | **Fetch** fails with inline error in source dialog. Tmp clone removed. |
| Required field missing (`plugin_id` / `entry_point` / `manifest_version`) | Same as above. |
| `plugin_id` already installed | **Trust & install** fails with "A plugin with this ID is already installed at github:user/repo. Uninstall it first." |
| `git clone` fails (network, auth, bad ref) | Inline error in source dialog with git's stderr surfaced. Tmp dir cleaned. |
| `requires_locksmith` not satisfied | Install proceeds; Plugins page shows the row with **⚠ Incompatible** badge. Plugin not loaded. Status persists across restarts. |
| `import_module(entry_point)` raises at startup | Plugin marked **⚠ Failed to load** with expandable traceback. Other plugins continue. |
| `on_app_started(app, window)` raises | Same — marked Failed to load; `on_app_stopping` NOT called for this plugin. |
| `AppService.start()` raises | Service skipped, plugin marked **⚠ Service start failed** with traceback. Plugin's shortcuts still install. |
| Shortcut callback raises at runtime | Logged, swallowed. Plugin remains loaded. |
| Plugin clone dir missing on startup but in `index.json` | Marked **⚠ Files missing** in Plugins page with [ Reinstall ] / [ Remove from registry ] buttons. |
| `index.json` malformed | Logged as warning, treated as empty. Wallet boots normally with zero plugins; user sees an empty Plugins page. Re-installing rebuilds the index. |
| Two wallets writing index simultaneously | `os.replace()` is atomic; one wins, the other reads stale; convergence is guaranteed on each wallet's next restart. |
| `plugin-enable.json` malformed | Logged warning, treated as `{"excluded": []}`. No plugins excluded. |

**Design rule:** a misbehaving plugin never crashes the wallet. Every plugin operation is wrapped in `try/except`, logged via `keri.help.ogler`, and converted to a "Failed" state visible on the Plugins page. This extends the pattern already used in `plugins/manager.py` (`logger.exception(...)`).

---

## Section G — Test plan

### Universal rule
All tests must be fully automated. Where automation needs visibility the UI doesn't expose, the implementation adds structured log lines specifically for test consumption — for example `logger.info("plugin.install.completed plugin_id=%s commit=%s", ...)` — rather than relying on hand-validation. Visual smoke tests use the screenshot-then-eyeball pattern from `tests/test_create_role_dialog_visual.py`, but the structural assertions must be machine-checkable.

### Unit tests (`tests/test_plugins_*`)

- `test_plugins_base.py` — `PluginCore`/`AppPlugin`/`VaultPlugin` class structure; instantiability requirements; abstractmethod coverage; `KeriFoundationPlugin` import smoke test.
- `test_plugins_installer.py` — install from local path (happy path, missing manifest, malformed TOML, missing required fields, duplicate plugin_id); uninstall; `index.json` round-trip; atomic write under simulated race (concurrent threading.Thread writers).
- `test_plugins_manager.py` — discovery walks `index.json`; entry-point fallback still works; `AppPlugin` vs `VaultPlugin` dispatch; per-wallet exclude filtering; error-path coverage (each row of section F).
- `test_plugins_kerifoundation_migration.py` — thin migration-wiring tests: `KeriFoundationPlugin` is an instance of `VaultPlugin`; instantiates without error; all previously-abstract methods are still callable. The broader regression gate is **the entire existing kerifoundation test suite** (`test_kerifoundation_*.py`) remaining green post-migration, enforced via CI.

### Visual smoke (`tests/test_plugins_page_visual.py`)

- Plugins page in each state: empty, one Loaded, one Failed (with traceback expanded), one Incompatible, one Excluded, one In-tree, mixed.
- Source dialog default state, with validation error.
- Trust dialog populated from a fixture manifest.

Pattern: render widget, structural asserts on state, `widget.grab()` PNG to `tests/_screenshots/`, eyeball or vision-LLM review. PNG outputs git-ignored.

### Integration (`tests/test_plugins_integration.py`)

- Wallet boots, installs a fixture `AppPlugin` from `tests/fixtures/plugins/echo-app/`, restarts via in-test mechanism, confirms `on_app_started` ran, declared shortcut is registered on the window, declared service `.start()` was called, declared service `.stop()` is called on close.

### Concurrency (`tests/test_plugins_concurrency.py`)

- Two `PluginInstaller` instances write to the same `index.json` concurrently (`threading.Thread`); after both complete, `index.json` is parseable and contains exactly one of the two installs intact.

### Bootstrap caveat for UI integration

Stage 1 UI integration tests **do** use the existing in-core dev-control harness (still present in this branch — it's only relocated in Stage 2) to drive the Plugins page. This is a one-time bootstrap; Stage 2 reverts the harness from core and re-implements it in the plugin repo, at which point Stage 1's integration tests are re-targeted to the plugin-flavored harness once installed.

### Manual gate before merge

Install via UI from a real local clone of a fixture plugin; install from a tiny `seriouscoderone/dummy-locksmith-plugin` test repo (to be created); restart; verify Plugins page; exclude; restart; verify; uninstall; restart; verify. CI: existing test suite remains green after the `KeriFoundationPlugin` migration.

---

## Section H — Stage 2 preview (dev-control as a plugin)

Just enough to prove Stage 1 unblocks Stage 2. Spec'd in its own cycle once Stage 1 lands.

The dev-control plugin lives in a separate repo (`github.com/seriouscoderone/locksmith-dev-control`):

```python
class DevControlPlugin(AppPlugin):
    plugin_id = "dev_control"

    def initialize(self, app):
        self._app = app

    def on_app_started(self, app, window):
        self._window = window
        self._service = DevControlService(
            window=window,
            socket_path=resolve_per_user_socket_path(),  # ← addresses review blocker #2
        )

    def get_app_shortcuts(self):
        return [(QKeySequence("Ctrl+Shift+G"), self._on_screenshot_hotkey)]
        # ← review blocker #1 solved by construction

    def get_app_services(self):
        return [self._service]
```

The PR #48 review blockers map onto Stage 2 work like this:

| PR #48 review blocker | Resolution in Stage 2 |
|---|---|
| 1. `Ctrl+Shift+G` not gated on env var | Solved by construction: plugin not installed = shortcut never declared. Env var goes away. |
| 2. `/tmp/locksmith-control.sock` is world-knowable | Plugin uses `$XDG_RUNTIME_DIR/locksmith-dev-control/<pid>.sock` with `0700` dir + `0600` socket. Declared in manifest as `net.listen` capability. |
| 3. `tree` leaks secrets | Plugin-side redaction: detect `QLineEdit.echoMode == Password`, plus configurable `objectName` regex for `password|passcode|seed|mnemonic|otp|secret`. |
| 4. `screenshot` arbitrary path | Constrained to `~/.locksmith/plugins/dev_control/screenshots/` (plugin's own user-scoped dir). Caller may pass a basename only; server sanitizes. |
| 5. Tests for env-var wiring | Becomes "tests for plugin install/load wiring" — covered in Stage 1's test plan. Plugin then adds its own internal tests. |
| 6. Tests for `toolTip` / `Type:N` / `click_list_item` | All live inside the dev-control plugin's own test suite. |

**PR #48 closing:** When Stage 1 ships and Stage 2's plugin repo exists, PR #48 is closed. The five files it added in core (`src/locksmith/dev_control.py`, `tools/devctl.py`, `tests/test_dev_control.py`, `docs/dev-control.md`, the 40-line `ui/window.py` patch) are reverted out of core and re-implemented in the plugin repo with the security/hardening fixes baked in.

---

## Section I — Scope cuts (explicit non-goals for v1)

- Plugin updates beyond reinstall. Updating a plugin = uninstall + install.
- pip / PyPI install. Plugins are git clones or local copies only.
- Plugin Python dependencies. Plugins must use only stdlib + what the wallet venv has (PySide6, keri, hio, locksmith).
- Plugin signing / trust store / verified publisher.
- Plugin sandboxing. Plugins run as in-process Python with full wallet permissions; the trust dialog warns explicitly.
- Sources beyond GitHub user/repo + local path.
- Hot-load / hot-disable. All install/uninstall/exclude/include changes require restart.
- Per-wallet plugin configuration UI. Plugins read config from `LocksmithConfig.plugin_configs[plugin_id]` (today's mechanism); no UI to edit it.
- Plugin marketplace / catalog. No discovery surface inside the wallet.
- Cross-plugin communication contract.

These remain open for follow-up cycles if needed.

---

## Appendix: file-level change list

New files:
- `src/locksmith/plugins/installer.py`
- `src/locksmith/ui/plugins/__init__.py`
- `src/locksmith/ui/plugins/page.py`
- `src/locksmith/ui/plugins/install_dialog.py`
- `src/locksmith/ui/plugins/trust_dialog.py`
- `tests/test_plugins_base.py`
- `tests/test_plugins_installer.py`
- `tests/test_plugins_manager.py`
- `tests/test_plugins_kerifoundation_migration.py`
- `tests/test_plugins_page_visual.py`
- `tests/test_plugins_integration.py`
- `tests/test_plugins_concurrency.py`
- `tests/fixtures/plugins/echo-app/` (test fixture)
- `docs/plugin-authoring.md` (replaces / extends `docs/developer-guide.rst` plugin section)

Modified files:
- `src/locksmith/plugins/base.py` (contract restructure)
- `src/locksmith/plugins/manager.py` (loader rewrite)
- `src/locksmith/plugins/kerifoundation/plugin.py` (`PluginBase, ...` → `VaultPlugin, ...`)
- `src/locksmith/ui/navigation.py` (new `Pages.PLUGINS`)
- `src/locksmith/ui/window.py` (Plugins page registration, `on_app_started` dispatch, service start/stop in `closeEvent`)
- `src/locksmith/ui/toolbar.py` (Plugins toolbar entry)
- `src/locksmith/core/apping.py` (app-level plugin teardown wiring)

No public API breakage outside the contract restructure documented in Section B.
