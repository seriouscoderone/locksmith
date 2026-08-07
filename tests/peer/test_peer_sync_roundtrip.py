# -*- encoding: utf-8 -*-
"""The round trip: ask a real listener, READ its reply, ingest the KEL.

This is the test the peer-sync feature shipped twice without, and both times a
broken feature looked healthy. First the query was minted v2 against a v1-pinned
parser and was rejected before it was processed. Then, once it WAS processed,
`peer_send` closed the socket before the answer could be read -- the responder
logged "Server peer-listener: sent chit or receipt or replay: 459" every five
seconds while the asking side's registry stayed empty and re-requested the same
SAIDs forever.

Neither defect is reachable by a unit test over message shape. Both are caught by
one question asked end to end against a REAL listener: does the KEL actually
arrive?
"""
import socket
import threading
import time

import pytest
from hio.base import doing
from hio.help import decking
from keri import kering
from keri.app import habbing
from keri.core import serdering

from locksmith.peer.doer import GuardedServerDoer
from locksmith.peer.sending import peer_request
from locksmith.peer.tcp import TCPServer
from locksmith.turret import directing as turret_directing


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _Listener:
    """A real Directant over a real TCP server, driven by a real Doist on a
    background thread -- assembled the way locksmith's PeerListenerDoer
    assembles it (peer/doer.py:76-98)."""

    def __init__(self, hab, port):
        self.server = TCPServer(host="127.0.0.1", port=port)
        self.directant = turret_directing.Directant(
            hab=hab, server=self.server, cues=decking.Deck(),
        )
        # The ServerDoer is what ACCEPTS connections. Without it the Directant
        # has nothing to service and every request times out empty -- which is
        # indistinguishable from the product bug this test exists to catch, so
        # it must be here and it must be the real one locksmith ships.
        self.doist = doing.Doist(tock=0.03125, real=True, limit=20.0)
        self._thread = threading.Thread(
            target=self.doist.do,
            kwargs={"doers": [GuardedServerDoer(server=self.server), self.directant]},
            daemon=True)

    def __enter__(self):
        self._thread.start()
        for _ in range(100):        # wait for the accept loop to bind
            if getattr(self.server, 'opened', False):
                break
            time.sleep(0.02)
        return self

    def __exit__(self, *exc):
        self.doist.exit()
        self._thread.join(timeout=5.0)
        try:
            self.server.close()
        except Exception:
            pass


def test_peer_request_reads_the_replay_and_ingest_accepts_the_kel():
    """End to end: asker -> listener -> replay -> asker's own KEL store.

    The asker starts NOT knowing the target at all. If the reply is never read,
    or is read but rejected, `target.pre` simply never appears in the asker's
    kevers -- which is precisely the live symptom this reproduces.
    """
    from keri_serviceaid.providers.peer_sync import (
        ingest_response, kel_sync_request,
    )

    port = _free_port()

    # v1 identifiers: what locksmith mints (core/habbing.py:432).
    with habbing.openHby(name="rt-target", temp=True) as thby, \
            habbing.openHby(name="rt-asker", temp=True) as ahby:
        target = thby.makeHab(name="target", version=kering.Vrsn_1_0)
        asker = ahby.makeHab(name="asker", version=kering.Vrsn_1_0)

        assert target.pre not in ahby.kevers, "asker must start ignorant"

        with _Listener(target, port):
            raw = kel_sync_request(asker, target.pre)
            reply = peer_request(None, target.pre, raw,
                                 endpoint_url=f"tcp://127.0.0.1:{port}",
                                 read_timeout=3.0)

        assert reply, ("no reply read -- the responder answers on the same "
                       "connection, so an empty read means we hung up first")

        accepted = ingest_response(ahby, reply)

        assert target.pre in ahby.kevers, (
            f"the target's KEL was not accepted; read {len(reply)} bytes")
        assert accepted >= 1
        assert ahby.kevers[target.pre].prefixer.qb64 == target.pre


def test_ingest_response_is_a_no_op_on_an_empty_reply():
    """An unreachable peer yields b"" from peer_request. That must be a quiet
    no-op, not an exception -- a watch that dies on one silent peer stops
    tracking every other peer too."""
    from keri_serviceaid.providers.peer_sync import ingest_response

    with habbing.openHby(name="rt-empty", temp=True) as hby:
        hby.makeHab(name="me", version=kering.Vrsn_1_0)
        assert ingest_response(hby, b"") == 0
        assert ingest_response(hby, None) == 0


