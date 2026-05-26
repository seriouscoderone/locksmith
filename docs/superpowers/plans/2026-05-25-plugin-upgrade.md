# Plugin Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add in-app detection and one-click upgrade for installed Locksmith plugins, with a restart banner — building on the spec at `docs/superpowers/specs/2026-05-25-plugin-upgrade-design.md`.

**Architecture:** Three layers. (1) `storage.py` gets helpers for an update-cache file and sidecar/previous clone dirs. (2) `updates.py` (new) owns a `PluginUpdateChecker` (plain class) that runs `git ls-remote` per github-source plugin and writes the cache. A `QTimer` in `LocksmithWindow` drives the periodic check; an immediate check fires at startup when the cache is stale. (3) `installer.py` gains an `upgrade()` method that re-clones into a sidecar and atomic-swaps. The Plugins UI reads the cache to render row state and exposes "Upgrade" + "Check now"; a global `UpgradeBanner` in `LocksmithWindow` prompts restart after a successful upgrade.

**Tech Stack:** Python 3.14, PySide6 (Qt) `QTimer` for periodic polling, `subprocess` to drive `git` CLI, JSON files for state.

**Branch:** `feat/plugin-upgrade` (already created off `dev`). Direct merge back to `dev` when done; no PR.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `src/locksmith/plugins/storage.py` | modify | Add `update_cache_path`, `read_update_cache`, `write_update_cache`, `plugin_staging_dir`, `plugin_previous_dir`. |
| `src/locksmith/plugins/updates.py` | **new** | `PluginUpdateChecker` (plain class) — `_ls_remote` seam, `check_all_plugins`, `should_check_now`, subscribe/notify, cache I/O bridge. |
| `src/locksmith/plugins/installer.py` | modify | Add `PluginInstaller.upgrade(plugin_id)` method. |
| `src/locksmith/core/apping.py` | modify | Instantiate `PluginUpdateChecker` on `LocksmithApplication`. |
| `src/locksmith/ui/window.py` | modify | Construct a `QTimer` that drives the periodic check; inject `UpgradeBanner` above the page stack. |
| `src/locksmith/ui/plugins/upgrade_banner.py` | **new** | Restart-banner widget (shown above page stack when upgrade staged). |
| `src/locksmith/ui/plugins/page.py` | modify | Per-row update state ("update available" / Upgrade button) + page-header "Check now" button. |
| `tests/test_plugin_storage_updates.py` | **new** | Unit tests for the new storage helpers. |
| `tests/test_plugin_update_checker.py` | **new** | Unit tests for `PluginUpdateChecker` (poll, subscribe, error handling). |
| `tests/test_plugin_installer_upgrade.py` | **new** | Unit tests for `Installer.upgrade()` using a local bare-repo fixture. |
| `tests/test_plugin_upgrade_integration.py` | **new** | Harness-driven end-to-end test (wallet → cache → row → Upgrade → banner). |

---

## Task 1: Storage helpers for update cache + sidecar/previous dirs

**Files:**
- Modify: `src/locksmith/plugins/storage.py`
- Test: `tests/test_plugin_storage_updates.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_plugin_storage_updates.py`:

```python
"""Tests for the update-cache + sidecar/previous storage helpers."""
from __future__ import annotations

import json

import pytest

from locksmith.plugins import storage


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    return tmp_path


def test_update_cache_path_lives_under_plugin_root(home):
    assert storage.update_cache_path() == home / ".locksmith" / "plugins" / "update-cache.json"


def test_read_update_cache_returns_default_when_missing(home):
    cache = storage.read_update_cache()
    assert cache == {"format": 1, "interval_hours": 6, "plugins": {}}


def test_write_then_read_update_cache_roundtrips(home):
    payload = {
        "format": 1,
        "interval_hours": 6,
        "plugins": {
            "ui_tester": {
                "ref": "main",
                "installed_commit": "abc",
                "latest_commit": "def",
                "latest_checked_at": "2026-05-25T00:00:00Z",
                "update_available": True,
                "last_error": None,
            }
        },
    }
    storage.write_update_cache(payload)
    assert storage.read_update_cache() == payload


def test_read_update_cache_returns_default_on_malformed_json(home):
    path = storage.update_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    cache = storage.read_update_cache()
    assert cache == {"format": 1, "interval_hours": 6, "plugins": {}}


def test_plugin_staging_dir_path(home):
    assert storage.plugin_staging_dir("ui_tester") == (
        home / ".locksmith" / "plugins" / "ui_tester.staging"
    )


def test_plugin_previous_dir_path(home):
    assert storage.plugin_previous_dir("ui_tester") == (
        home / ".locksmith" / "plugins" / "ui_tester.previous"
    )


def test_write_update_cache_is_atomic(home, monkeypatch):
    # Sanity: corrupted in-flight write should not leave a half-written file.
    # We can't easily simulate a crash; assert that intermediate temp files
    # are cleaned up after a failure in the underlying write helper.
    payload = {"format": 1, "interval_hours": 6, "plugins": {}}
    storage.write_update_cache(payload)
    # Final file exists; no stray .tmp files alongside.
    cache_dir = storage.update_cache_path().parent
    tmps = [p for p in cache_dir.iterdir() if p.name.startswith("update-cache.json.")]
    assert tmps == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/seriouscoderone/code/locksmith
.venv/bin/python -m pytest tests/test_plugin_storage_updates.py -v
```

Expected: 7 FAILs with `AttributeError: module 'locksmith.plugins.storage' has no attribute 'update_cache_path'` (and similar).

- [ ] **Step 3: Add the helpers to `storage.py`**

Append to `src/locksmith/plugins/storage.py` (after `enable_list_path` definition, before `index_lock_path`):

```python
def update_cache_path() -> Path:
    """Path to the per-plugin update-check cache (background poll output)."""
    return plugin_root() / "update-cache.json"


def plugin_staging_dir(plugin_id: str) -> Path:
    """Sidecar directory used by Installer.upgrade() during clone+swap."""
    return plugin_root() / f"{plugin_id}.staging"


def plugin_previous_dir(plugin_id: str) -> Path:
    """One-generation rollback breadcrumb left after a successful upgrade."""
    return plugin_root() / f"{plugin_id}.previous"
```

And, alongside `read_index` / `write_index` (after `_default_enable_list`), add:

