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

What was missing is the ASKING **and the reading**. `peer_send` — correct for
every other message on this transport — closes the socket the instant the write
completes, so the Reactant's reply ("Server peer-listener: sent chit or receipt
or replay: 459", measured live every 5s) went into a connection the asker had
already hung up on. This doer therefore uses `peer_request`, which reads the
reply, and hands the bytes to `ingest_response`.

Every message it sends and every reply it parses is built by
`keri_serviceaid.providers.peer_sync` (headless, pure, unit-tested without Qt or
sockets). No protocol decisions live here — deliberately, so the GUI, a CLI and
a service can share one implementation rather than three. What IS here is
threading: socket waits happen off the GUI thread, KERI state is touched only on
the doer's thread.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from keri import help
from hio.base import doing

from locksmith.core.branding import brand
from locksmith.peer.allowlist import PeerAllowlist
from locksmith.peer.sending import peer_request

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
        # Socket I/O only. peer_request blocks for up to its read timeout, and
        # the hio loop that drives this doer also drives the UI -- doing the
        # waiting inline would freeze the window for (timeout x peers) every
        # tick. Workers return raw bytes and touch no KERI state; every parse
        # happens back on this thread in _drain().
        self._pool = ThreadPoolExecutor(max_workers=4,
                                        thread_name_prefix="peer-sync")
        self._pending: list = []                    # (peer_pre, Future)
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
            # Drain FIRST: a reply that arrived since the last tick must be
            # ingested before missing_bodies decides what is still missing,
            # otherwise every in-flight body is re-requested every tick.
            self._drain(vault)
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
        self._ask(vault, peer_pre, kel_sync_request(hab, peer_pre), "qry/logs",
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
            self._ask(vault, peer_pre, body_request(hab, said, peer_pre=peer_pre),
                      f"pro/sealed {said[:12]}…", announce=True)

    def _ask(self, vault, peer_pre: str, raw: bytes, label: str,
             announce: bool = False) -> None:
        """Send a request and QUEUE its reply for parsing on the next tick.

        `announce` promotes the log line to INFO. A 5s loop over every paired
        peer would bury the log at INFO, so routine ticks stay DEBUG -- but
        logging the WHOLE feature at DEBUG once made it invisible in a build
        that logs at INFO, and its behaviour had to be inferred from the
        `peer.send.*` lines underneath it. The rare, meaningful events -- a
        peer's first sync, every body actually requested -- are INFO.
        """
        try:
            record = PeerAllowlist(vault.db).get(peer_pre)
            url = record.endpoint_url if record is not None else None
            if not url:
                return
            log = logger.info if announce else logger.debug
            log("peer_sync.sent peer=%s what=%s bytes=%d endpoint=%s",
                peer_pre[:12], label, len(raw), url)
            # Endpoint resolved HERE, on the thread that owns the db; the
            # worker gets a URL and bytes and nothing else.
            fut = self._pool.submit(peer_request, None, peer_pre, raw,
                                    endpoint_url=url)
            self._pending.append((peer_pre, label, fut))
        except Exception:               # noqa: BLE001 — never kill the watch
            logger.debug("peer_sync.ask_failed peer=%s what=%s",
                         peer_pre[:12], label, exc_info=True)

    def _drain(self, vault) -> None:
        """Parse every reply that has come back since the last tick.

        Runs on the doer's thread, so all KERI state is touched from the
        thread that owns it. Unfinished requests stay pending; a request that
        never answers is dropped when its future completes empty.
        """
        from keri_serviceaid.providers.peer_sync import ingest_response

        still = []
        for peer_pre, label, fut in self._pending:
            if not fut.done():
                still.append((peer_pre, label, fut))
                continue
            try:
                raw = fut.result()
            except Exception:           # noqa: BLE001 — unreachable peer is normal
                logger.debug("peer_sync.reply_failed peer=%s", peer_pre[:12],
                             exc_info=True)
                continue
            if not raw:
                continue
            try:
                accepted = ingest_response(
                    vault.hby, raw,
                    verifier=getattr(vault, "verifier", None),
                    exc=getattr(vault, "exc", None),
                )
                logger.info("peer_sync.received peer=%s what=%s bytes=%d new_events=%d",
                            peer_pre[:12], label, len(raw), accepted)
            except Exception:           # noqa: BLE001
                logger.warning("peer_sync.ingest_failed peer=%s what=%s",
                               peer_pre[:12], label, exc_info=True)
        self._pending = still