def test_a_prod_gets_a_bar_back_and_the_body_lands():
    """The whole point: ask for a sealed body, and HAVE IT.

    Asserting a responder exists is not enough — three separate defects each
    produced byte-identical silence on the wire, and every one of them would
    pass a "responder is wired" test:

      1. Kevery.anchoringPre could only match a bare {'d': said} seal, so a
         credential anchored by issuance (a 3-field SealEvent) looked
         UNANCHORED and processPro never cued.
      2. cueDo's processCuesIter pulls a prod cue off the deck and discards it,
         so a responder scheduled after it sees an empty deck.
      3. disclosable defaults to {} and policy defaults to denyAll, so a
         correctly-ordered responder still discloses nothing.

    So this asserts the body itself comes back.
    """
    from keri.app import prodding
    from keri.core import eventing as _eventing
    from keri_serviceaid.providers.peer_sync import body_request, ingest_response

    port = _free_port()
    with habbing.openHby(name="pb-disc", temp=True) as dhby, \
            habbing.openHby(name="pb-ask", temp=True) as ahby:
        disc = dhby.makeHab(name="discloser", version=kering.Vrsn_1_0)
        asker = ahby.makeHab(name="asker", version=kering.Vrsn_1_0)

        # An untargeted, unblinded ACDC-shaped SAD: no `u`, no `a.i`.
        from keri.core import coring
        sad = {"d": "", "i": disc.pre, "a": {"line_of_business": "auto",
                                             "jurisdiction": "US-WI"}}
        _, body = coring.Saider.saidify(sad=dict(sad))
        said = body["d"]

        # Anchor it the way credential issuance does: a 3-field SealEvent
        # whose `i` is the credential SAID (credentialing.py:628).
        disc.interact(data=[dict(i=said, s="0", d="E" + "T" * 43)])

        # Production shape: the listener's own hab is the NON-TRANSFERABLE
        # peer-listener EID (locksmith passes next(iter(hby.habs)) there), and
        # the bar must nonetheless be signed by the controller that anchored
        # the credential. A bar signed by the listener EID is rejected by the
        # recipient with "Bare not anchored error: ... has no seal in KEL of
        # B..." -- measured live.
        listener_eid = dhby.makeHab(name="peer-listener", transferable=False,
                                    version=kering.Vrsn_1_0)
        listener = _Listener(disc, port)
        listener.directant = turret_directing.Directant(
            hab=listener_eid, server=listener.server, cues=decking.Deck(),
            disclosable=lambda: {said: body},
            prodPolicy=prodding.openPolicy,
            prodHab=disc,
        )
        listener._thread = threading.Thread(
            target=listener.doist.do,
            kwargs={"doers": [GuardedServerDoer(server=listener.server),
                              listener.directant]},
            daemon=True)

        with listener:
            # NO separate introduction. introduced() prepends the asker's own
            # KEL to the prod itself, which is what production sends — a
            # responder that has never seen this AID drops the prod as
            # "Unknown sender" before authenticating it, silently at DEBUG.
            # Measured live: 32 prods lost exactly this way.
            from keri_serviceaid.providers.peer_sync import introduced
            pro = introduced(asker, body_request(asker, said, peer_pre=disc.pre))
            reply = peer_request(None, disc.pre, pro,
                                 endpoint_url=f"tcp://127.0.0.1:{port}",
                                 read_timeout=4.0)

        assert reply, "no bar came back — the prod was never answered"
        assert b'"t":"bar"' in reply, f"reply is not a bar: {reply[:120]}"

        got = prodding.ProdClient(hab=asker).harvest(
            serdering.SerderKERI(raw=bytes(reply)), said)
        assert got is not None, "bar carried no body for the requested SAID"
        assert got["a"]["jurisdiction"] == "US-WI"
        assert got["d"] == said, "body does not re-derive to the SAID asked for"

        # And it must SURVIVE processBar, which re-checks that the SAID is
        # anchored in the KEL of the bar's SIGNER. Harvesting the bytes proves
        # only that a bar came back; this proves the recipient accepts it.
        import logging
        from keri.core import parsing as _parsing
        seen = []

        class _Cap(logging.Handler):
            def emit(self, r):
                seen.append(r.getMessage())

        h = _Cap()
        for lg in (_parsing.logger, _eventing.logger):
            lg.addHandler(h)
            lg.setLevel(logging.ERROR)
        try:
            ingest_response(ahby, reply)
        finally:
            for lg in (_parsing.logger, _eventing.logger):
                lg.removeHandler(h)

        notanchored = [m for m in seen if "not anchored" in m]
        assert not notanchored, f"recipient rejected the bar: {notanchored[:1]}"
