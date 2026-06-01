# -*- encoding: utf-8 -*-
"""
locksmith.core.receipting module

Locksmith-local witness receipting compatibility helpers.

Two reasons this overrides keripy's :class:`agenting.Receiptor`:

1. Fixed catch-up behavior — keripy replays new-witness catch-up one
   event at a time and tears down the client after the first response.
   When a controller has prior history, newly added witnesses miss
   later events and then reject the next ``/receipts`` with 202. We
   send the full replay in one burst and drain every response before
   removing the client.

2. Structured per-witness logging — vanilla
   :meth:`agenting.Receiptor.receipt` ``print()`` s a single ``invalid
   response`` line to stdout on failure, with no per-request status
   info and nothing the wallet's log capture sees. After we hit
   ``Bare receipt collection insufficient (0/1)`` against a known-good
   pure-KERI witness (``witness.keri.host``) with no surfaced cause,
   the only path to a real diagnosis is to log every HTTP exchange
   ourselves.
"""
from keri import help
from keri.app import agenting, httping
from keri import kering
from keri.core import coring, serdering
from keri.core.counting import Codens, Counter
from keri.core.eventing import receipt as eventing_receipt
from keri.kering import Vrsn_1_0


logger = help.ogler.getLogger(__name__)


class LocksmithReceiptor(agenting.Receiptor):
    """Receiptor with fixed catch-up + structured logging."""

    def catchup(self, pre, wit):
        if pre not in self.hby.prefixes:
            raise kering.MissingEntryError(f"{pre} not a valid AID")

        hab = self.hby.habs[pre]

        try:
            client, client_doer = agenting.httpClient(hab, wit)
        except Exception as exc:  # noqa: BLE001 — surface the cause, don't silently no-op
            logger.error(
                f"witness.catchup.client_failed aid={pre} wit={wit} err={exc}"
            )
            return
        self.extend([client_doer])

        ims = bytearray(hab.replay(pre=pre))
        replay_bytes = len(ims)
        try:
            sent = httping.streamCESRRequests(
                client=client,
                dest=wit,
                ims=ims,
            )
            logger.info(
                f"witness.catchup.sent aid={pre} wit={wit} "
                f"events={sent} replay_bytes={replay_bytes}"
            )
            while len(client.responses) < sent:
                yield self.tock

            # Drain every response so we can log each status. The
            # parent class drained without inspecting; we inspect so
            # 4xx/5xx don't hide behind a successful drain.
            statuses = []
            while client.responses:
                rep = client.respond()
                status = getattr(rep, "status", None)
                statuses.append(status)
                if status is None or status >= 400:
                    body = getattr(rep, "body", b"")
                    snippet = bytes(body)[:200] if body else b""
                    logger.warning(
                        f"witness.catchup.bad_response aid={pre} wit={wit} "
                        f"status={status} body={snippet!r}"
                    )
            logger.info(
                f"witness.catchup.done aid={pre} wit={wit} statuses={statuses}"
            )
        finally:
            self.remove([client_doer])

    def receipt(self, pre, sn=None, auths=None):
        """Same wire flow as ``agenting.Receiptor.receipt`` but logs
        every per-witness HTTP status code so a silent rejection from
        the witness is visible in the wallet log.

        Mirrors keripy's structure exactly otherwise — the parent
        implementation is reproduced here because there's no public
        hook for inspecting the receipt-POST response. If keripy ever
        adds one, drop this override.
        """
        auths = auths if auths is not None else {}
        if pre not in self.hby.prefixes:
            raise kering.MissingEntryError(f"{pre} not a valid AID")

        hab = self.hby.habs[pre]
        sn = sn if sn is not None else hab.kever.sner.num
        wits = hab.kever.wits

        if len(wits) == 0:
            logger.info(f"witness.receipt.skipped aid={pre} reason=no_wits")
            return

        msg = hab.msgOwnEvent(sn=sn, framed=True)
        ser = serdering.SerderKERI(raw=msg)

        # For rotations: catch each newly-added witness up to current state
        if ser.ked["t"] in (coring.Ilks.rot,):
            adds = ser.ked.get("ba", [])
            for wit in adds:
                yield from self.catchup(ser.pre, wit)

        clients = {}
        doers = []
        for wit in wits:
            try:
                client, client_doer = agenting.httpClient(hab, wit)
                clients[wit] = client
                doers.append(client_doer)
                self.extend([client_doer])
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    f"witness.receipt.client_failed aid={pre} wit={wit} err={exc}"
                )

        rcts = {}
        for wit, client in clients.items():
            headers = {}
            if wit in auths:
                headers["Authorization"] = auths[wit]
            logger.info(
                f"witness.receipt.send aid={pre} sn={sn} wit={wit} "
                f"auth={'yes' if wit in auths else 'no'} bytes={len(msg)}"
            )

            httping.streamCESRRequests(
                client=client, dest=wit, ims=bytearray(msg),
                path="/receipts", headers=headers,
            )
            while not client.responses:
                yield self.tock

            rep = client.respond()
            status = getattr(rep, "status", None)
            body = getattr(rep, "body", b"") or b""
            if status == 200:
                logger.info(
                    f"witness.receipt.ok aid={pre} sn={sn} wit={wit} "
                    f"body_bytes={len(body)}"
                )
                rct = bytearray(body)
                hab.psr.parseOne(bytearray(rct))
                rserder = serdering.SerderKERI(raw=rct)
                del rct[: rserder.size]
                # pull off the count code
                Counter(qb64b=rct, strip=True, version=Vrsn_1_0)
                rcts[wit] = rct
            else:
                snippet = bytes(body)[:200] if body else b""
                logger.warning(
                    f"witness.receipt.rejected aid={pre} sn={sn} wit={wit} "
                    f"status={status} body={snippet!r}"
                )

        # Propagate retrieved receipts to other witnesses (unchanged
        # from parent — they need to see each other's receipts to
        # satisfy receipt-propagation invariants).
        from keri.app.agenting import schemes
        for wit in rcts:
            ewits = [w for w in rcts if w != wit]
            wigers = [rcts[w] for w in ewits]

            propagate = bytearray()
            if ser.ked["t"] in (coring.Ilks.icp, coring.Ilks.dip):
                propagate.extend(schemes(self.hby.db, eids=ewits))
            elif ser.ked["t"] in (coring.Ilks.rot, coring.Ilks.drt) and \
                    ("ba" in ser.ked and wit in ser.ked["ba"]):
                propagate.extend(schemes(self.hby.db, eids=ewits))

            rserder = eventing_receipt(pre=hab.pre, sn=sn, said=ser.said)
            propagate.extend(rserder.raw)
            propagate.extend(Counter(Codens.NonTransReceiptCouples,
                                     count=len(wigers), version=Vrsn_1_0).qb64b)
            for wiger in wigers:
                propagate.extend(wiger)

            client = clients[wit]
            sent = httping.streamCESRRequests(
                client=client, dest=wit, ims=bytearray(propagate),
            )
            while len(client.responses) < sent:
                yield self.tock

        self.remove(doers)
        logger.info(
            f"witness.receipt.complete aid={pre} sn={sn} "
            f"collected={list(rcts.keys())}"
        )
        return rcts.keys()
