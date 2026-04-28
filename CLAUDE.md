# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Locksmith is a PySide6 (Qt) desktop wallet application that is the KERI Foundation's open port of the LockSmith KERI identity vault. It manages KERI identifiers (Habs/Habery), ACDC credentials, witnesses/watchers, and group multisig flows; it depends heavily on `keri==1.3.4` for protocol primitives and `hio` for the cooperative-multitasking Doer model.

## Development setup

Python `>=3.12.6` is declared in `pyproject.toml`, but the team has hit issues on 3.14 — use **Python 3.13** locally per `docs/developer-guide.rst`.

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

## Common commands

- **Run the app:** `python -m locksmith.main` (or `python ./src/locksmith/main.py`)
- **Regenerate Qt resources after asset changes:** `python ./scripts/generate_qrc.py && pyside6-rcc resources.qrc -o resources_rc.py && mv resources_rc.py ./src/locksmith/`
- **Build Sphinx docs:** `python -m pip install -r docs/requirements.txt && sphinx-build -b html docs docs/_build/html`
- **macOS sign + notarize a built `.app`:** `./scripts/sign.sh` (requires `DEVELOPER_ID_APP_CERT` and `LOCKSMITH_ENVIRONMENT` env vars; `APP_IDENTIFIER`/`KC_PROFILE` in the script are placeholders that must be set per deployment)

There is no test suite at the moment — `pyproject.toml` configures a pytest pythonpath but no `tests/` exists. The CI workflow in `.github/workflows/release.ci.yml` is a release-only pipeline, and its build step is intentionally broken (was Flet, needs to be replaced with PySide6 packaging — see TODO in the workflow).

## Architecture

### Qt + hio integration (the core trick)

KERI logic is written as `hio.base.doing.Doer` cooperative tasks, but the UI is Qt. The bridge lives in `core/tasking.py`:

- `QtTask` wraps an `hio.Doist`. A `QTimer` fires `QtTask.run()` on each tick, which calls `doist.recur()` once — never blocks. A vault's lifetime corresponds to one running `QtTask`.
- `core/signals.py` `DoerSignalBridge` (a `QObject`) lets Doers emit Qt signals for UI components. It dynamically creates `Signal(dict)` attributes on first access via `__getattr__`, so doers can emit arbitrary named events without pre-declaration. The general-purpose signal is `doer_event(doer_name, event_type, data)`.
- The asyncio event loop is `qasync.QEventLoop` set as the global asyncio loop in `main.py`, so `async def` Doer hooks (e.g. `after_identifier_authenticated`) interoperate with Qt.

When changing background work, prefer adding a Doer and routing notifications through `vault.signals` rather than touching widgets from non-Qt code.

### Application object graph

`main.py` → `LocksmithWindow` (`ui/window.py`) → `LocksmithApplication` (`core/apping.py`) → `Vault` (`core/vaulting.py`).

- `LocksmithApplication` holds the singleton `LocksmithConfig`, the current `Vault`, the `QtTask` running it, and the `PluginManager`. Vault open/close is funneled through `app.open_vault` / `app.close_vault`.
- `Vault` is a `DoDoer` that owns the keripy `Habery` (`hby`), the credential `Regery` (`rgy`), a `LocksmithBaser` LMDB store (`db/basing.py`), and the `DoerSignalBridge`. It composes the canonical KERI doers (Anchorer, Postman, Witnesser, Querier, Adjudicator/`Watchmen`, `Registrar`, `CounselingCompletionDoer`, `TurretDoer`, etc.) into `self.doers`.
- `Vault.plugin_state: dict[str, Any]` is the keyed namespace plugins use to attach per-vault runtime state. Don't put plugin-specific keys on `Vault` directly — go through `plugin_state[plugin_id]`.

### Plugin system

This is the **primary extension point** — most of what was originally healthKERI-specific has been pulled out, leaving Locksmith as a host. See `TODO.md` for the active list of work that must be implemented as a KERI Foundation plugin (witness/watcher provisioning, ESSR integration, etc.) rather than added back to core.

- Discovery: `importlib.metadata.entry_points(group="locksmith.plugins")` (`plugins/manager.py`). Register new plugins under `[project.entry-points."locksmith.plugins"]` in `pyproject.toml`, then `pip install -e .`.
- Contracts: `plugins/base.py`. `PluginBase` is required (`plugin_id`, `initialize`, `on_vault_opened/closed`, `get_menu_entry/section/pages`, `get_doers`, optional witness hooks). Mix in `AccountProviderPlugin`, `IdentifierUploadProviderPlugin`, `WitnessProviderPlugin`, `WatcherProviderPlugin`, or `CredentialProviderPlugin` for capability-specific contracts.
- Lifecycle (from `docs/developer-guide.rst`): discovered → instantiated with no args → `initialize(app)` once → `get_pages()` registered into `VaultPage`, `get_menu_entry/section()` registered into `VaultNavMenu`. On vault open, `on_vault_opened(vault)` runs and `get_doers()` is appended to `vault.doers`. On close, `on_vault_closed(vault)`.
- `LocksmithConfig.plugin_configs: dict[str, dict]` is the keyed namespace for plugin configuration. Plugins read their own block via `plugin_configs.get(plugin_id, {})`.

