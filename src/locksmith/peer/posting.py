"""Peer-aware drop-in replacement for keripy's StreamPoster.

StreamPoster delivers messages to a recipient's mailbox/witness over
HTTP. PeerAwarePoster intercepts the deliver() step: if the recipient
is in the peer-mode allowlist with a reachable tcp:// endpoint, the
queued CESR bytes are written directly to that peer's TCP socket.
On peer failure (unreachable / bad URL), control falls through to the
wrapped StreamPoster's mailbox path.

Same `send()` + `deliver()` surface as StreamPoster so call sites in
locksmith.core.ipexing can swap implementations with no other change.
"""
from __future__ import annotations

from hio.base import doing
from hio.help import decking
from keri import help
from keri.app import forwarding

from locksmith.peer.allowlist import PeerAllowlist
from locksmith.peer.sending import SendOutcome, peer_send

logger = help.ogler.getLogger(__name__)


class PeerAwarePoster:
    """Wraps a forwarding.StreamPoster with peer-first transport.

    The recipient AID is the same as the underlying poster's. We
    intercept deliver() to attempt peer-mode delivery first.
    """

    def __init__(self, hby, recp, baser, *, src=None, hab=None, topic=None,
                 headers=None, **kwa):
        self.hby = hby
        self.recp = recp
        self.baser = baser
        self.hab = hab if hab is not None else (hby.habs[src] if src else None)
        self._inner = forwarding.StreamPoster(
            hby=hby, recp=recp, src=src, hab=hab, topic=topic,
            headers=headers, **kwa,
        )
        self._evts: list[dict] = []

    def send(self, serder, attachment=None):
        """Mirror StreamPoster.send: enqueue the serder + attachment.

        We also queue on the inner StreamPoster so that if the peer
        path fails, the mailbox fallback still has everything to send.
        """
        evt = {"serder": serder}
        if attachment is not None:
            evt["attachment"] = attachment
        self._evts.append(evt)
        if attachment is not None:
            self._inner.evts.append(evt)
        else:
            self._inner.evts.append({"serder": serder})

    def deliver(self) -> list:
        """Return doers that drain the queue.

        Strategy:
          1. Look up the recipient's PeerRecord. If absent → mailbox.
          2. Concatenate all queued serder.raw + attachment bytes.
          3. Call peer_send. If outcome is PEER, clear the inner
             StreamPoster's queue and return no-op (already delivered).
             Otherwise return the inner StreamPoster's mailbox doers.
        """
        allowlist = PeerAllowlist(self.baser)
        record = allowlist.get(self.recp)
        if record is None or not record.endpoint_url:
            logger.info(
                f"peer.outbound.no_record recipient={self.recp} → mailbox"
            )
            return self._inner.deliver()

        body = self._materialize_bytes()
        if not body:
            return []

        outcome = peer_send(
            allowlist=allowlist,
            recipient_aid=self.recp,
            exn_bytes=body,
            mailbox_send=lambda aid, bs: True,  # noop; we'll route below
        )

        if outcome is SendOutcome.PEER:
            # Successful peer delivery — clear the inner queue so the
            # mailbox doer doesn't double-send.
            self._inner.evts = decking.Deck()
            return []

        # Peer attempt failed or no peer record was usable. Fall back
        # to the inner StreamPoster (which still has the same queue).
        logger.info(
            f"peer.outbound.fallback recipient={self.recp} outcome={outcome.value}"
        )
        return self._inner.deliver()

    def _materialize_bytes(self) -> bytes:
        """Concatenate all queued serder.raw + attachment into a single
        CESR stream the peer's parser can consume.
        """
        buf = bytearray()
        for evt in self._evts:
            serder = evt["serder"]
            buf.extend(serder.raw)
            atc = evt.get("attachment", b"")
            if atc:
                buf.extend(atc)
        return bytes(buf)
