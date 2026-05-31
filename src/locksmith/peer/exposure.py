"""Read-side helpers for peer-mode exposure state.

The user toggles "Expose over peer mode" on per-AID. That call publishes
``/end/role/add`` (role=peer) rpys via ``PublishPeerRoleDoer``; the rpys
land in ``hab.db.ends[(cid, 'peer', eid)]``. Anything that needs to ask
"is this AID exposed right now?" — the diagnostic banner, the toggle's
initial state, the toolbar indicator — should read from this same
source of truth, not the in-memory ``_peer_exposed_aids`` set on the
vault (which only reflects toggles flipped *in the current process*).
"""
from __future__ import annotations

from typing import Iterable

from keri import kering


def is_aid_peer_exposed(hby, pre: str) -> bool:
    """True if ``pre`` has a current peer-role end record in its KEL."""
    hab = hby.habs.get(pre)
    if hab is None:
        return False
    end = hab.db.ends.get(keys=(pre, kering.Roles.peer, pre))
    if end is None:
        return False
    # keripy's EndpointRecord uses .enabled (controller-cut) or .allowed
    # (watcher-permitted). For our own AID exposing a peer role, both
    # tracks indicate "currently authorized."
    return bool(getattr(end, "enabled", None) or getattr(end, "allowed", None))


def exposed_pres(hby) -> list[str]:
    """List of qb64 prefixes of AIDs currently exposed for peer mode."""
    return [pre for pre in hby.habs.keys() if is_aid_peer_exposed(hby, pre)]


def count_exposed(hby) -> int:
    """Number of AIDs currently exposed. Cheap surface for banner / dot."""
    return sum(1 for _ in exposed_pres(hby))
