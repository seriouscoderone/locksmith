# Phase 5: Sparkle/WinSparkle Integration + In-App Update UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the end-to-end user-visible update experience defined in spec §8–§9: silent install-on-quit for minor/patch, native "What's New" modal for major releases, critical-update banner, KERI verification gating every install, Settings → Updates page with verification log, and first-launch consent.

**Architecture:** A thin cross-platform Python `controller` instantiates a platform-specific bridge (PyObjC `SPUUpdaterController` delegate on macOS, ctypes WinSparkle binding on Windows). The bridge is the only platform-specific code; everything else is pure Python (`scheduler`, `decision`, `log`, `consent`) or PySide6 widgets. The Phase 4 verifier (`locksmith.update.verify.verify_artifact`) is called from the bridge before any install proceeds. No "Install anyway" affordance exists anywhere in the code.

**Tech Stack:** PySide6 + qasync (existing), Sparkle 2.x framework (embedded), WinSparkle 0.8+ DLL (embedded), PyObjC (macOS-only), ctypes (Windows-only), QSettings for persisted prefs, pytest-qt + pytest-asyncio for tests.

---

## File Structure

**New files (Python):**
- `src/locksmith/update/__init__.py` — re-exports public API
- `src/locksmith/update/scheduler.py` — periodic check timer (30s initial, 4h cadence)
- `src/locksmith/update/decision.py` — pure-function decision tree (NO_UPDATE / SILENT_INSTALL / SHOW_WHATS_NEW / SHOW_CRITICAL_BANNER)
- `src/locksmith/update/controller.py` — top-level controller; wires scheduler + decision + bridge + UI signals
- `src/locksmith/update/sparkle_bridge.py` — PyObjC delegate (macOS-only import)
- `src/locksmith/update/sparkle_init.py` — `SPUStandardUpdaterController` setup
- `src/locksmith/update/winsparkle_bridge.py` — ctypes bindings (Windows-only)
- `src/locksmith/update/winsparkle_init.py` — WinSparkle setup
- `src/locksmith/update/prefs.py` — QSettings wrapper for update prefs
- `src/locksmith/update/deferral.py` — sliding 24h / 7-day cap logic

**New files (UI):**
- `src/locksmith/ui/settings/__init__.py`
- `src/locksmith/ui/settings/updates.py` — Settings → Updates tab
- `src/locksmith/ui/dialogs/__init__.py`
- `src/locksmith/ui/dialogs/whats_new.py` — major-version modal
- `src/locksmith/ui/dialogs/verification_log.py` — verification log page + detail view
- `src/locksmith/ui/dialogs/update_consent.py` — first-launch consent
- `src/locksmith/ui/banners/__init__.py`
- `src/locksmith/ui/banners/critical_update.py` — orange critical banner
- `src/locksmith/ui/toasts/__init__.py`
- `src/locksmith/ui/toasts/update_failed.py` — single-instance verification-failed toast

**Modified files:**
- `packaging/Locksmith.macos.spec` (extends Phase 2): embed Sparkle.framework, Info.plist additions, sign nested binaries
- `packaging/Locksmith.windows.spec` (extends Phase 3): bundle WinSparkle.dll
- `scripts/signLibs.sh` (extends): codesign Sparkle.framework helper binaries
- `src/locksmith/main.py`: wire update controller into bootstrap
- `src/locksmith/core/apping.py`: hold controller reference; expose to UI
- `src/locksmith/ui/window.py`: mount critical-update banner above page stack; mount update-failed toast; "Check for updates…" menu entry on Help menu
- `src/locksmith/ui/vault/settings/page.py`: surface "Updates" section linking to dedicated Updates page (or include `UpdatesSettingsWidget` as a section)
- `pyproject.toml`: add `pyobjc-framework-Cocoa` and `pyobjc-framework-Sparkle` (macOS-only optional deps); ensure `pytest-qt` is in dev deps

**New tests:**
- `tests/unit/update/__init__.py`
- `tests/unit/update/test_decision.py`
- `tests/unit/update/test_scheduler.py`
- `tests/unit/update/test_deferral.py`
- `tests/unit/update/test_prefs.py`
- `tests/ui/__init__.py`
- `tests/ui/test_updates_settings.py`
- `tests/ui/test_whats_new_dialog.py`
- `tests/ui/test_verification_log.py`
- `tests/ui/test_update_consent.py`
- `tests/ui/test_critical_banner.py`
- `tests/ui/test_update_failed_toast.py`
- `tests/integration/test_full_update_cycle_macos.py`
- `tests/integration/test_full_update_cycle_windows.py`
- `tests/integration/test_verification_failure_aborts_install.py`

---

## Task 1: Bootstrap the `locksmith.update` package skeleton

**Files:**
- Create: `src/locksmith/update/__init__.py`
- Create: `tests/unit/update/__init__.py`
- Test: `tests/unit/update/test_package_imports.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/update/test_package_imports.py
def test_update_package_exports_public_api():
    from locksmith.update import (
        UpdateController,
        UpdateScheduler,
        UpdateDecision,
        UpdatePrefs,
        Deferral,
    )
    assert UpdateController is not None
    assert UpdateScheduler is not None
    assert UpdateDecision is not None
    assert UpdatePrefs is not None
    assert Deferral is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/update/test_package_imports.py -v`
Expected: FAIL — `ImportError: cannot import name 'UpdateController' from 'locksmith.update'`

- [ ] **Step 3: Create minimal package**

```python
# src/locksmith/update/__init__.py
"""locksmith.update — update orchestration + UI bridge.

Public API:
    UpdateController     — top-level entry, instantiated from main.py
    UpdateScheduler      — periodic check timer
    UpdateDecision       — pure function over appcast Release + current version
    UpdatePrefs          — QSettings wrapper for user prefs
    Deferral             — sliding 24h / 7-day cap logic
"""
from locksmith.update.controller import UpdateController
from locksmith.update.scheduler import UpdateScheduler
from locksmith.update.decision import UpdateDecision
from locksmith.update.prefs import UpdatePrefs
from locksmith.update.deferral import Deferral

__all__ = [
    "UpdateController",
    "UpdateScheduler",
    "UpdateDecision",
    "UpdatePrefs",
    "Deferral",
]
```

Create empty stub files so imports resolve (real impls land in later tasks):

```python
# src/locksmith/update/controller.py
class UpdateController:
    pass

# src/locksmith/update/scheduler.py
class UpdateScheduler:
    pass

# src/locksmith/update/decision.py
class UpdateDecision:
    pass

# src/locksmith/update/prefs.py
class UpdatePrefs:
    pass

# src/locksmith/update/deferral.py
class Deferral:
    pass
```

```python
# tests/unit/update/__init__.py
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/update/test_package_imports.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/update tests/unit/update
git commit -m "feat(update): bootstrap locksmith.update package skeleton"
```

---

## Task 2: `UpdateDecision` — decision tree (spec §8.2)

**Files:**
- Modify: `src/locksmith/update/decision.py`
- Test: `tests/unit/update/test_decision.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/update/test_decision.py
import pytest
from dataclasses import dataclass

from locksmith.update.decision import (
    UpdateDecision, UpdateAction, Release,
)


def _release(version="1.2.3", is_major=False, is_critical=False, **kw):
    return Release(
        version=version,
        platform=kw.get("platform", "macos"),
        artifact_url=kw.get("artifact_url", "https://x/y"),
        artifact_sha256=kw.get("artifact_sha256", "abc"),
        artifact_size=kw.get("artifact_size", 1),
        anchor_url=kw.get("anchor_url", "https://x/y.cesr"),
        anchor_said=kw.get("anchor_said", "ESAID"),
        is_major=is_major,
        is_critical=is_critical,
        release_notes_url=kw.get("release_notes_url", "https://x/notes"),
        released_at=kw.get("released_at", "2026-05-28T00:00:00Z"),
        minimum_system_version=kw.get("minimum_system_version", "13.0"),
    )


def test_no_update_when_versions_equal():
    decision = UpdateDecision.evaluate(
        current_version="1.2.3",
        release=_release(version="1.2.3"),
    )
    assert decision.action == UpdateAction.NO_UPDATE


def test_no_update_when_current_is_newer():
    decision = UpdateDecision.evaluate(
        current_version="1.3.0",
        release=_release(version="1.2.3"),
    )
    assert decision.action == UpdateAction.NO_UPDATE


def test_critical_release_shows_banner_even_when_minor():
    decision = UpdateDecision.evaluate(
        current_version="1.2.2",
        release=_release(version="1.2.3", is_critical=True),
    )
    assert decision.action == UpdateAction.SHOW_CRITICAL_BANNER


def test_major_release_shows_whats_new_modal():
    decision = UpdateDecision.evaluate(
        current_version="1.2.3",
        release=_release(version="2.0.0", is_major=True),
    )
    assert decision.action == UpdateAction.SHOW_WHATS_NEW_MODAL


def test_minor_release_silent_install():
    decision = UpdateDecision.evaluate(
        current_version="1.2.3",
        release=_release(version="1.3.0", is_major=False),
    )
    assert decision.action == UpdateAction.SILENT_INSTALL


def test_patch_release_silent_install():
    decision = UpdateDecision.evaluate(
        current_version="1.2.3",
        release=_release(version="1.2.4"),
    )
    assert decision.action == UpdateAction.SILENT_INSTALL


def test_critical_overrides_major():
    decision = UpdateDecision.evaluate(
        current_version="1.2.3",
        release=_release(version="2.0.0", is_major=True, is_critical=True),
    )
    assert decision.action == UpdateAction.SHOW_CRITICAL_BANNER


def test_decision_carries_release():
    rel = _release(version="1.3.0")
    decision = UpdateDecision.evaluate(current_version="1.2.0", release=rel)
    assert decision.release is rel
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/update/test_decision.py -v`
Expected: FAIL — `ImportError: cannot import name 'UpdateAction'`

- [ ] **Step 3: Implement decision module**

```python
# src/locksmith/update/decision.py
"""Pure-function decision tree for update UX (spec §8.2)."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from keri import help

logger = help.ogler.getLogger(__name__)


class UpdateAction(Enum):
    NO_UPDATE = "no_update"
    SILENT_INSTALL = "silent_install"
    SHOW_WHATS_NEW_MODAL = "show_whats_new_modal"
    SHOW_CRITICAL_BANNER = "show_critical_banner"


@dataclass(frozen=True)
class Release:
    version: str
    platform: str
    artifact_url: str
    artifact_sha256: str
    artifact_size: int
    anchor_url: str
    anchor_said: str
    is_major: bool
    is_critical: bool
    release_notes_url: str
    released_at: str
    minimum_system_version: str


@dataclass(frozen=True)
class UpdateDecision:
    action: UpdateAction
    release: Release | None = None

    @classmethod
    def evaluate(cls, *, current_version: str, release: Release) -> "UpdateDecision":
        """Spec §8.2 decision tree.

        Critical > Major > Minor/Patch.
        """
        if _compare(release.version, current_version) <= 0:
            logger.info(
                "[update] decision=no_update current=%s candidate=%s",
                current_version, release.version,
            )
            return cls(action=UpdateAction.NO_UPDATE, release=None)

        if release.is_critical:
            logger.info("[update] decision=show_critical_banner candidate=%s", release.version)
            return cls(action=UpdateAction.SHOW_CRITICAL_BANNER, release=release)

        if release.is_major:
            logger.info("[update] decision=show_whats_new candidate=%s", release.version)
            return cls(action=UpdateAction.SHOW_WHATS_NEW_MODAL, release=release)

        logger.info("[update] decision=silent_install candidate=%s", release.version)
        return cls(action=UpdateAction.SILENT_INSTALL, release=release)


def _compare(a: str, b: str) -> int:
    """Return -1/0/1 like cmp() for two semver strings (X.Y.Z, no pre-release)."""
    pa = tuple(int(x) for x in a.split("."))
    pb = tuple(int(x) for x in b.split("."))
    if pa < pb:
        return -1
    if pa > pb:
        return 1
    return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/update/test_decision.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/update/decision.py tests/unit/update/test_decision.py
git commit -m "feat(update): decision tree for NO_UPDATE/SILENT/WHATS_NEW/CRITICAL"
```

---

## Task 3: `UpdatePrefs` — QSettings-backed user preferences

**Files:**
- Modify: `src/locksmith/update/prefs.py`
- Test: `tests/unit/update/test_prefs.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/update/test_prefs.py
import pytest
from PySide6.QtCore import QCoreApplication, QSettings


@pytest.fixture(autouse=True)
def qsettings_in_memory(tmp_path, monkeypatch):
    """Force QSettings to a temp ini so tests don't touch real user prefs."""
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(
        QSettings.IniFormat,
        QSettings.UserScope,
        str(tmp_path),
    )
    QCoreApplication.setOrganizationName("LocksmithTest")
    QCoreApplication.setApplicationName("LocksmithTest")
    yield


def test_check_automatically_defaults_to_true():
    from locksmith.update.prefs import UpdatePrefs
    prefs = UpdatePrefs()
    assert prefs.check_automatically is True


def test_check_automatically_persists():
    from locksmith.update.prefs import UpdatePrefs
    p1 = UpdatePrefs()
    p1.check_automatically = False
    p2 = UpdatePrefs()
    assert p2.check_automatically is False


def test_consent_seen_defaults_false():
    from locksmith.update.prefs import UpdatePrefs
    prefs = UpdatePrefs()
    assert prefs.consent_seen is False


def test_consent_seen_persists():
    from locksmith.update.prefs import UpdatePrefs
    p1 = UpdatePrefs()
    p1.consent_seen = True
    p2 = UpdatePrefs()
    assert p2.consent_seen is True


def test_last_deferred_timestamp_defaults_none():
    from locksmith.update.prefs import UpdatePrefs
    prefs = UpdatePrefs()
    assert prefs.last_deferred_at is None


def test_first_deferred_timestamp_persists_iso_string():
    from locksmith.update.prefs import UpdatePrefs
    p1 = UpdatePrefs()
    p1.first_deferred_at = "2026-05-28T12:00:00+00:00"
    p2 = UpdatePrefs()
    assert p2.first_deferred_at == "2026-05-28T12:00:00+00:00"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/update/test_prefs.py -v`
Expected: FAIL — `AttributeError: 'UpdatePrefs' object has no attribute 'check_automatically'`

- [ ] **Step 3: Implement**

```python
# src/locksmith/update/prefs.py
"""QSettings-backed user preferences for the update system.

Keys live under group "Updates/" so they're co-located with other future
settings groups.
"""
from __future__ import annotations

from PySide6.QtCore import QSettings


_GROUP = "Updates"


class UpdatePrefs:
    """Thin typed wrapper over QSettings for update-related prefs."""

    def __init__(self, settings: QSettings | None = None):
        self._s = settings or QSettings()

    # --- check_automatically (default True) ---
    @property
    def check_automatically(self) -> bool:
        v = self._s.value(f"{_GROUP}/check_automatically", True, type=bool)
        return bool(v)

    @check_automatically.setter
    def check_automatically(self, value: bool) -> None:
        self._s.setValue(f"{_GROUP}/check_automatically", bool(value))
        self._s.sync()

    # --- consent_seen (default False; flipped after one-time dialog) ---
    @property
    def consent_seen(self) -> bool:
        v = self._s.value(f"{_GROUP}/consent_seen", False, type=bool)
        return bool(v)

    @consent_seen.setter
    def consent_seen(self, value: bool) -> None:
        self._s.setValue(f"{_GROUP}/consent_seen", bool(value))
        self._s.sync()

    # --- first_deferred_at (ISO-8601 UTC of when a deferral chain began) ---
    @property
    def first_deferred_at(self) -> str | None:
        v = self._s.value(f"{_GROUP}/first_deferred_at", None)
        return str(v) if v else None

    @first_deferred_at.setter
    def first_deferred_at(self, value: str | None) -> None:
        if value is None:
            self._s.remove(f"{_GROUP}/first_deferred_at")
        else:
            self._s.setValue(f"{_GROUP}/first_deferred_at", value)
        self._s.sync()

    # --- last_deferred_at (most recent "Remind Me Tomorrow" click) ---
    @property
    def last_deferred_at(self) -> str | None:
        v = self._s.value(f"{_GROUP}/last_deferred_at", None)
        return str(v) if v else None

    @last_deferred_at.setter
    def last_deferred_at(self, value: str | None) -> None:
        if value is None:
            self._s.remove(f"{_GROUP}/last_deferred_at")
        else:
            self._s.setValue(f"{_GROUP}/last_deferred_at", value)
        self._s.sync()

    # --- deferred_version (which version the deferral chain applies to) ---
    @property
    def deferred_version(self) -> str | None:
        v = self._s.value(f"{_GROUP}/deferred_version", None)
        return str(v) if v else None

    @deferred_version.setter
    def deferred_version(self, value: str | None) -> None:
        if value is None:
            self._s.remove(f"{_GROUP}/deferred_version")
        else:
            self._s.setValue(f"{_GROUP}/deferred_version", value)
        self._s.sync()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/update/test_prefs.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/update/prefs.py tests/unit/update/test_prefs.py
git commit -m "feat(update): QSettings-backed UpdatePrefs (auto-check, consent, deferral)"
```

