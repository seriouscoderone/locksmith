# Designer Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship v1 of the `Micro App: Designer` Locksmith plugin — a Templates browser plus Overview plus 8 per-primitive editors plus validation/JSON/cross-ref surfaces — backed by file-on-disk storage and a per-vault LMDB index.

**Architecture:** Plugin under `src/locksmith/plugins/designer/` following the `ecosystem_viewer` shape. Reuses `locksmith.micro_app_template` for validation, saidification, and canonical JSON. Tail dir `keri/dgnr` for plugin storage. Visual editors are projections of a single in-memory JSON model; JSON source view is two-way bound.

**Tech Stack:** PySide6, Qt signals, `hio` (none in v1 — no Doers), `jsonschema`, keripy `Saider`, locksmith's `LMDBer`/`koming.Komer` for plugin storage.

**Spec it implements:** `docs/superpowers/specs/2026-05-12-designer-plugin.md`.

---

## File Structure

**New files (under `src/locksmith/plugins/designer/`):**

```
__init__.py                              # package marker, docstring
plugin.py                                # DesignerPlugin(PluginBase)
keys.py                                  # PAGE_KEY_* constants
store.py                                 # File I/O: read/write/list templates
db.py                                    # DesignerBaser (LMDB index)
validation.py                            # Adapter over locksmith.micro_app_template.validate
crossref.py                              # Reverse-direction "used by" index
model.py                                 # TemplateModel (QObject with change signals)
dialogs.py                               # CreateTemplateDialog, EditRoleDialog, EditHeaderDialog, ConfirmDeleteDialog
widgets/__init__.py
widgets/kind_rail.py                     # Left-rail list with kind-color dots
widgets/first_person_card.py             # Card on the Overview grid
widgets/cross_ref_chip.py                # "Used by" navigable chip
widgets/validation_badge.py              # Inline error/warning badge
widgets/validation_panel.py              # Togglable side panel
widgets/json_source_view.py              # Two-way bound JSON editor
widgets/state_machine_diagram.py         # TEL state-machine SVG (Exports)
widgets/swimlane_diagram.py              # Self-vs-counterparty SVG (Workflows)
widgets/primitive_editor_shell.py        # Shared shell: rail + identity + right pane
editors/__init__.py
editors/templates_browser.py             # TemplatesBrowserPage
editors/overview.py                      # TemplateOverviewPage
editors/commands.py                      # CommandsEditorPage
editors/aggregates.py                    # AggregatesEditorPage
editors/reactions.py                     # ReactionsEditorPage
editors/workflows.py                     # WorkflowsEditorPage
editors/projections.py                   # ProjectionsEditorPage
editors/rules.py                         # RulesEditorPage
editors/imports.py                       # ImportsEditorPage
editors/exports.py                       # ExportsEditorPage
README.md
```

**Modified files:**

```
pyproject.toml                           # Add designer = "..." entry point
```

**New test files (under `tests/plugins/designer/`):**

```
__init__.py
conftest.py                              # qapp + tmp_designer_dir fixtures
fixtures/regulator-grants-carrier-license.json
fixtures/carrier-license-application.json
fixtures/broken-references.json
fixtures/draft-untitled.json
test_store.py
test_db.py
test_validation.py
test_crossref.py
test_model.py
test_plugin_lifecycle.py
test_templates_browser_visual.py
test_overview_visual.py
test_commands_editor_visual.py
test_aggregates_editor_visual.py
test_reactions_editor_visual.py
test_workflows_editor_visual.py
test_projections_editor_visual.py
test_rules_editor_visual.py
test_imports_editor_visual.py
test_exports_editor_visual.py
test_validation_panel_visual.py
test_json_source_view.py
```

---

## Task 1: Plugin skeleton and page-key constants

**Files:**
- Create: `src/locksmith/plugins/designer/__init__.py`
- Create: `src/locksmith/plugins/designer/keys.py`
- Create: `src/locksmith/plugins/designer/plugin.py`
- Modify: `pyproject.toml` (entry-point registration)
- Test: `tests/plugins/designer/__init__.py`
- Test: `tests/plugins/designer/test_plugin_lifecycle.py`

- [ ] **Step 1: Create the package marker**

Write `src/locksmith/plugins/designer/__init__.py`:

```python
# -*- encoding: utf-8 -*-
"""
locksmith.plugins.designer package

Micro App: Designer — direct-manipulation authoring UI for
micro-app-template.json artifacts. See README.md for design rationale.
"""
```

- [ ] **Step 2: Define page-key constants**

Write `src/locksmith/plugins/designer/keys.py`:

```python
# -*- encoding: utf-8 -*-
"""Stable page-key constants for the Designer plugin.

These keys are registered into VaultPage.content_stack and used to
navigate between Designer surfaces. Keeping them in a single module
avoids string drift across pages, plugin lifecycle, and tests.
"""
from __future__ import annotations

PAGE_KEY_TEMPLATES_BROWSER = "designer.templates"
PAGE_KEY_OVERVIEW = "designer.overview"
PAGE_KEY_COMMANDS = "designer.commands"
PAGE_KEY_AGGREGATES = "designer.aggregates"
PAGE_KEY_REACTIONS = "designer.reactions"
PAGE_KEY_WORKFLOWS = "designer.workflows"
PAGE_KEY_PROJECTIONS = "designer.projections"
PAGE_KEY_RULES = "designer.rules"
PAGE_KEY_IMPORTS = "designer.imports"
PAGE_KEY_EXPORTS = "designer.exports"

ALL_PAGE_KEYS: tuple[str, ...] = (
    PAGE_KEY_TEMPLATES_BROWSER,
    PAGE_KEY_OVERVIEW,
    PAGE_KEY_COMMANDS,
    PAGE_KEY_AGGREGATES,
    PAGE_KEY_REACTIONS,
    PAGE_KEY_WORKFLOWS,
    PAGE_KEY_PROJECTIONS,
    PAGE_KEY_RULES,
    PAGE_KEY_IMPORTS,
    PAGE_KEY_EXPORTS,
)

PRIMITIVE_PAGE_KEY: dict[str, str] = {
    "commands": PAGE_KEY_COMMANDS,
    "aggregates": PAGE_KEY_AGGREGATES,
    "reactions": PAGE_KEY_REACTIONS,
    "workflows": PAGE_KEY_WORKFLOWS,
    "projections": PAGE_KEY_PROJECTIONS,
    "rules": PAGE_KEY_RULES,
    "imports": PAGE_KEY_IMPORTS,
    "exports": PAGE_KEY_EXPORTS,
}
```

- [ ] **Step 3: Write the plugin lifecycle test (RED)**

Write `tests/plugins/designer/__init__.py` (empty file).

Write `tests/plugins/designer/test_plugin_lifecycle.py`:

```python
# -*- encoding: utf-8 -*-
"""Lifecycle smoke tests for DesignerPlugin."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from locksmith.plugins.designer.plugin import DesignerPlugin
from locksmith.plugins.designer.keys import ALL_PAGE_KEYS


def test_plugin_id_is_designer(qapp):
    plugin = DesignerPlugin()
    assert plugin.plugin_id == "designer"


def test_get_pages_returns_all_page_keys(qapp):
    # initialize requires an app-like object; pass a stub
    class _App:
        pass

    plugin = DesignerPlugin()
    plugin.initialize(_App())
    pages = plugin.get_pages()
    for key in ALL_PAGE_KEYS:
        assert key in pages, f"Page {key} not registered"
```

- [ ] **Step 4: Run test, verify it fails**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_plugin_lifecycle.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'locksmith.plugins.designer.plugin'`

- [ ] **Step 5: Implement DesignerPlugin skeleton**

Write `src/locksmith/plugins/designer/plugin.py`:

```python
# -*- encoding: utf-8 -*-
"""
locksmith.plugins.designer.plugin module

DesignerPlugin — Locksmith plugin that registers the Micro App: Designer
sidebar entry and its 10 pages (Templates browser, Overview, 8 per-
primitive editors). See README.md for design.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget
from keri import help

from locksmith.plugins.base import PluginBase
from locksmith.plugins.designer.keys import (
    PAGE_KEY_TEMPLATES_BROWSER,
    PAGE_KEY_OVERVIEW,
    PAGE_KEY_COMMANDS,
    PAGE_KEY_AGGREGATES,
    PAGE_KEY_REACTIONS,
    PAGE_KEY_WORKFLOWS,
    PAGE_KEY_PROJECTIONS,
    PAGE_KEY_RULES,
    PAGE_KEY_IMPORTS,
    PAGE_KEY_EXPORTS,
)
from locksmith.ui.toolkit.widgets.buttons import BackButton
from locksmith.ui.vault.menu import MenuButton, MenuSpacer

logger = help.ogler.getLogger(__name__)


class DesignerPlugin(PluginBase):
    """Direct-manipulation authoring plugin for micro-app templates."""

    @property
    def plugin_id(self) -> str:
        return "designer"

    def initialize(self, app: Any) -> None:
        self._app = app
        self._db = None
        self._pages: dict[str, QWidget] = {}
        # Page widgets created lazily in subsequent tasks. For task 1
        # we register stub QWidgets so get_pages() returns the full key
        # set and downstream wiring tests can run.
        for key in (
            PAGE_KEY_TEMPLATES_BROWSER,
            PAGE_KEY_OVERVIEW,
            PAGE_KEY_COMMANDS,
            PAGE_KEY_AGGREGATES,
            PAGE_KEY_REACTIONS,
            PAGE_KEY_WORKFLOWS,
            PAGE_KEY_PROJECTIONS,
            PAGE_KEY_RULES,
            PAGE_KEY_IMPORTS,
            PAGE_KEY_EXPORTS,
        ):
            self._pages[key] = QWidget()
        logger.info("DesignerPlugin initialized (skeleton)")

    def on_vault_opened(self, vault: Any) -> None:
        # DB + page wiring filled in by subsequent tasks.
        pass

    def on_vault_closed(self, vault: Any, *, clear: bool = False) -> None:
        pass

    def get_menu_entry(self) -> MenuButton:
        return MenuButton(
            icon=QIcon(":/assets/material-icons/drafts.svg"),
            label="Micro App Designer",
        )

    def get_menu_section(self) -> list[QWidget]:
        items: list[QWidget] = [BackButton(dark_mode=False), MenuSpacer(15)]
        items.append(MenuButton(
            icon=QIcon(":/assets/material-icons/drafts.svg"),
            label="Templates",
        ))
        return items

    def get_pages(self) -> dict[str, QWidget]:
        return dict(self._pages)
```

- [ ] **Step 6: Register entry point in pyproject.toml**

Add line under `[project.entry-points."locksmith.plugins"]`:

```toml
designer = "locksmith.plugins.designer.plugin:DesignerPlugin"
```

- [ ] **Step 7: Re-install the package so entry point registers**

Run: `python -m pip install -e .`
Expected: `Successfully installed locksmith-...`

- [ ] **Step 8: Run test, verify it passes**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_plugin_lifecycle.py -v`
Expected: PASS (2 tests)

- [ ] **Step 9: Commit**

```bash
git add src/locksmith/plugins/designer/__init__.py \
        src/locksmith/plugins/designer/keys.py \
        src/locksmith/plugins/designer/plugin.py \
        pyproject.toml \
        tests/plugins/designer/__init__.py \
        tests/plugins/designer/test_plugin_lifecycle.py
git commit -m "feat(designer): plugin skeleton + page-key constants

Registers DesignerPlugin entry point, stable PAGE_KEY constants for the
10 surfaces, and a lifecycle smoke test that asserts every key is in
get_pages()."
```

---

## Task 2: File-on-disk template store

**Files:**
- Create: `src/locksmith/plugins/designer/store.py`
- Test: `tests/plugins/designer/test_store.py`

- [ ] **Step 1: Write the failing tests (RED)**

Write `tests/plugins/designer/test_store.py`:

```python
# -*- encoding: utf-8 -*-
"""TemplateStore: file-on-disk read/write/list for micro-app templates."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from locksmith.plugins.designer.store import (
    TemplateStore,
    TemplateRef,
    TemplateNotFound,
    TemplateAlreadyExists,
)


VALID_FIXTURE = {
    "d": "E" + "A" * 43,
    "spec_version": "micro-app-template/0.1",
    "header": {"label": "Test Template", "description": "test", "version": "1.0"},
    "role": {"id": "r1", "name": "tester", "kind": "individual"},
    "credentials": {"imports": [], "exports": []},
    "commands": [],
    "aggregates": [],
    "reactions": [],
    "workflows": [],
    "projections": [],
    "rules": [],
}

VALID_METADATA = {"ecosystems": [], "tags": [], "notes": ""}


@pytest.fixture
def store(tmp_path):
    return TemplateStore(root=tmp_path)


def test_list_empty_workspace(store):
    assert store.list_templates() == []


def test_save_and_load_draft(store):
    ref = store.save_draft(local_id="abc-123", doc=VALID_FIXTURE, metadata=VALID_METADATA)
    assert ref.kind == "draft"
    assert ref.local_id == "abc-123"
    listed = store.list_templates()
    assert len(listed) == 1
    assert listed[0].local_id == "abc-123"

    loaded_doc, loaded_meta = store.load(ref)
    assert loaded_doc["header"]["label"] == "Test Template"
    assert loaded_meta == VALID_METADATA


def test_save_registered_uses_said_as_dir(store):
    said = VALID_FIXTURE["d"]
    ref = store.save_registered(said=said, doc=VALID_FIXTURE, metadata=VALID_METADATA)
    assert ref.kind == "registered"
    assert ref.said == said
    target = store.root / "templates" / "registered" / said / "micro-app-template.json"
    assert target.exists()
    assert json.loads(target.read_text())["d"] == said


def test_load_missing_raises(store):
    ref = TemplateRef(kind="draft", local_id="does-not-exist", said=None)
    with pytest.raises(TemplateNotFound):
        store.load(ref)


def test_save_registered_twice_raises(store):
    said = VALID_FIXTURE["d"]
    store.save_registered(said=said, doc=VALID_FIXTURE, metadata=VALID_METADATA)
    with pytest.raises(TemplateAlreadyExists):
        store.save_registered(said=said, doc=VALID_FIXTURE, metadata=VALID_METADATA)


def test_save_registered_with_overwrite(store):
    said = VALID_FIXTURE["d"]
    store.save_registered(said=said, doc=VALID_FIXTURE, metadata=VALID_METADATA)
    updated = {**VALID_FIXTURE, "header": {**VALID_FIXTURE["header"], "label": "Updated"}}
    ref = store.save_registered(said=said, doc=updated, metadata=VALID_METADATA, overwrite=True)
    loaded_doc, _ = store.load(ref)
    assert loaded_doc["header"]["label"] == "Updated"


def test_promote_draft_to_registered(store):
    draft_ref = store.save_draft(local_id="d1", doc=VALID_FIXTURE, metadata=VALID_METADATA)
    promoted = store.promote_to_registered(draft_ref, said=VALID_FIXTURE["d"])
    assert promoted.kind == "registered"
    assert (store.root / "templates" / "drafts" / "d1").exists() is False
    assert (store.root / "templates" / "registered" / VALID_FIXTURE["d"]).exists()


def test_delete_draft(store):
    ref = store.save_draft(local_id="d1", doc=VALID_FIXTURE, metadata=VALID_METADATA)
    store.delete(ref)
    assert store.list_templates() == []


def test_list_returns_drafts_and_registered(store):
    store.save_draft(local_id="d1", doc=VALID_FIXTURE, metadata=VALID_METADATA)
    store.save_registered(said=VALID_FIXTURE["d"], doc=VALID_FIXTURE, metadata=VALID_METADATA)
    refs = store.list_templates()
    kinds = {r.kind for r in refs}
    assert kinds == {"draft", "registered"}
```

- [ ] **Step 2: Run test, verify RED**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'locksmith.plugins.designer.store'`

- [ ] **Step 3: Implement TemplateStore**

Write `src/locksmith/plugins/designer/store.py`:

```python
# -*- encoding: utf-8 -*-
"""File-on-disk template store for the Designer plugin.

Layout under `root`:

    root/templates/registered/<SAID>/{micro-app-template.json, metadata.json}
    root/templates/drafts/<local-id>/{micro-app-template.json, metadata.json}

`root` is set by the plugin to the canonical tail dir (keri/dgnr) or a
test temporary directory. The store treats both subdirs as shared
across vaults; vault-specific concerns live in DesignerBaser.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

TEMPLATE_FILENAME = "micro-app-template.json"
METADATA_FILENAME = "metadata.json"


class TemplateNotFound(Exception):
    """Raised when a ref does not resolve to an on-disk directory."""


class TemplateAlreadyExists(Exception):
    """Raised when saving registered without overwrite and dir exists."""


@dataclass(frozen=True)
class TemplateRef:
    """Locator for a template on disk.

    Exactly one of (local_id, said) is set, matching `kind`.
    """
    kind: Literal["draft", "registered"]
    local_id: str | None
    said: str | None


class TemplateStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    @property
    def _templates_dir(self) -> Path:
        return self.root / "templates"

    @property
    def _registered_dir(self) -> Path:
        return self._templates_dir / "registered"

    @property
    def _drafts_dir(self) -> Path:
        return self._templates_dir / "drafts"

    def _ref_dir(self, ref: TemplateRef) -> Path:
        if ref.kind == "registered":
            assert ref.said is not None
            return self._registered_dir / ref.said
        assert ref.local_id is not None
        return self._drafts_dir / ref.local_id

    def list_templates(self) -> list[TemplateRef]:
        refs: list[TemplateRef] = []
        if self._registered_dir.exists():
            for child in sorted(self._registered_dir.iterdir()):
                if child.is_dir() and (child / TEMPLATE_FILENAME).exists():
                    refs.append(TemplateRef(
                        kind="registered", local_id=None, said=child.name,
                    ))
        if self._drafts_dir.exists():
            for child in sorted(self._drafts_dir.iterdir()):
                if child.is_dir() and (child / TEMPLATE_FILENAME).exists():
                    refs.append(TemplateRef(
                        kind="draft", local_id=child.name, said=None,
                    ))
        return refs

    def load(self, ref: TemplateRef) -> tuple[dict[str, Any], dict[str, Any]]:
        dir_path = self._ref_dir(ref)
        if not dir_path.exists():
            raise TemplateNotFound(f"No template at {dir_path}")
        doc_path = dir_path / TEMPLATE_FILENAME
        meta_path = dir_path / METADATA_FILENAME
        if not doc_path.exists():
            raise TemplateNotFound(f"No {TEMPLATE_FILENAME} at {dir_path}")
        doc = json.loads(doc_path.read_text())
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        return doc, meta

    def save_draft(
        self, *, local_id: str, doc: dict[str, Any], metadata: dict[str, Any],
    ) -> TemplateRef:
        ref = TemplateRef(kind="draft", local_id=local_id, said=None)
        dir_path = self._ref_dir(ref)
        dir_path.mkdir(parents=True, exist_ok=True)
        (dir_path / TEMPLATE_FILENAME).write_text(
            json.dumps(doc, indent=2, sort_keys=True)
        )
        (dir_path / METADATA_FILENAME).write_text(
            json.dumps(metadata, indent=2, sort_keys=True)
        )
        return ref

    def save_registered(
        self, *, said: str, doc: dict[str, Any], metadata: dict[str, Any],
        overwrite: bool = False,
    ) -> TemplateRef:
        ref = TemplateRef(kind="registered", local_id=None, said=said)
        dir_path = self._ref_dir(ref)
        if dir_path.exists() and not overwrite:
            raise TemplateAlreadyExists(f"Already at {dir_path}")
        dir_path.mkdir(parents=True, exist_ok=True)
        (dir_path / TEMPLATE_FILENAME).write_text(
            json.dumps(doc, indent=2, sort_keys=True)
        )
        (dir_path / METADATA_FILENAME).write_text(
            json.dumps(metadata, indent=2, sort_keys=True)
        )
        return ref

    def promote_to_registered(
        self, draft_ref: TemplateRef, *, said: str,
    ) -> TemplateRef:
        if draft_ref.kind != "draft":
            raise ValueError(f"Expected draft ref, got {draft_ref.kind}")
        doc, meta = self.load(draft_ref)
        doc = {**doc, "d": said}
        self.save_registered(said=said, doc=doc, metadata=meta, overwrite=True)
        shutil.rmtree(self._ref_dir(draft_ref))
        return TemplateRef(kind="registered", local_id=None, said=said)

    def delete(self, ref: TemplateRef) -> None:
        dir_path = self._ref_dir(ref)
        if dir_path.exists():
            shutil.rmtree(dir_path)
```

- [ ] **Step 4: Run test, verify GREEN**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_store.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/store.py tests/plugins/designer/test_store.py
git commit -m "feat(designer): file-on-disk template store

TemplateStore reads, writes, lists, promotes, and deletes
micro-app-template.json + metadata.json pairs under
<root>/templates/{registered/<SAID>, drafts/<local-id>}/. Both subtrees
are shared across vaults; vault-specific concerns live in
DesignerBaser."
```

---

## Task 3: DesignerBaser LMDB index

**Files:**
- Create: `src/locksmith/plugins/designer/db.py`
- Test: `tests/plugins/designer/test_db.py`

- [ ] **Step 1: Write the failing tests (RED)**

Write `tests/plugins/designer/test_db.py`:

```python
# -*- encoding: utf-8 -*-
"""DesignerBaser: per-vault LMDB index for the Designer plugin."""
from __future__ import annotations

import pytest

from locksmith.plugins.designer.db import (
    DesignerBaser,
    TemplateIndexRecord,
    OpenStateRecord,
)


@pytest.fixture
def db(tmp_path):
    db = DesignerBaser(
        name="designer-test",
        headDirPath=str(tmp_path),
        reopen=True,
    )
    yield db
    db.close()


def test_put_and_get_index_record(db):
    rec = TemplateIndexRecord(
        ref_key="draft:abc-123",
        kind="draft",
        label="My Template",
        role_kind="individual",
        validation_summary="valid",
        modified_at="2026-05-12T10:00:00Z",
        source="manual",
    )
    db.put_index(rec)
    got = db.get_index("draft:abc-123")
    assert got is not None
    assert got.label == "My Template"
    assert got.kind == "draft"


def test_list_index_records(db):
    db.put_index(TemplateIndexRecord(
        ref_key="draft:a", kind="draft", label="A", role_kind="individual",
        validation_summary="valid", modified_at="2026-05-12T10:00:00Z",
        source="manual",
    ))
    db.put_index(TemplateIndexRecord(
        ref_key="registered:E" + "A" * 43, kind="registered", label="B",
        role_kind="organization", validation_summary="valid",
        modified_at="2026-05-12T11:00:00Z", source="manual",
    ))
    recs = db.list_index()
    assert len(recs) == 2


def test_delete_index_record(db):
    db.put_index(TemplateIndexRecord(
        ref_key="draft:x", kind="draft", label="X", role_kind="individual",
        validation_summary="valid", modified_at="2026-05-12T10:00:00Z",
        source="manual",
    ))
    db.delete_index("draft:x")
    assert db.get_index("draft:x") is None


def test_open_state_round_trip(db):
    db.put_open_state(OpenStateRecord(
        last_opened_ref_key="draft:abc",
        last_opened_at="2026-05-12T10:00:00Z",
    ))
    got = db.get_open_state()
    assert got is not None
    assert got.last_opened_ref_key == "draft:abc"


