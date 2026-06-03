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


def _db_open(hby) -> bool:
    """True if the Habery's LMDB env is currently open. During vault
    transitions (creation, deletion, restart) the db.env can be None
    even though the hby object still exists; touching ``db.ends.get``
    in that window raises ``AttributeError: 'NoneType' has no attribute
    'begin'``. All helpers below skip cleanly when the env isn't ready.
    """
    db = getattr(hby, "db", None)
    if db is None:
        return False
    env = getattr(db, "env", None)
    return env is not None


def is_aid_peer_exposed(hby, pre: str) -> bool:
    """True if ``pre`` has a current peer-role end record in its KEL."""
    if not _db_open(hby):
        return False
    hab = hby.habs.get(pre)
    if hab is None:
        return False
    try:
        end = hab.db.ends.get(keys=(pre, kering.Roles.peer, pre))
    except Exception:  # noqa: BLE001 — db can race shut during vault flips
        return False
    if end is None:
        return False
    # keripy's EndpointRecord uses .enabled (controller-cut) or .allowed
    # (watcher-permitted). For our own AID exposing a peer role, both
    # tracks indicate "currently authorized."
    return bool(getattr(end, "enabled", None) or getattr(end, "allowed", None))


def exposed_pres(hby) -> list[str]:
    """List of qb64 prefixes of AIDs currently exposed for peer mode."""
    if not _db_open(hby):
        return []
    return [pre for pre in hby.habs.keys() if is_aid_peer_exposed(hby, pre)]


def count_exposed(hby) -> int:
    """Number of AIDs currently exposed. Cheap surface for banner / dot."""
    return sum(1 for _ in exposed_pres(hby))
