import json
from pathlib import Path

import pytest

from locksmith_publisher.incept import (
    InceptionResult,
    _generate_persistent_next_keys,
    build_inception_event,
    run_inception_ceremony,
)
from locksmith_publisher.witness_client import Receipt
from locksmith_publisher.yubikey import FakeYubiKeyDevice


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_next_pubkeys(signers: list[FakeYubiKeyDevice]) -> list[bytes]:
    """Generate ephemeral next pubkeys from fake devices (one per signer)."""
    return [FakeYubiKeyDevice(serial=f"next-{d.serial}", slot=d.slot).generate_signing_key()
            for d in signers]


# ---------------------------------------------------------------------------
# build_inception_event — multisig (3 signers, quorum 2)
# ---------------------------------------------------------------------------

def test_build_inception_event_produces_2_of_3_multisig(fake_witness_pool, fake_devices):
    next_pks = _make_next_pubkeys(fake_devices)
    result = build_inception_event(
        signers=fake_devices,
        signer_quorum=2,
        witnesses=fake_witness_pool,
        toad=2,
        next_pubkeys=next_pks,
    )
    assert isinstance(result, InceptionResult)
    assert result.signing_threshold == 2
    assert result.rotation_threshold == 2
    assert result.toad == 2
    assert len(result.signer_pubkeys) == 3
    assert len(result.next_digests) == 3
    assert len(result.next_pubkeys) == 3
    assert result.aid_prefix.startswith("E")  # KERI self-addressing prefix
    assert result.serialized_event  # raw CESR / JSON bytes
    assert result.event_said


def test_build_inception_event_pre_rotates_next_keys(fake_witness_pool, fake_devices):
    next_pks = _make_next_pubkeys(fake_devices)
    result = build_inception_event(
        signers=fake_devices,
        signer_quorum=2,
        witnesses=fake_witness_pool,
        toad=2,
        next_pubkeys=next_pks,
    )
    # Pre-rotation: next pubkeys are distinct from current signer pubkeys.
    for npk in result.next_pubkeys:
        assert npk not in result.signer_pubkeys


# ---------------------------------------------------------------------------
# build_inception_event — single-sig (1 signer, quorum 1) — v1 default
# ---------------------------------------------------------------------------

def test_build_inception_event_single_sig(fake_witness_pool, fake_devices_single):
    next_pks = _make_next_pubkeys(fake_devices_single)
    result = build_inception_event(
        signers=fake_devices_single,
        signer_quorum=1,
        witnesses=fake_witness_pool,
        toad=2,
        next_pubkeys=next_pks,
    )
    assert isinstance(result, InceptionResult)
    assert result.signing_threshold == 1
    assert result.rotation_threshold == 1
    assert len(result.signer_pubkeys) == 1
    assert len(result.next_digests) == 1
    assert len(result.next_pubkeys) == 1
    assert result.aid_prefix.startswith("E")
    assert result.serialized_event
    assert result.event_said
    # Verify the inception event JSON has single-key arrays
    import json
    body = json.loads(result.serialized_event)
    assert len(body["k"]) == 1
    assert len(body["n"]) == 1
    assert body["kt"] == "1"
    assert body["nt"] == "1"


def test_build_inception_event_committed_digest_matches_next_verfer_qb64(
    fake_witness_pool, fake_devices_single
):
    """The digest in n: must equal Blake2b-256(next_verfer.qb64b).

    This is the KERI pre-rotation spec requirement: the rotation event must be
    signed with the next key, and the digest in the inception event must match.
    A failure here means rotation will NEVER work.
    """
    from keri.core import coring

    next_pks = _make_next_pubkeys(fake_devices_single)
    result = build_inception_event(
        signers=fake_devices_single,
        signer_quorum=1,
        witnesses=fake_witness_pool,
        toad=2,
        next_pubkeys=next_pks,
    )

    # Re-derive the expected digest independently.
    next_verfer = coring.Verfer(raw=next_pks[0], code=coring.MtrDex.Ed25519)
    expected_diger = coring.Diger(ser=next_verfer.qb64b)

    # Check the raw digest in the result.
    assert result.next_digests[0] == expected_diger.raw, (
        "Pre-rotation digest does not match Blake2b-256(next_verfer.qb64b) — "
        "rotation would be impossible with this inception event."
    )

    # Also verify against the n: field in the serialized event.
    body = json.loads(result.serialized_event)
    assert body["n"][0] == expected_diger.qb64, (
        f"n:[0] in serialized event ({body['n'][0]}) does not match "
        f"expected digest ({expected_diger.qb64})"
    )


# ---------------------------------------------------------------------------
# run_inception_ceremony — dry-run with 3 signers (backwards compat)
# ---------------------------------------------------------------------------