```python
def _default_update_cache() -> dict[str, Any]:
    return {"format": 1, "interval_hours": 6, "plugins": {}}


def read_update_cache() -> dict[str, Any]:
    """Read the update-check cache. Returns default if missing or malformed."""
    path = update_cache_path()
    if not path.exists():
        return _default_update_cache()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("plugin.update_cache.read_failed path=%s error=%s", path, e)
        return _default_update_cache()


def write_update_cache(payload: dict[str, Any]) -> None:
    """Atomically replace the update-check cache."""
    _atomic_write_json(update_cache_path(), payload)
    logger.info(
        "plugin.update_cache.written path=%s plugins=%d",
        update_cache_path(), len(payload.get("plugins", {})),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_plugin_storage_updates.py -v
```

Expected: 7 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/storage.py tests/test_plugin_storage_updates.py
git commit -m "feat(plugins): storage helpers for update cache + sidecar/previous dirs"
```

---

## Task 2: `PluginUpdateChecker` — pure cache logic + `_ls_remote` seam

This task adds the class with `check_all_plugins()`, `_ls_remote()`, `subscribe()`, and `cache()`. The Doer poll loop comes in Task 3.

**Files:**
- Create: `src/locksmith/plugins/updates.py`
- Test: `tests/test_plugin_update_checker.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_plugin_update_checker.py`:

```python
"""Tests for PluginUpdateChecker (cache logic + ls-remote seam)."""
from __future__ import annotations

import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from locksmith.plugins import storage
from locksmith.plugins.updates import PluginUpdateChecker


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    return tmp_path


def _seed_index(plugins):
    storage.write_index({"format": 1, "plugins": plugins})


def test_check_all_marks_update_available_when_remote_sha_differs(home, monkeypatch):
    _seed_index([{
        "plugin_id": "ui_tester",
        "source": {"type": "github", "user_repo": "x/y", "ref": None},
        "commit": "AAA",
        "installed_at": "2026-05-25T00:00:00Z",
        "manifest_snapshot": {},
    }])
    monkeypatch.setattr(
        "locksmith.plugins.updates._ls_remote",
        lambda url, ref: "BBB",
    )
    checker = PluginUpdateChecker(manager=None)
    checker.check_all_plugins()
    cache = checker.cache()
    entry = cache["plugins"]["ui_tester"]
    assert entry["installed_commit"] == "AAA"
    assert entry["latest_commit"] == "BBB"
    assert entry["update_available"] is True
    assert entry["last_error"] is None


def test_check_all_clears_update_available_when_remote_matches(home, monkeypatch):
    _seed_index([{
        "plugin_id": "ui_tester",
        "source": {"type": "github", "user_repo": "x/y", "ref": None},
        "commit": "AAA",
        "installed_at": "2026-05-25T00:00:00Z",
        "manifest_snapshot": {},
    }])
    monkeypatch.setattr(
        "locksmith.plugins.updates._ls_remote",
        lambda url, ref: "AAA",
    )
    checker = PluginUpdateChecker(manager=None)
    checker.check_all_plugins()
    assert checker.cache()["plugins"]["ui_tester"]["update_available"] is False


def test_check_all_skips_local_path_plugins(home, monkeypatch):
    _seed_index([{
        "plugin_id": "echo_app",
        "source": {"type": "local", "path": "/tmp/echo"},
        "commit": "local:2026-05-25T00:00:00",
        "installed_at": "2026-05-25T00:00:00Z",
        "manifest_snapshot": {},
    }])
    called = []
    monkeypatch.setattr(
        "locksmith.plugins.updates._ls_remote",
        lambda url, ref: called.append((url, ref)) or "BBB",
    )
    checker = PluginUpdateChecker(manager=None)
    checker.check_all_plugins()
    assert called == []
    assert "echo_app" not in checker.cache()["plugins"]


def test_check_all_records_last_error_on_subprocess_failure(home, monkeypatch):
    _seed_index([{
        "plugin_id": "ui_tester",
        "source": {"type": "github", "user_repo": "x/y", "ref": None},
        "commit": "AAA",
        "installed_at": "2026-05-25T00:00:00Z",
        "manifest_snapshot": {},
    }])

    def boom(url, ref):
        raise subprocess.CalledProcessError(128, "git ls-remote", stderr="repo not found")

    monkeypatch.setattr("locksmith.plugins.updates._ls_remote", boom)
    checker = PluginUpdateChecker(manager=None)
    checker.check_all_plugins()
    entry = checker.cache()["plugins"]["ui_tester"]
    assert entry["last_error"] is not None
    assert "repo not found" in entry["last_error"] or "exit 128" in entry["last_error"]


def test_check_all_one_plugin_failure_does_not_block_others(home, monkeypatch):
    _seed_index([
        {
            "plugin_id": "broken",
            "source": {"type": "github", "user_repo": "x/broken", "ref": None},
            "commit": "AAA", "installed_at": "0", "manifest_snapshot": {},
        },
        {
            "plugin_id": "fine",
            "source": {"type": "github", "user_repo": "x/fine", "ref": None},
            "commit": "AAA", "installed_at": "0", "manifest_snapshot": {},
        },
    ])

    def selective(url, ref):
        if "broken" in url:
            raise subprocess.CalledProcessError(128, "git", stderr="boom")
        return "BBB"

    monkeypatch.setattr("locksmith.plugins.updates._ls_remote", selective)
    checker = PluginUpdateChecker(manager=None)
    checker.check_all_plugins()
    cache = checker.cache()
    assert cache["plugins"]["broken"]["last_error"] is not None
    assert cache["plugins"]["fine"]["update_available"] is True


def test_subscribe_returns_unsubscribe_function(home):
    checker = PluginUpdateChecker(manager=None)
    callback = MagicMock()
    unsubscribe = checker.subscribe(callback)
    checker._notify_subscribers()
    callback.assert_called_once()
    unsubscribe()
    checker._notify_subscribers()
    callback.assert_called_once()  # not called again after unsubscribe


def test_check_all_notifies_subscribers(home, monkeypatch):
    _seed_index([{
        "plugin_id": "ui_tester",
        "source": {"type": "github", "user_repo": "x/y", "ref": None},
        "commit": "AAA", "installed_at": "0", "manifest_snapshot": {},
    }])
    monkeypatch.setattr("locksmith.plugins.updates._ls_remote", lambda u, r: "BBB")
    checker = PluginUpdateChecker(manager=None)
    callback = MagicMock()
    checker.subscribe(callback)
    checker.check_all_plugins()
    callback.assert_called()


def test_ls_remote_returns_first_sha(monkeypatch):
    """Direct unit test for the seam: parses git ls-remote stdout correctly."""
    from locksmith.plugins import updates

    sample_stdout = "a3f9c1dabe7c0f5e8b7a2b9d0c4e1f2a3b4c5d6e\tHEAD\n"
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stdout=sample_stdout, stderr=""),
    )
    assert updates._ls_remote("https://github.com/x/y.git", "HEAD").startswith("a3f9c1d")


