"""Sanity check: the Phase 5 public API surface is wired into ``locksmith.update``."""


def test_update_package_exports_phase5_public_api():
    from locksmith.update import (
        UpdateController,
        UpdateScheduler,
        UpdatePrefs,
        Deferral,
    )
    assert UpdateController is not None
    assert UpdateScheduler is not None
    assert UpdatePrefs is not None
    assert Deferral is not None


def test_update_package_still_exports_phase4_modules():
    # Smoke check: Phase 4 verify pipeline still imports cleanly after
    # Phase 5 additions to __init__.py.
    from locksmith.update import verify, staging, log, errors, appcast
    assert verify is not None
    assert staging is not None
    assert log is not None
    assert errors is not None
    assert appcast is not None
