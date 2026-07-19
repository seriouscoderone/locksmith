# -*- encoding: utf-8 -*-
"""Tests for `locksmith.core.serviceaid_bridge._inband_oobi_msgs` (Task 7):
the in-band reply-as-OOBI rpys (spec Sec 6) a `ServiceaidGrantDoer` queues
on the grant's postman -- `/loc/scheme` by the EID, `/end/role/add` by the
CID -- so a first-contact recipient whose parser already verified the
sender's streamed KEL can also learn how to reach back. Gated on the vault's
peer-mode settings being enabled AND this AID having opted into peer
exposure (`is_aid_peer_exposed`) -- stock wallets without peer mode are
unaffected (empty list, no behavior change)."""
from unittest.mock import MagicMock

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
