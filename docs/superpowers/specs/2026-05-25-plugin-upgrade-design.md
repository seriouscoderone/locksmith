# Plugin Upgrade Flow — Design

**Date:** 2026-05-25
**Status:** Approved for implementation
**Branch:** `feat/plugin-upgrade` (off `dev`, will merge directly back to `dev`)

## 1. Goal

When an installed plugin has new code available on its GitHub remote, Locksmith should detect this in the background, surface an "Upgrade" button on the Plugins page, fetch the new code on demand into a sidecar clone with atomic swap, and prompt the user to restart so the new code takes effect. No re-trust prompt in v1 (forward-looking note: future versions will gate trust on a KERI-AID-based author identity + reputation algorithm).

## 2. Scope

**In scope:**
- Background poll for github-source plugins, cached to disk
- "Update available" indicator on each plugin row
- "Upgrade" action that re-clones into a sidecar and atomic-swaps
- Restart banner (global, persistent for the session) with manual Restart button
- Cache invalidation, error handling, and rollback on failed upgrade

**Out of scope (v1):**
- Re-trust prompt on manifest changes (deferred until KERI-AID author trust exists)
- Pinning to tags / versions instead of branch HEAD
- Automatic restart
- Local-path-source plugins (no remote → no Upgrade button; user must uninstall + reinstall)
- Telemetry or metrics
- One-click rollback UI (the `<plugin_id>.previous/` breadcrumb is a recovery aid, not a feature)

## 3. Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Detection signal | Commit SHA drift on remote ref | Catches all changes including untagged fixes. Matches real workflow today (fixes pushed to `main` without version bumps). |
| Check cadence | Background poll, default every 6h, cached to disk | UI never hits the network. Predictable, respectful of GitHub rate limits, survives long-running wallet sessions. |
| Restart UX | Banner + manual Restart button | User keeps working in current session uninterrupted; explicit control over when new code activates. |
| Re-trust gate | None in v1 | Solo-author ecosystem currently; future KERI-AID author trust supersedes this anyway. |
| Local-path plugins | No upgrade affordance; uninstall + reinstall | Dev workflow; nothing to poll. |
| Process model | Plain Python class + Qt `QTimer` at wallet scope | Locksmith has no wallet-lifetime `Doist` today (Doers run inside the per-vault `QtTask`). The checker outlives vault opens/closes, so a Qt-driven timer is the right fit. |
| Remote check command | `git ls-remote <url> <ref>` via subprocess | No GitHub API rate limit. Installer already depends on git CLI. |
| Failed-upgrade recovery | Sidecar staging dir + atomic swap; keep one `<plugin_id>.previous/` | Cheap rollback breadcrumb without a UI flow. |

## 4. Architecture

Four pieces in `src/locksmith/plugins/` (three modified, one new):

```
plugins/
  updates.py        ← NEW: PluginUpdateChecker (plain class), check_all_plugins, cache I/O
  installer.py      ← extended: add upgrade(plugin_id) method
  storage.py        ← extended: update_cache_path(), read/write_update_cache(),
                                plugin_staging_dir(), plugin_previous_dir()
  manager.py        ← unchanged (still reads index.json, loads clones)
```

UI in `src/locksmith/ui/plugins/`:

```
plugins/
  page.py           ← per-plugin row gains Upgrade button + state indicator,
                     page-header "Check now" button
  upgrade_banner.py ← NEW: top-level "Upgrade staged — restart to activate"
```

Window integration:

```
ui/window.py        ← inject UpgradeBanner above the page stack
core/apping.py      ← instantiate PluginUpdateChecker on LocksmithApplication
ui/window.py        ← own the QTimer that drives periodic check_now()
```

### Data flow

```
        ┌──── git ls-remote (subprocess, 10s timeout)
        │
PluginUpdateChecker ──── writes ────► ~/.locksmith/plugins/update-cache.json
        │                                       │
        │                                       │ reads (no network)
        ▼                                       ▼
   QTimer.timeout                       PluginsPage rows
                                                 │
                                                 ▼
                                           Upgrade button
                                                 │
                                                 │ user click
                                                 ▼
                                  Installer.upgrade(plugin_id)
                                       ├─ clone into staging
                                       ├─ validate manifest
                                       ├─ rename old → .previous
                                       ├─ rename staging → final
                                       └─ update index.json
                                                 │
                                                 ▼
                                       UpgradeBanner shows
                                                 │
                                                 │ user click "Restart now"
                                                 ▼
                                       Popen(new process); quit()
```

