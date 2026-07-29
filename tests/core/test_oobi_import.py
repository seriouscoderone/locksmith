"""Pure-parse tests: no sockets, no Qt. Uses two in-process Haberies —
exporter publishes its peer role locally (the PublishPeerRoleDoer local
landing, done directly via hab.reply parsing), importer consumes."""
import pytest
from keri import Vrsn_1_0, kering
from keri.app import habbing

from locksmith.peer.cesr_blob import PeerBlobError, export_peer_blob, import_peer_blob
from locksmith.peer.oobi_import import parse_oobi_cesr
from locksmith.peer.resolution import resolve_peer_endpoints


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
        assert ei.value.reason in ("parse_failed", "damaged_stream")


# --- new-shape (distinct listener EID) artifacts, and migration ---------------


def _publish_via_listener(hby, hab, listener, url: str) -> bytes:
    """Publish the CURRENT shape: /loc/scheme signed by a separate listener EID,
    /end/role/add authorizing it. Returns the exported peer OOBI."""
    for msg in (
        listener.reply(route="/loc/scheme",
                       data=dict(eid=listener.pre, scheme=kering.Schemes.tcp,
                                 url=url)),
        hab.reply(route="/end/role/add",
                  data=dict(cid=hab.pre, role=kering.Roles.peer,
                            eid=listener.pre)),
    ):
        hby.psr.parse(ims=bytearray(msg))
    return bytes(hab.replyToOobi(aid=hab.pre, role=kering.Roles.peer))


@pytest.fixture()
def exporter_with_listener():
    with habbing.openHby(name="exp3", temp=True, version=Vrsn_1_0) as hby:
        hab = hby.makeHab(name="exp3", transferable=True, version=Vrsn_1_0)
        lsn = hby.makeHab(name="exp3lsn", transferable=False, ns="peer",
                          version=Vrsn_1_0)
        yield hby, hab, lsn


def test_parses_an_artifact_whose_endpoint_is_a_separate_eid(exporter_with_listener):
    """The endpoint provider is its own identifier, so the importer has to walk
    cid -> ends[peer] -> eid -> locs rather than look for a loc under the cid."""
    hby, hab, lsn = exporter_with_listener
    cesr = _publish_via_listener(hby, hab, lsn, "tcp://192.168.1.30:5622")
    with habbing.openHby(name="impn1", temp=True) as imp:
        assert parse_oobi_cesr(imp, cesr) == hab.pre
        assert resolve_peer_endpoints(imp.db, hab.pre) == [
            (lsn.pre, "tcp://192.168.1.30:5622")]
        # Nothing is published under the AID itself any more.
        assert imp.db.locs.get(keys=(hab.pre, kering.Schemes.tcp)) is None


def test_an_install_on_the_old_shape_upgrades_to_the_new_one(exporter_with_listener):
    """The migration path an already-shipped install actually walks: it learned an
    eid == cid endpoint, then the authority re-bakes under a listener EID.

    Note what the install ends up holding. The authority DID retire its legacy
    self-authorization — but ``replyEndRole`` exports only currently-authorized
    records, so the ``/end/role/cut`` is not in the artifact and the install never
    hears about it. It keeps the old record and now has two routes. What makes the
    upgrade land anyway is preference order: the more recently authorized route is
    the one dialed, and the stale one degrades to a fallback rather than
    shadowing it. See backlog/2026-07-28-endrole-cut-does-not-propagate.md.
    """
    hby, hab, lsn = exporter_with_listener
    old = _publish_peer_loc(hby, hab, "tcp://192.168.1.20:5621")

    with habbing.openHby(name="impn2", temp=True) as imp:
        parse_oobi_cesr(imp, old)
        assert resolve_peer_endpoints(imp.db, hab.pre) == [
            (hab.pre, "tcp://192.168.1.20:5621")]

        # Authority re-publishes under a listener EID and retires the legacy
        # self-authorization, exactly as PublishPeerRoleDoer now does.
        for msg in (
            lsn.reply(route="/loc/scheme",
                      data=dict(eid=lsn.pre, scheme=kering.Schemes.tcp,
                                url="tcp://192.168.1.30:5622")),
            hab.reply(route="/end/role/add",
                      data=dict(cid=hab.pre, role=kering.Roles.peer,
                                eid=lsn.pre)),
            hab.reply(route="/end/role/cut",
                      data=dict(cid=hab.pre, role=kering.Roles.peer,
                                eid=hab.pre)),
            hab.reply(route="/loc/scheme",
                      data=dict(eid=hab.pre, scheme=kering.Schemes.tcp, url="")),
        ):
            hby.psr.parse(ims=bytearray(msg))
        # The exporter's own state is clean: one live route.
        assert resolve_peer_endpoints(hby.db, hab.pre) == [
            (lsn.pre, "tcp://192.168.1.30:5622")]
        new = bytes(hab.replyToOobi(aid=hab.pre, role=kering.Roles.peer))
        assert b"/end/role/cut" not in new, (
            "if cuts ever start being exported, the lingering-stale-route "
            "workaround below can be simplified")

        parse_oobi_cesr(imp, new, expect=hab.pre)
        endpoints = resolve_peer_endpoints(imp.db, hab.pre)
        assert endpoints[0] == (lsn.pre, "tcp://192.168.1.30:5622"), endpoints
        # The retired route lingers, unheard-of cut and all, as a fallback only.
        assert (hab.pre, "tcp://192.168.1.20:5621") in endpoints