---

## Task 4: `Deferral` — sliding 24h / 7-day cap (spec §8.3)

**Files:**
- Modify: `src/locksmith/update/deferral.py`
- Test: `tests/unit/update/test_deferral.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/update/test_deferral.py
from datetime import datetime, timedelta, timezone

import pytest

from locksmith.update.deferral import Deferral


def _ts(dt: datetime) -> str:
    return dt.isoformat()


def test_no_deferral_yet_not_due():
    d = Deferral(
        first_deferred_at=None,
        last_deferred_at=None,
        deferred_version=None,
        candidate_version="1.3.0",
        now=datetime(2026, 5, 28, 12, 0, tzinfo=timezone.utc),
    )
    assert d.is_due_again() is False
    assert d.is_mandatory() is False


def test_due_after_24h_since_last_deferral():
    base = datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc)
    d = Deferral(
        first_deferred_at=_ts(base),
        last_deferred_at=_ts(base),
        deferred_version="1.3.0",
        candidate_version="1.3.0",
        now=base + timedelta(hours=24, minutes=1),
    )
    assert d.is_due_again() is True
    assert d.is_mandatory() is False


def test_not_due_before_24h_since_last_deferral():
    base = datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc)
    d = Deferral(
        first_deferred_at=_ts(base),
        last_deferred_at=_ts(base),
        deferred_version="1.3.0",
        candidate_version="1.3.0",
        now=base + timedelta(hours=23),
    )
    assert d.is_due_again() is False


def test_mandatory_after_7d_since_first_deferral():
    first = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    last = first + timedelta(hours=24)
    d = Deferral(
        first_deferred_at=_ts(first),
        last_deferred_at=_ts(last),
        deferred_version="1.3.0",
        candidate_version="1.3.0",
        now=first + timedelta(days=7, minutes=1),
    )
    assert d.is_mandatory() is True


def test_deferral_resets_on_new_candidate_version():
    first = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    d = Deferral(
        first_deferred_at=_ts(first),
        last_deferred_at=_ts(first),
        deferred_version="1.3.0",
        candidate_version="1.4.0",     # different version came along
        now=first + timedelta(days=8),
    )
    assert d.is_mandatory() is False
    assert d.is_due_again() is True   # this is a fresh prompt for 1.4.0


def test_record_deferral_emits_new_state():
    base = datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc)
    state = Deferral.record_deferral(
        first_deferred_at=None,
        deferred_version=None,
        candidate_version="1.3.0",
        now=base,
    )
    assert state.first_deferred_at == _ts(base)
    assert state.last_deferred_at == _ts(base)
    assert state.deferred_version == "1.3.0"


def test_record_deferral_keeps_first_when_continuing():
    first = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    now = first + timedelta(days=2)
    state = Deferral.record_deferral(
        first_deferred_at=_ts(first),
        deferred_version="1.3.0",
        candidate_version="1.3.0",
        now=now,
    )
    assert state.first_deferred_at == _ts(first)
    assert state.last_deferred_at == _ts(now)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/update/test_deferral.py -v`
Expected: FAIL — `TypeError: Deferral() takes no arguments`

- [ ] **Step 3: Implement**

```python
# src/locksmith/update/deferral.py
"""Sliding-window deferral logic per spec §8.3.

- "Remind Me Tomorrow" reschedules the prompt by 24h
- After 7 days from the first deferral on a given candidate version, the
  prompt becomes mandatory and dismiss-to-defer is disabled.
- A new candidate version (e.g., 1.4.0 supersedes 1.3.0 mid-chain) resets
  the deferral chain.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


_DEFERRAL_WINDOW = timedelta(hours=24)
_MAX_DEFERRAL = timedelta(days=7)


def _parse(ts: str | None) -> datetime | None:
    return datetime.fromisoformat(ts) if ts else None


@dataclass(frozen=True)
class DeferralState:
    first_deferred_at: str
    last_deferred_at: str
    deferred_version: str


@dataclass
class Deferral:
    """Read-only evaluation of "should we re-prompt now?".

    Construct from current QSettings values + candidate version + now;
    call `is_due_again()` / `is_mandatory()`.
    """
    first_deferred_at: str | None
    last_deferred_at: str | None
    deferred_version: str | None
    candidate_version: str
    now: datetime

    def _chain_applies(self) -> bool:
        return (
            self.deferred_version is not None
            and self.deferred_version == self.candidate_version
        )

    def is_due_again(self) -> bool:
        """True if the user should see the prompt again right now."""
        if not self._chain_applies():
            # Fresh candidate — show immediately
            return True
        last = _parse(self.last_deferred_at)
        if last is None:
            return True
        return self.now - last >= _DEFERRAL_WINDOW

    def is_mandatory(self) -> bool:
        """True if 7-day cap reached on this candidate — no more deferring."""
        if not self._chain_applies():
            return False
        first = _parse(self.first_deferred_at)
        if first is None:
            return False
        return self.now - first >= _MAX_DEFERRAL

    @staticmethod
    def record_deferral(
        *,
        first_deferred_at: str | None,
        deferred_version: str | None,
        candidate_version: str,
        now: datetime,
    ) -> DeferralState:
        """Return the new state to persist after user clicks 'Remind Me Tomorrow'."""
        same_chain = (
            deferred_version is not None
            and deferred_version == candidate_version
            and first_deferred_at is not None
        )
        first = first_deferred_at if same_chain else now.isoformat()
        return DeferralState(
            first_deferred_at=first,
            last_deferred_at=now.isoformat(),
            deferred_version=candidate_version,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/update/test_deferral.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/update/deferral.py tests/unit/update/test_deferral.py
git commit -m "feat(update): sliding 24h/7-day deferral logic"
```

---

## Task 5: `UpdateScheduler` — periodic check timer (spec §8.1)

**Files:**
- Modify: `src/locksmith/update/scheduler.py`
- Test: `tests/unit/update/test_scheduler.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/update/test_scheduler.py
import pytest
from PySide6.QtCore import QObject, Signal

from locksmith.update.scheduler import UpdateScheduler, INITIAL_DELAY_MS, CADENCE_MS


def test_initial_delay_is_30_seconds():
    assert INITIAL_DELAY_MS == 30_000


def test_cadence_is_4_hours():
    assert CADENCE_MS == 4 * 60 * 60 * 1000


def test_start_emits_check_requested_after_initial_delay(qtbot):
    scheduler = UpdateScheduler()
    with qtbot.waitSignal(scheduler.check_requested, timeout=2000):
        # Override the initial delay for test speed
        scheduler.start(initial_delay_ms_override=100)


def test_stop_prevents_further_checks(qtbot):
    scheduler = UpdateScheduler()
    scheduler.start(initial_delay_ms_override=50)
    qtbot.wait(150)  # let initial fire
    scheduler.stop()
    received = []
    scheduler.check_requested.connect(lambda: received.append(1))
    qtbot.wait(200)
    assert received == []


def test_trigger_now_emits_check_requested(qtbot):
    scheduler = UpdateScheduler()
    with qtbot.waitSignal(scheduler.check_requested, timeout=500):
        scheduler.trigger_now()


def test_is_enabled_reflects_running_state():
    scheduler = UpdateScheduler()
    assert scheduler.is_enabled is False
    scheduler.start(initial_delay_ms_override=10_000_000)  # huge delay; won't fire
    assert scheduler.is_enabled is True
    scheduler.stop()
    assert scheduler.is_enabled is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/update/test_scheduler.py -v`
Expected: FAIL — `ImportError: cannot import name 'INITIAL_DELAY_MS' from 'locksmith.update.scheduler'`

- [ ] **Step 3: Implement**

```python
# src/locksmith/update/scheduler.py
"""Periodic update-check timer (spec §8.1).

Initial check 30s after launch, then every 4 hours. Emits `check_requested`
on each tick; controller subscribes to it. Manual "Check now" calls
`trigger_now()` directly.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal
from keri import help

logger = help.ogler.getLogger(__name__)

INITIAL_DELAY_MS = 30_000               # 30 seconds
CADENCE_MS = 4 * 60 * 60 * 1000         # 4 hours


class UpdateScheduler(QObject):
    """Emits `check_requested` on the configured cadence."""

    check_requested = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._initial_timer = QTimer(self)
        self._initial_timer.setSingleShot(True)
        self._initial_timer.timeout.connect(self._on_initial_fired)

        self._cadence_timer = QTimer(self)
        self._cadence_timer.timeout.connect(self._on_cadence_fired)

        self._enabled = False

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def start(self, initial_delay_ms_override: int | None = None) -> None:
        """Begin scheduling. Initial fire at INITIAL_DELAY_MS, then every CADENCE_MS."""
        delay = initial_delay_ms_override if initial_delay_ms_override is not None else INITIAL_DELAY_MS
        logger.info("[update] scheduler.start initial_delay_ms=%d cadence_ms=%d", delay, CADENCE_MS)
        self._enabled = True
        self._initial_timer.start(delay)

    def stop(self) -> None:
        logger.info("[update] scheduler.stop")
        self._enabled = False
        self._initial_timer.stop()
        self._cadence_timer.stop()

    def trigger_now(self) -> None:
        """Manual 'Check now' trigger — emits immediately."""
        logger.info("[update] scheduler.trigger_now")
        self.check_requested.emit()

    def _on_initial_fired(self) -> None:
        logger.info("[update] scheduler.initial_fired")
        self.check_requested.emit()
        self._cadence_timer.start(CADENCE_MS)

    def _on_cadence_fired(self) -> None:
        logger.info("[update] scheduler.cadence_fired")
        self.check_requested.emit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/update/test_scheduler.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/update/scheduler.py tests/unit/update/test_scheduler.py
git commit -m "feat(update): UpdateScheduler with 30s initial + 4h cadence"
```

---

## Task 6: `UpdateController` — top-level controller scaffolding

**Files:**
- Modify: `src/locksmith/update/controller.py`
- Test: `tests/unit/update/test_controller.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/update/test_controller.py
import pytest
from unittest.mock import MagicMock

from PySide6.QtCore import QCoreApplication, QSettings

from locksmith.update.controller import UpdateController
from locksmith.update.decision import Release, UpdateAction


@pytest.fixture(autouse=True)
def isolate_qsettings(tmp_path):
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    QCoreApplication.setOrganizationName("LocksmithTest")
    QCoreApplication.setApplicationName("LocksmithTest")
    yield


def _release(**kw):
    defaults = dict(
        version="1.3.0", platform="macos",
        artifact_url="https://x/y", artifact_sha256="abc", artifact_size=1,
        anchor_url="https://x/y.cesr", anchor_said="ESAID",
        is_major=False, is_critical=False,
        release_notes_url="https://x/notes",
        released_at="2026-05-28T00:00:00Z",
        minimum_system_version="13.0",
    )
    defaults.update(kw)
    return Release(**defaults)


def test_controller_constructs_with_current_version():
    controller = UpdateController(current_version="1.2.3", platform="macos")
    assert controller.current_version == "1.2.3"
    assert controller.platform == "macos"


def test_controller_skips_check_when_disabled(qtbot):
    controller = UpdateController(current_version="1.2.3", platform="macos")
    controller.prefs.check_automatically = False
    fake_fetcher = MagicMock(return_value=_release(version="1.3.0"))
    controller._fetch_latest_release = fake_fetcher

    controller._on_check_requested()
    fake_fetcher.assert_not_called()


def test_controller_evaluates_silent_install_action(qtbot):
    controller = UpdateController(current_version="1.2.3", platform="macos")
    controller._fetch_latest_release = MagicMock(return_value=_release(version="1.3.0"))

    received = []
    controller.action_decided.connect(lambda decision: received.append(decision))

    controller._on_check_requested()
    assert len(received) == 1
    assert received[0].action == UpdateAction.SILENT_INSTALL
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/update/test_controller.py -v`
Expected: FAIL

- [ ] **Step 3: Implement controller scaffolding**

```python
# src/locksmith/update/controller.py
"""Top-level update controller (cross-platform).

Wires together: scheduler + decision tree + prefs + (later) platform bridge.
The actual platform-specific updater (Sparkle / WinSparkle) is plugged in
via `set_bridge()` so unit tests can drive the controller without
PyObjC/ctypes.
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal
from keri import help

from locksmith.update.decision import (
    Release, UpdateAction, UpdateDecision,
)
from locksmith.update.prefs import UpdatePrefs
from locksmith.update.scheduler import UpdateScheduler

logger = help.ogler.getLogger(__name__)


class UpdateController(QObject):
    """Cross-platform update orchestrator.

    Signals emitted for the UI layer to subscribe to:
      - action_decided(UpdateDecision)   — fires after every successful check
      - check_failed(str)                — fires when fetch fails (manual check surfaces it)
      - verification_failed(str)         — fires when KERI verification rejects a download
    """

    action_decided = Signal(object)        # UpdateDecision
    check_failed = Signal(str)             # error message
    verification_failed = Signal(str)      # version string

    def __init__(
        self,
        *,
        current_version: str,
        platform: str,
        prefs: UpdatePrefs | None = None,
        scheduler: UpdateScheduler | None = None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.current_version = current_version
        self.platform = platform
        self.prefs = prefs or UpdatePrefs()
        self.scheduler = scheduler or UpdateScheduler(self)
        self.scheduler.check_requested.connect(self._on_check_requested)

        self._bridge = None  # set later by sparkle_init / winsparkle_init

        # Override-able for tests:
        self._fetch_latest_release: Callable[[], Optional[Release]] = self._default_fetch_release

    def start(self) -> None:
        """Begin scheduled checks if prefs allow."""
        if self.prefs.check_automatically:
            logger.info("[update] controller.start check_automatically=True")
            self.scheduler.start()
        else:
            logger.info("[update] controller.start check_automatically=False (idle)")

    def stop(self) -> None:
        self.scheduler.stop()

    def check_now(self) -> None:
        """Manual 'Check now' entry point — bypasses auto-check pref."""
        logger.info("[update] controller.check_now (manual)")
        self.scheduler.trigger_now()

    def set_bridge(self, bridge) -> None:
        """Inject platform-specific Sparkle/WinSparkle bridge."""
        self._bridge = bridge

    # --- internals ---

    def _on_check_requested(self) -> None:
        if not self.prefs.check_automatically:
            logger.info("[update] controller.check_skipped (auto disabled)")
            return
        try:
            release = self._fetch_latest_release()
        except Exception as exc:  # network/parse error
            logger.warning("[update] controller.fetch_failed err=%s", exc)
            self.check_failed.emit(str(exc))
            return

        if release is None:
            logger.info("[update] controller.fetch_returned_none")
            return

        decision = UpdateDecision.evaluate(
            current_version=self.current_version,
            release=release,
        )
        logger.info(
            "[update] controller.action_decided action=%s candidate=%s",
            decision.action.value, release.version,
        )
        self.action_decided.emit(decision)

    def _default_fetch_release(self) -> Release | None:
        """Hook into the bridge's appcast fetch. Real impl lands when bridge is wired."""
        if self._bridge is None:
            return None
        return self._bridge.fetch_latest_release()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/update/test_controller.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/update/controller.py tests/unit/update/test_controller.py
git commit -m "feat(update): UpdateController scaffolding with action_decided signal"
```