### Process-state invariant

The currently running Python process keeps the **old** plugin's modules in `sys.modules` for the rest of the session. We do not attempt to unload — Python module reloading is unreliable when state hides in C extensions, Qt slot connections, or thread-local storage. Restart is the only way to pick up the new code. The banner enforces this contract.

## 5. Manifest + Index Schema

**Plugin manifest (`locksmith-plugin.toml`):** unchanged.

**Index (`~/.locksmith/plugins/index.json`):** existing fields plus one new optional field per record:

```json
{
  "plugin_id": "ui_tester",
  "source": { "type": "github", "user_repo": "...", "ref": null },
  "commit": "61f85eb...",                          // updated on upgrade
  "installed_at": "2026-05-25T...",                // updated on upgrade
  "manifest_snapshot": { ... },                    // re-parsed on upgrade
  "previous_commit": "e029c17e..."                 // NEW: SHA prior to most recent upgrade
}
```

`previous_commit` is a breadcrumb — populated on upgrade, never read by Locksmith code in v1. Exposed for manual recovery and as a hook for future rollback UI.

## 6. Update Cache

Path: `~/.locksmith/plugins/update-cache.json`.

```json
{
  "format": 1,
  "interval_hours": 6,
  "plugins": {
    "ui_tester": {
      "ref": "main",
      "installed_commit": "e029c17e5956fa9d98f377f28eaf29772628ec4b",
      "latest_commit":    "61f85eb...",
      "latest_checked_at":"2026-05-25T18:42:00Z",
      "update_available": true,
      "last_error": null
    }
  }
}
```

**Atomic write** via temp-file + `os.rename` — same pattern `storage.py` already uses for `index.json`.

**Why separate from index.json:** cache is volatile (rewritten every 6h). Index is the install trust record (must not corrupt). Separate files mean a corrupt cache file only means "stale update info," not "lost install records."

**`interval_hours` lives in the cache** rather than a separate config file. If the user wants to change it, they edit this file. Promotable to real config when there's a preferences UI.

**Storage functions** (mirror existing `storage.py` helpers):

```python
def update_cache_path() -> Path
def read_update_cache() -> dict[str, Any]
def write_update_cache(payload: dict[str, Any]) -> None    # atomic
def plugin_staging_dir(plugin_id: str) -> Path             # <root>/<id>.staging
def plugin_previous_dir(plugin_id: str) -> Path            # <root>/<id>.previous
```

## 7. `PluginUpdateChecker`

File: `src/locksmith/plugins/updates.py`.

```python
class PluginUpdateChecker:
    def __init__(self, manager: PluginManager, *, interval_hours: int = 6): ...
    def check_now(self) -> None                       # forces an immediate check_all_plugins()
    def check_all_plugins(self) -> None               # one full pass, writes cache, notifies
    def cache(self) -> dict[str, Any]
    def should_check_now(self) -> bool                # cache stale OR missing
    def subscribe(self, callback: Callable[[], None]) -> Callable[[], None]
        # Returns an unsubscribe function. Callbacks are fired on whichever
        # thread called check_all_plugins; since that's the Qt main thread
        # (driven by QTimer), no extra marshalling is needed.
```

The checker is a plain Python class — no `DoDoer`, no `QObject`. A Qt `QTimer` in `LocksmithWindow` (or wherever the wallet-lifetime UI is constructed) fires every `interval_hours` and calls `check_now()`. Subscribers receive callbacks synchronously on the Qt main thread.

### Poll scheduling

`LocksmithWindow` constructs a `QTimer` at startup:

