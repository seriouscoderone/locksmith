from pathlib import Path

from locksmith_publisher.incept import build_inception_event, InceptionResult, run_inception_ceremony


def test_build_inception_event_produces_2_of_3_multisig(fake_witness_pool, fake_devices):
    result = build_inception_event(
        signers=fake_devices,
        signer_quorum=2,
        witnesses=fake_witness_pool,
        toad=2,
    )
    assert isinstance(result, InceptionResult)
    assert result.signing_threshold == 2
    assert result.rotation_threshold == 2
    assert result.toad == 2
    assert len(result.signer_pubkeys) == 3
    assert len(result.next_digests) == 3
    assert result.aid_prefix.startswith("E")  # KERI self-addressing prefix
    assert result.serialized_event  # raw CESR / JSON bytes
    assert result.event_said


def test_build_inception_event_pre_rotates_next_keys(fake_witness_pool, fake_devices):
    result = build_inception_event(
        signers=fake_devices,
        signer_quorum=2,
        witnesses=fake_witness_pool,
        toad=2,
    )
    # Pre-rotation: next-key digests are not the same as current signer pubkeys.
    for digest in result.next_digests:
        assert digest not in result.signer_pubkeys


def test_run_inception_ceremony_dry_run_emits_anchor(tmp_path: Path, monkeypatch, fake_witness_pool):
    # Monkeypatch the witness discovery to avoid network in tests.
    monkeypatch.setattr(
        "locksmith_publisher.incept.default_witness_pool",
        lambda *_a, **_kw: fake_witness_pool,
    )
    # Monkeypatch the YubiKey opener to return fakes.
    from locksmith_publisher.yubikey import FakeYubiKeyDevice
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


import json

from locksmith_publisher.witness_client import Receipt


def test_run_inception_ceremony_submits_and_persists_receipts(tmp_path, monkeypatch, fake_witness_pool):
    monkeypatch.setattr(
        "locksmith_publisher.incept.default_witness_pool",
        lambda *_a, **_kw: fake_witness_pool,
    )
    from locksmith_publisher.yubikey import FakeYubiKeyDevice

    def fake_open(serial: str, slot: str):
        return FakeYubiKeyDevice(serial=serial, slot=slot)

    monkeypatch.setattr("locksmith_publisher.incept.open_real_device", fake_open)

    fake_receipts = [
        Receipt(witness_aid="Bw1", receipt_cesr="RCPT1"),
        Receipt(witness_aid="Bw2", receipt_cesr="RCPT2"),
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
        dry_run=False,
        submit=True,
        output_dir=tmp_path,
        yubikey_slots=["9c", "9c", "9c"],
    )

    icp_bytes = (tmp_path / "kel-events" / "icp-sn-0.cesr").read_bytes()
    assert b"-AAB" in icp_bytes or b"-AAC" in icp_bytes or len(icp_bytes) > 0
    receipts_path = tmp_path / "kel-events" / "icp-sn-0.receipts.json"
    assert receipts_path.exists()
    receipts_body = json.loads(receipts_path.read_text())
    assert len(receipts_body) == 2
    assert receipts_body[0]["witness_aid"] == "Bw1"
    summary = json.loads((tmp_path / "publisher-aid.json").read_text())
    assert summary["status"] == "live"
    assert summary["receipt_count"] == 2


def test_run_inception_ceremony_aborts_when_threshold_not_met(tmp_path, monkeypatch, fake_witness_pool):
    from locksmith_publisher.witness_client import WitnessThresholdNotMet
    from locksmith_publisher.yubikey import FakeYubiKeyDevice

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

    import pytest as _pytest
    with _pytest.raises(WitnessThresholdNotMet):
        run_inception_ceremony(
            witness_oobis=[w.oobi for w in fake_witness_pool],
            toad=2,
            quorum=2,
            signers=3,
            dry_run=False,
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
