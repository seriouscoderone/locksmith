# -*- encoding: utf-8 -*-
"""The transport edge of a watch: ask paired peers for KEL updates and bodies.

`AnchorWatcher` reads anchors from a KEL the wallet already has; C1's
`sealed_retrieval` verifies a body the wallet already has. Neither fetches, and
in witness-less direct mode there is no witness to fetch on our behalf — the
existing `witq` (WitnessInquisitor) query path has nobody to ask. So a watching
wallet's KEL copy of a peer stays frozen at whatever the pairing handshake left
behind, and it never observes another anchor. That is not a missing protocol:
the ANSWERING halves both already exist and are already wired.

  * `qry` route "logs" -> `Kevery.processQuery` replays the KEL, and the
    direct-mode Reactant builds its Parser with `kvy=` and replies through a
    path literally labelled "chit or receipt or replay".
  * `pro` route "/sealed" -> Plan A's `ProdResponder` answers with a `bar`.

What was missing is only the ASKING. This doer is that, and nothing more: every
message it sends is built by `keri_serviceaid.providers.peer_sync` (headless,
pure, unit-tested without Qt or sockets) and handed to the existing
`peer_send`. No protocol decisions live here — deliberately, so the GUI, a CLI
and a service can share one implementation of the asking rather than three.
"""
from __future__ import annotations

from keri import help
from hio.base import doing

from locksmith.core.branding import brand
from locksmith.peer.allowlist import PeerAllowlist
from locksmith.peer.sending import peer_send

logger = help.ogler.getLogger(__name__)

#: How often to ask. Slow on purpose: a watch is a background truth-tracking
#: loop, not a request/response path a user is waiting on, and each tick costs
#: every paired peer a KEL replay.
DEFAULT_TOCK = 5.0


class PeerSyncDoer(doing.Doer):
    """Per-vault poller: KEL sync for each paired peer, then bodies for the
    anchors that sync revealed.

    Args:
        app: the LocksmithApplication — read for ``app.vault`` only, and
            re-read every tick so a vault swap is picked up rather than
            captured (the stale-vault bug this codebase already hit once in
            the settings page).
        tock: seconds between passes.
    """

    def __init__(self, app, tock: float = DEFAULT_TOCK, **kwa):
        self.app = app
        self._checkpoints: dict[str, int] = {}      # peer AID -> last seen sn
        super().__init__(tock=tock, **kwa)

    def do(self, tymth, tock=0.0, **opts):
        """Same shape as InboundGrantWatchDoer/GateRecheckDoer so a Doist
        drives it identically."""
        self.wind(tymth)
        self.tock = tock or self.tock
        while True:
            yield self.tock
            self.sync_once()

    # -- one pass ---------------------------------------------------------

    def sync_once(self) -> None:
        """One asking pass. Never raises: a watch that dies on a single
        unreachable peer stops tracking every other peer too, and the failure
        would surface far from here."""
        try:
            from keri_serviceaid.providers.peer_sync import signing_hab

            vault = getattr(self.app, "vault", None)
            if vault is None:
                return
            # NOT next(iter(hby.habs.values())): that dict also holds
            # infrastructure EIDs -- notably the non-transferable
            # "peer-listener" -- and a query signed by a non-transferable AID
            # is dropped by the receiver before it is ever processed. See
            # signing_hab's docstring for the mechanism.
            hab = signing_hab(vault.hby, brand().default_aid_alias or "default")
            if hab is None:
                return                      # no identity yet — nothing to sign with
            for peer_pre in self._paired_peers(vault, hab):
                self._sync_peer(vault, hab, peer_pre)
        except Exception:                   # noqa: BLE001
            logger.exception("peer_sync.pass_failed")

    def _paired_peers(self, vault, hab) -> list[str]:
        """Every paired peer that is not one of our own identifiers."""
        try:
            own = set(vault.hby.habs.keys())
            records = PeerAllowlist(vault.db).list()
            return [r.aid for r in records if r.aid and r.aid not in own]
        except Exception:                   # noqa: BLE001
            logger.exception("peer_sync.peer_list_failed")
            return []

    def _sync_peer(self, vault, hab, peer_pre: str) -> None:
        from keri_serviceaid.providers.peer_sync import (
            anchored_saids, body_request, kel_sync_request, missing_bodies,
        )

        # 1. Ask the peer to replay its own KEL. Anchors we have never seen
        #    cannot be requested until they are visible here.
        first = peer_pre not in self._checkpoints
        self._send(vault, peer_pre, kel_sync_request(hab, peer_pre), "qry/logs",
                   announce=first)

        # 2. Ask for the bodies behind anchors we can see but do not hold.
        #    `missing_bodies` keeps this from re-requesting on every tick.
        try:
            from keri.app.anchoring import AnchorWatcher

            watcher = AnchorWatcher(hab=hab, pre=peer_pre)
            since = self._checkpoints.get(peer_pre, 0)
            saids = anchored_saids(watcher, since=since)
            self._checkpoints[peer_pre] = getattr(watcher, "checkpoint", since)
        except Exception:                   # noqa: BLE001 — a peer with no KEL yet
            return

        for said in missing_bodies(vault.rgy.reger, saids):
            self._send(vault, peer_pre, body_request(hab, said, peer_pre=peer_pre),
                       f"pro/sealed {said[:12]}…", announce=True)

    def _send(self, vault, peer_pre: str, raw: bytes, label: str,
              announce: bool = False) -> None:
        """`announce` promotes a send to INFO.

        A 5s loop over every paired peer would bury the log at INFO, so the
        routine tick stays at DEBUG. But logging the WHOLE feature at DEBUG
        made it invisible in a build that logs at INFO: this doer ran for
        minutes against a live demo emitting nothing of its own, and its
        behaviour had to be inferred from the `peer.send.*` lines underneath
        it. That is backwards for a background loop whose entire job is to be
        observable. So the events that are both RARE and MEANINGFUL -- the
        first sync of a peer, and every body actually requested -- are INFO.
        """
        try:
            outcome = peer_send(
                PeerAllowlist(vault.db), peer_pre, raw,
                mailbox_send=lambda _aid, _b: False,   # a watch never falls back
                keridb=vault.hby.db,
            )
            log = logger.info if announce else logger.debug
            log("peer_sync.sent peer=%s what=%s bytes=%d outcome=%s",
                peer_pre[:12], label, len(raw), outcome)
        except Exception:                   # noqa: BLE001 — unreachable peer is normal
            logger.debug("peer_sync.send_failed peer=%s what=%s",
                         peer_pre[:12], label, exc_info=True)
