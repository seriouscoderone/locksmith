"""Tests for the SoftwareKeyDevice persistence + encryption."""
from pathlib import Path

import pytest

from locksmith_publisher.software_key import (
    SoftwareKeyDevice,
    open_software_devices,
)
from locksmith_publisher.yubikey import YubiKeyError


def test_software_key_generates_and_persists(tmp_path: Path):
    dev = SoftwareKeyDevice(
        serial="sw-1",
        slot="sw",
        key_path=tmp_path / "key-1.enc.pem",
        passphrase=b"correct horse battery staple",
    )
    pub = dev.generate_signing_key()
    assert isinstance(pub, bytes)
    assert len(pub) == 32  # raw Ed25519 pubkey
    assert (tmp_path / "key-1.enc.pem").exists()
    # File is owner-only-readable
    mode = (tmp_path / "key-1.enc.pem").stat().st_mode & 0o777
    assert mode == 0o600


def test_software_key_signs_after_generate(tmp_path: Path):
    dev = SoftwareKeyDevice(
        serial="sw-1",
        slot="sw",
        key_path=tmp_path / "key-1.enc.pem",
        passphrase=b"test-passphrase",
    )
    dev.generate_signing_key()
    sig = dev.sign(b"hello, world")
    assert isinstance(sig, bytes)
    assert len(sig) == 64  # Ed25519 signature is 64 bytes


def test_software_key_idempotent_on_existing_file(tmp_path: Path):
    """If the key file already exists, generate_signing_key() loads it."""
    key_path = tmp_path / "key-1.enc.pem"
    dev1 = SoftwareKeyDevice(
        serial="sw-1", slot="sw", key_path=key_path, passphrase=b"pw1",
    )
    pub1 = dev1.generate_signing_key()

    # New device instance with the same path + passphrase — loads existing key.
    dev2 = SoftwareKeyDevice(
        serial="sw-1", slot="sw", key_path=key_path, passphrase=b"pw1",
    )
    pub2 = dev2.generate_signing_key()
    assert pub1 == pub2  # Same key reloaded


def test_software_key_sign_without_generate_raises(tmp_path: Path):
    dev = SoftwareKeyDevice(
        serial="sw-1", slot="sw",
        key_path=tmp_path / "missing.enc.pem",
        passphrase=b"pw",
    )
    with pytest.raises(YubiKeyError, match="does not exist"):
        dev.sign(b"hello")


def test_software_key_wrong_passphrase_raises(tmp_path: Path):
    key_path = tmp_path / "key-1.enc.pem"
    dev1 = SoftwareKeyDevice(
        serial="sw-1", slot="sw", key_path=key_path, passphrase=b"correct",
    )
    dev1.generate_signing_key()

    dev2 = SoftwareKeyDevice(
        serial="sw-1", slot="sw", key_path=key_path, passphrase=b"wrong",
    )
    with pytest.raises(YubiKeyError, match="wrong passphrase"):
        dev2.sign(b"hello")


def test_software_key_signatures_verify_against_pubkey(tmp_path: Path):
    """End-to-end: sign with software key, verify with the returned pubkey."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    dev = SoftwareKeyDevice(
        serial="sw-1", slot="sw",
        key_path=tmp_path / "key-1.enc.pem",
        passphrase=b"pw",
    )
    pub_raw = dev.generate_signing_key()
    pub = Ed25519PublicKey.from_public_bytes(pub_raw)

    msg = b"the message to sign"
    sig = dev.sign(msg)
    pub.verify(sig, msg)  # raises on failure; no exception means valid


def test_open_software_devices_returns_three(tmp_path: Path):
    devs = open_software_devices(tmp_path, [b"pw1", b"pw2", b"pw3"])
    assert len(devs) == 3
    assert devs[0].key_path == tmp_path / "key-1.enc.pem"
    assert devs[1].key_path == tmp_path / "key-2.enc.pem"
    assert devs[2].key_path == tmp_path / "key-3.enc.pem"
    for dev in devs:
        dev.generate_signing_key()
    # All three files exist and are distinct
    assert {(tmp_path / f"key-{i}.enc.pem").exists() for i in (1, 2, 3)} == {True}
    pubs = [d.generate_signing_key() for d in devs]
    assert len(set(pubs)) == 3  # Three distinct keys