def test_run_inception_ceremony_dry_run_emits_anchor(tmp_path: Path, monkeypatch, fake_witness_pool):
    # Monkeypatch the witness discovery to avoid network in tests.
    monkeypatch.setattr(
        "locksmith_publisher.incept.default_witness_pool",
        lambda *_a, **_kw: fake_witness_pool,
    )
    # Monkeypatch the YubiKey opener to return fakes.
    counter = {"i": 0}

    def fake_open(serial: str, slot: str):
        counter["i"] += 1
        return FakeYubiKeyDevice(serial=serial, slot=slot)

    monkeypatch.setattr("locksmith_publisher.incept.open_real_device", fake_open)

    run_inception_ceremony(
        witness_oobis=[w.oobi for w in fake_witness_pool],
        toad=2,
        quorum=2,
        signers=3,
        dry_run=True,
        output_dir=tmp_path,
        yubikey_slots=["9c", "9c", "9c"],
    )

    assert (tmp_path / "publisher_anchor.json").exists()
    assert (tmp_path / "publisher-aid.json").exists()
    assert (tmp_path / "kel-events" / "icp-sn-0.cesr").exists()


# ---------------------------------------------------------------------------
# run_inception_ceremony — software-key path, single-sig (new default)
# ---------------------------------------------------------------------------

def test_run_inception_ceremony_software_keys_single_sig_persists_current_and_next(
    tmp_path: Path, monkeypatch, fake_witness_pool
):
    """Single-sig software-key ceremony creates current and next key files."""
    monkeypatch.setattr(
        "locksmith_publisher.incept.default_witness_pool",
        lambda *_a, **_kw: fake_witness_pool,
    )
    sw_dir = tmp_path / "keys"
    passphrase = b"test-passphrase-abc123!"

    run_inception_ceremony(
        witness_oobis=[w.oobi for w in fake_witness_pool],
        toad=2,
        quorum=1,
        signers=1,
        dry_run=True,
        output_dir=tmp_path / "output",
        yubikey_slots=["sw"],
        software_key_dir=sw_dir,
        software_passphrases=[passphrase],
    )

    assert (sw_dir / "current" / "key-1.enc.pem").exists(), "current key not created"
    assert (sw_dir / "next" / "key-1.enc.pem").exists(), "next key not created"
    # Both files should have restrictive permissions.
    assert (sw_dir / "current" / "key-1.enc.pem").stat().st_mode & 0o777 == 0o600
    assert (sw_dir / "next" / "key-1.enc.pem").stat().st_mode & 0o777 == 0o600


def test_run_inception_ceremony_software_keys_next_key_digest_verifiable(
    tmp_path: Path, monkeypatch, fake_witness_pool
):
    """Load the persisted next key and verify its digest matches n:[0] in the ICP event.

    This is the rotation-feasibility proof: if the check passes, the AID CAN be
    rotated later using the stored next key.
    """
    from keri.core import coring
    from locksmith_publisher.software_key import SoftwareKeyDevice

    monkeypatch.setattr(
        "locksmith_publisher.incept.default_witness_pool",
        lambda *_a, **_kw: fake_witness_pool,
    )
    sw_dir = tmp_path / "keys"
    passphrase = b"test-passphrase-abc123!"
    output_dir = tmp_path / "output"

    run_inception_ceremony(
        witness_oobis=[w.oobi for w in fake_witness_pool],
        toad=2,
        quorum=1,
        signers=1,
        dry_run=True,
        output_dir=output_dir,
        yubikey_slots=["sw"],
        software_key_dir=sw_dir,
        software_passphrases=[passphrase],
    )

    # Read the n: field from the serialized inception event.
    icp_bytes = (output_dir / "kel-events" / "icp-sn-0.cesr").read_bytes()
    icp_body = json.loads(icp_bytes)
    committed_digest_qb64 = icp_body["n"][0]

    # Load the persisted next key and derive its public key.
    next_device = SoftwareKeyDevice(
        serial="sw-1",
        slot="sw",
        key_path=sw_dir / "next" / "key-1.enc.pem",
        passphrase=passphrase,
    )
    next_pubkey_raw = next_device.generate_signing_key()

    # Re-derive the expected digest.
    next_verfer = coring.Verfer(raw=next_pubkey_raw, code=coring.MtrDex.Ed25519)
    expected_diger = coring.Diger(ser=next_verfer.qb64b)

    assert expected_diger.qb64 == committed_digest_qb64, (
        f"Rotation feasibility FAILED: committed digest {committed_digest_qb64!r} "
        f"does not match Blake2b-256(loaded_next_verfer.qb64b) = {expected_diger.qb64!r}. "
        "The AID cannot be rotated with the stored next-key file."
    )


# ---------------------------------------------------------------------------
# run_inception_ceremony — submit + receipt persistence
# ---------------------------------------------------------------------------

