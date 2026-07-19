# -*- encoding: utf-8 -*-
"""The direct-mode peer inbound parser MUST have a Tevery, or keripy drops
every streamed registry TEL event (vcp/iss) with "No tevery to process so
dropped msg" -- so a credential PRESENTED over peer transport can never be
admitted by the recipient (its registry never verifies, reger.saved never
sets). Regression for the live-demo blocker: PeerDoer built its Directant
with no verifier, leaving Reactant.tevery = None.

Socket-free: PeerDoer constructs a TCPServer object but does not bind until
run, and Directant/Reactant do no I/O at construction -- so these tests open
no sockets and belong in tests/core/, never tests/peer/ (host rule).
"""
from unittest.mock import MagicMock

from locksmith.peer.doer import PeerDoer
from locksmith.peer.records import PeerModeSettings


def _hby():
    hby = MagicMock(name="hby")
    hby.habs = {"E" + "C" * 43: MagicMock(pre="E" + "C" * 43)}
    return hby


def test_peer_doer_threads_verifier_into_directant():
    verifier = MagicMock(name="verifier")
    doer = PeerDoer(
        hby=_hby(), baser=MagicMock(), settings=PeerModeSettings(enabled=True),
        exchanger=MagicMock(), is_destination_exposed=lambda a: True,
        verifier=verifier,
    )
    assert doer.directant is not None
    assert doer.directant.verifier is verifier   # -> Reactant builds a Tevery


def test_directant_without_verifier_would_drop_tel():
    """Guards the regression: no verifier -> directant.verifier is None ->
    Reactant.tevery is None -> streamed vcp/iss are dropped. This asserts the
    dependency so a future refactor can't silently reintroduce it."""
    doer = PeerDoer(
        hby=_hby(), baser=MagicMock(), settings=PeerModeSettings(enabled=True),
        exchanger=MagicMock(), is_destination_exposed=lambda a: True,
    )
    assert doer.directant.verifier is None


def test_disabled_peer_doer_is_inert():
    doer = PeerDoer(
        hby=_hby(), baser=MagicMock(), settings=PeerModeSettings(enabled=False),
        exchanger=MagicMock(), is_destination_exposed=lambda a: True,
        verifier=MagicMock(),
    )
    assert doer.directant is None
