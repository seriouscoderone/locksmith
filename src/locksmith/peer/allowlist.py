"""Sender allowlist for peer-mode inbound traffic."""
from __future__ import annotations

from keri import help

from locksmith.peer.records import PeerRecord

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

    def list(self) -> list[PeerRecord]:
        return [val for (_keys, val) in self._db.peerAllowlist.getTopItemIter()]
