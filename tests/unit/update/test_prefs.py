"""Tests for UpdatePrefs — QSettings-backed preferences wrapper."""
import pytest
from PySide6.QtCore import QCoreApplication, QSettings


@pytest.fixture(autouse=True)
def qsettings_in_memory(tmp_path):
    """Point QSettings at a temp ini so tests don't touch real user prefs."""
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


def test_deferred_version_persists_and_clears():
    from locksmith.update.prefs import UpdatePrefs
    p1 = UpdatePrefs()
    p1.deferred_version = "1.3.0"
    p2 = UpdatePrefs()
    assert p2.deferred_version == "1.3.0"
    p2.deferred_version = None
    p3 = UpdatePrefs()
    assert p3.deferred_version is None
