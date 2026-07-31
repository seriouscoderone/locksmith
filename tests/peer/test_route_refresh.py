"""A cached peer route refreshes from the KERI state instead of being permanent.

Born from the first live two-machine test
(backlog/2026-07-29-peer-record-endpoint-never-refreshes.md): the admin's
``PeerRecord`` held the requester's old NAT address forever, so every send kept
dialing the pairing-time cache even once a newer signed ``/loc/scheme`` had
landed in the KERI state. The fix here: the route cache re-resolves through
``peer/resolution.py`` (authorization-recency ordered) at send time and on
health-probe failure, refreshing a stale ``endpoint_url`` while preserving the
pairing identity (aid/label/paired_at).

**Scope — read this before treating any of it as end-to-end coverage of the
field failure.** Every test below *lands a newer signed rpy itself* and then
asserts the cache stops ignoring it. That precondition is exactly what did NOT
hold in either live incident: the peer never re-published after its address
changed (``ensure_direct_transport`` re-pins settings when the resolved address
moves but only runs ``PublishPeerRoleDoer`` on FIRST exposure), so on
2026-07-29 the admin's ``db.locs`` held the same stale loopback and
re-resolving would have found it. That missing upstream link is
``backlog/2026-07-29-address-change-never-republished.md`` — a separate queued
task, deliberately NOT fixed here. Three links are needed; this file covers
exactly the middle one:

1. the peer re-publishes when its address changes — NOT covered (upstream),
2. the admin picks up the newer announcement — **this file**,
3. undeliverable sends fail loudly — ``tests/peer/test_deliverability.py``.
"""
from __future__ import annotations

import socket
import threading

import pytest
from keri import Vrsn_1_0, kering
from keri.app import habbing

from locksmith.peer.allowlist import PeerAllowlist
from locksmith.peer.records import PeerRecord
from locksmith.peer.sending import SendOutcome, peer_send

PAIRED_AT = "2026-07-29T00:00:00.000000+00:00"


@pytest.fixture()
def hby():
    with habbing.openHby(name="refresh", temp=True, version=Vrsn_1_0) as h:
        yield h


def _publish(hby, signer_hab, ctrl_hab, eid: str, url: str):
    """Land a signed /loc/scheme + the controller's /end/role/add — the same
    pair PublishPeerRoleDoer writes and the in-band OOBI carries. A second
    call with a new url is exactly "a newer signed /loc/scheme arrived":
    hab.reply datestamps it now, so BADA's newer-wins updates db.locs.
    """
    for msg in (
        signer_hab.reply(route="/loc/scheme",
                         data=dict(eid=eid, scheme=kering.Schemes.tcp, url=url)),
        ctrl_hab.reply(route="/end/role/add",
                       data=dict(cid=ctrl_hab.pre, role=kering.Roles.peer,
                                 eid=eid)),
    ):
        hby.psr.parse(ims=bytearray(msg))


def _pair(baser, aid: str, url: str, label: str = "requester") -> PeerRecord:
    record = PeerRecord(aid=aid, label=label, endpoint_url=url,
                        paired_at=PAIRED_AT,
                        last_contacted_at="2026-07-29T01:00:00.000000+00:00")
    PeerAllowlist(baser).add(record)
    return record


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_refresh_updates_a_stale_record_to_the_newer_published_route(hby, baser):
    """The live failure, at the cache layer: record cached at A, BADA holds a
    newer loc B for the same listener EID — refresh_route repins the record
    at B and preserves the pairing identity fields."""
    ctrl = hby.makeHab(name="ctrl", transferable=True, version=Vrsn_1_0)
    lsn = hby.makeHab(name="lsn", transferable=False, ns="peer",
                      version=Vrsn_1_0)
    _publish(hby, lsn, ctrl, lsn.pre, "tcp://10.211.55.7:5622")
    _pair(baser, ctrl.pre, "tcp://10.211.55.7:5622")

    # The VM re-networks: a NEWER signed /loc/scheme for the same EID lands.
    _publish(hby, lsn, ctrl, lsn.pre, "tcp://192.168.1.40:5622")

    al = PeerAllowlist(baser)
    refreshed = al.refresh_route(hby.db, ctrl.pre)

    assert refreshed is not None
    assert refreshed.endpoint_url == "tcp://192.168.1.40:5622"
    assert refreshed.aid == ctrl.pre
    assert refreshed.label == "requester"
    assert refreshed.paired_at == PAIRED_AT
    assert refreshed.last_contacted_at == "2026-07-29T01:00:00.000000+00:00"
    # Persisted, not just returned — the next reader sees the fresh route.
    assert al.get(ctrl.pre).endpoint_url == "tcp://192.168.1.40:5622"


def test_refresh_keeps_a_record_the_kel_knows_nothing_about(hby, baser):
    """A manual pairing (hand-typed address, peer never published anything)
    must survive refresh verbatim — no authorized route resolving is not a
    reason to clobber the only address we have."""
    aid = "E" + "A" * 43
    _pair(baser, aid, "tcp://192.168.1.9:5621", label="hand-typed")

    refreshed = PeerAllowlist(baser).refresh_route(hby.db, aid)

    assert refreshed is not None
    assert refreshed.endpoint_url == "tcp://192.168.1.9:5621"
    assert refreshed.label == "hand-typed"


