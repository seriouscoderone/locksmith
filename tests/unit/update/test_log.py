"""Tests for ``locksmith.update.log`` — append-only verification log."""
import pytest

from locksmith.update.errors import SchemaError
from locksmith.update.log import (
    VerificationLogEntry,
    append_entry,
    default_log_path,
    read_entries,
)


def test_default_log_path_per_platform():
    p = default_log_path()
    assert p.name == "verification.log"


def test_append_then_read(tmp_path):
    log = tmp_path / "verification.log"
    append_entry(
        log,
        VerificationLogEntry(
            ts="2026-05-28T12:00:00Z",
            outcome="ok",
            version="1.0.0",
            publisher_aid="EAaa",
            anchor_said="EHsh1",
            fields={"sha256": "abc"},
        ),
    )
    append_entry(
        log,
        VerificationLogEntry(
            ts="2026-05-28T13:00:00Z",
            outcome="hash_mismatch",
            version="1.0.1",
            publisher_aid="EAaa",
            anchor_said="EHsh2",
            fields={"reason": "tampered binary"},
        ),
    )
    entries = read_entries(log)
    assert len(entries) == 2
    assert entries[0].outcome == "ok"
    assert entries[1].outcome == "hash_mismatch"
    assert entries[1].fields["reason"] == "tampered binary"


def test_entries_returned_sorted_by_ts(tmp_path):
    log = tmp_path / "v.log"
    append_entry(
        log,
        VerificationLogEntry(
            ts="2026-05-28T13:00:00Z", outcome="ok", version="1.0.1",
            publisher_aid="E", anchor_said="E", fields={},
        ),
    )
    append_entry(
        log,
        VerificationLogEntry(
            ts="2026-05-28T12:00:00Z", outcome="ok", version="1.0.0",
            publisher_aid="E", anchor_said="E", fields={},
        ),
    )
    entries = read_entries(log)
    assert [e.version for e in entries] == ["1.0.0", "1.0.1"]


def test_format_is_key_eq_value_per_memory_rule(tmp_path):
    log = tmp_path / "v.log"
    append_entry(
        log,
        VerificationLogEntry(
            ts="2026-05-28T12:00:00Z", outcome="ok", version="1.0.0",
            publisher_aid="EAaa", anchor_said="EHsh", fields={"sha256": "abc"},
        ),
    )
    raw = log.read_text()
    assert "ts=2026-05-28T12:00:00Z" in raw
    assert "outcome=ok" in raw
    assert "version=1.0.0" in raw
    assert "sha256=abc" in raw


def test_malformed_line_raises_schema_error(tmp_path):
    log = tmp_path / "v.log"
    log.write_text("ts=2026 outcome=ok this-token-not-kv\n")
    with pytest.raises(SchemaError):
        read_entries(log)


def test_missing_log_returns_empty_list(tmp_path):
    assert read_entries(tmp_path / "missing.log") == []


def test_append_is_append_only(tmp_path):
    log = tmp_path / "v.log"
    append_entry(
        log,
        VerificationLogEntry(
            ts="2026-05-28T12:00:00Z", outcome="ok", version="1.0.0",
            publisher_aid="E", anchor_said="E", fields={},
        ),
    )
    first = log.read_text()
    append_entry(
        log,
        VerificationLogEntry(
            ts="2026-05-28T13:00:00Z", outcome="ok", version="1.0.1",
            publisher_aid="E", anchor_said="E", fields={},
        ),
    )
    second = log.read_text()
    assert second.startswith(first)
    assert len(second) > len(first)


def test_reserved_key_in_fields_raises(tmp_path):
    log = tmp_path / "v.log"
    with pytest.raises(SchemaError) as e:
        append_entry(
            log,
            VerificationLogEntry(
                ts="2026-05-28T12:00:00Z", outcome="ok", version="1.0.0",
                publisher_aid="E", anchor_said="E", fields={"ts": "overlap"},
            ),
        )
    assert "ts" in e.value.reason


def test_value_with_whitespace_is_quoted(tmp_path):
    log = tmp_path / "v.log"
    append_entry(
        log,
        VerificationLogEntry(
            ts="2026-05-28T12:00:00Z", outcome="ok", version="1.0.0",
            publisher_aid="E", anchor_said="E",
            fields={"reason": "two words"},
        ),
    )
    raw = log.read_text()
    # shlex.quote uses single quotes around the value.
    assert "reason='two words'" in raw

    entries = read_entries(log)
    assert entries[0].fields["reason"] == "two words"


def test_missing_required_field_in_log_raises(tmp_path):
    """Hand-written log missing required key raises SchemaError on read."""
    log = tmp_path / "v.log"
    log.write_text("ts=2026 outcome=ok version=1.0.0 publisher_aid=E\n")  # missing anchor_said
    with pytest.raises(SchemaError):
        read_entries(log)


# --- VerificationResult persistence (Release Verification dialog) -----------

def _result(**over):
    from locksmith.update.verify import VerificationResult
    base = dict(
        ok=True, version="0.2.10", platform="macos",
        publisher_aid="EHjWPRGoY9PV", anchor_said="EO9Oh-3r",
        artifact_sha256="e9cee447", artifact_size=63013340,
        witness_receipts=5, kel_tip_sn=7,
    )
    base.update(over)
    return VerificationResult(**base)


def test_record_then_load_roundtrip(tmp_path):
    from locksmith.update.log import (
        record_verification_result, load_last_verification_result,
    )
    log = tmp_path / "verification.log"
    record_verification_result(_result(), path=log, ts="2026-06-26T00:04:16+00:00")

    got = load_last_verification_result(log)
    assert got is not None
    assert got.ok is True
    assert got.version == "0.2.10"
    assert got.platform == "macos"
    assert got.publisher_aid == "EHjWPRGoY9PV"
    assert got.anchor_said == "EO9Oh-3r"
    assert got.artifact_sha256 == "e9cee447"
    assert got.artifact_size == 63013340
    assert got.witness_receipts == 5
    assert got.kel_tip_sn == 7


def test_load_returns_latest_ok(tmp_path):
    from locksmith.update.log import (
        record_verification_result, load_last_verification_result,
    )
    log = tmp_path / "verification.log"
    record_verification_result(_result(version="0.2.8", kel_tip_sn=6),
                               path=log, ts="2026-06-26T00:00:00+00:00")
    record_verification_result(_result(version="0.2.10", kel_tip_sn=7),
                               path=log, ts="2026-06-26T01:00:00+00:00")
    got = load_last_verification_result(log)
    assert got.version == "0.2.10" and got.kel_tip_sn == 7


def test_load_none_when_missing_or_no_ok(tmp_path):
    from locksmith.update.log import load_last_verification_result
    assert load_last_verification_result(tmp_path / "nope.log") is None
    # A failed-only log yields no result for the dialog.
    log = tmp_path / "v.log"
    append_entry(log, VerificationLogEntry(
        ts="2026", outcome="failed", version="0.2.10",
        publisher_aid="E", anchor_said="E",
    ))
    assert load_last_verification_result(log) is None
