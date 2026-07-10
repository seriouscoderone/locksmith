"""TDD test: v2 KEL export via export_kel -> replay_kel round-trip.

Proves that:
  1. export_kel with a real v2 hab produces a genusified CESR stream that
     replay_kel can parse (RED: clonePreIter; GREEN: genusified messagize).
  2. The v1 fixture in tests/unit/update/test_kel_replay.py is unaffected
     (no-regression — exercised there, not here).

Root cause (documented in .superpowers/sdd/v2-replay-investigation.md):
  clonePreIter / cloneEvtMsg hardcode v1 CESR attachment count codes and emit
  no genus-version code, so a v2 event body is framed with v1 attachments — a
  self-inconsistent stream the verifier cannot re-ingest.  The fix: build the
  stream with eventing.messagize(..., gvrsn=serder.pvrsn, genusify=(sn==0))
  so the leading genus-version count code auto-raises the verifier's
  Parser(version=Vrsn_1_0) to v2.
"""
import pytest
from keri.app import habbing
from locksmith.update.kel_replay import replay_kel
from locksmith.update.errors import SignatureError

# A 21-character bran (Habery minimum).
_BRAN = "0123456789abcdefghijk"
_VERSION = "0.2.20"
_BRAND = "locksmith"
# Seal data that will be anchored in the ixn's `a` field.
_SEAL = [{"d": "E" + "A" * 43, "brand": _BRAND, "ver": _VERSION}]


# ---------------------------------------------------------------------------
# Helper: build a real (ephemeral) v2 hab with one ixn and export it.
# ---------------------------------------------------------------------------

def _make_v2_hab_and_export(hby):
    """Make a v2 hab, anchor one ixn, and call export_kel.

    Returns (hab, kel_bytes, anchor, ixn_said).
    """
    from locksmith_publisher.publish import export_kel

    hab = hby.makeHab("pub", icount=1, ncount=1, wits=[], toad=0)
    hab.interact(data=_SEAL)

    kel_bytes, anchor = export_kel(hby, hab, version=_VERSION, brand=_BRAND)
    ixn_serder, _, _ = hab.getOwnEvent(sn=1)
    return hab, kel_bytes, anchor, ixn_serder.said


# ---------------------------------------------------------------------------
# Core contract: genusified export replays through the production verifier.
# ---------------------------------------------------------------------------

def test_v2_export_replays_via_replay_kel():
    """export_kel must produce a stream that replay_kel accepts for a v2 hab.

    This is the key RED→GREEN test:
      - RED (before fix): clonePreIter export fails replay_kel with
        SignatureError("publisher_aid … not found in replayed KEL") because
        the v2 body + v1 attachment framing is self-inconsistent.
      - GREEN (after fix): genusified messagize export lands both icp and ixn
        in the replayed KEL.
    """
    with habbing.openHby(name="v2-export-test", temp=True, bran=_BRAN) as hby:
        hab, kel_bytes, anchor, ixn_said = _make_v2_hab_and_export(hby)

        state = replay_kel(
            kel_stream=kel_bytes,
            publisher_aid=hab.pre,
            embedded_sn=1,
            embedded_said=ixn_said,
            toad=0,
        )

    # Both events must land.
    assert state.current_sn == 1
    events_summary = [(e.sn, e.ilk) for e in state.events]
    assert events_summary == [(0, "icp"), (1, "ixn")], (
        f"expected [(0,'icp'),(1,'ixn')], got {events_summary}"
    )
    # AID must match.
    assert state.publisher_aid == hab.pre


