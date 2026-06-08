"""Unit tests for ``locksmith_publisher.signing_context``.

Exercises ``PemFileSigningContext`` end-to-end using synthetic PEM files
generated in-test (NEVER the real production PEM). Verifies:

* PEM load + signature path produces a SerderKERI-parseable ixn event
* SAID, sn, and prior-digest plumbing matches the cached KEL tip
* State file is updated after each build
* Mismatched publisher_aid in the state file is rejected
* Bundled-anchor seeding works
* Witness fallback seeding works (with a mocked WitnessClient.query_state)
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    BestAvailableEncryption,
    Encoding,
    PrivateFormat,
)
from keri.core import coring, serdering
from keri.core.eventing import incept

from locksmith_publisher.signing_context import (
    HabSigningContext,
    PemFileSigningContext,
    PublisherStateFile,
    derive_publisher_verfer_qb64,
)


@pytest.fixture
def synthetic_pem(tmp_path: Path) -> tuple[Path, bytes, bytes]:
    """Generate an Ed25519 keypair, persist the private half as encrypted PEM.

    Returns ``(key_dir, raw_pubkey, passphrase)``.
    """
    private = Ed25519PrivateKey.generate()
    public = private.public_key()
    raw_pub = public.public_bytes(
        encoding=Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    passphrase = b"correct-horse-battery"
    pem = private.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=BestAvailableEncryption(passphrase),
    )
    key_dir = tmp_path / "keys" / "current"
    key_dir.mkdir(parents=True)
    key_path = key_dir / "key-1.enc.pem"
    key_path.write_bytes(pem)
    key_path.chmod(0o600)
    return key_dir, raw_pub, passphrase


def _make_synthetic_publisher_icp(raw_pubkey: bytes) -> serdering.SerderKERI:
    """Build an icp event with the given Ed25519 pubkey as the controller.

    Returns the parsed SerderKERI so the test can grab the AID prefix +
    SAID and seed the PEM context's state file accordingly. (Note: we
    don't sign or commit; the test only needs the AID + SAID for
    seeding purposes.)
    """
    verfer = coring.Verfer(raw=raw_pubkey, code=coring.MtrDex.Ed25519)
    # Next-key digest: per Phase 1, Blake2b-256 of the qb64-encoded next
    # Verfer. For the unit test we just reuse the same pubkey — the
    # rotation chain isn't exercised here.
    next_verfer = coring.Verfer(raw=raw_pubkey, code=coring.MtrDex.Ed25519)
    diger = coring.Diger(ser=next_verfer.qb64b)
    return incept(
        keys=[verfer.qb64],
        isith="1",
        ndigs=[diger.qb64],
        nsith="1",
        wits=[],
        toad=0,
        code=coring.MtrDex.Blake3_256,
        kind="JSON",
    )


def _release_seal_fixture() -> dict:
    return {
        "release": {
            "v": "1.2.3",
            "channel": "stable",
            "released_at": "2026-05-28T14:30:00Z",
            "is_major": False,
            "is_critical": False,
            "previous_version": None,
            "minimum_system_versions": {"macos": "13.0", "windows": "10.0.19041"},
            "artifacts": [
                {
                    "platform": "macos",
                    "filename": "Locksmith-1.2.3.dmg",
                    "sha256": "a" * 64,
                    "size": 1234,
                }
            ],
            "release_notes_said": "EHshTestSAID" + "X" * 32,
        }
    }


# ---------------------------------------------------------------------------
# PublisherStateFile basics
# ---------------------------------------------------------------------------


def test_state_file_round_trip(tmp_path: Path):
    p = tmp_path / "state.json"
    s = PublisherStateFile(
        path=p,
        publisher_aid="EAAA",
        current_sn=3,
        last_event_digest="EHshXYZ",
    )
    s.save()
    loaded = PublisherStateFile.load(p)
    assert loaded.publisher_aid == "EAAA"
    assert loaded.current_sn == 3
    assert loaded.last_event_digest == "EHshXYZ"
    assert loaded.has_tip is True


def test_state_file_missing_file_returns_blank(tmp_path: Path):
    s = PublisherStateFile.load(tmp_path / "nope.json")
    assert s.publisher_aid == ""
    assert s.current_sn == -1
    assert s.has_tip is False


# ---------------------------------------------------------------------------
# PemFileSigningContext load + sign
# ---------------------------------------------------------------------------


def test_pem_context_rejects_missing_pem(tmp_path: Path):
    state = PublisherStateFile(path=tmp_path / "state.json")
    with pytest.raises(FileNotFoundError):
        PemFileSigningContext(
            publisher_aid="EAaa",
            keys_dir=tmp_path / "missing",
            passphrase=b"x",
            state_file=state,
        )


def test_pem_context_rejects_wrong_passphrase(synthetic_pem, tmp_path: Path):
    key_dir, _, _ = synthetic_pem
    state = PublisherStateFile(path=tmp_path / "state.json")
    with pytest.raises(Exception):  # YubiKeyError wrapping wrong-passphrase
        PemFileSigningContext(
            publisher_aid="EAaa",
            keys_dir=key_dir,
            passphrase=b"wrong-passphrase",
            state_file=state,
        )


def test_pem_context_loads_and_exposes_prefix(synthetic_pem, tmp_path: Path):
    key_dir, pubkey, passphrase = synthetic_pem
    icp_serder = _make_synthetic_publisher_icp(pubkey)
    state = PublisherStateFile(path=tmp_path / "state.json")
    ctx = PemFileSigningContext(
        publisher_aid=icp_serder.pre,
        keys_dir=key_dir,
        passphrase=passphrase,
        state_file=state,
    )
    assert ctx.prefix == icp_serder.pre


def test_pem_context_seed_then_build_signed_ixn(synthetic_pem, tmp_path: Path):
    key_dir, pubkey, passphrase = synthetic_pem
    icp_serder = _make_synthetic_publisher_icp(pubkey)
    state = PublisherStateFile(path=tmp_path / "state.json")
    ctx = PemFileSigningContext(
        publisher_aid=icp_serder.pre,
        keys_dir=key_dir,
        passphrase=passphrase,
        state_file=state,
    )
    ctx.seed_state_from_anchor(
        aid=icp_serder.pre, sn=0, event_digest=icp_serder.said
    )

    seal = _release_seal_fixture()
    raw, serder = ctx.build_signed_ixn(seal=seal)
    assert isinstance(serder, serdering.SerderKERI)
    assert serder.ked["t"] == "ixn"
    assert serder.ked["i"] == icp_serder.pre
    # sn advanced to 1 in the serder.
    assert serder.sn == 1
    # prior digest is the seeded inception SAID.
    assert serder.ked["p"] == icp_serder.said
    # Seal lives in `a`.
    assert serder.ked["a"][0] == seal
    # State file is NOT advanced by build_signed_ixn — only by commit_event.
    assert ctx.state_file.current_sn == 0
    assert ctx.state_file.last_event_digest == icp_serder.said
    # Now commit and verify state advanced + persisted.
    ctx.commit_event(serder)
    assert ctx.state_file.current_sn == 1
    assert ctx.state_file.last_event_digest == serder.said
    on_disk = PublisherStateFile.load(state.path)
    assert on_disk.current_sn == 1
    assert on_disk.last_event_digest == serder.said
    # Message has at least the event bytes; signature attachment present.
    assert raw.startswith(serder.raw)
    assert b"-AAB" in raw  # ControllerIdxSigs count=1 marker


def test_pem_context_sequential_builds_advance_sn(synthetic_pem, tmp_path: Path):
    key_dir, pubkey, passphrase = synthetic_pem
    icp = _make_synthetic_publisher_icp(pubkey)
    state = PublisherStateFile(path=tmp_path / "state.json")
    ctx = PemFileSigningContext(
        publisher_aid=icp.pre,
        keys_dir=key_dir,
        passphrase=passphrase,
        state_file=state,
    )
    ctx.seed_state_from_anchor(
        aid=icp.pre, sn=0, event_digest=icp.said
    )

    seal = _release_seal_fixture()
    _, s1 = ctx.build_signed_ixn(seal=seal)
    # Without commit, sn does NOT advance — second build also produces sn=1.
    _, s1_again = ctx.build_signed_ixn(seal=seal)
    assert s1.sn == 1
    assert s1_again.sn == 1
    # After commit_event, the next build advances to sn=2 chained on s1.
    ctx.commit_event(s1)
    _, s2 = ctx.build_signed_ixn(seal=seal)
    assert s2.sn == 2
    assert s2.ked["p"] == s1.said  # chains correctly


def test_pem_context_rejects_state_file_with_other_aid(synthetic_pem, tmp_path: Path):
    key_dir, pubkey, passphrase = synthetic_pem
    icp = _make_synthetic_publisher_icp(pubkey)
    # Pre-populate the state file with a DIFFERENT publisher AID.
    state_path = tmp_path / "state.json"
    PublisherStateFile(
        path=state_path,
        publisher_aid="ESomeOtherPublisher",
        current_sn=5,
        last_event_digest="EHshSomething",
    ).save()
    state = PublisherStateFile.load(state_path)
    with pytest.raises(ValueError, match="different publisher AID"):
        PemFileSigningContext(
            publisher_aid=icp.pre,
            keys_dir=key_dir,
            passphrase=passphrase,
            state_file=state,
        )


def test_pem_context_seed_rejects_mismatched_aid(synthetic_pem, tmp_path: Path):
    key_dir, pubkey, passphrase = synthetic_pem
    icp = _make_synthetic_publisher_icp(pubkey)
    state = PublisherStateFile(path=tmp_path / "state.json")
    ctx = PemFileSigningContext(
        publisher_aid=icp.pre,
        keys_dir=key_dir,
        passphrase=passphrase,
        state_file=state,
    )
    with pytest.raises(ValueError, match="does not match"):
        ctx.seed_state_from_anchor(
            aid="EWRONG_AID", sn=0, event_digest=icp.said
        )


def test_pem_context_build_without_seed_raises(synthetic_pem, tmp_path: Path):
    key_dir, pubkey, passphrase = synthetic_pem
    icp = _make_synthetic_publisher_icp(pubkey)
    state = PublisherStateFile(path=tmp_path / "state.json")
    ctx = PemFileSigningContext(
        publisher_aid=icp.pre,
        keys_dir=key_dir,
        passphrase=passphrase,
        state_file=state,
    )
    with pytest.raises(RuntimeError, match="KEL tip unknown"):
        ctx.build_signed_ixn(seal=_release_seal_fixture())


def test_pem_context_seed_from_witnesses(synthetic_pem, tmp_path: Path):
    key_dir, pubkey, passphrase = synthetic_pem
    icp = _make_synthetic_publisher_icp(pubkey)
    state = PublisherStateFile(path=tmp_path / "state.json")
    ctx = PemFileSigningContext(
        publisher_aid=icp.pre,
        keys_dir=key_dir,
        passphrase=passphrase,
        state_file=state,
    )
    fake_client = MagicMock()
    fake_client.query_state.return_value = MagicMock(
        sn=7, current_said="EHshFromWitness"
    )
    ctx.seed_state_from_witnesses(fake_client)
    assert ctx.state_file.current_sn == 7
    assert ctx.state_file.last_event_digest == "EHshFromWitness"
    fake_client.query_state.assert_called_once_with(icp.pre)


def test_signed_ixn_signature_verifies_against_pubkey(synthetic_pem, tmp_path: Path):
    """End-to-end sanity: signature attached to the ixn validates."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from keri.core.indexing import Siger

    key_dir, pubkey, passphrase = synthetic_pem
    icp = _make_synthetic_publisher_icp(pubkey)
    state = PublisherStateFile(path=tmp_path / "state.json")
    ctx = PemFileSigningContext(
        publisher_aid=icp.pre,
        keys_dir=key_dir,
        passphrase=passphrase,
        state_file=state,
    )
    ctx.seed_state_from_anchor(aid=icp.pre, sn=0, event_digest=icp.said)

    raw, serder = ctx.build_signed_ixn(seal=_release_seal_fixture())

    # Extract the attached signature bytes by parsing the trailer.
    # The message layout is: <event JSON><Counter><Siger qb64>.
    trailer = raw[len(serder.raw):]
    # Skip 4-char ControllerIdxSigs Counter (`-AAB` for count=1 v1.0).
    siger = Siger(qb64=trailer[4:].decode("ascii"))
    pubkey_obj = Ed25519PublicKey.from_public_bytes(pubkey)
    # Raises InvalidSignature if it doesn't verify.
    pubkey_obj.verify(siger.raw, bytes(serder.raw))


