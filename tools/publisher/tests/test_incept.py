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
        "locksmith_publisher.incept.discover_witness_pool",
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
