"""Integration test — export the witness-less peer OOBI through the UI.

Drives the View Identifier dialog the same way a user would:
  1. Click the alice row's "View" action in the identifier list.
  2. Select "Peer (offline)" in the OOBI role dropdown.
  3. Read the rendered token from the QLabel.

This replaces the `peer_export_blob` devctl bypass — it proves the UI
surface works end-to-end and exercises every widget the user touches.
Once peer_open_test_vault / peer_create_test_aid / peer_set_mode /
peer_expose_aid are themselves replaced with click sequences in
subsequent refactors, this test will run without any harness bypass
calls.

Why a separate test file: keeps the PoC visible during the harness
refactor. After the refactor lands, the assertion belongs alongside
the rest of the OOBI export coverage.
"""
import time

import pytest


@pytest.mark.integration
def test_export_blob_via_view_identifier_dialog(two_wallets):
    devctl = two_wallets["devctl"]
    a = two_wallets["a"]

    # --- setup (still uses bypasses pending step-4 of the refactor) ---
    r = devctl(a["sock"], "peer_open_test_vault",
               name="exptest",
               passcode="DoB2-e4Rr-gVOr-Nb1Y-7yBl-gI3n-i4cB-gf07")
    assert r.get("ok"), r
    r = devctl(a["sock"], "peer_set_mode", enabled=True, port=0,
               advertised_host="127.0.0.1")
    assert r.get("ok"), r
    r = devctl(a["sock"], "peer_create_test_aid", alias="alice")
    assert r.get("ok"), r
    r = devctl(a["sock"], "peer_expose_aid", alias="alice")
    assert r.get("ok"), r

    # Let the publish doer flush so the OOBI role rpys are in the KEL.
    time.sleep(0.5)

    # --- drive the UI ---
    # The identifier table renders rows by alias text. The harness's
    # click_row_action finds the row and triggers the per-row action menu.
    r = devctl(a["sock"], "click_row_action",
               row_text="alice", action="View")
    assert r.get("ok"), r

    # ViewIdentifierDialog opens; wait for the AID field to materialize.
    r = devctl(a["sock"], "wait_for",
               target="viewIdentifierDialog.aidField",
               condition="visible", timeout_ms=3000)
    assert r.get("ok"), r

    # Pick the witness-less peer OOBI role. The dropdown selection
    # triggers _generate_peer_blob which renders the token QLabel.
    r = devctl(a["sock"], "select",
               target="viewIdentifierDialog.oobiRoleCombo",
               value="Peer (offline)")
    assert r.get("ok"), r

    # Wait for the token label to appear.
    r = devctl(a["sock"], "wait_for",
               target="viewIdentifierDialog.oobiTokenLabel",
               condition="visible", timeout_ms=3000)
    assert r.get("ok"), r

    # Read the rendered token.
    r = devctl(a["sock"], "get_text",
               target="viewIdentifierDialog.oobiTokenLabel")
    assert r.get("ok"), r
    token = r["text"]
    assert token.startswith("locksmith-peer-oobi:v1:"), token
    # Reasonable size sanity — a real blob is around 1.8KB.
    assert len(token) > 1000, f"blob suspiciously short ({len(token)} chars)"