def test_v2_export_replay_kel_finds_anchor_event():
    """The ixn event that carries the release seal must appear in state.events
    with its seals accessible."""
    with habbing.openHby(name="v2-anchor-test", temp=True, bran=_BRAN) as hby:
        hab, kel_bytes, anchor, ixn_said = _make_v2_hab_and_export(hby)

        state = replay_kel(
            kel_stream=kel_bytes,
            publisher_aid=hab.pre,
            embedded_sn=1,
            embedded_said=ixn_said,
            toad=0,
        )

    # The anchor event must be present with the seal we anchored.
    ixn_events = [e for e in state.events if e.sn == 1]
    assert ixn_events, "ixn event (sn=1) must appear in replayed state"
    ixn_ev = ixn_events[0]
    assert ixn_ev.said == ixn_said
    seal_vers = [s.get("ver") for s in ixn_ev.seals if isinstance(s, dict)]
    assert _VERSION in seal_vers, (
        f"release version {_VERSION!r} not found in ixn seals: {ixn_ev.seals}"
    )


def test_export_kel_returns_anchor_dict():
    """export_kel must return a non-None anchor dict with said/sn/bytes keys."""
    with habbing.openHby(name="v2-anchor-dict-test", temp=True, bran=_BRAN) as hby:
        hab, kel_bytes, anchor, ixn_said = _make_v2_hab_and_export(hby)

    assert anchor is not None, "export_kel must return an anchor for a matching version/brand"
    assert anchor["said"] == ixn_said
    assert anchor["sn"] == 1
    assert isinstance(anchor["bytes"], bytes) and len(anchor["bytes"]) > 0


def test_export_kel_returns_none_anchor_when_no_matching_seal():
    """export_kel must return anchor=None when no ixn carries the requested version."""
    from locksmith_publisher.publish import export_kel

    with habbing.openHby(name="v2-no-anchor-test", temp=True, bran=_BRAN) as hby:
        hab = hby.makeHab("pub", icount=1, ncount=1, wits=[], toad=0)
        hab.interact(data=_SEAL)

        kel_bytes, anchor = export_kel(
            hby, hab, version="9.9.9", brand=_BRAND  # non-existent version
        )

    assert anchor is None, "export_kel must return None anchor when no seal matches"
    assert isinstance(kel_bytes, bytes) and len(kel_bytes) > 0


def test_export_kel_stream_starts_with_genus_code():
    """The exported stream must begin with a genus-version count code ('-_').

    The genus-version code is what auto-switches the Parser version (parsing.py:1029-1043).
    Its presence is what makes the genusified stream universally parseable.
    """
    from locksmith_publisher.publish import export_kel

    with habbing.openHby(name="v2-genus-test", temp=True, bran=_BRAN) as hby:
        hab = hby.makeHab("pub", icount=1, ncount=1, wits=[], toad=0)
        kel_bytes, _ = export_kel(hby, hab, version=_VERSION, brand=_BRAND)

    # keripy genus-version count codes start with '-_' (dash-underscore).
    assert kel_bytes[:2] == b"-_", (
        f"KEL stream must start with genus-version code '-_', "
        f"got {kel_bytes[:8]!r}"
    )


# ---------------------------------------------------------------------------
# Regression guard: clonePreIter FAILS for v2 (confirming the RED state).
# ---------------------------------------------------------------------------

def test_clone_pre_iter_fails_for_v2_hab():
    """Baseline: the OLD clonePreIter approach fails replay_kel on a v2 hab.

    This test locks in the RED state.  If it starts PASSING, something
    upstream (keripy cloneEvtMsg) was fixed — the export_kel fix can then
    be simplified back, but the GREEN tests must still hold.
    """
    from keri.db import dbing as _dbing
    from keri.core import serdering as _serdering

    with habbing.openHby(name="v2-clone-fail-test", temp=True, bran=_BRAN) as hby:
        hab = hby.makeHab("pub", icount=1, ncount=1, wits=[], toad=0)
        hab.interact(data=_SEAL)

        # clonePreIter export (old publisher path).
        kel = bytearray()
        for msg in hby.db.clonePreIter(pre=hab.pre):
            kel.extend(msg)

        ixn_serder, _, _ = hab.getOwnEvent(sn=1)

        with pytest.raises(SignatureError):
            replay_kel(
                kel_stream=bytes(kel),
                publisher_aid=hab.pre,
                embedded_sn=1,
                embedded_said=ixn_serder.said,
                toad=0,
            )
