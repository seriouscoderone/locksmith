"""Integration test — pairing happy path.

Two HOME-isolated wallets each:
  1. Open a fresh test vault.
  2. Create an AID (no witnesses — direct mode doesn't need them for
     the in-vault wire test).
  3. Enable peer mode on a free port and expose the AID.
  4. Read out the other AID's pre + peer endpoint URL.
  5. Force-pair via devctl (bypassing OOBI resolution — exercised in
     unit tests under tests/peer/test_peers_page.py).

The success criterion is that each wallet's allowlist contains the
other's AID after force_pair, and the structured log line
`peer.pair.success` is present in the wallet's log file.

These tests skip the OOBI-resolution path because that requires a
witness round-trip and a fully-published role authorization, which
adds witness-server flakiness without exercising any of the new code
introduced for peer mode (OOBI resolution is keripy machinery).
"""
import time

import pytest

from tests.integration.peer.conftest import expose_aid_via_ui


@pytest.mark.integration
def test_force_pair_populates_allowlists_both_directions(two_wallets):
    devctl = two_wallets["devctl"]
    a = two_wallets["a"]
    b = two_wallets["b"]

    # Bring vaults up on both sides
    for wallet in (a, b):
        r = devctl(wallet["sock"], "peer_open_test_vault",
                   name="ptest", passcode="DoB2-e4Rr-gVOr-Nb1Y-7yBl-gI3n-i4cB-gf07")
        assert r.get("ok") is True, r
        r = devctl(wallet["sock"], "peer_create_test_aid", alias="alice_or_bob")
        assert r.get("ok") is True, r
        r = devctl(wallet["sock"], "peer_set_mode", enabled=True, port=0)
        assert r.get("ok") is True, r
        expose_aid_via_ui(devctl, wallet["sock"], "alice_or_bob")

    # Read each side's AID pre + bound port
    aid_a = devctl(a["sock"], "peer_get_aid_pre", alias="alice_or_bob")["aid"]
    aid_b = devctl(b["sock"], "peer_get_aid_pre", alias="alice_or_bob")["aid"]
    port_a = devctl(a["sock"], "peer_get_port")["port"]
    port_b = devctl(b["sock"], "peer_get_port")["port"]

    # Force-pair both directions
    r = devctl(b["sock"], "peer_force_pair",
               aid=aid_a, endpoint_url=f"tcp://127.0.0.1:{port_a}", label="Alice")
    assert r.get("ok") is True, r
    r = devctl(a["sock"], "peer_force_pair",
               aid=aid_b, endpoint_url=f"tcp://127.0.0.1:{port_b}", label="Bob")
    assert r.get("ok") is True, r

    # Verify both allowlists
    peers_on_a = devctl(a["sock"], "peer_list")["peers"]
    peers_on_b = devctl(b["sock"], "peer_list")["peers"]
    assert any(p["aid"] == aid_b for p in peers_on_a), peers_on_a
    assert any(p["aid"] == aid_a for p in peers_on_b), peers_on_b

    # Give logging a beat to flush
    time.sleep(0.5)
    log_a = a["log"].read_text()
    log_b = b["log"].read_text()
    assert "peer.pair.success" in log_a
    assert "peer.pair.success" in log_b
