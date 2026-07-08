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
from keri.db import dbing
from keri.kering import Kinds, Vrsn_1_0


logger = help.ogler.getLogger(__name__)


def replay_with_evidence(hab, pre):
    """Build a catch-up replay stream with per-event evidence logging.

    Wire-equivalent to ``hab.replay(pre=pre)`` — the underlying
    ``db.cloneEvtMsg`` already concatenates any locally-stored wig
    (witness indexed sig) and rct (non-trans witness receipt) couples
    to each event's attachment group. What this function adds is
    deliberate visibility: a structured log line per event surfacing
    how many wig and rct couples we shipped with it. That's the only
    way to tell, after a catch-up that returns 204 and never lands
    the AID on the receiver, whether the wallet had evidence to ship
    or didn't.

    Observed in the field:
      - AIDs whose icp was actively witnessed by a now-retired witness
        and whose receipt was successfully ingested at the time show
        ``wigs=1`` for the icp. The wig couple ships in the catch-up
        payload.
      - Other AIDs show ``wigs=0 rcts=0`` for every event. Either we
        never collected receipts during inception (deployment race?)
        or a keripy parse-of-inbound-receipt wiring path didn't land
        them. Either way, no evidence ships; the receiver's TOAD gate
        can't be satisfied.

    Why this function exists rather than just calling ``hab.replay()``:
      The deliberate iteration over ``db.fels.getAllItemIter`` +
      ``db.cloneEvtMsg`` mirrors what ``hab.replay()`` does internally,
      so byte-for-byte the wire content is the same. But ``hab.replay()``
      is a black box for diagnostics — if the receiver silently drops
      the event there's no signal whether the wallet shipped the
      evidence it has or didn't. We have logs.

    Returns:
        (bytearray, int): the assembled stream and the event count.
    """
    pre_b = pre.encode("utf-8") if isinstance(pre, str) else pre
    msgs = bytearray()
    n_events = 0
    for keys, fn, dig in hab.db.fels.getAllItemIter(keys=pre_b, on=0):
        try:
            msg = hab.db.cloneEvtMsg(pre=pre_b, fn=fn, dig=dig)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                f"replay.skip_event aid={pre} fn={fn} dig={dig!r} err={exc}"
            )
            continue
        dgkey = dbing.dgKey(pre_b, dig)
        wigs = hab.db.wigs.get(keys=dgkey) or []
        rcts = hab.db.rcts.get(keys=dgkey) or []
        logger.info(
            f"replay.event aid={pre} fn={fn} bytes={len(msg)} "
            f"wigs={len(wigs)} rcts={len(rcts)}"
        )
        msgs.extend(msg)
        n_events += 1
    return msgs, n_events


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

        ims, n_events = replay_with_evidence(hab, pre)
        replay_bytes = len(ims)
        try:
            sent = httping.streamCESRRequests(
                client=client,
                dest=wit,
                ims=bytearray(ims),
            )
            logger.info(
                f"witness.catchup.sent aid={pre} wit={wit} "
                f"events={sent}/{n_events} replay_bytes={replay_bytes}"
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

            # TRANSITIONAL (KERI v2 v1-hold): pin the propagated receipt to v1
            # JSON. On the v2 keripy base eventing_receipt defaults to v2
            # CESR-native, whose raw starts with a count code (not a JSON `{`);
            # streamCESRRequests.sniff then rejects the stream with a
            # ColdStartError ("Expecting message counter tritet=txt"). The
            # controller + witnesses are v1, so frame the receipt v1.
            rserder = eventing_receipt(pre=hab.pre, sn=sn, said=ser.said,
                                       version=Vrsn_1_0, kind=Kinds.json)
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