def test_run_inception_ceremony_submits_and_persists_receipts(tmp_path, monkeypatch, fake_witness_pool):
    monkeypatch.setattr(
        "locksmith_publisher.incept.default_witness_pool",
        lambda *_a, **_kw: fake_witness_pool,
    )

    def fake_open(serial: str, slot: str):
        return FakeYubiKeyDevice(serial=serial, slot=slot)

    monkeypatch.setattr("locksmith_publisher.incept.open_real_device", fake_open)

    fake_receipts = [
        Receipt(witness_url="https://witness.keri.host", cesr_bytes=b"-FAB-RCPT1"),
        Receipt(witness_url="https://witness.legitim.us", cesr_bytes=b"-FAB-RCPT2"),
    ]

    class FakeWitnessClient:
        def __init__(self, witness_urls, threshold, **_kw):
            self.witness_urls = witness_urls
            self.threshold = threshold
            self.submitted: bytes | None = None

        def submit_event(self, cesr_bytes: bytes):
            self.submitted = cesr_bytes
            return list(fake_receipts)

    monkeypatch.setattr("locksmith_publisher.incept.WitnessClient", FakeWitnessClient)

    run_inception_ceremony(
        witness_oobis=[w.oobi for w in fake_witness_pool],
        toad=2,
        quorum=2,
        signers=3,
        dry_run=True,   # dry_run controls device backend; submit controls event submission
        submit=True,
        output_dir=tmp_path,
        yubikey_slots=["9c", "9c", "9c"],
    )

    icp_bytes = (tmp_path / "kel-events" / "icp-sn-0.cesr").read_bytes()
    assert b"-AAB" in icp_bytes or b"-AAC" in icp_bytes or len(icp_bytes) > 0
    # CESR receipts persisted as raw bytes
    receipts_cesr_path = tmp_path / "kel-events" / "icp-sn-0.receipts.cesr"
    assert receipts_cesr_path.exists()
    assert receipts_cesr_path.read_bytes() == b"-FAB-RCPT1-FAB-RCPT2"
    # JSON index records which witnesses contributed
    receipts_index_path = tmp_path / "kel-events" / "icp-sn-0.receipts.json"
    assert receipts_index_path.exists()
    index = json.loads(receipts_index_path.read_text())
    assert index["count"] == 2
    assert index["witnesses"] == ["https://witness.keri.host", "https://witness.legitim.us"]
    assert index["receipts_cesr_file"] == "icp-sn-0.receipts.cesr"
    summary = json.loads((tmp_path / "publisher-aid.json").read_text())
    assert summary["status"] == "live"
    assert summary["receipt_count"] == 2


def test_run_inception_ceremony_aborts_when_threshold_not_met(tmp_path, monkeypatch, fake_witness_pool):
    from locksmith_publisher.witness_client import WitnessThresholdNotMet

    monkeypatch.setattr(
        "locksmith_publisher.incept.default_witness_pool",
        lambda *_a, **_kw: fake_witness_pool,
    )
    monkeypatch.setattr(
        "locksmith_publisher.incept.open_real_device",
        lambda serial, slot: FakeYubiKeyDevice(serial=serial, slot=slot),
    )

    class FailingWitnessClient:
        def __init__(self, witness_urls, threshold, **_kw):
            pass

        def submit_event(self, cesr_bytes):
            raise WitnessThresholdNotMet(collected=1, threshold=2)

    monkeypatch.setattr("locksmith_publisher.incept.WitnessClient", FailingWitnessClient)

    with pytest.raises(WitnessThresholdNotMet):
        run_inception_ceremony(
            witness_oobis=[w.oobi for w in fake_witness_pool],
            toad=2,
            quorum=2,
            signers=3,
            dry_run=True,   # dry_run controls device backend; submit controls event submission
            submit=True,
            output_dir=tmp_path,
            yubikey_slots=["9c", "9c", "9c"],
        )
    summary_path = tmp_path / "publisher-aid.json"
    if summary_path.exists():
        body = json.loads(summary_path.read_text())
        assert body.get("status") != "live"


def test_run_inception_ceremony_dry_run_does_not_submit(tmp_path, monkeypatch, fake_witness_pool):
    """Dry-run mode keeps the existing behavior: no signing, no submission."""
    monkeypatch.setattr(
        "locksmith_publisher.incept.default_witness_pool",
        lambda *_a, **_kw: fake_witness_pool,
    )
    called = {"submit": False}

    class TrackingWitnessClient:
        def __init__(self, *_a, **_kw):
            pass

        def submit_event(self, cesr_bytes):
            called["submit"] = True
            return []

    monkeypatch.setattr("locksmith_publisher.incept.WitnessClient", TrackingWitnessClient)

    run_inception_ceremony(
        witness_oobis=[w.oobi for w in fake_witness_pool],
        toad=2,
        quorum=2,
        signers=3,
        dry_run=True,
        submit=False,
        output_dir=tmp_path,
        yubikey_slots=["9c", "9c", "9c"],
    )
    assert called["submit"] is False
    assert not (tmp_path / "kel-events" / "icp-sn-0.receipts.json").exists()
