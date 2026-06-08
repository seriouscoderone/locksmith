"""Tests for the publisher CLI's Phase 4 ``anchor`` subcommand.

Mocks the witness client and S3 client; exercises the real ``IxnAnchor``
build path against an ephemeral Hab.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from locksmith_publisher import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def publisher_keystore(monkeypatch):
    """Create an ephemeral publisher Habery; patch the CLI to use it.

    Real CLI invocations open the persistent Habery from the operator's
    keystore directory; tests instead inject a temp Hab.
    """
    from keri.app import habbing
    suffix = uuid.uuid4().hex[:8]
    name = f"pub_clitest_{suffix}"
    hby = habbing.Habery(name=name, base="", temp=True)
    hby.makeHab(
        name="publisher",
        transferable=True,
        isith="1",
        icount=1,
        nsith="1",
        ncount=1,
        wits=[],
        toad=0,
    )

    # Patch the CLI's keystore-open seam to return this in-memory Habery.
    def _fake_open(*, keystore_name, keystore_base, passphrase):
        return hby

    # close() is a no-op so the fixture teardown owns lifecycle.
    monkeypatch.setattr(
        "locksmith_publisher.cli._open_publisher_keystore", _fake_open
    )
    original_close = hby.close
    hby.close = lambda: None
    yield name, "", "test-passphrase"
    hby.close = original_close
    hby.close()


def test_anchor_command_dry_run_builds_event_and_persists_files(
    runner, publisher_keystore, tmp_path
):
    name, base, passcode = publisher_keystore

    # Create local "artifact" files so the CLI doesn't try S3.
    mac = tmp_path / "Locksmith-1.2.3.dmg"
    mac.write_bytes(b"MACOS_BYTES")
    win = tmp_path / "Locksmith-1.2.3.msi"
    win.write_bytes(b"WINDOWS_BYTES")

    out = tmp_path / "anchor_out"
    result = runner.invoke(
        cli.cli,
        [
            "anchor",
            "--version", "1.2.3",
            "--macos-artifact", str(mac),
            "--windows-artifact", str(win),
            "--key-source", "habery",
            "--keystore-name", name,
            "--keystore-base", base,
            "--passphrase", passcode,
            "--released-at", "2026-05-28T14:30:00Z",
            "--release-notes-said", "EHshTestSAID" + "X" * 32,
            "--output-dir", str(out),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output

    # Anchor file + metadata file should exist.
    assert (out / "release-anchor-1.2.3.cesr").exists()
    meta = json.loads((out / "release-anchor-1.2.3.json").read_text())
    assert meta["version"] == "1.2.3"
    assert meta["ilk"] == "ixn"
    assert meta["seal"]["release"]["v"] == "1.2.3"
    # No receipts file on dry-run.
    assert not (out / "release-anchor-1.2.3.receipts.cesr").exists()


def test_anchor_command_with_real_submit_calls_witness_client(
    runner, publisher_keystore, tmp_path
):
    name, base, passcode = publisher_keystore

    mac = tmp_path / "Locksmith-1.2.3.dmg"
    mac.write_bytes(b"MAC")
    win = tmp_path / "Locksmith-1.2.3.msi"
    win.write_bytes(b"WIN")

    out = tmp_path / "anchor_out"

    # Stub WitnessClient.submit_event + S3 calls.
    from locksmith_publisher.witness_client import Receipt
    fake_wc = MagicMock()
    fake_wc.submit_event.return_value = [
        Receipt(witness_url=f"https://wit{i}", cesr_bytes=b"RCPT" + str(i).encode())
        for i in range(3)
    ]
    fake_s3 = MagicMock()

    with patch("locksmith_publisher.cli.WitnessClient", return_value=fake_wc), \
         patch("locksmith_publisher.cli.S3.default", return_value=fake_s3):
        result = runner.invoke(
            cli.cli,
            [
                "anchor",
                "--version", "1.2.3",
                "--macos-artifact", str(mac),
                "--windows-artifact", str(win),
                "--key-source", "habery",
                "--keystore-name", name,
                "--keystore-base", base,
                "--passphrase", passcode,
                "--released-at", "2026-05-28T14:30:00Z",
                "--output-dir", str(out),
            ],
        )
    assert result.exit_code == 0, result.output
    # Witness submit and S3 puts were called.
    assert fake_wc.submit_event.called
    assert fake_s3.put_file.called
    # The release anchor event was uploaded.
    uploaded_keys = [c.kwargs["key"] for c in fake_s3.put_file.call_args_list]
    assert any("release-anchor-1.2.3.cesr" in k for k in uploaded_keys)


def test_anchor_command_fails_when_witnesses_threshold_not_met(
    runner, publisher_keystore, tmp_path
):
    name, base, passcode = publisher_keystore

    mac = tmp_path / "Locksmith-1.2.3.dmg"
    mac.write_bytes(b"M")
    win = tmp_path / "Locksmith-1.2.3.msi"
    win.write_bytes(b"W")

    from locksmith_publisher.witness_client import WitnessThresholdNotMet
    fake_wc = MagicMock()
    fake_wc.submit_event.side_effect = WitnessThresholdNotMet(collected=1, threshold=3)
    fake_s3 = MagicMock()

    with patch("locksmith_publisher.cli.WitnessClient", return_value=fake_wc), \
         patch("locksmith_publisher.cli.S3.default", return_value=fake_s3):
        result = runner.invoke(
            cli.cli,
            [
                "anchor",
                "--version", "1.2.3",
                "--macos-artifact", str(mac),
                "--windows-artifact", str(win),
                "--key-source", "habery",
                "--keystore-name", name,
                "--keystore-base", base,
                "--passphrase", passcode,
                "--released-at", "2026-05-28T14:30:00Z",
                "--output-dir", str(tmp_path / "out"),
            ],
        )
    assert result.exit_code != 0
    assert "threshold" in result.output.lower()
    # S3 should NOT have been called for the event because we failed first.
    assert not any("release-anchor" in (c.kwargs.get("key", "")) for c in fake_s3.put_file.call_args_list)


def test_anchor_command_pem_dry_run_with_synthetic_pem(runner, tmp_path):
    """End-to-end CLI test exercising the --key-source pem path.

    Generates a fresh Ed25519 PEM in a tmp keys-dir, seeds the state
    file with a synthetic publisher AID, and runs the anchor command
    in --dry-run mode (no witness submit, no S3 upload).
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        BestAvailableEncryption, Encoding, PrivateFormat,
    )
    from keri.core import coring
    from keri.core.eventing import incept

    # Synthesize PEM key.
    private = Ed25519PrivateKey.generate()
    pubkey_raw = private.public_key().public_bytes(
        encoding=Encoding.Raw, format=serialization.PublicFormat.Raw,
    )
    passphrase = b"pem-cli-test-passphrase"
    pem = private.private_bytes(
        encoding=Encoding.PEM, format=PrivateFormat.PKCS8,
        encryption_algorithm=BestAvailableEncryption(passphrase),
    )
    keys_dir = tmp_path / "keys" / "current"
    keys_dir.mkdir(parents=True)
    (keys_dir / "key-1.enc.pem").write_bytes(pem)

    # Build a synthetic icp event whose pre we'll use as the publisher AID.
    verfer = coring.Verfer(raw=pubkey_raw, code=coring.MtrDex.Ed25519)
    diger = coring.Diger(ser=verfer.qb64b)
    icp_serder = incept(
        keys=[verfer.qb64], isith="1",
        ndigs=[diger.qb64], nsith="1",
        wits=[], toad=0,
        code=coring.MtrDex.Blake3_256, kind="JSON",
    )

    # Artifacts.
    mac = tmp_path / "Locksmith-1.2.3.dmg"
    mac.write_bytes(b"MACOS_BYTES")
    win = tmp_path / "Locksmith-1.2.3.msi"
    win.write_bytes(b"WINDOWS_BYTES")

    out = tmp_path / "anchor_out"
    state_file = tmp_path / "state.json"

    result = runner.invoke(
        cli.cli,
        [
            "anchor",
            "--version", "1.2.3",
            "--macos-artifact", str(mac),
            "--windows-artifact", str(win),
            "--key-source", "pem",
            "--publisher-aid", icp_serder.pre,
            "--keys-dir", str(keys_dir),
            "--state-file", str(state_file),
            "--seed-aid", icp_serder.pre,
            "--seed-sn", "0",
            "--seed-digest", icp_serder.said,
            "--passphrase", passphrase.decode(),
            "--released-at", "2026-05-28T14:30:00Z",
            "--release-notes-said", "EHshTestSAID" + "X" * 32,
            "--output-dir", str(out),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output

    # Anchor + metadata files exist.
    assert (out / "release-anchor-1.2.3.cesr").exists()
    meta = json.loads((out / "release-anchor-1.2.3.json").read_text())
    assert meta["version"] == "1.2.3"
    assert meta["ilk"] == "ixn"
    # State file records the SEEDED tip (sn=0, the icp), NOT the
    # un-submitted ixn at sn=1. Dry-run must not advance past the seed
    # because no witness has actually confirmed the new event.
    state = json.loads(state_file.read_text())
    assert state["publisher_aid"] == icp_serder.pre
    assert state["current_sn"] == 0
    assert state["last_event_digest"] == icp_serder.said


def test_anchor_command_pem_seeds_from_bundled_anchor(runner, tmp_path, monkeypatch):
    """PEM mode: when no --seed-* flags and no local state, seed from the
    bundled publisher_anchor.json so the first ixn after inception works."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        BestAvailableEncryption, Encoding, PrivateFormat,
    )
    from keri.core import coring
    from keri.core.eventing import incept

    private = Ed25519PrivateKey.generate()
    pubkey_raw = private.public_key().public_bytes(
        encoding=Encoding.Raw, format=serialization.PublicFormat.Raw,
    )
    passphrase = b"bundle-seed-pp"
    pem = private.private_bytes(
        encoding=Encoding.PEM, format=PrivateFormat.PKCS8,
        encryption_algorithm=BestAvailableEncryption(passphrase),
    )
    keys_dir = tmp_path / "keys" / "current"
    keys_dir.mkdir(parents=True)
    (keys_dir / "key-1.enc.pem").write_bytes(pem)

    # Construct a real synthetic icp to get a valid AID + SAID pair the
    # SerderKERI validator will accept as `i` + `p` in the next ixn.
    verfer = coring.Verfer(raw=pubkey_raw, code=coring.MtrDex.Ed25519)
    diger = coring.Diger(ser=verfer.qb64b)
    icp_serder = incept(
        keys=[verfer.qb64], isith="1",
        ndigs=[diger.qb64], nsith="1",
        wits=[], toad=0,
        code=coring.MtrDex.Blake3_256, kind="JSON",
    )

    # Synthesize a bundled-anchor JSON pointing at this synthetic AID.
    fake_anchor = tmp_path / "publisher_anchor.json"
    fake_anchor.write_text(json.dumps({
        "publisher_aid": icp_serder.pre,
        "embedded_kel_hash": icp_serder.said,
        "embedded_kel_sn": 0,
        "witness_oobis": ["https://w1", "https://w2", "https://w3"],
    }))
    monkeypatch.setattr(
        "locksmith_publisher.cli._bundled_publisher_anchor_path",
        lambda: fake_anchor,
    )

    mac = tmp_path / "Locksmith-1.2.3.dmg"
    mac.write_bytes(b"MACOS")
    win = tmp_path / "Locksmith-1.2.3.msi"
    win.write_bytes(b"WIN")

    out = tmp_path / "anchor_out"
    state_file = tmp_path / "state.json"

    result = runner.invoke(
        cli.cli,
        [
            "anchor",
            "--version", "1.2.3",
            "--macos-artifact", str(mac),
            "--windows-artifact", str(win),
            "--keys-dir", str(keys_dir),
            "--state-file", str(state_file),
            "--passphrase", passphrase.decode(),
            "--released-at", "2026-05-28T14:30:00Z",
            "--output-dir", str(out),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output

    # State file records the seeded inception tip (sn=0). Dry-run did not
    # advance past it because no witness has confirmed the new event yet.
    state = json.loads(state_file.read_text())
    assert state["publisher_aid"] == icp_serder.pre
    assert state["current_sn"] == 0


def test_anchor_command_pem_mode_requires_publisher_aid(runner, tmp_path, monkeypatch):
    """If neither --publisher-aid nor a bundled anchor JSON is reachable, fail."""
    # Make the bundled-anchor lookup miss.
    monkeypatch.setattr(
        "locksmith_publisher.cli._bundled_publisher_anchor_path",
        lambda: None,
    )
    mac = tmp_path / "x.dmg"
    mac.write_bytes(b"x")
    win = tmp_path / "x.msi"
    win.write_bytes(b"x")
    keys_dir = tmp_path / "keys"
    keys_dir.mkdir()
    # Don't even create the PEM — we'll fail before loading it.
    result = runner.invoke(
        cli.cli,
        [
            "anchor",
            "--version", "1.2.3",
            "--macos-artifact", str(mac),
            "--windows-artifact", str(win),
            "--keys-dir", str(keys_dir),
            "--state-file", str(tmp_path / "state.json"),
            "--passphrase", "pw",
            "--released-at", "2026-05-28T14:30:00Z",
            "--output-dir", str(tmp_path / "out"),
            "--dry-run",
        ],
    )
    assert result.exit_code != 0
    assert "publisher aid" in result.output.lower()


def test_deprecated_sign_subcommand_exits_with_message(runner):
    result = runner.invoke(cli.cli, ["sign", "--version", "1.2.3"])
    assert result.exit_code == 2
    assert "anchor" in result.output.lower()


def test_deprecated_submit_subcommand_exits_with_message(runner):
    result = runner.invoke(cli.cli, ["submit", "--signed", "x"])
    assert result.exit_code == 2
    assert "anchor" in result.output.lower()