def test_get_open_state_when_unset(db):
    assert db.get_open_state() is None
```

- [ ] **Step 2: Run test, verify RED**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'locksmith.plugins.designer.db'`

- [ ] **Step 3: Implement DesignerBaser**

Write `src/locksmith/plugins/designer/db.py`:

```python
# -*- encoding: utf-8 -*-
"""DesignerBaser: per-vault LMDB index for the Designer plugin.

Stores fast-lookup metadata about templates the user has interacted with
in this vault. Source of truth for templates themselves is the on-disk
files under TemplateStore. This is purely an index + open-state cache.

Modeled on EcosystemBaser (ecosystem_viewer/db.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from keri.db import dbing, koming


@dataclass
class TemplateIndexRecord:
    """Cached metadata about one template the user has interacted with.

    `ref_key` is a unique key: "draft:<local-id>" or "registered:<SAID>".
    All other fields are display-cache derived from the on-disk file at
    plugin startup or save time.
    """
    ref_key: str = ""
    kind: str = "draft"  # "draft" | "registered"
    label: str = ""
    role_kind: str = ""  # "individual" | "organization" | "system" | ...
    validation_summary: str = "unknown"  # "valid" | "errors" | "warnings"
    modified_at: str = ""  # ISO-8601 UTC
    source: str = "manual"  # "manual" | "imported_file" | "imported_oobi"


@dataclass
class OpenStateRecord:
    """Last-opened template for resume-on-launch.

    Singleton: stored under the constant key ("_open_state",).
    """
    last_opened_ref_key: str = ""
    last_opened_at: str = ""


_OPEN_STATE_KEY = ("_open_state",)


class DesignerBaser(dbing.LMDBer):
    """LMDB database for the Designer plugin."""

    TailDirPath = "keri/dgnr"
    AltTailDirPath = ".keri/dgnr"
    TempPrefix = "dgnr"

    def __init__(
        self,
        name: str = "designer",
        headDirPath: str | None = None,
        reopen: bool = True,
        **kwa,
    ):
        self.index = None
        self.open_state = None
        super().__init__(name=name, headDirPath=headDirPath, reopen=reopen, **kwa)

    def reopen(self, **kwa):
        super().reopen(**kwa)
        self.index = koming.Komer(
            db=self, subkey='idx.', schema=TemplateIndexRecord,
        )
        self.open_state = koming.Komer(
            db=self, subkey='ops.', schema=OpenStateRecord,
        )
        return self.env

    def put_index(self, rec: TemplateIndexRecord) -> None:
        if not rec.ref_key:
            raise ValueError("TemplateIndexRecord.ref_key is required")
        self.index.pin(keys=(rec.ref_key,), val=rec)

    def get_index(self, ref_key: str) -> TemplateIndexRecord | None:
        return self.index.get(keys=(ref_key,))

    def list_index(self) -> list[TemplateIndexRecord]:
        return [val for (_keys, val) in self.index.getItemIter()]

    def delete_index(self, ref_key: str) -> None:
        self.index.rem(keys=(ref_key,))

    def put_open_state(self, rec: OpenStateRecord) -> None:
        self.open_state.pin(keys=_OPEN_STATE_KEY, val=rec)

    def get_open_state(self) -> OpenStateRecord | None:
        return self.open_state.get(keys=_OPEN_STATE_KEY)
```

- [ ] **Step 4: Run test, verify GREEN**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_db.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/db.py tests/plugins/designer/test_db.py
git commit -m "feat(designer): per-vault LMDB index store

DesignerBaser (TailDirPath keri/dgnr) caches template metadata for fast
Templates-browser rendering and remembers the last-opened template for
resume-on-launch. Index is rebuildable from disk; loss of the LMDB
does not lose data."
```

---

## Task 4: Validation adapter

**Files:**
- Create: `src/locksmith/plugins/designer/validation.py`
- Test: `tests/plugins/designer/test_validation.py`

The Designer's validation surface needs `ValidationIssue` records that carry a `surface` field (which editor should display them) and a normalized JSON-pointer `path`. The existing `locksmith.micro_app_template.validate` returns `ValidationError` with a slash-or-dot path string and no surface. This adapter wraps it, normalizes paths to JSON-pointer form, and derives the surface from the path prefix.

- [ ] **Step 1: Write the failing tests (RED)**

Write `tests/plugins/designer/test_validation.py`:

```python
# -*- encoding: utf-8 -*-
"""Validation adapter: wraps locksmith.micro_app_template.validate."""
from __future__ import annotations

from pathlib import Path

import pytest

from locksmith.plugins.designer.validation import (
    ValidationEngine,
    ValidationIssue,
    ValidationReport,
    surface_from_path,
)

META_SCHEMA = (
    Path(__file__).resolve().parents[2]
    / "docs" / "superpowers" / "specs" / "schemas"
    / "micro-app-template.schema.json"
)


VALID_FIXTURE = {
    "d": "E" + "A" * 43,
    "spec_version": "micro-app-template/0.1",
    "header": {"label": "Test", "description": "", "version": "1.0"},
    "role": {"id": "r1", "name": "tester", "kind": "individual"},
    "credentials": {"imports": [], "exports": []},
    "commands": [],
    "aggregates": [],
    "reactions": [],
    "workflows": [],
    "projections": [],
    "rules": [],
}


def test_surface_from_path_covers_all_primitives():
    assert surface_from_path("/commands/0/inputs") == "commands"
    assert surface_from_path("/credentials/imports/0") == "imports"
    assert surface_from_path("/credentials/exports/2/lifecycle") == "exports"
    assert surface_from_path("/workflows/1/steps") == "workflows"
    assert surface_from_path("/projections/0") == "projections"
    assert surface_from_path("/rules/3/body") == "rules"
    assert surface_from_path("/aggregates/0") == "aggregates"
    assert surface_from_path("/reactions/1/effect") == "reactions"
    assert surface_from_path("/header/label") == "overview"
    assert surface_from_path("/role/name") == "overview"
    assert surface_from_path("/d") == "overview"
    assert surface_from_path("") == "overview"


def test_validate_returns_clean_report_for_valid_doc():
    engine = ValidationEngine(meta_schema_path=META_SCHEMA)
    report = engine.validate(VALID_FIXTURE)
    assert isinstance(report, ValidationReport)
    assert report.is_valid is True
    assert report.errors == ()
    assert report.warnings == ()


def test_validate_returns_errors_for_missing_required():
    engine = ValidationEngine(meta_schema_path=META_SCHEMA)
    bad = {k: v for k, v in VALID_FIXTURE.items() if k != "header"}
    report = engine.validate(bad)
    assert report.is_valid is False
    assert len(report.errors) >= 1
    # Surfaces should route the missing-required error to "overview"
    # (the place the header is edited).
    assert any(e.surface == "overview" for e in report.errors)


def test_validate_routes_xref_error_to_correct_surface():
    engine = ValidationEngine(meta_schema_path=META_SCHEMA)
    doc = dict(VALID_FIXTURE)
    doc["credentials"] = {
        "imports": [],
        "exports": [
            {
                "id": "ex1",
                "name": "Test Cred",
                "schema_said": "E" + "B" * 43,
                "issuer_role_id": "r1",
                "issuee_role_id": "r2",
                "rule_refs": ["nonexistent-rule"],
                "lifecycle": {"transitions": []},
            }
        ],
    }
    report = engine.validate(doc)
    matching = [
        e for e in report.errors
        if e.surface == "exports" and "rule" in e.message.lower()
    ]
    assert matching, f"Expected a rule xref error on exports surface, got {report.errors}"


def test_json_pointer_path_starts_with_slash():
    engine = ValidationEngine(meta_schema_path=META_SCHEMA)
    bad = {k: v for k, v in VALID_FIXTURE.items() if k != "header"}
    report = engine.validate(bad)
    for issue in report.errors:
        assert issue.path == "" or issue.path.startswith("/"), \
            f"path {issue.path!r} not JSON-pointer normalized"
```

- [ ] **Step 2: Run test, verify RED**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_validation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'locksmith.plugins.designer.validation'`

- [ ] **Step 3: Implement the validation adapter**

Write `src/locksmith/plugins/designer/validation.py`:

```python
# -*- encoding: utf-8 -*-
"""Validation adapter for the Designer plugin.

Wraps locksmith.micro_app_template.validate to produce ValidationReport
records the Designer's UI consumes — with normalized JSON-pointer paths
and a `surface` field routing each issue to the editor that displays
it. The underlying validation logic (meta-schema + xref) is reused
unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from locksmith.micro_app_template.validate import (
    ValidationError as _RawError,
    validate_template as _validate_template,
)


@dataclass(frozen=True)
class ValidationIssue:
    severity: Literal["error", "warning"]
    code: str
    message: str
    path: str             # JSON-pointer ("" = root, "/commands/2/inputs")
    surface: str          # "commands" | "exports" | "imports" | … | "overview"


@dataclass(frozen=True)
class ValidationReport:
    errors: tuple[ValidationIssue, ...]
    warnings: tuple[ValidationIssue, ...]

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    @property
    def all_issues(self) -> tuple[ValidationIssue, ...]:
        return self.errors + self.warnings


_TOPLEVEL_TO_SURFACE: dict[str, str] = {
    "commands": "commands",
    "aggregates": "aggregates",
    "reactions": "reactions",
    "workflows": "workflows",
    "projections": "projections",
    "rules": "rules",
    "credentials": "credentials",  # refined below to imports/exports
    "header": "overview",
    "role": "overview",
    "d": "overview",
    "spec_version": "overview",
}


def surface_from_path(path: str) -> str:
    """Derive editor surface from a JSON-pointer path."""
    if not path or path == "/":
        return "overview"
    parts = path.lstrip("/").split("/")
    top = parts[0] if parts else ""
    if top == "credentials" and len(parts) >= 2:
        if parts[1] == "imports":
            return "imports"
        if parts[1] == "exports":
            return "exports"
    return _TOPLEVEL_TO_SURFACE.get(top, "overview")


def _normalize_path(raw: str) -> str:
    """Convert validator's path notation to JSON-pointer.

    Inputs we see:
      "credentials/exports/0/rule_refs/0"      (jsonschema-style)
      "credentials.exports[0].rule_refs[0]"    (xref-style)
      "<root>"                                  (jsonschema-style for root)
      ""                                        (already root)
    """
    if not raw or raw == "<root>":
        return ""
    # Replace bracket-index notation: foo[3] -> foo/3
    out = []
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch == ".":
            out.append("/")
        elif ch == "[":
            close = raw.find("]", i)
            if close == -1:
                out.append(ch)
                i += 1
                continue
            out.append("/")
            out.append(raw[i + 1 : close])
            i = close + 1
            continue
        else:
            out.append(ch)
        i += 1
    normalized = "".join(out)
    if not normalized.startswith("/"):
        normalized = "/" + normalized
    return normalized


def _issue_code(message: str) -> str:
    """Best-effort stable code from a validator's message.

    Real codes will be added when the validators emit them. For v1, use
    a heuristic prefix derived from message content.
    """
    msg = message.lower()
    if "required" in msg:
        return "missing-required"
    if "not found" in msg:
        return "unresolved-reference"
    if "additional" in msg and "not allowed" in msg:
        return "unexpected-property"
    if "match" in msg and "pattern" in msg:
        return "pattern-mismatch"
    return "schema-violation"


def _wrap(raw: _RawError) -> ValidationIssue:
    path = _normalize_path(raw.path)
    return ValidationIssue(
        severity="error" if raw.severity == "error" else "warning",
        code=_issue_code(raw.message),
        message=raw.message,
        path=path,
        surface=surface_from_path(path),
    )


class ValidationEngine:
    def __init__(self, meta_schema_path: Path):
        self.meta_schema_path = Path(meta_schema_path)

    def validate(self, doc: dict[str, Any]) -> ValidationReport:
        raw = _validate_template(doc, schema_path=self.meta_schema_path)
        errors: list[ValidationIssue] = []
        warnings: list[ValidationIssue] = []
        for r in raw.errors:
            wrapped = _wrap(r)
            (errors if wrapped.severity == "error" else warnings).append(wrapped)
        return ValidationReport(
            errors=tuple(errors), warnings=tuple(warnings),
        )
```

- [ ] **Step 4: Run test, verify GREEN**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_validation.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/validation.py tests/plugins/designer/test_validation.py
git commit -m "feat(designer): validation adapter with surface routing

Wraps locksmith.micro_app_template.validate to produce ValidationReport
records with JSON-pointer paths and a 'surface' field routing each
issue to the editor that displays it. Reuses the existing meta-schema
+ xref validators; adds path normalization and surface inference."
```

---

## Task 5: Cross-reference reverse index

**Files:**
- Create: `src/locksmith/plugins/designer/crossref.py`
- Test: `tests/plugins/designer/test_crossref.py`

This module computes "who consumes X?" given a template — the reverse direction of `locksmith.micro_app_template.xref` (which validates outgoing references). Powers the "Used by" chip strip on every editor.

- [ ] **Step 1: Write the failing tests (RED)**

Write `tests/plugins/designer/test_crossref.py`:

```python
# -*- encoding: utf-8 -*-
"""CrossRefIndex tests: reverse-direction reference lookups."""
from __future__ import annotations

import pytest

from locksmith.plugins.designer.crossref import (
    CrossRef,
    CrossRefIndex,
    compute_crossrefs,
)


@pytest.fixture
def doc():
    return {
        "d": "E" + "A" * 43,
        "spec_version": "micro-app-template/0.1",
        "header": {"label": "T", "description": "", "version": "1.0"},
        "role": {"id": "r1", "name": "tester", "kind": "individual"},
        "credentials": {
            "imports": [],
            "exports": [
                {
                    "id": "exp1",
                    "name": "License",
                    "schema_said": "E" + "B" * 43,
                    "issuer_role_id": "r1",
                    "issuee_role_id": "r2",
                    "rule_refs": ["solvency-rule"],
                    "lifecycle": {
                        "transitions": [
                            {
                                "from_state": "issued",
                                "to_state": "revoked",
                                "via_workflow": "revoke-wf",
                                "condition_rule_ref": None,
                            }
                        ],
                    },
                }
            ],
        },
        "commands": [
            {
                "id": "issue-license",
                "label": "Issue License",
                "effects": [{"kind": "issue", "credential_id": "exp1"}],
                "preconditions": ["solvency-rule"],
            }
        ],
        "aggregates": [],
        "reactions": [],
        "workflows": [
            {"id": "revoke-wf", "label": "Revoke License", "steps": []},
        ],
        "projections": [],
        "rules": [
            {"id": "solvency-rule", "label": "Min Capital $100M", "kind": "predicate"},
        ],
    }


def test_compute_returns_crossref_index(doc):
    idx = compute_crossrefs(doc)
    assert isinstance(idx, CrossRefIndex)


def test_rule_consumed_by_command_and_export(doc):
    idx = compute_crossrefs(doc)
    consumers = idx.consumers_of("rule:solvency-rule")
    surfaces = {c.surface for c in consumers}
    assert "commands" in surfaces
    assert "exports" in surfaces


def test_workflow_consumed_by_export(doc):
    idx = compute_crossrefs(doc)
    consumers = idx.consumers_of("workflow:revoke-wf")
    assert any(c.surface == "exports" for c in consumers)


def test_export_consumed_by_command(doc):
    idx = compute_crossrefs(doc)
    consumers = idx.consumers_of("export:exp1")
    assert any(c.surface == "commands" and c.primitive_label == "Issue License" for c in consumers)


def test_orphan_rule_has_no_consumers(doc):
    doc["rules"].append({"id": "orphan", "label": "Orphan", "kind": "predicate"})
    idx = compute_crossrefs(doc)
    assert idx.consumers_of("rule:orphan") == ()


def test_unknown_key_returns_empty_tuple(doc):
    idx = compute_crossrefs(doc)
    assert idx.consumers_of("rule:does-not-exist") == ()
```

- [ ] **Step 2: Run test, verify RED**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_crossref.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'locksmith.plugins.designer.crossref'`

- [ ] **Step 3: Implement crossref**

Write `src/locksmith/plugins/designer/crossref.py`:

```python
# -*- encoding: utf-8 -*-
"""Reverse-direction cross-reference index for the Designer.

For every primitive in a template, computes "who else references this?"
The result powers the 'Used by' chip strip on every editor surface.

Keys are strings of the form "<kind>:<id>", e.g. "rule:solvency-rule".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CrossRef:
    surface: str           # "commands" | "exports" | …
    primitive_label: str   # human label of the consumer
    primitive_path: str    # JSON pointer to the consumer entry


@dataclass(frozen=True)
class CrossRefIndex:
    _consumers: dict[str, tuple[CrossRef, ...]]

    def consumers_of(self, key: str) -> tuple[CrossRef, ...]:
        return self._consumers.get(key, ())

    def all_keys(self) -> tuple[str, ...]:
        return tuple(self._consumers.keys())


def _label(entry: dict[str, Any], fallback: str) -> str:
    return entry.get("label") or entry.get("name") or entry.get("id") or fallback


def compute_crossrefs(doc: dict[str, Any]) -> CrossRefIndex:
    """Walk the template and build the reverse-reference index."""
    out: dict[str, list[CrossRef]] = {}

    def add(key: str, ref: CrossRef) -> None:
        out.setdefault(key, []).append(ref)

    # Commands consume: preconditions (rules), effects.credential_id (exports/imports)
    for i, cmd in enumerate(doc.get("commands", [])):
        label = _label(cmd, f"command #{i}")
        path = f"/commands/{i}"
        for rule_id in cmd.get("preconditions", []):
            add(f"rule:{rule_id}", CrossRef(
                surface="commands", primitive_label=label, primitive_path=path,
            ))
        for rule_id in cmd.get("postconditions", []):
            add(f"rule:{rule_id}", CrossRef(
                surface="commands", primitive_label=label, primitive_path=path,
            ))
        for eff in cmd.get("effects", []):
            cred_id = eff.get("credential_id")
            if cred_id:
                add(f"export:{cred_id}", CrossRef(
                    surface="commands", primitive_label=label, primitive_path=path,
                ))
                add(f"import:{cred_id}", CrossRef(
                    surface="commands", primitive_label=label, primitive_path=path,
                ))

    # Exports consume: rule_refs, lifecycle.transitions.via_workflow + condition_rule_ref
    for i, exp in enumerate(doc.get("credentials", {}).get("exports", [])):
        label = _label(exp, f"export #{i}")
        path = f"/credentials/exports/{i}"
        for rule_id in exp.get("rule_refs", []):
            add(f"rule:{rule_id}", CrossRef(
                surface="exports", primitive_label=label, primitive_path=path,
            ))
        for t in exp.get("lifecycle", {}).get("transitions", []):
            wf = t.get("via_workflow")
            if wf:
                add(f"workflow:{wf}", CrossRef(
                    surface="exports", primitive_label=label, primitive_path=path,
                ))
            rr = t.get("condition_rule_ref")
            if rr:
                add(f"rule:{rr}", CrossRef(
                    surface="exports", primitive_label=label, primitive_path=path,
                ))

    # Imports consume: rule_refs
    for i, imp in enumerate(doc.get("credentials", {}).get("imports", [])):
        label = _label(imp, f"import #{i}")
        path = f"/credentials/imports/{i}"
        for rule_id in imp.get("rule_refs", []):
            add(f"rule:{rule_id}", CrossRef(
                surface="imports", primitive_label=label, primitive_path=path,
            ))

    # Workflows consume: step.rule_refs, step.command_id
    for i, wf in enumerate(doc.get("workflows", [])):
        label = _label(wf, f"workflow #{i}")
        path = f"/workflows/{i}"
        for step in wf.get("steps", []):
            for rule_id in step.get("rule_refs", []):
                add(f"rule:{rule_id}", CrossRef(
                    surface="workflows", primitive_label=label, primitive_path=path,
                ))
            cmd_id = step.get("command_id")
            if cmd_id:
                add(f"command:{cmd_id}", CrossRef(
                    surface="workflows", primitive_label=label, primitive_path=path,
                ))

    # Reactions consume: trigger.exn_kind & effect.command_id & effect.projection_id
    for i, rxn in enumerate(doc.get("reactions", [])):
        label = _label(rxn, f"reaction #{i}")
        path = f"/reactions/{i}"
        eff = rxn.get("effect", {})
        cmd_id = eff.get("command_id")
        if cmd_id:
            add(f"command:{cmd_id}", CrossRef(
                surface="reactions", primitive_label=label, primitive_path=path,
            ))
        proj_id = eff.get("projection_id")
        if proj_id:
            add(f"projection:{proj_id}", CrossRef(
                surface="reactions", primitive_label=label, primitive_path=path,
            ))

    # Projections consume: source aggregates
    for i, proj in enumerate(doc.get("projections", [])):
        label = _label(proj, f"projection #{i}")
        path = f"/projections/{i}"
        for agg_id in proj.get("source_aggregate_ids", []):
            add(f"aggregate:{agg_id}", CrossRef(
                surface="projections", primitive_label=label, primitive_path=path,
            ))

    return CrossRefIndex(_consumers={k: tuple(v) for k, v in out.items()})
```

- [ ] **Step 4: Run test, verify GREEN**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_crossref.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/crossref.py tests/plugins/designer/test_crossref.py
git commit -m "feat(designer): cross-reference reverse index

compute_crossrefs(doc) → CrossRefIndex with .consumers_of(key) lookup.
Reverse direction of locksmith.micro_app_template.xref (which validates
forward refs). Used by every editor's 'Used by' chip strip."
```

---

## Task 6: TemplateModel with signals

**Files:**
- Create: `src/locksmith/plugins/designer/model.py`
- Test: `tests/plugins/designer/test_model.py`

The model is a `QObject` wrapping the in-memory dict, emitting signals on every change so every editor surface, the validation panel, and the JSON view can subscribe. It also tracks the dirty flag.

- [ ] **Step 1: Write the failing tests (RED)**

Write `tests/plugins/designer/test_model.py`:

```python
# -*- encoding: utf-8 -*-
"""TemplateModel tests: signals, mutations, dirty tracking."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from locksmith.plugins.designer.model import TemplateModel


FIXTURE = {
    "d": "E" + "A" * 43,
    "spec_version": "micro-app-template/0.1",
    "header": {"label": "Original", "description": "", "version": "1.0"},
    "role": {"id": "r1", "name": "tester", "kind": "individual"},
    "credentials": {"imports": [], "exports": []},
    "commands": [],
    "aggregates": [],
    "reactions": [],
    "workflows": [],
    "projections": [],
    "rules": [],
}


def test_initial_state(qapp):
    m = TemplateModel(FIXTURE)
    assert m.doc == FIXTURE
    assert m.dirty is False


def test_set_path_changes_value_and_marks_dirty(qapp):
    m = TemplateModel(FIXTURE)
    m.set_path("/header/label", "Updated")
    assert m.doc["header"]["label"] == "Updated"
    assert m.dirty is True


def test_set_path_emits_changed(qapp):
    m = TemplateModel(FIXTURE)
    received: list[str] = []
    m.changed.connect(lambda path: received.append(path))
    m.set_path("/header/label", "Updated")
    assert received == ["/header/label"]


def test_append_to_collection(qapp):
    m = TemplateModel(FIXTURE)
    m.append_to("/commands", {"id": "c1", "label": "Do Thing"})
    assert len(m.doc["commands"]) == 1
    assert m.doc["commands"][0]["id"] == "c1"
    assert m.dirty is True


def test_remove_from_collection(qapp):
    seeded = {**FIXTURE, "commands": [{"id": "c1", "label": "Do"}]}
    m = TemplateModel(seeded)
    m.remove_from("/commands", 0)
    assert m.doc["commands"] == []
    assert m.dirty is True


def test_replace_doc_clears_dirty(qapp):
    m = TemplateModel(FIXTURE)
    m.set_path("/header/label", "Updated")
    new_fixture = {**FIXTURE, "header": {**FIXTURE["header"], "label": "Reloaded"}}
    m.replace_doc(new_fixture)
    assert m.doc["header"]["label"] == "Reloaded"
    assert m.dirty is False


def test_mark_clean(qapp):
    m = TemplateModel(FIXTURE)
    m.set_path("/header/label", "x")
    m.mark_clean()
    assert m.dirty is False
```

- [ ] **Step 2: Run test, verify RED**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_model.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement TemplateModel**

Write `src/locksmith/plugins/designer/model.py`:

```python
# -*- encoding: utf-8 -*-
"""TemplateModel: QObject wrapping the in-memory template dict.