### Configuration

`core/configing.py` `LocksmithConfig` is a singleton dataclass (`__new__` enforces `_instance`) selected per `LOCKSMITH_ENVIRONMENT` (`development` | `staging` | `production`). Each environment has its own `*_ROOT_AID`, `*_API_AID`, `*_ROOT_OOBI`, `*_API_OOBI`, `*_UNPROTECTED_URL`, `*_PROTECTED_URL` constants — **all empty by default**, and listed in `TODO.md` as Foundation-specific values to fill in. Env vars `LOCKSMITH_ROOT_AID` / `LOCKSMITH_API_AID` / `LOCKSMITH_ROOT_OOBI` / `LOCKSMITH_API_OOBI` / `LOCKSMITH_UNPROTECTED_URL` / `LOCKSMITH_PROTECTED_URL` override per-environment defaults at runtime.

`turret/authing.py` `Authenticator.verify` returns `False` when `self.root` is empty — until the root AID is configured, signed-request verification will deny everything. This is intentional and tracked in `TODO.md`.

### UI structure

- `ui/window.py` `LocksmithWindow` owns a `QStackedWidget` (`main_stack`) holding two top-level pages: `HomePage` and `VaultPage`. Navigation between top-level pages is via `NavigationManager` (`ui/navigation.py`); `Pages` is the canonical enum of top-level page keys.
- `ui/vault/page.py` `VaultPage` owns the inner `VaultNavMenu` sidebar plus a second `QStackedWidget` (`content_stack`) of sub-pages keyed by string. Core sub-pages register at init; plugins register more via `register_page(key, widget)` from their `get_pages()`.
- `ui/toolbar.py` `LocksmithToolbar` is the global top toolbar; pages declare what it should look like via `get_toolbar_config()` and `LocksmithWindow.on_page_changed` applies it.
- `ui/vaults/drawer.py` `VaultDrawer` is the homepage-only overlay drawer. `LocksmithWindow._update_page_ui` shows/hides it based on the active top-level page, and `resizeEvent` keeps its geometry in sync even when hidden.
- Notifications use a single-instance `NotificationToast` driven by the `vault.signals.doer_event` stream; signal connection is gated on the vault page being active (`_connect_toast_signals`/`_disconnect_toast_signals`).
- `ui/toolkit/` houses reusable widgets/pages/tables shared across vault sub-pages.

### Storage

- `db/basing.py` `LocksmithBaser` is an LMDB store (one per vault, named after `hby.name`) with sub-DBs `idm` (identifier metadata), `mbx` (mailbox listener state), `pluginSettings`. It lives at `keri/rt` / `.keri/rt` under the KERI base path.
- `OTPSecrets` is a separate LMDBer at `keri/locksmith` / `.keri/locksmith`.
- `BrowserPluginSettings` are auto-created on vault open with a `settings`-namespaced Hab generated via `hby.makeHab(..., ns="settings")` if none exists.

### Turret (browser-plugin bridge)

`turret/` implements a Unix-socket-based bridge to a browser plugin (talked to via `/tmp/keripy_kli.s`). `TurretDoer` (`core/turretting.py`) wires up the Unix server (`turret/uxd/serving.py`) plus an `Exchanger` with `IdentifiersHandler`, `CredentialsHandler`, and `IPEXGrantRequestHandler` (`turret/handling.py`), gated by `ExchangerShim` so only events from the configured plugin AID are processed.

### Native libsodium loading (macOS frozen bundles)

`main.py` `load_custom_libsodium` runs only when `sys.frozen` (PyInstaller etc.) — it picks the right `libsodium/libsodium.{23.arm,26.x86_64,...}.dylib` for the current arch, symlinks it to `libsodium/libsodium.dylib`, and sets `DYLD_LIBRARY_PATH`/`LD_LIBRARY_PATH` so pysodium finds it. Don't move or rename anything in `libsodium/` without updating this loader. `entitlements.plist` includes `cs.allow-dyld-environment-variables` so the env vars survive code signing.

## Working notes

- KERI logging goes through `keri.help.ogler` — get loggers via `help.ogler.getLogger(__name__)`, not the stdlib `logging.getLogger`. The root format and level are configured once in `main.py`.
- `resources_rc.py` is a generated 7+ MB Qt resource module — never edit by hand; regenerate with the command above. It must be imported (the import in `main.py` looks unused but registers asset paths into Qt).
- `core/configing.py` placeholders, `turret/authing.py` root-AID gate, plugin entry point registration, and witness/watcher/ESSR re-implementation as a plugin are the open foundation-port items; see `TODO.md` before adding anything that looks healthKERI-shaped to `core/`.
