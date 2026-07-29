"""Sender allowlist for peer-mode inbound traffic."""
from __future__ import annotations

from dataclasses import replace

from keri import help

from locksmith.peer.records import PeerRecord
from locksmith.peer.resolution import resolve_peer_endpoint

logger = help.ogler.getLogger(__name__)


class PeerAllowlist:
    """Thin wrapper around the `peer.` Komer subkey on LocksmithBaser.

    The allowlist is the set of peer AIDs the user has paired with via the
    Add Peer flow. Inbound exns from AIDs not in this list are dropped.
    """

    def __init__(self, db):
        self._db = db

    def add(self, record: PeerRecord) -> None:
        self._db.peerAllowlist.pin(keys=(record.aid,), val=record)
        logger.info(
            f"peer.pair.success aid={record.aid} endpoint={record.endpoint_url} label={record.label!r}"
        )

    def remove(self, aid: str) -> None:
        self._db.peerAllowlist.rem(keys=(aid,))
        logger.info(f"peer.pair.removed aid={aid}")

    def contains(self, aid: str) -> bool:
        return self._db.peerAllowlist.get(keys=(aid,)) is not None

    def get(self, aid: str) -> PeerRecord | None:
        return self._db.peerAllowlist.get(keys=(aid,))

    def refresh_route(self, keridb, aid: str) -> PeerRecord | None:
        """Re-resolve ``aid``'s freshest authorized route and heal a stale record.

        The record's ``endpoint_url`` is a *cache* of what resolution said at
        pairing time; the truth lives in the KERI state (``db.ends``/``db.locs``,
        read through ``peer/resolution.py``, authorization-recency ordered).
        BADA already lets a newer signed ``/loc/scheme`` win in the data layer —
        this makes the cache stop ignoring it
        (backlog/2026-07-29-peer-record-endpoint-never-refreshes.md).

        **This alone does not make an address change survivable.** It can only
        find what the peer actually announced, and a peer that changes address
        currently never re-publishes: ``ensure_direct_transport`` re-pins
        settings when the resolved address moves but runs
        ``PublishPeerRoleDoer`` only on FIRST exposure. Both live two-machine
        failures had the stale address in the admin's KEL state as well, so
        this refresh would have re-resolved the same dead route. The upstream
        link is backlog/2026-07-29-address-change-never-republished.md.

        Pairing identity (aid, label, paired_at, last_contacted_at) is
        preserved; only the route moves. When nothing resolves — a hand-typed
        pairing whose peer never published — the cached address is kept: an
        absent authorization is no reason to drop the only route we have.
        Single-route by design for now: this pins resolution's freshest pick,
        the same list a future multi-route selector will consume whole
        (backlog/2026-07-28-single-route-per-peer.md).

        Returns the current record (refreshed or unchanged), or None when
        ``aid`` was never paired — refresh never invents an allowlist entry.
        """
        record = self.get(aid)
        if record is None:
            return None
        url = resolve_peer_endpoint(keridb, aid)
        if not url or url == record.endpoint_url:
            return record
        refreshed = replace(record, endpoint_url=url)
        self._db.peerAllowlist.pin(keys=(aid,), val=refreshed)
        logger.info(
            f"peer.route.refreshed aid={aid} from={record.endpoint_url or '(empty)'} to={url}"
        )
        return refreshed

    def list(self) -> list[PeerRecord]:
        return [val for (_keys, val) in self._db.peerAllowlist.getTopItemIter()]
