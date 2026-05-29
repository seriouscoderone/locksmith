"""Tests for PeerHealthMonitorDoer — periodically probes each paired
peer's TCP endpoint and writes the outcome to db.peerHealth.
"""
from __future__ import annotations

import socket
from datetime import datetime, timezone

import pytest
from hio.base import doing

from locksmith.peer.allowlist import PeerAllowlist
from locksmith.peer.health import PeerHealthMonitorDoer
from locksmith.peer.records import PeerHealth, PeerRecord
from locksmith.peer.reachability import ReachabilityResult


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _add_peer(allowlist: PeerAllowlist, aid: str, endpoint_url: str) -> None:
    allowlist.add(PeerRecord(
        aid=aid, label=aid[:6], endpoint_url=endpoint_url, paired_at=_now(),
    ))


def _bind_random_port() -> tuple[socket.socket, int]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    return s, s.getsockname()[1]


def test_reachable_peer_recorded_as_ok(baser):
    allowlist = PeerAllowlist(baser)
    server, port = _bind_random_port()
    try:
        _add_peer(allowlist, "EAID_ALICE", f"tcp://127.0.0.1:{port}")
        doer = PeerHealthMonitorDoer(
            allowlist=allowlist, db=baser,
            interval_seconds=1.0, probe_timeout=0.5,
        )
        # One immediate probe cycle, then exit before the next sleep.
        doer.probe_all_once()
    finally:
        server.close()

    health = baser.peerHealth.get(keys=("EAID_ALICE",))
    assert health is not None
    assert health.last_outcome == "ok"
    assert health.consecutive_successes == 1
    assert health.consecutive_failures == 0
    assert health.probed_count == 1
    assert health.last_probed_at  # ISO timestamp populated


def test_unreachable_peer_records_failure_and_counts(baser):
    allowlist = PeerAllowlist(baser)
    # 127.0.0.1:1 — nothing listening; connection refused
    _add_peer(allowlist, "EAID_BOB", "tcp://127.0.0.1:1")
    doer = PeerHealthMonitorDoer(
        allowlist=allowlist, db=baser,
        interval_seconds=1.0, probe_timeout=0.3,
    )
    doer.probe_all_once()
    doer.probe_all_once()  # second cycle should bump consecutive_failures

    health = baser.peerHealth.get(keys=("EAID_BOB",))
    assert health is not None
    assert health.last_outcome == "refused"
    assert health.consecutive_failures == 2
    assert health.consecutive_successes == 0
    assert health.probed_count == 2


def test_recovery_resets_failure_counter(baser):
    allowlist = PeerAllowlist(baser)
    server, port = _bind_random_port()
    try:
        _add_peer(allowlist, "EAID_CHARLIE", f"tcp://127.0.0.1:{port}")
        doer = PeerHealthMonitorDoer(
            allowlist=allowlist, db=baser,
            interval_seconds=1.0, probe_timeout=0.5,
        )
        # Seed a fake failure state on this peer first
        baser.peerHealth.pin(keys=("EAID_CHARLIE",), val=PeerHealth(
            aid="EAID_CHARLIE",
            last_probed_at=_now(),
            last_outcome="refused",
            last_message="prior failure",
            consecutive_failures=3,
            consecutive_successes=0,
            probed_count=3,
        ))
        doer.probe_all_once()
    finally:
        server.close()

    health = baser.peerHealth.get(keys=("EAID_CHARLIE",))
    assert health.consecutive_failures == 0
    assert health.consecutive_successes == 1
    assert health.probed_count == 4


def test_malformed_endpoint_records_invalid_host(baser):
    """An endpoint that can't be parsed into host+port shouldn't crash
    the monitor; record an invalid_host outcome so the UI can flag it.
    """
    allowlist = PeerAllowlist(baser)
    _add_peer(allowlist, "EAID_BAD", "not-a-tcp-url")
    doer = PeerHealthMonitorDoer(
        allowlist=allowlist, db=baser,
        interval_seconds=1.0, probe_timeout=0.3,
    )
    doer.probe_all_once()

    health = baser.peerHealth.get(keys=("EAID_BAD",))
    assert health is not None
    assert health.last_outcome == "invalid_host"


def test_empty_allowlist_is_noop(baser):
    allowlist = PeerAllowlist(baser)
    doer = PeerHealthMonitorDoer(
        allowlist=allowlist, db=baser,
        interval_seconds=1.0, probe_timeout=0.3,
    )
    # Should not raise and should not populate any health records.
    doer.probe_all_once()
    assert list(baser.peerHealth.getTopItemIter()) == []


def test_doer_loop_terminates_on_stop(baser):
    """The hio doer should yield while sleeping and exit cleanly when
    the doist's limit elapses. Guards against busy-loops.
    """
    allowlist = PeerAllowlist(baser)
    doer = PeerHealthMonitorDoer(
        allowlist=allowlist, db=baser,
        interval_seconds=0.05, probe_timeout=0.1,
    )
    doist = doing.Doist(limit=0.5, tock=0.01, real=False)
    # Should return within limit without raising.
    doist.do(doers=[doer])
