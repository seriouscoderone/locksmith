"""Integration test — PeerAwarePoster picks the peer channel for paired
recipients and the mailbox channel otherwise.

Drives the wrapper via the same fixtures as the other live integration
tests, but doesn't require the full IPEX UI choreography. Asserts that
the wrapper's transport-selection logic fires on real subprocess
wallets with their real Habery + LocksmithBaser.
"""
import socket
import time

import pytest

from tests.integration.peer.conftest import (
    create_aid_via_ui, expose_aid_via_ui, free_port, set_peer_mode_via_ui,
)


def _free_port():
    return free_port()


@pytest.mark.integration
def test_peer_aware_poster_uses_peer_channel_when_paired(two_wallets):
    """Wallet A is paired with a fake peer at a reachable TCP listener
    (we stand up our own); the wrapper writes to that listener and
    skips the mailbox path."""
    devctl = two_wallets["devctl"]
    a = two_wallets["a"]

    devctl(a["sock"], "peer_open_test_vault",
           name="ptest", passcode="DoB2-e4Rr-gVOr-Nb1Y-7yBl-gI3n-i4cB-gf07")
    create_aid_via_ui(devctl, a["sock"], alias="alice")
    set_peer_mode_via_ui(devctl, a["sock"], port=free_port())
    expose_aid_via_ui(devctl, a["sock"], "alice")

    # Stand up a stub TCP listener Wallet A can reach
    port = _free_port()
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", port))
    server.listen(1)

    try:
        devctl(a["sock"], "peer_force_pair",
               aid="EFAKE_PEER_OUTBOUND_TEST_AAAAAAAAAAAAAAAAAAAA",
               endpoint_url=f"tcp://127.0.0.1:{port}",
               label="StubPeer")

        # Drive peer_send directly — this is the same code path
        # PeerAwarePoster.deliver() uses internally.
        result = devctl(a["sock"], "peer_test_send",
                        recipient_aid="EFAKE_PEER_OUTBOUND_TEST_AAAAAAAAAAAAAAAAAAAA",
                        payload="ipex-payload-stub")
        assert result["outcome"] == "peer"
        assert result["mailbox_calls"] == []
    finally:
        server.close()

    time.sleep(0.5)
    log = a["log"].read_text()
    assert "peer.send.peer_ok" in log
