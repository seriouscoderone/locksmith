# -*- encoding: utf-8 -*-
"""Tests for `locksmith.core.serviceaid_bridge._inband_oobi_msgs` (Task 7):
the in-band reply-as-OOBI rpys (spec Sec 6) a `ServiceaidGrantDoer` queues
on the grant's postman -- `/loc/scheme` by the EID, `/end/role/add` by the
CID -- so a first-contact recipient whose parser already verified the
sender's streamed KEL can also learn how to reach back. Gated on the vault's
peer-mode settings being enabled AND this AID having opted into peer
exposure (`is_aid_peer_exposed`) -- stock wallets without peer mode are
unaffected (empty list, no behavior change)."""
from types import SimpleNamespace
from unittest.mock import MagicMock

from keri import kering

from locksmith.core.serviceaid_bridge import _inband_oobi_msgs
from locksmith.peer.records import PeerModeSettings


def _hab(exposed=True):
    hab = MagicMock()
    hab.pre = "E" + "C" * 43
    # hab.reply returns one signed message: serder raw + attachment tail.
    hab.reply.side_effect = lambda route, data: b"{'fake':'serder'}ATTACH"
    return hab


def test_disabled_settings_yield_nothing(monkeypatch):
    monkeypatch.setattr(
        "locksmith.core.serviceaid_bridge.is_aid_peer_exposed", lambda hab: True)
    assert _inband_oobi_msgs(_hab(), PeerModeSettings(enabled=False)) == []
    assert _inband_oobi_msgs(_hab(), None) == []


def test_unexposed_hab_yields_nothing(monkeypatch):
    monkeypatch.setattr(
        "locksmith.core.serviceaid_bridge.is_aid_peer_exposed", lambda hab: False)
    assert _inband_oobi_msgs(_hab(), PeerModeSettings(enabled=True)) == []


def test_exposed_hab_yields_loc_and_endrole(monkeypatch):
    monkeypatch.setattr(
        "locksmith.core.serviceaid_bridge.is_aid_peer_exposed", lambda hab: True)
    # Real split needs a real serder; assert the reply routes requested
    # instead -- the serder/attachment split is exercised in Task 12's e2e.
    hab = _hab()
    calls = []
    hab.reply.side_effect = lambda route, data: calls.append((route, data)) or None
    try:
        _inband_oobi_msgs(hab, PeerModeSettings(enabled=True, port=5622,
                                                advertised_host="127.0.0.1"))
    except Exception:
        pass  # split fails on None -- routes were captured first
    routes = [c[0] for c in calls]
    assert routes == ["/loc/scheme", "/end/role/add"]
    assert calls[0][1]["url"] == "tcp://127.0.0.1:5622"
    assert calls[1][1]["role"] == "peer"


# ---------------------------------------------------------------------------
# Real-delegation coverage for the one-arg `is_aid_peer_exposed` adapter
# (Finding 2, review round 2): every test above monkeypatches the adapter
# away, so its `SimpleNamespace(db=hab.db, habs={hab.pre: hab})` stand-in --
# and the attribute contract it depends on (`db.ends.get`, keyed
# `(pre, kering.Roles.peer, pre)`, and the record's `.enabled`/`.allowed`
# attributes -- see `locksmith/peer/exposure.py`'s `is_aid_peer_exposed`)
# has never actually been exercised against the real exposure module. These
# tests do NOT monkeypatch `is_aid_peer_exposed`, pinning the adapter's
# delegation end to end.
# ---------------------------------------------------------------------------

def test_real_exposure_gate_lets_inband_oobi_proceed_when_end_record_enabled():
    """A `db.ends.get` result whose `.enabled` is True must let the REAL
    `locksmith.peer.exposure.is_aid_peer_exposed` return True through the
    adapter, so `_inband_oobi_msgs` proceeds past the exposure gate and
    calls `hab.reply` for both routes."""
    hab = _hab()
    hab.db.ends.get.return_value = SimpleNamespace(enabled=True, allowed=None)
    calls = []
    hab.reply.side_effect = lambda route, data: calls.append((route, data)) or None

    try:
        _inband_oobi_msgs(
            hab, PeerModeSettings(enabled=True, port=5622, advertised_host="127.0.0.1"),
        )
    except Exception:
        pass  # the serder/attachment split fails on the fake reply payload
              # above -- routes were already captured before that point.

    routes = [c[0] for c in calls]
    assert routes == ["/loc/scheme", "/end/role/add"]

    # Pins the exact db read the real exposure module performs (peer/
    # exposure.py:40): keyed (pre, kering.Roles.peer, pre) on `hab.db.ends`
    # -- the attribute contract the adapter's SimpleNamespace stand-in must
    # satisfy.
    hab.db.ends.get.assert_called_once_with(
        keys=(hab.pre, kering.Roles.peer, hab.pre)
    )


def test_real_exposure_gate_blocks_inband_oobi_when_end_record_missing():
    """No end-role record (`db.ends.get` returns None) must make the REAL
    exposure check return False through the adapter -- `_inband_oobi_msgs`
    short-circuits to `[]` without ever calling `hab.reply`."""
    hab = _hab()
    hab.db.ends.get.return_value = None

    assert _inband_oobi_msgs(hab, PeerModeSettings(enabled=True)) == []
    hab.reply.assert_not_called()


def test_real_exposure_gate_blocks_inband_oobi_when_end_record_disabled():
    """An end-role record present but neither enabled nor allowed (both
    falsy) must also make the REAL exposure check return False."""
    hab = _hab()
    hab.db.ends.get.return_value = SimpleNamespace(enabled=False, allowed=False)

    assert _inband_oobi_msgs(hab, PeerModeSettings(enabled=True)) == []
    hab.reply.assert_not_called()