---

## Task 7: Sparkle macOS bridge — PyObjC delegate

**Files:**
- Create: `src/locksmith/update/sparkle_bridge.py`
- Create: `src/locksmith/update/sparkle_init.py`
- Test: `tests/unit/update/test_sparkle_bridge.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/update/test_sparkle_bridge.py
"""Sparkle bridge tests — pure Python, no PyObjC dependency.

The bridge module guards PyObjC imports behind `sys.platform == 'darwin'`.
On non-Mac CI this test file exercises only the platform-neutral parts.
"""
import sys

import pytest


pytestmark = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="Sparkle bridge is macOS-only",
)


def test_bridge_module_imports_on_macos():
    from locksmith.update import sparkle_bridge  # noqa: F401


def test_should_proceed_calls_verifier_and_returns_true_on_pass(monkeypatch, tmp_path):
    from locksmith.update.sparkle_bridge import SparkleVerifierDelegate

    staged = tmp_path / "Locksmith-1.3.0.dmg"
    staged.write_bytes(b"fake")

    calls = {}

    def fake_verify(artifact_path, release_info):
        calls["artifact_path"] = artifact_path
        calls["release_info"] = release_info
        return True

    delegate = SparkleVerifierDelegate(
        verifier=fake_verify,
        log_recorder=lambda *args, **kw: None,
        on_failure=lambda *args, **kw: None,
    )
    delegate._captured_release_info = {"version": "1.3.0", "anchor_said": "ESAID"}

    result = delegate.shouldProceedWithInstall(str(staged))
    assert result is True
    assert calls["artifact_path"] == str(staged)
    assert calls["release_info"]["version"] == "1.3.0"


def test_should_proceed_deletes_artifact_and_returns_false_on_fail(tmp_path):
    from locksmith.update.sparkle_bridge import SparkleVerifierDelegate

    staged = tmp_path / "Locksmith-1.3.0.dmg"
    staged.write_bytes(b"tampered")

    failures = []
    log_entries = []

    delegate = SparkleVerifierDelegate(
        verifier=lambda *args, **kw: False,
        log_recorder=lambda **kw: log_entries.append(kw),
        on_failure=lambda version: failures.append(version),
    )
    delegate._captured_release_info = {"version": "1.3.0", "anchor_said": "ESAID"}

    result = delegate.shouldProceedWithInstall(str(staged))
    assert result is False
    assert not staged.exists()
    assert failures == ["1.3.0"]
    assert log_entries and log_entries[0]["status"] == "failed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/update/test_sparkle_bridge.py -v`
Expected: FAIL — `ImportError` (on macOS) or skipped (on non-macOS).

- [ ] **Step 3: Implement the bridge**

```python
# src/locksmith/update/sparkle_bridge.py
"""macOS Sparkle 2.x bridge via PyObjC.

We use Sparkle as an *orchestrator only* — its native EdDSA verification
is OFF (no `SUPublicEDKey` in Info.plist). All trust flows through the
Python KERI verifier (`locksmith.update.verify.verify_artifact` from
Phase 4) which we call in `updater:shouldProceedWithInstallForUpdate:`.

Design:
  - `SparkleVerifierDelegate` is a Python class with platform-neutral
    methods (`shouldProceedWithInstall(staged_path) -> bool`) that can be
    unit-tested without PyObjC.
  - `_SparkleObjCDelegate` is the PyObjC `NSObject` subclass that adapts
    the Sparkle Objective-C protocol calls into the Python class.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable

from keri import help

logger = help.ogler.getLogger(__name__)


class SparkleVerifierDelegate:
    """Platform-neutral verification gate. Holds no Objective-C state."""

    def __init__(
        self,
        *,
        verifier: Callable[[str, dict], bool],
        log_recorder: Callable[..., None],
        on_failure: Callable[[str], None],
    ):
        self._verifier = verifier
        self._log_recorder = log_recorder
        self._on_failure = on_failure
        # _captured_release_info is populated by willDownloadUpdate from the
        # SUAppcastItem the Sparkle delegate receives, then read here.
        self._captured_release_info: dict | None = None
        self._staged_path: str | None = None

    def willDownloadUpdate(self, release_info: dict) -> None:
        logger.info("[update] sparkle.will_download_update version=%s",
                    release_info.get("version"))
        self._captured_release_info = release_info

    def didDownloadUpdate(self, staged_path: str) -> None:
        logger.info("[update] sparkle.did_download_update path=%s", staged_path)
        self._staged_path = staged_path

    def shouldProceedWithInstall(self, staged_path: str) -> bool:
        """Called between download and install. Returns True iff verifier passes.

        On failure: deletes the staged file, records to verification log,
        invokes on_failure callback (which shows the toast).
        """
        info = self._captured_release_info or {}
        version = info.get("version", "unknown")
        logger.info("[update] sparkle.verify_begin version=%s", version)

        try:
            ok = self._verifier(staged_path, info)
        except Exception as exc:
            logger.error("[update] sparkle.verify_error version=%s err=%s", version, exc)
            ok = False

        if ok:
            logger.info("[update] sparkle.verify_pass version=%s", version)
            self._log_recorder(
                version=version,
                status="verified",
                anchor_said=info.get("anchor_said"),
                artifact_sha256=info.get("artifact_sha256"),
            )
            return True

        logger.warning("[update] sparkle.verify_fail version=%s", version)
        self._log_recorder(
            version=version,
            status="failed",
            anchor_said=info.get("anchor_said"),
            artifact_sha256=info.get("artifact_sha256"),
        )
        # Best-effort delete; ignore errors (Sparkle owns the lifecycle)
        try:
            p = Path(staged_path)
            if p.exists():
                p.unlink()
        except OSError as exc:
            logger.warning("[update] sparkle.cleanup_failed path=%s err=%s", staged_path, exc)
        self._on_failure(version)
        return False


# --- macOS-only PyObjC layer ---

if sys.platform == "darwin":  # pragma: no cover (covered by integration test)
    try:
        import objc                                       # noqa: F401
        from Foundation import NSObject                   # noqa: F401
        # Sparkle's SPUUpdaterDelegate protocol comes in via the Sparkle
        # framework loaded into the process at runtime by sparkle_init.
        _PYOBJC_AVAILABLE = True
    except ImportError:
        _PYOBJC_AVAILABLE = False
else:
    _PYOBJC_AVAILABLE = False


def make_objc_delegate(py_delegate: SparkleVerifierDelegate):
    """Return an NSObject that adapts Sparkle protocol callbacks to py_delegate.

    Returns None on non-macOS or when PyObjC isn't available; the caller
    must handle that case (in practice: macOS bundles always have PyObjC).
    """
    if not _PYOBJC_AVAILABLE:
        return None

    from Foundation import NSObject

    class _SparkleObjCDelegate(NSObject):
        def init(self):
            self = objc.super(_SparkleObjCDelegate, self).init()
            return self

        # Sparkle calls: -updater:willDownloadUpdate:withRequest:
        def updater_willDownloadUpdate_withRequest_(self, updater, item, request):
            info = {
                "version": str(item.displayVersionString()) if hasattr(item, "displayVersionString") else None,
                "anchor_said": _info_from_item(item, "SUAnchorSAID"),
                "artifact_sha256": _info_from_item(item, "SUArtifactSHA256"),
                "anchor_url": _info_from_item(item, "SUAnchorURL"),
                "is_major": _info_from_item(item, "SUIsMajor") == "true",
                "is_critical": _info_from_item(item, "SUIsCritical") == "true",
            }
            py_delegate.willDownloadUpdate(info)

        # Sparkle calls: -updater:didDownloadUpdate:
        def updater_didDownloadUpdate_(self, updater, item):
            # Sparkle doesn't directly expose the staged path here;
            # we capture it in shouldProceedWithInstall via item.downloadURL or
            # the staging directory. For now record the item and read path later.
            py_delegate.didDownloadUpdate("(captured-on-install)")

        # Sparkle calls: -updater:shouldProceedWithInstallForUpdate:withDownloadedPath:
        def updater_shouldProceedWithInstallForUpdate_withDownloadedPath_(
            self, updater, item, downloadedPath
        ):
            path = str(downloadedPath)
            return py_delegate.shouldProceedWithInstall(path)

    delegate = _SparkleObjCDelegate.alloc().init()
    return delegate


def _info_from_item(item, key: str) -> str | None:
    """Read a non-standard SUAppcastItem key set via custom appcast XML.

    Sparkle 2 supports arbitrary keys via `propertiesDictionary`.
    """
    try:
        props = item.propertiesDictionary()
        v = props.objectForKey_(key)
        return str(v) if v is not None else None
    except Exception:
        return None
```

```python
# src/locksmith/update/sparkle_init.py
"""macOS Sparkle 2.x initialization.

Called once from `locksmith.core.apping.LocksmithApplication` on Darwin
after the main window is constructed. Creates an
`SPUStandardUpdaterController`, attaches our delegate, and starts checking
on the scheduler's cadence (NOT Sparkle's built-in cadence — we disable
that and drive checks from `UpdateController.check_now`).
"""
from __future__ import annotations

import sys
from typing import Callable

from keri import help

from locksmith.update.sparkle_bridge import (
    SparkleVerifierDelegate, make_objc_delegate,
)

logger = help.ogler.getLogger(__name__)


def init_sparkle(
    *,
    verifier: Callable[[str, dict], bool],
    log_recorder: Callable[..., None],
    on_failure: Callable[[str], None],
):
    """Construct the Sparkle controller + delegate. Returns the controller
    (kept alive by the caller) and the Python delegate (for the bridge).

    On non-macOS, returns (None, None).
    """
    if sys.platform != "darwin":
        return None, None

    try:
        from Sparkle import SPUStandardUpdaterController
    except ImportError as exc:
        logger.error("[update] sparkle.import_failed err=%s", exc)
        return None, None

    py_delegate = SparkleVerifierDelegate(
        verifier=verifier,
        log_recorder=log_recorder,
        on_failure=on_failure,
    )
    objc_delegate = make_objc_delegate(py_delegate)

    # startingUpdater=False — we drive checks from our scheduler instead.
    controller = SPUStandardUpdaterController.alloc().initWithStartingUpdater_updaterDelegate_userDriverDelegate_(
        False, objc_delegate, None,
    )
    logger.info("[update] sparkle.initialized")
    return controller, py_delegate
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/update/test_sparkle_bridge.py -v`
Expected: PASS on macOS; SKIP on other platforms.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/update/sparkle_bridge.py src/locksmith/update/sparkle_init.py tests/unit/update/test_sparkle_bridge.py
git commit -m "feat(update): macOS Sparkle bridge with KERI verification gate"
```

---

## Task 8: WinSparkle Windows bridge — ctypes binding

**Files:**
- Create: `src/locksmith/update/winsparkle_bridge.py`
- Create: `src/locksmith/update/winsparkle_init.py`
- Test: `tests/unit/update/test_winsparkle_bridge.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/update/test_winsparkle_bridge.py
"""WinSparkle bridge tests — pure Python; ctypes guarded for non-Windows."""
import pytest


def test_verifier_gate_returns_true_on_pass(tmp_path):
    from locksmith.update.winsparkle_bridge import WinSparkleVerifierGate
    staged = tmp_path / "Locksmith-1.3.0.msi"
    staged.write_bytes(b"fake")

    gate = WinSparkleVerifierGate(
        verifier=lambda path, info: True,
        log_recorder=lambda **kw: None,
        on_failure=lambda v: None,
    )
    gate.set_release_info({"version": "1.3.0", "anchor_said": "ESAID"})
    gate.set_staged_path(str(staged))
    assert gate.can_shutdown_and_install() is True


def test_verifier_gate_returns_false_on_fail_and_deletes(tmp_path):
    from locksmith.update.winsparkle_bridge import WinSparkleVerifierGate
    staged = tmp_path / "Locksmith-1.3.0.msi"
    staged.write_bytes(b"tampered")

    failures = []
    logs = []
    gate = WinSparkleVerifierGate(
        verifier=lambda path, info: False,
        log_recorder=lambda **kw: logs.append(kw),
        on_failure=lambda v: failures.append(v),
    )
    gate.set_release_info({"version": "1.3.0", "anchor_said": "ESAID"})
    gate.set_staged_path(str(staged))
    assert gate.can_shutdown_and_install() is False
    assert not staged.exists()
    assert failures == ["1.3.0"]
    assert logs and logs[0]["status"] == "failed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/update/test_winsparkle_bridge.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# src/locksmith/update/winsparkle_bridge.py
"""Windows WinSparkle 0.8+ bridge via ctypes.

WinSparkle has no true "pre-install verification" hook. Its lifecycle:
    1. win_sparkle_check_update_with_ui() / *_without_ui()
    2. download into Sparkle staging dir
    3. ready to install — calls the "can shutdown?" callback
    4. relaunches the installer (which closes the app)

We hook step 3 — `win_sparkle_set_can_shutdown_callback` — to invoke the
Python KERI verifier. Returning FALSE from that callback prevents
WinSparkle from launching the MSI installer.

Limitation: WinSparkle's `can_shutdown_callback` semantics is "can we
gracefully exit?", not "should we install?". On a FALSE return, the
update simply stays in the staging directory; on next launch WinSparkle
won't re-trigger the same artifact (it remembers the version was
"downloaded"). We treat this as acceptable for v1 and document it.

Signature verification is DISABLED:
    win_sparkle_set_dsa_pub_pem(NULL)
This is mandatory per spec §3 (KERI is the sole trust mechanism).
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import CFUNCTYPE, c_int, c_void_p, c_char_p
from pathlib import Path
from typing import Callable

from keri import help

logger = help.ogler.getLogger(__name__)


# Callback signatures (WinSparkle uses cdecl on Windows)
CAN_SHUTDOWN_CB = CFUNCTYPE(c_int)
SHUTDOWN_REQUEST_CB = CFUNCTYPE(None)
ERROR_CB = CFUNCTYPE(None)


class WinSparkleVerifierGate:
    """Platform-neutral verification gate; mirrors SparkleVerifierDelegate."""

    def __init__(
        self,
        *,
        verifier: Callable[[str, dict], bool],
        log_recorder: Callable[..., None],
        on_failure: Callable[[str], None],
    ):
        self._verifier = verifier
        self._log_recorder = log_recorder
        self._on_failure = on_failure
        self._release_info: dict = {}
        self._staged_path: str | None = None

    def set_release_info(self, info: dict) -> None:
        self._release_info = info or {}

    def set_staged_path(self, path: str | None) -> None:
        self._staged_path = path

    def can_shutdown_and_install(self) -> bool:
        """Hooked into WinSparkle's can-shutdown callback."""
        if not self._staged_path:
            logger.warning("[update] winsparkle.no_staged_path_at_install")
            return False
        version = self._release_info.get("version", "unknown")
        logger.info("[update] winsparkle.verify_begin version=%s", version)

        try:
            ok = self._verifier(self._staged_path, self._release_info)
        except Exception as exc:
            logger.error("[update] winsparkle.verify_error version=%s err=%s", version, exc)
            ok = False

        if ok:
            logger.info("[update] winsparkle.verify_pass version=%s", version)
            self._log_recorder(
                version=version, status="verified",
                anchor_said=self._release_info.get("anchor_said"),
                artifact_sha256=self._release_info.get("artifact_sha256"),
            )
            return True

        logger.warning("[update] winsparkle.verify_fail version=%s", version)
        self._log_recorder(
            version=version, status="failed",
            anchor_said=self._release_info.get("anchor_said"),
            artifact_sha256=self._release_info.get("artifact_sha256"),
        )
        try:
            p = Path(self._staged_path)
            if p.exists():
                p.unlink()
        except OSError as exc:
            logger.warning("[update] winsparkle.cleanup_failed path=%s err=%s",
                           self._staged_path, exc)
        self._on_failure(version)
        return False