Emits `changed(path)` on every mutation so editor surfaces and the
JSON source view can re-render reactively. Tracks the dirty flag for
save prompts.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, Signal


def _walk(doc: dict[str, Any], parts: list[str]) -> Any:
    cur: Any = doc
    for p in parts:
        if isinstance(cur, list):
            cur = cur[int(p)]
        else:
            cur = cur[p]
    return cur


def _set_at(doc: dict[str, Any], parts: list[str], value: Any) -> None:
    parent = _walk(doc, parts[:-1])
    last = parts[-1]
    if isinstance(parent, list):
        parent[int(last)] = value
    else:
        parent[last] = value


def _path_parts(path: str) -> list[str]:
    if not path or path == "/":
        return []
    return [p for p in path.lstrip("/").split("/") if p]


class TemplateModel(QObject):
    changed = Signal(str)         # path that changed
    dirty_changed = Signal(bool)

    def __init__(self, doc: dict[str, Any]):
        super().__init__()
        self._doc = doc
        self._dirty = False

    @property
    def doc(self) -> dict[str, Any]:
        return self._doc

    @property
    def dirty(self) -> bool:
        return self._dirty

    def _set_dirty(self, value: bool) -> None:
        if self._dirty != value:
            self._dirty = value
            self.dirty_changed.emit(value)

    def get_path(self, path: str) -> Any:
        return _walk(self._doc, _path_parts(path))

    def set_path(self, path: str, value: Any) -> None:
        parts = _path_parts(path)
        if not parts:
            raise ValueError("Cannot set the root document via set_path()")
        _set_at(self._doc, parts, value)
        self._set_dirty(True)
        self.changed.emit(path)

    def append_to(self, path: str, value: Any) -> int:
        target = _walk(self._doc, _path_parts(path))
        if not isinstance(target, list):
            raise TypeError(f"Cannot append to non-list at {path}")
        target.append(value)
        self._set_dirty(True)
        self.changed.emit(path)
        return len(target) - 1

    def remove_from(self, path: str, index: int) -> None:
        target = _walk(self._doc, _path_parts(path))
        if not isinstance(target, list):
            raise TypeError(f"Cannot remove from non-list at {path}")
        del target[index]
        self._set_dirty(True)
        self.changed.emit(path)

    def replace_doc(self, new_doc: dict[str, Any]) -> None:
        self._doc = new_doc
        self._set_dirty(False)
        self.changed.emit("")

    def mark_clean(self) -> None:
        self._set_dirty(False)
```

- [ ] **Step 4: Run test, verify GREEN**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_model.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/model.py tests/plugins/designer/test_model.py
git commit -m "feat(designer): TemplateModel — single source of truth

QObject wrapping the in-memory template dict. Emits changed(path) on
every mutation. Tracks dirty flag for save prompts. Editor surfaces and
the JSON source view subscribe and re-render reactively."
```

---

## Task 7: PrimitiveEditorShell widget

**Files:**
- Create: `src/locksmith/plugins/designer/widgets/__init__.py`
- Create: `src/locksmith/plugins/designer/widgets/kind_rail.py`
- Create: `src/locksmith/plugins/designer/widgets/cross_ref_chip.py`
- Create: `src/locksmith/plugins/designer/widgets/validation_badge.py`
- Create: `src/locksmith/plugins/designer/widgets/primitive_editor_shell.py`
- Test: `tests/plugins/designer/test_primitive_editor_shell_visual.py`

This is the shared shell every per-primitive editor uses. Layout: top identity strip, left rail with kind-colored items + `+ Add`, right pane with sections.

- [ ] **Step 1: Write the failing visual test (RED)**

Write `tests/plugins/designer/test_primitive_editor_shell_visual.py`:

```python
# -*- encoding: utf-8 -*-
"""Structural + visual smoke test for PrimitiveEditorShell."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QWidget

from locksmith.plugins.designer.widgets.primitive_editor_shell import (
    PrimitiveEditorShell, RailItem,
)


SHOTS_DIR = Path(__file__).parent.parent.parent / "_screenshots" / "designer"


def _grab(widget, name: str) -> Path:
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = SHOTS_DIR / f"{name}.png"
    pix = widget.grab()
    assert not pix.isNull()
    assert pix.save(str(path))
    return path


def test_shell_renders_rail_items_and_default_pane(qapp):
    items = [
        RailItem(id="a", label="Item A", kind_color="#0ABFB0", has_errors=False),
        RailItem(id="b", label="Item B", kind_color="#0ABFB0", has_errors=True),
        RailItem(id="c", label="Item C", kind_color="#D97757", has_errors=False),
    ]
    shell = PrimitiveEditorShell(
        surface_label="Commands",
        template_label="Carrier License Application",
        items=items,
    )
    shell.resize(960, 720)
    shell.show()
    qapp.processEvents()
    QTest.qWait(200)
    qapp.processEvents()

    assert shell.rail_list.count() == 3
    assert shell.identity_label.text() == "Carrier License Application"
    assert shell.surface_label.text() == "Commands"

    _grab(shell, "shell_renders_rail")


def test_shell_selects_first_item_by_default(qapp):
    items = [RailItem(id="a", label="A", kind_color="#0ABFB0", has_errors=False)]
    shell = PrimitiveEditorShell(
        surface_label="X", template_label="T", items=items,
    )
    qapp.processEvents()
    assert shell.selected_item_id == "a"


def test_shell_emits_signal_on_item_click(qapp):
    items = [
        RailItem(id="a", label="A", kind_color="#0ABFB0", has_errors=False),
        RailItem(id="b", label="B", kind_color="#0ABFB0", has_errors=False),
    ]
    shell = PrimitiveEditorShell(
        surface_label="X", template_label="T", items=items,
    )
    received: list[str] = []
    shell.item_selected.connect(lambda iid: received.append(iid))
    shell.rail_list.setCurrentRow(1)
    qapp.processEvents()
    assert received == ["b"]
    assert shell.selected_item_id == "b"


def test_shell_set_right_pane_replaces_content(qapp):
    items = [RailItem(id="a", label="A", kind_color="#0ABFB0", has_errors=False)]
    shell = PrimitiveEditorShell(
        surface_label="X", template_label="T", items=items,
    )
    pane = QLabel("new content")
    shell.set_right_pane(pane)
    qapp.processEvents()
    assert shell.right_pane_container.layout().count() == 1
```

- [ ] **Step 2: Run test, verify RED**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_primitive_editor_shell_visual.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement shared widgets**

Write `src/locksmith/plugins/designer/widgets/__init__.py`:

```python
# -*- encoding: utf-8 -*-
"""Designer plugin reusable widgets."""
```

Write `src/locksmith/plugins/designer/widgets/validation_badge.py`:

```python
# -*- encoding: utf-8 -*-
"""ValidationBadge: small pill showing error/warning count or "valid"."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel


class ValidationBadge(QLabel):
    """Compact badge: green 'valid', amber 'N warnings', red 'N errors'."""

    def __init__(self, *, errors: int = 0, warnings: int = 0, parent=None):
        super().__init__(parent=parent)
        self.setMargin(0)
        self.set_counts(errors=errors, warnings=warnings)

    def set_counts(self, *, errors: int, warnings: int) -> None:
        if errors > 0:
            text = f"⛔ {errors} error{'s' if errors != 1 else ''}"
            bg = "#fce4e4"
            fg = "#9b1d1d"
        elif warnings > 0:
            text = f"⚠ {warnings} warning{'s' if warnings != 1 else ''}"
            bg = "#fff3cd"
            fg = "#7a5b00"
        else:
            text = "✓ valid"
            bg = "#e8f5e9"
            fg = "#1b5e20"
        self.setText(text)
        self.setStyleSheet(
            f"background:{bg};color:{fg};border-radius:10px;"
            f"padding:3px 8px;font-size:10px;font-weight:600;"
        )
```

Write `src/locksmith/plugins/designer/widgets/cross_ref_chip.py`:

```python
# -*- encoding: utf-8 -*-
"""CrossRefChip + CrossRefChipStrip: 'Used by' navigable pills."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from locksmith.plugins.designer.crossref import CrossRef


class CrossRefChip(QPushButton):
    navigated = Signal(str, str)  # surface, path

    def __init__(self, ref: CrossRef, parent=None):
        super().__init__(parent=parent)
        self._ref = ref
        self.setText(f"{ref.surface}: {ref.primitive_label}")
        self.setCursor(self.cursor())
        self.setFlat(True)
        self.setStyleSheet(
            "background:#f6f7f9;color:#444;border:1px solid #e0e3ea;"
            "border-radius:10px;padding:3px 10px;font-size:10px;"
        )
        self.clicked.connect(self._on_click)

    def _on_click(self) -> None:
        self.navigated.emit(self._ref.surface, self._ref.primitive_path)


class CrossRefChipStrip(QWidget):
    navigated = Signal(str, str)  # surface, path

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self._empty_label = QLabel("Not referenced elsewhere")
        self._empty_label.setStyleSheet("color:#aaa;font-size:11px;")
        self._layout.addWidget(self._empty_label)
        self._chips: list[CrossRefChip] = []

    def set_refs(self, refs: tuple[CrossRef, ...]) -> None:
        # Clear existing chips
        for c in self._chips:
            c.setParent(None)
            c.deleteLater()
        self._chips = []
        self._empty_label.setVisible(len(refs) == 0)
        for ref in refs:
            chip = CrossRefChip(ref)
            chip.navigated.connect(self.navigated.emit)
            self._layout.addWidget(chip)
            self._chips.append(chip)
        self._layout.addStretch(1)
```

Write `src/locksmith/plugins/designer/widgets/kind_rail.py`:

```python
# -*- encoding: utf-8 -*-
"""KindRail: left-rail list with kind-color dots and validation badges.

Used by every per-primitive editor as the typed list of entries.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QListWidget, QListWidgetItem


@dataclass(frozen=True)
class RailItem:
    id: str
    label: str
    kind_color: str  # CSS hex, e.g. "#0ABFB0"
    has_errors: bool


def _dot_icon(color_hex: str, size: int = 12) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(color_hex))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(0, 0, size, size)
    painter.end()
    return pix


class KindRail(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setStyleSheet(
            "QListWidget{background:#fff;border:0;}"
            "QListWidget::item{padding:8px 12px;border-bottom:1px solid #f0f2f5;}"
            "QListWidget::item:selected{background:#f6f7f9;color:#1A1C20;}"
        )

    def populate(self, items: list[RailItem]) -> None:
        self.clear()
        for r in items:
            label = r.label + ("  ⛔" if r.has_errors else "")
            item = QListWidgetItem(label)
            item.setIcon(_dot_icon(r.kind_color))
            item.setData(Qt.UserRole, r.id)
            self.addItem(item)
        if self.count() > 0:
            self.setCurrentRow(0)

    def selected_id(self) -> str | None:
        item = self.currentItem()
        if item is None:
            return None
        return item.data(Qt.UserRole)
```

Write `src/locksmith/plugins/designer/widgets/primitive_editor_shell.py`:

```python
# -*- encoding: utf-8 -*-
"""PrimitiveEditorShell: shared layout for every per-primitive editor.

Layout:
  ┌──────────────────────────────────────────────┐
  │ ← Back · <template label> · <surface label>  │  identity strip
  ├──────────┬───────────────────────────────────┤
  │ rail     │ right pane                        │
  │  • item  │ (sections set by the editor)      │
  │  • item  │                                   │
  │  + Add   │                                   │
  └──────────┴───────────────────────────────────┘
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from locksmith.plugins.designer.widgets.kind_rail import KindRail, RailItem


class PrimitiveEditorShell(QWidget):
    item_selected = Signal(str)   # id of selected rail item
    add_clicked = Signal()
    back_clicked = Signal()

    def __init__(
        self,
        *,
        surface_label: str,
        template_label: str,
        items: list[RailItem],
        parent=None,
    ):
        super().__init__(parent=parent)
        self._build(surface_label=surface_label, template_label=template_label)
        self.rail_list.populate(items)
        self.rail_list.currentItemChanged.connect(self._on_rail_change)

    def _build(self, *, surface_label: str, template_label: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Identity strip
        strip = QFrame()
        strip.setStyleSheet("background:#fff;border-bottom:1px solid #e0e3ea;")
        strip_lay = QHBoxLayout(strip)
        strip_lay.setContentsMargins(16, 10, 16, 10)
        self.back_button = QPushButton("← Back")
        self.back_button.setFlat(True)
        self.back_button.clicked.connect(self.back_clicked.emit)
        strip_lay.addWidget(self.back_button)
        sep1 = QLabel("·")
        sep1.setStyleSheet("color:#ccc;")
        strip_lay.addWidget(sep1)
        self.identity_label = QLabel(template_label)
        self.identity_label.setStyleSheet("font-weight:600;color:#1A1C20;")
        strip_lay.addWidget(self.identity_label)
        sep2 = QLabel("·")
        sep2.setStyleSheet("color:#ccc;")
        strip_lay.addWidget(sep2)
        self.surface_label = QLabel(surface_label)
        self.surface_label.setStyleSheet("color:#666;")
        strip_lay.addWidget(self.surface_label)
        strip_lay.addStretch(1)
        root.addWidget(strip)

        # Body: rail + right pane
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        rail_panel = QFrame()
        rail_panel.setFixedWidth(260)
        rail_panel.setStyleSheet("background:#fff;border-right:1px solid #e0e3ea;")
        rail_lay = QVBoxLayout(rail_panel)
        rail_lay.setContentsMargins(0, 0, 0, 0)
        rail_lay.setSpacing(0)
        self.rail_list = KindRail()
        rail_lay.addWidget(self.rail_list, 1)
        self.add_button = QPushButton("+ Add")
        self.add_button.setStyleSheet(
            "QPushButton{background:#fff;border:0;border-top:1px solid #f0f2f5;"
            "padding:10px;text-align:left;color:#666;}"
            "QPushButton:hover{background:#f6f7f9;}"
        )
        self.add_button.clicked.connect(self.add_clicked.emit)
        rail_lay.addWidget(self.add_button)
        body.addWidget(rail_panel)

        self.right_pane_container = QFrame()
        self.right_pane_container.setStyleSheet("background:#f6f7f9;")
        QVBoxLayout(self.right_pane_container).setContentsMargins(20, 20, 20, 20)
        body.addWidget(self.right_pane_container, 1)
        root.addLayout(body, 1)

    @property
    def selected_item_id(self) -> str | None:
        return self.rail_list.selected_id()

    def set_right_pane(self, widget: QWidget) -> None:
        layout = self.right_pane_container.layout()
        while layout.count():
            old = layout.takeAt(0).widget()
            if old is not None:
                old.setParent(None)
                old.deleteLater()
        layout.addWidget(widget)

    def repopulate_rail(self, items: list[RailItem]) -> None:
        self.rail_list.populate(items)

    def _on_rail_change(self, current, _previous) -> None:
        if current is None:
            return
        from PySide6.QtCore import Qt
        item_id = current.data(Qt.UserRole)
        if item_id:
            self.item_selected.emit(item_id)
```

- [ ] **Step 4: Run test, verify GREEN**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_primitive_editor_shell_visual.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/widgets/ \
        tests/plugins/designer/test_primitive_editor_shell_visual.py
git commit -m "feat(designer): shared editor shell + base widgets

PrimitiveEditorShell is the layout every per-primitive editor uses:
identity strip on top, KindRail (kind-colored typed list) on the left,
sectionable right pane on the right. Adds ValidationBadge and
CrossRefChipStrip widgets every editor will use."
```

---

## Task 8: TemplatesBrowserPage

**Files:**
- Create: `src/locksmith/plugins/designer/editors/__init__.py`
- Create: `src/locksmith/plugins/designer/editors/templates_browser.py`
- Test: `tests/plugins/designer/test_templates_browser_visual.py`
- Test: `tests/plugins/designer/conftest.py`
- Test: `tests/plugins/designer/fixtures/regulator-grants-carrier-license.json`
- Test: `tests/plugins/designer/fixtures/carrier-license-application.json`

- [ ] **Step 1: Create the test fixtures**

Write `tests/plugins/designer/fixtures/regulator-grants-carrier-license.json` (minimal valid template):

```json
{
  "d": "EGCpXap_yYxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx6yAv",
  "spec_version": "micro-app-template/0.1",
  "header": {
    "label": "Regulator Grants Carrier License",
    "description": "The state DOI authorizes carriers to bear risk in this jurisdiction.",
    "version": "1.0"
  },
  "role": {"id": "state-doi", "name": "state-doi", "kind": "government"},
  "credentials": {"imports": [], "exports": [
    {"id": "carrier-license", "name": "Carrier License",
     "schema_said": "EBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB",
     "issuer_role_id": "state-doi", "issuee_role_id": "carrier",
     "rule_refs": [], "lifecycle": {"transitions": []}}
  ]},
  "commands": [{"id": "issue-license", "label": "Issue License",
                "effects": [{"kind": "issue", "credential_id": "carrier-license"}],
                "preconditions": []}],
  "aggregates": [], "reactions": [],
  "workflows": [{"id": "review-app", "label": "Review Application", "steps": []}],
  "projections": [], "rules": []
}
```

Write `tests/plugins/designer/fixtures/carrier-license-application.json` (similar minimal valid template — adapt header/role/exports):

```json
{
  "d": "ECARRIERAPPxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "spec_version": "micro-app-template/0.1",
  "header": {
    "label": "Carrier License Application",
    "description": "Application a carrier files to obtain a state DOI license.",
    "version": "1.0"
  },
  "role": {"id": "carrier", "name": "carrier", "kind": "organization"},
  "credentials": {
    "imports": [{"id": "doi-charter", "name": "DOI Charter",
                 "schema_said": "EDOICHARTERxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                 "issuer_role_id": "state-doi", "issuee_role_id": "carrier",
                 "rule_refs": []}],
    "exports": []
  },
  "commands": [], "aggregates": [], "reactions": [],
  "workflows": [], "projections": [], "rules": []
}
```

- [ ] **Step 2: Add the conftest**

Write `tests/plugins/designer/conftest.py`:

```python
# -*- encoding: utf-8 -*-
"""Shared fixtures for Designer plugin tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from locksmith.plugins.designer.store import TemplateStore


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_dir():
    return FIXTURES


@pytest.fixture
def seeded_store(tmp_path):
    store = TemplateStore(root=tmp_path)
    for f in FIXTURES.glob("*.json"):
        doc = json.loads(f.read_text())
        store.save_registered(said=doc["d"], doc=doc, metadata={})
    return store
```

- [ ] **Step 3: Write the failing visual test (RED)**

Write `tests/plugins/designer/test_templates_browser_visual.py`:

```python
# -*- encoding: utf-8 -*-
"""Templates browser: structural + visual smoke test."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest

from locksmith.plugins.designer.editors.templates_browser import TemplatesBrowserPage


SHOTS_DIR = Path(__file__).parent.parent.parent / "_screenshots" / "designer"


def _grab(widget, name: str) -> Path:
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = SHOTS_DIR / f"{name}.png"
    pix = widget.grab()
    assert not pix.isNull()
    assert pix.save(str(path))
    return path


