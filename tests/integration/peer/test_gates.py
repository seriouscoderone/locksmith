"""Integration test — peer socket gate behavior.

Wire-level checks against a live subprocess wallet:

  - Sending garbage bytes to the peer socket does not crash the listener
    and does not produce a `peer.recv.delivered` log line (i.e. the
    handler stack was never reached).

The full sender-allowlist and destination-allowlist rejection paths
are covered by the unit tests in tests/peer/test_shim.py. Reproducing
them as live wire tests requires constructing valid signed CESR
exn messages from a paired sender wallet, which depends on full IPEX
issuance machinery — out of scope for the MVP integration suite.
A follow-up will exercise those gates via a programmatic exn helper.
"""
import socket
import time

import pytest

from tests.integration.peer.conftest import (
    expose_aid_via_ui, free_port, set_peer_mode_via_ui,
)


@pytest.mark.integration
def test_garbage_bytes_do_not_reach_handler_stack(two_wallets):
    devctl = two_wallets["devctl"]
    b = two_wallets["b"]

    # Bring B's vault + peer listener up
    r = devctl(b["sock"], "peer_open_test_vault",
               name="ptest", passcode="DoB2-e4Rr-gVOr-Nb1Y-7yBl-gI3n-i4cB-gf07")
    assert r.get("ok") is True, r
    r = devctl(b["sock"], "peer_create_test_aid", alias="bob")
    assert r.get("ok") is True, r
    port = free_port()
    set_peer_mode_via_ui(devctl, b["sock"], port=port)
    expose_aid_via_ui(devctl, b["sock"], "bob")

    # Connect and send garbage — not valid CESR.
    s = socket.create_connection(("127.0.0.1", port), timeout=3.0)
    try:
        s.sendall(b"\x00" * 64 + b"this is not a cesr exn")
    finally:
        s.close()

    # Let the server process the bytes
    time.sleep(1.0)

    # Listener should still be up (we can still ping the dev-control socket)
    pong = devctl(b["sock"], "ping")
    assert pong.get("ok") is True

    # Verify nothing reached the shim's delivery path
    log_b = b["log"].read_text()
    assert "peer.recv.delivered" not in log_b, (
        f"unexpected delivery from garbage bytes; tail:\n{log_b[-1500:]}"
    )
    # The listener-started log should still be there (sanity)
    assert "peer.listener.started" in log_b