# --- ctypes layer (Windows-only) ---

def load_winsparkle_dll(dll_path: str | None = None):
    """Load WinSparkle.dll. Returns the CDLL handle, or None on non-Windows."""
    if sys.platform != "win32":
        return None
    candidate = dll_path or "WinSparkle.dll"
    try:
        dll = ctypes.cdll.LoadLibrary(candidate)
    except OSError as exc:
        logger.error("[update] winsparkle.load_failed path=%s err=%s", candidate, exc)
        return None

    # Declare prototypes
    dll.win_sparkle_set_appcast_url.argtypes = [c_char_p]
    dll.win_sparkle_set_appcast_url.restype = None
    dll.win_sparkle_set_dsa_pub_pem.argtypes = [c_char_p]
    dll.win_sparkle_set_dsa_pub_pem.restype = None
    dll.win_sparkle_set_can_shutdown_callback.argtypes = [CAN_SHUTDOWN_CB]
    dll.win_sparkle_set_can_shutdown_callback.restype = None
    dll.win_sparkle_set_shutdown_request_callback.argtypes = [SHUTDOWN_REQUEST_CB]
    dll.win_sparkle_set_shutdown_request_callback.restype = None
    dll.win_sparkle_init.argtypes = []
    dll.win_sparkle_init.restype = None
    dll.win_sparkle_cleanup.argtypes = []
    dll.win_sparkle_cleanup.restype = None
    dll.win_sparkle_check_update_with_ui.argtypes = []
    dll.win_sparkle_check_update_with_ui.restype = None
    dll.win_sparkle_check_update_without_ui.argtypes = []
    dll.win_sparkle_check_update_without_ui.restype = None
    logger.info("[update] winsparkle.dll_loaded path=%s", candidate)
    return dll
```

```python
# src/locksmith/update/winsparkle_init.py
"""Windows WinSparkle initialization (called from apping.py on win32)."""
from __future__ import annotations

import sys
from typing import Callable

from keri import help

from locksmith.update.winsparkle_bridge import (
    WinSparkleVerifierGate, load_winsparkle_dll,
    CAN_SHUTDOWN_CB, SHUTDOWN_REQUEST_CB,
)

logger = help.ogler.getLogger(__name__)

APPCAST_URL = b"https://releases.keri.host/appcast/v1/windows.json"


def init_winsparkle(
    *,
    verifier: Callable[[str, dict], bool],
    log_recorder: Callable[..., None],
    on_failure: Callable[[str], None],
):
    """Returns (dll_handle, gate, callbacks_tuple) — all must be retained
    by the caller to keep ctypes callbacks alive.

    On non-Windows, returns (None, None, None).
    """
    if sys.platform != "win32":
        return None, None, None

    dll = load_winsparkle_dll()
    if dll is None:
        return None, None, None

    gate = WinSparkleVerifierGate(
        verifier=verifier,
        log_recorder=log_recorder,
        on_failure=on_failure,
    )

    def _can_shutdown_cb() -> int:
        return 1 if gate.can_shutdown_and_install() else 0

    def _shutdown_request_cb() -> None:
        logger.info("[update] winsparkle.shutdown_requested")
        # No-op here; WinSparkle proceeds with relaunch after this returns.

    c_can_shutdown = CAN_SHUTDOWN_CB(_can_shutdown_cb)
    c_shutdown_req = SHUTDOWN_REQUEST_CB(_shutdown_request_cb)

    dll.win_sparkle_set_appcast_url(APPCAST_URL)
    dll.win_sparkle_set_dsa_pub_pem(None)               # disable signature check
    dll.win_sparkle_set_can_shutdown_callback(c_can_shutdown)
    dll.win_sparkle_set_shutdown_request_callback(c_shutdown_req)
    dll.win_sparkle_init()
    logger.info("[update] winsparkle.initialized appcast=%s", APPCAST_URL.decode())

    callbacks = (c_can_shutdown, c_shutdown_req)
    return dll, gate, callbacks
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/update/test_winsparkle_bridge.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/update/winsparkle_bridge.py src/locksmith/update/winsparkle_init.py tests/unit/update/test_winsparkle_bridge.py
git commit -m "feat(update): Windows WinSparkle ctypes bridge with KERI gate"
```

---

## Task 9: First-launch consent dialog (spec §8.5)

**Files:**
- Create: `src/locksmith/ui/dialogs/__init__.py`
- Create: `src/locksmith/ui/dialogs/update_consent.py`
- Test: `tests/ui/__init__.py`, `tests/ui/test_update_consent.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/ui/test_update_consent.py
import pytest
from PySide6.QtCore import QCoreApplication, QSettings, Qt

from locksmith.update.prefs import UpdatePrefs
from locksmith.ui.dialogs.update_consent import UpdateConsentDialog


@pytest.fixture(autouse=True)
def isolate_qsettings(tmp_path):
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    QCoreApplication.setOrganizationName("LocksmithTest")
    QCoreApplication.setApplicationName("LocksmithTest")


def test_dialog_constructs(qtbot):
    dialog = UpdateConsentDialog()
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == "About Locksmith Updates"


def test_dialog_shows_keri_verification_text(qtbot):
    dialog = UpdateConsentDialog()
    qtbot.addWidget(dialog)
    text = dialog.body_label.text()
    assert "KERI" in text
    assert "verify" in text.lower()
    assert "quit" in text.lower()


def test_accepting_dialog_persists_consent_seen(qtbot):
    dialog = UpdateConsentDialog()
    qtbot.addWidget(dialog)
    dialog._on_accept()
    assert UpdatePrefs().consent_seen is True


def test_should_show_returns_false_when_already_seen():
    prefs = UpdatePrefs()
    prefs.consent_seen = True
    assert UpdateConsentDialog.should_show() is False


def test_should_show_returns_true_when_unseen():
    assert UpdateConsentDialog.should_show() is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_update_consent.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement**

```python
# src/locksmith/ui/dialogs/__init__.py
```

```python
# src/locksmith/ui/dialogs/update_consent.py
"""First-launch update consent dialog (spec §8.5).

One-time dismissible dialog explaining that updates are KERI-verified
and install on quit. Same content is also surfaced in About → Updates.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)
from keri import help

from locksmith.update.prefs import UpdatePrefs

logger = help.ogler.getLogger(__name__)


_BODY_TEXT = (
    "Locksmith checks for updates automatically. Each update is "
    "cryptographically verified against KERI.host's publisher key event "
    "log before it's installed. Updates apply when you quit Locksmith — "
    "no restart prompts, no installers to click through.\n\n"
    "You can change this any time in Settings → Updates."
)


class UpdateConsentDialog(QDialog):
    """Shown once on first launch. Dismissing it marks consent as seen."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About Locksmith Updates")
        self.setObjectName("UpdateConsentDialog")
        self.setModal(True)
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Updates are verified by KERI")
        f = QFont()
        f.setBold(True)
        f.setPointSize(16)
        title.setFont(f)
        layout.addWidget(title)

        self.body_label = QLabel(_BODY_TEXT)
        self.body_label.setWordWrap(True)
        self.body_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.body_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.ok_button = QPushButton("Got it")
        self.ok_button.setObjectName("UpdateConsentOkButton")
        self.ok_button.setDefault(True)
        self.ok_button.clicked.connect(self._on_accept)
        button_row.addWidget(self.ok_button)
        layout.addLayout(button_row)

    def _on_accept(self) -> None:
        UpdatePrefs().consent_seen = True
        logger.info("[update] consent_seen recorded")
        self.accept()

    @staticmethod
    def should_show() -> bool:
        """True on first launch (consent flag unset)."""
        return UpdatePrefs().consent_seen is False
```

```python
# tests/ui/__init__.py
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_update_consent.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/ui/dialogs tests/ui/__init__.py tests/ui/test_update_consent.py
git commit -m "feat(update-ui): first-launch consent dialog"
```

---

## Task 10: "What's New" major-version modal (spec §8.3)

**Files:**
- Create: `src/locksmith/ui/dialogs/whats_new.py`
- Test: `tests/ui/test_whats_new_dialog.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/ui/test_whats_new_dialog.py
import pytest
from PySide6.QtCore import QCoreApplication, QSettings, Qt
from PySide6.QtGui import QKeyEvent

from locksmith.update.prefs import UpdatePrefs
from locksmith.ui.dialogs.whats_new import WhatsNewDialog


@pytest.fixture(autouse=True)
def isolate_qsettings(tmp_path):
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    QCoreApplication.setOrganizationName("LocksmithTest")
    QCoreApplication.setApplicationName("LocksmithTest")


def _payload():
    return dict(
        version="2.0.0",
        summary="Native peer-to-peer sharing without a mailbox.",
        highlights=[
            "Direct peer connections via OOBI exchange",
            "Mailbox fallback when peers are offline",
            "Per-vault peer trust policies",
        ],
        release_notes_url="https://releases.keri.host/notes/2.0.0",
    )


def test_dialog_renders_version_and_summary(qtbot):
    dialog = WhatsNewDialog(**_payload())
    qtbot.addWidget(dialog)
    assert "2.0.0" in dialog.version_label.text()
    assert "peer-to-peer" in dialog.summary_label.text()


def test_dialog_lists_each_highlight_bullet(qtbot):
    payload = _payload()
    dialog = WhatsNewDialog(**payload)
    qtbot.addWidget(dialog)
    rendered = dialog.highlights_label.text()
    for bullet in payload["highlights"]:
        assert bullet in rendered


def test_install_on_quit_emits_signal(qtbot):
    dialog = WhatsNewDialog(**_payload())
    qtbot.addWidget(dialog)
    with qtbot.waitSignal(dialog.install_on_quit_requested, timeout=500):
        dialog.install_button.click()


def test_remind_tomorrow_emits_signal_and_persists_deferral(qtbot):
    dialog = WhatsNewDialog(**_payload())
    qtbot.addWidget(dialog)
    with qtbot.waitSignal(dialog.remind_tomorrow_requested, timeout=500):
        dialog.remind_button.click()
    prefs = UpdatePrefs()
    assert prefs.deferred_version == "2.0.0"
    assert prefs.last_deferred_at is not None


def test_escape_key_acts_as_remind_tomorrow(qtbot):
    dialog = WhatsNewDialog(**_payload())
    qtbot.addWidget(dialog)
    with qtbot.waitSignal(dialog.remind_tomorrow_requested, timeout=500):
        qtbot.keyPress(dialog, Qt.Key.Key_Escape)


def test_dialog_uses_no_qwebengineview(qtbot):
    """Spec §8.3 explicitly forbids embedded web views."""
    dialog = WhatsNewDialog(**_payload())
    qtbot.addWidget(dialog)
    from PySide6.QtWidgets import QWidget
    for child in dialog.findChildren(QWidget):
        assert type(child).__name__ != "QWebEngineView"


def test_full_release_notes_button_present(qtbot):
    dialog = WhatsNewDialog(**_payload())
    qtbot.addWidget(dialog)
    assert dialog.notes_link_button is not None
    assert dialog.notes_link_button.text() == "Full release notes"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_whats_new_dialog.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement**

```python
# src/locksmith/ui/dialogs/whats_new.py
"""'What's New' modal shown for major version updates (spec §8.3).

Constraints:
  - Native QDialog only (no QWebEngineView per spec §8.3)
  - Tone: calm, factual, anti-hype (no rocket emojis, no "amazing release")
  - Dismiss (X / Esc) == "Remind Me Tomorrow"
  - Persists deferral state on "Remind Me Tomorrow"
"""
from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices, QFont, QKeyEvent
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)
from keri import help

from locksmith.update.deferral import Deferral
from locksmith.update.prefs import UpdatePrefs

logger = help.ogler.getLogger(__name__)


class WhatsNewDialog(QDialog):
    install_on_quit_requested = Signal()
    remind_tomorrow_requested = Signal()

    def __init__(
        self,
        *,
        version: str,
        summary: str,
        highlights: list[str],
        release_notes_url: str,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("WhatsNewDialog")
        self.setWindowTitle(f"Locksmith {version}")
        self.setModal(True)
        self.setMinimumWidth(520)

        self._version = version
        self._release_notes_url = release_notes_url

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 24)
        layout.setSpacing(14)

        # Version
        self.version_label = QLabel(f"Locksmith {version}")
        vf = QFont()
        vf.setBold(True)
        vf.setPointSize(20)
        self.version_label.setFont(vf)
        layout.addWidget(self.version_label)

        # Summary (one-line hero)
        self.summary_label = QLabel(summary)
        self.summary_label.setWordWrap(True)
        sf = QFont()
        sf.setPointSize(13)
        self.summary_label.setFont(sf)
        self.summary_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.summary_label)

        # Highlights bullets
        bullet_html = "<ul style='margin-top: 6px; margin-bottom: 6px;'>"
        for h in highlights:
            # PlainText escaping isn't done here because we control the
            # content (provided from a verified appcast); still, no Markdown.
            bullet_html += f"<li>{_html_escape(h)}</li>"
        bullet_html += "</ul>"
        self.highlights_label = QLabel(bullet_html)
        self.highlights_label.setWordWrap(True)
        self.highlights_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.highlights_label)

        # Full release notes (opens browser)
        self.notes_link_button = QPushButton("Full release notes")
        self.notes_link_button.setObjectName("WhatsNewNotesLink")
        self.notes_link_button.setFlat(True)
        self.notes_link_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.notes_link_button.clicked.connect(self._open_notes)
        notes_row = QHBoxLayout()
        notes_row.addWidget(self.notes_link_button)
        notes_row.addStretch(1)
        layout.addLayout(notes_row)

        layout.addStretch(1)

        # Buttons
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.remind_button = QPushButton("Remind Me Tomorrow")
        self.remind_button.setObjectName("WhatsNewRemindButton")
        self.remind_button.clicked.connect(self._on_remind_clicked)
        button_row.addWidget(self.remind_button)

        self.install_button = QPushButton("Install on Quit")
        self.install_button.setObjectName("WhatsNewInstallButton")
        self.install_button.setDefault(True)
        self.install_button.clicked.connect(self._on_install_clicked)
        button_row.addWidget(self.install_button)
        layout.addLayout(button_row)

    def keyPressEvent(self, ev: QKeyEvent) -> None:  # noqa: N802
        if ev.key() == Qt.Key.Key_Escape:
            self._on_remind_clicked()
            return
        super().keyPressEvent(ev)

    def closeEvent(self, ev) -> None:  # noqa: N802
        # Treat X / window-close as "Remind Me Tomorrow"
        self._on_remind_clicked()
        super().closeEvent(ev)

    def _open_notes(self) -> None:
        logger.info("[update] whats_new.open_release_notes url=%s", self._release_notes_url)
        QDesktopServices.openUrl(QUrl(self._release_notes_url))

    def _on_install_clicked(self) -> None:
        logger.info("[update] whats_new.install_on_quit version=%s", self._version)
        self.install_on_quit_requested.emit()
        self.accept()

    def _on_remind_clicked(self) -> None:
        logger.info("[update] whats_new.remind_tomorrow version=%s", self._version)
        prefs = UpdatePrefs()
        new_state = Deferral.record_deferral(
            first_deferred_at=prefs.first_deferred_at,
            deferred_version=prefs.deferred_version,
            candidate_version=self._version,
            now=datetime.now(timezone.utc),
        )
        prefs.first_deferred_at = new_state.first_deferred_at
        prefs.last_deferred_at = new_state.last_deferred_at
        prefs.deferred_version = new_state.deferred_version
        self.remind_tomorrow_requested.emit()
        self.reject()