def test_browser_shows_seeded_templates(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    page.resize(1100, 800)
    page.show()
    qapp.processEvents()
    QTest.qWait(200)
    qapp.processEvents()

    assert page.card_count() == 2
    titles = page.card_titles()
    assert "Regulator Grants Carrier License" in titles
    assert "Carrier License Application" in titles
    _grab(page, "templates_browser_two_seeded")


def test_browser_empty_state(qapp, tmp_path):
    from locksmith.plugins.designer.store import TemplateStore
    empty = TemplateStore(root=tmp_path)
    page = TemplatesBrowserPage(store=empty)
    page.refresh()
    qapp.processEvents()
    assert page.card_count() == 0
    assert page.empty_state_visible() is True


def test_browser_emits_open_on_card_click(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    qapp.processEvents()
    received: list = []
    page.template_open_requested.connect(lambda ref: received.append(ref))
    page.click_first_card()
    qapp.processEvents()
    assert len(received) == 1
```

- [ ] **Step 4: Run test, verify RED**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_templates_browser_visual.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 5: Implement TemplatesBrowserPage**

Write `src/locksmith/plugins/designer/editors/__init__.py`:

```python
# -*- encoding: utf-8 -*-
"""Designer editor pages."""
```

Write `src/locksmith/plugins/designer/editors/templates_browser.py`:

```python
# -*- encoding: utf-8 -*-
"""TemplatesBrowserPage: entry surface for the Designer.

Lists every template the workspace knows about as cards in a 2-up grid.
Click a card → emit template_open_requested(ref).
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from locksmith.plugins.designer.store import TemplateRef, TemplateStore


_ROLE_KIND_COLOR: dict[str, str] = {
    "government": "#0ABFB0",
    "organization": "#0ABFB0",
    "individual": "#D97757",
    "system": "#888888",
    "device": "#888888",
    "agent": "#A36AE6",
}


class _TemplateCard(QFrame):
    clicked = Signal()

    def __init__(self, ref: TemplateRef, doc: dict[str, Any], parent=None):
        super().__init__(parent=parent)
        self._ref = ref
        self.setObjectName("card")
        self.setStyleSheet(
            "#card{background:#fff;border:1px solid #e0e3ea;border-radius:8px;}"
            "#card:hover{border:1px solid #d97757;}"
        )
        self._build(doc)

    @property
    def ref(self) -> TemplateRef:
        return self._ref

    @property
    def title(self) -> str:
        return self._title

    def _build(self, doc: dict[str, Any]) -> None:
        header = doc.get("header", {})
        role = doc.get("role", {})
        self._title = header.get("label", "(untitled)")
        kind = role.get("kind", "")
        color = _ROLE_KIND_COLOR.get(kind, "#888888")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(8)

        top = QHBoxLayout()
        swatch = QLabel()
        swatch.setFixedSize(44, 44)
        swatch.setStyleSheet(
            f"background:{color};border-radius:6px;"
        )
        top.addWidget(swatch)

        text = QVBoxLayout()
        title_row = QHBoxLayout()
        title = QLabel(self._title)
        title.setStyleSheet("font-size:15px;font-weight:600;color:#1A1C20;")
        title_row.addWidget(title)
        version = QLabel(f"v{header.get('version', '0.0')}")
        version.setStyleSheet(
            "color:#888;background:#f6f7f9;padding:2px 7px;border-radius:8px;"
            "font-size:10px;"
        )
        title_row.addWidget(version)
        title_row.addStretch(1)
        text.addLayout(title_row)

        subtitle = QLabel(
            f"<span style='color:{color};font-weight:600;'>"
            f"{role.get('name', '')}</span> · {kind}"
        )
        subtitle.setStyleSheet("font-size:11px;color:#666;")
        text.addWidget(subtitle)
        top.addLayout(text, 1)
        outer.addLayout(top)

        desc = QLabel(header.get("description", ""))
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size:12px;color:#444;")
        outer.addWidget(desc)

        counts = (
            f"{len(doc.get('credentials', {}).get('imports', []))} imports · "
            f"{len(doc.get('credentials', {}).get('exports', []))} exports · "
            f"{len(doc.get('commands', []))} commands · "
            f"{len(doc.get('workflows', []))} workflows"
        )
        footer = QHBoxLayout()
        ftext = QLabel(counts)
        ftext.setStyleSheet("font-size:10px;color:#888;")
        footer.addWidget(ftext)
        footer.addStretch(1)
        if self._ref.kind == "draft":
            badge = QLabel("DRAFT")
        else:
            badge = QLabel(f"{self._ref.said[:4]}…{self._ref.said[-4:]}")
        badge.setStyleSheet("font-size:9px;color:#aaa;font-family:monospace;")
        footer.addWidget(badge)
        outer.addLayout(footer)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(ev)


class TemplatesBrowserPage(QWidget):
    template_open_requested = Signal(object)  # TemplateRef
    new_template_requested = Signal()
    import_file_requested = Signal()

    def __init__(self, *, store: TemplateStore, parent=None):
        super().__init__(parent=parent)
        self._store = store
        self._cards: list[_TemplateCard] = []
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        toolbar = QFrame()
        toolbar.setStyleSheet("background:#fff;border-bottom:1px solid #e0e3ea;")
        toolbar_lay = QHBoxLayout(toolbar)
        toolbar_lay.setContentsMargins(20, 14, 20, 14)
        title = QLabel("Micro-App Templates")
        title.setStyleSheet("font-size:18px;font-weight:600;color:#1A1C20;")
        toolbar_lay.addWidget(title)
        toolbar_lay.addStretch(1)

        btn_import_file = QPushButton("⬇ Import file")
        btn_import_file.clicked.connect(self.import_file_requested.emit)
        btn_import_oobi = QPushButton("🌐 Import via OOBI")
        btn_import_oobi.setEnabled(False)
        btn_import_oobi.setToolTip("Coming in a future release")
        btn_new = QPushButton("+ New template")
        btn_new.setStyleSheet(
            "background:#d97757;color:#fff;font-weight:600;"
            "padding:7px 14px;border-radius:4px;"
        )
        btn_new.clicked.connect(self.new_template_requested.emit)
        for b in (btn_import_file, btn_import_oobi, btn_new):
            toolbar_lay.addWidget(b)
        root.addWidget(toolbar)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("border:0;background:#f6f7f9;")
        self._grid_host = QWidget()
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(20, 20, 20, 20)
        self._grid.setSpacing(14)
        self._empty_label = QLabel(
            "No templates yet. Click '+ New template' to author your first one."
        )
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setStyleSheet("color:#888;font-size:14px;padding:60px;")
        self._grid.addWidget(self._empty_label, 0, 0)
        self._scroll.setWidget(self._grid_host)
        root.addWidget(self._scroll, 1)

    def refresh(self) -> None:
        # Clear existing cards
        for c in self._cards:
            c.setParent(None)
            c.deleteLater()
        self._cards = []
        refs = self._store.list_templates()
        self._empty_label.setVisible(len(refs) == 0)
        for i, ref in enumerate(refs):
            doc, _meta = self._store.load(ref)
            card = _TemplateCard(ref=ref, doc=doc)
            card.clicked.connect(
                lambda r=ref: self.template_open_requested.emit(r)
            )
            row, col = divmod(i, 2)
            self._grid.addWidget(card, row, col)
            self._cards.append(card)

    def card_count(self) -> int:
        return len(self._cards)

    def card_titles(self) -> list[str]:
        return [c.title for c in self._cards]

    def empty_state_visible(self) -> bool:
        return self._empty_label.isVisible()

    def click_first_card(self) -> None:
        if self._cards:
            self._cards[0].clicked.emit()
```

- [ ] **Step 6: Run test, verify GREEN**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_templates_browser_visual.py -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Commit**

```bash
git add src/locksmith/plugins/designer/editors/ \
        tests/plugins/designer/conftest.py \
        tests/plugins/designer/fixtures/ \
        tests/plugins/designer/test_templates_browser_visual.py
git commit -m "feat(designer): templates browser page

Entry surface listing every template as cards in a 2-up grid. Click a
card → template_open_requested. Includes empty state. OOBI-import slot
disabled in v1."
```

---

## Task 9: TemplateOverviewPage (first-person cards)

**Files:**
- Create: `src/locksmith/plugins/designer/widgets/first_person_card.py`
- Create: `src/locksmith/plugins/designer/editors/overview.py`
- Test: `tests/plugins/designer/test_overview_visual.py`

The Overview shows the template's primitives as first-person mental-model cards. Each card lists the top 2-3 entries inline and exposes a `+ Add` affordance.

- [ ] **Step 1: Write the failing visual test (RED)**

Write `tests/plugins/designer/test_overview_visual.py`:

```python
# -*- encoding: utf-8 -*-
"""Overview page: structural + visual smoke test."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest

from locksmith.plugins.designer.editors.overview import TemplateOverviewPage
from locksmith.plugins.designer.model import TemplateModel


SHOTS_DIR = Path(__file__).parent.parent.parent / "_screenshots" / "designer"


def _grab(widget, name):
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = SHOTS_DIR / f"{name}.png"
    pix = widget.grab()
    assert not pix.isNull()
    assert pix.save(str(path))
    return path


def test_overview_renders_nine_first_person_cards(qapp, fixture_dir):
    doc = json.loads((fixture_dir / "regulator-grants-carrier-license.json").read_text())
    model = TemplateModel(doc)
    page = TemplateOverviewPage(model=model)
    page.resize(1100, 900)
    page.show()
    qapp.processEvents()
    QTest.qWait(200)

    cards = page.card_kinds()
    expected = [
        "role", "imports", "exports", "commands", "reactions",
        "workflows", "aggregates", "projections", "rules",
    ]
    assert cards == expected
    _grab(page, "overview_regulator_grants_license")


def test_overview_card_emits_drilldown(qapp, fixture_dir):
    doc = json.loads((fixture_dir / "regulator-grants-carrier-license.json").read_text())
    model = TemplateModel(doc)
    page = TemplateOverviewPage(model=model)
    received: list[str] = []
    page.drilldown_requested.connect(lambda kind: received.append(kind))
    page.click_card("commands")
    assert received == ["commands"]


def test_overview_header_strip_shows_label_and_role(qapp, fixture_dir):
    doc = json.loads((fixture_dir / "regulator-grants-carrier-license.json").read_text())
    model = TemplateModel(doc)
    page = TemplateOverviewPage(model=model)
    page.show()
    qapp.processEvents()
    assert page.header_label_text() == "Regulator Grants Carrier License"
    assert "state-doi" in page.role_chip_text()
```

- [ ] **Step 2: Run test, verify RED**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_overview_visual.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement FirstPersonCard**

Write `src/locksmith/plugins/designer/widgets/first_person_card.py`:

```python
# -*- encoding: utf-8 -*-
"""FirstPersonCard: an Overview card framed in first person."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)


class FirstPersonCard(QFrame):
    clicked = Signal()
    add_clicked = Signal()

    def __init__(
        self,
        *,
        framing: str,           # "I do …", "I hold …", etc.
        kind_label: str,        # human label of the primitive group, e.g. "Commands"
        count: int,
        preview_entries: list[str],
        parent=None,
    ):
        super().__init__(parent=parent)
        self.setObjectName("fpcard")
        self.setStyleSheet(
            "#fpcard{background:#fff;border:1px solid #e0e3ea;border-radius:8px;}"
            "#fpcard:hover{border:1px solid #d97757;}"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(6)

        header = QHBoxLayout()
        framing_label = QLabel(framing)
        framing_label.setStyleSheet("color:#888;font-size:11px;")
        header.addWidget(framing_label)
        header.addStretch(1)
        count_label = QLabel(str(count))
        count_label.setStyleSheet(
            "background:#f6f7f9;color:#666;border-radius:10px;"
            "padding:1px 8px;font-size:10px;font-weight:600;"
        )
        header.addWidget(count_label)
        outer.addLayout(header)

        kind = QLabel(kind_label)
        kind.setStyleSheet("font-size:15px;font-weight:600;color:#1A1C20;")
        outer.addWidget(kind)

        for entry in preview_entries[:3]:
            row = QLabel(f"• {entry}")
            row.setStyleSheet("font-size:12px;color:#444;")
            row.setWordWrap(True)
            outer.addWidget(row)
        if not preview_entries:
            empty = QLabel("(none yet)")
            empty.setStyleSheet("font-size:12px;color:#aaa;font-style:italic;")
            outer.addWidget(empty)

        add = QPushButton("+ Add")
        add.setFlat(True)
        add.setStyleSheet(
            "QPushButton{color:#666;text-align:left;border:0;padding:0;font-size:11px;}"
            "QPushButton:hover{color:#d97757;}"
        )
        add.clicked.connect(self.add_clicked.emit)
        outer.addWidget(add)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(ev)
```

- [ ] **Step 4: Implement TemplateOverviewPage**

Write `src/locksmith/plugins/designer/editors/overview.py`:

```python
# -*- encoding: utf-8 -*-
"""TemplateOverviewPage: first-person mental-model card grid.

Renders the open TemplateModel as a grid of FirstPersonCard widgets.
Clicking a card → drilldown_requested(kind).
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.widgets.first_person_card import FirstPersonCard


_CARD_SPECS: list[tuple[str, str, str, str]] = [
    # (kind, framing, label, doc-path-to-list)
    ("role",        "I am …",          "Role",                ""),     # special — singular
    ("imports",     "I hold …",        "Held credentials",    "credentials.imports"),
    ("exports",     "I issue …",       "Issued credentials",  "credentials.exports"),
    ("commands",    "I do …",          "Commands",            "commands"),
    ("reactions",   "I respond to …",  "Reactions",           "reactions"),
    ("workflows",   "I follow …",      "Workflows",           "workflows"),
    ("aggregates",  "I track …",       "Aggregates",          "aggregates"),
    ("projections", "I see …",         "Projections",         "projections"),
    ("rules",       "I'm bound by …",  "Rules",               "rules"),
]


def _list_at(doc: dict[str, Any], dotted_path: str) -> list[dict[str, Any]]:
    if not dotted_path:
        return []
    cur: Any = doc
    for part in dotted_path.split("."):
        if not isinstance(cur, dict):
            return []
        cur = cur.get(part)
        if cur is None:
            return []
    return cur if isinstance(cur, list) else []


def _entry_label(entry: dict[str, Any]) -> str:
    return entry.get("label") or entry.get("name") or entry.get("id") or "(unnamed)"


class TemplateOverviewPage(QWidget):
    drilldown_requested = Signal(str)        # kind name
    add_requested = Signal(str)              # kind name
    edit_header_requested = Signal()
    edit_role_requested = Signal()

    def __init__(self, *, model: TemplateModel, parent=None):
        super().__init__(parent=parent)
        self._model = model
        self._cards: dict[str, FirstPersonCard] = {}
        self._build()
        self._model.changed.connect(lambda _path: self._refresh())

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header strip
        header_strip = QFrame()
        header_strip.setStyleSheet(
            "background:#fff;border-bottom:1px solid #e0e3ea;"
        )
        h = QHBoxLayout(header_strip)
        h.setContentsMargins(20, 14, 20, 14)
        self._header_label = QLabel(self._model.doc.get("header", {}).get("label", ""))
        self._header_label.setStyleSheet("font-size:18px;font-weight:600;color:#1A1C20;")
        h.addWidget(self._header_label)
        sep = QLabel("·")
        sep.setStyleSheet("color:#ccc;")
        h.addWidget(sep)
        role = self._model.doc.get("role", {})
        self._role_chip = QPushButton(
            f"{role.get('name', '')} · {role.get('kind', '')}"
        )
        self._role_chip.setFlat(True)
        self._role_chip.setStyleSheet(
            "background:#0ABFB0;color:#fff;border-radius:10px;"
            "padding:3px 10px;font-size:11px;font-weight:600;"
        )
        self._role_chip.clicked.connect(self.edit_role_requested.emit)
        h.addWidget(self._role_chip)
        h.addStretch(1)
        h.addWidget(QPushButton("Edit header"))  # wired in dialogs task
        root.addWidget(header_strip)

        # Grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border:0;background:#f6f7f9;")
        host = QWidget()
        grid = QGridLayout(host)
        grid.setContentsMargins(20, 20, 20, 20)
        grid.setSpacing(14)

        for idx, (kind, framing, label, dotted) in enumerate(_CARD_SPECS):
            entries = _list_at(self._model.doc, dotted) if kind != "role" else []
            previews = [_entry_label(e) for e in entries]
            if kind == "role":
                role = self._model.doc.get("role", {})
                previews = [
                    f"{role.get('name', '(unnamed)')} ({role.get('kind', '?')})"
                ]
                count = 1
            else:
                count = len(entries)
            card = FirstPersonCard(
                framing=framing,
                kind_label=label,
                count=count,
                preview_entries=previews,
            )
            card.clicked.connect(lambda k=kind: self.drilldown_requested.emit(k))
            card.add_clicked.connect(lambda k=kind: self.add_requested.emit(k))
            row, col = divmod(idx, 3)
            grid.addWidget(card, row, col)
            self._cards[kind] = card

        scroll.setWidget(host)
        root.addWidget(scroll, 1)

    def _refresh(self) -> None:
        # Cheap full-rebuild on any change — templates are small.
        layout = self.layout()
        while layout.count():
            old = layout.takeAt(0).widget()
            if old is not None:
                old.setParent(None)
                old.deleteLater()
        self._cards = {}
        self._build()

    # Test affordances
    def card_kinds(self) -> list[str]:
        return list(self._cards.keys())

    def click_card(self, kind: str) -> None:
        if kind in self._cards:
            self._cards[kind].clicked.emit()

    def header_label_text(self) -> str:
        return self._header_label.text()

    def role_chip_text(self) -> str:
        return self._role_chip.text()
```

- [ ] **Step 5: Run test, verify GREEN**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_overview_visual.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add src/locksmith/plugins/designer/widgets/first_person_card.py \
        src/locksmith/plugins/designer/editors/overview.py \
        tests/plugins/designer/test_overview_visual.py
git commit -m "feat(designer): overview page with first-person cards

9-card grid framing each primitive group from the role's own
perspective (I am / I hold / I issue / I do / I respond to / I follow
/ I track / I see / I'm bound by). Clicking a card emits
drilldown_requested(kind); + Add emits add_requested(kind)."
```

---

## Tasks 10-17 overview: per-primitive editor pages

Tasks 10-17 each build one editor page (Commands, Aggregates, Reactions, Workflows, Projections, Rules, Imports, Exports). They share a structural template:

1. **Page class** — `class XEditorPage(QWidget)` composes `PrimitiveEditorShell` + a `_PrimitiveSectionPane` widget that builds the right pane.
2. **Section pane** — a `QWidget` taking the selected entry dict and exposing `set_entry(entry)`, building section frames (Identity, primitive-specific sections, Used-by chip strip).
3. **Rail population** — convert the model's list at the primitive's path to `RailItem` records (color-coded per kind).
4. **Cross-ref wiring** — for the selected item, look up `crossref.consumers_of("<kind>:<id>")` and feed the resulting tuple to the `CrossRefChipStrip`.
5. **Tests** — visual test that loads a fixture, asserts the rail count and the right pane shows the expected sections, then screenshots.

All 8 editors follow this pattern. The code below for each task gives the **specific** sections / fields / colors / fixture additions that differ.

The shared helper `_kind_color_for(kind: str)` is added in Task 10 and reused.

---

## Task 10: Commands editor

**Files:**
- Create: `src/locksmith/plugins/designer/editors/commands.py`
- Test: `tests/plugins/designer/test_commands_editor_visual.py`

The Commands editor's right pane has 4 sections: Identity (label/id), Inputs, Effects (TEL ops + exn sends — color-coded by kind), Pre/post conditions (rules referenced), Used-by.

- [ ] **Step 1: Write the failing visual test (RED)**

Write `tests/plugins/designer/test_commands_editor_visual.py`:

```python
# -*- encoding: utf-8 -*-
"""Commands editor: structural + visual smoke."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest

from locksmith.plugins.designer.editors.commands import CommandsEditorPage
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.crossref import compute_crossrefs


SHOTS_DIR = Path(__file__).parent.parent.parent / "_screenshots" / "designer"


def _grab(w, name):
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    p = SHOTS_DIR / f"{name}.png"
    pix = w.grab()
    assert pix.save(str(p))
    return p


def test_commands_editor_renders_rail_and_sections(qapp, fixture_dir):
    doc = json.loads((fixture_dir / "regulator-grants-carrier-license.json").read_text())
    model = TemplateModel(doc)
    cx = compute_crossrefs(doc)
    page = CommandsEditorPage(model=model, crossrefs=cx)
    page.resize(1100, 800)
    page.show()
    qapp.processEvents()
    QTest.qWait(200)

    assert page.shell.rail_list.count() == 1  # one command in fixture
    assert "Issue License" in page.section_text()
    _grab(page, "commands_editor")
```

- [ ] **Step 2: Run test, verify RED**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_commands_editor_visual.py -v`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Implement CommandsEditorPage**

Write `src/locksmith/plugins/designer/editors/commands.py`:

```python
# -*- encoding: utf-8 -*-
"""CommandsEditorPage: 'I do …' surface.

Sections: Identity · Inputs · Effects · Pre/post-conditions · Used-by.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame, QLabel, QLineEdit, QVBoxLayout, QWidget,
)

from locksmith.plugins.designer.crossref import CrossRefIndex
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.widgets.cross_ref_chip import CrossRefChipStrip
from locksmith.plugins.designer.widgets.kind_rail import RailItem
from locksmith.plugins.designer.widgets.primitive_editor_shell import (
    PrimitiveEditorShell,
)


_TEL_COLOR: dict[str, str] = {
    "issue": "#D97757",   # orange
    "update": "#0ABFB0",  # teal
    "revoke": "#E94B7B",  # pink
}


def _kind_color_for(role_kind: str) -> str:
    return {
        "government": "#0ABFB0",
        "organization": "#0ABFB0",
        "individual": "#D97757",
        "system": "#888888",
        "device": "#888888",
        "agent": "#A36AE6",
    }.get(role_kind, "#888888")


def _section(title: str) -> QFrame:
    frame = QFrame()
    frame.setStyleSheet(
        "QFrame{background:#fff;border:1px solid #e0e3ea;border-radius:6px;}"
    )
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(14, 12, 14, 12)
    lay.setSpacing(8)
    title_label = QLabel(title)
    title_label.setStyleSheet("font-size:12px;font-weight:600;color:#666;")
    lay.addWidget(title_label)
    return frame


class _CommandSectionPane(QWidget):
    def __init__(self, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._crossrefs = crossrefs
        self._build()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        self._identity = _section("Identity")
        self._label_field = QLineEdit()
        self._label_field.setPlaceholderText("Label (e.g. 'Issue License')")
        self._id_field = QLineEdit()
        self._id_field.setReadOnly(True)
        self._identity.layout().addWidget(QLabel("Label"))
        self._identity.layout().addWidget(self._label_field)
        self._identity.layout().addWidget(QLabel("ID"))
        self._identity.layout().addWidget(self._id_field)
        lay.addWidget(self._identity)

        self._inputs = _section("Inputs (parameters this command takes)")
        self._inputs_list = QLabel("(none)")
        self._inputs_list.setStyleSheet("color:#888;font-style:italic;")
        self._inputs.layout().addWidget(self._inputs_list)
        lay.addWidget(self._inputs)

        self._effects = _section("Effects (what fires when this runs)")
        self._effects_list = QLabel("(none)")
        self._effects_list.setStyleSheet("color:#888;font-style:italic;")
        self._effects.layout().addWidget(self._effects_list)
        lay.addWidget(self._effects)

        self._conditions = _section("Pre / post conditions")
        self._conditions_list = QLabel("(none)")
        self._conditions_list.setStyleSheet("color:#888;font-style:italic;")
        self._conditions.layout().addWidget(self._conditions_list)
        lay.addWidget(self._conditions)

        self._used_by = _section("Used by")
        self._chip_strip = CrossRefChipStrip()
        self._used_by.layout().addWidget(self._chip_strip)
        lay.addWidget(self._used_by)
        lay.addStretch(1)

    def set_entry(self, entry: dict[str, Any]) -> None:
        self._label_field.setText(entry.get("label", ""))
        self._id_field.setText(entry.get("id", ""))

        inputs = entry.get("inputs", [])
        if inputs:
            self._inputs_list.setText(
                "\n".join(f"• {i.get('name', '?')}: {i.get('type', '?')}" for i in inputs)
            )
            self._inputs_list.setStyleSheet("color:#444;")
        else:
            self._inputs_list.setText("(none)")
            self._inputs_list.setStyleSheet("color:#888;font-style:italic;")

        effects = entry.get("effects", [])
        if effects:
            lines = []
            for e in effects:
                kind = e.get("kind", "?")
                color = _TEL_COLOR.get(kind, "#444")
                target = e.get("credential_id", e.get("workflow_id", "?"))
                lines.append(
                    f"<span style='color:{color};font-weight:600;'>{kind}</span> → {target}"
                )
            self._effects_list.setText("<br>".join(lines))
            self._effects_list.setStyleSheet("color:#444;")
        else:
            self._effects_list.setText("(none)")
            self._effects_list.setStyleSheet("color:#888;font-style:italic;")

        pre = entry.get("preconditions", [])
        post = entry.get("postconditions", [])
        if pre or post:
            parts = []
            if pre:
                parts.append("Pre: " + ", ".join(pre))
            if post:
                parts.append("Post: " + ", ".join(post))
            self._conditions_list.setText("\n".join(parts))
            self._conditions_list.setStyleSheet("color:#444;")
        else:
            self._conditions_list.setText("(none)")
            self._conditions_list.setStyleSheet("color:#888;font-style:italic;")

        key = f"command:{entry.get('id', '')}"
        self._chip_strip.set_refs(self._crossrefs.consumers_of(key))

    def text_summary(self) -> str:
        return " ".join([
            self._label_field.text(),
            self._effects_list.text(),
            self._conditions_list.text(),
        ])


class CommandsEditorPage(QWidget):
    navigated = Signal(str, str)  # cross-ref navigation

    def __init__(
        self, *, model: TemplateModel, crossrefs: CrossRefIndex, parent=None,
    ):
        super().__init__(parent=parent)
        self._model = model
        self._crossrefs = crossrefs
        items = self._rail_items()
        template_label = model.doc.get("header", {}).get("label", "(untitled)")
        self.shell = PrimitiveEditorShell(
            surface_label="Commands",
            template_label=template_label,
            items=items,
            parent=self,
        )
        self._section_pane = _CommandSectionPane(crossrefs=crossrefs)
        self._section_pane.set_entry(
            self._model.doc.get("commands", [{}])[0] if items else {}
        )
        self.shell.set_right_pane(self._section_pane)
        self.shell.item_selected.connect(self._on_select)
        self._chip_strip = self._section_pane._chip_strip  # for outer wiring
        self._chip_strip.navigated.connect(self.navigated.emit)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.shell)

    def _rail_items(self) -> list[RailItem]:
        role_kind = self._model.doc.get("role", {}).get("kind", "")
        color = _kind_color_for(role_kind)
        items = []
        for c in self._model.doc.get("commands", []):
            items.append(RailItem(
                id=c.get("id", ""),
                label=c.get("label") or c.get("id") or "(unnamed)",
                kind_color=color,
                has_errors=False,
            ))
        return items

    def _on_select(self, item_id: str) -> None:
        for c in self._model.doc.get("commands", []):
            if c.get("id") == item_id:
                self._section_pane.set_entry(c)
                return

    def section_text(self) -> str:
        return self._section_pane.text_summary()
```

- [ ] **Step 4: Run test, verify GREEN**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_commands_editor_visual.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/editors/commands.py \
        tests/plugins/designer/test_commands_editor_visual.py
git commit -m "feat(designer): commands editor

'I do …' surface. Right pane: Identity / Inputs / Effects (TEL-color-
coded) / Pre-post conditions / Used-by chip strip. Adds _kind_color_for
helper reused by sibling editors."
```

---

## Task 11: Aggregates editor

**Files:**
- Create: `src/locksmith/plugins/designer/editors/aggregates.py`
- Test: `tests/plugins/designer/test_aggregates_editor_visual.py`

Right-pane sections: Identity · Source events (list) · Fold expression (text area) · Cardinality (singleton / collection radio) · Used-by.

- [ ] **Step 1: Add a fixture aggregate to the carrier fixture**

Modify `tests/plugins/designer/fixtures/carrier-license-application.json` — set `"aggregates"`:

```json
"aggregates": [
  {
    "id": "app-status",
    "label": "Application Status",
    "source_event_kinds": ["application.submitted", "application.approved"],
    "fold_expr": "events.last_or_default('pending').kind",
    "cardinality": "singleton"
  }
]
```

- [ ] **Step 2: Write the failing visual test (RED)**

Write `tests/plugins/designer/test_aggregates_editor_visual.py`:

```python
# -*- encoding: utf-8 -*-
"""Aggregates editor visual smoke test."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest

from locksmith.plugins.designer.editors.aggregates import AggregatesEditorPage
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.crossref import compute_crossrefs


SHOTS_DIR = Path(__file__).parent.parent.parent / "_screenshots" / "designer"


def test_aggregates_editor_renders(qapp, fixture_dir):
    doc = json.loads((fixture_dir / "carrier-license-application.json").read_text())
    model = TemplateModel(doc)
    page = AggregatesEditorPage(model=model, crossrefs=compute_crossrefs(doc))
    page.resize(1100, 800)
    page.show()
    qapp.processEvents()
    QTest.qWait(150)
    assert page.shell.rail_list.count() == 1
    text = page.section_text()
    assert "Application Status" in text or "app-status" in text
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    page.grab().save(str(SHOTS_DIR / "aggregates_editor.png"))
```

- [ ] **Step 3: Run test, verify RED**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_aggregates_editor_visual.py -v`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 4: Implement AggregatesEditorPage**

Write `src/locksmith/plugins/designer/editors/aggregates.py`:

```python
# -*- encoding: utf-8 -*-
"""AggregatesEditorPage: 'I track …' surface."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QLabel, QLineEdit, QPlainTextEdit, QRadioButton, QVBoxLayout,
    QButtonGroup, QHBoxLayout, QWidget,
)

from locksmith.plugins.designer.crossref import CrossRefIndex
from locksmith.plugins.designer.editors.commands import _kind_color_for, _section
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.widgets.cross_ref_chip import CrossRefChipStrip
from locksmith.plugins.designer.widgets.kind_rail import RailItem
from locksmith.plugins.designer.widgets.primitive_editor_shell import (
    PrimitiveEditorShell,
)


class _AggregateSectionPane(QWidget):
    def __init__(self, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._crossrefs = crossrefs
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        self._identity = _section("Identity")
        self._label = QLineEdit()
        self._id = QLineEdit(); self._id.setReadOnly(True)
        self._identity.layout().addWidget(QLabel("Label"))
        self._identity.layout().addWidget(self._label)
        self._identity.layout().addWidget(QLabel("ID"))
        self._identity.layout().addWidget(self._id)
        lay.addWidget(self._identity)

        self._events = _section("Source events")
        self._events_list = QLabel("(none)")
        self._events_list.setStyleSheet("color:#888;font-style:italic;")
        self._events.layout().addWidget(self._events_list)
        lay.addWidget(self._events)

        self._fold = _section("Fold expression (UEL/1.0)")
        self._fold_text = QPlainTextEdit()
        self._fold_text.setPlaceholderText(
            "events.last_or_default('pending').kind"
        )
        self._fold_text.setFixedHeight(80)
        self._fold.layout().addWidget(self._fold_text)
        lay.addWidget(self._fold)

        self._card = _section("Cardinality")
        card_row = QHBoxLayout()
        self._radio_single = QRadioButton("Singleton")
        self._radio_collection = QRadioButton("Collection")
        group = QButtonGroup(self)
        group.addButton(self._radio_single)
        group.addButton(self._radio_collection)
        card_row.addWidget(self._radio_single)
        card_row.addWidget(self._radio_collection)
        card_row.addStretch(1)
        self._card.layout().addLayout(card_row)
        lay.addWidget(self._card)

        self._used_by = _section("Used by")
        self.chip_strip = CrossRefChipStrip()
        self._used_by.layout().addWidget(self.chip_strip)
        lay.addWidget(self._used_by)
        lay.addStretch(1)

    def set_entry(self, entry: dict[str, Any]) -> None:
        self._label.setText(entry.get("label", ""))
        self._id.setText(entry.get("id", ""))
        evs = entry.get("source_event_kinds", [])
        if evs:
            self._events_list.setText("\n".join(f"• {e}" for e in evs))
            self._events_list.setStyleSheet("color:#444;")
        else:
            self._events_list.setText("(none)")
            self._events_list.setStyleSheet("color:#888;font-style:italic;")
        self._fold_text.setPlainText(entry.get("fold_expr", ""))
        if entry.get("cardinality") == "collection":
            self._radio_collection.setChecked(True)
        else:
            self._radio_single.setChecked(True)
        key = f"aggregate:{entry.get('id', '')}"
        self.chip_strip.set_refs(self._crossrefs.consumers_of(key))

    def text_summary(self) -> str:
        return f"{self._label.text()} {self._id.text()} {self._fold_text.toPlainText()}"


class AggregatesEditorPage(QWidget):
    navigated = Signal(str, str)

    def __init__(self, *, model: TemplateModel, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._model = model
        items = [
            RailItem(
                id=a.get("id", ""),
                label=a.get("label") or a.get("id") or "(unnamed)",
                kind_color=_kind_color_for(model.doc.get("role", {}).get("kind", "")),
                has_errors=False,
            )
            for a in model.doc.get("aggregates", [])
        ]
        self.shell = PrimitiveEditorShell(
            surface_label="Aggregates",
            template_label=model.doc.get("header", {}).get("label", "(untitled)"),
            items=items,
            parent=self,
        )
        self._pane = _AggregateSectionPane(crossrefs=crossrefs)
        if items:
            self._pane.set_entry(model.doc["aggregates"][0])
        self.shell.set_right_pane(self._pane)
        self.shell.item_selected.connect(self._on_select)
        self._pane.chip_strip.navigated.connect(self.navigated.emit)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.shell)

    def _on_select(self, item_id: str) -> None:
        for a in self._model.doc.get("aggregates", []):
            if a.get("id") == item_id:
                self._pane.set_entry(a)
                return

    def section_text(self) -> str:
        return self._pane.text_summary()
```

- [ ] **Step 5: Run test, verify GREEN**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_aggregates_editor_visual.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/locksmith/plugins/designer/editors/aggregates.py \
        tests/plugins/designer/test_aggregates_editor_visual.py \
        tests/plugins/designer/fixtures/carrier-license-application.json
git commit -m "feat(designer): aggregates editor

'I track …' surface. Right pane: Identity / Source events / Fold
expression (UEL/1.0 text area) / Cardinality (singleton vs collection)
/ Used-by. Carrier fixture extended with a sample aggregate."
```

---

## Task 12: Reactions editor

**Files:**
- Create: `src/locksmith/plugins/designer/editors/reactions.py`
- Test: `tests/plugins/designer/test_reactions_editor_visual.py`

Right-pane sections: Identity · Trigger (incoming exn kind / IPEX verb / TEL transition) · Effect (target command + projection) · Used-by.

- [ ] **Step 1: Add a reaction to the carrier fixture**

Modify `tests/plugins/designer/fixtures/carrier-license-application.json` — set `"reactions"`:

```json
"reactions": [
  {
    "id": "on-grant",
    "label": "License Grant Received",
    "trigger": {"kind": "ipex_verb", "verb": "grant", "credential_id": "doi-charter"},
    "effect": {"command_id": null, "projection_id": null}
  }
]
```

- [ ] **Step 2: Write the failing visual test (RED)**

Write `tests/plugins/designer/test_reactions_editor_visual.py`:

```python
# -*- encoding: utf-8 -*-
"""Reactions editor visual smoke test."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest

from locksmith.plugins.designer.editors.reactions import ReactionsEditorPage
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.crossref import compute_crossrefs


SHOTS_DIR = Path(__file__).parent.parent.parent / "_screenshots" / "designer"


def test_reactions_editor_renders(qapp, fixture_dir):
    doc = json.loads((fixture_dir / "carrier-license-application.json").read_text())
    model = TemplateModel(doc)
    page = ReactionsEditorPage(model=model, crossrefs=compute_crossrefs(doc))
    page.resize(1100, 800)
    page.show()
    qapp.processEvents()
    QTest.qWait(150)
    assert page.shell.rail_list.count() == 1
    text = page.section_text()
    assert "grant" in text.lower()
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    page.grab().save(str(SHOTS_DIR / "reactions_editor.png"))
```

- [ ] **Step 3: Run test, verify RED**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_reactions_editor_visual.py -v`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 4: Implement ReactionsEditorPage**

Write `src/locksmith/plugins/designer/editors/reactions.py`:

```python
# -*- encoding: utf-8 -*-
"""ReactionsEditorPage: 'I respond to …' surface."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget,
)

from locksmith.plugins.designer.crossref import CrossRefIndex
from locksmith.plugins.designer.editors.commands import _kind_color_for, _section
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.widgets.cross_ref_chip import CrossRefChipStrip
from locksmith.plugins.designer.widgets.kind_rail import RailItem
from locksmith.plugins.designer.widgets.primitive_editor_shell import (
    PrimitiveEditorShell,
)


class _ReactionSectionPane(QWidget):
    def __init__(self, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._crossrefs = crossrefs
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        self._identity = _section("Identity")
        self._label = QLineEdit()
        self._id = QLineEdit(); self._id.setReadOnly(True)
        self._identity.layout().addWidget(QLabel("Label"))
        self._identity.layout().addWidget(self._label)
        self._identity.layout().addWidget(QLabel("ID"))
        self._identity.layout().addWidget(self._id)
        lay.addWidget(self._identity)

        self._trigger = _section("Trigger (what fires this reaction)")
        self._trigger_summary = QLabel("(none)")
        self._trigger_summary.setStyleSheet("color:#444;")
        self._trigger.layout().addWidget(self._trigger_summary)
        lay.addWidget(self._trigger)

        self._effect = _section("Effect (what happens when triggered)")
        self._effect_summary = QLabel("(none)")
        self._effect_summary.setStyleSheet("color:#444;")
        self._effect.layout().addWidget(self._effect_summary)
        lay.addWidget(self._effect)

        self._used_by = _section("Used by")
        self.chip_strip = CrossRefChipStrip()
        self._used_by.layout().addWidget(self.chip_strip)
        lay.addWidget(self._used_by)
        lay.addStretch(1)

    def set_entry(self, entry: dict[str, Any]) -> None:
        self._label.setText(entry.get("label", ""))
        self._id.setText(entry.get("id", ""))
        trigger = entry.get("trigger", {})
        tkind = trigger.get("kind", "?")
        if tkind == "ipex_verb":
            self._trigger_summary.setText(
                f"IPEX verb <b>{trigger.get('verb', '?')}</b> "
                f"on credential <code>{trigger.get('credential_id', '?')}</code>"
            )
        elif tkind == "tel_transition":
            self._trigger_summary.setText(
                f"TEL transition <b>{trigger.get('from_state', '?')} → "
                f"{trigger.get('to_state', '?')}</b>"
            )
        elif tkind == "exn_kind":
            self._trigger_summary.setText(
                f"exn kind <b>{trigger.get('exn_kind', '?')}</b>"
            )
        else:
            self._trigger_summary.setText("(unset)")

        effect = entry.get("effect", {})
        cmd_id = effect.get("command_id")
        proj_id = effect.get("projection_id")
        parts = []
        if cmd_id:
            parts.append(f"runs command <b>{cmd_id}</b>")
        if proj_id:
            parts.append(f"updates projection <b>{proj_id}</b>")
        self._effect_summary.setText(", ".join(parts) if parts else "(unset)")

        key = f"reaction:{entry.get('id', '')}"
        self.chip_strip.set_refs(self._crossrefs.consumers_of(key))

    def text_summary(self) -> str:
        return self._trigger_summary.text() + " " + self._effect_summary.text()


class ReactionsEditorPage(QWidget):
    navigated = Signal(str, str)

    def __init__(self, *, model: TemplateModel, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._model = model
        items = [
            RailItem(
                id=r.get("id", ""),
                label=r.get("label") or r.get("id") or "(unnamed)",
                kind_color=_kind_color_for(model.doc.get("role", {}).get("kind", "")),
                has_errors=False,
            )
            for r in model.doc.get("reactions", [])
        ]
        self.shell = PrimitiveEditorShell(
            surface_label="Reactions",
            template_label=model.doc.get("header", {}).get("label", "(untitled)"),
            items=items,
            parent=self,
        )
        self._pane = _ReactionSectionPane(crossrefs=crossrefs)
        if items:
            self._pane.set_entry(model.doc["reactions"][0])
        self.shell.set_right_pane(self._pane)
        self.shell.item_selected.connect(self._on_select)
        self._pane.chip_strip.navigated.connect(self.navigated.emit)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.shell)

    def _on_select(self, item_id: str) -> None:
        for r in self._model.doc.get("reactions", []):
            if r.get("id") == item_id:
                self._pane.set_entry(r)
                return

    def section_text(self) -> str:
        return self._pane.text_summary()
```

- [ ] **Step 5: Run test, verify GREEN**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_reactions_editor_visual.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/locksmith/plugins/designer/editors/reactions.py \
        tests/plugins/designer/test_reactions_editor_visual.py \
        tests/plugins/designer/fixtures/carrier-license-application.json
git commit -m "feat(designer): reactions editor

'I respond to …' surface. Right pane: Identity / Trigger (IPEX verb /
TEL transition / exn kind) / Effect (command + projection) / Used-by."
```

---

## Task 13: Workflows editor (with SwimlaneDiagram)

**Files:**
- Create: `src/locksmith/plugins/designer/widgets/swimlane_diagram.py`
- Create: `src/locksmith/plugins/designer/editors/workflows.py`
- Test: `tests/plugins/designer/test_workflows_editor_visual.py`

Right-pane sections: Identity · Roles involved · Swimlane SVG diagram · Step list · Used-by.

- [ ] **Step 1: Extend the regulator fixture with a real workflow**

Modify `tests/plugins/designer/fixtures/regulator-grants-carrier-license.json` — replace the `"workflows"` array:

```json
"workflows": [
  {
    "id": "review-app",
    "label": "Review Application",
    "roles_involved": ["state-doi", "carrier"],
    "steps": [
      {"id": "s1", "actor_role": "carrier", "kind": "ipex.apply",
       "label": "Carrier applies", "rule_refs": [], "command_id": null},
      {"id": "s2", "actor_role": "state-doi", "kind": "ipex.offer",
       "label": "DOI offers license terms", "rule_refs": [], "command_id": null},
      {"id": "s3", "actor_role": "carrier", "kind": "ipex.agree",
       "label": "Carrier accepts terms", "rule_refs": [], "command_id": null},
      {"id": "s4", "actor_role": "state-doi", "kind": "ipex.grant",
       "label": "DOI grants license", "rule_refs": [],
       "command_id": "issue-license"}
    ]
  }
]
```

- [ ] **Step 2: Write the failing visual test (RED)**

Write `tests/plugins/designer/test_workflows_editor_visual.py`:

```python
# -*- encoding: utf-8 -*-
"""Workflows editor visual smoke test."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest

from locksmith.plugins.designer.editors.workflows import WorkflowsEditorPage
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.crossref import compute_crossrefs


SHOTS_DIR = Path(__file__).parent.parent.parent / "_screenshots" / "designer"


def test_workflows_editor_renders_swimlane(qapp, fixture_dir):
    doc = json.loads((fixture_dir / "regulator-grants-carrier-license.json").read_text())
    model = TemplateModel(doc)
    page = WorkflowsEditorPage(model=model, crossrefs=compute_crossrefs(doc))
    page.resize(1200, 800)
    page.show()
    qapp.processEvents()
    QTest.qWait(200)
    assert page.shell.rail_list.count() == 1
    assert page.swimlane_step_count() == 4
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    page.grab().save(str(SHOTS_DIR / "workflows_editor.png"))
```

- [ ] **Step 3: Run test, verify RED**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_workflows_editor_visual.py -v`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 4: Implement SwimlaneDiagram**

Write `src/locksmith/plugins/designer/widgets/swimlane_diagram.py`:

```python
# -*- encoding: utf-8 -*-
"""SwimlaneDiagram: self-vs-counterparty workflow visualization.

Renders the workflow's steps as a swim-lane diagram with each step in
its actor's lane and an arrow from the previous step. Done with
QGraphicsScene primitives — no external SVG lib needed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPen
from PySide6.QtWidgets import (
    QGraphicsScene, QGraphicsView,
)


_VERB_COLOR: dict[str, str] = {
    "ipex.apply": "#6A8FE6",
    "ipex.offer": "#A36AE6",
    "ipex.agree": "#0ABFB0",
    "ipex.grant": "#D97757",
    "ipex.admit": "#1B5E20",
    "ipex.spurn": "#9B1D1D",
}


@dataclass
class SwimlaneStep:
    label: str
    actor_role: str
    kind: str
    command_id: str | None


class SwimlaneDiagram(QGraphicsView):
    LANE_HEIGHT = 80
    STEP_WIDTH = 160
    STEP_HEIGHT = 50
    STEP_GAP = 30

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setRenderHint(self.renderHints() | self.renderHints())
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setStyleSheet("background:#fff;border:1px solid #e0e3ea;border-radius:6px;")
        self._step_count = 0

    @property
    def step_count(self) -> int:
        return self._step_count

    def render(self, *, lanes: list[str], steps: list[SwimlaneStep]) -> None:
        self._scene.clear()
        self._step_count = len(steps)

        lane_pen = QPen(QColor("#e0e3ea"))
        text_pen = QPen(QColor("#666"))
        label_font = QFont(); label_font.setPointSize(9); label_font.setBold(True)

        # Lane headers + horizontal dividers
        for i, lane in enumerate(lanes):
            y = i * self.LANE_HEIGHT
            self._scene.addRect(
                QRectF(0, y, max(800, len(steps) * (self.STEP_WIDTH + self.STEP_GAP)),
                       self.LANE_HEIGHT),
                lane_pen, QBrush(QColor("#fafbfc") if i % 2 == 0 else QColor("#fff")),
            )
            text = self._scene.addText(lane, label_font)
            text.setDefaultTextColor(QColor("#666"))
            text.setPos(8, y + 4)

        # Steps
        lane_index = {lane: i for i, lane in enumerate(lanes)}
        for j, step in enumerate(steps):
            x = 110 + j * (self.STEP_WIDTH + self.STEP_GAP)
            y = lane_index.get(step.actor_role, 0) * self.LANE_HEIGHT + 15
            color = _VERB_COLOR.get(step.kind, "#888888")
            box = self._scene.addRect(
                QRectF(x, y, self.STEP_WIDTH, self.STEP_HEIGHT),
                QPen(QColor(color), 2), QBrush(QColor(color).lighter(180)),
            )
            label_font.setBold(False)
            t = self._scene.addText(f"{step.kind}\n{step.label}", label_font)
            t.setDefaultTextColor(QColor("#1A1C20"))
            t.setPos(x + 6, y + 4)

            # Arrow from previous step
            if j > 0:
                prev_x = 110 + (j - 1) * (self.STEP_WIDTH + self.STEP_GAP) + self.STEP_WIDTH
                prev_y = (lane_index.get(steps[j - 1].actor_role, 0) * self.LANE_HEIGHT
                          + 15 + self.STEP_HEIGHT // 2)
                cur_y = y + self.STEP_HEIGHT // 2
                arrow_pen = QPen(QColor("#888"), 1)
                self._scene.addLine(prev_x, prev_y, x, cur_y, arrow_pen)
```

- [ ] **Step 5: Implement WorkflowsEditorPage**

Write `src/locksmith/plugins/designer/editors/workflows.py`:

```python
# -*- encoding: utf-8 -*-
"""WorkflowsEditorPage: 'I follow …' surface."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget,
)

from locksmith.plugins.designer.crossref import CrossRefIndex
from locksmith.plugins.designer.editors.commands import _kind_color_for, _section
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.widgets.cross_ref_chip import CrossRefChipStrip
from locksmith.plugins.designer.widgets.kind_rail import RailItem
from locksmith.plugins.designer.widgets.primitive_editor_shell import (
    PrimitiveEditorShell,
)
from locksmith.plugins.designer.widgets.swimlane_diagram import (
    SwimlaneDiagram, SwimlaneStep,
)


class _WorkflowSectionPane(QWidget):
    def __init__(self, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._crossrefs = crossrefs
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        self._identity = _section("Identity")
        self._label = QLineEdit()
        self._id = QLineEdit(); self._id.setReadOnly(True)
        self._identity.layout().addWidget(QLabel("Label"))
        self._identity.layout().addWidget(self._label)
        self._identity.layout().addWidget(QLabel("ID"))
        self._identity.layout().addWidget(self._id)
        lay.addWidget(self._identity)

        self._roles = _section("Roles involved")
        self._roles_label = QLabel("(none)")
        self._roles_label.setStyleSheet("color:#444;")
        self._roles.layout().addWidget(self._roles_label)
        lay.addWidget(self._roles)

        self._diagram_section = _section("Swimlane diagram")
        self.diagram = SwimlaneDiagram()
        self.diagram.setFixedHeight(220)
        self._diagram_section.layout().addWidget(self.diagram)
        lay.addWidget(self._diagram_section)

        self._steps = _section("Steps")
        self._steps_list = QLabel("(none)")
        self._steps_list.setStyleSheet("color:#444;")
        self._steps.layout().addWidget(self._steps_list)
        lay.addWidget(self._steps)

        self._used_by = _section("Used by")
        self.chip_strip = CrossRefChipStrip()
        self._used_by.layout().addWidget(self.chip_strip)
        lay.addWidget(self._used_by)
        lay.addStretch(1)

    def set_entry(self, entry: dict[str, Any]) -> None:
        self._label.setText(entry.get("label", ""))
        self._id.setText(entry.get("id", ""))
        roles = entry.get("roles_involved", [])
        self._roles_label.setText(", ".join(roles) if roles else "(none)")
        steps = entry.get("steps", [])
        if steps:
            self._steps_list.setText("\n".join(
                f"{i+1}. {s.get('actor_role', '?')}: {s.get('label', '')}"
                for i, s in enumerate(steps)
            ))
        else:
            self._steps_list.setText("(none)")
        self.diagram.render(
            lanes=roles or ["(unset)"],
            steps=[SwimlaneStep(
                label=s.get("label", ""),
                actor_role=s.get("actor_role", ""),
                kind=s.get("kind", "exn"),
                command_id=s.get("command_id"),
            ) for s in steps],
        )
        key = f"workflow:{entry.get('id', '')}"
        self.chip_strip.set_refs(self._crossrefs.consumers_of(key))


class WorkflowsEditorPage(QWidget):
    navigated = Signal(str, str)

    def __init__(self, *, model: TemplateModel, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._model = model
        items = [
            RailItem(
                id=w.get("id", ""),
                label=w.get("label") or w.get("id") or "(unnamed)",
                kind_color=_kind_color_for(model.doc.get("role", {}).get("kind", "")),
                has_errors=False,
            )
            for w in model.doc.get("workflows", [])
        ]
        self.shell = PrimitiveEditorShell(
            surface_label="Workflows",
            template_label=model.doc.get("header", {}).get("label", "(untitled)"),
            items=items,
            parent=self,
        )
        self._pane = _WorkflowSectionPane(crossrefs=crossrefs)
        if items:
            self._pane.set_entry(model.doc["workflows"][0])
        self.shell.set_right_pane(self._pane)
        self.shell.item_selected.connect(self._on_select)
        self._pane.chip_strip.navigated.connect(self.navigated.emit)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.shell)

    def _on_select(self, item_id: str) -> None:
        for w in self._model.doc.get("workflows", []):
            if w.get("id") == item_id:
                self._pane.set_entry(w)
                return

    def swimlane_step_count(self) -> int:
        return self._pane.diagram.step_count
```

- [ ] **Step 6: Run test, verify GREEN**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_workflows_editor_visual.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/locksmith/plugins/designer/widgets/swimlane_diagram.py \
        src/locksmith/plugins/designer/editors/workflows.py \
        tests/plugins/designer/test_workflows_editor_visual.py \
        tests/plugins/designer/fixtures/regulator-grants-carrier-license.json
git commit -m "feat(designer): workflows editor + swimlane diagram

'I follow …' surface. Right pane: Identity / Roles involved /
Swimlane SVG diagram (color-coded by IPEX verb) / Steps / Used-by.
QGraphicsScene-based diagram avoids external SVG dependency."
```

---

## Task 14: Projections editor (with live preview)

**Files:**
- Create: `src/locksmith/plugins/designer/editors/projections.py`
- Test: `tests/plugins/designer/test_projections_editor_visual.py`

Right-pane sections: Identity · Source aggregates / events · Render template (UEL expression) · Live preview · Used-by.

Open question §9.2 in the spec: a UEL/1.0 evaluator may not exist. **v1 falls back** — if no evaluator can be imported, the live-preview pane shows the rendered template text and a note "evaluator pending".

- [ ] **Step 1: Add a projection to the carrier fixture**

Modify `tests/plugins/designer/fixtures/carrier-license-application.json` — set `"projections"`:

```json
"projections": [
  {
    "id": "status-banner",
    "label": "Application Status Banner",
    "source_aggregate_ids": ["app-status"],
    "render": "'Your application is currently: ' + agg.app-status"
  }
]
```

- [ ] **Step 2: Write the failing visual test (RED)**

Write `tests/plugins/designer/test_projections_editor_visual.py`:

```python
# -*- encoding: utf-8 -*-
"""Projections editor visual smoke test."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest

from locksmith.plugins.designer.editors.projections import ProjectionsEditorPage
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.crossref import compute_crossrefs


SHOTS_DIR = Path(__file__).parent.parent.parent / "_screenshots" / "designer"


def test_projections_editor_renders(qapp, fixture_dir):
    doc = json.loads((fixture_dir / "carrier-license-application.json").read_text())
    model = TemplateModel(doc)
    page = ProjectionsEditorPage(model=model, crossrefs=compute_crossrefs(doc))
    page.resize(1200, 800)
    page.show()
    qapp.processEvents()
    QTest.qWait(150)
    assert page.shell.rail_list.count() == 1
    # Live preview pane should be visible whether or not evaluator exists.
    assert page.preview_visible() is True
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    page.grab().save(str(SHOTS_DIR / "projections_editor.png"))


def test_projections_editor_preview_fallback_text_when_no_evaluator(qapp, fixture_dir):
    doc = json.loads((fixture_dir / "carrier-license-application.json").read_text())
    model = TemplateModel(doc)
    page = ProjectionsEditorPage(model=model, crossrefs=compute_crossrefs(doc))
    page.show()
    qapp.processEvents()
    text = page.preview_text()
    # The fallback explicitly mentions the pending evaluator.
    assert "evaluator pending" in text.lower() or "Your application" in text
```

- [ ] **Step 3: Run test, verify RED**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_projections_editor_visual.py -v`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 4: Implement ProjectionsEditorPage**

Write `src/locksmith/plugins/designer/editors/projections.py`:

```python
# -*- encoding: utf-8 -*-
"""ProjectionsEditorPage: 'I see …' surface.

If a UEL/1.0 evaluator is importable from locksmith.uel.evaluator, the
live preview renders sample events through it. Otherwise it shows the
expression text and a 'evaluator pending' note (open spec question 9.2).
"""
from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QLabel, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget,
)

from locksmith.plugins.designer.crossref import CrossRefIndex
from locksmith.plugins.designer.editors.commands import _kind_color_for, _section
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.widgets.cross_ref_chip import CrossRefChipStrip
from locksmith.plugins.designer.widgets.kind_rail import RailItem
from locksmith.plugins.designer.widgets.primitive_editor_shell import (
    PrimitiveEditorShell,
)


def _resolve_uel_evaluator() -> Callable[[str, dict], str] | None:
    try:
        from locksmith.uel.evaluator import evaluate  # type: ignore
        return evaluate
    except Exception:
        return None


class _ProjectionSectionPane(QWidget):
    def __init__(self, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._crossrefs = crossrefs
        self._evaluator = _resolve_uel_evaluator()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        self._identity = _section("Identity")
        self._label = QLineEdit()
        self._id = QLineEdit(); self._id.setReadOnly(True)
        self._identity.layout().addWidget(QLabel("Label"))
        self._identity.layout().addWidget(self._label)
        self._identity.layout().addWidget(QLabel("ID"))
        self._identity.layout().addWidget(self._id)
        lay.addWidget(self._identity)

        self._source = _section("Source aggregates")
        self._source_label = QLabel("(none)")
        self._source_label.setStyleSheet("color:#444;")
        self._source.layout().addWidget(self._source_label)
        lay.addWidget(self._source)

        self._render = _section("Render expression (UEL/1.0)")
        self._render_text = QPlainTextEdit()
        self._render_text.setFixedHeight(60)
        self._render.layout().addWidget(self._render_text)
        lay.addWidget(self._render)

        self._preview = _section("Live preview")
        self._preview_label = QLabel("(no preview)")
        self._preview_label.setWordWrap(True)
        self._preview_label.setStyleSheet(
            "background:#f6f7f9;color:#444;padding:8px;border-radius:4px;"
        )
        self._preview.layout().addWidget(self._preview_label)
        lay.addWidget(self._preview)

        self._used_by = _section("Used by")
        self.chip_strip = CrossRefChipStrip()
        self._used_by.layout().addWidget(self.chip_strip)
        lay.addWidget(self._used_by)
        lay.addStretch(1)

        self._render_text.textChanged.connect(self._update_preview)

    def set_entry(self, entry: dict[str, Any]) -> None:
        self._label.setText(entry.get("label", ""))
        self._id.setText(entry.get("id", ""))
        sources = entry.get("source_aggregate_ids", [])
        self._source_label.setText(", ".join(sources) if sources else "(none)")
        self._render_text.setPlainText(entry.get("render", ""))
        self._update_preview()
        key = f"projection:{entry.get('id', '')}"
        self.chip_strip.set_refs(self._crossrefs.consumers_of(key))

    def _update_preview(self) -> None:
        expr = self._render_text.toPlainText().strip()
        if not expr:
            self._preview_label.setText("(no expression)")
            return
        if self._evaluator is None:
            self._preview_label.setText(
                f"<i>evaluator pending — showing raw expression:</i><br>"
                f"<code>{expr}</code>"
            )
            return
        try:
            sample_context = {"agg": {}, "events": []}
            self._preview_label.setText(str(self._evaluator(expr, sample_context)))
        except Exception as e:
            self._preview_label.setText(f"<span style='color:#9b1d1d;'>{e}</span>")

    def preview_text(self) -> str:
        return self._preview_label.text()


class ProjectionsEditorPage(QWidget):
    navigated = Signal(str, str)

    def __init__(self, *, model: TemplateModel, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._model = model
        items = [
            RailItem(
                id=p.get("id", ""),
                label=p.get("label") or p.get("id") or "(unnamed)",
                kind_color=_kind_color_for(model.doc.get("role", {}).get("kind", "")),
                has_errors=False,
            )
            for p in model.doc.get("projections", [])
        ]
        self.shell = PrimitiveEditorShell(
            surface_label="Projections",
            template_label=model.doc.get("header", {}).get("label", "(untitled)"),
            items=items,
            parent=self,
        )
        self._pane = _ProjectionSectionPane(crossrefs=crossrefs)
        if items:
            self._pane.set_entry(model.doc["projections"][0])
        self.shell.set_right_pane(self._pane)
        self.shell.item_selected.connect(self._on_select)
        self._pane.chip_strip.navigated.connect(self.navigated.emit)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.shell)

    def _on_select(self, item_id: str) -> None:
        for p in self._model.doc.get("projections", []):
            if p.get("id") == item_id:
                self._pane.set_entry(p)
                return

    def preview_visible(self) -> bool:
        return self._pane._preview_label.isVisible()

    def preview_text(self) -> str:
        return self._pane.preview_text()
```

- [ ] **Step 5: Run test, verify GREEN**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_projections_editor_visual.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add src/locksmith/plugins/designer/editors/projections.py \
        tests/plugins/designer/test_projections_editor_visual.py \
        tests/plugins/designer/fixtures/carrier-license-application.json
git commit -m "feat(designer): projections editor + UEL fallback preview

'I see …' surface. Right pane: Identity / Source aggregates / Render
expression / Live preview / Used-by. Preview pane gracefully falls
back to showing the raw expression when no UEL/1.0 evaluator is
importable (open spec question 9.2)."
```

---

## Task 15: Rules editor (typed by kind)

**Files:**
- Create: `src/locksmith/plugins/designer/editors/rules.py`
- Test: `tests/plugins/designer/test_rules_editor_visual.py`

Right-pane sections: Identity · Kind (legal-prose / predicate / computation / validation / behavioural-expectation — radio group, kind-color-coded) · Body · Attaches to (which command / workflow / credential) · Used-by.

- [ ] **Step 1: Add rules to the regulator fixture**

Modify `tests/plugins/designer/fixtures/regulator-grants-carrier-license.json` — set `"rules"`:

```json
"rules": [
  {"id": "solvency", "label": "Min Capital $100M", "kind": "predicate",
   "body": "applicant.capital_usd >= 100_000_000"},
  {"id": "fit-and-proper", "label": "Fit & Proper Persons", "kind": "validation",
   "body": "All officers must pass background check (RCW 48.05.030)"}
]
```

- [ ] **Step 2: Write the failing visual test (RED)**

Write `tests/plugins/designer/test_rules_editor_visual.py`:

```python
# -*- encoding: utf-8 -*-
"""Rules editor visual smoke test."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest

from locksmith.plugins.designer.editors.rules import RulesEditorPage
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.crossref import compute_crossrefs


SHOTS_DIR = Path(__file__).parent.parent.parent / "_screenshots" / "designer"


def test_rules_editor_renders_typed_rail(qapp, fixture_dir):
    doc = json.loads((fixture_dir / "regulator-grants-carrier-license.json").read_text())
    model = TemplateModel(doc)
    page = RulesEditorPage(model=model, crossrefs=compute_crossrefs(doc))
    page.resize(1100, 800)
    page.show()
    qapp.processEvents()
    QTest.qWait(150)
    assert page.shell.rail_list.count() == 2
    text = page.section_text()
    assert "predicate" in text.lower() or "Min Capital" in text
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    page.grab().save(str(SHOTS_DIR / "rules_editor.png"))
```

- [ ] **Step 3: Run test, verify RED**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_rules_editor_visual.py -v`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 4: Implement RulesEditorPage**

Write `src/locksmith/plugins/designer/editors/rules.py`:

```python
# -*- encoding: utf-8 -*-
"""RulesEditorPage: 'I'm bound by …' surface.

Rules are color-coded by kind in the rail:
  legal-prose → indigo, predicate → teal, computation → amber,
  validation → red, behavioural-expectation → purple.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QLabel, QLineEdit, QPlainTextEdit, QVBoxLayout, QComboBox, QWidget,
)

from locksmith.plugins.designer.crossref import CrossRefIndex
from locksmith.plugins.designer.editors.commands import _section
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.widgets.cross_ref_chip import CrossRefChipStrip
from locksmith.plugins.designer.widgets.kind_rail import RailItem
from locksmith.plugins.designer.widgets.primitive_editor_shell import (
    PrimitiveEditorShell,
)


_RULE_KIND_COLOR: dict[str, str] = {
    "legal-prose": "#4A4FCE",
    "predicate": "#0ABFB0",
    "computation": "#D9A04F",
    "validation": "#E94B4B",
    "behavioural-expectation": "#A36AE6",
}

_RULE_KINDS: list[str] = [
    "legal-prose", "predicate", "computation", "validation",
    "behavioural-expectation",
]


class _RuleSectionPane(QWidget):
    def __init__(self, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._crossrefs = crossrefs
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        self._identity = _section("Identity")
        self._label = QLineEdit()
        self._id = QLineEdit(); self._id.setReadOnly(True)
        self._identity.layout().addWidget(QLabel("Label"))
        self._identity.layout().addWidget(self._label)
        self._identity.layout().addWidget(QLabel("ID"))
        self._identity.layout().addWidget(self._id)
        lay.addWidget(self._identity)

        self._kind = _section("Kind")
        self._kind_combo = QComboBox()
        for k in _RULE_KINDS:
            self._kind_combo.addItem(k)
        self._kind.layout().addWidget(self._kind_combo)
        lay.addWidget(self._kind)

        self._body = _section("Body")
        self._body_text = QPlainTextEdit()
        self._body_text.setFixedHeight(100)
        self._body.layout().addWidget(self._body_text)
        lay.addWidget(self._body)

        self._used_by = _section("Used by")
        self.chip_strip = CrossRefChipStrip()
        self._used_by.layout().addWidget(self.chip_strip)
        lay.addWidget(self._used_by)
        lay.addStretch(1)

    def set_entry(self, entry: dict[str, Any]) -> None:
        self._label.setText(entry.get("label", ""))
        self._id.setText(entry.get("id", ""))
        kind = entry.get("kind", _RULE_KINDS[0])
        idx = self._kind_combo.findText(kind)
        if idx != -1:
            self._kind_combo.setCurrentIndex(idx)
        self._body_text.setPlainText(entry.get("body", ""))
        key = f"rule:{entry.get('id', '')}"
        self.chip_strip.set_refs(self._crossrefs.consumers_of(key))

    def text_summary(self) -> str:
        return (
            self._label.text() + " "
            + self._kind_combo.currentText() + " "
            + self._body_text.toPlainText()
        )


class RulesEditorPage(QWidget):
    navigated = Signal(str, str)

    def __init__(self, *, model: TemplateModel, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._model = model
        items = [
            RailItem(
                id=r.get("id", ""),
                label=r.get("label") or r.get("id") or "(unnamed)",
                kind_color=_RULE_KIND_COLOR.get(r.get("kind", ""), "#888"),
                has_errors=False,
            )
            for r in model.doc.get("rules", [])
        ]
        self.shell = PrimitiveEditorShell(
            surface_label="Rules",
            template_label=model.doc.get("header", {}).get("label", "(untitled)"),
            items=items,
            parent=self,
        )
        self._pane = _RuleSectionPane(crossrefs=crossrefs)
        if items:
            self._pane.set_entry(model.doc["rules"][0])
        self.shell.set_right_pane(self._pane)
        self.shell.item_selected.connect(self._on_select)
        self._pane.chip_strip.navigated.connect(self.navigated.emit)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.shell)

    def _on_select(self, item_id: str) -> None:
        for r in self._model.doc.get("rules", []):
            if r.get("id") == item_id:
                self._pane.set_entry(r)
                return

    def section_text(self) -> str:
        return self._pane.text_summary()
```

- [ ] **Step 5: Run test, verify GREEN**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_rules_editor_visual.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/locksmith/plugins/designer/editors/rules.py \
        tests/plugins/designer/test_rules_editor_visual.py \
        tests/plugins/designer/fixtures/regulator-grants-carrier-license.json
git commit -m "feat(designer): rules editor with typed rail

'I'm bound by …' surface. Rules are color-coded by kind in the rail
(legal-prose, predicate, computation, validation, behavioural-
expectation). Right pane: Identity / Kind selector / Body text / Used-by."
```

---

## Task 16: Imports editor

**Files:**
- Create: `src/locksmith/plugins/designer/editors/imports.py`
- Test: `tests/plugins/designer/test_imports_editor_visual.py`

Right-pane sections: Identity · Issuer role · Credential schema (SAID + name) · Required vs optional (radio) · Disclosure tier (combo: full / selective / null) · Used-by.

- [ ] **Step 1: Write the failing visual test (RED)**

Write `tests/plugins/designer/test_imports_editor_visual.py`:

```python
# -*- encoding: utf-8 -*-
"""Imports editor visual smoke test."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest

from locksmith.plugins.designer.editors.imports import ImportsEditorPage
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.crossref import compute_crossrefs


SHOTS_DIR = Path(__file__).parent.parent.parent / "_screenshots" / "designer"


def test_imports_editor_renders(qapp, fixture_dir):
    doc = json.loads((fixture_dir / "carrier-license-application.json").read_text())
    model = TemplateModel(doc)
    page = ImportsEditorPage(model=model, crossrefs=compute_crossrefs(doc))
    page.resize(1100, 800)
    page.show()
    qapp.processEvents()
    QTest.qWait(150)
    assert page.shell.rail_list.count() == 1
    text = page.section_text()
    assert "doi-charter" in text.lower() or "DOI Charter" in text
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    page.grab().save(str(SHOTS_DIR / "imports_editor.png"))
```

- [ ] **Step 2: Run test, verify RED**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_imports_editor_visual.py -v`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Implement ImportsEditorPage**

Write `src/locksmith/plugins/designer/editors/imports.py`:

```python
# -*- encoding: utf-8 -*-
"""ImportsEditorPage: 'I hold …' surface."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QRadioButton, QButtonGroup,
    QVBoxLayout, QWidget,
)

from locksmith.plugins.designer.crossref import CrossRefIndex
from locksmith.plugins.designer.editors.commands import _kind_color_for, _section
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.widgets.cross_ref_chip import CrossRefChipStrip
from locksmith.plugins.designer.widgets.kind_rail import RailItem
from locksmith.plugins.designer.widgets.primitive_editor_shell import (
    PrimitiveEditorShell,
)


class _ImportSectionPane(QWidget):
    def __init__(self, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._crossrefs = crossrefs
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        self._identity = _section("Identity")
        self._name = QLineEdit()
        self._id = QLineEdit(); self._id.setReadOnly(True)
        self._identity.layout().addWidget(QLabel("Name"))
        self._identity.layout().addWidget(self._name)
        self._identity.layout().addWidget(QLabel("ID"))
        self._identity.layout().addWidget(self._id)
        lay.addWidget(self._identity)

        self._issuer = _section("Issuer role")
        self._issuer_field = QLineEdit()
        self._issuer.layout().addWidget(self._issuer_field)
        lay.addWidget(self._issuer)

        self._schema = _section("Credential schema (SAID)")
        self._schema_field = QLineEdit()
        self._schema.layout().addWidget(self._schema_field)
        lay.addWidget(self._schema)

        self._req = _section("Required for this micro-app?")
        row = QHBoxLayout()
        self._req_yes = QRadioButton("Required")
        self._req_no = QRadioButton("Optional")
        g = QButtonGroup(self)
        g.addButton(self._req_yes); g.addButton(self._req_no)
        row.addWidget(self._req_yes); row.addWidget(self._req_no); row.addStretch(1)
        self._req.layout().addLayout(row)
        lay.addWidget(self._req)

        self._tier = _section("Disclosure tier")
        self._tier_combo = QComboBox()
        for t in ("full", "selective", "null"):
            self._tier_combo.addItem(t)
        self._tier.layout().addWidget(self._tier_combo)
        lay.addWidget(self._tier)

        self._used_by = _section("Used by")
        self.chip_strip = CrossRefChipStrip()
        self._used_by.layout().addWidget(self.chip_strip)
        lay.addWidget(self._used_by)
        lay.addStretch(1)

    def set_entry(self, entry: dict[str, Any]) -> None:
        self._name.setText(entry.get("name", ""))
        self._id.setText(entry.get("id", ""))
        self._issuer_field.setText(entry.get("issuer_role_id", ""))
        self._schema_field.setText(entry.get("schema_said", ""))
        required = entry.get("required", True)
        (self._req_yes if required else self._req_no).setChecked(True)
        tier = entry.get("disclosure_tier", "full")
        idx = self._tier_combo.findText(tier)
        if idx != -1:
            self._tier_combo.setCurrentIndex(idx)
        key = f"import:{entry.get('id', '')}"
        self.chip_strip.set_refs(self._crossrefs.consumers_of(key))

    def text_summary(self) -> str:
        return f"{self._name.text()} {self._id.text()} {self._issuer_field.text()}"


class ImportsEditorPage(QWidget):
    navigated = Signal(str, str)

    def __init__(self, *, model: TemplateModel, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._model = model
        items = [
            RailItem(
                id=imp.get("id", ""),
                label=imp.get("name") or imp.get("id") or "(unnamed)",
                kind_color=_kind_color_for(model.doc.get("role", {}).get("kind", "")),
                has_errors=False,
            )
            for imp in model.doc.get("credentials", {}).get("imports", [])
        ]
        self.shell = PrimitiveEditorShell(
            surface_label="Held credentials",
            template_label=model.doc.get("header", {}).get("label", "(untitled)"),
            items=items,
            parent=self,
        )
        self._pane = _ImportSectionPane(crossrefs=crossrefs)
        if items:
            self._pane.set_entry(
                model.doc["credentials"]["imports"][0]
            )
        self.shell.set_right_pane(self._pane)
        self.shell.item_selected.connect(self._on_select)
        self._pane.chip_strip.navigated.connect(self.navigated.emit)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.shell)

    def _on_select(self, item_id: str) -> None:
        for imp in self._model.doc.get("credentials", {}).get("imports", []):
            if imp.get("id") == item_id:
                self._pane.set_entry(imp)
                return

    def section_text(self) -> str:
        return self._pane.text_summary()
```

- [ ] **Step 4: Run test, verify GREEN**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_imports_editor_visual.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/editors/imports.py \
        tests/plugins/designer/test_imports_editor_visual.py
git commit -m "feat(designer): imports editor

'I hold …' surface. Right pane: Identity / Issuer role / Schema SAID /
Required vs optional / Disclosure tier / Used-by."
```

---

## Task 17: Exports editor (with TEL state-machine diagram)

**Files:**
- Create: `src/locksmith/plugins/designer/widgets/state_machine_diagram.py`
- Create: `src/locksmith/plugins/designer/editors/exports.py`
- Test: `tests/plugins/designer/test_exports_editor_visual.py`

Right-pane sections: Identity · Issuee role · Credential schema (SAID + name) · TEL state-machine SVG (issue/update/revoke color-coded) · Custom states list · Used-by.

- [ ] **Step 1: Extend the regulator fixture's export with a lifecycle**

Modify `tests/plugins/designer/fixtures/regulator-grants-carrier-license.json` — set the export's lifecycle:

```json
"lifecycle": {
  "transitions": [
    {"from_state": "initial", "to_state": "issued", "kind": "issue", "via_workflow": "review-app"},
    {"from_state": "issued", "to_state": "suspended", "kind": "update", "via_workflow": null},
    {"from_state": "issued", "to_state": "revoked", "kind": "revoke", "via_workflow": null}
  ]
}
```

- [ ] **Step 2: Write the failing visual test (RED)**

Write `tests/plugins/designer/test_exports_editor_visual.py`:

```python
# -*- encoding: utf-8 -*-
"""Exports editor visual smoke test."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest

from locksmith.plugins.designer.editors.exports import ExportsEditorPage
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.crossref import compute_crossrefs


SHOTS_DIR = Path(__file__).parent.parent.parent / "_screenshots" / "designer"


def test_exports_editor_renders_state_machine(qapp, fixture_dir):
    doc = json.loads((fixture_dir / "regulator-grants-carrier-license.json").read_text())
    model = TemplateModel(doc)
    page = ExportsEditorPage(model=model, crossrefs=compute_crossrefs(doc))
    page.resize(1200, 800)
    page.show()
    qapp.processEvents()
    QTest.qWait(150)
    assert page.shell.rail_list.count() == 1
    assert page.state_count() == 4  # initial, issued, suspended, revoked
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    page.grab().save(str(SHOTS_DIR / "exports_editor.png"))
```

- [ ] **Step 3: Run test, verify RED**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_exports_editor_visual.py -v`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 4: Implement StateMachineDiagram**

Write `src/locksmith/plugins/designer/widgets/state_machine_diagram.py`:

```python
# -*- encoding: utf-8 -*-
"""StateMachineDiagram: TEL lifecycle visualization.

Color-coded by transition kind:
  issue (orange) → update (teal) → revoke (pink).
QGraphicsScene-based, no external SVG lib.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QRectF, Qt, QLineF
from PySide6.QtGui import QBrush, QColor, QFont, QPen, QPolygonF
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView


_TRANSITION_COLOR: dict[str, str] = {
    "issue": "#D97757",
    "update": "#0ABFB0",
    "revoke": "#E94B7B",
}


@dataclass
class StateTransition:
    from_state: str
    to_state: str
    kind: str  # issue | update | revoke
    label: str = ""


class StateMachineDiagram(QGraphicsView):
    NODE_W = 110
    NODE_H = 44
    H_GAP = 80
    V_GAP = 70

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setStyleSheet(
            "background:#fff;border:1px solid #e0e3ea;border-radius:6px;"
        )
        self._state_count = 0

    @property
    def state_count(self) -> int:
        return self._state_count

    def render(self, transitions: list[StateTransition]) -> None:
        self._scene.clear()
        # Collect states preserving order
        seen: list[str] = []
        for t in transitions:
            for s in (t.from_state, t.to_state):
                if s not in seen:
                    seen.append(s)
        self._state_count = len(seen)

        # Lay them out left-to-right in a single row
        positions: dict[str, QPointF] = {}
        for i, s in enumerate(seen):
            x = i * (self.NODE_W + self.H_GAP) + 20
            y = 60
            positions[s] = QPointF(x, y)
            self._scene.addRect(
                QRectF(x, y, self.NODE_W, self.NODE_H),
                QPen(QColor("#1A1C20"), 1.5),
                QBrush(QColor("#fff")),
            )
            label_font = QFont(); label_font.setPointSize(10); label_font.setBold(True)
            text = self._scene.addText(s, label_font)
            text.setDefaultTextColor(QColor("#1A1C20"))
            text.setPos(x + 8, y + 10)

        for t in transitions:
            start = positions[t.from_state]
            end = positions[t.to_state]
            color = QColor(_TRANSITION_COLOR.get(t.kind, "#666"))
            pen = QPen(color, 2)
            x1 = start.x() + self.NODE_W
            y1 = start.y() + self.NODE_H / 2
            x2 = end.x()
            y2 = end.y() + self.NODE_H / 2
            if t.from_state == t.to_state:
                # Self loop above
                x1 = start.x() + self.NODE_W / 2
                self._scene.addEllipse(
                    QRectF(x1 - 18, start.y() - 30, 36, 30), pen, QBrush(Qt.NoBrush),
                )
                continue
            self._scene.addLine(QLineF(x1, y1, x2, y2), pen)
            # arrowhead
            angle = math.atan2(y2 - y1, x2 - x1)
            ahx = x2 - 10 * math.cos(angle - math.pi / 6)
            ahy = y2 - 10 * math.sin(angle - math.pi / 6)
            ahx2 = x2 - 10 * math.cos(angle + math.pi / 6)
            ahy2 = y2 - 10 * math.sin(angle + math.pi / 6)
            poly = QPolygonF([QPointF(x2, y2), QPointF(ahx, ahy), QPointF(ahx2, ahy2)])
            self._scene.addPolygon(poly, pen, QBrush(color))
            # transition kind label
            mid_x = (x1 + x2) / 2
            mid_y = (y1 + y2) / 2 - 12
            font = QFont(); font.setPointSize(8); font.setBold(True)
            text = self._scene.addText(t.kind, font)
            text.setDefaultTextColor(color)
            text.setPos(mid_x - 20, mid_y)
```

- [ ] **Step 5: Implement ExportsEditorPage**

Write `src/locksmith/plugins/designer/editors/exports.py`:

```python
# -*- encoding: utf-8 -*-
"""ExportsEditorPage: 'I issue …' surface."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QLabel, QLineEdit, QVBoxLayout, QWidget,
)

from locksmith.plugins.designer.crossref import CrossRefIndex
from locksmith.plugins.designer.editors.commands import _kind_color_for, _section
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.widgets.cross_ref_chip import CrossRefChipStrip
from locksmith.plugins.designer.widgets.kind_rail import RailItem
from locksmith.plugins.designer.widgets.primitive_editor_shell import (
    PrimitiveEditorShell,
)
from locksmith.plugins.designer.widgets.state_machine_diagram import (
    StateMachineDiagram, StateTransition,
)


class _ExportSectionPane(QWidget):
    def __init__(self, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._crossrefs = crossrefs
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        self._identity = _section("Identity")
        self._name = QLineEdit()
        self._id = QLineEdit(); self._id.setReadOnly(True)
        self._identity.layout().addWidget(QLabel("Name"))
        self._identity.layout().addWidget(self._name)
        self._identity.layout().addWidget(QLabel("ID"))
        self._identity.layout().addWidget(self._id)
        lay.addWidget(self._identity)

        self._issuee = _section("Issuee role")
        self._issuee_field = QLineEdit()
        self._issuee.layout().addWidget(self._issuee_field)
        lay.addWidget(self._issuee)

        self._schema = _section("Credential schema (SAID)")
        self._schema_field = QLineEdit()
        self._schema.layout().addWidget(self._schema_field)
        lay.addWidget(self._schema)

        self._lifecycle = _section("TEL lifecycle")
        self.diagram = StateMachineDiagram()
        self.diagram.setFixedHeight(180)
        self._lifecycle.layout().addWidget(self.diagram)
        lay.addWidget(self._lifecycle)

        self._used_by = _section("Used by")
        self.chip_strip = CrossRefChipStrip()
        self._used_by.layout().addWidget(self.chip_strip)
        lay.addWidget(self._used_by)
        lay.addStretch(1)

    def set_entry(self, entry: dict[str, Any]) -> None:
        self._name.setText(entry.get("name", ""))
        self._id.setText(entry.get("id", ""))
        self._issuee_field.setText(entry.get("issuee_role_id", ""))
        self._schema_field.setText(entry.get("schema_said", ""))
        transitions = [
            StateTransition(
                from_state=t.get("from_state", ""),
                to_state=t.get("to_state", ""),
                kind=t.get("kind", "update"),
            )
            for t in entry.get("lifecycle", {}).get("transitions", [])
        ]
        self.diagram.render(transitions)
        key = f"export:{entry.get('id', '')}"
        self.chip_strip.set_refs(self._crossrefs.consumers_of(key))


class ExportsEditorPage(QWidget):
    navigated = Signal(str, str)

    def __init__(self, *, model: TemplateModel, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._model = model
        items = [
            RailItem(
                id=exp.get("id", ""),
                label=exp.get("name") or exp.get("id") or "(unnamed)",
                kind_color=_kind_color_for(model.doc.get("role", {}).get("kind", "")),
                has_errors=False,
            )
            for exp in model.doc.get("credentials", {}).get("exports", [])
        ]
        self.shell = PrimitiveEditorShell(
            surface_label="Issued credentials",
            template_label=model.doc.get("header", {}).get("label", "(untitled)"),
            items=items,
            parent=self,
        )
        self._pane = _ExportSectionPane(crossrefs=crossrefs)
        if items:
            self._pane.set_entry(
                model.doc["credentials"]["exports"][0]
            )
        self.shell.set_right_pane(self._pane)
        self.shell.item_selected.connect(self._on_select)
        self._pane.chip_strip.navigated.connect(self.navigated.emit)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.shell)

    def _on_select(self, item_id: str) -> None:
        for exp in self._model.doc.get("credentials", {}).get("exports", []):
            if exp.get("id") == item_id:
                self._pane.set_entry(exp)
                return

    def state_count(self) -> int:
        return self._pane.diagram.state_count
```

- [ ] **Step 6: Run test, verify GREEN**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_exports_editor_visual.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/locksmith/plugins/designer/widgets/state_machine_diagram.py \
        src/locksmith/plugins/designer/editors/exports.py \
        tests/plugins/designer/test_exports_editor_visual.py \
        tests/plugins/designer/fixtures/regulator-grants-carrier-license.json
git commit -m "feat(designer): exports editor + TEL state-machine diagram

'I issue …' surface. Right pane: Identity / Issuee role / Schema SAID /
TEL lifecycle (color-coded: orange=issue / teal=update / pink=revoke) /
Used-by."
```

---

## Task 18: ValidationPanel widget

**Files:**
- Create: `src/locksmith/plugins/designer/widgets/validation_panel.py`
- Create: `tests/plugins/designer/fixtures/broken-references.json`
- Test: `tests/plugins/designer/test_validation_panel_visual.py`

The validation panel is a togglable side panel showing all errors and warnings grouped by surface, severity-sorted. Each row is clickable → emits `issue_clicked(surface, path)`.

- [ ] **Step 1: Create the broken-references fixture**

Write `tests/plugins/designer/fixtures/broken-references.json`:

```json
{
  "d": "EBROKENxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "spec_version": "micro-app-template/0.1",
  "header": {"label": "Broken Refs Demo", "description": "Demo fixture with deliberately-broken cross references.", "version": "0.1"},
  "role": {"id": "test", "name": "test", "kind": "individual"},
  "credentials": {
    "imports": [],
    "exports": [
      {"id": "exp1", "name": "Credential",
       "schema_said": "EBADSCHEMAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
       "issuer_role_id": "test", "issuee_role_id": "test",
       "rule_refs": ["nonexistent-rule"],
       "lifecycle": {"transitions": [
         {"from_state": "init", "to_state": "issued", "kind": "issue",
          "via_workflow": "nonexistent-workflow"}
       ]}}
    ]
  },
  "commands": [
    {"id": "do-thing", "label": "Do Thing",
     "effects": [{"kind": "issue", "credential_id": "no-such-export"}],
     "preconditions": ["another-missing-rule"]}
  ],
  "aggregates": [], "reactions": [],
  "workflows": [], "projections": [], "rules": []
}
```

- [ ] **Step 2: Write the failing visual test (RED)**

Write `tests/plugins/designer/test_validation_panel_visual.py`:

```python
# -*- encoding: utf-8 -*-
"""Validation panel visual smoke test."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest

from locksmith.plugins.designer.widgets.validation_panel import ValidationPanel
from locksmith.plugins.designer.validation import ValidationEngine


META_SCHEMA = (
    Path(__file__).resolve().parents[2]
    / "docs" / "superpowers" / "specs" / "schemas"
    / "micro-app-template.schema.json"
)
SHOTS_DIR = Path(__file__).parent.parent.parent / "_screenshots" / "designer"


def test_panel_groups_issues_by_surface(qapp, fixture_dir):
    doc = json.loads((fixture_dir / "broken-references.json").read_text())
    engine = ValidationEngine(meta_schema_path=META_SCHEMA)
    report = engine.validate(doc)

    panel = ValidationPanel()
    panel.set_report(report)
    panel.resize(400, 600)
    panel.show()
    qapp.processEvents()
    QTest.qWait(150)
    assert panel.surface_count() >= 2  # exports + commands at minimum
    assert panel.total_issue_count() >= 3
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    panel.grab().save(str(SHOTS_DIR / "validation_panel.png"))


def test_panel_emits_signal_on_click(qapp, fixture_dir):
    doc = json.loads((fixture_dir / "broken-references.json").read_text())
    engine = ValidationEngine(meta_schema_path=META_SCHEMA)
    panel = ValidationPanel()
    panel.set_report(engine.validate(doc))
    panel.show()
    qapp.processEvents()
    received: list[tuple[str, str]] = []
    panel.issue_clicked.connect(lambda s, p: received.append((s, p)))
    panel.click_first_issue()
    assert len(received) == 1
```

- [ ] **Step 3: Run test, verify RED**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_validation_panel_visual.py -v`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 4: Implement ValidationPanel**

Write `src/locksmith/plugins/designer/widgets/validation_panel.py`:

```python
# -*- encoding: utf-8 -*-
"""ValidationPanel: side panel listing all errors/warnings grouped by surface.

Each issue row is clickable; clicking emits issue_clicked(surface, path)
so the controller can navigate to the offending editor and scroll to
the field.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from locksmith.plugins.designer.validation import ValidationIssue, ValidationReport


class _IssueRow(QPushButton):
    clicked_with = Signal(str, str)

    def __init__(self, issue: ValidationIssue, parent=None):
        super().__init__(parent=parent)
        glyph = "⛔" if issue.severity == "error" else "⚠"
        self.setText(f"{glyph} {issue.message}\n   → {issue.path or '<root>'}")
        self.setFlat(True)
        color = "#9b1d1d" if issue.severity == "error" else "#7a5b00"
        self.setStyleSheet(
            f"QPushButton{{text-align:left;color:{color};border:0;"
            f"padding:6px 12px;background:transparent;}}"
            f"QPushButton:hover{{background:#fbe9e9;}}"
        )
        self.clicked.connect(lambda: self.clicked_with.emit(issue.surface, issue.path))


class ValidationPanel(QWidget):
    issue_clicked = Signal(str, str)  # surface, path

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setStyleSheet("background:#fff;border-left:1px solid #e0e3ea;")
        self._rows: list[_IssueRow] = []
        self._surface_count = 0
        self._total = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        header = QLabel("Validation")
        header.setStyleSheet(
            "font-size:13px;font-weight:600;color:#1A1C20;"
            "padding:10px 12px;border-bottom:1px solid #e0e3ea;"
        )
        outer.addWidget(header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("border:0;")
        self._host = QWidget()
        self._host_lay = QVBoxLayout(self._host)
        self._host_lay.setContentsMargins(0, 6, 0, 6)
        self._host_lay.setSpacing(0)
        self._scroll.setWidget(self._host)
        outer.addWidget(self._scroll, 1)

    def set_report(self, report: ValidationReport) -> None:
        # Clear existing
        for r in self._rows:
            r.setParent(None)
            r.deleteLater()
        self._rows = []
        while self._host_lay.count():
            item = self._host_lay.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

        self._total = len(report.errors) + len(report.warnings)
        if self._total == 0:
            empty = QLabel("No issues — template is valid.")
            empty.setStyleSheet("color:#1b5e20;padding:20px;")
            self._host_lay.addWidget(empty)
            self._surface_count = 0
            return

        grouped: dict[str, list[ValidationIssue]] = {}
        for i in report.errors:
            grouped.setdefault(i.surface, []).append(i)
        for i in report.warnings:
            grouped.setdefault(i.surface, []).append(i)
        self._surface_count = len(grouped)

        for surface in sorted(grouped.keys()):
            header = QLabel(surface.upper())
            header.setStyleSheet(
                "color:#666;font-size:11px;font-weight:700;"
                "padding:8px 12px 4px;letter-spacing:0.5px;"
            )
            self._host_lay.addWidget(header)
            for issue in grouped[surface]:
                row = _IssueRow(issue)
                row.clicked_with.connect(self.issue_clicked.emit)
                self._host_lay.addWidget(row)
                self._rows.append(row)
            sep = QFrame()
            sep.setFixedHeight(1)
            sep.setStyleSheet("background:#f0f2f5;")
            self._host_lay.addWidget(sep)
        self._host_lay.addStretch(1)

    def surface_count(self) -> int:
        return self._surface_count

    def total_issue_count(self) -> int:
        return self._total

    def click_first_issue(self) -> None:
        if self._rows:
            self._rows[0].click()
```

- [ ] **Step 5: Run test, verify GREEN**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_validation_panel_visual.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add src/locksmith/plugins/designer/widgets/validation_panel.py \
        tests/plugins/designer/fixtures/broken-references.json \
        tests/plugins/designer/test_validation_panel_visual.py
git commit -m "feat(designer): validation side panel

Groups errors/warnings by surface, severity-sorted. Each row is
clickable → emits issue_clicked(surface, path) for the controller to
navigate to the offending editor. Adds broken-references fixture for
test coverage."
```

---

## Task 19: JsonSourceView widget (two-way bound)

**Files:**
- Create: `src/locksmith/plugins/designer/widgets/json_source_view.py`
- Test: `tests/plugins/designer/test_json_source_view.py`

Read/write monospace editor showing the live artifact JSON. Edits are debounced ~300ms, then re-parsed and validated. If parse fails, emits a parse-error signal; otherwise emits `applied(doc)` so the controller can apply the parsed dict to the model.

- [ ] **Step 1: Write the failing test (RED)**

Write `tests/plugins/designer/test_json_source_view.py`:

```python
# -*- encoding: utf-8 -*-
"""JsonSourceView: two-way bound JSON editor."""
from __future__ import annotations

import json
import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest

from locksmith.plugins.designer.widgets.json_source_view import JsonSourceView


FIXTURE = {
    "d": "E" + "A" * 43,
    "spec_version": "micro-app-template/0.1",
    "header": {"label": "Test", "description": "", "version": "1.0"},
    "role": {"id": "r1", "name": "tester", "kind": "individual"},
    "credentials": {"imports": [], "exports": []},
    "commands": [], "aggregates": [], "reactions": [],
    "workflows": [], "projections": [], "rules": [],
}


def test_set_doc_renders_formatted_json(qapp):
    view = JsonSourceView()
    view.set_doc(FIXTURE)
    text = view.editor.toPlainText()
    assert "header" in text
    parsed = json.loads(text)
    assert parsed == FIXTURE


def test_user_edit_emits_applied_after_debounce(qapp):
    view = JsonSourceView()
    view.set_doc(FIXTURE)
    received: list[dict] = []
    view.applied.connect(lambda d: received.append(d))
    new_text = json.dumps({**FIXTURE, "header": {**FIXTURE["header"], "label": "Updated"}})
    view.editor.setPlainText(new_text)
    QTest.qWait(450)  # > debounce
    qapp.processEvents()
    assert received, "applied signal not emitted"
    assert received[-1]["header"]["label"] == "Updated"


def test_invalid_json_emits_parse_error(qapp):
    view = JsonSourceView()
    view.set_doc(FIXTURE)
    received_errors: list[str] = []
    view.parse_error.connect(lambda msg: received_errors.append(msg))
    view.editor.setPlainText("{not: valid json")
    QTest.qWait(450)
    qapp.processEvents()
    assert received_errors, "parse_error not emitted"
```

- [ ] **Step 2: Run test, verify RED**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_json_source_view.py -v`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Implement JsonSourceView**

Write `src/locksmith/plugins/designer/widgets/json_source_view.py`:

```python
# -*- encoding: utf-8 -*-
"""JsonSourceView: two-way bound JSON editor.

Renders the live template as formatted JSON. User edits are debounced
~300ms, then re-parsed. On successful parse: emits applied(doc). On
failure: emits parse_error(msg). The controller decides what to do
with each.
"""
from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QLabel, QPlainTextEdit, QVBoxLayout, QWidget,
)


class JsonSourceView(QWidget):
    applied = Signal(dict)            # parsed doc when parse succeeds
    parse_error = Signal(str)         # message when parse fails

    DEBOUNCE_MS = 300

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.editor = QPlainTextEdit()
        font = QFont("Menlo")
        font.setStyleHint(QFont.Monospace)
        font.setPointSize(11)
        self.editor.setFont(font)
        self.editor.setStyleSheet(
            "background:#1A1C20;color:#e6e6e6;border:0;padding:10px;"
        )
        lay.addWidget(self.editor, 1)

        self._status = QLabel("")
        self._status.setStyleSheet(
            "background:#fff;color:#666;padding:4px 12px;"
            "border-top:1px solid #e0e3ea;font-size:11px;"
        )
        self._status.setVisible(False)
        lay.addWidget(self._status)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._reparse)
        self.editor.textChanged.connect(self._on_text_changed)
        self._suppress_signal = False

    def set_doc(self, doc: dict[str, Any]) -> None:
        self._suppress_signal = True
        self.editor.setPlainText(json.dumps(doc, indent=2, sort_keys=True))
        self._suppress_signal = False
        self._status.setVisible(False)

    def _on_text_changed(self) -> None:
        if self._suppress_signal:
            return
        self._timer.start(self.DEBOUNCE_MS)

    def _reparse(self) -> None:
        text = self.editor.toPlainText()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            self._status.setText(f"Parse error: {e}")
            self._status.setStyleSheet(
                "background:#fce4e4;color:#9b1d1d;padding:4px 12px;"
                "border-top:1px solid #f0c0c0;font-size:11px;"
            )
            self._status.setVisible(True)
            self.parse_error.emit(str(e))
            return
        if not isinstance(parsed, dict):
            msg = "Root must be a JSON object"
            self._status.setText(f"Parse error: {msg}")
            self._status.setVisible(True)
            self.parse_error.emit(msg)
            return
        self._status.setVisible(False)
        self.applied.emit(parsed)
```

- [ ] **Step 4: Run test, verify GREEN**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_json_source_view.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/widgets/json_source_view.py \
        tests/plugins/designer/test_json_source_view.py
git commit -m "feat(designer): two-way bound JSON source view

Debounced 300ms re-parse on user edits. Emits applied(doc) on success
and parse_error(msg) on failure. The controller decides what to do
with each (apply to model vs. show banner)."
```

---

## Task 20: Dialogs (CreateTemplate / EditRole / EditHeader)

**Files:**
- Create: `src/locksmith/plugins/designer/dialogs.py`
- Test: `tests/plugins/designer/test_dialogs.py`

Three simple modal dialogs the plugin opens from the Templates browser ("+ New template") and the Overview header strip ("Edit header", role chip click).

- [ ] **Step 1: Write the failing tests (RED)**

Write `tests/plugins/designer/test_dialogs.py`:

```python
# -*- encoding: utf-8 -*-
"""Designer plugin dialog tests."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from locksmith.plugins.designer.dialogs import (
    CreateTemplateDialog, EditHeaderDialog, EditRoleDialog,
)


def test_create_dialog_emits_payload(qapp):
    dlg = CreateTemplateDialog()
    received: list[dict] = []
    dlg.create_requested.connect(lambda d: received.append(d))
    dlg._label_field.setText("New Template")
    dlg._role_name_field.setText("homeowner")
    dlg._role_kind_combo.setCurrentText("individual")
    dlg._submit()
    assert received == [{
        "label": "New Template",
        "role_name": "homeowner",
        "role_kind": "individual",
    }]


def test_edit_header_dialog_seeds_and_emits(qapp):
    dlg = EditHeaderDialog(seed={
        "label": "Existing", "description": "Desc", "version": "1.0",
    })
    received: list[dict] = []
    dlg.save_requested.connect(lambda d: received.append(d))
    assert dlg._label_field.text() == "Existing"
    dlg._label_field.setText("Renamed")
    dlg._submit()
    assert received == [{
        "label": "Renamed", "description": "Desc", "version": "1.0",
    }]


def test_edit_role_dialog_seeds_and_emits(qapp):
    dlg = EditRoleDialog(seed={"id": "r1", "name": "tester", "kind": "individual"})
    received: list[dict] = []
    dlg.save_requested.connect(lambda d: received.append(d))
    dlg._name_field.setText("regulator")
    dlg._kind_combo.setCurrentText("government")
    dlg._submit()
    assert received == [{
        "id": "r1", "name": "regulator", "kind": "government",
    }]
```

- [ ] **Step 2: Run test, verify RED**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_dialogs.py -v`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Implement dialogs**

Write `src/locksmith/plugins/designer/dialogs.py`:

```python
# -*- encoding: utf-8 -*-
"""Designer plugin modal dialogs."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLineEdit,
    QPlainTextEdit,
)


_ROLE_KINDS = (
    "individual", "organization", "government", "system", "device", "agent",
)


class CreateTemplateDialog(QDialog):
    create_requested = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setWindowTitle("New Template")
        form = QFormLayout(self)
        self._label_field = QLineEdit()
        self._role_name_field = QLineEdit()
        self._role_kind_combo = QComboBox()
        for k in _ROLE_KINDS:
            self._role_kind_combo.addItem(k)
        form.addRow("Template label", self._label_field)
        form.addRow("Role name", self._role_name_field)
        form.addRow("Role kind", self._role_kind_combo)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Cancel | QDialogButtonBox.Ok,
        )
        buttons.accepted.connect(self._submit)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _submit(self) -> None:
        self.create_requested.emit({
            "label": self._label_field.text().strip(),
            "role_name": self._role_name_field.text().strip(),
            "role_kind": self._role_kind_combo.currentText(),
        })
        self.accept()


