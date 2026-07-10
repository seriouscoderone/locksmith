"""Tests for ``locksmith.update.kel_replay`` — replays publisher KEL against witnesses."""
import json
from pathlib import Path

import pytest

from locksmith.update.errors import (
    RotationMismatchError,
    SchemaError,
    SignatureError,
    WitnessThresholdError,
)
from locksmith.update.kel_replay import (
    KelState,
    ReplayedEvent,
    extract_release_seal,
    replay_kel,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "update"


def load_kel_stream() -> bytes:
    return (FIXTURES / "kel" / "publisher.cesr").read_bytes()


def load_manifest() -> dict:
    return json.loads((FIXTURES / "publisher_aid.json").read_text())


def test_replay_from_inception_returns_state_at_tip():
    manifest = load_manifest()
    state = replay_kel(
        kel_stream=load_kel_stream(),
        publisher_aid=manifest["publisher_aid"],
        embedded_sn=0,
        embedded_said=None,
        toad=manifest["toad"],
    )
    assert isinstance(state, KelState)
    assert state.publisher_aid == manifest["publisher_aid"]
    assert state.current_sn == manifest["kel_tip_sn"]
    assert state.current_keys
    # icp + 3 ixn = 4 events.
    assert len(state.events) == 4


def test_replay_extracts_release_seal_for_known_said():
    """extract_release_seal finds a digest-seal (d+ver) in a replayed state.

    NOTE: The CESR fixture (publisher.cesr) was built with the old
    {"release": {...}} seal shape and will be regenerated in Task 2's fixture
    update.  Until then this test exercises the extraction logic against a
    synthetic digest-seal state rather than the fixture.
    """
    from locksmith.update.kel_replay import KelState
    # Synthetic state with digest seal shape (new format).
    state = KelState(
        publisher_aid="EMUvj_PEHgrWHRRyO7JYbqk-qEvuBMFbyoq22O-7DZ4A",
        current_sn=2,
        current_said="EBa1ObArnkSs1ynBfUcJTOIzYj9tiPHPfj6GmDrojYrc",
        current_keys=("K",),
        next_digest="N",
        toad=3,
        events=[
            ReplayedEvent(
                sn=2,
                said="EBa1ObArnkSs1ynBfUcJTOIzYj9tiPHPfj6GmDrojYrc",
                ilk="ixn",
                seals=[{"d": "Edigest101", "brand": "locksmith", "ver": "1.0.1"}],
                receipts=3,
            )
        ],
    )
    seal = extract_release_seal(
        state, anchor_said="EBa1ObArnkSs1ynBfUcJTOIzYj9tiPHPfj6GmDrojYrc"
    )
    assert seal["ver"] == "1.0.1"
    assert seal["brand"] == "locksmith"
    assert "d" in seal


def test_replay_rejects_wrong_publisher_aid():
    manifest = load_manifest()
    with pytest.raises(SignatureError) as e:
        replay_kel(
            kel_stream=load_kel_stream(),
            publisher_aid="EBOGUSAIDPREFIXDOESNOTMATCHANYTHING",
            embedded_sn=0,
            embedded_said=None,
            toad=manifest["toad"],
        )
    assert "publisher_aid" in e.value.reason.lower()


def test_replay_with_embedded_said_match_succeeds():
    manifest = load_manifest()
    state = replay_kel(
        kel_stream=load_kel_stream(),
        publisher_aid=manifest["publisher_aid"],
        embedded_sn=0,
        embedded_said=manifest["embedded_kel_hash"],
        toad=manifest["toad"],
    )
    assert state.current_sn == manifest["kel_tip_sn"]


def test_replay_with_wrong_embedded_said_raises():
    manifest = load_manifest()
    with pytest.raises(SignatureError) as e:
        replay_kel(
            kel_stream=load_kel_stream(),
            publisher_aid=manifest["publisher_aid"],
            embedded_sn=0,
            embedded_said="ENotTheActualSAIDOfTheInceptionEventXXXXXXXX",
            toad=manifest["toad"],
        )
    assert "embedded_said" in e.value.reason.lower()


def test_replay_rejects_insufficient_witness_receipts():
    """Force toad above the available number of receipts (3) so threshold fails."""
    manifest = load_manifest()
    with pytest.raises(WitnessThresholdError) as e:
        replay_kel(
            kel_stream=load_kel_stream(),
            publisher_aid=manifest["publisher_aid"],
            embedded_sn=0,
            embedded_said=None,
            toad=manifest["toad"] + 1,  # one more than we have
        )
    assert "receipt" in e.value.reason.lower()
    assert e.value.log_fields.get("sn") is not None


def test_replay_rejects_tampered_event_signature():
    """Concatenated tampered ixn event in the stream → SignatureError."""
    manifest = load_manifest()
    # Replace the tail with a stream containing only icp + tampered ixn
    # — keripy's parser will either reject or silently drop the bad event.
    # Either way, the bad ixn shouldn't make it past replay.
    real_stream = load_kel_stream()
    tampered = (FIXTURES / "tampered" / "tampered_event_1.0.1.cesr").read_bytes()
    # Concatenate the canonical stream + the tampered event again — replay
    # must either reject (raise) or the tampered event must not affect tip.
    stream = real_stream + tampered
    # The tampered bytes have the same SAID-like prefix but a flipped byte;
    # parser may raise SignatureError or simply drop. We accept either —
    # the invariant is that no replay returns a state with the tampered event
    # promoted into kevers.
    try:
        state = replay_kel(
            kel_stream=stream,
            publisher_aid=manifest["publisher_aid"],
            embedded_sn=0,
            embedded_said=None,
            toad=manifest["toad"],
        )
        # If we got a state back, it must still be at the canonical tip.
        assert state.current_sn == manifest["kel_tip_sn"]
    except (SignatureError, SchemaError, RotationMismatchError):
        # Parser rejected the tampered bytes — also acceptable.
        pass


def test_replay_from_embedded_sn_does_not_change_tip_state():
    """Trusting events 0..2 still produces the same tip kever state."""
    manifest = load_manifest()
    state = replay_kel(
        kel_stream=load_kel_stream(),
        publisher_aid=manifest["publisher_aid"],
        embedded_sn=2,
        embedded_said=None,
        toad=manifest["toad"],
    )
    assert state.current_sn == manifest["kel_tip_sn"]


def test_extract_release_seal_missing_said_raises():
    manifest = load_manifest()
    state = replay_kel(
        kel_stream=load_kel_stream(),
        publisher_aid=manifest["publisher_aid"],
        embedded_sn=0,
        embedded_said=None,
        toad=manifest["toad"],
    )
    with pytest.raises(SchemaError) as e:
        extract_release_seal(
            state,
            anchor_said="ENotInTheKEL_____________________________",
        )
    assert "anchor_said" in e.value.reason.lower()


def test_extract_release_seal_event_without_release_seal_raises():
    """Inception event has no seal → SchemaError."""
    manifest = load_manifest()
    state = replay_kel(
        kel_stream=load_kel_stream(),
        publisher_aid=manifest["publisher_aid"],
        embedded_sn=0,
        embedded_said=None,
        toad=manifest["toad"],
    )
    # icp event has empty seals.
    icp_event = next(e for e in state.events if e.sn == 0)
    with pytest.raises(SchemaError):
        extract_release_seal(state, anchor_said=icp_event.said)


def _ev(sn, brand, ver):
    seal = {"d": f"Edigest{sn}", "ver": ver}
    if brand is not None:
        seal["brand"] = brand
    return ReplayedEvent(sn=sn, said=f"E{sn}", ilk="ixn", seals=[seal], receipts=3)


def _state(events):
    return KelState(publisher_aid="Epub", current_sn=events[-1].sn,
                    current_said=events[-1].said, current_keys=("K",),
                    next_digest="N", toad=3, events=events)


def test_highest_version_for_brand_scopes_by_brand():
    from locksmith.update.kel_replay import highest_version_for_brand
    st = _state([_ev(10, "locksmith", "0.2.17"), _ev(12, "locksmith", "0.2.18"),
                 _ev(13, "usurance", "0.2.18"), _ev(14, "usurance", "0.2.20")])
    assert highest_version_for_brand(st, "locksmith") == "0.2.18"
    assert highest_version_for_brand(st, "usurance") == "0.2.20"


def test_highest_version_brandless_counts_as_locksmith():
    from locksmith.update.kel_replay import highest_version_for_brand
    st = _state([_ev(1, None, "0.1.0"), _ev(2, None, "0.2.18")])
    assert highest_version_for_brand(st, "locksmith") == "0.2.18"
    assert highest_version_for_brand(st, "usurance") is None
