"""Parse a raw witness-less OOBI CESR stream (KEL + role auth + loc
scheme) into a Habery. Shared by the offline pairing blob
(cesr_blob.import_peer_blob) and the HOA's bundled-OOBI pairing
(core.direct_transport). Same v1-hold pinning as the blob path — grep
TRANSITIONAL in cesr_blob for the lift condition."""
from __future__ import annotations

from keri import Vrsn_1_0, help, kering
from keri.core import eventing, parsing, routing

from locksmith.peer.cesr_blob import PeerBlobError
from locksmith.peer.resolution import resolve_peer_endpoints

logger = help.ogler.getLogger(__name__)


def _endpoint_state(db) -> set[tuple]:
    """Snapshot of every endpoint record, for "did this stream land anything?".

    Values, not counts: BADA supersedure replaces a url or flips an
    authorization in place without changing how many records there are.
    """
    state: set[tuple] = set()
    try:
        for keys, end in db.ends.getTopItemIter(keys=()):
            state.add(("end", tuple(keys), bool(end.enabled), bool(end.allowed)))
        for keys, loc in db.locs.getTopItemIter(keys=()):
            state.add(("loc", tuple(keys), loc.url))
    except Exception:  # noqa: BLE001 — db can race shut during vault flips
        pass
    return state


def parse_oobi_cesr(hby, cesr: bytes, *, expect: str | None = None) -> str:
    """Parse an OOBI CESR stream into `hby` and return the peer AID it carries.

    Without ``expect`` the answer is "whichever AID this stream introduced
    that published a tcp peer endpoint" — the first-contact case.

    With ``expect`` the answer is that AID specifically, whether or not the
    stream introduced it. Re-reading a bundled artifact for an AID the vault
    already knows adds no new kever, and the discovery form would report that
    as ``no_peer_role``; ``expect`` is what makes re-pairing (a re-baked
    authority OOBI whose /loc/scheme now names a different address) possible
    at all. Supersedure is BADA's: a later-dated rpy wins.

    An AID "published a tcp peer endpoint" is resolved natively —
    ``cid -> ends[peer] -> eid -> locs[eid]`` (``peer.resolution``) — so an
    endpoint provider that is its own identifier works, and a location that
    arrived without the authorization that vouches for it does not count.

    Raises ``PeerBlobError`` whose ``reason`` distinguishes three outcomes:

    * ``parse_failed`` — the parser itself raised.
    * ``damaged_stream`` — the parser consumed the stream without complaint but
      **nothing landed**. keripy's ``Parser.parse`` swallows per-message framing
      errors, so a blob damaged in transit desynchronizes and silently produces
      no state. This used to be reported as ``no_peer_role``, i.e. byte damage
      blamed on the other operator's configuration.
    * ``no_peer_role`` — something landed, but the AID has no peer endpoint.
      Genuinely ambiguous when damage is late in the stream (the KEL lands, the
      endpoint rpys don't), so the message names both possibilities.
    """
    db = hby.db
    rvy = routing.Revery(db=db)
    kvy = eventing.Kevery(db=db, lax=True, local=False, rvy=rvy)
    kvy.registerReplyRoutes(router=rvy.rtr)
    parser = parsing.Parser(kvy=kvy, rvy=rvy, version=Vrsn_1_0)

    pre_kevers = set(hby.kevers.keys())
    pre_endpoints = _endpoint_state(db)
    try:
        parser.parse(ims=bytearray(cesr), kvy=kvy, rvy=rvy)
    except Exception as e:  # noqa: BLE001
        raise PeerBlobError(
            "parse_failed",
            f"Couldn't parse the blob: {e}. The token may be corrupted.")

    new_kevers = [p for p in hby.kevers.keys() if p not in pre_kevers]
    candidates = [expect] if expect is not None else new_kevers
    for pre in candidates:
        endpoints = resolve_peer_endpoints(db, pre)
        if endpoints:
            eid, url = endpoints[0]
            logger.info(f"peer.oobi.imported aid={pre} eid={eid} endpoint={url}")
            return pre

    # Success is checked first so an idempotent re-parse of a good blob — which
    # changes nothing, because BADA rejects a same-dated update — is not mistaken
    # for a damaged one.
    if not new_kevers and _endpoint_state(db) == pre_endpoints:
        raise PeerBlobError(
            "damaged_stream",
            "This pairing token appears to be damaged — nothing in it was "
            "accepted. Copy the whole token again and retry; even one changed "
            "or missing character invalidates it.")

    raise PeerBlobError(
        "no_peer_role",
        "The blob parsed but no AID inside it published a peer-role tcp "
        "endpoint. Either the peer doesn't have 'Expose over peer mode' enabled "
        "on any identifier, or the token was damaged in transit — if you expect "
        "it to be enabled, re-copy the whole token and retry.")
