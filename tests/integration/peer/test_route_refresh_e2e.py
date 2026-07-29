"""Integration test — a moved peer is dialed at its NEW address, end to end.

Two real wallets, real widgets, real TCP. The live failure this pins
(backlog/2026-07-29-peer-record-endpoint-never-refreshes.md) was: the admin's
``PeerRecord`` cached the requester's address at pairing time and every
subsequent send dialed it forever, so a requester that changed address became
permanently unreachable and the grant died silently.

The script:

1. A (joseph) and B (alice) come up with peer listeners; A pairs with B at
   B's FIRST port. A's ``PeerRecord[alice]`` now caches that address.
2. B moves: Settings → a new port → apply, then the *Expose over peer mode*
   toggle off/on, which re-publishes a later-dated signed ``/loc/scheme`` at
   the new port. B's listener is now on the new port and NOTHING is listening
   on the old one.
3. A pastes B's freshly-exported blob into Add Peer. The dialog parses the
   blob (landing the newer signed rpy in A's KEL state via BADA) and THEN
   refuses to pair — so A's cached ``PeerRecord`` still holds the OLD
   address. This is the exact state the live admin was in, and it is also
   what a user trying to self-serve hits: re-pairing is refused and there is
   no unpair/edit UI
   (backlog/2026-07-28-paired-peers-cannot-be-unpaired.md). The refusal
   message itself is misleading — see
   backlog/2026-07-29-reimport-of-a-known-peer-misreports.md, found by this
   test.
4. A issues a credential to alice and clicks Grant.

Asserted on the wire:

- A's log carries ``peer.route.refreshed`` moving the cached record from the
  old port to the new one,
- A's log carries ``peer.send.peer_ok`` at the NEW port (and never at the old
  one), and
- B's log carries ``peer.recv.delivered`` — B's shim accepted the grant.

**Scope.** Step 2 re-publishes deliberately and explicitly, because that is
the precondition this fix needs and the thing that does NOT happen by itself:
``ensure_direct_transport`` re-pins settings when the resolved address moves
but only runs ``PublishPeerRoleDoer`` on FIRST exposure, so a wallet whose
address changes keeps serving its old announcement forever
(backlog/2026-07-29-address-change-never-republished.md — a separate queued
task). Without that upstream fix this test's step 2 is a manual workaround,
not something the field reproduces on its own. Read it as coverage of link 2
of 3: peer re-publishes (upstream, missing) → admin picks up the newer
announcement (HERE) → undeliverable sends fail loudly
(tests/peer/test_deliverability.py).
"""
import time

import pytest

from tests.integration.peer.conftest import (
    create_aid_via_ui, free_port, import_peer_blob_via_ui,
    open_test_vault_via_ui, set_peer_mode_via_ui,
)
from tests.integration.peer.test_send import _expose_and_export, _load_schema


def _reexpose_and_export(devctl, sock, alias):
    """Toggle *Expose over peer mode* off and back on, then read the blob.

    The off/on cycle is what re-publishes: ``_publish_peer_role`` builds the
    ``/loc/scheme`` url from the CURRENT ``peerSettings.port`` each time it
    runs, so after a port change this lands a later-dated rpy at the new port
    (BADA then makes it win over the old one wherever it is parsed).
    """
    devctl(sock, "click_row_action", row_text=alias, action="View")
    devctl(sock, "wait_for", target="viewIdentifierDialog.aidField",
           condition="visible", timeout_ms=3000)

    r = devctl(sock, "is_checked", target="viewIdentifierDialog.exposeToggle")
    assert r.get("ok"), r
    assert r["checked"], "expected alice to already be exposed from setup"

    devctl(sock, "click", target="viewIdentifierDialog.exposeToggle")
    time.sleep(0.6)   # PublishPeerRoleDoer flush (/end/role/cut)
    devctl(sock, "click", target="viewIdentifierDialog.exposeToggle")
    time.sleep(0.8)   # PublishPeerRoleDoer flush (/end/role/add + new loc)

    r = devctl(sock, "is_checked", target="viewIdentifierDialog.exposeToggle")
    assert r == {"ok": True, "checked": True}, r

    devctl(sock, "select", target="viewIdentifierDialog.oobiRoleCombo",
           value="Peer (offline)")
    devctl(sock, "wait_for", target="viewIdentifierDialog.oobiTokenLabel",
           condition="visible", timeout_ms=3000)
    blob = devctl(sock, "get_text",
                  target="viewIdentifierDialog.oobiTokenLabel")["text"]
    devctl(sock, "click", target="Close")
    return blob


