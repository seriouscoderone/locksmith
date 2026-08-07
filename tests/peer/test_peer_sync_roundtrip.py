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
