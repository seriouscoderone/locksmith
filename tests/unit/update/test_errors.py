"""Tests for the typed exception hierarchy in ``locksmith.update.errors``."""
import pytest

from locksmith.update.errors import (
    DowngradeError,
    HashMismatchError,
    NetworkError,
    RotationMismatchError,
    SchemaError,
    SignatureError,
    StagingError,
    StaleAppcastError,
    UpdateError,
    WitnessDuplicityError,
    WitnessThresholdError,
)


def test_all_errors_inherit_from_update_error():
    assert issubclass(SignatureError, UpdateError)
    assert issubclass(HashMismatchError, UpdateError)
    assert issubclass(WitnessThresholdError, UpdateError)
    assert issubclass(StaleAppcastError, UpdateError)
    assert issubclass(DowngradeError, UpdateError)
    assert issubclass(RotationMismatchError, UpdateError)
    assert issubclass(WitnessDuplicityError, UpdateError)
    assert issubclass(NetworkError, UpdateError)
    assert issubclass(SchemaError, UpdateError)
    assert issubclass(StagingError, UpdateError)


def test_exit_codes_match_spec():
    assert SignatureError.exit_code == 10
    assert HashMismatchError.exit_code == 11
    assert WitnessThresholdError.exit_code == 12
    assert StaleAppcastError.exit_code == 13
    assert DowngradeError.exit_code == 13
    assert NetworkError.exit_code == 14
    assert RotationMismatchError.exit_code == 10
    assert WitnessDuplicityError.exit_code == 10
    assert SchemaError.exit_code == 10
    assert StagingError.exit_code == 10


def test_error_carries_log_fields():
    err = HashMismatchError(
        reason="expected abc, got def",
        log_fields={"expected_sha256": "abc", "actual_sha256": "def"},
    )
    assert err.reason == "expected abc, got def"
    assert err.log_fields["expected_sha256"] == "abc"
    assert err.log_fields["actual_sha256"] == "def"
    assert "expected abc" in str(err)


def test_error_without_log_fields_defaults_to_empty():
    err = NetworkError("connection refused")
    assert err.log_fields == {}


def test_base_update_error_exit_code_is_one():
    """Custom subclasses without an explicit exit_code fall back to UpdateError's default."""
    assert UpdateError.exit_code == 1
