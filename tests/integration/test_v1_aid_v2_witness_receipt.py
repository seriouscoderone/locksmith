"""Task 3 (KERI v2 v1-hold) — interop gate: a v1 Locksmith AID running on the
v2 keripy base collects toad witness receipts through the real
``LocksmithReceiptor``.

This is the validate-early proof for the v1-hold strategy. Findings that shaped
it (verified live in the main session, 2026-07-08):

  * **The receipt round-trip converges.** A v1 (``KERI10``) AID, witnessed by a
    v1 witness, accrues its witness signature (``wigs``) via
    ``LocksmithReceiptor`` on the v2 keripy library. GREEN below.

  * **The Habery must be pinned to v1** (``Habery(version=Vrsn_1_0)``, now done
    in ``core/habbing.open_hby``). Otherwise ``hby.psr`` defaults to v2 and
    misreads the inbound v1 receipt's CESR attachment count codes, so the wig
    never lands. ``makeHab`` still needs its own v1 pin (it does not inherit
    ``hby.version``) — see Task 2. This test pins its control Habery the same
    way to mirror production.

  * **Receipt propagation had to be pinned to v1 JSON.** On the v2 base
    ``eventing.receipt`` defaults to v2 CESR-native (its raw begins with a count
    code, not ``{``), which ``streamCESRRequests.sniff`` rejects with a
    ``ColdStartError``. ``receipting.py`` now frames the propagated receipt v1.
    The generator completing cleanly below locks that fix.

  * **The production federation is v1** (deployed pre-v2-reconciliation), so
    this v1↔v1 path is what Locksmith actually ships against. A *future* v2
    federation would additionally require the witness to parse v1 streams
    (``setupWitness(version=Vrsn_1_0)`` shows the knob) — a keripy/federation
    concern out of Locksmith's scope, tracked separately.

Modeled on ``test_confirmdoer_receipts_over_http.py`` (real in-process keripy
witness, no external process).
"""
import time

import pytest
from hio.base import doing, tyming
from keri.app import habbing, indirecting
from keri.core import Salter
from keri.db import basing
from keri.kering import Vrsn_1_0
from keri import Schemes

from locksmith.core.receipting import LocksmithReceiptor

WIT_ALIAS = "wan"
WIT_HTTP_PORT = 5646
WIT_URL = f"http://127.0.0.1:{WIT_HTTP_PORT}/"


@pytest.mark.integration
def test_v1_aid_receipted_by_witness_on_v2_base():
    with habbing.openHby(name="witv1", salt=Salter(raw=b"witsaltwitsalt00").qb64) as witHby, \
            habbing.openHby(name="alicev1", salt=Salter(raw=b"0123456789abcdef").qb64,
                            version=Vrsn_1_0) as ctrlHby:
        # Real keripy witness on the v2 base, pinned v1 (mirrors the current
        # federation, which runs pre-v2-reconciliation keripy). HTTP only.
        witDoers = indirecting.setupWitness(alias=WIT_ALIAS, hby=witHby, tcpPort=None,
                                            httpPort=WIT_HTTP_PORT, version=Vrsn_1_0)
        witHab = witHby.habByName(WIT_ALIAS)

        # v1 AID (pinned) with the witness in its TOAD=1 pool.
        alice = ctrlHby.makeHab(name="alice", transferable=True,
                                wits=[witHab.pre], toad=1, version=Vrsn_1_0)
        assert alice.kever.serder.sad["v"].startswith("KERI10"), \
            f"alice must be a v1 AID, got {alice.kever.serder.sad['v']}"

        # Let alice resolve the witness HTTP URL (fetchUrls reads only db.locs).
        ctrlHby.db.locs.pin(keys=(witHab.pre, Schemes.http),
                            val=basing.LocationRecord(url=WIT_URL))
        assert alice.fetchUrls(eid=witHab.pre, scheme="http")[Schemes.http] == WIT_URL

        receiptor = LocksmithReceiptor(hby=ctrlHby)
        completed = {}

        def _collect(tymth, tock=0.0, **kwa):
            yield tock
            yield from receiptor.receipt(pre=alice.pre, sn=0)
            completed["ok"] = True  # only set if receipt() returns without raising

        doers = list(witDoers) + [receiptor, doing.doify(_collect)]
        doist = doing.Doist(limit=15.0, tock=0.03125, doers=doers)
        doist.enter()
        tymer = tyming.Tymer(tymth=doist.tymen(), duration=doist.limit)
        try:
            while not tymer.expired:
                doist.recur()
                time.sleep(doist.tock)
                if completed.get("ok") and len(ctrlHby.db.wigs.get(
                        keys=(alice.pre.encode(), alice.kever.serder.saidb))) >= 1:
                    break
        finally:
            doist.exit()

        wigs = ctrlHby.db.wigs.get(keys=(alice.pre.encode(), alice.kever.serder.saidb))
        # Structured log line for automation (feedback_testing_automated).
        print(f"[INTEROP] v1_aid={alice.pre} v1_v={alice.kever.serder.sad['v']} "
              f"wits={witHab.kever.serder.sad['v']} wigs_on_icp={len(wigs)} "
              f"receipt_completed={completed.get('ok', False)}")
        assert len(wigs) >= 1, (
            "v1 AID collected no witness receipt on the v2 keripy base — the v1 "
            "inbound receipt was not parsed as v1 (check the Habery v1 pin)")
        assert completed.get("ok"), (
            "LocksmithReceiptor.receipt did not complete — receipt propagation "
            "likely raised (check the v1 receipt-serder pin in receipting.py)")