def test_refresh_returns_none_for_an_unpaired_aid(hby, baser):
    """Refreshing an AID that was never paired resolves nothing and must not
    invent an allowlist entry (the allowlist is an authorization surface)."""
    al = PeerAllowlist(baser)
    assert al.refresh_route(hby.db, "E" + "B" * 43) is None
    assert al.get("E" + "B" * 43) is None


def test_refresh_is_a_noop_when_the_cache_already_matches(hby, baser, caplog):
    """Same resolved route → no rewrite, no refresh log line (the send path
    calls this every time; a quiet steady state matters)."""
    import logging

    ctrl = hby.makeHab(name="same", transferable=True, version=Vrsn_1_0)
    lsn = hby.makeHab(name="samelsn", transferable=False, ns="peer",
                      version=Vrsn_1_0)
    _publish(hby, lsn, ctrl, lsn.pre, "tcp://192.168.1.40:5622")
    _pair(baser, ctrl.pre, "tcp://192.168.1.40:5622")

    with caplog.at_level(logging.INFO, logger="locksmith.peer.allowlist"):
        refreshed = PeerAllowlist(baser).refresh_route(hby.db, ctrl.pre)

    assert refreshed.endpoint_url == "tcp://192.168.1.40:5622"
    assert not any("peer.route.refreshed" in r.message for r in caplog.records)


def test_refresh_fills_an_empty_endpoint_from_a_later_publication(hby, baser):
    """HOA bring-up can pair before the authority's routes resolve, leaving
    endpoint_url="". Once a route lands, refresh must fill it in — otherwise
    the record gates the peer path off forever."""
    ctrl = hby.makeHab(name="late", transferable=True, version=Vrsn_1_0)
    lsn = hby.makeHab(name="latelsn", transferable=False, ns="peer",
                      version=Vrsn_1_0)
    _pair(baser, ctrl.pre, "", label="authority")

    _publish(hby, lsn, ctrl, lsn.pre, "tcp://192.168.1.40:5622")

    refreshed = PeerAllowlist(baser).refresh_route(hby.db, ctrl.pre)
    assert refreshed.endpoint_url == "tcp://192.168.1.40:5622"
    assert refreshed.label == "authority"


def test_send_dials_the_newer_route_given_a_newer_rpy_has_arrived(hby, baser):
    """THE pinned regression (backlog work item 3): pair at address A, land a
    newer signed /loc/scheme for address B, assert the next send dials B.

    A is a dead port (the old address); B is a live listener. Without the
    refresh the send dials A, times out, and falls back. With it, the bytes
    arrive at B over the peer channel.

    PRECONDITION, and the reason this is not end-to-end coverage of the live
    failure: the ``_publish(url_b)`` call below is the peer having re-published
    its new address. In both live incidents that never happened — no newer rpy
    ever arrived, so the admin's KEL state held the stale address too and this
    refresh would have re-resolved the same dead route. The missing upstream
    link is backlog/2026-07-29-address-change-never-republished.md.
    """
    ctrl = hby.makeHab(name="mover", transferable=True, version=Vrsn_1_0)
    lsn = hby.makeHab(name="moverlsn", transferable=False, ns="peer",
                      version=Vrsn_1_0)

    dead_port = _free_port()
    url_a = f"tcp://127.0.0.1:{dead_port}"          # paired here (stale)
    _publish(hby, lsn, ctrl, lsn.pre, url_a)
    _pair(baser, ctrl.pre, url_a)

    live_port = _free_port()
    url_b = f"tcp://127.0.0.1:{live_port}"          # the peer actually moved here
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", live_port))
    server.listen(1)

    received = bytearray()

    def _accept():
        conn, _ = server.accept()
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                break
            received.extend(chunk)
        conn.close()

    t = threading.Thread(target=_accept, daemon=True)
    t.start()

    _publish(hby, lsn, ctrl, lsn.pre, url_b)  # the newer signed /loc/scheme

    mailbox_calls = []
    try:
        outcome = peer_send(
            allowlist=PeerAllowlist(baser),
            recipient_aid=ctrl.pre,
            exn_bytes=b"GRANT-BYTES",
            mailbox_send=lambda aid, bs: mailbox_calls.append(aid) or True,
            keridb=hby.db,
        )
        t.join(timeout=5.0)
    finally:
        server.close()

    assert outcome is SendOutcome.PEER, (
        f"send should dial the refreshed route {url_b}, not the stale {url_a}")
    assert bytes(received) == b"GRANT-BYTES"
    assert mailbox_calls == []
    # And the cache itself was healed for the next reader.
    assert PeerAllowlist(baser).get(ctrl.pre).endpoint_url == url_b


def test_send_without_keridb_keeps_the_legacy_shape(baser):
    """Callers that have no KERI db in hand (or tests) keep the old contract:
    no refresh, dial the record as cached."""
    _pair(baser, "E" + "C" * 43, "tcp://127.0.0.1:1")  # nothing listening

    calls = []
    outcome = peer_send(
        allowlist=PeerAllowlist(baser),
        recipient_aid="E" + "C" * 43,
        exn_bytes=b"X",
        mailbox_send=lambda aid, bs: calls.append(aid) or True,
    )
    assert outcome is SendOutcome.FALLBACK
    assert calls == ["E" + "C" * 43]
