"""PeerAwarePoster — peer-first IPEX wrapper around StreamPoster."""
import logging
import socket
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from locksmith.peer.allowlist import PeerAllowlist
from locksmith.peer.posting import PeerAwarePoster
from locksmith.peer.records import PeerRecord


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _make_serder(data=b"FAKE-CESR-EVENT"):
    """Cheap stand-in for a keripy serder. The wrapper only reads `.raw`."""
    return SimpleNamespace(raw=data, said="SAID_FAKE", size=len(data))


def _make_hby(recp_aid):
    """Minimal Habery stand-in. StreamPoster touches hby.habs[src] when
    no hab is passed. We pass hab explicitly so this can be empty."""
    return SimpleNamespace(habs={}, db=SimpleNamespace())


def test_peer_record_present_and_endpoint_reachable_uses_peer_channel(baser):
    """When the recipient has a PeerRecord and a real TCP listener is
    bound at the endpoint, deliver() writes the queued bytes there and
    returns an empty doer list (mailbox not invoked)."""
    port = _free_port()
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOCK_STREAM, socket.SO_REUSEADDR, 1) if False else server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", port))
    server.listen(1)

    PeerAllowlist(baser).add(PeerRecord(
        aid="EAID_BOB", label="Bob",
        endpoint_url=f"tcp://127.0.0.1:{port}",
        paired_at=datetime.now(timezone.utc).isoformat(),
    ))

    hby = _make_hby("EAID_BOB")
    fake_hab = SimpleNamespace(kever=SimpleNamespace(prefixer=SimpleNamespace(qb64b=b"")))

    poster = PeerAwarePoster(
        hby=hby, recp="EAID_BOB", baser=baser, hab=fake_hab, topic="credential",
    )
    poster.send(serder=_make_serder(b"EVENT_ONE"))
    poster.send(serder=_make_serder(b"EVENT_TWO"), attachment=b"ATTACH")

    # Patch out the inner StreamPoster.deliver to confirm it's NOT called.
    with patch.object(poster._inner, "deliver") as mock_deliver:
        doers = poster.deliver()
        assert mock_deliver.call_count == 0, "mailbox path should not be invoked"
        assert doers == []
    server.close()


def test_no_peer_record_falls_through_to_mailbox(baser):
    """No PeerRecord → inner StreamPoster.deliver() is called."""
    hby = _make_hby("EAID_UNKNOWN")
    fake_hab = SimpleNamespace(kever=SimpleNamespace(prefixer=SimpleNamespace(qb64b=b"")))

    poster = PeerAwarePoster(
        hby=hby, recp="EAID_UNKNOWN", baser=baser, hab=fake_hab, topic="credential",
    )
    poster.send(serder=_make_serder())

    with patch.object(poster._inner, "deliver", return_value=[]) as mock_deliver:
        poster.deliver()
        assert mock_deliver.call_count == 1


def test_deliver_dials_the_refreshed_route_not_the_cached_one(baser):
    """The live-failure fix at the poster layer: the cached PeerRecord points
    at a dead address, but a newer signed /loc/scheme (BADA-accepted) says the
    peer moved. deliver() must re-resolve through peer/resolution.py and dial
    the fresh address (backlog/2026-07-29-peer-record-endpoint-never-refreshes.md).
    """
    from keri import Vrsn_1_0, kering
    from keri.app import habbing

    with habbing.openHby(name="postref", temp=True, version=Vrsn_1_0) as hby:
        ctrl = hby.makeHab(name="ctrl", transferable=True, version=Vrsn_1_0)
        lsn = hby.makeHab(name="lsn", transferable=False, ns="peer",
                          version=Vrsn_1_0)

        def _publish(url):
            for msg in (
                lsn.reply(route="/loc/scheme",
                          data=dict(eid=lsn.pre, scheme=kering.Schemes.tcp,
                                    url=url)),
                ctrl.reply(route="/end/role/add",
                           data=dict(cid=ctrl.pre, role=kering.Roles.peer,
                                     eid=lsn.pre)),
            ):
                hby.psr.parse(ims=bytearray(msg))

        dead_port = _free_port()
        _publish(f"tcp://127.0.0.1:{dead_port}")
        PeerAllowlist(baser).add(PeerRecord(
            aid=ctrl.pre, label="mover",
            endpoint_url=f"tcp://127.0.0.1:{dead_port}",
            paired_at=datetime.now(timezone.utc).isoformat(),
        ))

        live_port = _free_port()
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", live_port))
        server.listen(1)
        _publish(f"tcp://127.0.0.1:{live_port}")  # newer loc: the peer moved

        fake_hab = SimpleNamespace(
            kever=SimpleNamespace(prefixer=SimpleNamespace(qb64b=b"")))
        poster = PeerAwarePoster(
            hby=hby, recp=ctrl.pre, baser=baser, hab=fake_hab,
            topic="credential",
        )
        poster.send(serder=_make_serder(b"MOVED-EVENT"))

        try:
            with patch.object(poster._inner, "deliver") as mock_deliver:
                doers = poster.deliver()
        finally:
            server.close()

        assert mock_deliver.call_count == 0, (
            "peer moved to a live address — mailbox fallback must not run")
        assert doers == []
        from locksmith.peer.sending import SendOutcome
        assert poster.last_outcome is SendOutcome.PEER
        assert PeerAllowlist(baser).get(ctrl.pre).endpoint_url == (
            f"tcp://127.0.0.1:{live_port}")


def test_unreachable_peer_falls_back_to_mailbox(baser, caplog):
    """Peer endpoint unreachable → outcome=peer→mailbox → inner deliver()
    runs as fallback."""
    PeerAllowlist(baser).add(PeerRecord(
        aid="EAID_BOB", label="Bob",
        endpoint_url="tcp://127.0.0.1:1",  # nothing listening
        paired_at=datetime.now(timezone.utc).isoformat(),
    ))

    hby = _make_hby("EAID_BOB")
    fake_hab = SimpleNamespace(kever=SimpleNamespace(prefixer=SimpleNamespace(qb64b=b"")))

    poster = PeerAwarePoster(
        hby=hby, recp="EAID_BOB", baser=baser, hab=fake_hab, topic="credential",
    )
    poster.send(serder=_make_serder())

    with patch.object(poster._inner, "deliver", return_value=["fallback_doer"]) as mock_deliver:
        with caplog.at_level(logging.INFO, logger="locksmith.peer.posting"):
            doers = poster.deliver()
        assert mock_deliver.call_count == 1
        assert doers == ["fallback_doer"]
        assert any("peer.outbound.fallback" in r.message for r in caplog.records)