def _paste_newer_blob_expecting_refusal(devctl, sock, blob):
    """Paste an already-paired peer's NEWER blob into Add Peer.

    ``AddPeerDialog._on_pair`` calls ``import_peer_blob`` — which PARSES the
    rpys into the KEL state, so BADA accepts the newer ``/loc/scheme`` — and
    only then refuses to pair. The cached ``PeerRecord`` is left untouched,
    which is exactly the live "a known sender's newer rpy arrived, but the
    route cache still holds the old address" state.

    The refusal message is currently WRONG (it claims no peer-role endpoint
    was published rather than "already paired"): ``import_peer_blob`` only
    considers NEWLY-learned kevers as candidates, so a re-import for an AID
    already in ``hby.kevers`` never reaches the already-paired branch. Filed
    as backlog/2026-07-29-reimport-of-a-known-peer-misreports.md. This helper
    asserts only that pairing was REFUSED — the test's real proof is that the
    send below dials the new port, which can only happen if the rpy landed.
    """
    r = devctl(sock, "click", target="vaultNavMenu.settingsButton")
    assert r.get("ok"), r
    devctl(sock, "wait_for", target="peerSettingsSection.addPeerButton",
           condition="visible", timeout_ms=3000)
    devctl(sock, "click", target="peerSettingsSection.addPeerButton")
    devctl(sock, "wait_for", target="addPeerDialog.oobiInput",
           condition="visible", timeout_ms=3000)
    devctl(sock, "type", target="addPeerDialog.oobiInput", text=blob)
    devctl(sock, "click", target="addPeerDialog.pairButton")
    time.sleep(0.5)

    err = devctl(sock, "get_text", target="addPeerDialog.errorLabel")
    assert err.get("text", "").strip(), (
        "expected Add Peer to REFUSE re-pairing an already-paired peer "
        "(leaving the cached record stale); the dialog reported no error, so "
        "the record may have been rewritten and this test would no longer be "
        "exercising the refresh at all"
    )
    devctl(sock, "click", target="addPeerDialog.cancelButton")
    time.sleep(0.3)
    devctl(sock, "click", target="vaultNavMenu.identifiersButton")


@pytest.mark.integration
def test_grant_dials_the_peers_new_address_after_it_moved(two_wallets):
    devctl = two_wallets["devctl"]
    a, b = two_wallets["a"], two_wallets["b"]

    port_b1 = free_port()
    port_b2 = free_port()
    assert port_b1 != port_b2

    # --- bring up both wallets; B listens on its FIRST port ---
    open_test_vault_via_ui(devctl, a["sock"], name="ptest")
    create_aid_via_ui(devctl, a["sock"], alias="joseph")
    set_peer_mode_via_ui(devctl, a["sock"], port=free_port())

    open_test_vault_via_ui(devctl, b["sock"], name="ptest_b")
    create_aid_via_ui(devctl, b["sock"], alias="alice")
    set_peer_mode_via_ui(devctl, b["sock"], port=port_b1)

    # --- mutual pairing at B's FIRST address ---
    alice_blob_old = _expose_and_export(devctl, b["sock"], "alice")
    joseph_blob = _expose_and_export(devctl, a["sock"], "joseph")
    import_peer_blob_via_ui(devctl, a["sock"], alice_blob_old, label="alice")
    import_peer_blob_via_ui(devctl, b["sock"], joseph_blob, label="joseph")

    # --- B MOVES: new port + re-publish at it. Nothing listens on port_b1. ---
    set_peer_mode_via_ui(devctl, b["sock"], port=port_b2)
    alice_blob_new = _reexpose_and_export(devctl, b["sock"], "alice")
    assert alice_blob_new != alice_blob_old, (
        "re-export after the port change should carry different rpys")

    # --- A learns the newer route but keeps the stale cached record ---
    _paste_newer_blob_expecting_refusal(
        devctl, a["sock"], alice_blob_new)

    # --- schemas, then issue + grant from A to alice ---
    _load_schema(devctl, a["sock"], with_registry=True)
    _load_schema(devctl, b["sock"], with_registry=False)

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
           target="Greeting message *", text="hello-after-the-move")
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
    time.sleep(8.0)

    # --- wire-level assertions ---
    log_a = a["log"].read_text()
    old_url = f"tcp://127.0.0.1:{port_b1}"
    new_url = f"tcp://127.0.0.1:{port_b2}"

    assert "peer.route.refreshed" in log_a, (
        "A never re-resolved the cached route; the send would have dialed "
        f"the stale {old_url} forever. Log tail:\n{log_a[-4000:]}"
    )
    assert f"to={new_url}" in log_a, (
        f"the refresh should have moved the record to {new_url}. Log tail:\n"
        f"{log_a[-4000:]}"
    )
    assert f"peer.send.peer_ok" in log_a, (
        f"A's grant was not delivered over peer transport. Log tail:\n"
        f"{log_a[-4000:]}"
    )
    assert f"peer.send.peer_ok recipient=" in log_a and f"endpoint={new_url}" in log_a, (
        f"the successful send should name {new_url}. Log tail:\n{log_a[-4000:]}"
    )
    assert f"peer.send.peer_ok" not in "".join(
        line for line in log_a.splitlines() if old_url in line
    ), f"a send succeeded against the STALE {old_url}; nothing listens there"
    assert "channel=peer" in log_a, (
        "the grant fell back to mailbox instead of the refreshed peer route")

    log_b = b["log"].read_text()
    assert "peer.recv.delivered" in log_b, (
        "B's shim never delivered the grant — the bytes did not arrive at "
        f"the new port. Log tail:\n{log_b[-4000:]}"
    )
