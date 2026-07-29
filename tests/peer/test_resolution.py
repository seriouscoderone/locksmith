"""Native peer-endpoint resolution: cid -> ends[peer] -> eid -> locs[eid].

This is the resolution keripy already does for the mailbox and witness roles
(``forwarding.py`` via ``hab.endsFor``). The peer path used to skip it and read
``db.locs.get(keys=(aid, tcp))`` directly, which only worked because it also
published ``eid == cid``.

Two properties matter and both are tested here against a real Habery:

* the **new** shape (a distinct listener EID) resolves, and
* the **old** shape (``eid == cid``, what every shipped install holds) still
  resolves, because it is a degenerate case of the same walk. That is what makes
  the migration free.
"""
from __future__ import annotations

import pytest
from keri import Vrsn_1_0, kering
from keri.app import habbing

from locksmith.peer.resolution import (
    peer_role_eids, resolve_peer_endpoint, resolve_peer_endpoints,
)

NEW_URL = "tcp://192.168.1.50:5622"
OLD_URL = "tcp://192.168.1.51:5621"


@pytest.fixture()
def hby():
    with habbing.openHby(name="res", temp=True, version=Vrsn_1_0) as h:
        yield h


def _publish(hby, signer_hab, ctrl_hab, eid: str, url: str, allow: bool = True):
    """Land a /loc/scheme signed by the endpoint provider plus the controller's
    /end/role authorization — what PublishPeerRoleDoer does locally."""
    msgs = [signer_hab.reply(
        route="/loc/scheme",
        data=dict(eid=eid, scheme=kering.Schemes.tcp, url=url))]
    msgs.append(ctrl_hab.reply(
        route="/end/role/add" if allow else "/end/role/cut",
        data=dict(cid=ctrl_hab.pre, role=kering.Roles.peer, eid=eid)))
    for msg in msgs:
        hby.psr.parse(ims=bytearray(msg))


def test_resolves_a_distinct_listener_eid(hby):
    ctrl = hby.makeHab(name="ctrl", transferable=True, version=Vrsn_1_0)
    lsn = hby.makeHab(name="lsn", transferable=False, ns="peer", version=Vrsn_1_0)
    _publish(hby, lsn, ctrl, lsn.pre, NEW_URL)

    assert resolve_peer_endpoints(hby.db, ctrl.pre) == [(lsn.pre, NEW_URL)]
    assert resolve_peer_endpoint(hby.db, ctrl.pre) == NEW_URL
    assert peer_role_eids(hby.db, ctrl.pre) == [lsn.pre]


def test_resolves_the_legacy_eid_equals_cid_shape(hby):
    """Every install shipped so far published eid == cid. Those records must keep
    resolving with no migration — the whole reason to go native rather than
    inventing a second lookup."""
    ctrl = hby.makeHab(name="legacy", transferable=True, version=Vrsn_1_0)
    _publish(hby, ctrl, ctrl, ctrl.pre, OLD_URL)

    assert resolve_peer_endpoints(hby.db, ctrl.pre) == [(ctrl.pre, OLD_URL)]
    assert resolve_peer_endpoint(hby.db, ctrl.pre) == OLD_URL


def test_a_cut_authorization_resolves_to_nothing(hby):
    """Revocation has to be effective through the resolver: /end/role/cut means
    not reachable, whatever db.locs still holds for that eid."""
    ctrl = hby.makeHab(name="cut", transferable=True, version=Vrsn_1_0)
    lsn = hby.makeHab(name="cutlsn", transferable=False, ns="peer", version=Vrsn_1_0)
    _publish(hby, lsn, ctrl, lsn.pre, NEW_URL)
    assert resolve_peer_endpoint(hby.db, ctrl.pre) == NEW_URL

    hby.psr.parse(ims=bytearray(ctrl.reply(
        route="/end/role/cut",
        data=dict(cid=ctrl.pre, role=kering.Roles.peer, eid=lsn.pre))))

    assert resolve_peer_endpoints(hby.db, ctrl.pre) == []
    assert resolve_peer_endpoint(hby.db, ctrl.pre) is None


def test_an_unauthorized_location_is_not_resolved(hby):
    """A /loc/scheme with no matching /end/role is an address nobody vouched for.

    This is reachable in practice: a peer-OOBI damaged in transit can land the
    loc while the authorization is dropped. Reading db.locs directly — what the
    old code did — returns that address as a success.
    """
    ctrl = hby.makeHab(name="unauth", transferable=True, version=Vrsn_1_0)
    lsn = hby.makeHab(name="unauthlsn", transferable=False, ns="peer",
                      version=Vrsn_1_0)
    hby.psr.parse(ims=bytearray(lsn.reply(
        route="/loc/scheme",
        data=dict(eid=lsn.pre, scheme=kering.Schemes.tcp, url=NEW_URL))))

    # The location is in the db...
    assert hby.db.locs.get(keys=(lsn.pre, kering.Schemes.tcp)).url == NEW_URL
    # ...but nothing authorizes it for this cid, so it does not resolve.
    assert resolve_peer_endpoints(hby.db, ctrl.pre) == []


