"""Update verification + orchestration subsystem for Locksmith.

Phase 4 (verification) public surface:

- ``verify.verify_artifact(...)``
- ``staging.stage_and_lock(...)``
- ``log.append_entry(...)`` / ``log.read_entries(...)``
- ``errors.UpdateError`` and subclasses

Phase 5 (orchestration) public surface:

- ``UpdateController``  — top-level entry; owns prefs + scheduler, routes
                          checks to the native Sparkle/WinSparkle framework
                          via an injected ``on_check`` callback
- ``UpdateScheduler``   — periodic check timer (30s initial + 4h cadence)
- ``UpdatePrefs``       — QSettings wrapper for user prefs
- ``Deferral``          — sliding 24h / 7-day cap logic
"""
from locksmith.update.controller import UpdateController
from locksmith.update.deferral import Deferral, DeferralState
from locksmith.update.prefs import UpdatePrefs
from locksmith.update.scheduler import UpdateScheduler

__all__ = [
    "UpdateController",
    "UpdateScheduler",
    "UpdatePrefs",
    "Deferral",
    "DeferralState",
]
