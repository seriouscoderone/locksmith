"""Tests for the spec §8.2 update decision tree."""
from locksmith.update.decision import (
    Release, UpdateAction, UpdateDecision,
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
    assert decision.release is None


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


def test_decision_carries_release_when_update_available():
    rel = _release(version="1.3.0")
    decision = UpdateDecision.evaluate(current_version="1.2.0", release=rel)
    assert decision.release is rel
