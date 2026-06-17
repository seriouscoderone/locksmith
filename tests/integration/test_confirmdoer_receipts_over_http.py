"""Integration test (issue #77 / keripy #1422): ConfirmDoer must collect the
delegator's witness receipts over HTTP via the shared Receiptor, not the
direct-mode WitnessReceiptor (which hangs against a 204-on-/ witness).

RED rationale
-------------
The current ``ConfirmDoer`` (src/locksmith/core/habbing.py) anchors the
delegate's dip into the delegator's KEL and then collects witness receipts
via ``agenting.WitnessReceiptor``. Over HTTP, ``WitnessReceiptor`` drives an
``HTTPMessenger`` that POSTs the event to the witness ``/`` route. keripy's
witness ``HttpEnd.on_post`` returns **HTTP 204 with no body** for KEL events
(icp/rot/ixn/dip/drt) — the receipt is produced asynchronously and is *not*
returned on that POST. ``WitnessReceiptor.receiptDo`` then busy-waits on
``len(wigers) == len(wits)`` which never becomes true, so the delegator's
anchoring event collects **no witness receipts within the time budget**.

This test asserts that the delegator's anchoring event accrues at least one
witness signature (``wigs``). With the current ConfirmDoer it does not (RED).
After the planned migration to the shared ``Receiptor`` — which POSTs to
``/receipts`` and reads the 200-response receipt couple — wigs land (GREEN).

The test does NOT require ConfirmDoer to *finish*: after receipting, it goes
on to query the delegate's KEL, which won't resolve in this minimal setup.
That is fine — the poll loop breaks the moment wigs appear, and the Doist
``limit`` hard-bounds the run so it can never truly hang.

Fixture notes
-------------
* Real keripy witness via ``indirecting.setupWitness`` (HTTP only, port 5642,
  alias ``wan`` — matching keripy's WitnessUrls table).
* ``_seed_wit_ends`` reproduces ``tests.conftest.DbSeed.seedWitEnds``'s
  end-role + loc-scheme ``rpy``-seeding inline (the keripy ``DbSeed`` class is
  not importable on this venv — ``tests.conftest`` resolves to locksmith's own
  conftest), so the delegator db can resolve the witness HTTP URL.
* The delegate's dip is seeded directly into the delegator db's escrow logs
  (``evts`` + ``delegables`` + ``sigs`` + ``dtss`` + ``esrs``), mirroring
  exactly what keripy's ``Kever.escrowDelegableEvent`` writes when the real
  delegation-request handler escrows a pending delegated inception. This is
  what makes ``ConfirmDoer.confirmDo`` find the event via
  ``db.evts.get(dgKey(pre, edig))`` and proceed to anchor + receipt.
"""
import time
from types import SimpleNamespace

import pytest
from hio.base import doing, tyming
from keri.app import habbing, indirecting, forwarding
from keri.core import coring, parsing, eventing, indexing, routing
from keri.core import Salter
from keri.core.coring import Dater
from keri.db import dbing, basing
from keri.kering import Vrsn_1_0
from keri import help, Schemes, Roles

from locksmith.core import habbing as lh
from locksmith.core.receipting import LocksmithReceiptor

WIT_ALIAS = "wan"
WIT_HTTP_PORT = 5642
WIT_URL = f"http://127.0.0.1:{WIT_HTTP_PORT}/"


def _seed_wit_ends(ctrl_db, wit_hab):
    """Seed the controller db's end-role + loc-scheme records so it can
    resolve the witness HTTP URL.

    Inline reproduction of ``tests.conftest.DbSeed.seedWitEnds`` for the
    http scheme only: build a Revery/Kevery + Parser bound to ``ctrl_db``
    and parse the witness's own ``makeEndRole`` (controller role) and
    ``makeLocScheme`` (http URL) reply messages into it.
    """
    rtr = routing.Router()
    rvy = routing.Revery(db=ctrl_db, rtr=rtr)
    kvy = eventing.Kevery(db=ctrl_db, lax=False, local=True, rvy=rvy)
    kvy.registerReplyRoutes(router=rtr)
    # version=Vrsn_1_0 is load-bearing: without it Parser.parse drives
    # allParsator into an infinite empty-stream yield loop and hangs. This
    # matches keripy's DbSeed.seedWitEnds which passes version=Vrsn_1_0.
    psr = parsing.Parser(framed=True, kvy=kvy, rvy=rvy, version=Vrsn_1_0)

    msgs = bytearray()
    msgs.extend(wit_hab.makeEndRole(eid=wit_hab.pre,
                                    role=Roles.controller,
                                    stamp=help.nowIso8601()))
    msgs.extend(wit_hab.makeLocScheme(url=WIT_URL,
                                      scheme=Schemes.http,
                                      stamp=help.nowIso8601()))
    psr.parse(ims=msgs)