```python
self.plugin_update_timer = QTimer(self)
self.plugin_update_timer.setInterval(interval_hours * 3600 * 1000)  # ms
self.plugin_update_timer.timeout.connect(app.plugin_update_checker.check_now)
self.plugin_update_timer.start()
# Kick off one immediate check at wallet open if the cache is stale.
QTimer.singleShot(0, lambda: (
    app.plugin_update_checker.check_now()
    if app.plugin_update_checker.should_check_now() else None
))
```

`should_check_now()` returns `True` if `cache.checked_at` is missing or older than `interval_hours`. Lets the timer skip its first tick when the cache is fresh from a recent launch.

### `check_all_plugins()` per plugin

1. Skip if `source.type != "github"`
2. Compute URL: `https://github.com/{source.user_repo}.git`
3. `subprocess.run(["git", "ls-remote", url, ref_or_HEAD], capture_output=True, timeout=10)`
4. Parse the leading SHA from stdout (first whitespace-delimited token of first line)
5. Compare to `record.commit`
6. Update cache entry:
   - On success: `latest_commit`, `latest_checked_at`, `update_available`, `last_error=None`
7. Notify subscribers (UI re-reads the cache)
8. Emit `logger.info("plugin.update.checked plugin_id=%s ...")`

### Error handling

| Error | Cache effect | UI effect |
|---|---|---|
| `git ls-remote` exit ≠ 0 | `last_error="ls-remote: <stderr>"`; preserve `update_available` and `latest_commit` | Row tooltip shows error; "couldn't check ⚠" |
| Timeout (10s) | Same | Same |
| `git` not on PATH | Same, but error includes "install git" | Same (practically impossible — installer requires git) |
| Unexpected exception | Logged via `logger.exception`; swallowed at per-plugin level | One bad plugin can't kill the checker for others |

### `check_now()`

Forces an immediate `check_all_plugins()` regardless of `interval_hours`. Used by the "Check now" UI button and by tests.

### Mounting

In `core/apping.py`'s `__init__` (after `self.plugin_manager`):

```python
from locksmith.plugins.updates import PluginUpdateChecker
self.plugin_update_checker = PluginUpdateChecker(manager=self.plugin_manager)
```

The `QTimer` lives in `LocksmithWindow` (see "Poll scheduling" above) because timers need a `QObject` parent in Qt's event loop. The checker itself is stateless wrt Qt.

### Subprocess blocking note

`subprocess.run` blocks the Qt main thread for the duration of `ls-remote` (typically <1s, capped at 10s). The check runs once every `interval_hours` and most calls are sub-second, so the UI freeze is imperceptible. If it becomes a problem (many plugins or slow networks), move the call into a `QThreadPool.start(...)` worker in a follow-up.

## 8. Upgrade Pipeline

New method on existing `Installer` class:

```python
def upgrade(self, plugin_id: str) -> dict[str, Any]:
    """Re-fetch latest commit for a github-source plugin.
    Returns the new index record. Raises on failure; previous clone untouched."""
```

### Execution sequence

1. **Read record** from `index.json`. Raise if `source.type != "github"`.
2. **Clone into staging:**
   ```python
   staging = storage.plugin_staging_dir(plugin_id)
   if staging.exists():
       shutil.rmtree(staging)
   self._fetch_into(source, staging)    # reuses existing private helper
   ```
3. **Validate manifest:**
   ```python
   manifest = self._parse_manifest_in(staging)  # reuses existing helper
   if manifest.plugin_id != plugin_id:
       shutil.rmtree(staging)
       raise InstallerError(f"new manifest declares different plugin_id: {manifest.plugin_id}")
   ```
4. **Get new SHA:**
   ```python
   new_sha = subprocess.check_output(
       ["git", "-C", str(staging), "rev-parse", "HEAD"]
   ).decode().strip()
   ```
5. **Atomic swap:**
   ```python
   final    = storage.plugin_clone_dir(plugin_id)
   previous = storage.plugin_previous_dir(plugin_id)

   if previous.exists():
       shutil.rmtree(previous)
   old_sha = record["commit"]
   os.rename(final, previous)
   try:
       os.rename(staging, final)
   except OSError:
       os.rename(previous, final)  # best-effort rollback
       raise
   ```
