# Locksmith Plugin Loader — Stage 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land Stage 1 of the plugin extraction: split `PluginBase` into `PluginCore`/`AppPlugin`/`VaultPlugin`, add an in-app Plugins page with GitHub/local install, and wire app-lifecycle hooks — without changing any user-visible behavior of the existing in-tree `kerifoundation` plugin.

**Architecture:** Three new contract classes replace one. A new in-app installer clones/copies plugins into `~/.locksmith/plugins/<plugin-id>/` and tracks them in `index.json`; per-wallet exclude state lives at `<keri-base>/locksmith/plugin-enable.json`. The rewritten `PluginManager` walks the index and dispatches lifecycle hooks against the correct base class; the legacy entry-points path is preserved as a fallback so `kerifoundation` keeps loading. UI is a new top-level `Pages.PLUGINS` page on the home stack, reachable pre-vault-unlock, with a two-step install flow (source → trust/confirm).

**Tech Stack:** Python 3.14, PySide6 6.10, `tomllib` (stdlib), `git` CLI via `subprocess`, `pytest`/`pytest-qt`, `keri.help.ogler` for logging.

**Spec:** `docs/superpowers/specs/2026-05-16-locksmith-plugin-loader-design.md`
**Tracking:** [keri-foundation/locksmith#50](https://github.com/keri-foundation/locksmith/issues/50)

---

## Conventions every task assumes

- All `pytest` runs use `QT_QPA_PLATFORM=offscreen` (already exported in `tests/conftest.py`, but pass it explicitly to avoid surprises).
- The active venv is `/Users/seriouscoderone/code/locksmith/.venv/` (Python 3.14). Use `.venv/bin/python -m pytest …`. **Don't** create a new venv inside the worktree.
- Logging goes through `from keri import help; logger = help.ogler.getLogger(__name__)`. **Do not** use stdlib `logging.getLogger`.
- Every commit message follows the repo style: `<type>(<scope>): <summary>` (e.g., `feat(plugins): add PluginCore + AppPlugin contract`). Add the `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` trailer.
- The worktree's branch is `pr/dev-control-harness`. Stage 1 commits land on this branch — same branch as PR #48, which stays open as the parking spot for Stage 2's revert.
- Tests must be fully automated. When UI state isn't otherwise observable, add `logger.info("plugin.<op>.<event> key=value …")` lines and assert against captured log output via `caplog` (pytest fixture) or by reading the wallet's logfile. **Do not** rely on visual inspection in CI.

---

## File structure

```
src/locksmith/
    plugins/
        base.py                    [REWRITE: PluginCore + AppPlugin + VaultPlugin]
        manager.py                 [REWRITE: index.json discovery + type-aware dispatch]
        installer.py               [NEW: clone, copy, atomic index updates, uninstall]
        manifest.py                [NEW: parse + validate locksmith-plugin.toml]
        storage.py                 [NEW: paths + atomic-JSON helpers]
        kerifoundation/
            plugin.py              [MODIFY: PluginBase → VaultPlugin in base classes]
    ui/
        navigation.py              [MODIFY: add Pages.PLUGINS]
        toolbar.py                 [MODIFY: add plugins_clicked signal + button]
        window.py                  [MODIFY: register Plugins page, wire app-lifecycle dispatch]
        plugins/
            __init__.py            [NEW]
            page.py                [NEW: PluginsPage]
            install_dialog.py      [NEW: InstallSourceDialog]
            trust_dialog.py        [NEW: PluginTrustDialog]
    core/
        apping.py                  [MODIFY: hold app-plugin set, expose accessors]

tests/
    fixtures/plugins/echo-app/     [NEW: minimal AppPlugin fixture]
        locksmith-plugin.toml
        echo_app/
            __init__.py
            plugin.py
    fixtures/plugins/malformed-toml/locksmith-plugin.toml         [NEW]
    fixtures/plugins/missing-required-fields/locksmith-plugin.toml [NEW]
    test_plugins_base.py           [NEW]
    test_plugins_manifest.py       [NEW]
    test_plugins_storage.py        [NEW]
    test_plugins_installer.py      [NEW]
    test_plugins_manager.py        [NEW]
    test_plugins_kerifoundation_migration.py [NEW]
    test_plugins_page_visual.py    [NEW]
    test_plugins_integration.py    [NEW]
    test_plugins_concurrency.py    [NEW]

docs/
    plugin-authoring.md            [NEW]
```

---

## Task 1: Project scaffolding + fixture plugin

**Why first:** Subsequent tasks need a real on-disk fixture plugin to test against. Creating the dir structure and the fixture once avoids repeating the boilerplate.

**Files:**
- Create: `tests/fixtures/plugins/echo-app/locksmith-plugin.toml`
- Create: `tests/fixtures/plugins/echo-app/echo_app/__init__.py`
- Create: `tests/fixtures/plugins/echo-app/echo_app/plugin.py`
- Create: `tests/fixtures/plugins/malformed-toml/locksmith-plugin.toml`
- Create: `tests/fixtures/plugins/missing-required-fields/locksmith-plugin.toml`

- [ ] **Step 1: Create the echo-app fixture manifest**

`tests/fixtures/plugins/echo-app/locksmith-plugin.toml`:

```toml
plugin_id = "echo_app"
entry_point = "echo_app.plugin:EchoAppPlugin"
manifest_version = 1
name = "Echo App"
version = "0.1.0"
description = "Test fixture: a minimal AppPlugin used by Stage 1 tests."
author = "Locksmith Test Suite"
requires_locksmith = ">=0.0.1"
capabilities = ["app.service"]

[capabilities_detail]
"app.service" = "Logs lifecycle events for test assertions."
```

- [ ] **Step 2: Create the fixture's plugin module**

`tests/fixtures/plugins/echo-app/echo_app/__init__.py`: empty file.

`tests/fixtures/plugins/echo-app/echo_app/plugin.py`:

```python
from __future__ import annotations

from keri import help

from locksmith.plugins.base import AppPlugin

logger = help.ogler.getLogger(__name__)


class EchoService:
    """Trivial AppService that logs start/stop for test assertions."""

    def __init__(self, plugin_id: str):
        self._plugin_id = plugin_id

    def start(self) -> None:
        logger.info("plugin.service.started plugin_id=%s", self._plugin_id)

    def stop(self) -> None:
        logger.info("plugin.service.stopped plugin_id=%s", self._plugin_id)


class EchoAppPlugin(AppPlugin):
    """Minimal AppPlugin used by the Stage 1 integration tests."""

    @property
    def plugin_id(self) -> str:
        return "echo_app"

    def initialize(self, app) -> None:
        logger.info("plugin.initialize plugin_id=%s", self.plugin_id)

    def on_app_started(self, app, window) -> None:
        logger.info("plugin.on_app_started plugin_id=%s", self.plugin_id)

    def on_app_stopping(self, app) -> None:
        logger.info("plugin.on_app_stopping plugin_id=%s", self.plugin_id)

    def get_app_services(self):
        return [EchoService(self.plugin_id)]
```

- [ ] **Step 3: Create the malformed-TOML fixture**

`tests/fixtures/plugins/malformed-toml/locksmith-plugin.toml`:

```
this is = not valid TOML = at all
[unclosed_section
```

- [ ] **Step 4: Create the missing-required-fields fixture**

`tests/fixtures/plugins/missing-required-fields/locksmith-plugin.toml`:

```toml
# plugin_id and entry_point are intentionally absent.
manifest_version = 1
name = "Incomplete"
version = "0.0.1"
description = "Missing required fields on purpose."
```

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/plugins/
git commit -m "$(cat <<'EOF'
test(plugins): add Stage 1 fixture plugins

echo-app: minimal AppPlugin used by manager and integration tests.
malformed-toml: covers TOML parser error paths.
missing-required-fields: covers manifest validation error paths.

Refs: #50
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Plugin contract restructure (`PluginCore` / `AppPlugin` / `VaultPlugin`)

**Why now:** Every later task depends on these classes. We rewrite `base.py` whole — `PluginBase` becomes a deprecated alias for backward import compatibility during the same commit.

**Files:**
- Modify: `src/locksmith/plugins/base.py` (full rewrite)
- Create: `tests/test_plugins_base.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_plugins_base.py`:

```python
"""Contract restructure tests for PluginCore / AppPlugin / VaultPlugin."""
from __future__ import annotations

import pytest

from locksmith.plugins import base as plugins_base
from locksmith.plugins.base import (
    AppPlugin,
    PluginCore,
    VaultPlugin,
)


def test_plugin_core_requires_plugin_id_and_initialize():
    # Cannot instantiate a PluginCore subclass that doesn't implement both abstractmethods.
    class Incomplete(PluginCore):
        pass

    with pytest.raises(TypeError):
        Incomplete()


def test_app_plugin_minimal_subclass_instantiates():
    class MinApp(AppPlugin):
        @property
        def plugin_id(self):
            return "min_app"

        def initialize(self, app):
            pass

    p = MinApp()
    assert p.plugin_id == "min_app"
    assert p.get_app_shortcuts() == []
    assert p.get_app_services() == []
    # Default lifecycle hooks are no-ops.
    p.on_app_started(app=None, window=None)
    p.on_app_stopping(app=None)


def test_vault_plugin_subclass_must_implement_vault_hooks():
    class IncompleteVault(VaultPlugin):
        @property
        def plugin_id(self):
            return "incomplete_vault"

        def initialize(self, app):
            pass
        # Intentionally missing the vault hooks.

    with pytest.raises(TypeError):
        IncompleteVault()


def test_app_and_vault_can_be_combined():
    class Hybrid(AppPlugin, VaultPlugin):
        @property
        def plugin_id(self):
            return "hybrid"

        def initialize(self, app): pass
        def on_vault_opened(self, vault): pass
        def on_vault_closed(self, vault, *, clear=False): pass
        def get_menu_entry(self): return None
        def get_menu_section(self): return []
        def get_pages(self): return {}

    h = Hybrid()
    # isinstance checks drive the PluginManager dispatch later.
    assert isinstance(h, AppPlugin)
    assert isinstance(h, VaultPlugin)


def test_plugin_base_alias_still_resolves():
    # Backward-compat alias so legacy imports don't break before Task 3 migrates them.
    assert plugins_base.PluginBase is plugins_base.VaultPlugin
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_plugins_base.py -v
```

Expected: All tests **FAIL** — `AppPlugin` / `PluginCore` not importable yet, or existing `PluginBase` doesn't satisfy the new shape.

- [ ] **Step 3: Rewrite `src/locksmith/plugins/base.py`**

Full new content (replaces the existing file):

```python
# -*- encoding: utf-8 -*-
"""
locksmith.plugins.base module

Plugin contracts for Locksmith extensions.

Three base classes:
- ``PluginCore``: shared minimum (plugin_id + initialize).
- ``AppPlugin``: app/window lifecycle hooks (run pre-vault-unlock).
- ``VaultPlugin``: vault lifecycle hooks (the original surface).

A plugin can inherit one, the other, or both. PluginManager dispatches
hooks based on isinstance() checks against AppPlugin / VaultPlugin.

``PluginBase`` is kept as a deprecated alias for VaultPlugin so existing
in-tree imports continue to resolve while Task 3 migrates them. Remove
the alias once kerifoundation has been migrated.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from hio.base import doing
    from PySide6.QtGui import QKeySequence
    from PySide6.QtWidgets import QWidget
    from locksmith.ui.vault.menu import MenuButton


class PluginCore(ABC):
    """Shared minimum every plugin must implement."""

    @property
    @abstractmethod
    def plugin_id(self) -> str:
        """Unique namespace key for this plugin (e.g. 'your_plugin')."""

    @abstractmethod
    def initialize(self, app: Any) -> None:
        """Called once at startup after plugin discovery, before any hooks fire."""


class AppPlugin(PluginCore):
    """Plugin that hooks into app/window lifecycle.

    Inherit this for plugins that need to do work before any vault is
    opened — e.g., install global shortcuts, run a background service
    that owns a window-attached resource. No abstractmethods beyond the
    PluginCore minimum; all hooks default to no-ops.
    """

    def on_app_started(self, app: Any, window: Any) -> None:
        """Called once after LocksmithWindow.__init__ completes."""

    def on_app_stopping(self, app: Any) -> None:
        """Called once during LocksmithWindow.closeEvent, before services stop."""

    def get_app_shortcuts(self) -> list[tuple["QKeySequence", Callable[[], None]]]:
        """Global keyboard shortcuts to install on the main window.

        Each tuple is (sequence, callback). PluginManager installs them
        with Qt.ApplicationShortcut context.
        """
        return []

    def get_app_services(self) -> list[Any]:
        """Long-lived services owned by the plugin.

        Each service is duck-typed: must have ``start() -> None`` and
        ``stop() -> None``. PluginManager calls start() in discovery order
        after on_app_started, and stop() in reverse order before
        on_app_stopping.
        """
        return []


class VaultPlugin(PluginCore):
    """Plugin that hooks into vault lifecycle (the original surface)."""

    @abstractmethod
    def on_vault_opened(self, vault: Any) -> None:
        """Called when a vault is opened. Start doers, open plugin DB, etc."""

    @abstractmethod
    def on_vault_closed(self, vault: Any, *, clear: bool = False) -> None:
        """Called when a vault is closed. Cleanup, close DB, etc.

        When ``clear`` is True, plugin-local durable state tied to the
        vault should also be deleted from disk.
        """

    @abstractmethod
    def get_menu_entry(self) -> "MenuButton":
        """Entry button shown in the main vault sidebar."""

    @abstractmethod
    def get_menu_section(self) -> list["QWidget"]:
        """Submenu items shown when the plugin menu is pushed."""

    @abstractmethod
    def get_pages(self) -> dict[str, "QWidget"]:
        """page_key -> widget mappings to register in VaultPage."""

    # Optional hooks — defaults are no-ops.

    def get_doers(self) -> list["doing.Doer"]:
        return []

    def prepare_vault_deletion(self, vault: Any) -> None:
        pass

    def get_witness_batches(self, vault: Any, hab_pre: str) -> Any | None:
        return None

    def get_witness_state(self, vault: Any, wit_eid: str) -> Any | None:
        return None

    def update_witness_state(self, vault: Any, wit_eid: str) -> None:
        pass

    def update_witness_state_after_auth(self, vault: Any, wit_eid: str) -> None:
        pass

    async def after_identifier_authenticated(self, vault: Any, hab: Any) -> None:
        pass


# Backward-compat alias. Remove after Task 3 (kerifoundation migration).
PluginBase = VaultPlugin


# Existing capability mixins — keep their shape; they now apply only to VaultPlugin.

class AccountProviderPlugin(ABC):
    """Mixin for plugins with a setup/account creation flow."""

    @abstractmethod
    def is_setup_complete(self, vault: Any) -> bool: ...

    @abstractmethod
    def get_setup_page(self, vault: Any) -> tuple[str, bool]: ...

    def on_account_created(self, vault: Any, account: Any) -> None:
        pass


class IdentifierUploadProviderPlugin(ABC):
    """Contract for plugins that upload/sync local identifiers to a platform."""


class WitnessProviderPlugin(ABC):
    """Contract for plugins that provision witness services."""


class WatcherProviderPlugin(ABC):
    """Contract for plugins that provision watcher services."""


class CredentialProviderPlugin(ABC):
    """Contract for plugins that manage published credentials."""
```

- [ ] **Step 4: Run the new tests to verify they pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_plugins_base.py -v
```

Expected: All 5 tests **PASS**.

- [ ] **Step 5: Run the full existing test suite as a regression gate**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -x --ignore=tests/fixtures
```

Expected: No regressions. Existing tests that import `PluginBase` still resolve via the alias.

- [ ] **Step 6: Commit**

```bash
git add src/locksmith/plugins/base.py tests/test_plugins_base.py
git commit -m "$(cat <<'EOF'
feat(plugins): split PluginBase into PluginCore + AppPlugin + VaultPlugin

PluginCore holds the shared minimum (plugin_id, initialize). AppPlugin
adds app/window lifecycle hooks for plugins that need to run before any
vault is opened (shortcuts, long-lived services). VaultPlugin carries
the existing vault/menu/page contract, with abstractmethods unchanged so
existing implementations don't drift.

PluginBase is preserved as a VaultPlugin alias so kerifoundation and any
external callers keep importing. Removed in the next commit after the
in-tree migration.

Refs: #50
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Migrate `KeriFoundationPlugin` to `VaultPlugin`

**Why now:** Removes the only consumer of the `PluginBase` alias so we can delete the alias in this same commit, keeping the contract tidy.

**Files:**
- Modify: `src/locksmith/plugins/kerifoundation/plugin.py:18, 45`
- Modify: `src/locksmith/plugins/base.py` (delete `PluginBase = VaultPlugin` alias)
- Create: `tests/test_plugins_kerifoundation_migration.py`

- [ ] **Step 1: Write the migration tests**

`tests/test_plugins_kerifoundation_migration.py`:

```python
"""Thin wiring tests confirming kerifoundation migrated to VaultPlugin cleanly.

The broader regression gate is the full kerifoundation test suite
(`test_kerifoundation_*.py`), which must remain green post-migration.
"""
from __future__ import annotations

from locksmith.plugins.base import VaultPlugin
from locksmith.plugins.kerifoundation.plugin import KeriFoundationPlugin


def test_kerifoundation_is_vault_plugin():
    plugin = KeriFoundationPlugin()
    assert isinstance(plugin, VaultPlugin)


def test_kerifoundation_implements_all_vault_abstractmethods():
    plugin = KeriFoundationPlugin()
    # If any abstractmethod was missed, instantiation would have raised TypeError.
    for name in (
        "on_vault_opened",
        "on_vault_closed",
        "get_menu_entry",
        "get_menu_section",
        "get_pages",
    ):
        assert callable(getattr(plugin, name)), f"missing {name}"


def test_kerifoundation_plugin_id_unchanged():
    assert KeriFoundationPlugin().plugin_id == "kerifoundation"
```

- [ ] **Step 2: Run the tests to verify they fail (or pass via alias)**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_plugins_kerifoundation_migration.py -v
```

Expected: Tests PASS via the `PluginBase = VaultPlugin` alias from Task 2. They will keep passing after the base-class change too — the test is checking the *target state*, not the intermediate state.

- [ ] **Step 3: Update `KeriFoundationPlugin`'s base classes**

Edit `src/locksmith/plugins/kerifoundation/plugin.py`.

At line 18, change the import:
```python
# Before
from locksmith.plugins.base import AccountProviderPlugin, PluginBase, WitnessProviderPlugin

# After
from locksmith.plugins.base import AccountProviderPlugin, VaultPlugin, WitnessProviderPlugin
```

At line 45, change the class declaration:
```python
# Before
class KeriFoundationPlugin(PluginBase, WitnessProviderPlugin, AccountProviderPlugin):

# After
class KeriFoundationPlugin(VaultPlugin, WitnessProviderPlugin, AccountProviderPlugin):
```

No method body changes. The docstring at line 46-51 stays as-is.

- [ ] **Step 4: Delete the `PluginBase` alias**

Edit `src/locksmith/plugins/base.py`. Remove the two-line block:
```python
# Backward-compat alias. Remove after Task 3 (kerifoundation migration).
PluginBase = VaultPlugin
```

- [ ] **Step 5: Search for any other `PluginBase` imports and migrate**

```bash
grep -rn "from locksmith.plugins.base import.*PluginBase\|plugins.base.PluginBase" src tests
```

Expected: zero hits after Step 3. If any remain, change them to `VaultPlugin` in the same edit pattern.

- [ ] **Step 6: Run the migration tests + full kerifoundation suite**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_plugins_kerifoundation_migration.py tests/test_kerifoundation_account_gating.py tests/test_kerifoundation_onboarding_service.py tests/test_kerifoundation_onboarding_ui.py tests/test_kerifoundation_vault_deletion.py tests/test_kerifoundation_witnesses.py -v
```

Expected: All PASS. Any failure here = behavior changed and migration is wrong; fix before continuing.

- [ ] **Step 7: Run the full test suite**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -x --ignore=tests/fixtures
```

Expected: No regressions.

- [ ] **Step 8: Commit**

```bash
git add src/locksmith/plugins/base.py src/locksmith/plugins/kerifoundation/plugin.py tests/test_plugins_kerifoundation_migration.py
git commit -m "$(cat <<'EOF'
refactor(plugins): migrate KeriFoundationPlugin to VaultPlugin

Drops the PluginBase backward-compat alias. KeriFoundationPlugin now
inherits VaultPlugin directly; no method signatures changed, all
existing kerifoundation tests stay green.

Refs: #50
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Manifest parser (`locksmith-plugin.toml`)

**Why now:** The installer (Task 6) and manager (Task 7) both consume parsed manifests. Land the parser first as a pure-function module — no I/O, no Qt — so it's trivially testable.

**Files:**
- Create: `src/locksmith/plugins/manifest.py`
- Create: `tests/test_plugins_manifest.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_plugins_manifest.py`:

```python
"""Tests for locksmith-plugin.toml parsing + validation."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from locksmith.plugins.manifest import (
    Manifest,
    ManifestError,
    parse_manifest,
    parse_manifest_text,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "plugins"


def test_parse_echo_app_fixture():
    m = parse_manifest(FIXTURE_ROOT / "echo-app" / "locksmith-plugin.toml")
    assert m.plugin_id == "echo_app"
    assert m.entry_point == "echo_app.plugin:EchoAppPlugin"
    assert m.manifest_version == 1
    assert m.name == "Echo App"
    assert m.version == "0.1.0"
    assert m.requires_locksmith == ">=0.0.1"
    assert m.capabilities == ["app.service"]
    assert m.capabilities_detail == {
        "app.service": "Logs lifecycle events for test assertions.",
    }


def test_parse_malformed_toml_raises():
    with pytest.raises(ManifestError) as exc:
        parse_manifest(FIXTURE_ROOT / "malformed-toml" / "locksmith-plugin.toml")
    assert "invalid TOML" in str(exc.value).lower() or "parse" in str(exc.value).lower()


def test_parse_missing_required_fields_raises():
    with pytest.raises(ManifestError) as exc:
        parse_manifest(FIXTURE_ROOT / "missing-required-fields" / "locksmith-plugin.toml")
    msg = str(exc.value)
    assert "plugin_id" in msg
    assert "entry_point" in msg


def test_entry_point_format_validated():
    text = textwrap.dedent("""
        plugin_id = "x"
        entry_point = "no_colon_here"
        manifest_version = 1
        name = "x"
        version = "0.1.0"
        description = "x"
    """).strip()
    with pytest.raises(ManifestError) as exc:
        parse_manifest_text(text, source="<test>")
    assert "entry_point" in str(exc.value)
    assert "module:Class" in str(exc.value)


def test_plugin_id_format_validated():
    text = textwrap.dedent("""
        plugin_id = "has spaces"
        entry_point = "mod:Cls"
        manifest_version = 1
        name = "x"
        version = "0.1.0"
        description = "x"
    """).strip()
    with pytest.raises(ManifestError) as exc:
        parse_manifest_text(text, source="<test>")
    assert "plugin_id" in str(exc.value)


def test_manifest_to_dict_roundtrip():
    m = parse_manifest(FIXTURE_ROOT / "echo-app" / "locksmith-plugin.toml")
    d = m.to_dict()
    assert d["plugin_id"] == "echo_app"
    assert d["capabilities"] == ["app.service"]
    # to_dict is the snapshot stored in index.json — must be json-serializable.
    import json
    json.dumps(d)


def test_unknown_capabilities_preserved_verbatim():
    text = textwrap.dedent("""
        plugin_id = "x"
        entry_point = "mod:Cls"
        manifest_version = 1
        name = "x"
        version = "0.1.0"
        description = "x"
        capabilities = ["app.shortcut", "made.up.capability"]
    """).strip()
    m = parse_manifest_text(text, source="<test>")
    assert "made.up.capability" in m.capabilities
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_plugins_manifest.py -v
```

Expected: All fail — module doesn't exist.

- [ ] **Step 3: Implement `src/locksmith/plugins/manifest.py`**

```python
# -*- encoding: utf-8 -*-
"""
locksmith.plugins.manifest module

Parser + validator for ``locksmith-plugin.toml``.

Pure-function module. No I/O beyond reading the manifest path; no Qt;
no PluginManager dependency. Returns a Manifest dataclass that captures
exactly the fields the spec defines. Unknown keys are preserved in
``extra`` so future fields don't trip on this parser.
"""
from __future__ import annotations

import re
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


PLUGIN_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
ENTRY_POINT_RE = re.compile(r"^[A-Za-z_][\w.]*:[A-Za-z_]\w*$")


class ManifestError(ValueError):
    """Raised when a manifest is missing, malformed, or fails validation."""


@dataclass(frozen=True)
class Manifest:
    plugin_id: str
    entry_point: str
    manifest_version: int
    name: str
    version: str
    description: str
    author: str = ""
    homepage: str = ""
    license: str = ""
    requires_locksmith: str = ""
    capabilities: list[str] = field(default_factory=list)
    capabilities_detail: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable snapshot. Stored in index.json at install time."""
        return asdict(self)


REQUIRED_FIELDS = ("plugin_id", "entry_point", "manifest_version")
TRUST_DIALOG_FIELDS = ("name", "version", "description")
KNOWN_FIELDS = {
    *REQUIRED_FIELDS,
    *TRUST_DIALOG_FIELDS,
    "author", "homepage", "license", "requires_locksmith",
    "capabilities", "capabilities_detail",
}


def parse_manifest(path: Path | str) -> Manifest:
    """Read and parse a manifest file. Raises ManifestError on failure."""
    path = Path(path)
    if not path.exists():
        raise ManifestError(f"manifest file not found: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ManifestError(f"could not read manifest {path}: {e}") from e
    return parse_manifest_text(text, source=str(path))


def parse_manifest_text(text: str, *, source: str) -> Manifest:
    """Parse manifest text. `source` is only used for error messages."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ManifestError(f"invalid TOML in {source}: {e}") from e

    missing = [f for f in REQUIRED_FIELDS if f not in data]
    if missing:
        raise ManifestError(
            f"manifest at {source} is missing required field(s): "
            f"{', '.join(missing)}"
        )

    missing_trust = [f for f in TRUST_DIALOG_FIELDS if not data.get(f)]
    if missing_trust:
        raise ManifestError(
            f"manifest at {source} is missing required trust-dialog field(s): "
            f"{', '.join(missing_trust)}"
        )

    if not isinstance(data["plugin_id"], str) or not PLUGIN_ID_RE.match(data["plugin_id"]):
        raise ManifestError(
            f"manifest at {source}: plugin_id must match {PLUGIN_ID_RE.pattern!r}, "
            f"got {data['plugin_id']!r}"
        )

    if not isinstance(data["entry_point"], str) or not ENTRY_POINT_RE.match(data["entry_point"]):
        raise ManifestError(
            f"manifest at {source}: entry_point must be 'module:Class', "
            f"got {data['entry_point']!r}"
        )

    if data["manifest_version"] != 1:
        raise ManifestError(
            f"manifest at {source}: unsupported manifest_version "
            f"{data['manifest_version']} (this wallet supports 1)"
        )

    extra = {k: v for k, v in data.items() if k not in KNOWN_FIELDS}
    return Manifest(
        plugin_id=data["plugin_id"],
        entry_point=data["entry_point"],
        manifest_version=int(data["manifest_version"]),
        name=data["name"],
        version=data["version"],
        description=data["description"],
        author=str(data.get("author", "")),
        homepage=str(data.get("homepage", "")),
        license=str(data.get("license", "")),
        requires_locksmith=str(data.get("requires_locksmith", "")),
        capabilities=list(data.get("capabilities", []) or []),
        capabilities_detail=dict(data.get("capabilities_detail", {}) or {}),
        extra=extra,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_plugins_manifest.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/manifest.py tests/test_plugins_manifest.py
git commit -m "$(cat <<'EOF'
feat(plugins): add locksmith-plugin.toml parser and validator

Pure-function module: reads TOML, validates the required-for-load and
required-for-trust-dialog fields, normalizes capabilities, captures
unknown keys in `extra` so future schema additions don't break old
wallets parsing new manifests.

Refs: #50
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Storage helpers (`storage.py`) — paths + atomic JSON

**Why now:** The installer and manager both read/write `index.json` and `plugin-enable.json`. Centralizing the path resolution + atomic-write primitive keeps both correct and gives us one place to test the race-safety.

**Files:**
- Create: `src/locksmith/plugins/storage.py`
- Create: `tests/test_plugins_storage.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_plugins_storage.py`:

```python
"""Tests for the plugin storage layer (paths + atomic JSON writes)."""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from locksmith.plugins import storage


def test_plugin_root_uses_tmp_path(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    assert storage.plugin_root() == tmp_path / ".locksmith" / "plugins"


def test_index_path_under_plugin_root(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    assert storage.index_path() == tmp_path / ".locksmith" / "plugins" / "index.json"


def test_plugin_clone_dir_under_plugin_root(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    assert storage.plugin_clone_dir("dev_control") == (
        tmp_path / ".locksmith" / "plugins" / "dev_control"
    )


def test_read_index_when_missing_returns_default(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    assert storage.read_index() == {"format": 1, "plugins": []}


def test_write_index_then_read_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    payload = {
        "format": 1,
        "plugins": [{"plugin_id": "x", "source": {"type": "local", "path": "/p"}}],
    }
    storage.write_index(payload)
    assert storage.read_index() == payload


def test_write_index_is_atomic(tmp_path, monkeypatch):
    """Two threads racing to write the index produce a valid file, not corruption."""
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    storage.write_index({"format": 1, "plugins": []})

    def writer(name):
        for _ in range(50):
            storage.write_index(
                {"format": 1, "plugins": [{"plugin_id": name}]}
            )

    threads = [threading.Thread(target=writer, args=(n,)) for n in ("a", "b", "c")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    final = storage.read_index()
    assert final["format"] == 1
    assert isinstance(final["plugins"], list)
    # Whichever writer won the last race must have produced one of these:
    assert final["plugins"][0]["plugin_id"] in ("a", "b", "c")


def test_read_index_with_malformed_json_returns_default_and_logs(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    storage.plugin_root().mkdir(parents=True, exist_ok=True)
    storage.index_path().write_text("{ not json", encoding="utf-8")
    with caplog.at_level("WARNING"):
        result = storage.read_index()
    assert result == {"format": 1, "plugins": []}


def test_read_enable_list_when_missing_returns_default(tmp_path):
    keri_base = tmp_path / "keri-base"
    assert storage.read_enable_list(keri_base) == {"format": 1, "excluded": []}


def test_write_then_read_enable_list(tmp_path):
    keri_base = tmp_path / "keri-base"
    storage.write_enable_list(keri_base, {"format": 1, "excluded": ["dev_control"]})
    assert storage.read_enable_list(keri_base)["excluded"] == ["dev_control"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_plugins_storage.py -v
```

Expected: All fail — `storage` module doesn't exist.

- [ ] **Step 3: Implement `src/locksmith/plugins/storage.py`**

```python
# -*- encoding: utf-8 -*-
"""
locksmith.plugins.storage module

Path resolution + atomic JSON read/write for plugin install state.

Two files are managed:
- ``~/.locksmith/plugins/index.json``: user-scoped, shared across all
  Locksmith wallet instances. Records what's installed.
- ``<keri-base>/locksmith/plugin-enable.json``: per-wallet exclude list.

Both writes use temp-file + os.replace() for atomicity, so concurrent
wallet instances installing simultaneously can never see a half-written
file. Last writer wins; convergence on next restart.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from keri import help

logger = help.ogler.getLogger(__name__)


def _user_home() -> Path:
    """Indirection point so tests can monkeypatch the home dir."""
    return Path.home()


def plugin_root() -> Path:
    """Directory holding all user-scoped plugin clones + the registry."""
    return _user_home() / ".locksmith" / "plugins"


def index_path() -> Path:
    """Path to the shared installed-plugin registry."""
    return plugin_root() / "index.json"


def plugin_clone_dir(plugin_id: str) -> Path:
    """Where a plugin's repo clone lives on disk."""
    return plugin_root() / plugin_id


def enable_list_path(keri_base: Path) -> Path:
    """Per-wallet plugin-enable.json under the given KERI base path."""
    return Path(keri_base) / "locksmith" / "plugin-enable.json"


def _default_index() -> dict[str, Any]:
    return {"format": 1, "plugins": []}


def _default_enable_list() -> dict[str, Any]:
    return {"format": 1, "excluded": []}


def read_index() -> dict[str, Any]:
    """Read the shared install registry. Returns default if missing or malformed."""
    path = index_path()
    if not path.exists():
        return _default_index()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("plugin.index.read_failed path=%s error=%s", path, e)
        return _default_index()


def write_index(payload: dict[str, Any]) -> None:
    """Atomically replace the shared install registry."""
    _atomic_write_json(index_path(), payload)
    logger.info("plugin.index.written path=%s plugins=%d", index_path(), len(payload.get("plugins", [])))


def read_enable_list(keri_base: Path) -> dict[str, Any]:
    """Read this wallet's exclude list. Returns default if missing or malformed."""
    path = enable_list_path(keri_base)
    if not path.exists():
        return _default_enable_list()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("plugin.enable.read_failed path=%s error=%s", path, e)
        return _default_enable_list()


def write_enable_list(keri_base: Path, payload: dict[str, Any]) -> None:
    """Atomically replace this wallet's exclude list."""
    path = enable_list_path(keri_base)
    _atomic_write_json(path, payload)
    logger.info("plugin.enable.written path=%s excluded=%s", path, payload.get("excluded", []))


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # NamedTemporaryFile in the same directory ensures os.replace stays atomic
    # (cross-filesystem rename is not atomic on Linux).
    fd, tmp = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_plugins_storage.py -v
```

Expected: All 9 tests PASS. The race test (`test_write_index_is_atomic`) runs three threads each writing 50 times; the final file is always parseable JSON.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/storage.py tests/test_plugins_storage.py
git commit -m "$(cat <<'EOF'
feat(plugins): add storage layer (paths + atomic JSON helpers)

plugin_root(), index_path(), plugin_clone_dir(), enable_list_path()
centralize path resolution. read/write helpers for index.json (shared,
user-scoped) and plugin-enable.json (per-wallet). Writes use
tempfile + os.replace() so concurrent wallet instances can't corrupt
the registry. Malformed JSON is treated as the empty default with a
warning log line for the Plugins page.

Refs: #50
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Installer (`installer.py`) — clone, copy, install, uninstall

**Why now:** Manifest + storage are in place. The installer is the only non-trivial I/O surface left before the manager rewrite.

**Files:**
- Create: `src/locksmith/plugins/installer.py`
- Create: `tests/test_plugins_installer.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_plugins_installer.py`:

```python
"""Tests for the plugin installer (local + git sources, install, uninstall)."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from locksmith.plugins import storage
from locksmith.plugins.installer import (
    InstallError,
    PluginInstaller,
    SourceDescriptor,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "plugins"


@pytest.fixture
def installer(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    return PluginInstaller()


def test_install_from_local_path_happy(installer, tmp_path):
    src = SourceDescriptor(type="local", path=str(FIXTURE_ROOT / "echo-app"))
    record = installer.install(src)
    assert record["plugin_id"] == "echo_app"
    assert record["source"]["type"] == "local"
    # Clone landed at the expected path.
    clone = storage.plugin_clone_dir("echo_app")
    assert (clone / "locksmith-plugin.toml").exists()
    assert (clone / "echo_app" / "plugin.py").exists()
    # Index updated.
    idx = storage.read_index()
    assert len(idx["plugins"]) == 1
    assert idx["plugins"][0]["plugin_id"] == "echo_app"
    # Snapshot includes manifest fields.
    snap = idx["plugins"][0]["manifest_snapshot"]
    assert snap["plugin_id"] == "echo_app"
    assert snap["entry_point"] == "echo_app.plugin:EchoAppPlugin"


def test_install_rejects_malformed_manifest(installer):
    src = SourceDescriptor(type="local", path=str(FIXTURE_ROOT / "malformed-toml"))
    with pytest.raises(InstallError) as exc:
        installer.install(src)
    assert "invalid TOML" in str(exc.value).lower() or "parse" in str(exc.value).lower()
    # No clone left behind, no index entry.
    assert storage.read_index()["plugins"] == []


def test_install_rejects_missing_required_fields(installer):
    src = SourceDescriptor(type="local", path=str(FIXTURE_ROOT / "missing-required-fields"))
    with pytest.raises(InstallError):
        installer.install(src)
    assert storage.read_index()["plugins"] == []


def test_install_rejects_local_path_without_manifest(installer, tmp_path):
    bad = tmp_path / "no-manifest"
    bad.mkdir()
    with pytest.raises(InstallError) as exc:
        installer.install(SourceDescriptor(type="local", path=str(bad)))
    assert "locksmith-plugin.toml" in str(exc.value)


def test_install_rejects_duplicate_plugin_id(installer):
    src = SourceDescriptor(type="local", path=str(FIXTURE_ROOT / "echo-app"))
    installer.install(src)
    with pytest.raises(InstallError) as exc:
        installer.install(src)
    assert "already installed" in str(exc.value).lower()


def test_uninstall_removes_clone_and_index_entry(installer):
    src = SourceDescriptor(type="local", path=str(FIXTURE_ROOT / "echo-app"))
    installer.install(src)
    installer.uninstall("echo_app")
    assert not storage.plugin_clone_dir("echo_app").exists()
    assert storage.read_index()["plugins"] == []


def test_uninstall_unknown_plugin_raises(installer):
    with pytest.raises(InstallError) as exc:
        installer.uninstall("nope")
    assert "not installed" in str(exc.value).lower()


def test_install_github_invokes_git_clone(installer, monkeypatch, tmp_path):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        # Simulate a successful clone by copying the fixture into the dest.
        dest = Path(cmd[-1])
        shutil.copytree(FIXTURE_ROOT / "echo-app", dest)
        # Simulate `git rev-parse HEAD` later by writing a fake .git/HEAD ref.
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    def fake_check_output(cmd, **kwargs):
        # `git rev-parse HEAD`
        return b"a3f9c1dabe7c0f5e8b7a2b9d0c4e1f2a3b4c5d6e\n"

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(subprocess, "check_output", fake_check_output)

    src = SourceDescriptor(type="github", user_repo="acme/echo", ref=None)
    record = installer.install(src)

    assert captured["cmd"][:3] == ["git", "clone", "--depth"]
    assert "https://github.com/acme/echo.git" in captured["cmd"]
    assert record["commit"].startswith("a3f9c1d")
    assert record["source"] == {"type": "github", "user_repo": "acme/echo", "ref": None}


def test_install_github_clone_failure_surfaces(installer, monkeypatch):
    def failing_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="fatal: repo not found")

    monkeypatch.setattr(subprocess, "run", failing_run)
    src = SourceDescriptor(type="github", user_repo="acme/missing", ref=None)
    with pytest.raises(InstallError) as exc:
        installer.install(src)
    assert "git clone" in str(exc.value).lower()
    assert "repo not found" in str(exc.value)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_plugins_installer.py -v
```

Expected: All fail — `installer` module doesn't exist.

- [ ] **Step 3: Implement `src/locksmith/plugins/installer.py`**

```python
# -*- encoding: utf-8 -*-
"""
locksmith.plugins.installer module

Install / uninstall plugins. Pure logic + filesystem + ``git`` CLI.
No UI dependency; called by the Plugins page dialogs but also usable
from tests and scripts.
"""
from __future__ import annotations

import datetime
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from keri import help

from locksmith.plugins import storage
from locksmith.plugins.manifest import Manifest, ManifestError, parse_manifest

logger = help.ogler.getLogger(__name__)


class InstallError(RuntimeError):
    """Raised when an install or uninstall cannot complete."""


@dataclass(frozen=True)
class SourceDescriptor:
    """How to fetch a plugin."""

    type: Literal["github", "local"]
    user_repo: str | None = None  # for github
    ref: str | None = None        # for github (branch or tag)
    path: str | None = None       # for local

    def to_dict(self) -> dict[str, Any]:
        if self.type == "github":
            return {"type": "github", "user_repo": self.user_repo, "ref": self.ref}
        return {"type": "local", "path": self.path}


class PluginInstaller:
    """Install + uninstall plugins. Operates on storage paths only."""

    def install(self, source: SourceDescriptor) -> dict[str, Any]:
        """Install a plugin from the given source. Returns the index record."""
        logger.info("plugin.install.requested source=%s", source.to_dict())

        # Stage into a temp dir alongside the final location so the final rename is atomic.
        storage.plugin_root().mkdir(parents=True, exist_ok=True)
        staging_dir = Path(tempfile.mkdtemp(
            prefix=".tmp-install-", dir=storage.plugin_root(),
        ))

        try:
            commit = self._fetch_into(source, staging_dir)

            manifest = self._parse_manifest_in(staging_dir)
            self._check_not_already_installed(manifest.plugin_id)

            final_dir = storage.plugin_clone_dir(manifest.plugin_id)
            if final_dir.exists():
                raise InstallError(
                    f"plugin clone directory already exists at {final_dir}"
                )

            staging_dir.rename(final_dir)
            staging_dir = None  # rename succeeded; don't clean up

            record = self._record_for(manifest, source, commit)
            self._append_to_index(record)
            logger.info(
                "plugin.install.completed plugin_id=%s commit=%s",
                manifest.plugin_id, commit,
            )
            return record
        except InstallError:
            raise
        except Exception as e:
            logger.exception("plugin.install.unexpected_failure")
            raise InstallError(f"unexpected install failure: {e}") from e
        finally:
            if staging_dir is not None and staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)

    def uninstall(self, plugin_id: str) -> None:
        """Remove a plugin from disk and from the index."""
        logger.info("plugin.uninstall.requested plugin_id=%s", plugin_id)
        idx = storage.read_index()
        kept = [p for p in idx.get("plugins", []) if p["plugin_id"] != plugin_id]
        if len(kept) == len(idx.get("plugins", [])):
            raise InstallError(f"plugin not installed: {plugin_id}")

        clone = storage.plugin_clone_dir(plugin_id)
        if clone.exists():
            shutil.rmtree(clone)

        idx["plugins"] = kept
        storage.write_index(idx)
        logger.info("plugin.uninstall.completed plugin_id=%s", plugin_id)

    # ------------------- internals ----------------------------------

    def _fetch_into(self, source: SourceDescriptor, dest: Path) -> str:
        """Populate ``dest`` with the plugin content. Returns the commit SHA (or stub for local)."""
        if source.type == "local":
            assert source.path is not None
            src_path = Path(source.path)
            if not src_path.exists():
                raise InstallError(f"local source path does not exist: {src_path}")
            # `dest` was just created by mkdtemp — empty it before copytree.
            shutil.rmtree(dest)
            shutil.copytree(src_path, dest)
            return "local:" + datetime.datetime.utcnow().isoformat(timespec="seconds")

        # github
        assert source.user_repo is not None
        # `dest` was just mkdtemp'd; git clone wants an empty dir, so remove first.
        shutil.rmtree(dest)
        url = f"https://github.com/{source.user_repo}.git"
        cmd = ["git", "clone", "--depth", "1"]
        if source.ref:
            cmd += ["--branch", source.ref]
        cmd += [url, str(dest)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise InstallError(
                f"git clone failed (exit {result.returncode}): "
                f"{result.stderr.strip() or 'no stderr'}"
            )
        # Read the cloned commit SHA so we record exactly what was installed.
        sha = subprocess.check_output(
            ["git", "-C", str(dest), "rev-parse", "HEAD"],
        ).decode("utf-8").strip()
        return sha

    def _parse_manifest_in(self, clone_dir: Path) -> Manifest:
        manifest_file = clone_dir / "locksmith-plugin.toml"
        if not manifest_file.exists():
            raise InstallError(
                f"no locksmith-plugin.toml at {clone_dir} — not a Locksmith plugin"
            )
        try:
            return parse_manifest(manifest_file)
        except ManifestError as e:
            raise InstallError(str(e)) from e

    def _check_not_already_installed(self, plugin_id: str) -> None:
        idx = storage.read_index()
        for p in idx.get("plugins", []):
            if p["plugin_id"] == plugin_id:
                src = p.get("source", {})
                raise InstallError(
                    f"plugin '{plugin_id}' is already installed "
                    f"(from {src.get('type', '?')}:{src.get('user_repo') or src.get('path')}). "
                    f"Uninstall it first."
                )

    def _record_for(
        self, manifest: Manifest, source: SourceDescriptor, commit: str,
    ) -> dict[str, Any]:
        return {
            "plugin_id": manifest.plugin_id,
            "source": source.to_dict(),
            "commit": commit,
            "installed_at": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "manifest_snapshot": manifest.to_dict(),
        }

    def _append_to_index(self, record: dict[str, Any]) -> None:
        idx = storage.read_index()
        idx.setdefault("format", 1)
        idx.setdefault("plugins", []).append(record)
        storage.write_index(idx)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_plugins_installer.py -v
```

Expected: All 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/installer.py tests/test_plugins_installer.py
git commit -m "$(cat <<'EOF'
feat(plugins): add PluginInstaller (local + github sources, uninstall)

SourceDescriptor unifies local-path and github user/repo install vectors.
install() stages into a tmp dir under ~/.locksmith/plugins/, parses and
validates the manifest, refuses duplicate plugin_id, then atomically
renames into the final location and appends to index.json. uninstall()
removes the clone and the index entry. git failures surface stderr to
the caller for UI display. Structured log lines at every state
transition for test consumption.

Refs: #50
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: PluginManager rewrite (index-driven discovery + type-aware dispatch)

**Why now:** The contract, manifest, storage, and installer are all in place. The manager ties them together — and is the file with the most behavior change.

**Files:**
- Modify: `src/locksmith/plugins/manager.py` (full rewrite)
- Create: `tests/test_plugins_manager.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_plugins_manager.py`:

```python
"""Tests for the rewritten PluginManager (index discovery, dispatch, exclude)."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from locksmith.plugins import storage
from locksmith.plugins.base import AppPlugin, VaultPlugin
from locksmith.plugins.installer import PluginInstaller, SourceDescriptor
from locksmith.plugins.manager import PluginManager


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "plugins"


@pytest.fixture
def isolated_plugin_root(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    # Make sure echo_app fixture is importable after install.
    if "echo_app" in sys.modules:
        del sys.modules["echo_app"]
    yield tmp_path
    if "echo_app" in sys.modules:
        del sys.modules["echo_app"]


@pytest.fixture
def fake_app():
    app = MagicMock()
    app.config = SimpleNamespace(base="")
    return app


def _install_echo(installer):
    installer.install(SourceDescriptor(type="local", path=str(FIXTURE_ROOT / "echo-app")))


def test_discovery_loads_installed_plugins_from_index(isolated_plugin_root, fake_app):
    _install_echo(PluginInstaller())
    mgr = PluginManager(fake_app, keri_base=isolated_plugin_root / "keri")
    mgr.discover()
    assert "echo_app" in mgr.loaded_ids()


def test_discovery_calls_initialize(isolated_plugin_root, fake_app):
    _install_echo(PluginInstaller())
    mgr = PluginManager(fake_app, keri_base=isolated_plugin_root / "keri")
    mgr.discover()
    plugin = mgr.get_plugin("echo_app")
    assert plugin is not None
    assert isinstance(plugin, AppPlugin)


def test_on_app_started_runs_only_app_plugins(isolated_plugin_root, fake_app, caplog):
    _install_echo(PluginInstaller())
    mgr = PluginManager(fake_app, keri_base=isolated_plugin_root / "keri")
    mgr.discover()
    with caplog.at_level("INFO"):
        mgr.on_app_started(window=MagicMock())
    # The echo fixture logs at each lifecycle event — assert against it.
    assert any("on_app_started plugin_id=echo_app" in rec.getMessage() for rec in caplog.records)


def test_on_app_stopping_stops_services_in_reverse(isolated_plugin_root, fake_app, caplog):
    _install_echo(PluginInstaller())
    mgr = PluginManager(fake_app, keri_base=isolated_plugin_root / "keri")
    mgr.discover()
    window = MagicMock()
    mgr.on_app_started(window=window)
    with caplog.at_level("INFO"):
        mgr.on_app_stopping()
    messages = [rec.getMessage() for rec in caplog.records]
    assert any("service.stopped plugin_id=echo_app" in m for m in messages)
    assert any("on_app_stopping plugin_id=echo_app" in m for m in messages)


def test_excluded_plugin_is_not_loaded(isolated_plugin_root, fake_app):
    _install_echo(PluginInstaller())
    keri_base = isolated_plugin_root / "keri"
    storage.write_enable_list(keri_base, {"format": 1, "excluded": ["echo_app"]})
    mgr = PluginManager(fake_app, keri_base=keri_base)
    mgr.discover()
    assert "echo_app" not in mgr.loaded_ids()
    assert "echo_app" in mgr.excluded_ids()


def test_missing_clone_dir_marks_files_missing(isolated_plugin_root, fake_app):
    _install_echo(PluginInstaller())
    # Sabotage: remove the clone dir but leave the index intact.
    import shutil as _sh
    _sh.rmtree(storage.plugin_clone_dir("echo_app"))
    mgr = PluginManager(fake_app, keri_base=isolated_plugin_root / "keri")
    mgr.discover()
    state = mgr.get_state("echo_app")
    assert state.status == "files_missing"
    assert "echo_app" not in mgr.loaded_ids()


def test_failed_initialize_marks_failed_does_not_crash(isolated_plugin_root, fake_app, caplog):
    _install_echo(PluginInstaller())
    mgr = PluginManager(fake_app, keri_base=isolated_plugin_root / "keri")
    # Inject a failing initialize on the plugin module before discovery.
    import echo_app.plugin as ep
    orig_init = ep.EchoAppPlugin.initialize
    ep.EchoAppPlugin.initialize = lambda self, app: (_ for _ in ()).throw(RuntimeError("boom"))
    try:
        with caplog.at_level("ERROR"):
            mgr.discover()
    finally:
        ep.EchoAppPlugin.initialize = orig_init
    state = mgr.get_state("echo_app")
    assert state.status == "failed"
    assert "boom" in state.error
    # The wallet must not have crashed — other plugins (none here) would still load.
    assert isinstance(mgr.loaded_ids(), list)


def test_entry_point_fallback_still_works(isolated_plugin_root, fake_app):
    """Entry-point-registered plugins (in-tree kerifoundation) must still load."""
    from locksmith.ui.vault.menu import MenuButton  # used by VaultPlugin contract
    mgr = PluginManager(fake_app, keri_base=isolated_plugin_root / "keri")
    mgr.discover()
    # The wallet's pyproject.toml declares `kerifoundation` as an entry point.
    assert "kerifoundation" in mgr.loaded_ids()
    kf = mgr.get_plugin("kerifoundation")
    assert isinstance(kf, VaultPlugin)


def test_excluded_kerifoundation_still_skipped_via_entry_points(
    isolated_plugin_root, fake_app,
):
    keri_base = isolated_plugin_root / "keri"
    storage.write_enable_list(keri_base, {"format": 1, "excluded": ["kerifoundation"]})
    mgr = PluginManager(fake_app, keri_base=keri_base)
    mgr.discover()
    assert "kerifoundation" not in mgr.loaded_ids()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_plugins_manager.py -v
```

Expected: Many fail — the manager doesn't have the new API yet.

- [ ] **Step 3: Rewrite `src/locksmith/plugins/manager.py`**

```python
# -*- encoding: utf-8 -*-
"""
locksmith.plugins.manager module

Plugin discovery, lifecycle dispatch, and state tracking.

Discovery order:
1. Walk ``~/.locksmith/plugins/index.json``. For each entry:
   - skip if in this wallet's exclude list
   - skip if requires_locksmith is not satisfied (mark Incompatible)
   - skip if clone dir is missing (mark Files-Missing)
   - else add the clone to sys.path, import the entry_point, instantiate
2. Walk Python entry-points registered under ``locksmith.plugins`` for
   in-tree plugins (kerifoundation today). Same exclude check applies.
3. Call ``initialize(app)`` on each loaded plugin (any exception marks
   it Failed and removes it from the loaded set).

Dispatch:
- App lifecycle hooks (on_app_started, on_app_stopping, app shortcuts,
  app services) only run on plugins that are instances of AppPlugin.
- Vault hooks only run on plugins that are instances of VaultPlugin.
- A plugin that inherits both gets both code paths.
"""
from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, TYPE_CHECKING

from keri import help

from locksmith.plugins import storage
from locksmith.plugins.base import (
    AccountProviderPlugin,
    AppPlugin,
    PluginCore,
    VaultPlugin,
)

if TYPE_CHECKING:
    from locksmith.ui.vault.menu import VaultNavMenu
    from locksmith.ui.vault.page import VaultPage

logger = help.ogler.getLogger(__name__)

ENTRY_POINT_GROUP = "locksmith.plugins"


@dataclass
class PluginState:
    plugin_id: str
    status: str = "loaded"   # loaded | excluded | incompatible | files_missing | failed
    error: str = ""
    source: dict[str, Any] = field(default_factory=dict)
    manifest_snapshot: dict[str, Any] = field(default_factory=dict)
    in_tree: bool = False


class PluginManager:
    """Discovers, initializes, and manages Locksmith plugins."""

    def __init__(self, app: Any, *, keri_base: Path):
        self._app = app
        self._keri_base = Path(keri_base)
        self._plugins: dict[str, PluginCore] = {}
        self._states: dict[str, PluginState] = {}
        self._started_services: dict[str, list[Any]] = {}

    # ------------------- discovery ---------------------------------

    def discover(self) -> None:
        excluded = set(
            storage.read_enable_list(self._keri_base).get("excluded", [])
        )
        self._discover_from_index(excluded)
        self._discover_from_entry_points(excluded)
        self._call_initialize_on_all()

    def _discover_from_index(self, excluded: set[str]) -> None:
        idx = storage.read_index()
        for record in idx.get("plugins", []):
            pid = record.get("plugin_id")
            if not pid:
                continue
            self._states[pid] = PluginState(
                plugin_id=pid,
                source=record.get("source", {}),
                manifest_snapshot=record.get("manifest_snapshot", {}),
            )
            if pid in excluded:
                self._states[pid].status = "excluded"
                logger.info("plugin.skipped reason=excluded plugin_id=%s", pid)
                continue
            if not self._compat_ok(record):
                self._states[pid].status = "incompatible"
                logger.info("plugin.skipped reason=incompatible plugin_id=%s", pid)
                continue
            clone = storage.plugin_clone_dir(pid)
            if not clone.exists():
                self._states[pid].status = "files_missing"
                logger.warning(
                    "plugin.skipped reason=files_missing plugin_id=%s expected_at=%s",
                    pid, clone,
                )
                continue
            try:
                self._load_from_clone(record, clone)
            except Exception as e:  # noqa: BLE001
                self._states[pid].status = "failed"
                self._states[pid].error = self._format_error(e)
                logger.exception("plugin.load_failed plugin_id=%s", pid)

    def _discover_from_entry_points(self, excluded: set[str]) -> None:
        try:
            eps = importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)
        except Exception:
            logger.exception("plugin.entry_points.discovery_failed")
            return
        for ep in eps:
            try:
                plugin_cls = ep.load()
                plugin = plugin_cls()
                pid = plugin.plugin_id
                if pid in self._states:
                    # Already loaded via index — index wins.
                    continue
                state = PluginState(plugin_id=pid, in_tree=True)
                if pid in excluded:
                    state.status = "excluded"
                    self._states[pid] = state
                    logger.info("plugin.skipped reason=excluded plugin_id=%s", pid)
                    continue
                self._plugins[pid] = plugin
                self._states[pid] = state
                logger.info("plugin.loaded plugin_id=%s source=entry_point", pid)
            except Exception as e:  # noqa: BLE001
                logger.exception(
                    "plugin.entry_point.load_failed name=%s", ep.name,
                )

    def _load_from_clone(self, record: dict[str, Any], clone: Path) -> None:
        pid = record["plugin_id"]
        snap = record.get("manifest_snapshot", {})
        entry_point = snap.get("entry_point")
        if not entry_point or ":" not in entry_point:
            raise RuntimeError(f"missing or malformed entry_point in record: {entry_point!r}")

        module_name, _, class_name = entry_point.partition(":")

        # Put the clone dir on sys.path so its top-level package imports.
        clone_str = str(clone)
        if clone_str not in sys.path:
            sys.path.insert(0, clone_str)

        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)
        plugin = cls()
        if plugin.plugin_id != pid:
            raise RuntimeError(
                f"plugin_id mismatch: manifest says {pid!r}, "
                f"class returns {plugin.plugin_id!r}"
            )
        self._plugins[pid] = plugin
        logger.info("plugin.loaded plugin_id=%s source=clone path=%s", pid, clone)

    def _call_initialize_on_all(self) -> None:
        for pid in list(self._plugins.keys()):
            plugin = self._plugins[pid]
            try:
                plugin.initialize(self._app)
            except Exception as e:  # noqa: BLE001
                self._states[pid].status = "failed"
                self._states[pid].error = self._format_error(e)
                del self._plugins[pid]
                logger.exception("plugin.initialize_failed plugin_id=%s", pid)

    @staticmethod
    def _format_error(e: Exception) -> str:
        return "".join(traceback.format_exception_only(type(e), e)).strip()

    def _compat_ok(self, record: dict[str, Any]) -> bool:
        """Apply the requires_locksmith gate. Stage 1 always passes; Stage N tightens."""
        # For Stage 1 we don't yet read locksmith's own version. Always accept.
        # When wallet versioning lands, parse requires_locksmith (PEP 440-style range)
        # and compare against locksmith.__version__.
        return True

    # ------------------- public read API ---------------------------

    def loaded_ids(self) -> list[str]:
        return list(self._plugins.keys())

    def excluded_ids(self) -> list[str]:
        return [s.plugin_id for s in self._states.values() if s.status == "excluded"]

    def get_plugin(self, plugin_id: str) -> PluginCore | None:
        return self._plugins.get(plugin_id)

    def get_state(self, plugin_id: str) -> PluginState | None:
        return self._states.get(plugin_id)

    def all_states(self) -> list[PluginState]:
        return list(self._states.values())

    # ------------------- App-lifecycle dispatch --------------------

    def on_app_started(self, window: Any) -> None:
        for pid, plugin in self._plugins.items():
            if not isinstance(plugin, AppPlugin):
                continue
            try:
                plugin.on_app_started(self._app, window)
            except Exception:
                self._states[pid].status = "failed"
                self._states[pid].error = self._format_error_from_current()
                logger.exception("plugin.on_app_started_failed plugin_id=%s", pid)
                continue
            services = []
            for service in plugin.get_app_services():
                try:
                    service.start()
                    services.append(service)
                except Exception:
                    logger.exception(
                        "plugin.service.start_failed plugin_id=%s service=%s",
                        pid, type(service).__name__,
                    )
            self._started_services[pid] = services

    def on_app_stopping(self) -> None:
        # Stop services in reverse start order.
        for pid in reversed(list(self._started_services.keys())):
            for service in reversed(self._started_services.get(pid, [])):
                try:
                    service.stop()
                except Exception:
                    logger.exception(
                        "plugin.service.stop_failed plugin_id=%s service=%s",
                        pid, type(service).__name__,
                    )
        for pid, plugin in self._plugins.items():
            if not isinstance(plugin, AppPlugin):
                continue
            try:
                plugin.on_app_stopping(self._app)
            except Exception:
                logger.exception("plugin.on_app_stopping_failed plugin_id=%s", pid)

    # ------------------- Vault-lifecycle dispatch ------------------

    def discover_and_initialize_vault_ui(
        self, vault_page: "VaultPage", nav_menu: "VaultNavMenu",
    ) -> None:
        """Register vault-plugin pages and menus into the VaultPage.

        Called from LocksmithWindow.__init__ after pages are created.
        Replaces the old discover_and_initialize() entrypoint.
        """
        for pid, plugin in self._plugins.items():
            if not isinstance(plugin, VaultPlugin):
                continue
            try:
                for key, widget in plugin.get_pages().items():
                    vault_page.register_page(key, widget)
                nav_menu.register_plugin_section(
                    pid, plugin.get_menu_entry(), plugin.get_menu_section(),
                )
            except Exception:
                logger.exception("plugin.vault_ui.register_failed plugin_id=%s", pid)

    def on_vault_opened(self, vault: Any) -> None:
        for pid, plugin in self._plugins.items():
            if not isinstance(plugin, VaultPlugin):
                continue
            try:
                plugin.on_vault_opened(vault)
                vault.doers.extend(plugin.get_doers())
            except Exception:
                logger.exception("plugin.on_vault_opened_failed plugin_id=%s", pid)

    def prepare_vault_deletion(self, vault: Any) -> None:
        for pid, plugin in self._plugins.items():
            if not isinstance(plugin, VaultPlugin):
                continue
            try:
                plugin.prepare_vault_deletion(vault)
            except Exception:
                logger.exception("plugin.prepare_vault_deletion_failed plugin_id=%s", pid)
                raise

    def on_vault_closed(self, vault: Any, *, clear: bool = False) -> None:
        for pid, plugin in self._plugins.items():
            if not isinstance(plugin, VaultPlugin):
                continue
            try:
                plugin.on_vault_closed(vault, clear=clear)
            except Exception:
                logger.exception("plugin.on_vault_closed_failed plugin_id=%s", pid)

    def is_setup_complete(self, plugin_id: str, vault: Any) -> bool:
        plugin = self._plugins.get(plugin_id)
        if plugin and isinstance(plugin, AccountProviderPlugin):
            return plugin.is_setup_complete(vault)
        return True

    async def after_identifier_authenticated(self, vault: Any, hab: Any) -> None:
        for pid, plugin in self._plugins.items():
            if not isinstance(plugin, VaultPlugin):
                continue
            try:
                await plugin.after_identifier_authenticated(vault, hab)
            except Exception:
                logger.exception(
                    "plugin.after_identifier_authenticated_failed plugin_id=%s", pid,
                )

    def get_witness_batches(self, vault: Any, hab_pre: str) -> Any | None:
        merged = []
        seen = set()
        for plugin in self._plugins.values():
            if not isinstance(plugin, VaultPlugin):
                continue
            result = plugin.get_witness_batches(vault, hab_pre)
            if result is None:
                continue
            for batch in getattr(result, "batches", []) or []:
                if not isinstance(batch, (list, tuple)) or not batch:
                    continue
                key = tuple(sorted(str(eid) for eid in batch))
                if key in seen:
                    continue
                seen.add(key)
                merged.append(list(batch))
        if not merged:
            return None
        return SimpleNamespace(batches=merged)

    def update_witness_state_after_rotation(self, vault: Any, wit_eid: str) -> None:
        for plugin in self._plugins.values():
            if isinstance(plugin, VaultPlugin):
                plugin.update_witness_state(vault, wit_eid)

    def update_witness_state_after_auth(self, vault: Any, wit_eid: str) -> None:
        for plugin in self._plugins.values():
            if isinstance(plugin, VaultPlugin):
                plugin.update_witness_state_after_auth(vault, wit_eid)

    # ------------------- internal helpers --------------------------

    def _format_error_from_current(self) -> str:
        import sys as _sys
        exc = _sys.exc_info()[1]
        return self._format_error(exc) if exc else ""
```

- [ ] **Step 4: Update the legacy callsite signature**

`src/locksmith/ui/window.py` currently calls `self.app.plugin_manager.discover_and_initialize(vault_page, vault_page.nav_menu)` at line 88. This signature is preserved by Task 13 (window wiring); for now, add a temporary shim so the manager change doesn't break anything:

Edit `src/locksmith/plugins/manager.py`, append after the existing class body:

```python
    def discover_and_initialize(
        self, vault_page: "VaultPage", nav_menu: "VaultNavMenu",
    ) -> None:
        """Legacy entrypoint kept for ui.window compatibility until Task 13."""
        self.discover()
        self.discover_and_initialize_vault_ui(vault_page, nav_menu)
```

- [ ] **Step 5: Update `LocksmithApplication` to construct the manager with `keri_base`**

In `src/locksmith/core/apping.py`, find the line:

```python
self.plugin_manager = PluginManager(self)
```

Change to:

```python
from pathlib import Path as _Path  # if not already imported
self.plugin_manager = PluginManager(
    self, keri_base=_Path(self.config.base or _Path.home() / ".keri"),
)
```

Verify the surrounding code; if `Path` is already imported at the module top, use it directly without the alias.

- [ ] **Step 6: Run the manager tests**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_plugins_manager.py -v
```

Expected: All 9 tests PASS.

- [ ] **Step 7: Run the full test suite as a regression gate**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -x --ignore=tests/fixtures
```

Expected: No regressions. Existing kerifoundation tests still pass because `discover_and_initialize` shim preserves the old call signature.

- [ ] **Step 8: Commit**

```bash
git add src/locksmith/plugins/manager.py src/locksmith/core/apping.py tests/test_plugins_manager.py
git commit -m "$(cat <<'EOF'
feat(plugins): rewrite PluginManager for index-driven discovery + typed dispatch

Walks ~/.locksmith/plugins/index.json first, then falls back to Python
entry-points so in-tree kerifoundation keeps loading. Plugins are
imported by adding their clone dir to sys.path and importlib-loading
the entry_point. Failures are isolated per plugin and surfaced through
PluginState (loaded / excluded / incompatible / files_missing / failed).

Dispatch is type-aware: AppPlugin hooks (on_app_started, on_app_stopping,
get_app_shortcuts, get_app_services) walk only AppPlugin instances;
vault hooks walk only VaultPlugin instances. A plugin inheriting both
gets both code paths.

Legacy discover_and_initialize() is preserved as a shim against
ui/window.py until the window wiring task lands.

Refs: #50
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Add `Pages.PLUGINS` navigation entry

**Why now:** Smallest possible UI change — one enum value — but the Plugins page widget (Task 9) and toolbar button (Task 12) both depend on it.

**Files:**
- Modify: `src/locksmith/ui/navigation.py:16-19`

- [ ] **Step 1: Add the enum value**

Edit `src/locksmith/ui/navigation.py`, change:

```python
class Pages(Enum):
    """Enumeration of available pages in the application."""
    HOME = "home"
    VAULT = "vault"
```

to:

```python
class Pages(Enum):
    """Enumeration of available pages in the application."""
    HOME = "home"
    PLUGINS = "plugins"
    VAULT = "vault"
```

- [ ] **Step 2: Verify the change parses**

```bash
.venv/bin/python -c "from locksmith.ui.navigation import Pages; print(Pages.PLUGINS.value)"
```

Expected: `plugins`

- [ ] **Step 3: Run the full test suite**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -x --ignore=tests/fixtures
```

Expected: No regressions.

- [ ] **Step 4: Commit**

```bash
git add src/locksmith/ui/navigation.py
git commit -m "$(cat <<'EOF'
feat(ui): add Pages.PLUGINS navigation key

Reserves the enum value for the new top-level Plugins page added in the
next commit. Standalone for easy revert.

Refs: #50
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: PluginsPage widget (list + state badges)

**Why now:** Page widget can be tested via structural asserts + screenshot before any dialogs are wired up. Install/Uninstall buttons are stubs for this task; they get hooked up in Tasks 10–11.

**Files:**
- Create: `src/locksmith/ui/plugins/__init__.py`
- Create: `src/locksmith/ui/plugins/page.py`
- Create: `tests/test_plugins_page_visual.py`

- [ ] **Step 1: Write the failing test**

`tests/test_plugins_page_visual.py`:

```python
"""Visual + structural smoke test for the PluginsPage.

Pattern follows tests/test_create_role_dialog_visual.py:
- render, structurally assert, screenshot to tests/_screenshots/.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtTest import QTest

from locksmith.plugins.manager import PluginState
from locksmith.ui.plugins.page import PluginsPage


SCREENSHOT_DIR = Path(__file__).parent / "_screenshots"


@pytest.fixture
def fake_app_with_states():
    states = [
        PluginState(
            plugin_id="kerifoundation",
            status="loaded",
            manifest_snapshot={"name": "KERI Foundation", "version": "0.3.1",
                                "description": "Onboarding, witnesses, watchers"},
            in_tree=True,
        ),
        PluginState(
            plugin_id="echo_app",
            status="loaded",
            source={"type": "github", "user_repo": "acme/echo", "ref": None},
            manifest_snapshot={"name": "Echo App", "version": "0.1.0",
                                "description": "Logs lifecycle events"},
        ),
        PluginState(
            plugin_id="future",
            status="incompatible",
            error="requires Locksmith >=0.5 (you have 0.4)",
            manifest_snapshot={"name": "Future Plugin", "version": "0.2.0",
                                "description": "From the future"},
        ),
    ]
    app = MagicMock()
    app.plugin_manager.all_states.return_value = states
    return app


def test_page_renders_all_states(qapp, fake_app_with_states):
    page = PluginsPage(fake_app_with_states)
    page.resize(900, 700)
    page.show()
    QTest.qWait(250)
    qapp.processEvents()

    # Structural: one row per state, each showing the plugin's name.
    rendered_names = [w.text() for w in page.findChildren(type(page).PluginNameLabel)]
    assert "KERI Foundation" in rendered_names
    assert "Echo App" in rendered_names
    assert "Future Plugin" in rendered_names

    # In-tree badge present on kerifoundation only.
    in_tree_labels = [
        w for w in page.findChildren(type(page).InTreeBadge) if w.isVisible()
    ]
    assert len(in_tree_labels) == 1

    # Status badge text correct.
    statuses = [b.text() for b in page.findChildren(type(page).StatusBadge)]
    assert any("Loaded" in s for s in statuses)
    assert any("Incompatible" in s for s in statuses)

    # Visual.
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    page.grab().save(str(SCREENSHOT_DIR / "plugins_page_mixed_states.png"))


def test_empty_state(qapp):
    app = MagicMock()
    app.plugin_manager.all_states.return_value = []
    page = PluginsPage(app)
    page.resize(900, 700)
    page.show()
    QTest.qWait(250)
    qapp.processEvents()
    assert page.findChild(type(page).EmptyStateLabel) is not None
    page.grab().save(str(SCREENSHOT_DIR / "plugins_page_empty.png"))


def test_install_button_emits_signal(qapp, fake_app_with_states):
    page = PluginsPage(fake_app_with_states)
    page.show()
    QTest.qWait(250)
    qapp.processEvents()

    fired = {"count": 0}
    page.install_clicked.connect(lambda: fired.update(count=fired["count"] + 1))
    page._install_button.click()
    qapp.processEvents()
    assert fired["count"] == 1
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_plugins_page_visual.py -v
```

Expected: Fail — `PluginsPage` doesn't exist.

- [ ] **Step 3: Create `src/locksmith/ui/plugins/__init__.py`**

Empty file.

- [ ] **Step 4: Implement `src/locksmith/ui/plugins/page.py`**

```python
# -*- encoding: utf-8 -*-
"""
locksmith.ui.plugins.page module

Top-level Plugins page (Pages.PLUGINS). Lists installed plugins with
state badges; exposes Install / Uninstall / Exclude affordances.

Install and Uninstall both surface signals; the LocksmithWindow wires
those signals to dialogs and to PluginInstaller calls (Task 13).
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from keri import help

logger = help.ogler.getLogger(__name__)


_STATUS_COPY = {
    "loaded":         ("● Loaded",            "#1c8a3a"),
    "excluded":       ("○ Excluded (this wallet)", "#777"),
    "incompatible":   ("⚠ Incompatible",      "#a8770a"),
    "files_missing":  ("⚠ Files missing",     "#a8770a"),
    "failed":         ("⚠ Failed to load",    "#c8341c"),
}


class PluginsPage(QWidget):
    """The Plugins management page."""

    install_clicked = Signal()
    uninstall_clicked = Signal(str)   # plugin_id
    exclude_toggled = Signal(str, bool)  # plugin_id, now_excluded

    class PluginNameLabel(QLabel):
        pass

    class StatusBadge(QLabel):
        pass

    class InTreeBadge(QLabel):
        pass

    class EmptyStateLabel(QLabel):
        pass

    def __init__(self, app: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self.app = app
        self.setObjectName("PluginsPage")
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(16)

        header = QLabel("Plugins")
        header.setStyleSheet("font-size: 22px; font-weight: 600;")
        outer.addWidget(header)

        self._restart_banner = QLabel(
            "⚠ Restart required to finish applying changes."
        )
        self._restart_banner.setStyleSheet(
            "background:#fff4d6; padding:8px 12px; border:1px solid #d6b15a;"
        )
        self._restart_banner.setVisible(False)
        outer.addWidget(self._restart_banner)

        self._list_scroll = QScrollArea()
        self._list_scroll.setWidgetResizable(True)
        self._list_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setSpacing(12)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._list_scroll.setWidget(self._list_container)
        outer.addWidget(self._list_scroll, stretch=1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self._install_button = QPushButton("+ Install plugin")
        self._install_button.setObjectName("plugins_install_button")
        self._install_button.clicked.connect(self.install_clicked.emit)
        button_row.addWidget(self._install_button)
        outer.addLayout(button_row)

    def _refresh(self) -> None:
        # Clear existing rows.
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        states = list(self.app.plugin_manager.all_states())
        if not states:
            empty = self.EmptyStateLabel(
                "No plugins installed yet.\nClick + Install plugin to add one."
            )
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color:#777; padding:32px;")
            self._list_layout.addWidget(empty)
            return

        for state in states:
            self._list_layout.addWidget(self._make_row(state))

    def _make_row(self, state) -> QWidget:
        card = QFrame()
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setStyleSheet(
            "QFrame { border:1px solid #ddd; border-radius:6px; "
            "background:#fff; padding:12px; }"
        )
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        v = QVBoxLayout(card)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(6)

        snap = state.manifest_snapshot or {}
        name = snap.get("name", state.plugin_id)
        version = snap.get("version", "")
        desc = snap.get("description", "")

        top_row = QHBoxLayout()
        name_label = self.PluginNameLabel(name)
        name_label.setStyleSheet("font-weight:600; font-size:15px;")
        top_row.addWidget(name_label)
        if version:
            v_label = QLabel(f"v{version}")
            v_label.setStyleSheet("color:#777; padding-left:8px;")
            top_row.addWidget(v_label)
        if state.in_tree:
            in_tree = self.InTreeBadge("[ in-tree ]")
            in_tree.setStyleSheet("color:#777; padding-left:8px;")
            top_row.addWidget(in_tree)
        elif state.source:
            src = state.source
            if src.get("type") == "github":
                src_label = QLabel(f"from github:{src.get('user_repo', '?')}")
                src_label.setStyleSheet("color:#777; padding-left:8px;")
                top_row.addWidget(src_label)
        top_row.addStretch(1)
        v.addLayout(top_row)

        if desc:
            desc_label = QLabel(desc)
            desc_label.setStyleSheet("color:#444;")
            desc_label.setWordWrap(True)
            v.addWidget(desc_label)

        bottom_row = QHBoxLayout()
        text, color = _STATUS_COPY.get(state.status, ("?", "#888"))
        badge = self.StatusBadge(text)
        badge.setStyleSheet(f"color:{color}; font-weight:600;")
        bottom_row.addWidget(badge)
        if state.error and state.status in ("failed", "incompatible"):
            err = QLabel(state.error)
            err.setStyleSheet("color:#c8341c; font-style:italic; padding-left:8px;")
            err.setWordWrap(True)
            bottom_row.addWidget(err, stretch=1)
        bottom_row.addStretch(1)
        if not state.in_tree:
            exclude_btn = QPushButton(
                "Include on this wallet" if state.status == "excluded"
                else "Exclude on this wallet"
            )
            exclude_btn.clicked.connect(
                lambda _=False, pid=state.plugin_id, was=state.status == "excluded":
                self.exclude_toggled.emit(pid, not was)
            )
            bottom_row.addWidget(exclude_btn)
            uninstall_btn = QPushButton("Uninstall")
            uninstall_btn.clicked.connect(
                lambda _=False, pid=state.plugin_id:
                self.uninstall_clicked.emit(pid)
            )
            bottom_row.addWidget(uninstall_btn)
        v.addLayout(bottom_row)
        return card

    # Toolbar / window protocol — every page implements this.

    def get_toolbar_config(self) -> dict:
        return {"title": "Plugins", "show_back": False}

    def on_show(self) -> None:
        self._refresh()

    def on_hide(self) -> None:
        pass

    def set_restart_required(self, required: bool) -> None:
        self._restart_banner.setVisible(required)
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_plugins_page_visual.py -v
```

Expected: All 3 tests PASS. Screenshots land at `tests/_screenshots/plugins_page_mixed_states.png` and `plugins_page_empty.png`.

- [ ] **Step 6: Commit**

```bash
git add src/locksmith/ui/plugins/__init__.py src/locksmith/ui/plugins/page.py tests/test_plugins_page_visual.py
git commit -m "$(cat <<'EOF'
feat(ui): add PluginsPage widget

Lists installed plugins with per-row state badges (Loaded / Excluded /
Incompatible / Files missing / Failed). Per-plugin Uninstall and Exclude
buttons emit signals; the page does not call PluginInstaller directly
(window wires that up later). Restart-required banner is hidden by
default. In-tree plugins (entry-point-registered) get an [ in-tree ]
badge and no Uninstall.

Refs: #50
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Install source dialog (Step 1 of the wizard)

**Why now:** PluginsPage emits `install_clicked`; the window will wire it to this dialog in Task 13. Test the dialog standalone first.

**Files:**
- Create: `src/locksmith/ui/plugins/install_dialog.py`
- Modify: `tests/test_plugins_page_visual.py` (add dialog tests inline — same file)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_plugins_page_visual.py`:

```python
from locksmith.plugins.installer import SourceDescriptor
from locksmith.ui.plugins.install_dialog import InstallSourceDialog


def test_install_dialog_default_state(qapp):
    dlg = InstallSourceDialog()
    dlg.show()
    QTest.qWait(200)
    qapp.processEvents()
    # GitHub radio selected by default.
    assert dlg.github_radio.isChecked()
    assert not dlg.local_radio.isChecked()
    # Fetch button starts disabled (no input yet).
    assert not dlg.fetch_button.isEnabled()
    dlg.grab().save(str(SCREENSHOT_DIR / "install_dialog_default.png"))


def test_github_userrepo_validation(qapp):
    dlg = InstallSourceDialog()
    dlg.show()
    QTest.qWait(150)

    # Bad format.
    dlg.user_repo_input.setText("not a valid format")
    qapp.processEvents()
    assert not dlg.fetch_button.isEnabled()
    assert "must be" in dlg.error_label.text().lower() or "format" in dlg.error_label.text().lower()

    # Good format.
    dlg.user_repo_input.setText("acme/echo")
    qapp.processEvents()
    assert dlg.fetch_button.isEnabled()
    assert dlg.error_label.text() == ""


def test_local_path_validation(qapp, tmp_path):
    dlg = InstallSourceDialog()
    dlg.show()
    QTest.qWait(150)
    dlg.local_radio.setChecked(True)
    qapp.processEvents()

    # Path doesn't exist.
    dlg.local_path_input.setText(str(tmp_path / "nope"))
    qapp.processEvents()
    assert not dlg.fetch_button.isEnabled()

    # Path exists but no manifest.
    (tmp_path / "no-manifest").mkdir()
    dlg.local_path_input.setText(str(tmp_path / "no-manifest"))
    qapp.processEvents()
    assert not dlg.fetch_button.isEnabled()
    assert "locksmith-plugin.toml" in dlg.error_label.text()

    # Path with manifest.
    plug = tmp_path / "with-manifest"
    plug.mkdir()
    (plug / "locksmith-plugin.toml").write_text("placeholder\n")
    dlg.local_path_input.setText(str(plug))
    qapp.processEvents()
    assert dlg.fetch_button.isEnabled()


def test_fetch_emits_source_descriptor(qapp):
    dlg = InstallSourceDialog()
    dlg.show()
    QTest.qWait(150)
    captured = {}
    dlg.source_chosen.connect(lambda src: captured.update(src=src))

    dlg.user_repo_input.setText("acme/echo")
    dlg.ref_input.setText("main")
    qapp.processEvents()
    dlg.fetch_button.click()
    qapp.processEvents()

    assert captured["src"] == SourceDescriptor(
        type="github", user_repo="acme/echo", ref="main",
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_plugins_page_visual.py -v
```

Expected: New tests fail; existing visual tests still pass.

- [ ] **Step 3: Implement `src/locksmith/ui/plugins/install_dialog.py`**

```python
# -*- encoding: utf-8 -*-
"""
locksmith.ui.plugins.install_dialog module

Step 1 of the install wizard: pick a source (GitHub user/repo or local path).
Emits ``source_chosen(SourceDescriptor)`` on Fetch. The window owns the
subsequent fetch + trust-dialog flow.
"""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from locksmith.plugins.installer import SourceDescriptor


_GITHUB_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class InstallSourceDialog(QDialog):
    """Two-section source picker: GitHub | Local path."""

    source_chosen = Signal(SourceDescriptor)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Install plugin")
        self.setMinimumWidth(520)

        outer = QVBoxLayout(self)
        outer.setSpacing(12)
        outer.setContentsMargins(20, 20, 20, 20)

        outer.addWidget(QLabel("Source:"))
        self.github_radio = QRadioButton("GitHub  user/repo")
        self.github_radio.setChecked(True)
        self.github_radio.toggled.connect(self._on_source_kind_changed)
        outer.addWidget(self.github_radio)

        gh_row = QHBoxLayout()
        gh_row.addSpacing(28)
        self.user_repo_input = QLineEdit()
        self.user_repo_input.setPlaceholderText("e.g. seriouscoderone/locksmith-dev-control")
        self.user_repo_input.textChanged.connect(self._revalidate)
        gh_row.addWidget(self.user_repo_input)
        outer.addLayout(gh_row)

        self.local_radio = QRadioButton("Local path")
        self.local_radio.toggled.connect(self._on_source_kind_changed)
        outer.addWidget(self.local_radio)

        loc_row = QHBoxLayout()
        loc_row.addSpacing(28)
        self.local_path_input = QLineEdit()
        self.local_path_input.setPlaceholderText("/path/to/plugin/clone")
        self.local_path_input.setEnabled(False)
        self.local_path_input.textChanged.connect(self._revalidate)
        loc_row.addWidget(self.local_path_input)
        outer.addLayout(loc_row)

        ref_form = QFormLayout()
        self.ref_input = QLineEdit()
        self.ref_input.setPlaceholderText("(defaults to default branch HEAD)")
        ref_form.addRow("Branch/ref (optional):", self.ref_input)
        outer.addLayout(ref_form)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color:#c8341c;")
        self.error_label.setWordWrap(True)
        outer.addWidget(self.error_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        button_row.addWidget(cancel)
        self.fetch_button = QPushButton("Fetch")
        self.fetch_button.setEnabled(False)
        self.fetch_button.clicked.connect(self._on_fetch)
        button_row.addWidget(self.fetch_button)
        outer.addLayout(button_row)

    # ----- handlers -------------------------------------------------

    def _on_source_kind_changed(self) -> None:
        gh_active = self.github_radio.isChecked()
        self.user_repo_input.setEnabled(gh_active)
        self.local_path_input.setEnabled(not gh_active)
        self._revalidate()

    def _revalidate(self) -> None:
        ok, err = self._validate()
        self.error_label.setText(err)
        self.fetch_button.setEnabled(ok)

    def _validate(self) -> tuple[bool, str]:
        if self.github_radio.isChecked():
            text = self.user_repo_input.text().strip()
            if not text:
                return False, ""
            if not _GITHUB_RE.match(text):
                return False, (
                    "user/repo must be in the format owner/name "
                    "(letters, digits, dot, underscore, dash)."
                )
            return True, ""
        # Local path
        text = self.local_path_input.text().strip()
        if not text:
            return False, ""
        path = Path(text)
        if not path.exists():
            return False, f"path does not exist: {path}"
        if not (path / "locksmith-plugin.toml").exists():
            return False, f"no locksmith-plugin.toml in {path}"
        return True, ""

    def _on_fetch(self) -> None:
        ref = self.ref_input.text().strip() or None
        if self.github_radio.isChecked():
            src = SourceDescriptor(
                type="github",
                user_repo=self.user_repo_input.text().strip(),
                ref=ref,
            )
        else:
            src = SourceDescriptor(
                type="local",
                path=self.local_path_input.text().strip(),
            )
        self.source_chosen.emit(src)
        self.accept()
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_plugins_page_visual.py -v
```

Expected: All tests pass, including the 4 new install-dialog tests.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/ui/plugins/install_dialog.py tests/test_plugins_page_visual.py
git commit -m "$(cat <<'EOF'
feat(ui): add InstallSourceDialog (Step 1 of install wizard)

GitHub user/repo input or local path radio. Inline validation: bad
GitHub format and missing-path/missing-manifest local cases keep Fetch
disabled and surface an error label. On Fetch, emits a SourceDescriptor
to the caller for the trust-dialog step.

Refs: #50
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Trust dialog (Step 2 of the wizard)

**Why now:** Symmetric to Task 10 — testable standalone with a fixture manifest snapshot.

**Files:**
- Create: `src/locksmith/ui/plugins/trust_dialog.py`
- Modify: `tests/test_plugins_page_visual.py` (append tests)

- [ ] **Step 1: Append the failing tests**

Append to `tests/test_plugins_page_visual.py`:

```python
from locksmith.ui.plugins.trust_dialog import PluginTrustDialog


_FIXTURE_PARSED = {
    "plugin_id": "dev_control",
    "name": "Dev Control Harness",
    "version": "0.1.0",
    "description": "JSON-over-unix-socket harness for driving the live UI",
    "author": "Joseph Hunsaker",
    "capabilities": ["app.shortcut", "app.service", "window.full_access",
                     "fs.write", "net.listen"],
    "capabilities_detail": {
        "fs.write": "Writes screenshot PNGs",
        "net.listen": "Unix socket at $XDG_RUNTIME_DIR/...",
    },
}
_FIXTURE_SOURCE = {"type": "github", "user_repo": "acme/dev-control", "ref": None}
_FIXTURE_COMMIT = "a3f9c1dabe7c0f5e8b7a2b9d0c4e1f2a3b4c5d6e"


def test_trust_dialog_populates_from_manifest(qapp):
    dlg = PluginTrustDialog(
        manifest_snapshot=_FIXTURE_PARSED,
        source=_FIXTURE_SOURCE,
        commit=_FIXTURE_COMMIT,
    )
    dlg.show()
    QTest.qWait(250)
    qapp.processEvents()
    # Headline contains the name + version.
    assert "Dev Control Harness" in dlg.headline.text()
    assert "0.1.0" in dlg.headline.text()
    # Source line shows github user_repo and short commit.
    assert "acme/dev-control" in dlg.source_line.text()
    assert "a3f9c1d" in dlg.source_line.text()
    # Capability bullets present and human-readable.
    bullet_text = dlg.capability_block.toPlainText() if hasattr(dlg.capability_block, "toPlainText") else dlg.capability_block.text()
    for cap in ("keyboard shortcuts", "background services",
                "full main window", "write", "listening socket"):
        assert cap in bullet_text.lower(), f"missing capability copy: {cap}"
    dlg.grab().save(str(SCREENSHOT_DIR / "trust_dialog_populated.png"))


def test_trust_dialog_accept_emits(qapp):
    dlg = PluginTrustDialog(
        manifest_snapshot=_FIXTURE_PARSED,
        source=_FIXTURE_SOURCE,
        commit=_FIXTURE_COMMIT,
    )
    fired = {"accepted": False}
    dlg.trusted.connect(lambda: fired.update(accepted=True))
    dlg.show()
    QTest.qWait(150)
    dlg.accept_button.click()
    qapp.processEvents()
    assert fired["accepted"]


def test_trust_dialog_cancel_does_not_emit(qapp):
    dlg = PluginTrustDialog(
        manifest_snapshot=_FIXTURE_PARSED,
        source=_FIXTURE_SOURCE,
        commit=_FIXTURE_COMMIT,
    )
    fired = {"accepted": False}
    dlg.trusted.connect(lambda: fired.update(accepted=True))
    dlg.show()
    QTest.qWait(150)
    dlg.cancel_button.click()
    qapp.processEvents()
    assert not fired["accepted"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_plugins_page_visual.py -v
```

Expected: New tests fail.

- [ ] **Step 3: Implement `src/locksmith/ui/plugins/trust_dialog.py`**

```python
# -*- encoding: utf-8 -*-
"""
locksmith.ui.plugins.trust_dialog module

Step 2 of the install wizard: show the parsed manifest and ask the user
to confirm. Capability strings are translated to human copy; unknown
strings are shown verbatim with "(unrecognized)" appended.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


_CAPABILITY_COPY = {
    "app.shortcut":       "install global keyboard shortcuts",
    "app.service":        "run background services",
    "window.full_access": "inspect / control the full main window",
    "vault.full_access":  "access vault internals and credentials",
    "fs.write":           "write to disk",
    "fs.read":            "read from disk",
    "net.listen":         "open a local listening socket",
    "net.connect":        "make outbound network connections",
}


class PluginTrustDialog(QDialog):
    """Confirmation dialog before a plugin is installed."""

    trusted = Signal()

    def __init__(
        self,
        *,
        manifest_snapshot: dict[str, Any],
        source: dict[str, Any],
        commit: str,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Trust this plugin?")
        self.setMinimumWidth(560)

        name = manifest_snapshot.get("name", manifest_snapshot.get("plugin_id", "<unnamed>"))
        version = manifest_snapshot.get("version", "")

        outer = QVBoxLayout(self)
        outer.setSpacing(12)
        outer.setContentsMargins(20, 20, 20, 20)

        self.headline = QLabel(f"Trust '{name}' v{version}?")
        self.headline.setStyleSheet("font-size:18px; font-weight:600;")
        outer.addWidget(self.headline)

        if source.get("type") == "github":
            src_text = f"From: github.com/{source.get('user_repo')} @ {commit[:7]}"
        else:
            src_text = f"From: {source.get('path')}"
        self.source_line = QLabel(src_text)
        self.source_line.setStyleSheet("color:#444;")
        outer.addWidget(self.source_line)

        if manifest_snapshot.get("author"):
            outer.addWidget(QLabel(f"Author: {manifest_snapshot['author']}"))

        desc = manifest_snapshot.get("description", "")
        if desc:
            desc_label = QLabel(f"“{desc}”")
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet("color:#222; padding: 6px 0;")
            outer.addWidget(desc_label)

        outer.addWidget(QLabel("This plugin declares it will:"))
        self.capability_block = QTextBrowser()
        self.capability_block.setReadOnly(True)
        self.capability_block.setOpenLinks(False)
        self.capability_block.setStyleSheet(
            "QTextBrowser { background:#fafafa; border:1px solid #ddd; padding:8px; }"
        )
        self.capability_block.setHtml(self._capabilities_html(manifest_snapshot))
        self.capability_block.setMaximumHeight(160)
        outer.addWidget(self.capability_block)

        warn = QLabel(
            "Plugins run with full wallet permissions.  "
            "Only install plugins you trust."
        )
        warn.setStyleSheet("color:#a8770a; font-style:italic; padding:4px 0;")
        warn.setWordWrap(True)
        outer.addWidget(warn)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_row.addWidget(self.cancel_button)
        self.accept_button = QPushButton("Trust && install")
        self.accept_button.clicked.connect(self._on_accept)
        button_row.addWidget(self.accept_button)
        outer.addLayout(button_row)

    def _capabilities_html(self, snap: dict[str, Any]) -> str:
        caps = snap.get("capabilities", []) or []
        detail = snap.get("capabilities_detail", {}) or {}
        if not caps:
            return "<i>No capabilities declared.</i>"
        rows = []
        for cap in caps:
            copy = _CAPABILITY_COPY.get(cap, f"{cap} <i>(unrecognized)</i>")
            rows.append(f"<li>{copy}")
            if cap in detail:
                rows[-1] += (
                    f"<br><span style='padding-left:18px; color:#666;'>"
                    f"&#x21B3; {detail[cap]}</span>"
                )
            rows[-1] += "</li>"
        return "<ul style='margin:0; padding-left:18px;'>" + "".join(rows) + "</ul>"

    def _on_accept(self) -> None:
        self.trusted.emit()
        self.accept()
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_plugins_page_visual.py -v
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/ui/plugins/trust_dialog.py tests/test_plugins_page_visual.py
git commit -m "$(cat <<'EOF'
feat(ui): add PluginTrustDialog (Step 2 of install wizard)

Renders parsed manifest snapshot for user review: name+version,
source+short commit, author, description, capability list translated
to human copy (unknown cap strings get "(unrecognized)"). Emits trusted
on Trust&Install; reject closes without firing. The wallet-permissions
warning is always visible.

Refs: #50
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Toolbar Plugins button

**Why now:** Needed before the window can route page changes to the Plugins page from the toolbar.

**Files:**
- Modify: `src/locksmith/ui/toolbar.py` (add signal + button)

- [ ] **Step 1: Inspect the existing toolbar to copy its pattern**

```bash
grep -n "settings_clicked\|home_clicked" src/locksmith/ui/toolbar.py | head -10
```

Use the existing `home_clicked` button pattern as the template — same icon-button + tooltip + signal style.

- [ ] **Step 2: Add `plugins_clicked` signal + button**

Edit `src/locksmith/ui/toolbar.py`. Locate the signals section (where `settings_clicked = Signal()` is declared) and add:

```python
plugins_clicked = Signal()
```

Locate the button creation block where `home_clicked` button is built (search for `home_clicked.emit` or the home icon name). Immediately after that button, add a parallel block — use the same widget style/sizing:

```python
        # Plugins button — opens the top-level Plugins page.
        plugins_button = self._make_icon_button(
            icon_name="extension",  # Material Symbol; verify by checking what other buttons use
            tooltip="Plugins",
            object_name="toolbar_plugins_button",
        )
        plugins_button.clicked.connect(self.plugins_clicked.emit)
        # Add it alongside Home in whichever layout the toolbar uses.
        layout.addWidget(plugins_button)
```

**Note for the implementer:** the exact helper name (`_make_icon_button` above is a placeholder) and the layout variable depend on how toolbar.py is currently structured. Read the surrounding code for `home_clicked` and mirror it precisely. Use a Material Symbol that already exists in `assets/material-icons/` — `extension.svg` is the Material Symbols name for the plugin/extension glyph; verify it's already in the resources via `ls assets/material-icons/ | grep -i extension`. If not present, use any plugin-suggestive icon that IS present (e.g. `device_hub.svg`, `hub.svg`, `schema.svg`).

- [ ] **Step 3: Verify the button is reachable and signals**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -c "
from PySide6.QtWidgets import QApplication
import sys
app = QApplication.instance() or QApplication(sys.argv)
from unittest.mock import MagicMock
from locksmith.ui.toolbar import LocksmithToolbar
tb = LocksmithToolbar(MagicMock(), None)
fired = []
tb.plugins_clicked.connect(lambda: fired.append(1))
btn = tb.findChild(type(tb).__bases__[0], 'toolbar_plugins_button')
print('button found' if btn else 'BUTTON NOT FOUND')
btn.click()
assert fired == [1]
print('signal fired')
"
```

Expected: `button found` followed by `signal fired`. If the button isn't reachable, re-check the objectName and layout.addWidget call.

- [ ] **Step 4: Run the full test suite**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -x --ignore=tests/fixtures
```

Expected: No regressions.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/ui/toolbar.py
git commit -m "$(cat <<'EOF'
feat(ui): add Plugins button to the home toolbar

Mirrors the existing home_clicked pattern: icon button with tooltip,
emits plugins_clicked. Wiring to navigate to Pages.PLUGINS lands in the
window integration task.

Refs: #50
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Window integration (Plugins page registration + app-lifecycle dispatch)

**Why now:** All pieces (page, dialogs, manager, installer, toolbar button) exist. This task wires them together in `LocksmithWindow`.

**Files:**
- Modify: `src/locksmith/ui/window.py`
- Modify: `src/locksmith/core/apping.py` (expose `keri_base` on the app, if not already)

- [ ] **Step 1: Register Pages.PLUGINS in the window's page dict**

Edit `src/locksmith/ui/window.py`. Locate the page-creation block around line 79–81:

```python
        self.pages = {}
        self.pages[Pages.HOME] = HomePage(self)
        self.pages[Pages.VAULT] = VaultPage(self)
```

Replace with:

```python
        from locksmith.ui.plugins.page import PluginsPage
        self.pages = {}
        self.pages[Pages.HOME] = HomePage(self)
        self.pages[Pages.PLUGINS] = PluginsPage(self.app, self)
        self.pages[Pages.VAULT] = VaultPage(self)
```

- [ ] **Step 2: Wire the toolbar Plugins button to navigation**

In `LocksmithWindow.__init__`, after the existing toolbar connections (around line 60–64), add:

```python
        self.toolbar.plugins_clicked.connect(self.on_plugins)
```

Then add the handler method (alongside `on_settings`, `on_home`, etc.):

```python
    def on_plugins(self) -> None:
        self.nav_manager.navigate_to(Pages.PLUGINS)
```

- [ ] **Step 3: Wire the PluginsPage signals to the install flow**

After the page registration (Step 1), inside `__init__`:

```python
        plugins_page = self.pages[Pages.PLUGINS]
        plugins_page.install_clicked.connect(self._open_install_flow)
        plugins_page.uninstall_clicked.connect(self._handle_uninstall)
        plugins_page.exclude_toggled.connect(self._handle_exclude_toggle)
```

Add the handlers as methods on `LocksmithWindow`:

```python
    def _open_install_flow(self) -> None:
        from locksmith.ui.plugins.install_dialog import InstallSourceDialog
        dlg = InstallSourceDialog(self)
        dlg.source_chosen.connect(self._handle_source_chosen)
        dlg.exec()

    def _handle_source_chosen(self, source) -> None:
        from locksmith.plugins.installer import InstallError, PluginInstaller
        from locksmith.ui.plugins.trust_dialog import PluginTrustDialog
        # Pre-fetch into a staging area to read the manifest before the
        # trust dialog appears. The installer's install() method does
        # the same fetch internally; here we replicate the fetch step
        # so we can show the manifest before committing.
        installer = PluginInstaller()
        try:
            record = installer.install(source)
        except InstallError as e:
            self._show_error("Install failed", str(e))
            return
        # Show trust dialog AFTER install completes. Since trust comes
        # post-install in this minimal flow, present a confirmation+undo:
        # if the user clicks Cancel in the trust dialog, uninstall.
        snap = record["manifest_snapshot"]
        dlg = PluginTrustDialog(
            manifest_snapshot=snap,
            source=record["source"],
            commit=record["commit"],
            parent=self,
        )
        dlg.trusted.connect(lambda: self._on_trust_accepted(record["plugin_id"]))
        result = dlg.exec()
        if result != dlg.Accepted:
            try:
                installer.uninstall(record["plugin_id"])
            except InstallError:
                logger.exception("plugin.rollback_failed plugin_id=%s", record["plugin_id"])
        self.pages[Pages.PLUGINS]._refresh()
        self.pages[Pages.PLUGINS].set_restart_required(True)

    def _on_trust_accepted(self, plugin_id: str) -> None:
        logger.info("plugin.trust.accepted plugin_id=%s", plugin_id)
        self.pages[Pages.PLUGINS].set_restart_required(True)

    def _handle_uninstall(self, plugin_id: str) -> None:
        from locksmith.plugins.installer import InstallError, PluginInstaller
        try:
            PluginInstaller().uninstall(plugin_id)
        except InstallError as e:
            self._show_error("Uninstall failed", str(e))
            return
        self.pages[Pages.PLUGINS]._refresh()
        self.pages[Pages.PLUGINS].set_restart_required(True)

    def _handle_exclude_toggle(self, plugin_id: str, now_excluded: bool) -> None:
        from pathlib import Path
        from locksmith.plugins import storage
        keri_base = Path(self.app.config.base or Path.home() / ".keri")
        current = storage.read_enable_list(keri_base)
        excluded = set(current.get("excluded", []))
        if now_excluded:
            excluded.add(plugin_id)
        else:
            excluded.discard(plugin_id)
        storage.write_enable_list(keri_base, {"format": 1, "excluded": sorted(excluded)})
        self.pages[Pages.PLUGINS]._refresh()
        self.pages[Pages.PLUGINS].set_restart_required(True)

    def _show_error(self, title: str, message: str) -> None:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(self, title, message)
```

**Note for the implementer:** the two-step flow as written above is *fetch-then-confirm-with-rollback*. The cleaner UX would be *fetch-into-staging → trust-then-finalize*, which requires a small change in PluginInstaller to expose a `prepare(source) -> record` method that returns without finalizing, and `finalize(record)` / `discard(record)` to commit or undo. If the implementer has bandwidth, do the cleaner split — but if pressed, the rollback approach above works and is shippable. File a follow-up issue for the staging refactor.

- [ ] **Step 4: Replace the legacy plugin discovery call**

Find the line at `src/locksmith/ui/window.py:88`:

```python
        self.app.plugin_manager.discover_and_initialize(vault_page, vault_page.nav_menu)
```

Replace with:

```python
        # Discover plugins from the index + entry-points and call initialize on each.
        self.app.plugin_manager.discover()
        # Register vault-plugin pages and menus into the VaultPage.
        self.app.plugin_manager.discover_and_initialize_vault_ui(
            vault_page, vault_page.nav_menu,
        )
```

- [ ] **Step 5: Call `on_app_started` after the window is fully built**

At the end of `LocksmithWindow.__init__` (after the existing `logger.info("LocksmithHome initialized")` at line 130), add:

```python
        # Run app-lifecycle hooks for any AppPlugin instances loaded above.
        # Done last so plugins see a fully-constructed window.
        self.app.plugin_manager.on_app_started(window=self)
```

- [ ] **Step 6: Wire `on_app_stopping` on close**

Locate the `closeEvent` method in `LocksmithWindow` (or add one if absent). Make it:

```python
    def closeEvent(self, event) -> None:
        try:
            self.app.plugin_manager.on_app_stopping()
        except Exception:
            logger.exception("plugin.on_app_stopping.dispatch_failed")
        super().closeEvent(event)
```

If `closeEvent` already exists, insert the `plugin_manager.on_app_stopping()` call at the very top (before any existing teardown).

- [ ] **Step 7: Run the full test suite**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -x --ignore=tests/fixtures
```

Expected: No regressions. Existing kerifoundation tests still pass because `discover_and_initialize_vault_ui` registers their pages and menus identically.

- [ ] **Step 8: Manual smoke test**

```bash
.venv/bin/python -m locksmith.main
```

Verify:
- The toolbar has a Plugins button.
- Clicking it shows the Plugins page.
- The page lists `kerifoundation` with the `[ in-tree ]` badge.
- The `+ Install plugin` button opens the source dialog.
- Pasting a local path to `tests/fixtures/plugins/echo-app/` and clicking Fetch shows the trust dialog with the echo-app capabilities; clicking Trust&Install adds Echo App to the list and shows the restart banner.
- Quitting and re-launching the wallet still loads kerifoundation; the echo-app plugin appears as Loaded.

If any step doesn't match, fix before committing.

- [ ] **Step 9: Commit**

```bash
git add src/locksmith/ui/window.py
git commit -m "$(cat <<'EOF'
feat(ui): wire Plugins page + app-lifecycle dispatch into LocksmithWindow

Registers Pages.PLUGINS, hooks the toolbar Plugins button to navigation,
and connects PluginsPage signals to the install/uninstall/exclude
flows. Replaces the legacy discover_and_initialize() with the new
two-step PluginManager.discover() + discover_and_initialize_vault_ui()
pair. Calls on_app_started(window=self) after the window finishes
building, and on_app_stopping in closeEvent.

The install flow uses a fetch-then-confirm-with-rollback shape today;
a follow-up should refactor PluginInstaller to expose prepare/finalize
for a cleaner staging-area UX.

Refs: #50
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: Concurrency + integration tests

**Why now:** All code paths exist. Two final test files prove the system behaves correctly under (a) concurrent index writers and (b) a real end-to-end install → restart → load cycle using the in-core dev-control harness as the test driver.

**Files:**
- Create: `tests/test_plugins_concurrency.py`
- Create: `tests/test_plugins_integration.py`

- [ ] **Step 1: Write the concurrency test**

`tests/test_plugins_concurrency.py`:

```python
"""Two PluginInstaller instances writing the index concurrently never corrupt it."""
from __future__ import annotations

import shutil
import threading
from pathlib import Path

import pytest

from locksmith.plugins import storage
from locksmith.plugins.installer import PluginInstaller, SourceDescriptor


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "plugins"


@pytest.fixture
def isolated_root(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    yield tmp_path


def _make_variant(tmp_path: Path, name: str) -> Path:
    """Clone the echo fixture under a new plugin_id so two installs don't collide on duplicate-id."""
    dst = tmp_path / name
    shutil.copytree(FIXTURE_ROOT / "echo-app", dst)
    manifest = dst / "locksmith-plugin.toml"
    content = manifest.read_text(encoding="utf-8")
    content = content.replace('plugin_id = "echo_app"', f'plugin_id = "{name}"')
    content = content.replace(
        'entry_point = "echo_app.plugin:EchoAppPlugin"',
        f'entry_point = "echo_app.plugin:EchoAppPlugin"',  # entry point class still the same
    )
    manifest.write_text(content, encoding="utf-8")
    return dst


def test_two_concurrent_installs_both_appear(isolated_root, tmp_path):
    variant_a = _make_variant(tmp_path / "src", "echo_a")
    variant_b = _make_variant(tmp_path / "src", "echo_b")

    errors: list[Exception] = []

    def install(src: SourceDescriptor):
        try:
            PluginInstaller().install(src)
        except Exception as e:
            errors.append(e)

    threads = [
        threading.Thread(target=install,
                         args=(SourceDescriptor(type="local", path=str(variant_a)),)),
        threading.Thread(target=install,
                         args=(SourceDescriptor(type="local", path=str(variant_b)),)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"installer raised: {errors}"
    idx = storage.read_index()
    pids = {p["plugin_id"] for p in idx["plugins"]}
    assert pids == {"echo_a", "echo_b"}
    # Index is well-formed JSON (already enforced by storage.read_index, but explicit).
    import json
    raw = storage.index_path().read_text(encoding="utf-8")
    json.loads(raw)
```

- [ ] **Step 2: Write the integration test**

`tests/test_plugins_integration.py`:

```python
"""End-to-end: install a local fixture, simulate a restart, verify it loads + hooks fire.

This test does NOT use the wallet's full GUI startup path — it
constructs LocksmithApplication + PluginManager directly to keep the
test hermetic. The in-core dev-control harness (still present in this
branch under src/locksmith/dev_control.py) is what would drive an
actual GUI test; see Task 16's manual checklist for that exercise.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from locksmith.plugins import storage
from locksmith.plugins.installer import PluginInstaller, SourceDescriptor
from locksmith.plugins.manager import PluginManager


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "plugins"


@pytest.fixture
def isolated_root(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    if "echo_app" in sys.modules:
        del sys.modules["echo_app"]
    yield tmp_path
    if "echo_app" in sys.modules:
        del sys.modules["echo_app"]


def test_install_restart_load_lifecycle(isolated_root, caplog):
    keri_base = isolated_root / "keri"
    fake_app = MagicMock()

    # 1. Install.
    PluginInstaller().install(
        SourceDescriptor(type="local", path=str(FIXTURE_ROOT / "echo-app")),
    )

    # 2. Simulate a restart: fresh PluginManager.
    mgr = PluginManager(fake_app, keri_base=keri_base)

    # 3. Discover + initialize.
    with caplog.at_level("INFO"):
        mgr.discover()
    assert "echo_app" in mgr.loaded_ids()
    state = mgr.get_state("echo_app")
    assert state.status == "loaded"
    assert any(
        "plugin.initialize plugin_id=echo_app" in rec.getMessage()
        for rec in caplog.records
    )

    # 4. on_app_started fires the AppPlugin hook + service.start.
    caplog.clear()
    with caplog.at_level("INFO"):
        mgr.on_app_started(window=MagicMock())
    msgs = [rec.getMessage() for rec in caplog.records]
    assert any("on_app_started plugin_id=echo_app" in m for m in msgs)
    assert any("service.started plugin_id=echo_app" in m for m in msgs)

    # 5. on_app_stopping reverses in expected order.
    caplog.clear()
    with caplog.at_level("INFO"):
        mgr.on_app_stopping()
    msgs = [rec.getMessage() for rec in caplog.records]
    # Service stop comes before on_app_stopping for the same plugin (per spec).
    stop_idx = next(i for i, m in enumerate(msgs) if "service.stopped plugin_id=echo_app" in m)
    hook_idx = next(i for i, m in enumerate(msgs) if "on_app_stopping plugin_id=echo_app" in m)
    assert stop_idx < hook_idx


def test_uninstall_then_restart_omits_plugin(isolated_root):
    fake_app = MagicMock()
    inst = PluginInstaller()
    inst.install(SourceDescriptor(type="local", path=str(FIXTURE_ROOT / "echo-app")))
    inst.uninstall("echo_app")
    mgr = PluginManager(fake_app, keri_base=isolated_root / "keri")
    mgr.discover()
    assert "echo_app" not in mgr.loaded_ids()


def test_exclude_then_restart_skips_plugin(isolated_root):
    fake_app = MagicMock()
    keri_base = isolated_root / "keri"
    PluginInstaller().install(
        SourceDescriptor(type="local", path=str(FIXTURE_ROOT / "echo-app")),
    )
    storage.write_enable_list(keri_base, {"format": 1, "excluded": ["echo_app"]})
    mgr = PluginManager(fake_app, keri_base=keri_base)
    mgr.discover()
    assert "echo_app" not in mgr.loaded_ids()
    assert "echo_app" in mgr.excluded_ids()
```

- [ ] **Step 3: Run both new test files**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_plugins_concurrency.py tests/test_plugins_integration.py -v
```

Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_plugins_concurrency.py tests/test_plugins_integration.py
git commit -m "$(cat <<'EOF'
test(plugins): concurrency + end-to-end install/restart/load coverage

Concurrency: two installer threads writing the index in parallel both
land their entries without corrupting the file. Integration: install →
fresh PluginManager → discover → on_app_started → on_app_stopping
exercises the full lifecycle and asserts against the structured log
lines emitted at each transition. Uninstall + exclude flows also
covered.

Refs: #50
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 15: Plugin authoring docs (`docs/plugin-authoring.md`)

**Why now:** Last task before the CI gate. Future plugin authors (starting with the dev-control plugin in Stage 2) need a single document that tells them: what's in a manifest, what the contract looks like, how to test their plugin.

**Files:**
- Create: `docs/plugin-authoring.md`

- [ ] **Step 1: Write the doc**

`docs/plugin-authoring.md`:

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add docs/plugin-authoring.md
git commit -m "$(cat <<'EOF'
docs(plugins): add plugin authoring guide

Companion to the design spec, from the author's-eye view: manifest
fields, which base class to use, AppPlugin example matching the test
fixture, install flow, testing conventions, and the v1 'cannot do'
list.

Refs: #50
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 16: Final regression gate + push

**Why now:** All code is in; this is the explicit CI-gate moment.

- [ ] **Step 1: Run the full test suite**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest --ignore=tests/fixtures -v
```

Expected: All tests pass, including every existing `test_kerifoundation_*` file.

- [ ] **Step 2: Manual smoke walkthrough**

Boot the wallet:

```bash
.venv/bin/python -m locksmith.main
```

Walk through:

1. Toolbar Plugins button is present. Click it → Plugins page renders.
2. kerifoundation appears with `[ in-tree ]` badge and Loaded status.
3. `+ Install plugin` → source dialog. Try `acme/totally-nonexistent` (Fetch should produce a clone failure error). Cancel.
4. `+ Install plugin` → switch to Local path, point at `tests/fixtures/plugins/echo-app/`. Fetch. Trust dialog appears with Echo App, the capability bullet for `app.service`, and the wallet-permissions warning.
5. Click Trust&Install. Echo App appears in the list as Loaded. Restart-required banner shows.
6. Click Exclude on this wallet on Echo App → banner stays, row says Excluded after refresh.
7. Quit the wallet and re-launch. Echo App is in the list but not loaded (excluded). Click Include on this wallet, restart again, Echo App loads (check log for `plugin.on_app_started plugin_id=echo_app`).
8. Uninstall Echo App. Confirm. Restart. Echo App is gone.

If any step doesn't work, fix before pushing.

- [ ] **Step 3: Push the branch**

```bash
git push origin pr/dev-control-harness
```

- [ ] **Step 4: Update GitHub issue #50 status**

```bash
gh issue comment 50 -R keri-foundation/locksmith --body "$(cat <<'EOF'
Stage 1 implementation landed on `pr/dev-control-harness` (commits 2feeef2..HEAD).

- Contract restructure: ✓ (PluginCore + AppPlugin + VaultPlugin)
- Kerifoundation migration: ✓ (no behavior change)
- Manifest parser + storage helpers: ✓
- PluginInstaller (local + github sources): ✓
- PluginManager rewrite (index discovery + typed dispatch): ✓
- PluginsPage + Install/Trust dialogs + Toolbar button: ✓
- Window app-lifecycle wiring: ✓
- Concurrency + integration tests: ✓
- Plugin authoring docs at docs/plugin-authoring.md: ✓
- Full test suite green: ✓

Stage 2 (dev-control as a plugin + closing PR #48) is the next cycle.
EOF
)"
```

---

## Self-review checklist

Before declaring this plan complete, run through:

**Spec coverage:**

| Spec section | Task that implements it |
|---|---|
| A.1 Contract restructure | Tasks 2 + 3 |
| A.2 Loader rewrite | Task 7 |
| A.3 Installer | Tasks 5 + 6 |
| A.4 Plugins page | Tasks 8 + 9 + 10 + 11 |
| A.5 Window/app integration | Tasks 12 + 13 |
| B Plugin contract | Task 2 |
| C Manifest format | Task 4 |
| D Storage layout | Task 5 |
| E UI flow | Tasks 9 + 10 + 11 + 13 |
| F Failure modes | Tasks 6 (install failures) + 7 (load failures) + 9 (UI states) |
| G Test plan — unit | Tasks 2, 3, 4, 5, 6, 7 |
| G Test plan — visual | Tasks 9, 10, 11 |
| G Test plan — concurrency | Task 14 |
| G Test plan — integration | Task 14 |
| G Test plan — bootstrap caveat | Task 16 manual step using current in-core harness |
| H Stage 2 preview | (not implemented in Stage 1) |
| I Scope cuts | All — none of the cut items have tasks |

No spec section is left without coverage. Stage 2 preview is intentionally not a task; it's the next cycle's plan.

**Known caveats / follow-ups:**

- Task 13 implements the install flow as fetch-then-confirm-with-rollback because the staging-area split was deferred. File a follow-up issue if not done before Stage 2 starts.
- `requires_locksmith` is parsed but always returns True (Task 7 `_compat_ok`). Add real version-range matching once Locksmith starts shipping versioned releases. Trivial follow-up.
- Plugin Python deps are explicitly out of scope (spec Section I). If kerifoundation or future plugins start needing extra deps, design a vendoring or per-plugin venv shim in a follow-up cycle.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-16-locksmith-plugin-loader-stage1.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Uses superpowers:subagent-driven-development.

**2. Inline Execution** — Execute tasks in this session using superpowers:executing-plans, batch execution with checkpoints.

Which approach?