def _seed_delegable_dip(ctrl_db, src_db, dipser):
    """Seed a pending delegated-inception event into ``ctrl_db``'s escrow
    logs exactly as keripy's ``Kever.escrowDelegableEvent`` would.

    The controller (delegator) db must contain the dip in ``evts`` (so
    ConfirmDoer can read it via ``db.evts.get(dgKey(pre, said))``) and in
    ``delegables``. We pull the controller signatures from the delegate's
    own ``sigs`` log (``src_db``) and replicate the same key-state writes
    the escrow path performs.
    """
    dgkey = dbing.dgKey(dipser.preb, dipser.saidb)
    sigs = src_db.sigs.get(keys=dgkey)
    sigers = [indexing.Siger(qb64b=s.qb64b) for s in sigs]

    ctrl_db.esrs.put(keys=dgkey, val=basing.EventSourceRecord(local=False))
    ctrl_db.dtss.put(keys=dgkey, val=Dater())
    ctrl_db.sigs.put(keys=dgkey, vals=sigers)
    ctrl_db.evts.put(keys=(dipser.preb, dipser.saidb), val=dipser)
    ctrl_db.delegables.add(dbing.snKey(dipser.preb, dipser.sn), dipser.saidb)


@pytest.mark.integration
def test_confirmdoer_collects_delegator_receipts_over_http():
    with habbing.openHby(name="withby", salt=Salter(raw=b"witsaltwitsalt00").qb64) as witHby, \
            habbing.openHby(name="delegator", salt=Salter(raw=b"0123456789abcdef").qb64) as dgrHby, \
            habbing.openHby(name="delegate", salt=Salter(raw=b"delegatedelegate").qb64) as delHby:
        # Real keripy witness, HTTP only (tcpPort=None) on the canonical
        # WitnessUrls port for alias "wan".
        witDoers = indirecting.setupWitness(alias=WIT_ALIAS, hby=witHby,
                                            tcpPort=None, httpPort=WIT_HTTP_PORT)
        witHab = witHby.habByName(WIT_ALIAS)

        # Delegator D with the witness in its TOAD=1 pool.
        dgr = dgrHby.makeHab(name="D", transferable=True, wits=[witHab.pre], toad=1)

        # Let D resolve the witness HTTP URL.
        _seed_wit_ends(dgrHby.db, witHab)
        assert dgr.fetchUrls(eid=witHab.pre, scheme="http")[Schemes.http] == WIT_URL

        # Delegate G's delegated inception (delpre = D).
        dele = delHby.makeHab(name="G", transferable=True, delpre=dgr.pre)
        dipser = dele.kever.serder

        # Place G's pending dip into D's delegable escrow (evts + delegables),
        # so ConfirmDoer.confirmDo finds it and anchors + receipts.
        _seed_delegable_dip(dgrHby.db, delHby.db, dipser)

        receiptor = LocksmithReceiptor(hby=dgrHby)
        vault = SimpleNamespace(
            hby=dgrHby, hbyDoer=habbing.HaberyDoer(habery=dgrHby), receiptor=receiptor,
            postman=forwarding.Poster(hby=dgrHby), counselor=SimpleNamespace(),
            notifier=SimpleNamespace(), mux=SimpleNamespace(), exc=SimpleNamespace(),
            mbx=SimpleNamespace())
        app = SimpleNamespace(vault=vault)
        confirm = lh.ConfirmDoer(app=app, alias="D",
                                 escrowed=[(dele.pre, 0, dipser.said)],
                                 interact=True, auto=True)

        doers = list(witDoers) + [receiptor, confirm]
        doist = doing.Doist(limit=10.0, tock=0.03125, doers=doers)
        doist.enter()
        tymer = tyming.Tymer(tymth=doist.tymen(), duration=doist.limit)
        try:
            while not tymer.expired:
                doist.recur()
                time.sleep(doist.tock)
                kev = dgrHby.kevers[dgr.pre]
                if kev.sner.num >= 1 and len(dgrHby.db.wigs.get(
                        keys=(dgr.pre.encode(), kev.serder.saidb))) >= 1:
                    break
        finally:
            doist.exit()

        kev = dgrHby.kevers[dgr.pre]
        assert kev.sner.num >= 1, "delegator never produced its anchoring event"
        wigs = dgrHby.db.wigs.get(keys=(dgr.pre.encode(), kev.serder.saidb))
        assert len(wigs) >= 1, (
            "delegator anchoring event collected no witness receipts over HTTP — "
            "ConfirmDoer still on the WitnessReceiptor push path that hangs vs a "
            "204-on-/ witness (#77)")