6. **Update `index.json`:** new `commit`, `installed_at`, `manifest_snapshot`, `previous_commit=old_sha`. Atomic via existing `storage.write_index`.
7. **Clear cache `update_available` for this plugin** so banner/row flips immediately:
   ```python
   cache = storage.read_update_cache()
   if plugin_id in cache.get("plugins", {}):
       entry = cache["plugins"][plugin_id]
       entry["installed_commit"] = new_sha
       entry["latest_commit"]    = new_sha
       entry["update_available"] = False
       entry["last_error"]       = None
   storage.write_update_cache(cache)
   ```
8. **Return** the new record. Caller (UI) sets the banner flag.

### Failure modes

| Failure | Recovery |
|---|---|
| Clone into staging fails | Staging dir removed; final untouched; raise |
| Manifest parse fails | Staging dir removed; final untouched; raise with parse error |
| `plugin_id` mismatch | Staging dir removed; final untouched; raise with both ids |
| Rename old→previous fails | Final untouched; raise (rare — same-FS rename) |
| Rename staging→final fails after previous-move | Best-effort `os.rename(previous, final)` rollback; raise. If even the rollback rename fails, surface fatal error with both absolute paths so user can recover manually. Not coded for, but documented. |
| Index write fails after successful swap | Index is source of truth; attempt directory rollback. Surface error. |

### Cleanup policy

`<plugin_id>.previous/` is overwritten by the *next* successful upgrade (only one generation kept). Manual rollback is not a v1 feature; the breadcrumb exists for forensic recovery.

## 9. UI Surface

### (a) Per-plugin row state on Plugins page

State is computed from the cache entry + the in-session "upgrade staged" flag:

```
[ Installed ]                                         # update_available == false
[ Installed · update available ]    [ Upgrade ]       # update_available == true
[ Installed · checking… ]                             # transient during check_now()
[ Installed · couldn't check ⚠ ]                      # last_error set; tooltip shows error
[ Installed · upgrade staged · restart ]              # post-upgrade, before restart
```

Local-path plugins (no remote) always show `[ Installed ]` — no Upgrade button, no check indicator.

### (b) Page-level "Check now" button

In the Plugins page header. Triggers `PluginUpdateChecker.check_now()`. While the check is running:
- Button is disabled
- All rows show `checking…`
- On completion: button re-enables, rows render new state

### (c) Restart banner

New widget `upgrade_banner.py` shown above the page stack on every page (not just Plugins):

```
┌─────────────────────────────────────────────────────────────┐
│  ⟳  Plugin update staged. Restart Locksmith to activate.    │
│                                            [ Restart now ]  │
└─────────────────────────────────────────────────────────────┘
```

**State source:** in-memory boolean on `LocksmithWindow` (or `PluginManager`). Set when `installer.upgrade()` returns success. Not persisted — if the user closes the wallet, the next launch loads new code and the banner doesn't need to exist anymore.

**Restart action:**
```python
def restart_now(self):
    subprocess.Popen([sys.executable, *sys.argv])  # start replacement first
    QApplication.quit()                            # then quit
```
Relaunched process opens to the standard lock screen — no vault unlock state restoration. Matches "restart is restart."

### Reactive rendering

`PluginUpdateChecker` calls registered callbacks after each successful `check_all_plugins()` pass. `PluginsPage` subscribes on construction and unsubscribes on teardown. Since the check is invoked from the Qt main thread (via `QTimer` or button click), the callback is already on the right thread — no marshalling needed:

```python
class PluginsPage(QWidget):
    def __init__(self, ...):
        self._unsubscribe = self.app.plugin_update_checker.subscribe(self._refresh_rows)

    def _refresh_rows(self):
        cache = self.app.plugin_update_checker.cache()
        for row in self._rows:
            row.set_update_state(cache["plugins"].get(row.plugin_id, {}))

    def closeEvent(self, ev):
        self._unsubscribe()
        super().closeEvent(ev)
```

### Logging

Every check, upgrade, and swap emits a structured log line (`plugin.update.checked`, `plugin.update.upgraded`, `plugin.update.swap_failed`, `plugin.update.banner_shown`). Necessary because UI tests can't see the banner directly — they assert on log lines + `devctl tree` output.

