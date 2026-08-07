"""PeerDoer composes the TCP listener, Directant, and allowlist shim."""
from __future__ import annotations

from typing import Callable

from hio.base import doing
from hio.help import decking
from hio.core.tcp.serving import ServerDoer
from keri import help
from keri.app import prodding

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

            # Answering a `pro`. Without this the listener parses a prod, the
            # Kevery cues it, and cueDo pulls the cue off the deck and discards
            # it -- measured live as 538 prods sent, 0 replies, 0 bodies held.
            #
            # `disclosable` is a CALLABLE evaluated per inbound connection, not
            # a startup snapshot, so a mandate declared mid-session is
            # disclosable without a restart. It is computed by a RULE over this
            # controller's own credentials (untargeted AND unblinded) rather
            # than curated: a hand-kept map would be an ACL keyed by SAID,
            # which Principle VIII forbids as squarely as one keyed by AID.
            #
            # The policy is deliberately open, because the RULE is the gate.
            # Everything it admits is an ACDC the spec calls public
            # (no `u` -> "SHOULD be considered a public (non-confidential)
            # ACDC") and untargeted -- addressed to whoever is watching. What
            # this does NOT do is express "actuaries may, competitors may
            # not"; that needs the disclosee to present authority, which is
            # what ProdResponder's policy hook and the prod's q["az"] are for.
            def _disclosable():
                from keri_serviceaid.providers.disclosure import disclosable_bodies

                verifier = self._verifier
                if verifier is None or getattr(verifier, "reger", None) is None:
                    return {}
                return disclosable_bodies(verifier.reger)

            # NOT first_hab for signing bars: that is the non-transferable
            # peer-listener EID, and a bar it signs is rejected by the
            # recipient's processBar as "not anchored" — the credential is
            # anchored in the controller's OWN KEL, not the listener's.
            # Guarded: receiving is this listener's core job, and it must not
            # fail to start because the DISCLOSURE extra could not resolve a
            # signer. Without one, prods simply go unanswered — which is the
            # behaviour before this feature existed.
            try:
                from keri_serviceaid.providers.peer_sync import signing_hab
                from locksmith.core.branding import brand
                prod_hab = signing_hab(hby, brand().default_aid_alias or "default")
            except Exception:               # noqa: BLE001
                logger.debug("prod.signer_unresolved", exc_info=True)
                prod_hab = None

            self.directant = turret_directing.Directant(
                hab=first_hab,
                prodHab=prod_hab,
                server=self.server,
                verifier=self._verifier,
                exchanger=self.shim,
                cues=cues,
                disclosable=_disclosable,
                prodPolicy=prodding.openPolicy,
            )
            doers = [server_doer, self.directant]

        super().__init__(doers=doers, **kwa)
