# -*- encoding: utf-8 -*-
"""Tests for `locksmith.core.serviceaid_bridge._inband_oobi_msgs` (Task 7):
the in-band reply-as-OOBI rpys (spec Sec 6) a `ServiceaidGrantDoer` queues
on the grant's postman -- `/loc/scheme` by the EID, `/end/role/add` by the
CID -- so a first-contact recipient whose parser already verified the
sender's streamed KEL can also learn how to reach back. Gated on the vault's
peer-mode settings being enabled AND this AID having opted into peer
exposure (`is_aid_peer_exposed`) -- stock wallets without peer mode are
unaffected (empty list, no behavior change).

Built on a real Habery rather than a MagicMock hab. The rpys are no longer
re-signed here: they are the ones already published, loaded back out of the db,
so what matters is which records exist — something a mock cannot represent. It
also lets the decisive assertion be the real one: parse the output into a fresh
Habery and check the recipient can resolve a return address.
"""
import pytest
from hio.base import doing
from keri import Vrsn_1_0, kering
from keri.app import habbing
from keri.core import parsing, signing

from locksmith.core.serviceaid_bridge import _inband_oobi_msgs
from locksmith.peer.listener_eid import listener_eid
from locksmith.peer.publishing import PublishPeerRoleDoer
from locksmith.peer.records import PeerModeSettings
from locksmith.peer.resolution import resolve_peer_endpoints

URL = "tcp://192.168.1.20:5622"


@pytest.fixture()
def hby_hab():
    hby = habbing.Habery(
        name="inband", bran="A" * 21,
        salt=signing.Salter(raw=b"0123456789abcdef").qb64, temp=True,
        version=Vrsn_1_0,
    )
    try:
        yield hby, hby.makeHab(name="sender", isith="1", icount=1,
                               transferable=True, version=Vrsn_1_0)
    finally:
        hby.close()


def _expose(hby, hab, url=URL):
    doing.Doist(limit=4.0, tock=0.03125, real=False).do(
        doers=[PublishPeerRoleDoer(hby=hby, hab=hab, url=url)])


def test_disabled_settings_yield_nothing(hby_hab):
    hby, hab = hby_hab
    _expose(hby, hab)
    assert _inband_oobi_msgs(hab, PeerModeSettings(enabled=False)) == []
    assert _inband_oobi_msgs(hab, None) == []


def test_unexposed_hab_yields_nothing(hby_hab):
    """Never published a peer role, so there is nothing to advertise."""
    hby, hab = hby_hab
    assert _inband_oobi_msgs(hab, PeerModeSettings(enabled=True)) == []


def test_revoked_hab_yields_nothing(hby_hab):
    hby, hab = hby_hab
    _expose(hby, hab)
    assert _inband_oobi_msgs(hab, PeerModeSettings(enabled=True))
    doing.Doist(limit=4.0, tock=0.03125, real=False).do(
        doers=[PublishPeerRoleDoer(hby=hby, hab=hab, url=URL, allow=False)])
    assert _inband_oobi_msgs(hab, PeerModeSettings(enabled=True)) == []


def test_exposed_hab_yields_loc_and_endrole(hby_hab):
    hby, hab = hby_hab
    _expose(hby, hab)

    msgs = _inband_oobi_msgs(hab, PeerModeSettings(enabled=True, port=5622))
    routes = [serder.ked["r"] for serder, _atc in msgs]
    assert routes == ["/loc/scheme", "/end/role/add"]

    loc, end = (m[0].ked["a"] for m in msgs)
    eid = listener_eid(hby)
    assert loc == dict(eid=eid, scheme=kering.Schemes.tcp, url=URL)
    assert end == dict(cid=hab.pre, role=kering.Roles.peer, eid=eid)


def test_the_advertised_endpoint_is_the_one_actually_published(hby_hab):
    """The address comes from what was published, not from `settings`. A stale or
    blank advertised_host in settings cannot make this rpy disagree with the
    endpoint the vault has actually authorized."""
    hby, hab = hby_hab
    _expose(hby, hab, url="tcp://10.1.2.3:7777")

    msgs = _inband_oobi_msgs(
        hab, PeerModeSettings(enabled=True, port=5622, advertised_host=""))
    assert msgs[0][0].ked["a"]["url"] == "tcp://10.1.2.3:7777"


def test_it_does_not_republish_the_legacy_self_endpoint(hby_hab):
    """Regression: re-signing `eid=hab.pre` here would resurrect, on every send,
    the legacy self-authorization PublishPeerRoleDoer retires on upgrade."""
    hby, hab = hby_hab
    # A vault that once published the old shape, then upgraded.
    for msg in (
        hab.reply(route="/loc/scheme",
                  data=dict(eid=hab.pre, scheme=kering.Schemes.tcp,
                            url="tcp://10.9.9.9:5621")),
        hab.reply(route="/end/role/add",
                  data=dict(cid=hab.pre, role=kering.Roles.peer, eid=hab.pre)),
    ):
        hby.psr.parse(ims=bytearray(msg))
    _expose(hby, hab)

    msgs = _inband_oobi_msgs(hab, PeerModeSettings(enabled=True, port=5622))
    advertised = {m[0].ked["a"].get("eid") for m in msgs}
    assert advertised == {listener_eid(hby)}
    assert hab.pre not in advertised


def test_a_recipient_can_resolve_the_return_address_from_these_rpys(hby_hab):
    """What the whole mechanism is for: a first-contact recipient parses these and
    can dial back. Asserting on the recipient's resolved endpoint is the only
    assertion that proves the rpys are well-formed AND correctly signed."""
    hby, hab = hby_hab
    _expose(hby, hab)
    msgs = _inband_oobi_msgs(hab, PeerModeSettings(enabled=True, port=5622))

    stream = bytearray(hab.replay(hab.pre))
    for serder, atc in msgs:
        stream.extend(serder.raw)
        if atc:
            stream.extend(atc)

    with habbing.openHby(name="inbandrecip", temp=True) as recip:
        from keri.core import eventing, routing
        rvy = routing.Revery(db=recip.db)
        kvy = eventing.Kevery(db=recip.db, lax=True, local=False, rvy=rvy)
        kvy.registerReplyRoutes(router=rvy.rtr)
        parsing.Parser(kvy=kvy, rvy=rvy, version=Vrsn_1_0).parse(
            ims=stream, kvy=kvy, rvy=rvy)

        assert hab.pre in recip.kevers
        assert resolve_peer_endpoints(recip.db, hab.pre) == [
            (listener_eid(hby), URL)]
