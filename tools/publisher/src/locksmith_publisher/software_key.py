"""Software-backed signing key for publisher AID bootstrap.

When YubiKeys aren't available yet, the inception ceremony can run with
Ed25519 private keys persisted to disk as passphrase-encrypted PKCS#8 PEM.

THIS IS A BOOTSTRAP TOOL. The intended long-term storage is hardware-backed
(YubiKey PIV slot 9c). KERI's pre-rotation mechanism lets you rotate from
software keys to hardware keys later without changing the publisher AID
prefix — every previously-signed release stays verifiable.

Operational hygiene for software keys:
- Each key file MUST live in a distinct storage location (laptop disk,
  password manager attachment, encrypted USB drive in a safe, etc.)
- Each file MUST use a distinct passphrase
- The ceremony loads all 3 keys into memory at signing time — run the
  inception on a clean machine, then immediately distribute the encrypted
  files to their respective storage locations
- For release signing (Phase 4), implement the multi-machine partial-signing
  flow so the 3 keys are never decrypted into the same process again
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import (
    BestAvailableEncryption,
    Encoding,
    PrivateFormat,
    NoEncryption,
    load_pem_private_key,
)

from .yubikey import YubiKeyDevice, YubiKeyError


@dataclass(eq=False)
class SoftwareKeyDevice(YubiKeyDevice):
    """Persists an Ed25519 private key as a passphrase-encrypted PEM file.

    Drop-in replacement for YubiKeyDevice — implements the same abstract
    interface, but the "device" is just a file on disk that the operator
    is responsible for storing securely.

    Lifecycle:
    1. First call to `generate_signing_key()` creates a fresh keypair,
       encrypts the private key with `passphrase`, and writes to `key_path`.
    2. Subsequent calls to `sign()` load the encrypted PEM and decrypt
       with `passphrase`, then sign.
    3. If `key_path` already exists when `generate_signing_key()` is called,
       the existing key is loaded (not regenerated) — this lets the ceremony
       be re-run idempotently on existing keys.
    """

    key_path: Path = field(default=Path("/tmp/missing.enc.pem"))
    passphrase: bytes = field(default=b"")

    def __post_init__(self) -> None:
        if not isinstance(self.key_path, Path):
            self.key_path = Path(self.key_path)
        if isinstance(self.passphrase, str):
            self.passphrase = self.passphrase.encode("utf-8")

    def generate_signing_key(self) -> bytes:
        """Generate-or-load the Ed25519 key. Returns raw 32-byte public key."""
        if self.key_path.exists():
            private_key = self._load_existing()
        else:
            private_key = Ed25519PrivateKey.generate()
            self._save_encrypted(private_key)
        public_key = private_key.public_key()
        return public_key.public_bytes(
            encoding=Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    def sign(self, message: bytes) -> bytes:
        if not self.key_path.exists():
            raise YubiKeyError(
                f"software key file {self.key_path} does not exist; "
                f"call generate_signing_key() first to create it"
            )
        private_key = self._load_existing()
        return private_key.sign(message)

    def _save_encrypted(self, private_key: Ed25519PrivateKey) -> None:
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        encryption: object
        if self.passphrase:
            encryption = BestAvailableEncryption(self.passphrase)
        else:
            encryption = NoEncryption()
        pem = private_key.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.PKCS8,
            encryption_algorithm=encryption,
        )
        # 0600 permissions — owner read/write only
        self.key_path.write_bytes(pem)
        self.key_path.chmod(0o600)

    def _load_existing(self) -> Ed25519PrivateKey:
        pem = self.key_path.read_bytes()
        try:
            key = load_pem_private_key(
                pem,
                password=self.passphrase if self.passphrase else None,
            )
        except (ValueError, TypeError) as exc:
            raise YubiKeyError(
                f"failed to decrypt software key at {self.key_path}: "
                f"wrong passphrase or corrupted file ({exc})"
            ) from exc
        if not isinstance(key, Ed25519PrivateKey):
            raise YubiKeyError(
                f"key file at {self.key_path} is not Ed25519 "
                f"(found {type(key).__name__})"
            )
        return key


def open_software_devices(
    key_dir: Path,
    passphrases: list[bytes],
    *,
    slot: str = "sw",
) -> list[SoftwareKeyDevice]:
    """Open a directory full of software keys, one per passphrase.

    Files are named `key-1.enc.pem`, `key-2.enc.pem`, ... in order.
    Returns a list of N SoftwareKeyDevice instances corresponding to the
    N passphrases provided.
    """
    key_dir = Path(key_dir)
    devices: list[SoftwareKeyDevice] = []
    for i, passphrase in enumerate(passphrases, start=1):
        devices.append(
            SoftwareKeyDevice(
                serial=f"sw-{i}",
                slot=slot,
                key_path=key_dir / f"key-{i}.enc.pem",
                passphrase=passphrase,
            )
        )
    return devices