def test_ls_remote_raises_on_nonzero_exit(monkeypatch):
    from locksmith.plugins import updates

    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **kw: SimpleNamespace(returncode=128, stdout="", stderr="not found"),
    )
    with pytest.raises(subprocess.CalledProcessError):
        updates._ls_remote("https://github.com/x/missing.git", "HEAD")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_plugin_update_checker.py -v
```

Expected: `ImportError: cannot import name 'PluginUpdateChecker' from 'locksmith.plugins.updates'` (module doesn't exist).

- [ ] **Step 3: Create `src/locksmith/plugins/updates.py`**

```python
# -*- encoding: utf-8 -*-
"""
locksmith.plugins.updates module

Background poll for plugin updates. PluginUpdateChecker reads
~/.locksmith/plugins/index.json, runs `git ls-remote` per github-source
plugin, and writes the result to ~/.locksmith/plugins/update-cache.json.
The Qt main window owns a QTimer that calls check_now() periodically.

See docs/superpowers/specs/2026-05-25-plugin-upgrade-design.md.
"""
from __future__ import annotations

import datetime
import subprocess
from typing import Any, Callable

from keri import help

from locksmith.plugins import storage

logger = help.ogler.getLogger(__name__)


def _ls_remote(url: str, ref: str) -> str:
    """Return the SHA at the given ref on the given remote URL.

    Raises subprocess.CalledProcessError on non-zero exit.
    """
    result = subprocess.run(
        ["git", "ls-remote", url, ref],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, ["git", "ls-remote", url, ref],
            output=result.stdout, stderr=result.stderr,
        )
    first_line = result.stdout.splitlines()[0] if result.stdout else ""
    sha = first_line.split("\t")[0].strip() if first_line else ""
    if not sha:
        raise subprocess.CalledProcessError(
            -1, ["git", "ls-remote", url, ref],
            output=result.stdout, stderr="empty ls-remote output",
        )
    return sha


def _now_iso() -> str:
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"