## 10. Testing

### (a) Unit tests for `updates.py` (no network, no subprocess)

Seam: a private `_ls_remote(url, ref) -> str` helper that's the only thing tests stub.

```python
def test_poll_writes_cache_with_update_available(monkeypatch): ...
def test_poll_records_last_error_on_subprocess_failure(monkeypatch): ...
def test_poll_skips_local_path_plugins(monkeypatch): ...
def test_poll_skips_when_interval_not_elapsed(monkeypatch): ...
def test_check_now_forces_immediate_check(monkeypatch): ...
def test_subscribers_notified_after_poll(monkeypatch): ...
```

Tests call `check_all_plugins()` and `should_check_now()` directly — no generator-driving needed since the class is plain Python.

### (b) Unit tests for `installer.upgrade()` (uses local bare repo, no network)

Test fixture:

```python
@pytest.fixture
def fake_remote_repo(tmp_path):
    """A bare git repo on disk addressable via file:// URL.
    The same `git clone --depth 1` code path works."""
    repo = tmp_path / "remote.git"
    subprocess.check_call(["git", "init", "--bare", str(repo)])
    return repo
```

Tests:

```python
def test_upgrade_swaps_clone_and_updates_index(tmp_path, fake_remote_repo): ...
def test_upgrade_creates_previous_dir_pointing_at_old_sha(...): ...
def test_upgrade_failure_leaves_clone_dir_intact(monkeypatch): ...
def test_upgrade_rejects_changed_plugin_id(...): ...
def test_upgrade_rejects_local_path_source(...): ...
def test_upgrade_clears_cache_update_available_flag(...): ...
def test_upgrade_overwrites_existing_previous_dir(...): ...
```

### (c) Integration test using locksmith-ui-tester harness

End-to-end (uses the `ui_tester` plugin's `devctl` socket):

1. Install `ui_tester` against a fake-github local fixture at commit A
2. Bump fixture to commit B
3. Trigger `PluginUpdateChecker.check_now()` via a test-only hook or just by setting the cache mtime
4. Use `devctl click '{"target":"Plugins"}'` to navigate to Plugins page
5. Use `devctl tree` to assert the row shows "update available"
6. Use `devctl click '{"target":"Upgrade"}'` (with row-scoped selector)
7. Use `devctl tree` to assert the banner widget is visible
8. Assert `index.json` reflects commit B

### Deliberately not tested in CI

- Real `git ls-remote https://github.com/...` — covered by manual smoke before merging to `dev`. CI can't reliably hit GitHub without auth.
- Actual `subprocess.Popen([sys.executable, *sys.argv])` restart — mocked in unit tests; manual smoke verifies the real path.

## 11. Forward-Looking Notes

### KERI-AID author trust (future)

The "re-trust on capability change" question was deferred. The intended future shape:

- Plugin manifest declares the author as a KERI AID (not just a string).
- Locksmith maintains a per-vault trust list of author AIDs.
- Reputation algorithm (defined in a separate future spec) gates trust at install + upgrade time.
- This subsumes the "did capabilities change?" question — trust is rooted in the author AID, not per-capability diffs.

Not in v1 scope. Captured here so the v1 "never re-prompt" decision doesn't get re-litigated without context.

### Tag/version pinning (future)

`source.ref` already accepts a value — the upgrade flow respects it (`git ls-remote <url> <ref>`). UI for pinning is not built in v1 (default branch HEAD is what everyone wants right now). When/if we add pinning, the manifest schema is already ready.

### Real config UI for `interval_hours` (future)

For now, edit `update-cache.json` directly. When a wallet-wide preferences UI exists, this gets promoted.

## 12. Open Questions

None at this time. All forking decisions are resolved above.

## 13. Branch + Merge Plan

- Branch: `feat/plugin-upgrade` off `dev`
- Worktree: `.worktrees/plugin-upgrade/` (created at implementation time via `superpowers:using-git-worktrees`)
- Merge: direct merge back to `dev` when done; no PR; no immediate merge to `main`.