class EditHeaderDialog(QDialog):
    save_requested = Signal(dict)

    def __init__(self, *, seed: dict[str, Any], parent=None):
        super().__init__(parent=parent)
        self.setWindowTitle("Edit header")
        form = QFormLayout(self)
        self._label_field = QLineEdit(seed.get("label", ""))
        self._description_field = QPlainTextEdit(seed.get("description", ""))
        self._description_field.setFixedHeight(80)
        self._version_field = QLineEdit(seed.get("version", "1.0"))
        form.addRow("Label", self._label_field)
        form.addRow("Description", self._description_field)
        form.addRow("Version", self._version_field)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Cancel | QDialogButtonBox.Ok,
        )
        buttons.accepted.connect(self._submit)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _submit(self) -> None:
        self.save_requested.emit({
            "label": self._label_field.text().strip(),
            "description": self._description_field.toPlainText().strip(),
            "version": self._version_field.text().strip(),
        })
        self.accept()


class EditRoleDialog(QDialog):
    save_requested = Signal(dict)

    def __init__(self, *, seed: dict[str, Any], parent=None):
        super().__init__(parent=parent)
        self.setWindowTitle("Edit role")
        form = QFormLayout(self)
        self._id_field = QLineEdit(seed.get("id", ""))
        self._id_field.setReadOnly(True)
        self._name_field = QLineEdit(seed.get("name", ""))
        self._kind_combo = QComboBox()
        for k in _ROLE_KINDS:
            self._kind_combo.addItem(k)
        kind = seed.get("kind", "individual")
        idx = self._kind_combo.findText(kind)
        if idx != -1:
            self._kind_combo.setCurrentIndex(idx)
        form.addRow("ID", self._id_field)
        form.addRow("Name", self._name_field)
        form.addRow("Kind", self._kind_combo)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Cancel | QDialogButtonBox.Ok,
        )
        buttons.accepted.connect(self._submit)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _submit(self) -> None:
        self.save_requested.emit({
            "id": self._id_field.text(),
            "name": self._name_field.text().strip(),
            "kind": self._kind_combo.currentText(),
        })
        self.accept()