class PluginUpdateChecker:
    """Compares installed plugin SHAs to remote HEAD and maintains a cache.

    Plain Python — the Qt main window drives a QTimer that calls check_now()
    periodically. Subscribers are notified on whichever thread invokes
    check_all_plugins() (in production that's always the Qt main thread).
    """

    def __init__(self, manager: Any, *, interval_hours: int = 6):
        self._manager = manager
        self._interval_seconds = interval_hours * 3600
        self._subscribers: list[Callable[[], None]] = []

    @property
    def interval_seconds(self) -> int:
        return self._interval_seconds

    def cache(self) -> dict[str, Any]:
        """Return the current update cache (read fresh from disk each call)."""
        return storage.read_update_cache()

    def subscribe(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Register a callback fired after each check_all_plugins() pass.
        Returns an unsubscribe function."""
        self._subscribers.append(callback)

        def _unsubscribe() -> None:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

        return _unsubscribe

    def check_now(self) -> None:
        """Run check_all_plugins() unconditionally. Called by the UI button
        and by the QTimer in LocksmithWindow."""
        self.check_all_plugins()

    def should_check_now(self) -> bool:
        """True if the cache is missing or older than interval_seconds.
        Used at startup to decide whether to fire an immediate check."""
        cache = storage.read_update_cache()
        elapsed = self._elapsed_since(cache.get("checked_at"))
        return elapsed is None or elapsed >= self._interval_seconds

    def check_all_plugins(self) -> None:
        """One full pass: for every github-source plugin in the index,
        run ls-remote and update the cache. Notify subscribers at the end."""
        idx = storage.read_index()
        cache = storage.read_update_cache()
        cache.setdefault("plugins", {})

        installed_ids = set()
        for record in idx.get("plugins", []):
            pid = record["plugin_id"]
            source = record.get("source", {})
            if source.get("type") != "github":
                continue
            installed_ids.add(pid)
            self._check_one(record, source, cache)

        # Drop cache entries for plugins no longer in the index.
        cache["plugins"] = {
            pid: entry for pid, entry in cache["plugins"].items() if pid in installed_ids
        }

        cache["checked_at"] = _now_iso()
        storage.write_update_cache(cache)
        self._notify_subscribers()

    # ----- internals ------------------------------------------------------

    def _check_one(
        self, record: dict[str, Any], source: dict[str, Any], cache: dict[str, Any],
    ) -> None:
        pid = record["plugin_id"]
        user_repo = source.get("user_repo")
        ref = source.get("ref") or "HEAD"
        url = f"https://github.com/{user_repo}.git"
        installed = record["commit"]
        existing = cache["plugins"].get(pid, {})
        try:
            latest = _ls_remote(url, ref)
        except subprocess.CalledProcessError as e:
            err = (e.stderr or "").strip() or f"ls-remote exit {e.returncode}"
            cache["plugins"][pid] = {
                "ref": ref,
                "installed_commit": installed,
                "latest_commit": existing.get("latest_commit"),
                "latest_checked_at": _now_iso(),
                "update_available": existing.get("update_available", False),
                "last_error": f"ls-remote: {err}",
            }
            logger.info(
                "plugin.update.check_failed plugin_id=%s error=%s", pid, err,
            )
            return
        except Exception as e:  # noqa: BLE001
            logger.exception("plugin.update.unexpected_check_failure plugin_id=%s", pid)
            cache["plugins"][pid] = {
                "ref": ref,
                "installed_commit": installed,
                "latest_commit": existing.get("latest_commit"),
                "latest_checked_at": _now_iso(),
                "update_available": existing.get("update_available", False),
                "last_error": f"unexpected: {type(e).__name__}: {e}",
            }
            return

        cache["plugins"][pid] = {
            "ref": ref,
            "installed_commit": installed,
            "latest_commit": latest,
            "latest_checked_at": _now_iso(),
            "update_available": latest != installed,
            "last_error": None,
        }
        logger.info(
            "plugin.update.checked plugin_id=%s installed=%s latest=%s update_available=%s",
            pid, installed[:7], latest[:7], latest != installed,
        )

    def _elapsed_since(self, iso: str | None) -> float | None:
        if not iso:
            return None
        try:
            ts = datetime.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return None
        return (datetime.datetime.utcnow() - ts).total_seconds()

    def _notify_subscribers(self) -> None:
        for cb in list(self._subscribers):
            try:
                cb()
            except Exception:  # noqa: BLE001
                logger.exception("plugin.update.subscriber_failure")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_plugin_update_checker.py -v
```

Expected: 9 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/updates.py tests/test_plugin_update_checker.py
git commit -m "feat(plugins): PluginUpdateChecker with ls-remote seam, subscribe, error isolation"
```

---

## Task 3: `PluginUpdateChecker` — `should_check_now()` scheduling helper

The class already has `should_check_now()` from Task 2. Add tests so the QTimer wiring in Task 4 has a tested invariant to rely on.

**Files:**
- Modify: `tests/test_plugin_update_checker.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_plugin_update_checker.py`:

```python
def _iso_minus_seconds(seconds: int) -> str:
    import datetime
    t = datetime.datetime.utcnow() - datetime.timedelta(seconds=seconds)
    return t.isoformat(timespec="seconds") + "Z"


def test_should_check_now_true_when_cache_missing(home):
    checker = PluginUpdateChecker(manager=None, interval_hours=6)
    assert checker.should_check_now() is True


def test_should_check_now_true_when_cache_stale(home):
    storage.write_update_cache({
        "format": 1, "interval_hours": 6,
        "checked_at": _iso_minus_seconds(7 * 3600),  # 7h ago, > 6h interval
        "plugins": {},
    })
    checker = PluginUpdateChecker(manager=None, interval_hours=6)
    assert checker.should_check_now() is True


def test_should_check_now_false_when_cache_fresh(home):
    storage.write_update_cache({
        "format": 1, "interval_hours": 6,
        "checked_at": _iso_minus_seconds(60),  # 1m ago, well within 6h
        "plugins": {},
    })
    checker = PluginUpdateChecker(manager=None, interval_hours=6)
    assert checker.should_check_now() is False


def test_should_check_now_true_when_checked_at_unparseable(home):
    storage.write_update_cache({
        "format": 1, "interval_hours": 6,
        "checked_at": "not-an-iso-timestamp",
        "plugins": {},
    })
    checker = PluginUpdateChecker(manager=None, interval_hours=6)
    assert checker.should_check_now() is True
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_plugin_update_checker.py -v
```

Expected: 13 PASSED (9 from Task 2 + 4 new).

- [ ] **Step 3: Commit**

```bash
git add tests/test_plugin_update_checker.py
git commit -m "test(plugins): cover PluginUpdateChecker.should_check_now scheduling"
```

---

## Task 4: Mount checker in app + QTimer in window

**Files:**
- Modify: `src/locksmith/core/apping.py`
- Modify: `src/locksmith/ui/window.py`

The checker is constructed in `apping.py` (so it lives for the lifetime of the `LocksmithApplication`). The `QTimer` is owned by `LocksmithWindow` (timers need a `QObject` parent).

- [ ] **Step 1: Add the checker to `apping.py`**

In `src/locksmith/core/apping.py`, after line 14 add the import:

```python
from locksmith.plugins.updates import PluginUpdateChecker
```

And after `self.plugin_manager = PluginManager(...)` (around line 57), add:

```python
        self.plugin_update_checker = PluginUpdateChecker(manager=self.plugin_manager)
        logger.info(
            "plugin_update_checker.constructed interval_hours=%d",
            self.plugin_update_checker.interval_seconds // 3600,
        )
```

- [ ] **Step 2: Wire the QTimer in `window.py`**

In `src/locksmith/ui/window.py`, add the QTimer at the END of `LocksmithWindow.__init__`, immediately *before* the existing `self.app.plugin_manager.on_app_started(window=self)` call (around line 140). Placing it at the end (rather than near the central-widget setup at line 71) avoids conflicts with the banner injection in Task 8.

```python
        # --- Plugin update polling ---
        # Fires check_now() every interval_seconds via QTimer. Immediate check
        # at startup if the cache is stale (or missing).
        from PySide6.QtCore import QTimer

        self.plugin_update_timer = QTimer(self)
        self.plugin_update_timer.setInterval(
            self.app.plugin_update_checker.interval_seconds * 1000,
        )
        self.plugin_update_timer.timeout.connect(
            self.app.plugin_update_checker.check_now,
        )
        self.plugin_update_timer.start()

        if self.app.plugin_update_checker.should_check_now():
            QTimer.singleShot(0, self.app.plugin_update_checker.check_now)
        # --- end plugin update polling ---

        self.app.plugin_manager.on_app_started(window=self)  # unchanged existing line
```

(The last line is shown just so you can identify the right insertion point — don't duplicate it. Insert the QTimer block above the *existing* `on_app_started` call.)

- [ ] **Step 3: Smoke-run the wallet**

```bash
LOCKSMITH_ENVIRONMENT=development poetry run python -m locksmith &
LOCKSMITH_PID=$!
sleep 8
# Should see both "plugin_update_checker.constructed" and "plugin.update_cache.written" in logs
kill $LOCKSMITH_PID
```

Expected: log line `plugin_update_checker.constructed interval_hours=6` at startup. If the cache was stale or missing, `plugin.update_cache.written` shortly after.

- [ ] **Step 4: Commit**

```bash
git add src/locksmith/core/apping.py src/locksmith/ui/window.py
git commit -m "feat(apping,window): construct PluginUpdateChecker + QTimer-driven poll"
```

---

## Task 5: `PluginInstaller.upgrade()` — sidecar clone + atomic swap

**Files:**
- Modify: `src/locksmith/plugins/installer.py`
- Test: `tests/test_plugin_installer_upgrade.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_plugin_installer_upgrade.py`:

```python
"""Tests for PluginInstaller.upgrade() — sidecar clone + atomic swap."""
from __future__ import annotations

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


def _install_at(installer, monkeypatch, sha):
    """Install the echo-app fixture as a github plugin, faking the clone."""
    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "clone"]:
            dest = Path(cmd[-1])
            shutil.copytree(FIXTURE_ROOT / "echo-app", dest)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    def fake_check_output(cmd, **kwargs):
        return (sha + "\n").encode()

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(subprocess, "check_output", fake_check_output)
    return installer.install(
        SourceDescriptor(type="github", user_repo="acme/echo", ref=None),
    )


def test_upgrade_swaps_clone_and_updates_index(installer, monkeypatch, tmp_path):
    _install_at(installer, monkeypatch, "AAA")
    # Simulate new commit on remote
    def fake_run_v2(cmd, **kwargs):
        if cmd[:2] == ["git", "clone"]:
            dest = Path(cmd[-1])
            shutil.copytree(FIXTURE_ROOT / "echo-app", dest)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run_v2)
    monkeypatch.setattr(subprocess, "check_output", lambda cmd, **kw: b"BBB\n")

    new_record = installer.upgrade("echo_app")
    assert new_record["commit"] == "BBB"
    assert new_record["previous_commit"] == "AAA"
    assert storage.plugin_previous_dir("echo_app").exists()
    assert not storage.plugin_staging_dir("echo_app").exists()
    idx = storage.read_index()
    rec = [p for p in idx["plugins"] if p["plugin_id"] == "echo_app"][0]
    assert rec["commit"] == "BBB"
    assert rec["previous_commit"] == "AAA"


def test_upgrade_clears_cache_update_available(installer, monkeypatch):
    _install_at(installer, monkeypatch, "AAA")
    storage.write_update_cache({
        "format": 1, "interval_hours": 6,
        "plugins": {
            "echo_app": {
                "ref": "HEAD", "installed_commit": "AAA", "latest_commit": "BBB",
                "latest_checked_at": "x", "update_available": True, "last_error": None,
            }
        },
    })
    monkeypatch.setattr(subprocess, "check_output", lambda cmd, **kw: b"BBB\n")
    installer.upgrade("echo_app")
    entry = storage.read_update_cache()["plugins"]["echo_app"]
    assert entry["installed_commit"] == "BBB"
    assert entry["latest_commit"] == "BBB"
    assert entry["update_available"] is False
    assert entry["last_error"] is None


def test_upgrade_rejects_local_path_source(installer, monkeypatch):
    """Local-path plugins have no remote; upgrade should error explicitly."""
    src = SourceDescriptor(type="local", path=str(FIXTURE_ROOT / "echo-app"))
    installer.install(src)
    with pytest.raises(InstallError) as exc:
        installer.upgrade("echo_app")
    assert "local" in str(exc.value).lower()


def test_upgrade_rejects_unknown_plugin(installer):
    with pytest.raises(InstallError) as exc:
        installer.upgrade("not-installed")
    assert "not installed" in str(exc.value).lower()


def test_upgrade_failure_leaves_clone_dir_intact(installer, monkeypatch):
    _install_at(installer, monkeypatch, "AAA")
    # Sabotage the staging clone
    def failing_run(cmd, **kwargs):
        if cmd[:2] == ["git", "clone"]:
            return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="boom")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", failing_run)
    with pytest.raises(InstallError):
        installer.upgrade("echo_app")
    # Final dir still present at original SHA
    assert storage.plugin_clone_dir("echo_app").exists()
    idx = storage.read_index()
    rec = [p for p in idx["plugins"] if p["plugin_id"] == "echo_app"][0]
    assert rec["commit"] == "AAA"
    # No leftover staging
    assert not storage.plugin_staging_dir("echo_app").exists()


def test_upgrade_rejects_changed_plugin_id(installer, monkeypatch, tmp_path):
    """Defends against the remote repo's manifest being edited to claim a different plugin_id."""
    _install_at(installer, monkeypatch, "AAA")

    # Build a staging fixture with a different plugin_id in its manifest.
    different_id_src = tmp_path / "different-id-src"
    shutil.copytree(FIXTURE_ROOT / "echo-app", different_id_src)
    toml_path = different_id_src / "locksmith-plugin.toml"
    toml_path.write_text(
        toml_path.read_text().replace('plugin_id = "echo_app"', 'plugin_id = "other_id"'),
        encoding="utf-8",
    )

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "clone"]:
            dest = Path(cmd[-1])
            shutil.copytree(different_id_src, dest)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(subprocess, "check_output", lambda cmd, **kw: b"BBB\n")
    with pytest.raises(InstallError) as exc:
        installer.upgrade("echo_app")
    assert "plugin_id" in str(exc.value)
    assert not storage.plugin_staging_dir("echo_app").exists()
    # Original install untouched
    idx = storage.read_index()
    rec = [p for p in idx["plugins"] if p["plugin_id"] == "echo_app"][0]
    assert rec["commit"] == "AAA"


