"""Integration test — expose and export through the View Identifier UI.

Drives the View Identifier dialog the same way a user would:
  1. Click the alice row's "View" action in the identifier list.
  2. Toggle "Expose over peer mode" on (publishes role/loc rpys).
  3. Select "Peer (offline)" in the OOBI role dropdown.
  4. Read the rendered CESR blob from the QLabel.

This replaces both `peer_export_blob` and `peer_expose_aid` harness
bypasses — every action is a real widget interaction. Once
peer_open_test_vault / peer_create_test_aid / peer_set_mode are
also replaced with click sequences in subsequent refactors, this
test will run without any harness bypass calls.
"""
import time

import pytest

from tests.integration.peer.conftest import (
    free_port, set_peer_mode_via_ui,
)


@pytest.mark.integration
def test_expose_and_export_via_view_identifier_dialog(two_wallets):
    devctl = two_wallets["devctl"]
    a = two_wallets["a"]

    # --- setup (peer_open_test_vault + peer_create_test_aid are the
    # remaining bypasses pending later refactor steps) ---
    r = devctl(a["sock"], "peer_open_test_vault",
               name="exptest",
               passcode="DoB2-e4Rr-gVOr-Nb1Y-7yBl-gI3n-i4cB-gf07")
    assert r.get("ok"), r
    r = devctl(a["sock"], "peer_create_test_aid", alias="alice")
    assert r.get("ok"), r
    # Enable peer mode through Settings → Peer Mode UI.
    set_peer_mode_via_ui(devctl, a["sock"], port=free_port())

    # --- drive the UI ---
    # Open View Identifier dialog for alice.
    r = devctl(a["sock"], "click_row_action",
               row_text="alice", action="View")
    assert r.get("ok"), r
    r = devctl(a["sock"], "wait_for",
               target="viewIdentifierDialog.aidField",
               condition="visible", timeout_ms=3000)
    assert r.get("ok"), r

    # Expose toggle starts unchecked for a brand-new AID.
    r = devctl(a["sock"], "is_checked",
               target="viewIdentifierDialog.exposeToggle")
    assert r == {"ok": True, "checked": False}

    # Toggle on — fires _on_peer_expose_toggled, which adds the AID to
    # _peer_exposed_aids AND runs PublishPeerRoleDoer to publish the
    # role + loc rpys into the KEL.
    r = devctl(a["sock"], "click",
               target="viewIdentifierDialog.exposeToggle")
    assert r.get("ok"), r
    r = devctl(a["sock"], "is_checked",
               target="viewIdentifierDialog.exposeToggle")
    assert r == {"ok": True, "checked": True}

    # Give the publish doer a tick to write rpys to db.
    time.sleep(0.5)

    # Pick the witness-less peer OOBI role; renders the token QLabel.
    r = devctl(a["sock"], "select",
               target="viewIdentifierDialog.oobiRoleCombo",
               value="Peer (offline)")
    assert r.get("ok"), r
    r = devctl(a["sock"], "wait_for",
               target="viewIdentifierDialog.oobiTokenLabel",
               condition="visible", timeout_ms=3000)
    assert r.get("ok"), r

    # Read the rendered token; presence of the role rpys is implied by
    # the blob length (a bare-KEL blob is ~460 bytes; with role/loc
    # rpys + their attachment groups it grows to ~1.8KB).
    r = devctl(a["sock"], "get_text",
               target="viewIdentifierDialog.oobiTokenLabel")
    assert r.get("ok"), r
    token = r["text"]
    assert token.startswith("locksmith-peer-oobi:v1:"), token
    assert len(token) > 1000, (
        f"blob suspiciously short ({len(token)} chars); "
        "the expose toggle may not have actually published the role/loc rpys"
    )