def test_derive_publisher_verfer_qb64_is_deterministic(synthetic_pem):
    _, pubkey, _ = synthetic_pem
    a = derive_publisher_verfer_qb64(pubkey)
    b = derive_publisher_verfer_qb64(pubkey)
    assert a == b
    assert a.startswith("D")  # Ed25519 Verfer qb64 prefix


# ---------------------------------------------------------------------------
# HabSigningContext — back-compat path for Phase 4 tests + --key-source habery
# ---------------------------------------------------------------------------


def test_hab_signing_context_wraps_existing_hab(tmp_path: Path):
    from keri.app import habbing

    suffix = uuid.uuid4().hex[:8]
    hby = habbing.Habery(name=f"sctx_test_{suffix}", base="", temp=True)
    try:
        hab = hby.makeHab(
            name="publisher",
            transferable=True,
            wits=[],
            toad=0,
            icount=1,
            isith="1",
            ncount=1,
            nsith="1",
        )
        ctx = HabSigningContext(hab=hab)
        assert ctx.prefix == hab.pre
        assert ctx.current_sn == 0
        assert ctx.last_event_digest == hab.kever.serder.said

        raw, serder = ctx.build_signed_ixn(seal=_release_seal_fixture())
        assert serder.ked["t"] == "ixn"
        assert serder.sn == 1
        assert ctx.current_sn == 1
    finally:
        hby.close()
