import types
import pytest
from locksmith_publisher import publish

_AID = "EHjWPRGoY9PV_tjNUJ7_XgwXLWg77fDm3BSGHd3lDFhD"


def _state(events):
    # Mimic kel_replay.KelState/ReplayedEvent shape (only fields the guard reads).
    ev = [types.SimpleNamespace(sn=e[0], said=e[1], seals=e[2]) for e in events]
    return types.SimpleNamespace(publisher_aid=_AID, current_sn=ev[-1].sn if ev else 0,
                                 events=ev)


def test_guard_passes_when_anchor_accepted(monkeypatch):
    monkeypatch.setattr(publish, "replay_kel", lambda **kw: _state([
        (0, "Eicp", []),
        (1, "Eanchor", [{"d": "E" + "A" * 43, "brand": "locksmith", "ver": "0.2.4"}]),
    ]))
    # Should not raise.
    publish.assert_kel_anchors_release(
        kel_bytes=b"x", publisher_aid=_AID, version="0.2.4",
        anchor_said="Eanchor", toad=3)


def test_guard_raises_when_anchor_not_accepted(monkeypatch):
    # Under-receipted anchor → escrowed → absent from state.events (the 0.2.4 bug).
    monkeypatch.setattr(publish, "replay_kel", lambda **kw: _state([
        (0, "Eicp", []),
    ]))
    with pytest.raises(RuntimeError, match="not anchored|not present|not accepted"):
        publish.assert_kel_anchors_release(
            kel_bytes=b"x", publisher_aid=_AID, version="0.2.4",
            anchor_said="Eanchor", toad=3)
