"""Pure-parse tests: no sockets, no Qt. Uses two in-process Haberies —
exporter publishes its peer role locally (the PublishPeerRoleDoer local
landing, done directly via hab.reply parsing), importer consumes."""
import pytest
from keri import Vrsn_1_0, kering
from keri.app import habbing

from locksmith.peer.cesr_blob import PeerBlobError, export_peer_blob, import_peer_blob
from locksmith.peer.oobi_import import parse_oobi_cesr


@pytest.fixture()
def exporter_cesr():
    # Pin the exporter to v1: parse_oobi_cesr hardcodes version=Vrsn_1_0 (the
    # v1-hold — see the TRANSITIONAL comment in cesr_blob.py). openHby's
    # protocol-version default is v2, so without this pin hab.reply()/
    # replyToOobi() would emit v2-framed messages that the v1 parser
    # silently fails to route (no exception, just no landed loc — the same
    # failure mode the v1-hold comment warns about).
    with habbing.openHby(name="exp", temp=True, version=Vrsn_1_0) as hby:
        hab = hby.makeHab(name="exp", transferable=True, version=Vrsn_1_0)
        for msg in (
            hab.reply(route="/loc/scheme",
                      data=dict(eid=hab.pre, scheme=kering.Schemes.tcp,
                                url="tcp://127.0.0.1:5621")),
            hab.reply(route="/end/role/add",
                      data=dict(cid=hab.pre, role=kering.Roles.peer, eid=hab.pre)),
        ):
            hby.psr.parse(ims=bytearray(msg))
        cesr = hab.replyToOobi(aid=hab.pre, role=kering.Roles.peer)
        yield hab.pre, bytes(cesr)


def test_parse_lands_kel_and_tcp_loc(exporter_cesr):
    aid, cesr = exporter_cesr
    with habbing.openHby(name="imp", temp=True) as hby:
        got = parse_oobi_cesr(hby, cesr)
        assert got == aid
        assert aid in hby.kevers
        loc = hby.db.locs.get(keys=(aid, kering.Schemes.tcp))
        assert loc is not None and loc.url == "tcp://127.0.0.1:5621"


def _publish_peer_loc(hby, hab, url: str) -> bytes:
    """Land a fresh /loc/scheme + /end/role/add for `url` and export the
    resulting peer OOBI — what a re-baked brand artifact is."""
    for msg in (
        hab.reply(route="/loc/scheme",
                  data=dict(eid=hab.pre, scheme=kering.Schemes.tcp, url=url)),
        hab.reply(route="/end/role/add",
                  data=dict(cid=hab.pre, role=kering.Roles.peer, eid=hab.pre)),
    ):
        hby.psr.parse(ims=bytearray(msg))
    return bytes(hab.replyToOobi(aid=hab.pre, role=kering.Roles.peer))


@pytest.fixture()
def exporter():
    with habbing.openHby(name="exp2", temp=True, version=Vrsn_1_0) as hby:
        hab = hby.makeHab(name="exp2", transferable=True, version=Vrsn_1_0)
        yield hby, hab


def test_reparsing_a_known_aid_is_idempotent(exporter_cesr):
    """Re-pairing has to be able to re-read the bundled artifact on every
    vault open. The first parse makes the AID known, so a second parse adds
    no NEW kever — that must not be mistaken for "no peer role in the blob"."""
    aid, cesr = exporter_cesr
    with habbing.openHby(name="imp4", temp=True) as hby:
        assert parse_oobi_cesr(hby, cesr) == aid
        assert parse_oobi_cesr(hby, cesr, expect=aid) == aid


def test_reparse_supersedes_a_changed_endpoint(exporter):
    """The whole point of re-baking an authority OOBI: a later-dated
    /loc/scheme replaces the endpoint an install already learned."""
    hby, hab = exporter
    old = _publish_peer_loc(hby, hab, "tcp://127.0.0.1:5621")
    new = _publish_peer_loc(hby, hab, "tcp://192.168.1.20:5621")
    with habbing.openHby(name="imp5", temp=True) as imp:
        parse_oobi_cesr(imp, old)
        assert imp.db.locs.get(
            keys=(hab.pre, kering.Schemes.tcp)).url == "tcp://127.0.0.1:5621"
        parse_oobi_cesr(imp, new, expect=hab.pre)
        assert imp.db.locs.get(
            keys=(hab.pre, kering.Schemes.tcp)).url == "tcp://192.168.1.20:5621"


def test_expect_raises_when_that_aid_has_no_peer_loc(exporter_cesr):
    aid, cesr = exporter_cesr
    other = "E" + "Z" * 43
    with habbing.openHby(name="imp6", temp=True) as hby:
        with pytest.raises(PeerBlobError) as ei:
            parse_oobi_cesr(hby, cesr, expect=other)
        assert ei.value.reason == "no_peer_role"


def test_garbage_raises_parse_failed():
    with habbing.openHby(name="imp2", temp=True) as hby:
        with pytest.raises(PeerBlobError) as ei:
            parse_oobi_cesr(hby, b"\x00not-cesr")
        assert ei.value.reason in ("parse_failed", "no_peer_role")


def test_blob_import_delegates_to_helper(exporter_cesr):
    aid, cesr = exporter_cesr
    import base64
    blob = "locksmith-peer-oobi:v1:" + base64.b64encode(cesr).decode("ascii")
    with habbing.openHby(name="imp3", temp=True) as hby:
        assert import_peer_blob(hby, blob) == aid