def _html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_whats_new_dialog.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/ui/dialogs/whats_new.py tests/ui/test_whats_new_dialog.py
git commit -m "feat(update-ui): What's New modal for major version updates"
```

---

## Task 11: Critical-update banner (spec §8.2)

**Files:**
- Create: `src/locksmith/ui/banners/__init__.py`
- Create: `src/locksmith/ui/banners/critical_update.py`
- Test: `tests/ui/test_critical_banner.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/ui/test_critical_banner.py
import pytest
from locksmith.ui.banners.critical_update import CriticalUpdateBanner


def test_banner_hidden_by_default(qtbot):
    banner = CriticalUpdateBanner()
    qtbot.addWidget(banner)
    assert banner.isVisible() is False


def test_show_for_version_displays_version(qtbot):
    banner = CriticalUpdateBanner()
    qtbot.addWidget(banner)
    banner.show()
    banner.show_for_version("1.2.4")
    assert banner.isVisible() is True
    assert "1.2.4" in banner._label.text()
    assert "security" in banner._label.text().lower()


def test_install_now_emits_signal(qtbot):
    banner = CriticalUpdateBanner()
    qtbot.addWidget(banner)
    banner.show()
    banner.show_for_version("1.2.4")
    with qtbot.waitSignal(banner.install_requested, timeout=500):
        banner._install_button.click()


def test_dismiss_hides_banner(qtbot):
    banner = CriticalUpdateBanner()
    qtbot.addWidget(banner)
    banner.show()
    banner.show_for_version("1.2.4")
    banner._dismiss_button.click()
    assert banner.isVisible() is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_critical_banner.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

```python
# src/locksmith/ui/banners/__init__.py
```

```python
# src/locksmith/ui/banners/critical_update.py
"""Orange critical-update banner shown in the main window (spec §8.2).

Pattern mirrors `locksmith.ui.plugins.upgrade_banner.UpgradeBanner` so it
slots into the existing main-window layout cleanly.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QWidget,
)


_ORANGE_BG = "#F59E0B"   # warning orange
_TEXT = "#1F2937"        # near-black


class CriticalUpdateBanner(QWidget):
    install_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("CriticalUpdateBanner")
        self.setStyleSheet(
            f"#CriticalUpdateBanner {{ background-color: {_ORANGE_BG}; }} "
            f"QLabel {{ color: {_TEXT}; }} "
            f"QPushButton {{ background-color: white; color: {_TEXT}; "
            f"border: 1px solid {_TEXT}; border-radius: 4px; padding: 4px 10px; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(12)

        self._label = QLabel("Security update ready.")
        layout.addWidget(self._label, stretch=1)

        self._install_button = QPushButton("Install on Quit")
        self._install_button.setObjectName("CriticalBannerInstallButton")
        self._install_button.clicked.connect(self.install_requested.emit)
        layout.addWidget(self._install_button)

        self._dismiss_button = QPushButton("Dismiss")
        self._dismiss_button.setObjectName("CriticalBannerDismissButton")
        self._dismiss_button.clicked.connect(self.hide)
        layout.addWidget(self._dismiss_button)

        self.hide()

    def show_for_version(self, version: str) -> None:
        self._label.setText(
            f"Security update {version} ready — will install on quit."
        )
        self.show()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_critical_banner.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/ui/banners tests/ui/test_critical_banner.py
git commit -m "feat(update-ui): critical-update orange banner"
```

---

## Task 12: Update-failed toast (spec §9.2)

**Files:**
- Create: `src/locksmith/ui/toasts/__init__.py`
- Create: `src/locksmith/ui/toasts/update_failed.py`
- Test: `tests/ui/test_update_failed_toast.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/ui/test_update_failed_toast.py
import pytest
from PySide6.QtWidgets import QMainWindow

from locksmith.ui.toasts.update_failed import UpdateFailedToast


def test_toast_text_mentions_verification(qtbot):
    window = QMainWindow()
    qtbot.addWidget(window)
    toast = UpdateFailedToast(parent=window)
    qtbot.addWidget(toast)
    toast.show_for_version("1.2.4")
    assert "couldn't be verified" in toast._label.text()
    assert "1.2.4" not in toast._label.text(), \
        "Toast must not leak version numbers — spec §9.2 keeps it generic"


def test_only_one_visible_instance(qtbot):
    window = QMainWindow()
    qtbot.addWidget(window)
    toast = UpdateFailedToast(parent=window)
    qtbot.addWidget(toast)
    toast.show_for_version("1.2.4")
    first_visible = toast.isVisible()
    # second call shouldn't crash and should still show only one
    toast.show_for_version("1.2.5")
    assert toast.isVisible() == first_visible


def test_no_install_anyway_button(qtbot):
    """Spec §9 — verification failure never offers 'Install anyway'."""
    window = QMainWindow()
    qtbot.addWidget(window)
    toast = UpdateFailedToast(parent=window)
    qtbot.addWidget(toast)
    toast.show_for_version("1.2.4")
    from PySide6.QtWidgets import QPushButton
    for btn in toast.findChildren(QPushButton):
        assert "install anyway" not in btn.text().lower()
        assert "force install" not in btn.text().lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_update_failed_toast.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

```python
# src/locksmith/ui/toasts/__init__.py
```

```python
# src/locksmith/ui/toasts/update_failed.py
"""Single-instance toast shown when KERI verification fails (spec §9.2).

Spec rules:
  - Generic message — does NOT leak version numbers, hash details, etc.
  - NEVER offers "Install anyway" or any other affordance to bypass the gate.
  - Single instance: subsequent failures while visible are coalesced.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget
from keri import help

logger = help.ogler.getLogger(__name__)


_BG = "#FEF3C7"
_TEXT = "#1F2937"
_BORDER = "#F59E0B"


class UpdateFailedToast(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("UpdateFailedToast")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet(
            f"#UpdateFailedToast {{ background-color: {_BG}; "
            f"border: 1px solid {_BORDER}; border-radius: 8px; }} "
            f"QLabel {{ color: {_TEXT}; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        self._label = QLabel(
            "An update was downloaded but couldn't be verified. "
            "It's been discarded."
        )
        self._label.setObjectName("UpdateFailedToastLabel")
        layout.addWidget(self._label, stretch=1)

        self._close_button = QPushButton("Dismiss")
        self._close_button.setObjectName("UpdateFailedToastDismissButton")
        self._close_button.clicked.connect(self.hide)
        layout.addWidget(self._close_button)

        self.hide()

    def show_for_version(self, version: str) -> None:
        logger.info("[update] toast.update_failed_shown version=%s", version)
        if self.isVisible():
            return
        self.adjustSize()
        if self.parent() is not None:
            p = self.parent()
            x = (p.width() - self.width()) // 2
            y = p.height() - self.height() - 30
            self.move(x, y)
        self.show()
        # Auto-dismiss after 8s
        QTimer.singleShot(8000, self.hide)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_update_failed_toast.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/ui/toasts tests/ui/test_update_failed_toast.py
git commit -m "feat(update-ui): single-instance update-failed toast (no override)"
```

---

## Task 13: Verification log dialog (spec §8.6)

**Files:**
- Create: `src/locksmith/ui/dialogs/verification_log.py`
- Test: `tests/ui/test_verification_log.py`

This depends on `locksmith.update.log` (Phase 4 deliverable). The plan assumes Phase 4 provides:

```python
# Phase 4: src/locksmith/update/log.py
class VerificationLogEntry:
    version: str
    verified_at: datetime
    status: str               # "verified" | "failed"
    failure_reason: str | None
    publisher_aid: str
    kel_sn: int
    event_said: str
    witness_receipts: list[dict]   # [{aid, received_at}, ...]
    artifact_sha256: str

class VerificationLog:
    @classmethod
    def open(cls) -> "VerificationLog": ...
    def all_entries(self) -> list[VerificationLogEntry]: ...
    def append(self, entry: VerificationLogEntry) -> None: ...
    def export_json(self) -> str: ...
```

- [ ] **Step 1: Write the failing test**

```python
# tests/ui/test_verification_log.py
from datetime import datetime, timezone

import pytest

from locksmith.ui.dialogs.verification_log import VerificationLogDialog


class _FakeEntry:
    def __init__(self, version, status, failure_reason=None):
        self.version = version
        self.verified_at = datetime(2026, 5, 28, 12, 0, tzinfo=timezone.utc)
        self.status = status
        self.failure_reason = failure_reason
        self.publisher_aid = "EAbc...XYZ"
        self.kel_sn = 17
        self.event_said = "ESAID"
        self.witness_receipts = [
            {"aid": "Bwit1", "received_at": "2026-05-28T12:00:01Z"},
            {"aid": "Bwit2", "received_at": "2026-05-28T12:00:02Z"},
        ]
        self.artifact_sha256 = "abc" * 21 + "d"


class _FakeLog:
    def __init__(self, entries):
        self._entries = entries

    def all_entries(self):
        return list(self._entries)

    def export_json(self):
        import json
        return json.dumps([
            {"version": e.version, "status": e.status} for e in self._entries
        ])


def test_dialog_lists_entries(qtbot):
    entries = [
        _FakeEntry("1.2.3", "verified"),
        _FakeEntry("1.2.1-bad", "failed", failure_reason="hash mismatch"),
    ]
    dialog = VerificationLogDialog(log=_FakeLog(entries))
    qtbot.addWidget(dialog)
    assert dialog.table.rowCount() == 2
    assert dialog.table.item(0, 0).text() == "1.2.3"
    assert "✓" in dialog.table.item(0, 2).text()
    assert "✗" in dialog.table.item(1, 2).text()


def test_export_json_emits_string(qtbot):
    entries = [_FakeEntry("1.2.3", "verified")]
    dialog = VerificationLogDialog(log=_FakeLog(entries))
    qtbot.addWidget(dialog)
    received = []
    dialog.export_requested.connect(lambda s: received.append(s))
    dialog.export_button.click()
    assert received and "1.2.3" in received[0]


def test_details_button_opens_detail_view(qtbot):
    entries = [_FakeEntry("1.2.3", "verified")]
    dialog = VerificationLogDialog(log=_FakeLog(entries))
    qtbot.addWidget(dialog)
    received = []
    dialog.detail_requested.connect(lambda entry: received.append(entry.version))
    dialog._open_detail_for_row(0)
    assert received == ["1.2.3"]


def test_empty_log_renders_empty_state(qtbot):
    dialog = VerificationLogDialog(log=_FakeLog([]))
    qtbot.addWidget(dialog)
    assert dialog.empty_label.isVisible() is True
    assert dialog.table.isVisible() is False


def test_detail_view_shows_publisher_aid_and_witnesses(qtbot):
    from locksmith.ui.dialogs.verification_log import VerificationDetailDialog
    entry = _FakeEntry("1.2.3", "verified")
    detail = VerificationDetailDialog(entry=entry)
    qtbot.addWidget(detail)
    text = detail.details_text.toPlainText()
    assert "EAbc...XYZ" in text
    assert "17" in text
    assert "Bwit1" in text
    assert "Bwit2" in text


def test_no_install_anyway_in_verification_log(qtbot):
    """Spec §9 — verification log never has a re-install affordance for failed entries."""
    entries = [_FakeEntry("1.2.1-bad", "failed", failure_reason="hash mismatch")]
    dialog = VerificationLogDialog(log=_FakeLog(entries))
    qtbot.addWidget(dialog)
    from PySide6.QtWidgets import QPushButton
    for btn in dialog.findChildren(QPushButton):
        assert "install anyway" not in btn.text().lower()
        assert "retry install" not in btn.text().lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_verification_log.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement**

```python
# src/locksmith/ui/dialogs/verification_log.py
"""Verification log dialog (spec §8.6).

Reads from `locksmith.update.log.VerificationLog` (Phase 4). Renders a
table; clicking [details ►] opens a full read-only KERI trace. Export
button exposes JSON for support tickets.
"""
from __future__ import annotations

from typing import Protocol

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)
from keri import help

logger = help.ogler.getLogger(__name__)


class VerificationLogProtocol(Protocol):
    def all_entries(self) -> list: ...
    def export_json(self) -> str: ...


_COL_VERSION = 0
_COL_VERIFIED_AT = 1
_COL_STATUS = 2
_COL_ACTION = 3


class VerificationLogDialog(QDialog):
    export_requested = Signal(str)       # JSON text
    detail_requested = Signal(object)    # log entry

    def __init__(self, log: VerificationLogProtocol, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("VerificationLogDialog")
        self.setWindowTitle("Update Verification Log")
        self.setMinimumSize(720, 420)
        self._log = log

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("Update verification history")
        f = QFont(); f.setBold(True); f.setPointSize(14)
        title.setFont(f)
        layout.addWidget(title)

        self.empty_label = QLabel("No updates have been verified yet.")
        self.empty_label.setStyleSheet("color: #6B7280; padding: 24px;")
        layout.addWidget(self.empty_label)

        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(["Version", "Verified at", "Status", "Action"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table, stretch=1)

        button_row = QHBoxLayout()
        self.export_button = QPushButton("Export JSON")
        self.export_button.setObjectName("VerificationLogExportButton")
        self.export_button.clicked.connect(self._on_export)
        button_row.addWidget(self.export_button)
        button_row.addStretch(1)
        self.close_button = QPushButton("Close")
        self.close_button.setObjectName("VerificationLogCloseButton")
        self.close_button.clicked.connect(self.accept)
        button_row.addWidget(self.close_button)
        layout.addLayout(button_row)

        self._populate()

    def _populate(self) -> None:
        entries = self._log.all_entries()
        if not entries:
            self.empty_label.show()
            self.table.hide()
            return
        self.empty_label.hide()
        self.table.show()
        self.table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            v_item = QTableWidgetItem(entry.version)
            self.table.setItem(row, _COL_VERSION, v_item)
            self.table.setItem(
                row, _COL_VERIFIED_AT,
                QTableWidgetItem(entry.verified_at.strftime("%Y-%m-%d %H:%M")),
            )
            if entry.status == "verified":
                s = QTableWidgetItem("✓ Verified")
                s.setForeground(QColor("#059669"))
            else:
                reason = entry.failure_reason or ""
                s = QTableWidgetItem(f"✗ Failed — {reason}".rstrip(" —"))
                s.setForeground(QColor("#DC2626"))
            self.table.setItem(row, _COL_STATUS, s)

            details_btn = QPushButton("details ►")
            details_btn.setObjectName(f"VerificationLogDetailsButton_{row}")
            details_btn.clicked.connect(
                lambda checked=False, r=row: self._open_detail_for_row(r)
            )
            self.table.setCellWidget(row, _COL_ACTION, details_btn)
        self.table.resizeColumnsToContents()

    def _open_detail_for_row(self, row: int) -> None:
        entries = self._log.all_entries()
        if 0 <= row < len(entries):
            entry = entries[row]
            logger.info("[update] verification_log.open_detail version=%s", entry.version)
            self.detail_requested.emit(entry)
            VerificationDetailDialog(entry=entry, parent=self).exec()

    def _on_export(self) -> None:
        text = self._log.export_json()
        logger.info("[update] verification_log.export_json bytes=%d", len(text))
        self.export_requested.emit(text)


class VerificationDetailDialog(QDialog):
    """Read-only full KERI trace for a single verification."""

    def __init__(self, entry, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("VerificationDetailDialog")
        self.setWindowTitle(f"Verification trace — {entry.version}")
        self.setMinimumSize(560, 380)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setPlainText(_format_entry(entry))
        layout.addWidget(self.details_text, stretch=1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        close = QPushButton("Close")
        close.setObjectName("VerificationDetailCloseButton")
        close.clicked.connect(self.accept)
        button_row.addWidget(close)
        layout.addLayout(button_row)


def _format_entry(entry) -> str:
    lines = [
        f"Version:           {entry.version}",
        f"Verified at:       {entry.verified_at.isoformat()}",
        f"Status:            {entry.status}",
    ]
    if entry.status == "failed":
        lines.append(f"Failure reason:    {entry.failure_reason or '(unspecified)'}")
    lines.extend([
        "",
        "Publisher AID:     " + entry.publisher_aid,
        f"KEL sequence #:    {entry.kel_sn}",
        "Event SAID:        " + entry.event_said,
        "Artifact SHA-256:  " + entry.artifact_sha256,
        "",
        "Witness receipts:",
    ])
    for w in entry.witness_receipts:
        lines.append(f"  • {w['aid']}   received {w['received_at']}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_verification_log.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/ui/dialogs/verification_log.py tests/ui/test_verification_log.py
git commit -m "feat(update-ui): verification log dialog + detail view"
```

---

## Task 14: Settings → Updates widget

**Files:**
- Create: `src/locksmith/ui/settings/__init__.py`
- Create: `src/locksmith/ui/settings/updates.py`
- Test: `tests/ui/test_updates_settings.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/ui/test_updates_settings.py
import pytest
from PySide6.QtCore import QCoreApplication, QSettings

from locksmith.update.prefs import UpdatePrefs
from locksmith.ui.settings.updates import UpdatesSettingsWidget, UpdateStatus


@pytest.fixture(autouse=True)
def isolate_qsettings(tmp_path):
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    QCoreApplication.setOrganizationName("LocksmithTest")
    QCoreApplication.setApplicationName("LocksmithTest")


def test_default_status_is_up_to_date(qtbot):
    w = UpdatesSettingsWidget()
    qtbot.addWidget(w)
    assert "up to date" in w.status_label.text().lower()


def test_set_status_update_ready(qtbot):
    w = UpdatesSettingsWidget()
    qtbot.addWidget(w)
    w.set_status(UpdateStatus.UPDATE_READY, version="1.2.4")
    assert "1.2.4" in w.status_label.text()
    assert "install on quit" in w.status_label.text().lower()


def test_set_status_critical(qtbot):
    w = UpdatesSettingsWidget()
    qtbot.addWidget(w)
    w.set_status(UpdateStatus.CRITICAL_READY, version="1.2.4")
    assert "security" in w.status_label.text().lower()


def test_set_status_failed_check(qtbot):
    w = UpdatesSettingsWidget()
    qtbot.addWidget(w)
    w.set_status(UpdateStatus.CHECK_FAILED, last_success="2026-05-25 09:00")
    assert "couldn't check" in w.status_label.text().lower()
    assert "2026-05-25" in w.status_label.text()


def test_toggle_persists_to_prefs(qtbot):
    w = UpdatesSettingsWidget()
    qtbot.addWidget(w)
    assert w.auto_check_toggle.isChecked() is True
    w.auto_check_toggle.setChecked(False)
    assert UpdatePrefs().check_automatically is False


def test_check_now_emits_signal(qtbot):
    w = UpdatesSettingsWidget()
    qtbot.addWidget(w)
    with qtbot.waitSignal(w.check_now_requested, timeout=500):
        w.check_now_button.click()


def test_view_verification_log_emits_signal(qtbot):
    w = UpdatesSettingsWidget()
    qtbot.addWidget(w)
    with qtbot.waitSignal(w.view_log_requested, timeout=500):
        w.view_log_button.click()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_updates_settings.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

```python
# src/locksmith/ui/settings/__init__.py
```

```python
# src/locksmith/ui/settings/updates.py
"""Settings → Updates widget (spec §8.6).

