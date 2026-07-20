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

from keri import kering

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

    # Pin version=Vrsn_1_0. Under the KERI-v2 v1-hold every Locksmith AID is v1,
    # so a peer's hab.replyToOobi blob is a v1 stream — parse it v1. (A mismatched
    # parser silently drops the endpoint rpys, so the AID imports with no tcp loc,
    # or against older keripy spun Parser.allParsator at 100% CPU with no error.)
    # NOTE: v2-native peer blobs are NOT yet supported — their KEL parses but the
    # embedded /end/role + /loc/scheme rpys don't route into db.ends/db.locs on a
    # combined-stream import. That lifts with the v1-hold (grep TRANSITIONAL);
    # until then peer mode is v1-to-v1.
    from locksmith.peer.oobi_import import parse_oobi_cesr
    return parse_oobi_cesr(hby, cesr)


class PeerBlobError(Exception):
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
