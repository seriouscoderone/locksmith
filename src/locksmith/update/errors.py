"""Typed exception hierarchy for the in-app update verifier.

Each error type maps to a verifier-CLI exit code (see ``--verify-update``).
Every error carries ``log_fields`` — a dict of structured key/value pairs
written to the verification log in ``key=value`` form per
``[[feedback-testing-automated]]``.
"""
from __future__ import annotations

from typing import Any, Mapping


class UpdateError(Exception):
    """Base class for every verifier-rejected update.

    Subclasses set ``exit_code`` (used by the standalone CLI) and may populate
    ``log_fields`` for structured logging.
    """

    exit_code: int = 1

    def __init__(self, reason: str, log_fields: Mapping[str, Any] | None = None):
        super().__init__(reason)
        self.reason = reason
        self.log_fields: dict[str, Any] = dict(log_fields or {})

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.reason


class SignatureError(UpdateError):
    """The KEL event signature does not verify against the current key state."""

    exit_code = 10


class HashMismatchError(UpdateError):
    """The downloaded artifact SHA256 does not match the anchored seal."""

    exit_code = 11


class WitnessThresholdError(UpdateError):
    """Fewer than ``toad`` valid witness receipts attached to an event."""

    exit_code = 12


class StaleAppcastError(UpdateError):
    """Appcast points at a version older than the current KEL tip."""

    exit_code = 13


class DowngradeError(UpdateError):
    """An older release is being offered as a newer one (replay)."""

    exit_code = 13


class RotationMismatchError(UpdateError):
    """A ``rot`` event violates the pre-rotation commitment in the prior event."""

    exit_code = 10


class WitnessDuplicityError(UpdateError):
    """Witnesses returned divergent key state for the publisher AID."""

    exit_code = 10


class SchemaError(UpdateError):
    """Appcast or KEL stream did not conform to its schema."""

    exit_code = 10


class StagingError(UpdateError):
    """Staging-dir permissions, lock acquisition, or re-hash failed."""

    exit_code = 10


class NetworkError(UpdateError):
    """Could not reach the appcast, KEL, or witness pool."""

    exit_code = 14
