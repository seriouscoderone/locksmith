"""Two-gate allowlist check between the TCP socket and the Exchanger."""
from __future__ import annotations

from typing import Callable

from keri import help, kering

from locksmith.peer.allowlist import PeerAllowlist

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
        RUN first-update: register it so the reply path works."""
        if not (self._open_inbound and self._hby is not None):
            return False
        if sender not in self._hby.kevers:
            return False
        loc = self._hby.db.locs.get(keys=(sender, kering.Schemes.tcp))
        if loc is None or not loc.url:
            return False
        if self._on_first_contact is not None:
            self._on_first_contact(sender, loc.url)
        logger.info(
            f"peer.gate.first_contact_registered sender={sender} url={loc.url}"
        )
        return True
