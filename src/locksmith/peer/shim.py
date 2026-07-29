"""Two-gate allowlist check between the TCP socket and the Exchanger."""
from __future__ import annotations

from typing import Callable

from keri import help

from locksmith.peer.allowlist import PeerAllowlist
from locksmith.peer.resolution import resolve_peer_endpoint

logger = help.ogler.getLogger(__name__)


class PeerExchangerShim:
    """Filters inbound exns before handing them to the keripy Exchanger.

    Gate 1: sender AID must be in the paired-peers allowlist.
    Gate 2: destination AID (exn `rp` field) must have role=peer opted in.

    Modeled on locksmith.core.turretting.ExchangerShim but using two
    independent allowlists instead of a single-AID equality check.
    """

    def __init__(
        self,
        allowlist: PeerAllowlist,
        exchanger,
        is_destination_exposed: Callable[[str], bool],
        *,
        hby=None,
        open_inbound: bool = False,
        on_first_contact=None,
    ):
        self._allowlist = allowlist
        self.exchanger = exchanger
        self._is_destination_exposed = is_destination_exposed
        self._hby = hby
        self._open_inbound = open_inbound
        self._on_first_contact = on_first_contact

    def processEvent(self, serder, tsgs=None, cigars=None, **kwargs):
        try:
            sender = serder.ked.get("i", "")
            recipient = serder.ked.get("rp", "")
            # keripy's ipexGrantExn (and the rest of the IPEX family)
            # builds exn messages with rp="" and the actual recipient
            # AID embedded in the attribute block as a.i. Fall back to
            # that when rp is empty so the destination-exposed gate
            # checks the right AID.
            if not recipient:
                attrs = serder.ked.get("a") or {}
                if isinstance(attrs, dict):
                    recipient = attrs.get("i", "") or recipient
        except AttributeError:
            logger.warning("peer.parser.discarded reason=non_exn_payload")
            return

        if not self._allowlist.contains(sender):
            if not self._first_contact_accepted(sender, serder):
                logger.warning(
                    f"peer.gate.sender_rejected sender={sender} said={serder.said}"
                )
                return

        if not self._is_destination_exposed(recipient):
            logger.warning(
                f"peer.gate.destination_not_exposed sender={sender} "
                f"destination={recipient} said={serder.said}"
            )
            return

        logger.info(
            f"peer.recv.delivered sender={sender} destination={recipient} said={serder.said}"
        )
        self.exchanger.processEvent(serder, tsgs, cigars, **kwargs)

    def _first_contact_accepted(self, sender: str, serder) -> bool:
        """Config-gated open-inbound posture (spec Sec 7): accept a
        first-contact sender iff its KEL verified from the in-band OOBI
        (present in kevers) AND it published a reachable tcp loc-scheme.
        RUN first-update: register it so the reply path works.

        The endpoint is resolved natively — cid -> ends[peer] -> eid -> locs[eid]
        — so the sender must have *authorized* the address, not merely had a
        location land. Reading db.locs directly, as this used to, admits an
        address nobody vouched for: a stream damaged (or trimmed) so that the
        /loc/scheme lands while its /end/role/add is dropped leaves exactly that
        state, and this is the gate deciding whether to talk to a stranger.
        """
        if not (self._open_inbound and self._hby is not None):
            return False
        if sender not in self._hby.kevers:
            return False
        url = resolve_peer_endpoint(self._hby.db, sender)
        if not url:
            return False
        if self._on_first_contact is not None:
            self._on_first_contact(sender, url)
        logger.info(
            f"peer.gate.first_contact_registered sender={sender} url={url}"
        )
        return True
