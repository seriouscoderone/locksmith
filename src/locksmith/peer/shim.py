"""Two-gate allowlist check between the TCP socket and the Exchanger."""
from __future__ import annotations

from typing import Callable

from keri import help

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
    ):
        self._allowlist = allowlist
        self.exchanger = exchanger
        self._is_destination_exposed = is_destination_exposed

    def processEvent(self, serder, tsgs=None, cigars=None, **kwargs):
        try:
            sender = serder.ked.get("i", "")
            recipient = serder.ked.get("rp", "")
        except AttributeError:
            logger.warning("peer.parser.discarded reason=non_exn_payload")
            return

        if not self._allowlist.contains(sender):
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
