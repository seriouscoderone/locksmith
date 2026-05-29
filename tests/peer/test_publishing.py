"""Tests for PublishPeerRoleDoer — landing peer role/loc rpys locally
and pushing them to the AID's witnesses so witness-served peer OOBIs
work as designed.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from hio.base import doing


@pytest.fixture
def hab_with_witnesses():
    """Real-ish Hab built on a Habery so kvy/rvy/psr exist and
    Parser.parse + WitnessPublisher have surfaces to land on.
    """
    from keri.app import habbing
    from keri.core import signing

    hby = habbing.Habery(
        name=f"pubtest",
        bran="A" * 21,
        salt=signing.Salter(raw=b"0123456789abcdef").qb64,
        temp=True,
    )
    try:
        hab = hby.makeHab(name="alice", isith="1", icount=1, transferable=True)
        yield hby, hab
    finally:
        hby.close()


def test_publish_no_witnesses_emits_no_witnesses_event(hab_with_witnesses):
    """A solo AID with no witnesses should not block, should land rpys
    locally, and should emit a 'no_witnesses' event so the UI can warn
    the user that the witness-served peer-OOBI path won't work.
    """
    from locksmith.peer.publishing import PublishPeerRoleDoer

    hby, hab = hab_with_witnesses
    assert hab.kever.wits == []  # baseline: no witnesses

    captured: list[tuple[str, str, dict]] = []
    bridge = SimpleNamespace(
        emit_doer_event=lambda doer_name, event_type, data: captured.append(
            (doer_name, event_type, data)
        )
    )

    doer = PublishPeerRoleDoer(
        hby=hby,
        hab=hab,
        url="tcp://127.0.0.1:5621",
        signal_bridge=bridge,
    )

    doist = doing.Doist(limit=2.0, tock=0.03125, real=False)
    doist.do(doers=[doer])

    # Local db should have a peer-role end and tcp loc for this AID
    from keri import kering
    end = hby.db.ends.get(keys=(hab.pre, kering.Roles.peer, hab.pre))
    assert end is not None and (end.enabled or end.allowed)
    loc = hby.db.locs.get(keys=(hab.pre, kering.Schemes.tcp))
    assert loc is not None and loc.url == "tcp://127.0.0.1:5621"

    # Signal should fire once with no_witnesses
    assert len(captured) == 1
    doer_name, event_type, data = captured[0]
    assert doer_name == "PublishPeerRoleDoer"
    assert event_type == "no_witnesses"
    assert data["aid"] == hab.pre
    assert data["witnesses_count"] == 0


def test_publish_with_witnesses_emits_publish_complete(monkeypatch, hab_with_witnesses):
    """With one or more witnesses, the doer should hand off the locally-
    parsed rpys to a WitnessPublisher and emit publish_complete when the
    publisher signals it sent everything.

    We monkeypatch WitnessPublisher so the test doesn't try to dial real
    witness sockets — only the wiring (we feed msgs in, cues come back
    out) is under test.
    """
    from locksmith.peer import publishing

    hby, hab = hab_with_witnesses
    fake_wits = ["BWIT_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
                 "BWIT_BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"]
    monkeypatch.setattr(publishing, "_witnesses_for", lambda hab: fake_wits)

    sent_msgs: list[bytes] = []

    class FakePublisher(doing.DoDoer):
        """A real DoDoer with a worker doer that drains msgs into cues
        and records them in sent_msgs. The .idle property flips True once
        both queued messages have been processed.
        """
        def __init__(self, hby, **kwa):
            self.hby = hby
            self.msgs = []
            self.cues = []
            self.posted = 0
            super().__init__(doers=[doing.doify(self._send_do)], **kwa)

        def _send_do(self, tymth=None, tock=0.0, **opts):
            self.wind(tymth)
            self.tock = tock
            _ = (yield self.tock)
            while True:
                while self.msgs:
                    evt = self.msgs.pop(0)
                    sent_msgs.append(bytes(evt["msg"]))
                    self.cues.append(evt)
                    self.posted += 1
                yield self.tock

        @property
        def idle(self):
            return not self.msgs and self.posted >= 2  # 2 = loc + end

    monkeypatch.setattr(publishing, "WitnessPublisher",
                        lambda hby, **kwa: FakePublisher(hby, **kwa))

    captured: list[tuple[str, str, dict]] = []
    bridge = SimpleNamespace(
        emit_doer_event=lambda doer_name, event_type, data: captured.append(
            (doer_name, event_type, data)
        )
    )

    doer = publishing.PublishPeerRoleDoer(
        hby=hby,
        hab=hab,
        url="tcp://192.168.1.42:5621",
        signal_bridge=bridge,
    )

    doist = doing.Doist(limit=2.0, tock=0.03125, real=False)
    doist.do(doers=[doer])

    # Should have queued 2 messages (loc + end) on the publisher
    assert len(sent_msgs) == 2

    # Should have emitted publish_complete with witnesses_count=2
    complete_events = [e for e in captured if e[1] == "publish_complete"]
    assert len(complete_events) == 1
    _, _, data = complete_events[0]
    assert data["aid"] == hab.pre
    assert data["witnesses_count"] == 2
