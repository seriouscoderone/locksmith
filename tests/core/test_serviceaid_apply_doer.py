# -*- encoding: utf-8 -*-
"""ServiceaidApplyDoer: frame + persist + deliver an IPEX apply over the
peer channel; direct-mode failures are loud (no silent mailbox fallback)."""
from unittest.mock import MagicMock

import pytest
from hio.base import doing
from keri.app import habbing
from keri.peer import exchanging

from locksmith.core import serviceaid_bridge as bridge
from locksmith.core.serviceaid_bridge import ServiceaidApplyDoer, make_apply_doer

SCHEMA = "E" + "A" * 43


def bridge_poster_name() -> str:
    return "PeerAwarePoster"   # match the symbol grantDo constructs (Step 0)


class _Sig:
    def __init__(self):
        self.events = []

    def emit_doer_event(self, source, event_type, data):
        self.events.append((source, event_type, data))


class _FakePoster:
    """Stands in for the peer-aware poster: records sends, reports channel."""
    def __init__(self, *, channel="peer", **kwa):
        self._channel = channel
        self.sent_msgs = []

    def send(self, *, serder=None, attachment=None, **kwa):
        self.sent_msgs.append(serder)

    def deliver(self):
        return []          # nothing to drive; nested DoDoer finishes at once

    @property
    def last_outcome(self):
        class _O:
            value = self._channel

        return _O() if self._channel else None


@pytest.fixture()
def vaulted_app():
    with habbing.openHby(name="applydoer", temp=True) as hby:
        hab = hby.makeHab(name="user")
        vault = MagicMock()
        vault.hby = hby
        vault.exc = exchanging.Exchanger(hby=hby, handlers=[])
        vault.signals = _Sig()
        vault.db = None                       # no peer settings -> no in-band OOBI
        app = MagicMock()
        app.vault = vault
        yield app, hab


def _drive(doer):
    doist = doing.Doist(limit=2.0, tock=0.03125, real=False)
    doist.do(doers=[doer])


def test_apply_sent_over_peer_persists_and_emits(vaulted_app, monkeypatch):
    app, hab = vaulted_app
    poster = _FakePoster(channel="peer")
    monkeypatch.setattr(bridge, bridge_poster_name(), lambda **kwa: poster)

    doer = ServiceaidApplyDoer(app, schema_said=SCHEMA, recipient=hab.pre,
                               hab_pre=hab.pre)
    _drive(doer)

    events = app.vault.signals.events
    assert ("ApplyFlow", "apply_sent") in [(s, t) for s, t, _ in events]
    from keri_serviceaid.providers import list_sent_applies
    assert len(list_sent_applies(app.vault.hby, hab.pre)) == 1


def test_non_peer_channel_is_a_loud_failure(vaulted_app, monkeypatch):
    app, hab = vaulted_app
    monkeypatch.setattr(bridge, bridge_poster_name(),
                        lambda **kwa: _FakePoster(channel="mailbox"))
    doer = ServiceaidApplyDoer(app, schema_said=SCHEMA, recipient=hab.pre,
                               hab_pre=hab.pre)
    _drive(doer)
    kinds = [(s, t) for s, t, _ in app.vault.signals.events]
    assert ("ApplyFlow", "apply_failed") in kinds
    assert ("ApplyFlow", "apply_sent") not in kinds


def test_make_apply_doer_rejects_ineligible_hab(vaulted_app, monkeypatch):
    app, hab = vaulted_app
    monkeypatch.setattr(bridge, "serviceaid_eligible", lambda h: False)
    doer = make_apply_doer(app, hab, schema_said=SCHEMA, recipient=hab.pre)
    assert doer is None
    kinds = [(s, t) for s, t, _ in app.vault.signals.events]
    assert ("ApplyFlow", "apply_failed") in kinds
