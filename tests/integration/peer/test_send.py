"""Integration test — peer_send routes to peer endpoint when reachable.

Sets up two wallets, force-pairs them, then drives A's peer_send via
devctl with a placeholder payload. Asserts A logs peer.send.peer_ok
and the TCP connection actually reached B's listener (visible as a
non-error byte arrival; we can't assert peer.recv.delivered because
the placeholder payload isn't a valid CESR exn).

This is the live wire-level confirmation that peer_send's PEER branch
works end-to-end against a real subprocess listener.
"""
import time

import pytest

from tests.integration.peer.conftest import expose_aid_via_ui


def _setup_wallet(devctl, sock, alias):
    devctl(sock, "peer_open_test_vault",
           name="ptest", passcode="DoB2-e4Rr-gVOr-Nb1Y-7yBl-gI3n-i4cB-gf07")
    devctl(sock, "peer_create_test_aid", alias=alias)
    devctl(sock, "peer_set_mode", enabled=True, port=0)
    expose_aid_via_ui(devctl, sock, alias)


@pytest.mark.integration
def test_peer_send_to_reachable_peer_uses_peer_channel(two_wallets):
    devctl = two_wallets["devctl"]
    a, b = two_wallets["a"], two_wallets["b"]

    _setup_wallet(devctl, a["sock"], "alice")
    _setup_wallet(devctl, b["sock"], "bob")

    aid_b = devctl(b["sock"], "peer_get_aid_pre", alias="bob")["aid"]
    port_b = devctl(b["sock"], "peer_get_port")["port"]

    # A force-pairs B's endpoint
    r = devctl(a["sock"], "peer_force_pair",
               aid=aid_b, endpoint_url=f"tcp://127.0.0.1:{port_b}", label="Bob")
    assert r.get("ok") is True

    # A calls peer_send → should hit B's listener
    r = devctl(a["sock"], "peer_test_send",
               recipient_aid=aid_b, payload="placeholder-bytes")
    assert r.get("ok") is True, r
    assert r["outcome"] == "peer", r
    assert r["mailbox_calls"] == [], "mailbox shouldn't have been called"

    time.sleep(0.5)

    log_a = a["log"].read_text()
    assert "peer.send.attempt" in log_a
    assert "peer.send.peer_ok" in log_a
