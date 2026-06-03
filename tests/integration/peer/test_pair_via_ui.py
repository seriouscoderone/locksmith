"""Integration test — pair two wallets via the Add Peer dialog UI.

A exposes alice and exports the CESR blob through View Identifier →
"Peer (offline)". B pastes that blob into the Add Peer dialog (Settings
→ Pair new peer) and clicks Pair. The peer list on B should then
contain alice.

This is the live wire-level proof of the witness-less pairing UI:
every step the user touches — settings nav, dialog open, paste, click
— is driven through real widgets. Replaces the peer_import_blob bypass.
"""
import time

import pytest

from tests.integration.peer.conftest import (
    create_aid_via_ui,
    free_port,
    import_peer_blob_via_ui,
    set_peer_mode_via_ui,
)


@pytest.mark.integration
def test_pair_via_add_peer_dialog(two_wallets):
    devctl = two_wallets["devctl"]
    a, b = two_wallets["a"], two_wallets["b"]

    # --- A: create alice, expose + export blob in a single View dialog
    # session (open once, toggle expose, select role, read token). The
    # expose-then-close-then-reopen pattern is avoided because reopening
    # a dialog by row_action in quick succession races against the
    # close animation. ---
    r = devctl(a["sock"], "peer_open_test_vault",
               name="ptest",
               passcode="DoB2-e4Rr-gVOr-Nb1Y-7yBl-gI3n-i4cB-gf07")
    assert r.get("ok"), r
    create_aid_via_ui(devctl, a["sock"], alias="alice")
    set_peer_mode_via_ui(devctl, a["sock"], port=free_port())

    r = devctl(a["sock"], "click_row_action",
               row_text="alice", action="View")
    assert r.get("ok"), r
    r = devctl(a["sock"], "wait_for",
               target="viewIdentifierDialog.aidField",
               condition="visible", timeout_ms=3000)
    assert r.get("ok"), r

    # Toggle expose on.
    r = devctl(a["sock"], "click",
               target="viewIdentifierDialog.exposeToggle")
    assert r.get("ok"), r
    time.sleep(0.5)  # PublishPeerRoleDoer flush

    # Select Peer (offline) role to render the blob.
    r = devctl(a["sock"], "select",
               target="viewIdentifierDialog.oobiRoleCombo",
               value="Peer (offline)")
    assert r.get("ok"), r
    r = devctl(a["sock"], "wait_for",
               target="viewIdentifierDialog.oobiTokenLabel",
               condition="visible", timeout_ms=3000)
    assert r.get("ok"), r
    r = devctl(a["sock"], "get_text",
               target="viewIdentifierDialog.oobiTokenLabel")
    assert r.get("ok"), r
    blob = r["text"]
    assert blob.startswith("locksmith-peer-oobi:v1:"), blob

    # --- B: bring up vault, paste the blob via Add Peer dialog ---
    r = devctl(b["sock"], "peer_open_test_vault",
               name="ptest",
               passcode="DoB2-e4Rr-gVOr-Nb1Y-7yBl-gI3n-i4cB-gf07")
    assert r.get("ok"), r
    set_peer_mode_via_ui(devctl, b["sock"], port=free_port())

    import_peer_blob_via_ui(devctl, b["sock"], blob, label="alice@A")

    # B's allowlist should now contain alice. peer_list is a diagnostic
    # query (no UI-only equivalent for reading the allowlist with the
    # endpoint URL attached, so we keep the existing diagnostic).
    r = devctl(b["sock"], "peer_list")
    assert r.get("ok"), r
    peers = r["peers"]
    assert len(peers) == 1, peers
    assert peers[0]["label"] == "alice@A", peers[0]
    assert peers[0]["endpoint_url"].startswith("tcp://"), peers[0]
