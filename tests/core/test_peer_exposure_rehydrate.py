# -*- encoding: utf-8 -*-
"""The inbound destination gate (`_peer_exposed_aids`, shim gate 2) must be
REHYDRATED from the persisted peer-role end records on vault-open. Without
it, an AID exposed in a prior session silently loses exposure across an app
restart and the shim drops every inbound exn to it
(`peer.gate.destination_not_exposed`) -- credential presentation over peer
transport breaks after a restart. Regression for the live-demo blocker (the
relaunched DOI dropped the carrier's grant).

Uses a real temp Habery + real keripy end-role publication (no sockets, no
Qt), then exercises the exact seeding expression Vault.__init__ uses.
"""
from keri import kering
from keri.app import habbing

from locksmith.peer import exposure as peer_exposure


def _expose(hab, hby):
    """Publish a peer-role end + tcp loc for hab, landing the end records in
    hab.db.ends the same way PublishPeerRoleDoer does."""
    for msg in (
        hab.reply(route="/loc/scheme",
                  data=dict(eid=hab.pre, scheme=kering.Schemes.tcp,
                            url="tcp://127.0.0.1:5621")),
        hab.reply(route="/end/role/add",
                  data=dict(cid=hab.pre, role=kering.Roles.peer, eid=hab.pre)),
    ):
        hby.psr.parse(ims=bytearray(msg))


def test_exposed_pres_reflects_persisted_end_record():
    with habbing.openHby(name="exp", temp=True) as hby:
        hab = hby.makeHab(name="doi", transferable=True)
        assert peer_exposure.exposed_pres(hby) == []      # not exposed yet
        _expose(hab, hby)
        assert peer_exposure.exposed_pres(hby) == [hab.pre]  # now exposed
        # This is exactly what Vault.__init__ now seeds _peer_exposed_aids with:
        seeded = set(peer_exposure.exposed_pres(hby))
        assert hab.pre in seeded


def test_fresh_habery_seeds_empty():
    with habbing.openHby(name="exp2", temp=True) as hby:
        hby.makeHab(name="doi2", transferable=True)
        assert set(peer_exposure.exposed_pres(hby)) == set()   # nothing published