def test_upgrade_overwrites_existing_previous_dir(installer, monkeypatch, tmp_path):
    _install_at(installer, monkeypatch, "AAA")
    # First upgrade to BBB, populating .previous
    monkeypatch.setattr(subprocess, "check_output", lambda cmd, **kw: b"BBB\n")
    installer.upgrade("echo_app")
    assert storage.plugin_previous_dir("echo_app").exists()
    # Write a marker into .previous so we can detect it being replaced
    (storage.plugin_previous_dir("echo_app") / "MARKER_FROM_FIRST_UPGRADE").write_text("x")

    # Second upgrade to CCC — .previous should now reflect BBB, not the original AAA marker
    monkeypatch.setattr(subprocess, "check_output", lambda cmd, **kw: b"CCC\n")
    installer.upgrade("echo_app")
    assert not (storage.plugin_previous_dir("echo_app") / "MARKER_FROM_FIRST_UPGRADE").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_plugin_installer_upgrade.py -v
```

Expected: 7 FAILs with `AttributeError: 'PluginInstaller' object has no attribute 'upgrade'`.

- [ ] **Step 3: Add `upgrade()` to `PluginInstaller`**

In `src/locksmith/plugins/installer.py`, after the `uninstall()` method (around line 119), insert:

```python
    def upgrade(self, plugin_id: str) -> dict[str, Any]:
        """Re-fetch latest commit for a github-source plugin via sidecar
        clone + atomic swap. Returns the new index record.

        Raises InstallError on failure; the existing clone is left intact.
        See docs/superpowers/specs/2026-05-25-plugin-upgrade-design.md.
        """
        logger.info("plugin.upgrade.requested plugin_id=%s", plugin_id)
        idx = storage.read_index()
        record = next(
            (p for p in idx.get("plugins", []) if p["plugin_id"] == plugin_id),
            None,
        )
        if record is None:
            raise InstallError(f"plugin not installed: {plugin_id}")

        source_dict = record.get("source", {})
        if source_dict.get("type") != "github":
            raise InstallError(
                f"plugin '{plugin_id}' has source type "
                f"'{source_dict.get('type')}' — upgrade only supports github sources; "
                f"uninstall and reinstall to pick up changes."
            )

        source = SourceDescriptor(
            type="github",
            user_repo=source_dict.get("user_repo"),
            ref=source_dict.get("ref"),
        )

        staging = storage.plugin_staging_dir(plugin_id)
        previous = storage.plugin_previous_dir(plugin_id)
        final = storage.plugin_clone_dir(plugin_id)
        old_sha = record["commit"]

        # Stage fresh clone
        if staging.exists():
            shutil.rmtree(staging)
        try:
            storage.plugin_root().mkdir(parents=True, exist_ok=True)
            staging.mkdir()
            new_sha = self._fetch_into(source, staging)
            manifest = self._parse_manifest_in(staging)
            if manifest.plugin_id != plugin_id:
                raise InstallError(
                    f"new manifest declares plugin_id={manifest.plugin_id!r}, "
                    f"expected {plugin_id!r}"
                )
        except InstallError:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            raise
        except Exception as e:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            logger.exception("plugin.upgrade.staging_failure plugin_id=%s", plugin_id)
            raise InstallError(f"upgrade staging failed: {e}") from e

        # Atomic swap
        if previous.exists():
            shutil.rmtree(previous)
        try:
            final.rename(previous)
        except OSError as e:
            shutil.rmtree(staging, ignore_errors=True)
            raise InstallError(f"could not move old clone aside: {e}") from e

        try:
            staging.rename(final)
        except OSError as e:
            # Best-effort rollback: put the old clone back in place
            try:
                previous.rename(final)
            except OSError:
                logger.exception(
                    "plugin.upgrade.swap_unrecoverable plugin_id=%s "
                    "previous=%s staging=%s final=%s",
                    plugin_id, previous, staging, final,
                )
            shutil.rmtree(staging, ignore_errors=True)
            raise InstallError(f"could not swap new clone into place: {e}") from e

        # Update index
        with storage.index_write_lock():
            idx = storage.read_index()
            for p in idx.get("plugins", []):
                if p["plugin_id"] == plugin_id:
                    p["commit"] = new_sha
                    p["installed_at"] = (
                        datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
                    )
                    p["manifest_snapshot"] = manifest.to_dict()
                    p["previous_commit"] = old_sha
                    break
            storage.write_index(idx)
            new_record = next(p for p in idx["plugins"] if p["plugin_id"] == plugin_id)

        # Update cache: reflect new installed_commit, clear update_available
        cache = storage.read_update_cache()
        if plugin_id in cache.get("plugins", {}):
            entry = cache["plugins"][plugin_id]
            entry["installed_commit"] = new_sha
            entry["latest_commit"] = new_sha
            entry["update_available"] = False
            entry["last_error"] = None
        storage.write_update_cache(cache)

        logger.info(
            "plugin.upgrade.completed plugin_id=%s old=%s new=%s",
            plugin_id, old_sha[:7], new_sha[:7],
        )
        return new_record
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_plugin_installer_upgrade.py -v
```

Expected: 7 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/plugins/installer.py tests/test_plugin_installer_upgrade.py
git commit -m "feat(installer): add upgrade(plugin_id) — sidecar clone + atomic swap"
```

