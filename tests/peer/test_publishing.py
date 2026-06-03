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


def test_revoke_publishes_cut_rpy_and_nullifies_loc(monkeypatch, hab_with_witnesses):
    """With allow=False the doer must (a) write /end/role/cut + an empty
    /loc/scheme rpy locally — these are how keripy expresses "this role
    is no longer authorized" — and (b) push them to witnesses so the
    revocation propagates. Empty url='' on a /loc/scheme nullifies the
    endpoint per Hab.makeLocScheme docs.
    """
    from locksmith.peer import publishing

    hby, hab = hab_with_witnesses
    fake_wits = ["BWIT_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"]
    monkeypatch.setattr(publishing, "_witnesses_for", lambda hab: fake_wits)

    sent_msgs: list[bytes] = []

    monkeypatch.setattr(
        publishing, "messenger",
        lambda hab, wit: _FakeMessenger(status=204, sent_msgs_sink=sent_msgs),
    )

    captured: list[tuple[str, str, dict]] = []
    bridge = SimpleNamespace(
        emit_doer_event=lambda doer_name, event_type, data: captured.append(
            (doer_name, event_type, data)
        )
    )

    doer = publishing.PublishPeerRoleDoer(
        hby=hby, hab=hab, url="tcp://192.168.1.42:5621",
        signal_bridge=bridge, allow=False,
    )
    doist = doing.Doist(limit=2.0, tock=0.03125, real=False)
    doist.do(doers=[doer])

    assert len(sent_msgs) == 2

    # Verify the messages are the cut/empty forms by route inspection.
    import json
    routes = []
    for raw in sent_msgs:
        # CESR stream: JSON SAD followed by `-`-prefixed attachment group.
        # Walk to the matching closing brace (depth-counted; SAIDs contain
        # hyphens so splitting on `-` won't work).
        depth = 0
        end = 0
        for i, b in enumerate(raw):
            if b == 0x7B:
                depth += 1
            elif b == 0x7D:
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        sad = json.loads(raw[:end])
        assert sad["t"] == "rpy"
        routes.append(sad["r"])
        if sad["r"] == "/loc/scheme":
            assert sad["a"]["url"] == "", "loc rpy must have empty url to nullify"
    assert set(routes) == {"/loc/scheme", "/end/role/cut"}

    complete_events = [e for e in captured if e[1] == "publish_complete"]
    assert len(complete_events) == 1


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


class _FakeMessenger(doing.DoDoer):
    """Stand-in for keri.app.agenting.HTTPMessenger that records the bytes
    it would have POSTed and pretends each one got the configured status
    code as a response. Drives DoDoer the same way as the real messenger:
    msgs deque to push into, sent deque to read responses from, idle
    flipping True once all queued messages have been processed.
    """
    def __init__(self, status: int = 204, sent_msgs_sink: list[bytes] | None = None):
        from types import SimpleNamespace
        self.msgs = []
        self.sent = []
        self._status = status
        self._sink = sent_msgs_sink
        self._processed = 0
        super().__init__(doers=[doing.doify(self._run)])

    def _run(self, tymth=None, tock=0.0, **opts):
        self.wind(tymth)
        self.tock = tock
        _ = (yield self.tock)
        from types import SimpleNamespace
        while True:
            while self.msgs:
                m = self.msgs.pop(0)
                if self._sink is not None:
                    self._sink.append(bytes(m))
                self.sent.append(
                    SimpleNamespace(status=self._status, reason="",
                                    errored=False, error=None)
                )
                self._processed += 1
            yield self.tock

    @property
    def idle(self):
        # one queued msg per rpy (we always publish 2: loc + end)
        return not self.msgs and self._processed >= 2


def test_publish_with_witnesses_emits_publish_complete(monkeypatch, hab_with_witnesses):
    """With one or more witnesses, the doer creates an HTTPMessenger per
    witness via agenting.messenger(), queues the rpys, waits for idle,
    and emits publish_complete with per-witness status info.
    """
    from locksmith.peer import publishing

    hby, hab = hab_with_witnesses
    fake_wits = ["BWIT_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
                 "BWIT_BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"]
    monkeypatch.setattr(publishing, "_witnesses_for", lambda hab: fake_wits)

    sent_msgs: list[bytes] = []
    created_for_wits: list[str] = []

    def _fake_messenger(hab, wit):
        created_for_wits.append(wit)
        return _FakeMessenger(status=204, sent_msgs_sink=sent_msgs)

    monkeypatch.setattr(publishing, "messenger", _fake_messenger)

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

    # 2 witnesses × 2 messages = 4 POSTs
    assert len(sent_msgs) == 4
    assert created_for_wits == fake_wits

    complete_events = [e for e in captured if e[1] == "publish_complete"]
    assert len(complete_events) == 1
    _, _, data = complete_events[0]
    assert data["aid"] == hab.pre
    assert data["witnesses_count"] == 2
    # Per-witness status info is what the next sprint item (HTTP-status
    # capture) actually adds — assert the shape and that all are 2xx.
    assert "witnesses" in data
    assert len(data["witnesses"]) == 2
    for entry in data["witnesses"]:
        assert entry["wit"] in fake_wits
        assert entry["status"] == 204
        assert entry["ok"] is True


def test_publish_records_non_2xx_as_rejected(monkeypatch, hab_with_witnesses):
    """If the witness returns 5xx/4xx (e.g. kerihost's old broken inbox),
    the doer still completes — but the per-witness entry must be flagged
    ok=False so callers / logs can distinguish "delivered" from "rejected"
    without re-curling.
    """
    from locksmith.peer import publishing

    hby, hab = hab_with_witnesses
    fake_wits = ["BWIT_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"]
    monkeypatch.setattr(publishing, "_witnesses_for", lambda hab: fake_wits)

    def _fake_messenger(hab, wit):
        return _FakeMessenger(status=504, sent_msgs_sink=None)

    monkeypatch.setattr(publishing, "messenger", _fake_messenger)

    captured: list[tuple[str, str, dict]] = []
    bridge = SimpleNamespace(
        emit_doer_event=lambda doer_name, event_type, data: captured.append(
            (doer_name, event_type, data)
        )
    )

    doer = publishing.PublishPeerRoleDoer(
        hby=hby, hab=hab, url="tcp://10.0.0.5:5621", signal_bridge=bridge,
    )
    doist = doing.Doist(limit=2.0, tock=0.03125, real=False)
    doist.do(doers=[doer])

    complete = [e for e in captured if e[1] == "publish_complete"]
    assert len(complete) == 1
    _, _, data = complete[0]
    assert data["witnesses"][0]["status"] == 504
    assert data["witnesses"][0]["ok"] is False
