"""Witness-less peer pairing via self-contained CESR blob.

The witness-served OOBI URL is the spec's MVP option (§4a.i), but in
practice most production witnesses do not propagate role authorization
reply messages — only the KEL inception. The dialog therefore can't
auto-discover the peer's TCP endpoint from a witness-served peer-OOBI.

This module provides a witness-less alternative (§4a.ii in the spec):
the exporting wallet generates a base64-encoded CESR stream containing
the AID's KEL + the role=peer authorization + the tcp:// loc scheme.
The importing wallet parses the blob into its Habery, populating
kevers + locs with no witness round-trip required.

The blob format is a short text token: ``locksmith-peer-oobi:v1:<b64>``.
The prefix lets the Add Peer dialog auto-detect blob vs URL input.
"""
from __future__ import annotations

import base64

from keri import Vrsn_1_0, help, kering
from keri.core import eventing, parsing, routing

logger = help.ogler.getLogger(__name__)


BLOB_PREFIX = "locksmith-peer-oobi:v1:"


def export_peer_blob(hab) -> str:
    """Build a witness-less peer-OOBI blob for the given hab.

    Returns a token of the form ``locksmith-peer-oobi:v1:<base64>``.
    The base64 payload is the CESR stream from ``hab.replyToOobi`` for
    the peer role — KEL events + role auth + loc scheme + sigs.
    """
    cesr = hab.replyToOobi(aid=hab.pre, role=kering.Roles.peer)
    if not cesr:
        raise ValueError(
            "replyToOobi returned empty; AID is not exposed for peer role"
        )
    encoded = base64.b64encode(bytes(cesr)).decode("ascii")
    return f"{BLOB_PREFIX}{encoded}"


def is_peer_blob(text: str) -> bool:
    """True if `text` looks like an exported peer-OOBI blob."""
    return text.strip().startswith(BLOB_PREFIX)


def import_peer_blob(hby, blob: str) -> str:
    """Parse a peer-OOBI blob into the Habery's databases.

    Returns the AID extracted from the parsed events. Raises
    ``PeerBlobError`` with a user-readable message on any failure.
    """
    text = blob.strip()
    if not text.startswith(BLOB_PREFIX):
        raise PeerBlobError(
            "bad_prefix",
            "Not a Locksmith peer OOBI blob — missing the "
            f"{BLOB_PREFIX!r} prefix.",
        )
    payload = text[len(BLOB_PREFIX):]
    try:
        cesr = base64.b64decode(payload, validate=True)
    except (ValueError, base64.binascii.Error) as e:
        raise PeerBlobError(
            "bad_base64",
            f"Couldn't decode the blob: {e}. Make sure you copied the "
            f"entire token.",
        )

    # Build a Revery + Kevery wired to this Habery's db so parsed
    # events land in hby.kevers and the role auths land in hby.db.locs.
    db = hby.db
    rvy = routing.Revery(db=db)
    kvy = eventing.Kevery(db=db, lax=True, local=False, rvy=rvy)
    kvy.registerReplyRoutes(router=rvy.rtr)
    # Pin version=Vrsn_1_0: the default Parser version is KERI 2.0; the
    # blob is built from hab.replyToOobi which serializes v1 events. The
    # version mismatch causes Parser.allParsator to loop forever on
    # CESR counter codes that don't exist in v2 — Wallet pegged at 100%
    # CPU with no exception ever raised. Same fix as publishing.py.
    parser = parsing.Parser(kvy=kvy, rvy=rvy, version=Vrsn_1_0)

    try:
        parser.parse(ims=bytearray(cesr), kvy=kvy, rvy=rvy)
    except Exception as e:  # noqa: BLE001
        raise PeerBlobError(
            "parse_failed",
            f"Couldn't parse the blob: {e}. The token may be corrupted.",
        )

    # Identify the AID — the inception event's pre is in hby.kevers.
    # If the blob contained events for an existing AID (rotation), it
    # will be in kevers already; if new, the parser just added it.
    # We can't know the "intended" AID without rescanning the events,
    # so we walk the freshly-populated kevers and pick the one whose
    # locs has a peer-role tcp endpoint.
    for pre in hby.kevers.keys():
        loc = hby.db.locs.get(keys=(pre, kering.Schemes.tcp))
        if loc is not None and loc.url:
            logger.info(
                f"peer.blob.imported aid={pre} endpoint={loc.url}"
            )
            return pre

    raise PeerBlobError(
        "no_peer_role",
        "The blob parsed but no AID inside it published a peer-role "
        "tcp endpoint. The peer may not have 'Expose over peer mode' "
        "enabled on any identifier.",
    )


class PeerBlobError(Exception):
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
