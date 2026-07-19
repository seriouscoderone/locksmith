"""Parse a raw witness-less OOBI CESR stream (KEL + role auth + loc
scheme) into a Habery. Shared by the offline pairing blob
(cesr_blob.import_peer_blob) and the HOA's bundled-OOBI pairing
(core.direct_transport). Same v1-hold pinning as the blob path — grep
TRANSITIONAL in cesr_blob for the lift condition."""
from __future__ import annotations

from keri import Vrsn_1_0, help, kering
from keri.core import eventing, parsing, routing

from locksmith.peer.cesr_blob import PeerBlobError

logger = help.ogler.getLogger(__name__)


def parse_oobi_cesr(hby, cesr: bytes) -> str:
    db = hby.db
    rvy = routing.Revery(db=db)
    kvy = eventing.Kevery(db=db, lax=True, local=False, rvy=rvy)
    kvy.registerReplyRoutes(router=rvy.rtr)
    parser = parsing.Parser(kvy=kvy, rvy=rvy, version=Vrsn_1_0)

    pre_kevers = set(hby.kevers.keys())
    try:
        parser.parse(ims=bytearray(cesr), kvy=kvy, rvy=rvy)
    except Exception as e:  # noqa: BLE001
        raise PeerBlobError(
            "parse_failed",
            f"Couldn't parse the OOBI stream: {e}.")

    for pre in hby.kevers.keys():
        if pre in pre_kevers:
            continue
        loc = hby.db.locs.get(keys=(pre, kering.Schemes.tcp))
        if loc is not None and loc.url:
            logger.info(f"peer.oobi.imported aid={pre} endpoint={loc.url}")
            return pre

    raise PeerBlobError(
        "no_peer_role",
        "The stream parsed but no new AID published a peer-role tcp "
        "endpoint.")