---

## Task 6: `UpgradeBanner` widget

**Files:**
- Create: `src/locksmith/ui/plugins/upgrade_banner.py`
- Test: covered by integration test (Task 9). Widget is too simple for a standalone unit test.

- [ ] **Step 1: Create the widget**

`src/locksmith/ui/plugins/upgrade_banner.py`:

```python
# -*- encoding: utf-8 -*-
"""
locksmith.ui.plugins.upgrade_banner module

Global banner shown above the page stack when one or more plugins have
been upgraded in the current session. Clicking "Restart now" emits
`restart_requested`; the LocksmithWindow already has
`_handle_restart_requested` that does the actual relaunch (reused from
the post-uninstall flow).
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QWidget,
)


class UpgradeBanner(QWidget):
    """Restart-prompt banner. Hidden by default; show_banner() reveals it."""

    restart_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self.setObjectName("UpgradeBanner")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(12)

        self._label = QLabel("⟳  Plugin update staged. Restart Locksmith to activate.")
        layout.addWidget(self._label, stretch=1)

        self._restart_button = QPushButton("Restart now")
        self._restart_button.setObjectName("UpgradeBannerRestartButton")
        self._restart_button.clicked.connect(self.restart_requested.emit)
        layout.addWidget(self._restart_button)

        self.hide()

    def show_banner(self) -> None:
        """Reveal the banner. Idempotent."""
        self.show()
```

- [ ] **Step 2: Verify the import doesn't break anything**

```bash
.venv/bin/python -c "from locksmith.ui.plugins.upgrade_banner import UpgradeBanner; print('OK')"
```

Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add src/locksmith/ui/plugins/upgrade_banner.py
git commit -m "feat(ui): UpgradeBanner widget for post-upgrade restart prompt"
```

---

## Task 7: Plugins page — per-row update state + "Upgrade" button

**Files:**
- Modify: `src/locksmith/ui/plugins/page.py`
- Test: covered by integration test (Task 9).

This task assumes Task 4 mounted `app.plugin_update_checker`. The Plugins page reads the cache via `app.plugin_update_checker.cache()`, subscribes to changes, and renders per-row state.

- [ ] **Step 1: Read the existing row builder**

```bash
grep -n "_make_row\|bottom_row\|uninstall_btn\|exclude_btn" src/locksmith/ui/plugins/page.py | head -30
```

Locate `_make_row` (around line 235) — the function that builds the per-plugin row's bottom action area.

- [ ] **Step 2: Add the row helpers**

In `src/locksmith/ui/plugins/page.py`, near the other marker subclasses (around line 79), add:

```python
    class UpgradeButton(QPushButton):
        pass

    class UpdateStateLabel(QLabel):
        pass
```

In `__init__` (around line 91-97), subscribe to the checker:

```python
        # Subscribe to update-checker notifications. The check runs on the
        # Qt main thread (driven by QTimer), so the callback can directly
        # touch widgets without marshalling.
        self._update_unsubscribe = None
        checker = getattr(self.app, "plugin_update_checker", None)
        if checker is not None:
            self._update_unsubscribe = checker.subscribe(self._refresh)
```

In `closeEvent` (add one if absent at the bottom of the class):

```python
    def closeEvent(self, ev):  # noqa: N802
        if self._update_unsubscribe is not None:
            self._update_unsubscribe()
            self._update_unsubscribe = None
        super().closeEvent(ev)
```

In `_make_row` after the existing `bottom_row` is populated, add the update-state widget and Upgrade button (only for github-source plugins):

```python
        # Update-state hint + Upgrade button, driven from the update cache.
        checker = getattr(self.app, "plugin_update_checker", None)
        is_github = state.source.get("type") == "github"
        if checker is not None and is_github:
            cache = checker.cache()
            entry = cache.get("plugins", {}).get(state.plugin_id, {})
            state_label = self.UpdateStateLabel()
            state_label.setObjectName(f"_update_state_label_{state.plugin_id}")
            if entry.get("last_error"):
                state_label.setText("couldn't check ⚠")
                state_label.setToolTip(entry["last_error"])
                bottom_row.addWidget(state_label)
            elif entry.get("update_available"):
                state_label.setText("update available")
                bottom_row.addWidget(state_label)
                upgrade_btn = self.UpgradeButton("Upgrade")
                upgrade_btn.setObjectName(f"_upgrade_btn_{state.plugin_id}")
                upgrade_btn.clicked.connect(
                    lambda _checked=False, pid=state.plugin_id: self._on_upgrade_clicked(pid),
                )
                bottom_row.addWidget(upgrade_btn)
