"""The EID of the vault's peer listener.

A peer dials a socket, and that socket belongs to the *vault* — one listener, one
port, ``db.peerSettings`` keyed ``("default",)``. It is not a property of any one
AID. So it gets its own identifier, and each AID that wants to be reachable there
authorizes it with ``/end/role/add (cid=<aid>, role=peer, eid=<listener>)``. That
is the same shape KERI already uses for witnesses and mailboxes: N controllers
authorize one endpoint provider.

Two properties are load-bearing, both keripy's constraints rather than ours:

* **Non-transferable.** ``/loc/scheme`` is authenticated as coming from the *eid*
  itself — ``processReplyLocScheme`` sets ``aid = eid`` and BADA's ``acceptReply``
  drops any signature not from that aid. Meanwhile ``replyEndRole`` emits
  ``replay(cid)`` plus each eid's loc/end records, and never replays the eid's own
  KEL. A transferable listener would therefore ship indexed signatures the
  receiving wallet has no key state to verify, and the endpoint would fail to land
  with no error. A non-transferable prefix carries its public key, so the attached
  cigar verifies standalone.
* **Namespaced.** ``ns="peer"`` keeps the listener out of the Identifiers page,
  which enumerates ``db.names`` and skips anything whose namespace isn't ``""``
  (``ui/vault/identifiers/list.py``). The listener is infrastructure; surfacing it
  as an identity the user manages would be a lie about what it is. Same trick as
  the turret's ``ns="settings"`` hab.

``alias`` is a parameter rather than a baked-in constant because ``db.locs`` is
keyed ``(eid, scheme)`` — one url per scheme per EID — so a second tcp route is
only expressible as a second EID. Multi-route
(``backlog/2026-07-28-single-route-per-peer.md``) mints another listener; nothing
here assumes there is only one.
"""
from __future__ import annotations

from keri import Vrsn_1_0, help
from keri.core.signing import Salter

logger = help.ogler.getLogger(__name__)

PEER_NS = "peer"
PEER_LISTENER_ALIAS = "peer-listener"


def listener_hab(hby, alias: str = PEER_LISTENER_ALIAS):
    """Return the listener Hab for ``alias``, or None if it hasn't been minted.

    Read-path callers use this: asking "where is this vault reachable?" must not
    have the side effect of creating an identifier.
    """
    try:
        return hby.habByName(alias, ns=PEER_NS)
    except Exception:  # noqa: BLE001 — db can race shut during vault flips
        return None


def listener_eid(hby, alias: str = PEER_LISTENER_ALIAS) -> str | None:
    """qb64 prefix of the vault's peer listener, or None if not minted yet."""
    hab = listener_hab(hby, alias=alias)
    return hab.pre if hab is not None else None


def ensure_listener_hab(hby, alias: str = PEER_LISTENER_ALIAS):
    """Return the listener Hab for ``alias``, minting it on first use.

    Idempotent and stable: re-minting would hand every peer a new EID and orphan
    every authorization already published for the old one.
    """
    hab = listener_hab(hby, alias=alias)
    if hab is not None:
        return hab
    hab = hby.makeHab(
        name=alias,
        ns=PEER_NS,
        transferable=False,
        # A FRESH RANDOM SALT, not the Habery's. Salty key creation derives from
        # (salt, stem) and the Habery's salt follows the passcode, so without this
        # two vaults opened with the same passcode mint the IDENTICAL listener
        # prefix. Since db.locs is keyed (eid, scheme), two different sockets then
        # contend for one location record and BADA's datestamp picks a winner: a
        # peer paired with both resolves one address for both and traffic goes to
        # the wrong vault. One user's two vaults sharing a passcode is ordinary.
        # The keys are persisted in the keystore, so the EID is still stable
        # across restarts — it just isn't derivable.
        salt=Salter().qb64,
        # TRANSITIONAL: hold Locksmith events at v1 (makeHab defaults v2 on the
        # v2 keripy base); lift with serviceaid. grep TRANSITIONAL.
        version=Vrsn_1_0,
    )
    logger.info(f"peer.listener.minted alias={alias} eid={hab.pre}")
    return hab