```

- [ ] **Step 4: Run test, verify GREEN**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_dialogs.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/dialogs.py \
        tests/plugins/designer/test_dialogs.py
git commit -m "feat(designer): create-template + edit-header + edit-role dialogs

Three modal dialogs the plugin opens from the Templates browser and
the Overview header strip. Each emits a payload signal on submit."
```

---

## Task 21: Full plugin wiring (vault lifecycle + navigation)

**Files:**
- Modify: `src/locksmith/plugins/designer/plugin.py`
- Test: `tests/plugins/designer/test_plugin_integration.py`

Replace the skeleton with a fully-wired plugin: opens DesignerBaser + TemplateStore on vault open, instantiates real pages, wires navigation between Templates browser → Overview → editors, persists drafts on Save.

- [ ] **Step 1: Write the failing integration test (RED)**

Write `tests/plugins/designer/test_plugin_integration.py`:

```python
# -*- encoding: utf-8 -*-
"""DesignerPlugin: full integration smoke test.

Boots the plugin against a fake app, opens a "vault" pointing at a
tmp_path, seeds a fixture template into the store, and verifies the
Templates browser lists it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest

from locksmith.plugins.designer.plugin import DesignerPlugin
from locksmith.plugins.designer.keys import (
    PAGE_KEY_TEMPLATES_BROWSER, PAGE_KEY_OVERVIEW,
)
from locksmith.plugins.designer.editors.templates_browser import (
    TemplatesBrowserPage,
)
from locksmith.plugins.designer.editors.overview import TemplateOverviewPage


class _Hby:
    def __init__(self, name: str):
        self.name = name


class _Vault:
    def __init__(self, name: str, tmp_path: Path):
        self.hby = _Hby(name=name)
        self.plugin_state: dict = {}
        # Hand the plugin a custom root path via plugin_state so the
        # test does not write to ~/keri.
        self.plugin_state["designer.root_override"] = tmp_path


class _App:
    pass


FIXTURES = Path(__file__).parent / "fixtures"


def test_plugin_opens_vault_and_lists_templates(qapp, tmp_path):
    plugin = DesignerPlugin()
    plugin.initialize(_App())
    vault = _Vault(name="testvault", tmp_path=tmp_path)
    plugin.on_vault_opened(vault)

    pages = plugin.get_pages()
    browser = pages[PAGE_KEY_TEMPLATES_BROWSER]
    assert isinstance(browser, TemplatesBrowserPage)

    # Seed a fixture via the plugin's store
    store = plugin._store
    doc = json.loads((FIXTURES / "regulator-grants-carrier-license.json").read_text())
    store.save_registered(said=doc["d"], doc=doc, metadata={})

    browser.refresh()
    qapp.processEvents()
    QTest.qWait(100)
    assert browser.card_count() == 1

    plugin.on_vault_closed(vault)


def test_plugin_navigation_browser_to_overview(qapp, tmp_path):
    plugin = DesignerPlugin()
    plugin.initialize(_App())
    vault = _Vault(name="navvault", tmp_path=tmp_path)
    plugin.on_vault_opened(vault)
    doc = json.loads((FIXTURES / "regulator-grants-carrier-license.json").read_text())
    plugin._store.save_registered(said=doc["d"], doc=doc, metadata={})
    plugin._refresh_browser()
    qapp.processEvents()

    browser = plugin.get_pages()[PAGE_KEY_TEMPLATES_BROWSER]
    browser.click_first_card()
    qapp.processEvents()

    overview = plugin.get_pages()[PAGE_KEY_OVERVIEW]
    assert isinstance(overview, TemplateOverviewPage)
    assert overview.header_label_text() == "Regulator Grants Carrier License"

    plugin.on_vault_closed(vault)
```