```

Add the click handler near `_on_install_button_clicked` (around line 325):

```python
    def _on_upgrade_clicked(self, plugin_id: str) -> None:
        """Run installer.upgrade(plugin_id), then show the restart banner."""
        from locksmith.plugins.installer import InstallError, PluginInstaller

        installer = PluginInstaller()
        try:
            installer.upgrade(plugin_id)
        except InstallError as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Upgrade failed", str(e))
            return
        # Surface the global restart banner.
        window = self.window()
        banner = getattr(window, "upgrade_banner", None)
        if banner is not None:
            banner.show_banner()
        self._refresh()
```

- [ ] **Step 3: Smoke-run the wallet to confirm no regressions on Plugins page**

```bash
LOCKSMITH_ENVIRONMENT=development poetry run python -m locksmith &
LOCKSMITH_PID=$!
sleep 6
# Use ui-tester to navigate to Plugins and snapshot.
devctl click '{"target": "Plugins"}' || true
devctl screenshot '{"path": "/tmp/plugins-page.png"}' || true
kill $LOCKSMITH_PID
```

Expected: wallet starts, Plugins page renders, no crashes. If `ui_tester` is installed, its row may show `update available` + Upgrade button (if a new SHA is on remote).

- [ ] **Step 4: Commit**

```bash
git add src/locksmith/ui/plugins/page.py
git commit -m "feat(plugins-page): per-row update state + Upgrade button"
```

---

## Task 8: Plugins page — "Check now" button + Window banner injection

**Files:**
- Modify: `src/locksmith/ui/plugins/page.py`
- Modify: `src/locksmith/ui/window.py`

- [ ] **Step 1: Add "Check now" button to Plugins page header**

In `src/locksmith/ui/plugins/page.py` `_build_ui` (around the install panel area), add a button near the page header:

```python
        # "Check now" button — manual refresh of the update cache.
        self._check_now_button = QPushButton("Check now")
        self._check_now_button.setObjectName("PluginsCheckNowButton")
        self._check_now_button.clicked.connect(self._on_check_now_clicked)
        # Insert into the existing header row layout (adjust to match the existing pattern).
        # Look for the existing header QHBoxLayout in _build_ui — append there.
```

And the handler near `_on_upgrade_clicked`:

```python
    def _on_check_now_clicked(self) -> None:
        checker = getattr(self.app, "plugin_update_checker", None)
        if checker is None:
            return
        self._check_now_button.setEnabled(False)
        try:
            checker.check_now()
        finally:
            self._check_now_button.setEnabled(True)
        self._refresh()
```

If `_build_ui` doesn't have an obvious header `QHBoxLayout`, create one and insert the button alongside the existing install-tile area. Keep the change minimal — one new layout row at most.

- [ ] **Step 2: Inject UpgradeBanner in `LocksmithWindow`**

The current `LocksmithWindow.__init__` builds the central widget like this (around line 68–73 of `src/locksmith/ui/window.py`):

```python
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
```

`main_layout` ends up holding just `self.main_stack` (line ~124). To inject the banner above the stack, change `main_layout` to vertical and add the banner first:

```python
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        outer_layout = QVBoxLayout(central_widget)        # was QHBoxLayout
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Global restart banner — hidden until a plugin upgrade lands.
        from locksmith.ui.plugins.upgrade_banner import UpgradeBanner
        self.upgrade_banner = UpgradeBanner(parent=central_widget)
        self.upgrade_banner.restart_requested.connect(self._handle_restart_requested)
        outer_layout.addWidget(self.upgrade_banner)

        # Horizontal container holds the page stack (preserves the original layout shape).
        stack_holder = QWidget()
        outer_layout.addWidget(stack_holder)
        main_layout = QHBoxLayout(stack_holder)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
