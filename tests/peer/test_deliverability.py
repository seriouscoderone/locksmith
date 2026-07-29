"""Deliverability policy for the admin grant path — never lie about delivery.

The first live two-machine test lost a grant silently: the peer dial failed,
the poster fell back to keripy's StreamPoster, and the recipient had no
mailbox/agent/witness ends — so the "fallback" delivered nowhere while the
operator saw success
(backlog/2026-07-29-grant-send-reports-success-while-undeliverable.md).

``mailbox_route_exists`` mirrors StreamPoster's OWN routing walk
(``forwarding.StreamPoster._chunk``: controller/agent/mailbox ends first,
else witness ends, all via ``hab.endsFor``) so "the fallback had nowhere to
deliver" is decided by the same rules keripy routes by. ``undeliverable``
composes it with the transport channel; ``recipient_label`` names the peer in
the failure copy.
"""
from __future__ import annotations

import pytest
from keri import Vrsn_1_0, kering
from keri.app import habbing

from locksmith.peer.allowlist import PeerAllowlist
from locksmith.peer.posting import (
    mailbox_route_exists,
    recipient_label,
    undeliverable,
)
from locksmith.peer.records import PeerRecord

MBX_URL = "http://mailbox.example:5632/"


@pytest.fixture()
def hby():
    with habbing.openHby(name="deliv", temp=True, version=Vrsn_1_0) as h:
        yield h


def _reply(hby, hab, route, data):
    hby.psr.parse(ims=bytearray(hab.reply(route=route, data=data)))


def test_no_ends_at_all_means_no_mailbox_route(hby):
    """The live requester: witnessless AID, no mailbox — the fallback has
    nowhere to route, exactly the case that must go loud."""
    me = hby.makeHab(name="me", transferable=True, version=Vrsn_1_0)
    recp = hby.makeHab(name="recp", transferable=True, version=Vrsn_1_0)

    assert mailbox_route_exists(me, recp.pre) is False


def test_a_located_mailbox_end_is_a_route(hby):
    me = hby.makeHab(name="me2", transferable=True, version=Vrsn_1_0)
    recp = hby.makeHab(name="recp2", transferable=True, version=Vrsn_1_0)
    mbx = hby.makeHab(name="mbx2", transferable=False, version=Vrsn_1_0)

    _reply(hby, mbx, "/loc/scheme",
           dict(eid=mbx.pre, scheme=kering.Schemes.http, url=MBX_URL))
    _reply(hby, recp, "/end/role/add",
           dict(cid=recp.pre, role=kering.Roles.mailbox, eid=mbx.pre))

    assert mailbox_route_exists(me, recp.pre) is True


def test_a_peer_only_end_is_not_a_mailbox_route(hby):
    """Peer-role ends are the DIRECT channel — StreamPoster's fallback never
    routes through them, so they must not count as 'somewhere to deliver'."""
    me = hby.makeHab(name="me3", transferable=True, version=Vrsn_1_0)
    recp = hby.makeHab(name="recp3", transferable=True, version=Vrsn_1_0)
    lsn = hby.makeHab(name="lsn3", transferable=False, ns="peer",
                      version=Vrsn_1_0)

    _reply(hby, lsn, "/loc/scheme",
           dict(eid=lsn.pre, scheme=kering.Schemes.tcp,
                url="tcp://192.168.1.9:5622"))
    _reply(hby, recp, "/end/role/add",
           dict(cid=recp.pre, role=kering.Roles.peer, eid=lsn.pre))

    assert mailbox_route_exists(me, recp.pre) is False


def test_a_mailbox_end_with_no_location_is_not_a_route(hby):
    """Role authorization without a /loc/scheme routes nowhere — keripy
    would pick the eid and then have no URL to dial."""
    me = hby.makeHab(name="me4", transferable=True, version=Vrsn_1_0)
    recp = hby.makeHab(name="recp4", transferable=True, version=Vrsn_1_0)
    mbx = hby.makeHab(name="mbx4", transferable=False, version=Vrsn_1_0)

    _reply(hby, recp, "/end/role/add",
           dict(cid=recp.pre, role=kering.Roles.mailbox, eid=mbx.pre))

    assert mailbox_route_exists(me, recp.pre) is False


def test_a_located_witness_is_a_route(hby):
    """A witnessed recipient can be reached store-and-forward through its
    witness — StreamPoster's `elif Roles.witness` branch."""
    me = hby.makeHab(name="me5", transferable=True, version=Vrsn_1_0)
    wit = hby.makeHab(name="wit5", transferable=False, version=Vrsn_1_0)
    _reply(hby, wit, "/loc/scheme",
           dict(eid=wit.pre, scheme=kering.Schemes.http,
                url="http://wit.example:5631/"))
    recp = hby.makeHab(name="recp5", transferable=True, wits=[wit.pre],
                       toad=1, version=Vrsn_1_0)

    assert mailbox_route_exists(me, recp.pre) is True


def test_undeliverable_composes_channel_and_route(hby):
    me = hby.makeHab(name="me6", transferable=True, version=Vrsn_1_0)
    recp = hby.makeHab(name="recp6", transferable=True, version=Vrsn_1_0)

    # Peer channel delivered → never undeliverable, ends or not.
    assert undeliverable("peer", me, recp.pre) is False
    # Fallback/mailbox channel with no route → the silent-loss case.
    assert undeliverable("peer→mailbox", me, recp.pre) is True
    assert undeliverable("mailbox", me, recp.pre) is True

    mbx = hby.makeHab(name="mbx6", transferable=False, version=Vrsn_1_0)
    _reply(hby, mbx, "/loc/scheme",
           dict(eid=mbx.pre, scheme=kering.Schemes.http, url=MBX_URL))
    _reply(hby, recp, "/end/role/add",
           dict(cid=recp.pre, role=kering.Roles.mailbox, eid=mbx.pre))

    # Same fallback channel, but now the mailbox leg really has a route.
    assert undeliverable("peer→mailbox", me, recp.pre) is False


def test_recipient_label_prefers_the_pairing_label(baser):
    aid = "E" + "L" * 43
    PeerAllowlist(baser).add(PeerRecord(
        aid=aid, label="requester-vm", endpoint_url="tcp://10.0.0.2:5622"))

    assert recipient_label(baser, aid) == "requester-vm"


def test_recipient_label_falls_back_to_contact_alias_then_short_aid(baser):
    aid = "E" + "M" * 43

    class FakeOrg:
        def get(self, pre, field=None):
            return {"alias": "bob-from-contacts"} if pre == aid else None

    assert recipient_label(baser, aid, org=FakeOrg()) == "bob-from-contacts"
    assert recipient_label(baser, aid) == aid[:12] + "…"
