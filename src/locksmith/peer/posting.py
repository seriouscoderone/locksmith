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
from keri import help, kering
from keri.app import forwarding

from locksmith.peer.allowlist import PeerAllowlist
from locksmith.peer.sending import SendOutcome, peer_send

logger = help.ogler.getLogger(__name__)

#: The roles keripy's StreamPoster routes the mailbox path through, in its
#: own preference order (forwarding.StreamPoster._chunk): direct-send roles
#: first, store-and-forward via a witness last.
_FALLBACK_ROLES = (
    kering.Roles.controller,
    kering.Roles.agent,
    kering.Roles.mailbox,
    kering.Roles.witness,
)


def mailbox_route_exists(hab, recp: str) -> bool:
    """True iff keripy's StreamPoster has anywhere to deliver for ``recp``.

    Mirrors ``forwarding.StreamPoster._chunk``'s routing walk over
    ``hab.endsFor(recp)``: controller/agent/mailbox ends first, else the
    recipient's witnesses. A role only counts with at least one located URL —
    an authorization with no ``/loc/scheme`` still routes nowhere. Peer-role
    ends deliberately don't count: they are the direct channel, and this
    predicate exists to say whether the mailbox FALLBACK can deliver.

    When this is False, the inner StreamPoster's deliver() logs "No end
    roles" and returns no doers — the fallback "delivery" is a silent no-op.
    That is the condition the loud-failure policy below exists to surface
    (backlog/2026-07-29-grant-send-reports-success-while-undeliverable.md).
    """
    try:
        ends = hab.endsFor(recp)
        for role in _FALLBACK_ROLES:
            for _eid, locs in (ends.get(role) or {}).items():
                if any(url for url in locs.values()):
                    return True
    except Exception:  # noqa: BLE001 — an errored walk would have errored
        # StreamPoster's own routing too; treat as "nowhere to deliver".
        return False
    return False


def undeliverable(channel: str, hab, recp: str) -> bool:
    """True when a send's outcome means the message reached nobody.

    ``channel`` is the ``SendOutcome`` value string the delivery tail already
    reports (``last_outcome``). A confirmed peer delivery is always
    deliverable; a mailbox/fallback outcome is honest only if the recipient
    actually has somewhere the mailbox path can route — otherwise reporting
    success is a lie (the first live two-machine test lost a grant exactly
    this way).
    """
    if channel == SendOutcome.PEER.value:
        return False
    return not mailbox_route_exists(hab, recp)


def recipient_label(baser, aid: str, org=None) -> str:
    """Operator-readable name for ``aid`` in delivery-failure surfaces.

    Pairing label first (what the user typed at Add Peer / first-contact
    registration), then the contact alias (keripy Organizer), then a
    shortened AID — never the full 44-char prefix in a banner.
    """
    try:
        record = PeerAllowlist(baser).get(aid)
    except Exception:  # noqa: BLE001 — label lookup must never break a send
        record = None
    label = getattr(record, "label", "")
    if isinstance(label, str) and label:
        return label
    if org is not None:
        try:
            contact = org.get(aid)
        except Exception:  # noqa: BLE001
            contact = None
        alias = (contact or {}).get("alias", "")
        if isinstance(alias, str) and alias:
            return alias
    return f"{aid[:12]}…"


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
        #: SendOutcome of the most recent deliver() call, or None if
        #: deliver() hasn't been called yet. Read this from outside to
        #: surface the transport channel in the UI (e.g. notification
        #: toast badges "peer", "mailbox", "peer→mailbox").
        self.last_outcome: SendOutcome | None = None

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
        # Re-resolve the recipient's current authorized route before deciding
        # anything: the record's endpoint_url is a pairing-time cache, and a
        # peer that moved has already landed its newer signed /loc/scheme in
        # the KERI db via BADA. Refreshing here (and again inside peer_send —
        # idempotent) is what keeps an address change from being permanent
        # (backlog/2026-07-29-peer-record-endpoint-never-refreshes.md).
        keridb = getattr(self.hby, "db", None)
        if keridb is not None:
            record = allowlist.refresh_route(keridb, self.recp)
        else:
            record = allowlist.get(self.recp)
        if record is None or not record.endpoint_url:
            logger.info(
                f"peer.outbound.no_record recipient={self.recp} → mailbox"
            )
            self.last_outcome = SendOutcome.MAILBOX
            return self._inner.deliver()

        body = self._materialize_bytes()
        if not body:
            return []

        outcome = peer_send(
            allowlist=allowlist,
            recipient_aid=self.recp,
            exn_bytes=body,
            mailbox_send=lambda aid, bs: True,  # noop; we'll route below
            keridb=keridb,
        )

        if outcome is SendOutcome.PEER:
            logger.info(
                f"peer.outbound.peer_ok recipient={self.recp} "
                f"bytes={len(body)} events={len(self._evts)}"
            )
            # Successful peer delivery — clear the inner queue so the
            # mailbox doer doesn't double-send.
            self._inner.evts = decking.Deck()
            self.last_outcome = SendOutcome.PEER
            return []

        # Peer attempt failed or no peer record was usable. Fall back
        # to the inner StreamPoster (which still has the same queue).
        logger.info(
            f"peer.outbound.fallback recipient={self.recp} outcome={outcome.value}"
        )
        self.last_outcome = SendOutcome.FALLBACK
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
