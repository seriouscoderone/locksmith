"""PublishPeerRoleDoer publishes under a real listener EID — and retires the
legacy self-authorization an already-shipped vault is holding.

Run against a real Habery with no witnesses, so the doer takes its
``no_witnesses`` path and we assert on what actually landed in db.ends/db.locs
rather than on what was handed to a fake messenger.
"""
from __future__ import annotations

import pytest
from hio.base import doing
from keri import Vrsn_1_0, kering
from keri.app import habbing
from keri.core import signing

from locksmith.peer.listener_eid import listener_eid
from locksmith.peer.publishing import PublishPeerRoleDoer
from locksmith.peer.resolution import resolve_peer_endpoints

URL = "tcp://192.168.1.42:5621"


@pytest.fixture()
def hby_hab():
    hby = habbing.Habery(
        name="pubeid", bran="A" * 21,
        salt=signing.Salter(raw=b"0123456789abcdef").qb64, temp=True,
        version=Vrsn_1_0,
    )
    try:
        hab = hby.makeHab(name="alice", isith="1", icount=1, transferable=True,
                          version=Vrsn_1_0)
        yield hby, hab
    finally:
        hby.close()


def _run(doer):
    doing.Doist(limit=4.0, tock=0.03125, real=False).do(doers=[doer])


def _publish(hby, hab, url=URL, allow=True):
    doer = PublishPeerRoleDoer(hby=hby, hab=hab, url=url, allow=allow)
    _run(doer)
    return doer


def test_publishes_the_location_under_the_listener_eid_not_the_aid(hby_hab):
    hby, hab = hby_hab
    _publish(hby, hab)

    eid = listener_eid(hby)
    assert eid is not None and eid != hab.pre

    loc = hby.db.locs.get(keys=(eid, kering.Schemes.tcp))
    assert loc is not None and loc.url == URL
    # The AID itself is no longer a location — that was the bug.
    assert hby.db.locs.get(keys=(hab.pre, kering.Schemes.tcp)) is None


def test_authorizes_the_listener_eid_for_the_aid(hby_hab):
    hby, hab = hby_hab
    _publish(hby, hab)

    eid = listener_eid(hby)
    end = hby.db.ends.get(keys=(hab.pre, kering.Roles.peer, eid))
    assert end is not None
    assert end.enabled or end.allowed
    assert resolve_peer_endpoints(hby.db, hab.pre) == [(eid, URL)]


def test_two_aids_in_one_vault_share_the_listener(hby_hab):
    """The socket is per-vault, so a second exposed AID authorizes the SAME EID
    rather than minting a second one. This is the co-location correlation handle
    the design accepts deliberately — see the spec's correlation decision."""
    hby, hab = hby_hab
    bob = hby.makeHab(name="bob", isith="1", icount=1, transferable=True,
                      version=Vrsn_1_0)
    _publish(hby, hab)
    _publish(hby, bob)

    eid = listener_eid(hby)
    assert resolve_peer_endpoints(hby.db, hab.pre) == [(eid, URL)]
    assert resolve_peer_endpoints(hby.db, bob.pre) == [(eid, URL)]


def test_revoking_cuts_the_authorization(hby_hab):
    hby, hab = hby_hab
    _publish(hby, hab)
    assert resolve_peer_endpoints(hby.db, hab.pre)

    _publish(hby, hab, allow=False)
    assert resolve_peer_endpoints(hby.db, hab.pre) == []


def test_revoking_one_aid_leaves_the_other_reachable(hby_hab):
    """Why revoke no longer nullifies the location: the location belongs to the
    vault's shared listener, so voiding it because ONE AID stopped exposing would
    silently unreach every other exposed AID in the same vault."""
    hby, hab = hby_hab
    bob = hby.makeHab(name="bob2", isith="1", icount=1, transferable=True,
                      version=Vrsn_1_0)
    _publish(hby, hab)
    _publish(hby, bob)

    _publish(hby, hab, allow=False)

    assert resolve_peer_endpoints(hby.db, hab.pre) == []
    assert resolve_peer_endpoints(hby.db, bob.pre) == [(listener_eid(hby), URL)]


def test_republishing_retires_a_legacy_self_authorization(hby_hab):
    """Migration for already-shipped vaults.

    An install that published the old shape holds ``ends[(cid, peer, cid)]``
    allowed and ``locs[(cid, tcp)]``. Re-publishing under the new shape must not
    leave that standing, or the vault advertises TWO endpoints and a remote can
    resolve the stale one. Supersedure is BADA's — a later-dated rpy wins — the
    same mechanism test_oobi_import pins for re-baked artifacts.
    """
    hby, hab = hby_hab
    legacy_url = "tcp://10.0.0.9:5621"
    for msg in (
        hab.reply(route="/loc/scheme",
                  data=dict(eid=hab.pre, scheme=kering.Schemes.tcp,
                            url=legacy_url)),
        hab.reply(route="/end/role/add",
                  data=dict(cid=hab.pre, role=kering.Roles.peer, eid=hab.pre)),
    ):
        hby.psr.parse(ims=bytearray(msg))
    assert resolve_peer_endpoints(hby.db, hab.pre) == [(hab.pre, legacy_url)]

    _publish(hby, hab)

    eid = listener_eid(hby)
    # Exactly one route, under the listener EID — the legacy one is gone.
    assert resolve_peer_endpoints(hby.db, hab.pre) == [(eid, URL)]
    legacy_end = hby.db.ends.get(keys=(hab.pre, kering.Roles.peer, hab.pre))
    assert not (legacy_end.enabled or legacy_end.allowed)
    legacy_loc = hby.db.locs.get(keys=(hab.pre, kering.Schemes.tcp))
    assert legacy_loc is None or not legacy_loc.url


def test_publishing_without_a_legacy_record_emits_no_migration_rpys(hby_hab):
    """The migration is conditional: a fresh vault has nothing to retire and must
    not publish a cut for an authorization that never existed."""
    hby, hab = hby_hab
    doer = _publish(hby, hab)
    assert doer.migrated is False

    hby2_hab = hby.makeHab(name="carol", isith="1", icount=1, transferable=True,
                           version=Vrsn_1_0)
    for msg in (
        hby2_hab.reply(route="/loc/scheme",
                       data=dict(eid=hby2_hab.pre, scheme=kering.Schemes.tcp,
                                 url="tcp://10.0.0.8:5621")),
        hby2_hab.reply(route="/end/role/add",
                       data=dict(cid=hby2_hab.pre, role=kering.Roles.peer,
                                 eid=hby2_hab.pre)),
    ):
        hby.psr.parse(ims=bytearray(msg))
    doer2 = _publish(hby, hby2_hab)
    assert doer2.migrated is True


def test_the_published_oobi_resolves_natively_in_a_fresh_wallet(hby_hab):
    """End to end: what a peer receives must resolve to the same address without
    the peer holding any of our other state."""
    hby, hab = hby_hab
    _publish(hby, hab)
    cesr = bytes(hab.replyToOobi(aid=hab.pre, role=kering.Roles.peer))
    assert cesr

    from locksmith.peer.oobi_import import parse_oobi_cesr
    with habbing.openHby(name="freshimp", temp=True) as imp:
        assert parse_oobi_cesr(imp, cesr) == hab.pre
        assert resolve_peer_endpoints(imp.db, hab.pre) == [(listener_eid(hby), URL)]