Surfaces: status line w/ colored dot, "Check automatically" toggle,
"Check now" button, "View verification log" button.
"""
from __future__ import annotations

from enum import Enum

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)
from keri import help

from locksmith.update.prefs import UpdatePrefs

logger = help.ogler.getLogger(__name__)


class UpdateStatus(Enum):
    UP_TO_DATE = "up_to_date"          # green
    UPDATE_READY = "update_ready"      # blue
    CRITICAL_READY = "critical_ready"  # orange
    CHECK_FAILED = "check_failed"      # yellow


_DOT_COLORS = {
    UpdateStatus.UP_TO_DATE: "#059669",
    UpdateStatus.UPDATE_READY: "#2563EB",
    UpdateStatus.CRITICAL_READY: "#F59E0B",
    UpdateStatus.CHECK_FAILED: "#FACC15",
}


class UpdatesSettingsWidget(QWidget):
    check_now_requested = Signal()
    view_log_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("UpdatesSettingsWidget")
        self._prefs = UpdatePrefs()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        header = QLabel("Updates")
        hf = QFont(); hf.setBold(True); hf.setPointSize(14)
        header.setFont(hf)
        layout.addWidget(header)

        # Status row
        status_row = QHBoxLayout()
        self.dot_label = QLabel("●")
        self.dot_label.setObjectName("UpdatesStatusDot")
        status_row.addWidget(self.dot_label)
        self.status_label = QLabel("You're up to date.")
        self.status_label.setObjectName("UpdatesStatusLabel")
        status_row.addWidget(self.status_label)
        status_row.addStretch(1)
        layout.addLayout(status_row)

        # Auto-check toggle
        self.auto_check_toggle = QCheckBox("Check automatically")
        self.auto_check_toggle.setObjectName("UpdatesAutoCheckToggle")
        self.auto_check_toggle.setChecked(self._prefs.check_automatically)
        self.auto_check_toggle.toggled.connect(self._on_auto_toggled)
        layout.addWidget(self.auto_check_toggle)

        # Buttons
        button_row = QHBoxLayout()
        self.check_now_button = QPushButton("Check now")
        self.check_now_button.setObjectName("UpdatesCheckNowButton")
        self.check_now_button.clicked.connect(self.check_now_requested.emit)
        button_row.addWidget(self.check_now_button)

        self.view_log_button = QPushButton("View verification log")
        self.view_log_button.setObjectName("UpdatesViewLogButton")
        self.view_log_button.clicked.connect(self.view_log_requested.emit)
        button_row.addWidget(self.view_log_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        self.set_status(UpdateStatus.UP_TO_DATE)

    def set_status(
        self,
        status: UpdateStatus,
        *,
        version: str | None = None,
        last_success: str | None = None,
    ) -> None:
        color = _DOT_COLORS[status]
        self.dot_label.setStyleSheet(f"color: {color}; font-size: 16px;")
        if status == UpdateStatus.UP_TO_DATE:
            self.status_label.setText("You're up to date.")
        elif status == UpdateStatus.UPDATE_READY:
            self.status_label.setText(
                f"Update {version} ready — will install on quit."
            )
        elif status == UpdateStatus.CRITICAL_READY:
            self.status_label.setText(
                f"Security update {version} ready."
            )
        elif status == UpdateStatus.CHECK_FAILED:
            suffix = f" (last successful check: {last_success})" if last_success else ""
            self.status_label.setText(f"Couldn't check for updates{suffix}.")

    def _on_auto_toggled(self, checked: bool) -> None:
        self._prefs.check_automatically = bool(checked)
        logger.info("[update] settings.auto_check_set value=%s", checked)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_updates_settings.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/ui/settings tests/ui/test_updates_settings.py
git commit -m "feat(update-ui): Settings → Updates widget with status + toggle"
```

---

## Task 15: Wire `UpdateController` UI signals to dialogs/banner/toast

**Files:**
- Modify: `src/locksmith/update/controller.py`
- Test: `tests/unit/update/test_controller_ui_routing.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/update/test_controller_ui_routing.py
import pytest
from unittest.mock import MagicMock

from PySide6.QtCore import QCoreApplication, QSettings

from locksmith.update.controller import UpdateController
from locksmith.update.decision import Release, UpdateAction, UpdateDecision


@pytest.fixture(autouse=True)
def isolate(tmp_path):
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    QCoreApplication.setOrganizationName("LocksmithTest")
    QCoreApplication.setApplicationName("LocksmithTest")


def _release(**kw):
    defaults = dict(
        version="1.3.0", platform="macos",
        artifact_url="https://x/y", artifact_sha256="abc", artifact_size=1,
        anchor_url="https://x/y.cesr", anchor_said="ESAID",
        is_major=False, is_critical=False,
        release_notes_url="https://x/notes",
        released_at="2026-05-28T00:00:00Z",
        minimum_system_version="13.0",
    )
    defaults.update(kw)
    return Release(**defaults)


def test_handle_decision_routes_critical_to_banner(qtbot):
    controller = UpdateController(current_version="1.2.3", platform="macos")
    sink = MagicMock()
    controller.show_critical_banner_requested = MagicMock()
    controller.show_critical_banner_requested.emit = sink

    decision = UpdateDecision(
        action=UpdateAction.SHOW_CRITICAL_BANNER,
        release=_release(version="1.2.4", is_critical=True),
    )
    controller.handle_decision(decision)
    sink.assert_called_once_with("1.2.4")


def test_handle_decision_routes_major_to_whats_new(qtbot):
    controller = UpdateController(current_version="1.2.3", platform="macos")
    sink = MagicMock()
    controller.show_whats_new_requested = MagicMock()
    controller.show_whats_new_requested.emit = sink

    rel = _release(version="2.0.0", is_major=True)
    controller.handle_decision(
        UpdateDecision(action=UpdateAction.SHOW_WHATS_NEW_MODAL, release=rel)
    )
    sink.assert_called_once_with(rel)


def test_handle_decision_routes_silent_to_install_on_quit(qtbot):
    controller = UpdateController(current_version="1.2.3", platform="macos")
    sink = MagicMock()
    controller.silent_install_scheduled = MagicMock()
    controller.silent_install_scheduled.emit = sink

    rel = _release(version="1.3.0")
    controller.handle_decision(
        UpdateDecision(action=UpdateAction.SILENT_INSTALL, release=rel)
    )
    sink.assert_called_once_with(rel)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/update/test_controller_ui_routing.py -v`
Expected: FAIL.

- [ ] **Step 3: Modify controller**

Add to `src/locksmith/update/controller.py` (within the `UpdateController` class):

```python
    # Signals for the UI layer:
    show_critical_banner_requested = Signal(str)        # version
    show_whats_new_requested = Signal(object)           # Release
    silent_install_scheduled = Signal(object)           # Release

    def handle_decision(self, decision: UpdateDecision) -> None:
        """Route an UpdateDecision to the appropriate UI surface."""
        from locksmith.update.decision import UpdateAction
        if decision.action == UpdateAction.NO_UPDATE:
            return
        if decision.action == UpdateAction.SHOW_CRITICAL_BANNER:
            self.show_critical_banner_requested.emit(decision.release.version)
        elif decision.action == UpdateAction.SHOW_WHATS_NEW_MODAL:
            self.show_whats_new_requested.emit(decision.release)
        elif decision.action == UpdateAction.SILENT_INSTALL:
            self.silent_install_scheduled.emit(decision.release)
```

Also wire `action_decided` -> `handle_decision` in `__init__`:

```python
        self.action_decided.connect(self.handle_decision)
```

Add these two Signal declarations at the class-level (after `verification_failed = Signal(str)`).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/update/test_controller_ui_routing.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/update/controller.py tests/unit/update/test_controller_ui_routing.py
git commit -m "feat(update): controller routes decisions to banner/modal/silent signals"
```

---

## Task 16: Bootstrap wiring — `LocksmithApplication` holds the controller

**Files:**
- Modify: `src/locksmith/core/apping.py`
- Test: `tests/unit/update/test_apping_wires_controller.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/update/test_apping_wires_controller.py
import pytest
from PySide6.QtCore import QCoreApplication, QSettings


@pytest.fixture(autouse=True)
def isolate(tmp_path):
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    QCoreApplication.setOrganizationName("LocksmithTest")
    QCoreApplication.setApplicationName("LocksmithTest")


def test_app_constructs_update_controller():
    from locksmith.core.apping import LocksmithApplication
    from locksmith.core.configing import LocksmithConfig
    from locksmith.update.controller import UpdateController

    app = LocksmithApplication(config=LocksmithConfig.get_instance())
    assert isinstance(app.update_controller, UpdateController)


def test_app_exposes_verification_log():
    from locksmith.core.apping import LocksmithApplication
    from locksmith.core.configing import LocksmithConfig

    app = LocksmithApplication(config=LocksmithConfig.get_instance())
    # log may be lazily initialized; just confirm attribute exists
    assert hasattr(app, "verification_log")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/update/test_apping_wires_controller.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'update_controller'`

- [ ] **Step 3: Modify `apping.py`**

Add at the top of `apping.py`:

```python
import platform as _platform
import sys
from importlib import import_module

from locksmith.update.controller import UpdateController
from locksmith.version import __version__ as _LOCKSMITH_VERSION
```

(If `locksmith.version` doesn't yet export `__version__`, Phase 2 added it — verify when implementing.)

Inside `LocksmithApplication.__init__`, **after** `self.plugin_update_checker` is constructed, add:

```python
        # --- Update system (spec §8) ---
        self.update_controller = UpdateController(
            current_version=_LOCKSMITH_VERSION,
            platform=_detect_platform(),
            parent=None,
        )
        try:
            log_mod = import_module("locksmith.update.log")
            self.verification_log = log_mod.VerificationLog.open()
        except Exception as exc:  # Phase 4 not present in this test env
            logger.info("[update] verification_log.unavailable err=%s", exc)
            self.verification_log = None
```

Add at module scope:

```python
def _detect_platform() -> str:
    if sys.platform == "darwin":
        return "macos"
    if sys.platform == "win32":
        return "windows"
    return _platform.system().lower()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/update/test_apping_wires_controller.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/core/apping.py tests/unit/update/test_apping_wires_controller.py
git commit -m "feat(update): wire UpdateController into LocksmithApplication"
```

---

## Task 17: Bootstrap wiring — main window mounts banner, toast, consent

**Files:**
- Modify: `src/locksmith/ui/window.py`
- Test: `tests/ui/test_window_mounts_update_surfaces.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/ui/test_window_mounts_update_surfaces.py
import pytest
from PySide6.QtCore import QCoreApplication, QSettings

from locksmith.ui.banners.critical_update import CriticalUpdateBanner
from locksmith.ui.toasts.update_failed import UpdateFailedToast


@pytest.fixture(autouse=True)
def isolate(tmp_path):
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    QCoreApplication.setOrganizationName("LocksmithTest")
    QCoreApplication.setApplicationName("LocksmithTest")


def test_window_mounts_critical_banner(qtbot):
    from locksmith.ui.window import LocksmithWindow
    from locksmith.core.configing import LocksmithConfig
    w = LocksmithWindow(LocksmithConfig.get_instance())
    qtbot.addWidget(w)
    found = w.findChildren(CriticalUpdateBanner)
    assert len(found) == 1


def test_window_mounts_update_failed_toast(qtbot):
    from locksmith.ui.window import LocksmithWindow
    from locksmith.core.configing import LocksmithConfig
    w = LocksmithWindow(LocksmithConfig.get_instance())
    qtbot.addWidget(w)
    found = w.findChildren(UpdateFailedToast)
    assert len(found) == 1


def test_critical_signal_shows_banner(qtbot):
    from locksmith.ui.window import LocksmithWindow
    from locksmith.core.configing import LocksmithConfig
    w = LocksmithWindow(LocksmithConfig.get_instance())
    qtbot.addWidget(w)
    w.app.update_controller.show_critical_banner_requested.emit("1.2.4")
    banner = w.findChildren(CriticalUpdateBanner)[0]
    assert banner.isVisible() is True


def test_verification_failure_shows_toast(qtbot):
    from locksmith.ui.window import LocksmithWindow
    from locksmith.core.configing import LocksmithConfig
    w = LocksmithWindow(LocksmithConfig.get_instance())
    qtbot.addWidget(w)
    w.show()
    w.app.update_controller.verification_failed.emit("1.2.4")
    toast = w.findChildren(UpdateFailedToast)[0]
    assert toast.isVisible() is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_window_mounts_update_surfaces.py -v`
Expected: FAIL.

- [ ] **Step 3: Modify `window.py`**

In `LocksmithWindow.__init__`, after the `self.upgrade_banner` block, add:

```python
        # Critical update banner (spec §8.2)
        from locksmith.ui.banners.critical_update import CriticalUpdateBanner
        self.critical_update_banner = CriticalUpdateBanner(parent=central_widget)
        outer_layout.addWidget(self.critical_update_banner)
        self.app.update_controller.show_critical_banner_requested.connect(
            self.critical_update_banner.show_for_version
        )

        # Update-failed toast (spec §9.2)
        from locksmith.ui.toasts.update_failed import UpdateFailedToast
        self.update_failed_toast = UpdateFailedToast(parent=self)
        self.app.update_controller.verification_failed.connect(
            self.update_failed_toast.show_for_version
        )

        # First-launch consent (spec §8.5)
        from locksmith.ui.dialogs.update_consent import UpdateConsentDialog
        if UpdateConsentDialog.should_show():
            QTimer.singleShot(800, lambda: UpdateConsentDialog(parent=self).exec())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_window_mounts_update_surfaces.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/ui/window.py tests/ui/test_window_mounts_update_surfaces.py
git commit -m "feat(update-ui): mount critical banner + update-failed toast + consent"
```

---

## Task 18: Hook "What's New" modal into the controller

**Files:**
- Modify: `src/locksmith/ui/window.py`
- Test: `tests/ui/test_window_whats_new_routing.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/ui/test_window_whats_new_routing.py
import pytest
from PySide6.QtCore import QCoreApplication, QSettings

from locksmith.update.decision import Release


@pytest.fixture(autouse=True)
def isolate(tmp_path):
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    QCoreApplication.setOrganizationName("LocksmithTest")
    QCoreApplication.setApplicationName("LocksmithTest")


def _release(version="2.0.0"):
    return Release(
        version=version, platform="macos",
        artifact_url="https://x/y", artifact_sha256="abc", artifact_size=1,
        anchor_url="https://x/y.cesr", anchor_said="ESAID",
        is_major=True, is_critical=False,
        release_notes_url="https://x/notes",
        released_at="2026-05-28T00:00:00Z",
        minimum_system_version="13.0",
    )


def test_whats_new_signal_opens_dialog(qtbot, monkeypatch):
    from locksmith.ui.window import LocksmithWindow
    from locksmith.core.configing import LocksmithConfig
    w = LocksmithWindow(LocksmithConfig.get_instance())
    qtbot.addWidget(w)

    opened = []

    from locksmith.ui.dialogs import whats_new as wn

    class _FakeDialog:
        def __init__(self, **kw):
            opened.append(kw)
            self.install_on_quit_requested = wn.WhatsNewDialog.install_on_quit_requested
            self.remind_tomorrow_requested = wn.WhatsNewDialog.remind_tomorrow_requested

        def exec(self):
            return 0

    monkeypatch.setattr(wn, "WhatsNewDialog", _FakeDialog)
    w.app.update_controller.show_whats_new_requested.emit(_release(version="2.0.0"))
    assert opened and opened[0]["version"] == "2.0.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_window_whats_new_routing.py -v`
Expected: FAIL.

- [ ] **Step 3: Modify `window.py`**

After the critical banner wiring, add:

```python
        # What's New modal (spec §8.3)
        self.app.update_controller.show_whats_new_requested.connect(
            self._on_show_whats_new
        )
```

And add the method on `LocksmithWindow`:

```python
    def _on_show_whats_new(self, release) -> None:
        from locksmith.ui.dialogs.whats_new import WhatsNewDialog
        # Highlights + summary come from the release notes API; for v1 we
        # source them from the release_notes_url metadata embedded in the
        # appcast or fall back to a short generic line.
        summary = getattr(release, "summary", None) or "New major release available."
        highlights = list(getattr(release, "highlights", []) or [])
        dlg = WhatsNewDialog(
            version=release.version,
            summary=summary,
            highlights=highlights[:5],
            release_notes_url=release.release_notes_url,
            parent=self,
        )
        dlg.exec()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_window_whats_new_routing.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/ui/window.py tests/ui/test_window_whats_new_routing.py
git commit -m "feat(update-ui): open What's New modal from controller signal"
```

---

## Task 19: Add Updates section to Settings page

**Files:**
- Modify: `src/locksmith/ui/vault/settings/page.py`
- Test: `tests/ui/test_settings_page_has_updates_section.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/ui/test_settings_page_has_updates_section.py
import pytest
from PySide6.QtCore import QCoreApplication, QSettings

from locksmith.ui.settings.updates import UpdatesSettingsWidget


@pytest.fixture(autouse=True)
def isolate(tmp_path):
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    QCoreApplication.setOrganizationName("LocksmithTest")
    QCoreApplication.setApplicationName("LocksmithTest")


def test_settings_page_contains_updates_section(qtbot):
    from PySide6.QtWidgets import QWidget
    from locksmith.ui.vault.settings.page import SettingsPage
    parent = QWidget()
    parent.app = None
    page = SettingsPage(parent=parent)
    qtbot.addWidget(page)
    assert page.findChildren(UpdatesSettingsWidget), \
        "SettingsPage should embed an UpdatesSettingsWidget"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_settings_page_has_updates_section.py -v`
Expected: FAIL.

- [ ] **Step 3: Modify `page.py`**

In `SettingsPage.__init__`, locate `self._create_danger_zone_section(content_layout)` and add **before** it:

```python
        # Updates section (spec §8.6)
        self._create_updates_section(content_layout)
```

Add the method at the bottom of the class:

```python
    def _create_updates_section(self, parent_layout):
        from locksmith.ui.settings.updates import UpdatesSettingsWidget
        from locksmith.ui.dialogs.verification_log import VerificationLogDialog

        self.updates_widget = UpdatesSettingsWidget(self)
        parent_layout.addWidget(self.updates_widget)

        if self.app is not None and getattr(self.app, "update_controller", None) is not None:
            self.updates_widget.check_now_requested.connect(
                self.app.update_controller.check_now
            )

        def _open_log():
            if self.app is None or getattr(self.app, "verification_log", None) is None:
                return
            VerificationLogDialog(log=self.app.verification_log, parent=self).exec()

        self.updates_widget.view_log_requested.connect(_open_log)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_settings_page_has_updates_section.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/ui/vault/settings/page.py tests/ui/test_settings_page_has_updates_section.py
git commit -m "feat(update-ui): add Updates section to vault settings page"
```

---

## Task 20: Add "Check for updates…" entry to Help menu

**Files:**
- Modify: `src/locksmith/ui/window.py`
- Test: `tests/ui/test_window_help_menu.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/ui/test_window_help_menu.py
import pytest
from PySide6.QtCore import QCoreApplication, QSettings


@pytest.fixture(autouse=True)
def isolate(tmp_path):
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    QCoreApplication.setOrganizationName("LocksmithTest")
    QCoreApplication.setApplicationName("LocksmithTest")


def test_help_menu_has_check_for_updates_action(qtbot):
    from locksmith.ui.window import LocksmithWindow
    from locksmith.core.configing import LocksmithConfig
    w = LocksmithWindow(LocksmithConfig.get_instance())
    qtbot.addWidget(w)
    actions = [a.text() for a in w.menuBar().actions()]
    assert any("Help" in a for a in actions), f"Expected Help menu, found {actions}"

    help_menu = next(m for m in w.menuBar().findChildren(type(w.menuBar())) if False)
    # Iterate through menubar's QMenu children
    from PySide6.QtWidgets import QMenu
    help_menu = None
    for m in w.menuBar().findChildren(QMenu):
        if m.title().replace("&", "") == "Help":
            help_menu = m
            break
    assert help_menu is not None
    titles = [a.text().replace("&", "") for a in help_menu.actions()]
    assert any("Check for updates" in t for t in titles), f"Expected 'Check for updates…', got {titles}"


def test_check_for_updates_action_triggers_check_now(qtbot, monkeypatch):
    from locksmith.ui.window import LocksmithWindow
    from locksmith.core.configing import LocksmithConfig
    from PySide6.QtWidgets import QMenu

    w = LocksmithWindow(LocksmithConfig.get_instance())
    qtbot.addWidget(w)

    triggered = []
    monkeypatch.setattr(
        w.app.update_controller, "check_now",
        lambda: triggered.append(1),
    )

    help_menu = next(
        m for m in w.menuBar().findChildren(QMenu)
        if m.title().replace("&", "") == "Help"
    )
    action = next(
        a for a in help_menu.actions()
        if "Check for updates" in a.text().replace("&", "")
    )
    action.trigger()
    assert triggered == [1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_window_help_menu.py -v`
Expected: FAIL.

- [ ] **Step 3: Modify `window.py`**

In `LocksmithWindow.__init__`, after the toolbar is added, add:

```python
        self._build_menu_bar()
```

Add the method:

```python
    def _build_menu_bar(self) -> None:
        from PySide6.QtGui import QAction
        menubar = self.menuBar()
        help_menu = menubar.addMenu("&Help")

        check_action = QAction("Check for updates…", self)
        check_action.setObjectName("HelpMenuCheckForUpdatesAction")
        check_action.triggered.connect(self.app.update_controller.check_now)
        help_menu.addAction(check_action)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_window_help_menu.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/ui/window.py tests/ui/test_window_help_menu.py
git commit -m "feat(update-ui): Help menu → Check for updates…"
```

---

## Task 21: Start the controller from `main.py` after window shown

**Files:**
- Modify: `src/locksmith/main.py`
- Test: smoke-tested in Task 23 integration tests (no separate unit test)

- [ ] **Step 1: Edit `main.py`**

After `window.show()` and before `with loop:`, add:

```python
    # Start the update scheduler (spec §8.1)
    window.app.update_controller.start()
```

- [ ] **Step 2: Run existing tests to confirm nothing breaks**

Run: `pytest tests/ -x -q --ignore=tests/integration`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add src/locksmith/main.py
git commit -m "feat(update): start update controller on app bootstrap"
```

---

## Task 22: PyInstaller spec — embed Sparkle.framework on macOS

**Files:**
- Modify: `packaging/Locksmith.macos.spec`
- Modify: `scripts/signLibs.sh`
- Test: `tests/unit/update/test_macos_spec_has_sparkle.py`

(Spec from Phase 2 is the baseline; this task only adds the Sparkle bits.)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/update/test_macos_spec_has_sparkle.py
from pathlib import Path


def test_macos_spec_references_sparkle_framework():
    spec_path = Path("packaging/Locksmith.macos.spec")
    content = spec_path.read_text()
    assert "Sparkle.framework" in content


def test_macos_spec_sets_sufeed_url():
    spec_path = Path("packaging/Locksmith.macos.spec")
    content = spec_path.read_text()
    assert "SUFeedURL" in content
    assert "releases.keri.host/appcast/v1/macos.json" in content


def test_macos_spec_does_not_set_public_ed_key():
    """Spec §3 — KERI is sole trust; Sparkle's signature verification stays OFF."""
    spec_path = Path("packaging/Locksmith.macos.spec")
    content = spec_path.read_text()
    assert "SUPublicEDKey" not in content


