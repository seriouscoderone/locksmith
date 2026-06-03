"""Integration test — peer_send routes to peer endpoint when reachable.

Two real wallets:
  - B exposes bob and exports the witness-less peer-OOBI blob through
    the View Identifier dialog (one session: toggle expose, select role,
    read token).
  - A pastes that blob into the Add Peer dialog and clicks Pair.
  - A drives peer_send → A's TCP connect lands on B's listener.

Asserts the outcome is "peer" (not the mailbox fallback), no mailbox
stub was invoked, and A's log carries peer.send.peer_ok. This is the
wire-level proof of delivery — unit tests cover the routing-decision
logic alone; this proves the network path actually works between two
subprocesses.

The diagnostic peer_test_send op survives because there's no UI surface
for "send a raw exn from this wallet to that peer" — IPEX constructs
grant messages, but this test is at the transport layer.
"""
import time

import pytest

from tests.integration.peer.conftest import (
    create_aid_via_ui, free_port, import_peer_blob_via_ui,
    open_test_vault_via_ui, set_peer_mode_via_ui,
)


def _setup_basic(devctl, sock, alias):
    """Vault + AID + peer-mode listener. No expose — caller does that
    in the View Identifier session that also reads the blob."""
    open_test_vault_via_ui(devctl, sock, name="ptest")
    create_aid_via_ui(devctl, sock, alias=alias)
    set_peer_mode_via_ui(devctl, sock, port=free_port())


def _expose_and_export(devctl, sock, alias):
    """Open View Identifier, toggle expose ON, select Peer (offline)
    role, return the rendered CESR blob. One dialog session — avoids
    the open-close-reopen race the separate helpers hit.
    """
    r = devctl(sock, "click_row_action",
               row_text=alias, action="View")
    assert r.get("ok"), r
    r = devctl(sock, "wait_for",
               target="viewIdentifierDialog.aidField",
               condition="visible", timeout_ms=3000)
    assert r.get("ok"), r

    r = devctl(sock, "click",
               target="viewIdentifierDialog.exposeToggle")
    assert r.get("ok"), r
    time.sleep(0.5)  # PublishPeerRoleDoer flush

    r = devctl(sock, "select",
               target="viewIdentifierDialog.oobiRoleCombo",
               value="Peer (offline)")
    assert r.get("ok"), r
    r = devctl(sock, "wait_for",
               target="viewIdentifierDialog.oobiTokenLabel",
               condition="visible", timeout_ms=3000)
    assert r.get("ok"), r
    r = devctl(sock, "get_text",
               target="viewIdentifierDialog.oobiTokenLabel")
    assert r.get("ok"), r
    return r["text"]


@pytest.mark.integration
def test_peer_send_to_reachable_peer_uses_peer_channel(two_wallets):
    devctl = two_wallets["devctl"]
    a, b = two_wallets["a"], two_wallets["b"]

    _setup_basic(devctl, a["sock"], "alice")
    _setup_basic(devctl, b["sock"], "bob")

    # B exposes bob and emits the blob in one View Identifier session.
    bob_blob = _expose_and_export(devctl, b["sock"], "bob")
    assert bob_blob.startswith("locksmith-peer-oobi:v1:"), bob_blob

    # A pastes the blob through the real Add Peer dialog.
    import_peer_blob_via_ui(devctl, a["sock"], bob_blob, label="Bob")

    # Diagnostic readback — no UI surface for "give me the recipient's pre."
    aid_b = devctl(b["sock"], "peer_get_aid_pre", alias="bob")["aid"]

    r = devctl(a["sock"], "peer_test_send",
               recipient_aid=aid_b, payload="placeholder-bytes")
    assert r.get("ok") is True, r
    assert r["outcome"] == "peer", r
    assert r["mailbox_calls"] == [], "mailbox shouldn't have been called"

    time.sleep(0.5)
    log_a = a["log"].read_text()
    assert "peer.send.attempt" in log_a
    assert "peer.send.peer_ok" in log_a