# --- error attribution: damaged stream vs genuinely-unexposed peer ------------


def _duplicate_char_at(blob: bytes, offset: int) -> bytes:
    """Duplicate one byte — the corruption a real re-bake hit in transit, where
    three CESR couples each gained a repeated character."""
    return blob[:offset] + blob[offset:offset + 1] + blob[offset:]


def test_a_damaged_blob_is_reported_as_damaged_not_as_no_peer_role(exporter_cesr):
    """The incident this pins: a peer OOBI corrupted in transit (duplicated
    characters inside CESR couples) desynchronized the stream, keripy's
    Parser.parse swallowed the per-message framing errors, nothing landed, and
    the operator was told *"The peer may not have 'Expose over peer mode'
    enabled"* — sending them to change settings on a machine that was fine.

    Byte damage and a misconfigured peer are different problems with different
    fixes, so they must not share an error.
    """
    aid, good = exporter_cesr
    damaged = _duplicate_char_at(good, 62)
    with habbing.openHby(name="impc1", temp=True) as hby:
        with pytest.raises(PeerBlobError) as ei:
            parse_oobi_cesr(hby, damaged)
        assert ei.value.reason == "damaged_stream", (
            f"got {ei.value.reason!r}: {ei.value}")
        assert aid not in hby.kevers  # nothing landed at all


def test_a_damaged_blob_is_still_damaged_when_an_aid_is_expected(exporter_cesr):
    """The HOA re-reads a bundled artifact with expect=<authority>; a damaged
    bundle must not be reported as the authority having disabled peer mode."""
    aid, good = exporter_cesr
    damaged = _duplicate_char_at(good, 62)
    with habbing.openHby(name="impc2", temp=True) as hby:
        with pytest.raises(PeerBlobError) as ei:
            parse_oobi_cesr(hby, damaged, expect=aid)
        assert ei.value.reason == "damaged_stream"


def test_an_intact_blob_from_an_unexposed_aid_still_says_no_peer_role(exporter_cesr):
    """The truthful case for the original message: the stream landed fine, the
    AID just has no peer role."""
    aid, cesr = exporter_cesr
    other = "E" + "Z" * 43
    with habbing.openHby(name="impc3", temp=True) as hby:
        with pytest.raises(PeerBlobError) as ei:
            parse_oobi_cesr(hby, cesr, expect=other)
        assert ei.value.reason == "no_peer_role"


def test_a_partially_landed_blob_admits_damage_as_a_possibility(exporter_cesr):
    """Damage late in the stream lands the KEL and drops the endpoint rpys, which
    is genuinely indistinguishable from an unexposed peer. The message must not
    claim certainty it doesn't have."""
    aid, good = exporter_cesr
    damaged = _duplicate_char_at(good, int(len(good) * 0.8))
    with habbing.openHby(name="impc4", temp=True) as hby:
        with pytest.raises(PeerBlobError) as ei:
            parse_oobi_cesr(hby, damaged)
        assert aid in hby.kevers          # the KEL did land
        assert ei.value.reason == "no_peer_role"
        assert "damaged" in str(ei.value).lower()


def test_a_location_without_its_authorization_is_not_accepted(exporter_with_listener):
    """Corruption can land a /loc/scheme while dropping the /end/role/add that
    authorizes it. Reading db.locs directly — the old behaviour — pairs the peer
    at an address nobody vouched for."""
    hby, hab, lsn = exporter_with_listener
    for msg in (
        lsn.reply(route="/loc/scheme",
                  data=dict(eid=lsn.pre, scheme=kering.Schemes.tcp,
                            url="tcp://192.168.1.30:5622")),
        hab.reply(route="/end/role/add",
                  data=dict(cid=hab.pre, role=kering.Roles.peer, eid=lsn.pre)),
    ):
        hby.psr.parse(ims=bytearray(msg))
    # Ship the KEL and the location, but withhold the authorization.
    partial = bytes(hab.replay(hab.pre)) + bytes(
        hab.loadLocScheme(eid=lsn.pre, scheme=kering.Schemes.tcp))

    with habbing.openHby(name="impc5", temp=True) as imp:
        with pytest.raises(PeerBlobError) as ei:
            parse_oobi_cesr(imp, partial, expect=hab.pre)
        assert ei.value.reason == "no_peer_role"
        assert resolve_peer_endpoints(imp.db, hab.pre) == []


def test_blob_import_delegates_to_helper(exporter_cesr):
    aid, cesr = exporter_cesr
    import base64
    blob = "locksmith-peer-oobi:v1:" + base64.b64encode(cesr).decode("ascii")
    with habbing.openHby(name="imp3", temp=True) as hby:
        assert import_peer_blob(hby, blob) == aid
