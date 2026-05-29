import pytest

from locksmith_publisher.yubikey import (
    YubiKeyDevice,
    FakeYubiKeyDevice,
    YubiKeyError,
)


def test_fake_yubikey_generates_ed25519_keypair():
    dev = FakeYubiKeyDevice(serial="fake-1", slot="9c")
    public_key = dev.generate_signing_key()
    assert isinstance(public_key, bytes)
    assert len(public_key) == 32  # raw Ed25519 public key


def test_fake_yubikey_signs_with_generated_key():
    dev = FakeYubiKeyDevice(serial="fake-1", slot="9c")
    dev.generate_signing_key()
    sig = dev.sign(b"hello world")
    assert isinstance(sig, bytes)
    assert len(sig) == 64  # Ed25519 signature is 64 bytes


def test_fake_yubikey_signing_before_keygen_raises():
    dev = FakeYubiKeyDevice(serial="fake-1", slot="9c")
    with pytest.raises(YubiKeyError, match="no key generated"):
        dev.sign(b"hello")


def test_yubikey_device_is_abstract_interface():
    # Real YubiKeyDevice is abstract; cannot instantiate without a backend.
    with pytest.raises(TypeError):
        YubiKeyDevice(serial="real-1", slot="9c")  # type: ignore[abstract]