def test_macos_spec_sets_bundle_id():
    spec_path = Path("packaging/Locksmith.macos.spec")
    content = spec_path.read_text()
    assert "host.keri.locksmith" in content


def test_sign_libs_handles_sparkle_framework():
    sh = Path("scripts/signLibs.sh").read_text()
    assert "Sparkle.framework" in sh
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/update/test_macos_spec_has_sparkle.py -v`
Expected: FAIL (or skip if file not yet present from Phase 2; if so, this task creates the additions on top of the Phase 2 baseline).

- [ ] **Step 3: Edit `packaging/Locksmith.macos.spec`**

Append/merge into the existing `Analysis(...)` `datas=[]` entry — pointing at a Sparkle.framework checked into `packaging/macos/Sparkle.framework`:

```python
# At the top of the file:
import os
SPARKLE_FRAMEWORK = os.path.join(os.path.dirname(SPECPATH), 'macos', 'Sparkle.framework')

# In the existing Analysis(...) call, add to datas:
datas=[
    # ... existing entries from Phase 2 ...
    (SPARKLE_FRAMEWORK, 'Frameworks/Sparkle.framework'),
],
```

And in the `BUNDLE(...)` call's `info_plist={...}` dict, add:

```python
info_plist={
    # ... existing keys from Phase 2 ...
    'CFBundleIdentifier': 'host.keri.locksmith',
    'SUFeedURL': 'https://releases.keri.host/appcast/v1/macos.json',
    'SUEnableInstallerLauncherService': True,
    'SUEnableAutomaticChecks': False,   # we drive checks; not Sparkle
    'NSAppTransportSecurity': {
        'NSAllowsArbitraryLoads': False,
        'NSExceptionDomains': {},
    },
    # SUPublicEDKey intentionally OMITTED — Sparkle signature verification
    # disabled; KERI is the sole trust mechanism per spec §3.
},
```

- [ ] **Step 4: Edit `scripts/signLibs.sh`**

Add (preserving existing logic):

```bash
# Sign Sparkle.framework nested binaries (Sparkle ships multiple helper executables).
SPARKLE_FRAMEWORK="$APP_BUNDLE/Contents/Frameworks/Sparkle.framework"
if [ -d "$SPARKLE_FRAMEWORK" ]; then
    echo "[signLibs] codesigning Sparkle.framework helpers"
    # Sign each helper executable individually first, then the framework itself
    for helper in "$SPARKLE_FRAMEWORK/Versions/B/XPCServices/Downloader.xpc" \
                  "$SPARKLE_FRAMEWORK/Versions/B/XPCServices/Installer.xpc" \
                  "$SPARKLE_FRAMEWORK/Versions/B/Autoupdate" \
                  "$SPARKLE_FRAMEWORK/Versions/B/Updater.app"; do
        if [ -e "$helper" ]; then
            codesign --force --options runtime \
                     --sign "$DEVELOPER_ID_APP_CERT" \
                     --timestamp "$helper"
        fi
    done
    codesign --force --options runtime \
             --sign "$DEVELOPER_ID_APP_CERT" \
             --timestamp "$SPARKLE_FRAMEWORK"
fi
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/update/test_macos_spec_has_sparkle.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add packaging/Locksmith.macos.spec scripts/signLibs.sh tests/unit/update/test_macos_spec_has_sparkle.py
git commit -m "feat(packaging): embed Sparkle.framework + Info.plist (sig verif OFF)"
```

---

## Task 23: PyInstaller spec — bundle WinSparkle.dll on Windows

**Files:**
- Modify: `packaging/Locksmith.windows.spec`
- Test: `tests/unit/update/test_windows_spec_has_winsparkle.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/update/test_windows_spec_has_winsparkle.py
from pathlib import Path


def test_windows_spec_bundles_winsparkle_dll():
    spec = Path("packaging/Locksmith.windows.spec").read_text()
    assert "WinSparkle.dll" in spec


