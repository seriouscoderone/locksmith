"""YubiKey PIV signing wrapper.

Real YubiKey access uses `python-fido2` / `yubikit`. This module exposes an
abstract `YubiKeyDevice` interface so unit tests can swap in `FakeYubiKeyDevice`
without touching real hardware.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization


class YubiKeyError(RuntimeError):
    """Raised on YubiKey backend errors."""


@dataclass(eq=False)
class YubiKeyDevice(abc.ABC):
    """Abstract device handle. Subclasses provide a hardware or fake backend."""

    serial: str
    slot: str  # PIV slot, e.g. "9c" (Digital Signature)

    @abc.abstractmethod
    def generate_signing_key(self) -> bytes:
        """Generate a new Ed25519 key in the PIV slot. Returns raw 32-byte public key."""

    @abc.abstractmethod
    def sign(self, message: bytes) -> bytes:
        """Sign `message` and return raw 64-byte Ed25519 signature."""


class FakeYubiKeyDevice(YubiKeyDevice):
    """In-process fake used by tests and dry-run mode."""

    def __init__(self, serial: str, slot: str) -> None:
        super().__init__(serial=serial, slot=slot)
        self._private: Ed25519PrivateKey | None = None
        self._public: Ed25519PublicKey | None = None

    def generate_signing_key(self) -> bytes:
        self._private = Ed25519PrivateKey.generate()
        self._public = self._private.public_key()
        return self._public.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    def sign(self, message: bytes) -> bytes:
        if self._private is None:
            raise YubiKeyError("no key generated yet")
        return self._private.sign(message)


def open_real_device(serial: str, slot: str) -> YubiKeyDevice:
    """Open a real YubiKey via python-fido2 / yubikit.

    Stubbed in Phase 1 — the inception ceremony runs in --dry-run mode against
    FakeYubiKeyDevice on developer workstations during development. Production
    inception calls this with real device serials; the implementation is filled
    in by Phase 4 alongside the release signing flow.
    """
    raise YubiKeyError(
        f"real YubiKey backend not implemented in Phase 1 (serial={serial}, slot={slot}). "
        "Use FakeYubiKeyDevice or --dry-run during Phase 1."
    )
