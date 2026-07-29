"""Resolve where an AID is reachable in peer mode: cid -> ends[peer] -> eid -> locs.

This is the walk keripy already does for the mailbox and witness roles
(``hab.endsFor`` / ``hab.fetchRoleUrls``, used by ``forwarding.Poster``). The peer
path used to shortcut it and read ``db.locs.get(keys=(aid, tcp))`` directly, which
only worked because the same code also published ``eid == cid``.

Going through the authorization record buys two things beyond correctness:

* **The legacy shape keeps working for free.** An install that published
  ``eid == cid`` has ``ends[(cid, peer, cid)]`` and ``locs[(cid, tcp)]``; this walk
  finds ``eid = cid`` and resolves it. No migration, no version flag — the old
  shape is a degenerate case of the general one.
* **An unauthorized location stops resolving.** A ``/loc/scheme`` that landed
  without its ``/end/role/add`` is an address nobody vouched for, and that is
  reachable in practice — a peer-OOBI damaged in transit can land one and drop the
  other. Reading ``db.locs`` directly returns it as a success.

Everything returns *all* authorized routes rather than one, because ``db.locs`` is
keyed ``(eid, scheme)`` — one url per scheme per EID — so a second tcp route is
only expressible as a second EID. Callers that still handle a single route take
the first; nothing here assumes there is only one
(``backlog/2026-07-28-single-route-per-peer.md``).
"""
from __future__ import annotations

from keri import help, kering

logger = help.ogler.getLogger(__name__)


def _authorized(end) -> bool:
    """True if an EndpointRecord currently authorizes its EID.

    keripy writes ``.enabled`` for a controller-signed add/cut and ``.allowed``
    for a watcher-permitted one. For a peer role either indicates authorized;
    a cut leaves both false.
    """
    return bool(getattr(end, "enabled", None) or getattr(end, "allowed", None))


def _authorized_at(db, cid: str, eid: str) -> str:
    """Datestamp keripy recorded for this authorization, or "" if unavailable.

    Follows keripy's own trail: ``db.eans[(cid, role, eid)]`` holds the SAID of
    the accepted ``/end/role`` rpy and ``db.sdts[said]`` its datetime — the same
    pair BADA compares in ``acceptReply`` to decide which reply is later. ISO-8601
    strings sort correctly as strings.
    """
    try:
        saider = db.eans.get(keys=(cid, kering.Roles.peer, eid))
        if saider is None:
            return ""
        dater = db.sdts.get(keys=(saider.qb64b,))
    except Exception:  # noqa: BLE001
        return ""
    return getattr(dater, "dts", "") or ""


def peer_role_eids(db, cid: str) -> list[str]:
    """EIDs ``cid`` currently authorizes for the peer role, freshest first.

    Ordering matters because a ``/end/role/cut`` does not travel: ``replyEndRole``
    exports only currently-authorized records, so when a controller retires an
    old endpoint the cut is absent from the artifact peers receive. An install
    that learned the old endpoint keeps holding it and ends up with two routes.
    Preferring the most recently authorized one means the new address wins
    anyway, and the older survives as a lower-priority fallback rather than
    shadowing it. See backlog/2026-07-28-endrole-cut-does-not-propagate.md.

    LMDB key order is by EID, which bears no relation to recency, so the sort is
    doing real work here.
    """
    try:
        items = list(db.ends.getTopItemIter(keys=(cid, kering.Roles.peer)))
    except Exception:  # noqa: BLE001 — db can race shut during vault flips
        return []
    eids = [eid for (_cid, _role, eid), end in items if _authorized(end)]
    # Stable sort on a descending datestamp: EIDs with no recorded datestamp
    # sort last but keep their relative order.
    return sorted(eids, key=lambda eid: _authorized_at(db, cid, eid),
                  reverse=True)


def resolve_peer_endpoints(
    db, cid: str, scheme: str = kering.Schemes.tcp,
) -> list[tuple[str, str]]:
    """``(eid, url)`` for every endpoint ``cid`` authorizes in the peer role.

    Both halves are required: an authorization with no location and a location
    with no authorization each resolve to nothing.
    """
    out: list[tuple[str, str]] = []
    for eid in peer_role_eids(db, cid):
        try:
            loc = db.locs.get(keys=(eid, scheme))
        except Exception:  # noqa: BLE001
            continue
        if loc is not None and loc.url:
            out.append((eid, loc.url))
    return out


def resolve_peer_endpoint(
    db, cid: str, scheme: str = kering.Schemes.tcp,
) -> str | None:
    """The url ``cid`` is reachable at in peer mode, or None.

    Returns the first authorized route. Callers that want to try alternatives on
    failure should use ``resolve_peer_endpoints``.
    """
    endpoints = resolve_peer_endpoints(db, cid, scheme=scheme)
    return endpoints[0][1] if endpoints else None


def is_peer_exposed(db, cid: str) -> bool:
    """True if ``cid`` currently authorizes any EID for the peer role.

    Deliberately independent of whether a location has landed: "the user turned
    exposure on" is the authorization, and a UI toggle should reflect that even
    in the window before the loc rpy is processed.
    """
    return bool(peer_role_eids(db, cid))
