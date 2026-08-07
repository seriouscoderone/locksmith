"""PeerDoer composes the TCP listener, Directant, and allowlist shim."""
from __future__ import annotations

from typing import Callable

from hio.base import doing
from hio.help import decking
from hio.core.tcp.serving import ServerDoer
from keri import help

from locksmith.peer.allowlist import PeerAllowlist
from locksmith.peer.records import PeerModeSettings
from locksmith.peer.shim import PeerExchangerShim
from locksmith.peer.tcp import TCPServer
from locksmith.turret import directing as turret_directing

logger = help.ogler.getLogger(__name__)


class GuardedServerDoer(ServerDoer):
    """ServerDoer that no-ops when its server is closed.

    Vault.restart_peer_mode swaps the active PeerDoer by closing the old
    server's socket out-of-band. hio's DoDoer can't remove children at
    runtime, so the stale ServerDoer stays in the parent doers list and
    its recur() keeps running. hio's stock ServerDoer.recur calls
    server.service() unconditionally, which dereferences self.ss (now
    None after close), raising AttributeError and killing the doist.
    Guarding on .opened lets the stale doer linger harmlessly.
    """
    def recur(self, tyme):
        if not getattr(self.server, "opened", False):
            return False
        return super().recur(tyme)


class PeerDoer(doing.DoDoer):
    """DoDoer wrapping the peer-mode TCP server, hio ServerDoer, and Directant.

    When settings.enabled is False, the doer is inert (no socket, no doers).
    """

    def __init__(
        self,
        hby,
        baser,
        settings: PeerModeSettings,
        exchanger,
        is_destination_exposed: Callable[[str], bool],
        on_first_contact=None,
        verifier=None,
        disclosable=None,
        prod_hab=None,
        prod_policy=None,
        **kwa,
    ):
        self._hby = hby
        self._baser = baser
        self._settings = settings
        self._exchanger = exchanger
        self._verifier = verifier
        self.server = None
        self.directant = None
        self.shim = None

        doers: list[doing.Doer] = []

        if settings.enabled:
            allowlist = PeerAllowlist(baser)
            self.shim = PeerExchangerShim(
                allowlist=allowlist,
                exchanger=exchanger,
                is_destination_exposed=is_destination_exposed,
                hby=hby,
                open_inbound=settings.open_inbound,
                on_first_contact=on_first_contact,
            )

            self.server = TCPServer(
                host=settings.bind_host,
                port=settings.port,
            )
            server_doer = GuardedServerDoer(server=self.server)

            # Reuse the turret Directant (same module Locksmith already
            # ships) but pass our shim instead of the per-plugin one.
            # The verifier is REQUIRED for credential presentation over peer
            # transport: without it the Reactant builds Parser(tvy=None), and
            # keripy drops every streamed registry TEL event (vcp/iss) with
            # "No tevery to process so dropped msg" -- so a presented ACDC's
            # registry never verifies and the recipient can never admit it.
            # (KELs still land via the always-present kvy.)
            cues = decking.Deck()
            first_hab = next(iter(getattr(hby, "habs", {}).values()), None)

            # Answering a `pro` is KERI protocol and belongs here. WHAT may be
            # disclosed, and WHICH identity signs the disclosure, are
            # application questions -- they arrive already decided, via
            # `disclosable` / `prod_hab`, and this module never computes them.
            # Defaulting both to None means the base discloses nothing, which
            # is the correct posture for a wallet with no app policy loaded.
            self.directant = turret_directing.Directant(
                hab=first_hab,
                prodHab=prod_hab,
                server=self.server,
                verifier=self._verifier,
                exchanger=self.shim,
                cues=cues,
                disclosable=disclosable,
                prodPolicy=prod_policy,
            )
            doers = [server_doer, self.directant]

        super().__init__(doers=doers, **kwa)