```

Then leave the rest of `__init__` (`self.main_stack = QStackedWidget()` and `main_layout.addWidget(self.main_stack)`) untouched — `main_layout` now points at the inner holder so existing code still works.

Reuse of `_handle_restart_requested` (already defined in `window.py` for the uninstall-restart flow) gives us the same robust QProcess-based relaunch the existing flow uses.

- [ ] **Step 3: Smoke-run the wallet**

```bash
LOCKSMITH_ENVIRONMENT=development poetry run python -m locksmith &
LOCKSMITH_PID=$!
sleep 6
devctl click '{"target": "Plugins"}' || true
devctl click '{"target": "Check now"}' || true
devctl screenshot '{"path": "/tmp/plugins-check-now.png"}' || true
kill $LOCKSMITH_PID
```

Expected: clicking "Check now" disables the button briefly and triggers a refresh. The banner is not yet visible (no upgrade has run).

- [ ] **Step 4: Commit**

```bash
git add src/locksmith/ui/plugins/page.py src/locksmith/ui/window.py
git commit -m "feat(ui): Check-now button + UpgradeBanner injection in main window"
```

---

## Task 9: End-to-end integration test (cache → row → Upgrade → banner)

This test drives the running wallet via the `locksmith-ui-tester` `devctl` harness. It uses a local bare-repo fixture as the "GitHub" remote so the test is hermetic.

**Files:**
- Create: `tests/test_plugin_upgrade_integration.py`

- [ ] **Step 1: Write the test**

`tests/test_plugin_upgrade_integration.py`:

```python
"""End-to-end test: install → bump remote → check_now → row shows update →
click Upgrade → banner appears → index.json reflects new commit.

Uses a local bare-repo as the github remote. The fake URL passed into the
installer is monkeypatched at the storage layer (via the source's user_repo)
to point at file:// instead of github.com.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from locksmith.plugins import storage
from locksmith.plugins.installer import PluginInstaller, SourceDescriptor
from locksmith.plugins.updates import PluginUpdateChecker


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "plugins"


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def fake_remote(tmp_path):
    """Build a bare git repo on disk that's reachable via file:// URL.
    Commit content from fixtures/plugins/echo-app at HEAD."""
    work = tmp_path / "work"
    shutil.copytree(FIXTURE_ROOT / "echo-app", work)
    subprocess.check_call(["git", "init", "-q", str(work)])
    subprocess.check_call(["git", "-C", str(work), "add", "."])
    subprocess.check_call(
        ["git", "-C", str(work), "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-q", "-m", "v1"],
    )
    bare = tmp_path / "remote.git"
    subprocess.check_call(["git", "clone", "-q", "--bare", str(work), str(bare)])
    return work, bare


def test_full_cycle_install_check_upgrade(home, fake_remote, monkeypatch):
    work, bare = fake_remote

    # Steer the installer's URL builder + checker's URL builder at file://
    fake_url = f"file://{bare}"

    def fake_fetch_run(cmd, **kw):
        if cmd[:2] == ["git", "clone"]:
            # Replace the github URL with our file:// URL and let the real git CLI run.
            cmd = [arg if not arg.startswith("https://github.com/") else fake_url for arg in cmd]
            return subprocess.run(cmd, **kw)
        return subprocess.run(cmd, **kw)

    monkeypatch.setattr(subprocess, "run", fake_fetch_run)

    # 1) Install echo_app from the fake github source
    installer = PluginInstaller()
    installer.install(SourceDescriptor(type="github", user_repo="acme/echo", ref=None))
    idx = storage.read_index()
    rec = [p for p in idx["plugins"] if p["plugin_id"] == "echo_app"][0]
    sha_v1 = rec["commit"]

    # 2) Bump the bare remote with a new commit
    (work / "BUMP").write_text("v2", encoding="utf-8")
    subprocess.check_call(["git", "-C", str(work), "add", "BUMP"])
    subprocess.check_call(
        ["git", "-C", str(work), "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-q", "-m", "v2"],
    )
    subprocess.check_call(["git", "-C", str(work), "push", "-q", str(bare), "HEAD:master"])

    # 3) Drive ls-remote at the fake URL
    def fake_ls_remote(url, ref):
        # The checker computes https://github.com/acme/echo.git; swap it for file://
        if url.startswith("https://github.com/"):
            url = fake_url
        result = subprocess.run(
            ["git", "ls-remote", url, ref], capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout.splitlines()[0].split("\t")[0].strip()

    monkeypatch.setattr("locksmith.plugins.updates._ls_remote", fake_ls_remote)

    # 4) check_now → cache reflects update available
    checker = PluginUpdateChecker(manager=None)
    checker.check_now()
    entry = checker.cache()["plugins"]["echo_app"]
    assert entry["update_available"] is True
    assert entry["latest_commit"] != sha_v1

    # 5) Upgrade
    installer.upgrade("echo_app")
    idx = storage.read_index()
    rec2 = [p for p in idx["plugins"] if p["plugin_id"] == "echo_app"][0]
    assert rec2["commit"] != sha_v1
    assert rec2["previous_commit"] == sha_v1

    # 6) Cache reflects "all caught up"
    entry2 = storage.read_update_cache()["plugins"]["echo_app"]
    assert entry2["update_available"] is False
    assert entry2["installed_commit"] == rec2["commit"]

    # 7) .previous breadcrumb exists
    assert storage.plugin_previous_dir("echo_app").exists()
```

- [ ] **Step 2: Run the test**

```bash
.venv/bin/python -m pytest tests/test_plugin_upgrade_integration.py -v
```

Expected: 1 PASSED.

- [ ] **Step 3: Commit**

```bash
git add tests/test_plugin_upgrade_integration.py
git commit -m "test(plugins): end-to-end integration — install, check, upgrade, cache"
```

---

## Task 10: Run full test suite + manual smoke

- [ ] **Step 1: Run all plugin tests**

```bash
.venv/bin/python -m pytest tests/test_plugin_storage_updates.py \
                          tests/test_plugin_update_checker.py \
                          tests/test_plugin_installer_upgrade.py \
                          tests/test_plugin_upgrade_integration.py \
                          tests/test_plugins_installer.py \
                          tests/test_plugins_storage.py \
                          tests/test_plugins_concurrency.py \
                          tests/test_plugins_integration.py \
                          tests/test_plugins_manager.py -v
```

Expected: all green. Existing plugin tests should not regress.

- [ ] **Step 2: Run the broader test suite to catch indirect regressions**

```bash
.venv/bin/python -m pytest tests/ -x --ignore=tests/test_keri_v2_compat.py 2>&1 | tail -30
```

`test_keri_v2_compat.py` is excluded because it has known pre-existing failures unrelated to this work (keripy 2.0 API rename `makeOwnEvent` → `msgOwnEvent`, documented during the receiptor migration).

Expected: all green except optionally-skipped tests.

- [ ] **Step 3: Manual smoke — full upgrade cycle against real GitHub**

```bash
# Bring up the wallet with the harness plugin installed and the ui_tester source pinned old.
# (Manually downgrade ui_tester in ~/.locksmith/plugins/index.json to point at an older SHA.)

LOCKSMITH_ENVIRONMENT=development poetry run python -m locksmith &
LOCKSMITH_PID=$!
sleep 6
devctl click '{"target": "Plugins"}'
devctl click '{"target": "Check now"}'
sleep 3
devctl tree '{"clickable_only": true}' | grep -i "upgrade\|update"  # expect to see "Upgrade" button
devctl screenshot '{"path": "/tmp/plugins-update-available.png"}'

devctl click '{"target": "Upgrade"}'
sleep 5
devctl tree | grep -i "restart"   # expect to see the banner's "Restart now"
devctl screenshot '{"path": "/tmp/plugins-after-upgrade.png"}'

kill $LOCKSMITH_PID
```

Expected outputs:
- Before upgrade: row shows `update available` + Upgrade button visible in tree.
- After upgrade click: banner becomes visible, row state changes.
- `~/.locksmith/plugins/index.json` shows the new commit; `<plugin_id>.previous/` exists.

- [ ] **Step 4: Merge `feat/plugin-upgrade` → `dev`**

```bash
git checkout dev
git merge --no-ff feat/plugin-upgrade -m "Merge branch 'feat/plugin-upgrade' into dev (plugin upgrade flow)"
```

Done. No push to `origin/dev` and no merge to `main` — those happen on the user's schedule.

---

## Notes for the implementer

- **Existing patterns to follow**: `test_plugins_installer.py` shows the `monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)` isolation pattern. Reuse it in every test fixture so tests never touch the real `~/.locksmith/`.
- **No `DoDoer`**: spec was originally written assuming a wallet-lifetime `Doist`, which Locksmith doesn't have (Doers run inside the per-vault `QtTask`). The checker is a plain class driven by a `QTimer` in `LocksmithWindow`. See spec section 7 for the reasoning.
- **`devctl`**: the CLI ships from `locksmith-ui-tester`. If it's not on PATH, invoke `python -m locksmith_ui_tester.cli <op>` instead.
- **Banner is global** (in `LocksmithWindow`, not on the Plugins page). The existing `_restart_banner` on `PluginsContent` is for *uninstalls* and is left alone in v1. Unifying them is a follow-up.
- **`subprocess` is blocking** inside `_ls_remote`. Each call blocks the Qt main thread for up to 10s (timeout). In practice ~1s per plugin. Acceptable for v1 — if it becomes a UX problem, move into a `QThreadPool` worker.