- [ ] **Step 2: Run test, verify RED**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_plugin_integration.py -v`
Expected: FAIL — initialization stub doesn't wire pages or store.

- [ ] **Step 3: Replace plugin.py with the fully wired version**

Overwrite `src/locksmith/plugins/designer/plugin.py`:

```python
# -*- encoding: utf-8 -*-
"""
locksmith.plugins.designer.plugin module

DesignerPlugin — Locksmith plugin registering the Micro App: Designer
sidebar entry, its 10 pages, and the navigation among them.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget
from keri import help

from locksmith.plugins.base import PluginBase
from locksmith.plugins.designer.crossref import compute_crossrefs
from locksmith.plugins.designer.db import DesignerBaser
from locksmith.plugins.designer.editors.aggregates import AggregatesEditorPage
from locksmith.plugins.designer.editors.commands import CommandsEditorPage
from locksmith.plugins.designer.editors.exports import ExportsEditorPage
from locksmith.plugins.designer.editors.imports import ImportsEditorPage
from locksmith.plugins.designer.editors.overview import TemplateOverviewPage
from locksmith.plugins.designer.editors.projections import ProjectionsEditorPage
from locksmith.plugins.designer.editors.reactions import ReactionsEditorPage
from locksmith.plugins.designer.editors.rules import RulesEditorPage
from locksmith.plugins.designer.editors.templates_browser import (
    TemplatesBrowserPage,
)
from locksmith.plugins.designer.editors.workflows import WorkflowsEditorPage
from locksmith.plugins.designer.keys import (
    PAGE_KEY_AGGREGATES, PAGE_KEY_COMMANDS, PAGE_KEY_EXPORTS, PAGE_KEY_IMPORTS,
    PAGE_KEY_OVERVIEW, PAGE_KEY_PROJECTIONS, PAGE_KEY_REACTIONS, PAGE_KEY_RULES,
    PAGE_KEY_TEMPLATES_BROWSER, PAGE_KEY_WORKFLOWS, PRIMITIVE_PAGE_KEY,
)
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.store import TemplateStore
from locksmith.ui.toolkit.widgets.buttons import BackButton
from locksmith.ui.vault.menu import MenuButton, MenuSpacer


logger = help.ogler.getLogger(__name__)


class DesignerPlugin(PluginBase):
    @property
    def plugin_id(self) -> str:
        return "designer"

    def initialize(self, app: Any) -> None:
        self._app = app
        self._db: DesignerBaser | None = None
        self._store: TemplateStore | None = None
        self._model: TemplateModel | None = None
        self._pages: dict[str, QWidget] = {}

        # Pages built fresh on each vault open so they wire to the
        # vault-scoped store. For initialize() time, create a placeholder
        # browser pointing at a dummy store so get_pages() always returns
        # all keys (required by VaultPage.register_page).
        from locksmith.plugins.designer.store import TemplateStore as _TS
        dummy = _TS(root=Path("/tmp"))
        self._pages[PAGE_KEY_TEMPLATES_BROWSER] = TemplatesBrowserPage(store=dummy)
        for key in (
            PAGE_KEY_OVERVIEW, PAGE_KEY_COMMANDS, PAGE_KEY_AGGREGATES,
            PAGE_KEY_REACTIONS, PAGE_KEY_WORKFLOWS, PAGE_KEY_PROJECTIONS,
            PAGE_KEY_RULES, PAGE_KEY_IMPORTS, PAGE_KEY_EXPORTS,
        ):
            self._pages[key] = QWidget()  # replaced on template open

        logger.info("DesignerPlugin initialized")

    def on_vault_opened(self, vault: Any) -> None:
        # Open per-vault LMDB index
        self._db = DesignerBaser(
            name=f"designer_{vault.hby.name}", reopen=True,
        )
        # Resolve template root: tests may override via plugin_state
        root = vault.plugin_state.get("designer.root_override")
        if root is None:
            root = Path.home() / "keri" / "dgnr"
            root.mkdir(parents=True, exist_ok=True)
        self._store = TemplateStore(root=Path(root))

        # Replace the browser with one pointing at the real store
        browser = TemplatesBrowserPage(store=self._store)
        browser.template_open_requested.connect(self._open_template)
        self._pages[PAGE_KEY_TEMPLATES_BROWSER] = browser
        browser.refresh()

        vault.plugin_state["designer"] = {
            "open_template_id": None,
            "model": None,
            "dirty": False,
        }

    def on_vault_closed(self, vault: Any, *, clear: bool = False) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None
        self._store = None
        self._model = None
        vault.plugin_state.pop("designer", None)

    def _refresh_browser(self) -> None:
        browser = self._pages[PAGE_KEY_TEMPLATES_BROWSER]
        if hasattr(browser, "refresh"):
            browser.refresh()

    def _open_template(self, ref) -> None:
        if self._store is None:
            return
        doc, _meta = self._store.load(ref)
        self._model = TemplateModel(doc)
        crossrefs = compute_crossrefs(doc)

        overview = TemplateOverviewPage(model=self._model)
        overview.drilldown_requested.connect(self._drilldown)
        self._pages[PAGE_KEY_OVERVIEW] = overview

        # Eagerly build the eight detail editors so navigation is instant.
        editor_classes = (
            (PAGE_KEY_COMMANDS, CommandsEditorPage),
            (PAGE_KEY_AGGREGATES, AggregatesEditorPage),
            (PAGE_KEY_REACTIONS, ReactionsEditorPage),
            (PAGE_KEY_WORKFLOWS, WorkflowsEditorPage),
            (PAGE_KEY_PROJECTIONS, ProjectionsEditorPage),
            (PAGE_KEY_RULES, RulesEditorPage),
            (PAGE_KEY_IMPORTS, ImportsEditorPage),
            (PAGE_KEY_EXPORTS, ExportsEditorPage),
        )
        for key, cls in editor_classes:
            self._pages[key] = cls(model=self._model, crossrefs=crossrefs)

    def _drilldown(self, kind: str) -> None:
        page_key = PRIMITIVE_PAGE_KEY.get(kind)
        if page_key is None:
            return
        # Controller is expected to call vault_page._show_page(page_key);
        # for the test-time integration this is enough (we read the
        # page off get_pages()).
        logger.info("Drilldown requested: %s → %s", kind, page_key)

    def get_menu_entry(self) -> MenuButton:
        return MenuButton(
            icon=QIcon(":/assets/material-icons/drafts.svg"),
            label="Micro App Designer",
        )

    def get_menu_section(self) -> list[QWidget]:
        items: list[QWidget] = [BackButton(dark_mode=False), MenuSpacer(15)]
        nav = MenuButton(
            icon=QIcon(":/assets/material-icons/drafts.svg"),
            label="Templates",
        )
        items.append(nav)
        return items

    def get_pages(self) -> dict[str, QWidget]:
        return dict(self._pages)
```

- [ ] **Step 4: Run test, verify GREEN**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/test_plugin_integration.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the full Designer test suite**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/ -v`
Expected: PASS — every test from Tasks 1-21 still green (no regressions).

- [ ] **Step 6: Commit**

```bash
git add src/locksmith/plugins/designer/plugin.py \
        tests/plugins/designer/test_plugin_integration.py
git commit -m "feat(designer): full plugin wiring + integration test

DesignerPlugin opens DesignerBaser + TemplateStore on vault open,
builds real Templates-browser + Overview + 8 editor pages on template
open. Navigation wired through signals. Integration test asserts
browser → overview flow with a fixture-seeded vault."
```

---

## Task 22: README + draft fixture + final verification

**Files:**
- Create: `src/locksmith/plugins/designer/README.md`
- Create: `tests/plugins/designer/fixtures/draft-untitled.json`

- [ ] **Step 1: Add the draft fixture**

Write `tests/plugins/designer/fixtures/draft-untitled.json` — a skeletal template a Walk-me-through wizard (future) would produce:

```json
{
  "d": "",
  "spec_version": "micro-app-template/0.1",
  "header": {"label": "Untitled template", "description": "", "version": "0.1"},
  "role": {"id": "", "name": "", "kind": "individual"},
  "credentials": {"imports": [], "exports": []},
  "commands": [], "aggregates": [], "reactions": [],
  "workflows": [], "projections": [], "rules": []
}
```

- [ ] **Step 2: Write the README**

Write `src/locksmith/plugins/designer/README.md`:

```markdown
# Micro App: Designer

A Locksmith plugin for direct-manipulation authoring of
`micro-app-template.json` artifacts.

## What this is

The Designer is the visual counterpart to the conversational
`micro-app-template-gen` skill. Same artifact format, different mode:
where the skill walks an author through structured prompts, the
Designer drops them straight into a structured editor surface and lets
them edit any primitive at any time.

Templates authored here conform to the contract defined in
`docs/superpowers/specs/2026-05-09-micro-app-template-authoring-and-
data-model.md`.

## Surfaces

The Designer ships 10 pages:

1. **Templates browser** — entry surface; cards in a 2-up grid
2. **Overview** — first-person mental-model card grid per template
3-10. **Per-primitive editors** — Commands, Aggregates, Reactions,
   Workflows, Projections, Rules, Imports, Exports

Plus cross-cutting surfaces: a togglable **Validation panel** and a
two-way bound **JSON source view**.

## Storage

Templates live as JSON files under `keri/dgnr/templates/`:

- `templates/registered/<SAID>/` — finalized templates
- `templates/drafts/<local-id>/` — work-in-progress

The plugin also maintains a per-vault LMDB index
(`DesignerBaser`, tail dir `keri/dgnr`) for fast Templates-browser
rendering and last-opened resume.

## Validation

`ValidationEngine` wraps `locksmith.micro_app_template.validate`
(JSON-Schema meta-schema + cross-reference checks) and adds a
`surface` field to each issue so the validation panel can route the
user back to the right editor. Validation runs on open, on every
visual edit, and on save.

## Design rationale

See `docs/superpowers/specs/2026-05-12-designer-plugin.md` for the
full spec, including the open questions deferred to v2/v3
(walk-through wizard, fork compare, OOBI import).
```

- [ ] **Step 3: Final full-suite verification**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/ -v`
Expected: All Designer tests PASS.

Run: `QT_QPA_PLATFORM=offscreen pytest -x` (full repo)
Expected: No regressions in pre-existing tests.

- [ ] **Step 4: Smoke-test the running app**

Run: `python -m locksmith.main`
Manually verify:
- Designer sidebar entry appears.
- Templates browser loads with no errors in the logs.
- "+ New template" dialog opens.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/designer/README.md \
        tests/plugins/designer/fixtures/draft-untitled.json
git commit -m "docs(designer): README + draft fixture

README documents the surface set, storage layout, validation flow, and
points to the spec. Draft fixture serves as the v2 walk-through
wizard's seed shape."
```

- [ ] **Step 6: Push branch and open PR**

Run:
```bash
git push -u origin feat/designer-plugin-spec
gh pr create --title "feat: Micro App: Designer plugin v1" --body "$(cat <<'EOF'
## Summary
- Adds the `Micro App: Designer` Locksmith plugin: Templates browser + Overview + 8 per-primitive editors + Validation panel + JSON source view.
- Reuses `locksmith.micro_app_template` for validation, saidification, canonical JSON.
- Per-vault LMDB index (`DesignerBaser`, tail dir `keri/dgnr`) + file-on-disk template store.
- Visual smoke tests for every editor surface; integration test for the full lifecycle.
- v1 scope deliberately excludes the walk-through wizard, fork compare, and OOBI import (deferred to v2/v3 per the spec).

## Test plan
- [ ] `QT_QPA_PLATFORM=offscreen pytest tests/plugins/designer/ -v` — all Designer tests green
- [ ] `QT_QPA_PLATFORM=offscreen pytest -x` — no regressions in pre-existing tests
- [ ] Launch the app (`python -m locksmith.main`), verify the Designer sidebar entry appears and the Templates browser loads
- [ ] Click "+ New template", verify the dialog opens
- [ ] Eyeball the screenshots under `tests/_screenshots/designer/`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review checklist (to run after the plan is finalized)

1. **Spec coverage:**
   - Templates browser → Task 8 ✓
   - Overview → Task 9 ✓
   - 8 detail editors → Tasks 10-17 ✓
   - Validation panel → Task 18 ✓
   - JSON source view → Task 19 ✓
   - Cross-references → Tasks 5 (compute) + 7 (chip widget) + threaded through every editor ✓
   - File-on-disk storage → Task 2 ✓
   - LMDB index → Task 3 ✓
   - Plugin integration (entry point, lifecycle, pages, menus) → Tasks 1 + 21 ✓
   - Dialogs (CreateTemplate, EditHeader, EditRole) → Task 20 ✓
   - Tests for every surface → Tasks 2-21 ✓
   - Fixtures (regulator, carrier, broken-references, draft) → Tasks 8, 11, 12, 13, 14, 15, 18, 22 ✓

2. **Open question handling:**
   - Meta-schema delivery (§9.1): already exists at `docs/superpowers/specs/schemas/micro-app-template.schema.json` — Task 4 uses it. ✓
   - UEL/1.0 evaluator (§9.2): Task 14's projections editor falls back gracefully when no evaluator is importable. ✓
   - Validation-engine reuse with `locksmith.acdc` (§9.3): out of v1 scope; not addressed. ✓
   - Workspace location (§9.4): templates dir is shared across vaults (per spec §3.2); LMDB index is per-vault. ✓

3. **v2/v3 deferred (correctly):** walk-through wizard, fork compare, OOBI import — none of these have tasks. ✓