def test_windows_spec_has_appcast_constant():
    spec = Path("packaging/Locksmith.windows.spec").read_text()
    assert "releases.keri.host/appcast/v1/windows.json" in spec
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/update/test_windows_spec_has_winsparkle.py -v`
Expected: FAIL.

- [ ] **Step 3: Edit `packaging/Locksmith.windows.spec`**

In the `binaries=[]` list inside `Analysis(...)`, add:

```python
# WinSparkle bundled DLL (placed alongside Locksmith.exe at runtime).
# Source DLL is committed under packaging/windows/winsparkle/WinSparkle.dll
binaries=[
    # ... existing entries from Phase 3 ...
    (os.path.join('windows', 'winsparkle', 'WinSparkle.dll'), '.'),
],
```

And at the top of the spec (as documentation/constant):

```python
# Appcast URL configured at runtime by winsparkle_init.py:
#   https://releases.keri.host/appcast/v1/windows.json
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/update/test_windows_spec_has_winsparkle.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add packaging/Locksmith.windows.spec tests/unit/update/test_windows_spec_has_winsparkle.py
git commit -m "feat(packaging): bundle WinSparkle.dll in Windows spec"
```

---

## Task 24: Integration test — macOS full update cycle

**Files:**
- Create: `tests/integration/__init__.py` (if not present)
- Create: `tests/integration/test_full_update_cycle_macos.py`

This is a CI-only test that runs on `macos-latest` against a staging publisher AID + appcast.

- [ ] **Step 1: Write the integration test**

```python
# tests/integration/test_full_update_cycle_macos.py
"""End-to-end macOS update cycle (CI macos-latest only).

Flow:
  1. Build a v1.0.0 PyInstaller bundle using the macOS spec (uses Phase 2 helpers).
  2. Stand up a local HTTP server serving a test appcast advertising v1.0.1.
  3. Stand up a test publisher AID + witness pool (from tests/fixtures/update/).
  4. Launch the v1.0.0 binary, drive Sparkle's `SPUUpdaterController.checkForUpdates`.
  5. Block until install-on-quit completes.
  6. Assert the v1.0.1 binary is the running process after restart.
"""
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        sys.platform != "darwin",
        reason="macOS-only integration test",
    ),
]


@pytest.fixture(scope="module")
def staging_appcast_server(tmp_path_factory):
    """Local HTTP server serving the v1.0.1 appcast + DMG fixture."""
    from tests.fixtures.update.harness import StagingAppcastServer
    server = StagingAppcastServer(
        root=tmp_path_factory.mktemp("appcast"),
        version="1.0.1",
    )
    server.start()
    yield server
    server.stop()


@pytest.fixture(scope="module")
def v1_0_0_bundle(tmp_path_factory):
    """Build the v1.0.0 .app once for the module."""
    work = tmp_path_factory.mktemp("build")
    subprocess.run(
        [sys.executable, "-m", "PyInstaller",
         "--workpath", str(work / "build"),
         "--distpath", str(work / "dist"),
         "--noconfirm",
         "packaging/Locksmith.macos.spec"],
        check=True,
        env={**os.environ, "LOCKSMITH_VERSION": "1.0.0"},
    )
    app = work / "dist" / "Locksmith.app"
    assert app.exists()
    return app


def test_v1_0_0_updates_to_v1_0_1_via_sparkle(v1_0_0_bundle, staging_appcast_server):
    binary = v1_0_0_bundle / "Contents" / "MacOS" / "Locksmith"
    env = {
        **os.environ,
        "SUFeedURL": staging_appcast_server.feed_url,
        "LOCKSMITH_UPDATE_TEST_MODE": "1",
    }
    proc = subprocess.Popen([str(binary), "--check-for-updates-and-quit"], env=env)

    deadline = time.time() + 180  # 3-minute budget
    while time.time() < deadline:
        if proc.poll() is not None:
            break
        time.sleep(2)

    assert proc.returncode == 0, f"updater exited non-zero: {proc.returncode}"

    # Spawn the (now-updated) binary and ask its version
    out = subprocess.check_output([str(binary), "--version"], env=env, timeout=30)
    assert b"1.0.1" in out
```

- [ ] **Step 2: Run the test locally** (will fail unless on macOS with bundle infra in place)

Run: `pytest tests/integration/test_full_update_cycle_macos.py -v -m integration`
Expected: FAIL or SKIP. Acceptable in this phase — the test is gated on CI macos-latest.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/__init__.py tests/integration/test_full_update_cycle_macos.py
git commit -m "test(update): macOS full update-cycle integration test"
```

---

## Task 25: Integration test — Windows full update cycle

**Files:**
- Create: `tests/integration/test_full_update_cycle_windows.py`

- [ ] **Step 1: Write the integration test**

```python
# tests/integration/test_full_update_cycle_windows.py
"""End-to-end Windows update cycle (CI windows-latest only)."""
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        sys.platform != "win32",
        reason="Windows-only integration test",
    ),
]


@pytest.fixture(scope="module")
def staging_appcast_server(tmp_path_factory):
    from tests.fixtures.update.harness import StagingAppcastServer
    server = StagingAppcastServer(
        root=tmp_path_factory.mktemp("appcast"),
        version="1.0.1",
        platform="windows",
    )
    server.start()
    yield server
    server.stop()


@pytest.fixture(scope="module")
def v1_0_0_msi_install(tmp_path_factory):
    """Build the v1.0.0 MSI and install it silently into a per-user dir."""
    work = tmp_path_factory.mktemp("build")
    # Build the MSI using the Windows spec + WiX (see Phase 3 plan).
    subprocess.run(
        ["powershell", "-File", "scripts/build-windows.ps1",
         "-Version", "1.0.0",
         "-OutputDir", str(work / "dist")],
        check=True,
    )
    msi = work / "dist" / "Locksmith-1.0.0.msi"
    install_dir = work / "install"
    subprocess.run(
        ["msiexec", "/i", str(msi), "/qn",
         f"INSTALLDIR={install_dir}"],
        check=True,
    )
    return install_dir


def test_v1_0_0_updates_to_v1_0_1_via_winsparkle(v1_0_0_msi_install, staging_appcast_server):
    binary = v1_0_0_msi_install / "Locksmith.exe"
    env = {
        **os.environ,
        "LOCKSMITH_UPDATE_APPCAST_URL": staging_appcast_server.feed_url,
        "LOCKSMITH_UPDATE_TEST_MODE": "1",
    }
    proc = subprocess.Popen([str(binary), "--check-for-updates-and-quit"], env=env)

    deadline = time.time() + 180
    while time.time() < deadline:
        if proc.poll() is not None:
            break
        time.sleep(2)

    assert proc.returncode == 0

    out = subprocess.check_output([str(binary), "--version"], env=env, timeout=30)
    assert b"1.0.1" in out
```

- [ ] **Step 2: Run the test locally** (will be skipped on macOS)

Run: `pytest tests/integration/test_full_update_cycle_windows.py -v -m integration`
Expected: SKIP locally; runs on CI windows-latest.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_full_update_cycle_windows.py
git commit -m "test(update): Windows full update-cycle integration test"
```

---

## Task 26: Integration test — verification failure aborts install

**Files:**
- Create: `tests/integration/test_verification_failure_aborts_install.py`

- [ ] **Step 1: Write the integration test**

```python
# tests/integration/test_verification_failure_aborts_install.py
"""Feed a tampered artifact (correct appcast hash, wrong file contents);
verify install is aborted, log records the failure, app stays on old version.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def tampered_appcast_server(tmp_path_factory):
    from tests.fixtures.update.harness import StagingAppcastServer
    server = StagingAppcastServer(
        root=tmp_path_factory.mktemp("appcast"),
        version="1.0.1",
        tampered=True,             # serves binary whose SHA256 != appcast's claim
    )
    server.start()
    yield server
    server.stop()


@pytest.mark.skipif(sys.platform not in ("darwin", "win32"),
                    reason="requires macOS or Windows")
def test_tampered_artifact_aborts_install_and_logs_failure(
    tampered_appcast_server, tmp_path,
):
    from tests.fixtures.update.harness import build_v1_0_0_bundle
    binary = build_v1_0_0_bundle(tmp_path)

    env = {
        **os.environ,
        "LOCKSMITH_UPDATE_APPCAST_URL": tampered_appcast_server.feed_url,
        "LOCKSMITH_UPDATE_TEST_MODE": "1",
        "LOCKSMITH_LOG_DIR": str(tmp_path / "logs"),
    }
    proc = subprocess.Popen(
        [str(binary), "--check-for-updates-and-quit"],
        env=env,
    )

    deadline = time.time() + 120
    while time.time() < deadline:
        if proc.poll() is not None:
            break
        time.sleep(1)

    assert proc.returncode == 0   # exits cleanly even after refusing install

    # Binary should still report v1.0.0
    out = subprocess.check_output([str(binary), "--version"], env=env, timeout=30)
    assert b"1.0.0" in out

    # Verification log must record the failure
    log_path = Path(env["LOCKSMITH_LOG_DIR"]) / "verification.log"
    text = log_path.read_text()
    assert "verify_fail" in text
    assert "1.0.1" in text

    # Staged file must be gone
    staging = (
        Path.home() / "Library/Application Support/Locksmith/staging"
        if sys.platform == "darwin"
        else Path(os.environ["LOCALAPPDATA"]) / "Locksmith" / "staging"
    )
    if staging.exists():
        assert not list(staging.glob("Locksmith-1.0.1.*"))
```

- [ ] **Step 2: Run the test locally** (skipped unless on macOS/Windows)

Run: `pytest tests/integration/test_verification_failure_aborts_install.py -v -m integration`
Expected: SKIP locally; runs on CI matrix.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_verification_failure_aborts_install.py
git commit -m "test(update): verification failure aborts install + logs"
```

---

## Task 27: Add macOS-only PyObjC deps to `pyproject.toml`

**Files:**
- Modify: `pyproject.toml`
- Test: `tests/unit/update/test_pyproject_has_pyobjc.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/update/test_pyproject_has_pyobjc.py
import sys
from pathlib import Path

try:
    import tomllib                       # Python 3.11+
except ImportError:
    import tomli as tomllib              # type: ignore


def test_pyobjc_marker_present_for_darwin():
    pp = tomllib.loads(Path("pyproject.toml").read_text())
    deps = pp.get("project", {}).get("dependencies", [])
    project = pp.get("project", {})
    optional = project.get("optional-dependencies", {})

    # Either in main deps with marker or in optional-dependencies
    has_pyobjc = any(
        ("pyobjc-framework-Cocoa" in d or "pyobjc-framework-Sparkle" in d)
        and "sys_platform" in d
        for d in deps
    )
    has_optional = any(
        any("pyobjc-framework-Cocoa" in d or "pyobjc-framework-Sparkle" in d
            for d in lst)
        for lst in optional.values()
    )
    assert has_pyobjc or has_optional, "Need PyObjC Cocoa+Sparkle pinned for Darwin"


def test_pytest_qt_in_dev_dependencies():
    pp = tomllib.loads(Path("pyproject.toml").read_text())
    project = pp.get("project", {})
    optional = project.get("optional-dependencies", {})
    dev = optional.get("dev", []) + optional.get("test", [])
    assert any("pytest-qt" in d for d in dev), "pytest-qt required for UI tests"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/update/test_pyproject_has_pyobjc.py -v`
Expected: FAIL.

- [ ] **Step 3: Edit `pyproject.toml`**

Under `[project] dependencies`, add:

```toml
dependencies = [
    # ... existing ...
    'pyobjc-framework-Cocoa>=10.0; sys_platform == "darwin"',
    'pyobjc-framework-Sparkle>=10.0; sys_platform == "darwin"',
]
```

Under `[project.optional-dependencies] dev` (or `test`), add `pytest-qt`:

```toml
[project.optional-dependencies]
dev = [
    # ... existing ...
    "pytest-qt>=4.4",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/update/test_pyproject_has_pyobjc.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/unit/update/test_pyproject_has_pyobjc.py
git commit -m "feat(update): pin PyObjC Sparkle + pytest-qt deps"
```

---

## Task 28: Smoke-run the full UI test suite

- [ ] **Step 1: Run the entire new test suite**

```bash
pytest tests/unit/update tests/ui -v --tb=short
```

Expected: All unit + UI tests pass. (Integration tests are skipped here.)

- [ ] **Step 2: Run lint / static checks**

```bash
ruff check src/locksmith/update src/locksmith/ui/dialogs src/locksmith/ui/banners src/locksmith/ui/toasts src/locksmith/ui/settings
```

Expected: clean (or document any inherited style overrides).

- [ ] **Step 3: Verify no forbidden UX patterns introduced**

```bash
grep -RIn "QWebEngineView" src/locksmith/ui/dialogs && echo "FAIL: web view forbidden" || echo "OK: no QWebEngineView"
grep -RIn -i "install anyway\|force install\|override verification" src/locksmith/ && echo "FAIL: override affordance found" || echo "OK: no bypass affordances"
grep -RIn -i "🚀\|amazing release\|exciting update" src/locksmith/update src/locksmith/ui/dialogs && echo "FAIL: hype language" || echo "OK: tone is calm"
```

Expected: all three checks print OK.

- [ ] **Step 4: Commit**

```bash
git commit --allow-empty -m "test(update): full Phase 5 suite passes + tone/forbidden-UX guard"
```

---

## Self-Review

**1. Spec coverage check:**

| Spec section | Covered by tasks |
|--------------|------------------|
| §8.1 check cadence | Task 5 (UpdateScheduler) |
| §8.2 decision tree | Task 2 (UpdateDecision), Task 15 (routing) |
| §8.3 What's New modal | Task 10 |
| §8.3 no QWebEngineView | Task 10 (explicit test), Task 28 (grep guard) |
| §8.4 install-on-quit verifier hook | Task 7 (sparkle), Task 8 (winsparkle) |
| §8.5 first-launch consent | Task 9 |
| §8.6 Settings → Updates | Task 14, Task 19 (wiring) |
| §8.6 verification log | Task 13 |
| §8.7 forbidden UX | Task 28 (grep guards) |
| §9.2 verification-failed toast (no override) | Task 12 |
| §9 no install-anyway | Tasks 12, 13 (explicit tests), Task 28 |
| Sparkle signature verification OFF | Task 22 (no SUPublicEDKey) |
| WinSparkle signature verification OFF | Task 8 (`set_dsa_pub_pem(None)`) |
| KERI gate before install | Tasks 7, 8 (verifier callback) |
| Integration tests (mac + win + tampered) | Tasks 24, 25, 26 |
| PyObjC dep + pytest-qt | Task 27 |

All deliverables in the prompt's "Deliverables" list are addressed.

**2. Placeholder scan:** No "TBD", "implement later", or "similar to Task N" remain. All code blocks contain full code.

**3. Type consistency:**
- `UpdateDecision.evaluate(*, current_version, release)` used consistently in Tasks 2, 6, 15.
- `Release` dataclass field names match the spec §6.3 schema (`anchor_said`, `is_major`, `is_critical`, etc.) and are used identically in tests and impls.
- Bridge `verifier` callable signature `(artifact_path: str, release_info: dict) -> bool` is consistent across Sparkle and WinSparkle bridges (Tasks 7, 8) and the bootstrap (`apping.py`, Task 16).
- `VerificationLog` protocol (Task 13) matches Phase 4 contract.
- `UpdatePrefs` properties (`check_automatically`, `consent_seen`, `first_deferred_at`, `last_deferred_at`, `deferred_version`) defined in Task 3 are used identically in Tasks 4, 9, 10, 14.

**4. Cross-phase dependency notes** (called out for executors):
- `locksmith.update.log.VerificationLog` and `VerificationLogEntry` are imported lazily (Task 16 wraps in try/except; Task 13 uses Protocol). When Phase 4 ships, the executor must remove the try/except guard in `apping.py` and confirm the Protocol contract matches.
- `locksmith.update.verify.verify_artifact` is referenced via the `verifier` callable in the bridges. Bootstrap wiring (in `apping.py` or a future `update_init` module) must inject it; this plan stops short of importing it directly so unit tests don't require Phase 4.
- `locksmith.version.__version__` (Phase 2 deliverable) is read in Task 16; if not yet present, executor must add a placeholder.
- `packaging/Locksmith.macos.spec` and `packaging/Locksmith.windows.spec` baselines come from Phases 2 and 3 respectively; Tasks 22 and 23 only add the Sparkle/WinSparkle deltas.

Plan is complete and self-consistent.
