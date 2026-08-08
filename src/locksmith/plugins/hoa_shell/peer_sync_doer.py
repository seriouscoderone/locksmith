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

#: How many unanswered `pro`s for one SAID before this peer is presumed to be
#: withholding it, and we stop asking.
#:
#: Withholding is SILENT: `ProdResponder.processProd` returns None and logs on the
#: RESPONDER's side (`keri/app/prodding.py:148-152`), so the asker cannot tell
#: "not disclosable to you" from "in flight". `credential_anchors` removes the
#: registry events, which can NEVER have a body; this cap covers the other half —
#: a real credential the peer declines to disclose, which no filter can predict.
#: Deliberately generous: the cost of guessing wrong is a stalled leg, and the
#: cost of one surplus ask is a log line.
MAX_BODY_ASKS = 6


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
        # (peer AID, SAID) -> how many DELIVERED asks for that body.
        # See MAX_BODY_ASKS: silent withholding is indistinguishable from
        # in-flight, so the only way to stop asking forever is to count.
        # Undelivered asks are refunded in _drain -- a peer that is down is not
        # a peer that refused.
        self._body_asks: dict[tuple[str, str], int] = {}
        # (peer AID, SAID) pairs already announced as given up, so the give-up
        # line is logged once rather than on every subsequent tick.
        self._body_gave_up: set[tuple[str, str]] = set()
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
            anchored_seals, body_request, credential_anchors, introduced,
            kel_sync_request, missing_bodies, registry_of, tel_sync_request,
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
            seals = anchored_seals(watcher, since=since)
            # Only the anchors that could name an ACDC. A KEL also anchors
            # registry inceptions and rotations, which have no body to fetch and
            # can only ever be withheld -- silently, so the asker would re-ask on
            # every tick forever. Measured on the arc: 27 of 33 prods from the
            # designer went to the admin, which had nothing to disclose to it.
            saids = credential_anchors(vault.rgy.reger, seals)
            self._checkpoints[peer_pre] = getattr(watcher, "checkpoint", since)
        except Exception:                   # noqa: BLE001 — a peer with no KEL yet
            return

        for said in missing_bodies(vault.rgy.reger, saids):
            if not self._claim_body_ask(peer_pre, said):
                continue
            # introduced(): a peer that has never seen this AID drops the
            # prod as "Unknown sender" before authenticating it -- silently.
            #
            # The refund closure is what keeps the cap honest: only an ask the
            # peer actually RECEIVED counts against it. `said` and `peer_pre` are
            # bound per iteration deliberately (default args, not closure capture
            # over the loop variable).
            self._ask(vault, peer_pre,
                      introduced(hab, body_request(hab, said, peer_pre=peer_pre)),
                      f"pro/sealed {said[:12]}…", announce=True,
                      on_undelivered=(lambda p=peer_pre, s=said:
                                      self._refund_body_ask(p, s)))

        # 3. Ask for the TEL of every body we now hold but cannot place in a
        #    registry state.
        #
        #    A `bar` discloses a SAD and nothing else. The ACDC spec keeps the
        #    two apart: the Registry inception's SAID "MUST be anchored in the
        #    Issuer's KEL as the Registry proof seal", update events "MUST also
        #    be anchored", and a validator "can look up the seal in the Issuer's
        #    KEL and verify that the SAID of the Transaction Event is the SAID
        #    in the seal" (acdc-specification.md:3636-3651). The seal is in the
        #    KEL, which step 1 syncs; the Transaction Event is in the TEL, which
        #    nothing fetched. A reader holding body + seal still cannot say
        #    issued-vs-revoked, so it correctly refuses to act — measured, as
        #    `MissingEntryError: Missing TEL event ... at sn=0` on a mandate
        #    that had been disclosed, stored and verified.
        #
        #    The spec allows the state proof attached OR out-of-band; this is
        #    the out-of-band half, so a `bar` stays a pure disclosure and the
        #    reader does its own asking.
        for said in self._tel_gaps(vault, saids):
            self._ask(vault, peer_pre,
                      tel_sync_request(hab, peer_pre, registry_of(
                          vault.rgy.reger.creds.get(keys=(said,)).sad), said),
                      f"qry/tels {said[:12]}…", announce=True)

    def _claim_body_ask(self, peer_pre: str, said: str) -> bool:
        """True if we may still `pro` this peer for this body; records the attempt.

        The other half of the prod waste, and the half no filter can predict:
        `credential_anchors` removes the anchors that CANNOT have a body, but a
        peer may also simply decline to disclose a real credential — a role
        credential issued to somebody else, say. That refusal is SILENT
        (`ProdResponder.processProd` returns None and logs on the RESPONDER's
        side, `keri/app/prodding.py:148-152`), so from here "withheld" and "in
        flight" look identical and counting is the only way to stop.

        Counted per (peer, said): the same SAID may be disclosable by one peer and
        not another, so exhausting one peer must not give up on the rest.

        Only DELIVERED asks count. An ask whose bytes never reached the peer is
        refunded by `_drain` via `_refund_body_ask`, because a peer that is DOWN
        tells us nothing about what it would disclose. Without that refund this
        cap did the opposite of its job, measured 2026-08-08: six prods to an
        admin that was not running, "presuming withheld", and then permanent
        silence toward a peer that had never once been asked. Six wasted ticks is
        noise; never asking again is a stalled leg.
        """
        key = (peer_pre, said)
        # The give-up mark is AUTHORITATIVE, checked before the count. Reading the
        # count alone let a single refund buy another ask forever: exhaust, decline,
        # refund on an unreachable blip, and the count drops back under the cap.
        # Caught by test_a_refund_after_giving_up_does_not_re_arm_the_asking.
        if key in self._body_gave_up:
            return False
        asks = self._body_asks.get(key, 0)
        if asks >= MAX_BODY_ASKS:
            if key not in self._body_gave_up:
                self._body_gave_up.add(key)
                # Announced HERE, on the first ask actually declined -- not on
                # the last one allowed. It used to fire at `asks + 1 ==
                # MAX_BODY_ASKS` and then return True, so the log read
                # "will not ask again" immediately followed by peer_sync.sent.
                logger.info(
                    "peer_sync.body_asks_exhausted said=%s peer=%s after=%d "
                    "delivered asks — presuming withheld, will not ask again",
                    said[:12], peer_pre[:12], MAX_BODY_ASKS)
            return False
        self._body_asks[key] = asks + 1
        return True

    def _refund_body_ask(self, peer_pre: str, said: str) -> None:
        """Un-count an ask whose bytes never reached the peer.

        Called from `_drain` when `peer_request` reports `delivered=False`. Cannot
        take the counter below zero, and deliberately does NOT clear the
        gave-up mark: once a peer has genuinely declined MAX_BODY_ASKS delivered
        asks, a later unreachable blip must not re-arm the asking."""
        key = (peer_pre, said)
        asks = self._body_asks.get(key, 0)
        if asks <= 0:
            return
        self._body_asks[key] = asks - 1
        logger.debug("peer_sync.body_ask_refunded said=%s peer=%s now=%d "
                     "(never delivered)", said[:12], peer_pre[:12], asks - 1)

    def _tel_gaps(self, vault, saids) -> list:
        """SAIDs whose body we hold, whose registry we can name, and whose TEL
        we do not have. Asked once per tick until the TEL lands.

        Fails toward NOT asking: anything unreadable is skipped rather than
        re-queried forever, mirroring `missing_bodies`' own posture.
        """
        from keri_serviceaid.providers.peer_sync import (
            registry_of as registry_of_sad,
        )

        reger = vault.rgy.reger
        out = []
        for said in saids:
            try:
                creder = reger.creds.get(keys=(said,))
                if creder is None:
                    continue                 # no body yet — step 2 owns that
                if not registry_of_sad(creder.sad):
                    continue                 # not registry-backed; no TEL to want
                if reger.tels.get(keys=said, on=0) is not None:
                    continue                 # already have it
                out.append(said)
            except Exception:                # noqa: BLE001
                logger.debug("peer_sync.tel_gap_unreadable said=%s", said[:12])
        return out

    def _ask(self, vault, peer_pre: str, raw: bytes, label: str,
             announce: bool = False, on_undelivered=None) -> None:
        """Send a request and QUEUE its reply for parsing on the next tick.

        `announce` promotes the log line to INFO. A 5s loop over every paired
        peer would bury the log at INFO, so routine ticks stay DEBUG -- but
        logging the WHOLE feature at DEBUG once made it invisible in a build
        that logs at INFO, and its behaviour had to be inferred from the
        `peer.send.*` lines underneath it. The rare, meaningful events -- a
        peer's first sync, every body actually requested -- are INFO.

        `on_undelivered`, when given, is called from `_drain` if the bytes never
        reached the peer. Only the prod path uses it, to refund an ask that
        cannot be evidence about disclosure.

        Note the log line says QUEUED, not sent: the socket work happens off this
        thread, so at this point nothing has been transmitted. It read
        "peer_sync.sent" until 2026-08-08, which is how six prods to an admin
        that was not running looked like six prods answered with silence.
        """
        try:
            record = PeerAllowlist(vault.db).get(peer_pre)
            url = record.endpoint_url if record is not None else None
            if not url:
                if on_undelivered is not None:
                    on_undelivered()
                return
            log = logger.info if announce else logger.debug
            log("peer_sync.queued peer=%s what=%s bytes=%d endpoint=%s",
                peer_pre[:12], label, len(raw), url)
            # Endpoint resolved HERE, on the thread that owns the db; the
            # worker gets a URL and bytes and nothing else.
            outcome: dict = {}
            fut = self._pool.submit(peer_request, None, peer_pre, raw,
                                    endpoint_url=url, outcome=outcome)
            self._pending.append((peer_pre, label, fut, outcome, on_undelivered))
        except Exception:               # noqa: BLE001 — never kill the watch
            if on_undelivered is not None:
                on_undelivered()
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
        for peer_pre, label, fut, outcome, on_undelivered in self._pending:
            if not fut.done():
                still.append((peer_pre, label, fut, outcome, on_undelivered))
                continue
            try:
                raw = fut.result()
            except Exception:           # noqa: BLE001 — unreachable peer is normal
                if on_undelivered is not None:
                    on_undelivered()
                logger.debug("peer_sync.reply_failed peer=%s", peer_pre[:12],
                             exc_info=True)
                continue
            # Undelivered is NOT an answer. `peer_request` returns b"" for both
            # "never connected" and "connected, said nothing", and conflating
            # them let the prod-ask cap read a down peer as a refusing one.
            if not outcome.get("delivered", False):
                if on_undelivered is not None:
                    on_undelivered()
                logger.debug("peer_sync.undelivered peer=%s what=%s",
                             peer_pre[:12], label)
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
