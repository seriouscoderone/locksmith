"""Integration test — IPEX credential grant delivered over peer transport.

Two real wallets:
  - B (alice) brings up vault, AID, peer listener, exposes alice.
  - A (joseph) brings up vault, AID, peer listener.
  - Mutual pairing via the witness-less CESR-blob OOBI (paste blob in
    the Add Peer dialog, both directions).
  - Both load a minimal demo schema; A creates a credential registry.
  - A issues a credential to alice and clicks Grant.

Asserts the wire-level evidence:
  - A's log carries ``peer.send.peer_ok`` with ``channel=peer`` (not
    the mailbox fallback).
  - B's log carries ``peer.recv.delivered`` — the PeerExchangerShim
    accepted the grant and handed it to the Exchanger.

Together these prove the credential grant moved from A's
SendGrantDoer → PeerAwarePoster → TCP → B's Directant → Reactant →
Parser → shim → Exchanger, all driven through real widgets.
"""
import time
from pathlib import Path

import pytest

from tests.integration.peer.conftest import (
    create_aid_via_ui, free_port, import_peer_blob_via_ui,
    open_test_vault_via_ui, set_peer_mode_via_ui,
)


SCHEMA_FIXTURE = (
    Path(__file__).parent / "fixtures" / "demo-greeting.json"
)


def _expose_and_export(devctl, sock, alias):
    """Open View Identifier, toggle expose, pick Peer (offline) role,
    return the rendered CESR blob (one dialog session).
    """
    devctl(sock, "click_row_action", row_text=alias, action="View")
    devctl(sock, "wait_for",
           target="viewIdentifierDialog.aidField",
           condition="visible", timeout_ms=3000)
    devctl(sock, "click", target="viewIdentifierDialog.exposeToggle")
    time.sleep(0.5)  # PublishPeerRoleDoer flush
    devctl(sock, "select",
           target="viewIdentifierDialog.oobiRoleCombo",
           value="Peer (offline)")
    devctl(sock, "wait_for",
           target="viewIdentifierDialog.oobiTokenLabel",
           condition="visible", timeout_ms=3000)
    return devctl(sock, "get_text",
                  target="viewIdentifierDialog.oobiTokenLabel")["text"]


def _load_schema(devctl, sock, with_registry):
    devctl(sock, "click", target="vaultNavMenu.credentialsButton")
    time.sleep(0.3)
    devctl(sock, "click", target="vaultNavMenu.schemaButton")
    time.sleep(0.5)
    devctl(sock, "click", target="Add Schema")
    time.sleep(0.3)
    devctl(sock, "click", target="File")
    time.sleep(0.2)
    devctl(sock, "type", target="File Path", text=str(SCHEMA_FIXTURE))
    time.sleep(0.5)
    if with_registry:
        devctl(sock, "click", target="Use for Credential Issuance")
        time.sleep(0.3)
        devctl(sock, "select", target="Issuer", index=1)
        time.sleep(0.3)
    devctl(sock, "click", target="Load Schema")
    time.sleep(2.5)


@pytest.mark.integration
def test_ipex_grant_routes_over_peer_channel(two_wallets):
    devctl = two_wallets["devctl"]
    a, b = two_wallets["a"], two_wallets["b"]

    # --- bring up both wallets ---
    open_test_vault_via_ui(devctl, a["sock"], name="ptest")
    create_aid_via_ui(devctl, a["sock"], alias="joseph")
    set_peer_mode_via_ui(devctl, a["sock"], port=free_port())

    open_test_vault_via_ui(devctl, b["sock"], name="ptest")
    create_aid_via_ui(devctl, b["sock"], alias="alice")
    set_peer_mode_via_ui(devctl, b["sock"], port=free_port())

    # --- mutual pairing ---
    alice_blob = _expose_and_export(devctl, b["sock"], "alice")
    joseph_blob = _expose_and_export(devctl, a["sock"], "joseph")
    import_peer_blob_via_ui(devctl, a["sock"], alice_blob, label="alice")
    import_peer_blob_via_ui(devctl, b["sock"], joseph_blob, label="joseph")

    # --- schemas ---
    _load_schema(devctl, a["sock"], with_registry=True)
    _load_schema(devctl, b["sock"], with_registry=False)

    # --- issue + grant ---
    devctl(a["sock"], "click", target="vaultNavMenu.issuedCredentialsButton")
    time.sleep(0.5)
    devctl(a["sock"], "click", target="Issue Credential")
    time.sleep(0.5)
    devctl(a["sock"], "select",
           target="issueCredentialDialog.schemaCombo", index=1)
    time.sleep(0.5)
    devctl(a["sock"], "select",
           target="issueCredentialDialog.recipientCombo", index=1)
    time.sleep(0.5)
    devctl(a["sock"], "type",
           target="Greeting message *", text="hello-over-peer")
    time.sleep(0.3)
    devctl(a["sock"], "click", target="issueCredentialDialog.issueButton")
    time.sleep(3.0)

    devctl(a["sock"], "click_row_action",
           row_text="Demo Greeting", action="Grant")
    time.sleep(1.0)
    devctl(a["sock"], "select",
           target="grantCredentialDialog.recipientCombo", index=0)
    time.sleep(0.3)
    devctl(a["sock"], "click", target="grantCredentialDialog.grantButton")

    # Wait for the grant message to round-trip the loopback. peer_send
    # is sub-millisecond; B's Reactant+shim+exchanger chain processes
    # within a few hundred ms. Be generous.
    time.sleep(8.0)

    # --- wire-level assertions on both logs ---
    log_a = a["log"].read_text()
    assert "peer.send.peer_ok" in log_a, (
        "A's PeerAwarePoster should have chosen the peer channel; "
        "missing peer.send.peer_ok"
    )
    assert "channel=peer" in log_a, (
        "A's grant routed through mailbox instead of peer: missing "
        "channel=peer"
    )

    log_b = b["log"].read_text()
    assert "peer.recv.delivered" in log_b, (
        "B's shim never delivered the grant — bytes arrived but parse "
        "or gate dropped them. Check Directant/Reactant wiring."
    )
