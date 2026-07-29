"""Read-side helpers for peer-mode exposure state.

The user toggles "Expose over peer mode" on per-AID. That call publishes
``/end/role/add`` (role=peer) rpys via ``PublishPeerRoleDoer``; the rpys
land in ``hab.db.ends[(cid, 'peer', eid)]``. Anything that needs to ask
"is this AID exposed right now?" — the diagnostic banner, the toggle's
initial state, the toolbar indicator — should read from this same
source of truth, not the in-memory ``_peer_exposed_aids`` set on the
vault (which only reflects toggles flipped *in the current process*).

The ``eid`` is the vault's peer listener, not the AID (``peer.listener_eid``), so
"is this exposed?" is "does this AID authorize ANY eid for the peer role?" —
answered by ``peer.resolution``. Reading ``ends[(pre, peer, pre)]`` as this used to
would report every AID as unexposed the moment the listener got its own identity,
while still returning True for vaults holding the old ``eid == cid`` records.
"""
from __future__ import annotations

from typing import Iterable

from locksmith.peer.resolution import is_peer_exposed


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
    """True if ``pre`` currently authorizes any endpoint for the peer role."""
    if not _db_open(hby):
        return False
    hab = hby.habs.get(pre)
    if hab is None:
        return False
    return is_peer_exposed(hab.db, pre)


def exposed_pres(hby) -> list[str]:
    """List of qb64 prefixes of AIDs currently exposed for peer mode."""
    if not _db_open(hby):
        return []
    return [pre for pre in hby.habs.keys() if is_aid_peer_exposed(hby, pre)]


def count_exposed(hby) -> int:
    """Number of AIDs currently exposed. Cheap surface for banner / dot."""
    return sum(1 for _ in exposed_pres(hby))
