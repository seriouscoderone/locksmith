"""Tests for the sliding 24h / 7-day deferral logic (spec §8.3)."""
from datetime import datetime, timedelta, timezone

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
    # A fresh candidate with no prior deferral should prompt immediately.
    assert d.is_due_again() is True
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
    assert d.is_due_again() is True   # fresh prompt for 1.4.0


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


def test_record_deferral_resets_first_on_new_candidate():
    first = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    now = first + timedelta(days=2)
    state = Deferral.record_deferral(
        first_deferred_at=_ts(first),
        deferred_version="1.3.0",
        candidate_version="1.4.0",
        now=now,
    )
    assert state.first_deferred_at == _ts(now)
    assert state.deferred_version == "1.4.0"