def test_an_authorization_with_no_location_is_not_resolved(hby):
    ctrl = hby.makeHab(name="noloc", transferable=True, version=Vrsn_1_0)
    lsn = hby.makeHab(name="noloclsn", transferable=False, ns="peer",
                      version=Vrsn_1_0)
    hby.psr.parse(ims=bytearray(ctrl.reply(
        route="/end/role/add",
        data=dict(cid=ctrl.pre, role=kering.Roles.peer, eid=lsn.pre))))

    assert resolve_peer_endpoints(hby.db, ctrl.pre) == []


def test_other_roles_are_not_mistaken_for_peer(hby):
    ctrl = hby.makeHab(name="mbx", transferable=True, version=Vrsn_1_0)
    lsn = hby.makeHab(name="mbxlsn", transferable=False, ns="peer",
                      version=Vrsn_1_0)
    for msg in (
        lsn.reply(route="/loc/scheme",
                  data=dict(eid=lsn.pre, scheme=kering.Schemes.tcp, url=NEW_URL)),
        ctrl.reply(route="/end/role/add",
                   data=dict(cid=ctrl.pre, role=kering.Roles.mailbox, eid=lsn.pre)),
    ):
        hby.psr.parse(ims=bytearray(msg))

    assert resolve_peer_endpoints(hby.db, ctrl.pre) == []


def test_reports_every_authorized_route_not_just_the_first(hby):
    """db.locs is keyed (eid, scheme), so two tcp routes means two EIDs. The
    resolver returns all of them so multi-route selection has something to
    select from (backlog/2026-07-28-single-route-per-peer.md)."""
    ctrl = hby.makeHab(name="multi", transferable=True, version=Vrsn_1_0)
    lan = hby.makeHab(name="lan", transferable=False, ns="peer", version=Vrsn_1_0)
    relay = hby.makeHab(name="relay", transferable=False, ns="peer",
                        version=Vrsn_1_0)
    _publish(hby, lan, ctrl, lan.pre, NEW_URL)
    _publish(hby, relay, ctrl, relay.pre, OLD_URL)

    got = dict(resolve_peer_endpoints(hby.db, ctrl.pre))
    assert got == {lan.pre: NEW_URL, relay.pre: OLD_URL}


def test_unknown_cid_resolves_to_nothing(hby):
    assert resolve_peer_endpoints(hby.db, "E" + "Z" * 43) == []
    assert resolve_peer_endpoint(hby.db, "E" + "Z" * 43) is None


def test_the_most_recently_authorized_route_is_preferred(hby):
    """Ordering is load-bearing for the migration, because a cut does not travel.

    ``replyEndRole`` exports only *currently authorized* records, so when an
    authority retires its legacy ``eid == cid`` self-authorization the
    ``/end/role/cut`` is simply absent from the re-baked artifact — an install
    that already learned the old shape keeps holding it and ends up with two
    routes. Preferring the freshest authorization means the new address wins
    anyway, with the older one surviving as a lower-priority fallback.

    The ordering key is keripy's own: the datestamp it stored for the
    authorization rpy (``db.eans`` -> ``db.sdts``). Same "latest-seen" notion BADA
    already uses to decide which reply to accept.

    The two EIDs here are chosen so LMDB key order *contradicts* recency —
    otherwise this test passes on ``db.ends`` iteration order alone and proves
    nothing about the sort.
    """
    ctrl = hby.makeHab(name="fresh", transferable=True, version=Vrsn_1_0)
    one = hby.makeHab(name="lsn1", transferable=False, ns="peer",
                      version=Vrsn_1_0)
    two = hby.makeHab(name="lsn2", transferable=False, ns="peer",
                      version=Vrsn_1_0)
    # Publish the lower-sorting EID FIRST so it is both older and first in key
    # order; the newer route can then only come first if recency is what orders.
    older, newer = sorted([one, two], key=lambda h: h.pre)
    _publish(hby, older, ctrl, older.pre, OLD_URL)
    _publish(hby, newer, ctrl, newer.pre, NEW_URL)
    assert older.pre < newer.pre  # key order would put the OLDER one first

    endpoints = resolve_peer_endpoints(hby.db, ctrl.pre)
    assert len(endpoints) == 2, endpoints
    assert endpoints[0] == (newer.pre, NEW_URL), (
        f"expected the more recently authorized route first, got {endpoints}")
    assert resolve_peer_endpoint(hby.db, ctrl.pre) == NEW_URL


def test_a_stale_legacy_route_does_not_win_after_an_upgrade(hby):
    """The migration case end to end, at the resolver: an install holding the old
    eid == cid record learns a newer listener-EID authorization, and the address
    it dials is the new one."""
    ctrl = hby.makeHab(name="upg", transferable=True, version=Vrsn_1_0)
    lsn = hby.makeHab(name="upglsn", transferable=False, ns="peer",
                      version=Vrsn_1_0)
    _publish(hby, ctrl, ctrl, ctrl.pre, OLD_URL)     # legacy, learned first
    _publish(hby, lsn, ctrl, lsn.pre, NEW_URL)       # upgraded artifact

    assert resolve_peer_endpoint(hby.db, ctrl.pre) == NEW_URL
