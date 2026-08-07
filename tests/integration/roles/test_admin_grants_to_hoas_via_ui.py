# -*- encoding: utf-8 -*-
"""The real ecosystem shape: a vanilla admin serving two branded HOAs.

Every leg runs through a real UI in a real process. Nothing is issued in-process
on the test's behalf, and nothing is handed to a wallet as a file.

`four_wallets`' docstring explains why this used to be impossible, and the
distinction matters: the blocker was always the *vanilla recipient*, whose
Notifications admit goes through `QDialog.exec()` — a modal on the Qt main
thread the devctl server dispatches on, deadlocking the harness. Vanilla
ISSUING and GRANTING was always drivable, and an HOA recipient admits with no
modal at all. So vanilla-admin -> HOA-recipient is precisely the combination
that works.

The second thing that made it impossible was trust, not UI: a branded HOA
accepts role credentials only from the authority its EGF pins, which ships as
the real usurance-admin. `admin_then_two_hoas` mints an ecosystem rooted at a
wallet the suite owns instead — see tests/integration/peer/testegf.py.

Built leg by leg; nothing here asserts a step that has not actually been driven.
"""
import time
from pathlib import Path

import pytest

from tests.integration.peer.conftest import (  # noqa: F401 (fixture)
    accept_grant_via_hoa_notifications, admin_then_two_hoas, create_aid_via_ui,
    free_port, import_peer_blob_via_ui, landing_target, open_test_vault_via_ui,
    open_workspace_via_hoa_setup, set_peer_mode_via_ui, wait_for_peer_reachable,
)
from tests.integration.roles.conftest import (
    ACTUARY_ROLE_SCHEMA_SAID, CUO_ROLE_SCHEMA_SAID, _expose_and_export,
    issue_and_grant_role_via_admin_ui, load_issuable_schema_via_admin_ui,
    request_role_via_hoa_ui, wait_for_admin_notifications,
)

pytestmark = pytest.mark.integration


def _bring_up_hoa(devctl, wallet, vault_name):
    """Open an HOA's vault and put it on the air. It mints its own identifier."""
    sock = wallet["sock"]
    open_test_vault_via_ui(devctl, sock, vault_name)
    set_peer_mode_via_ui(devctl, sock, port=free_port())
    return sock


def test_the_admin_pairs_outward_with_both_hoas(admin_then_two_hoas):
    """Leg 2 — the admin does the pairing, which is what makes this tractable.

    A peeled HOA only has to PUBLISH its OOBI, which Settings renders in a
    readable field; the vanilla admin imports it through the Add Peer dialog
    that has always worked. Nothing needs the HOA's own pairing dialog.

    The fixture has already opened the admin's vault, created its AID, put it on
    the air, and derived an EGF rooted at it — so by here the HOAs exist and
    already trust this admin.
    """
    devctl = admin_then_two_hoas["devctl"]
    admin = admin_then_two_hoas["admin"]["sock"]

    assert landing_target(devctl, admin) == "vaultNavMenu.identifiersButton", (
        "the admin must be VANILLA — its Identifiers/Credentials surfaces are "
        "what the issue and grant flows are driven through")

    cuo = _bring_up_hoa(devctl, admin_then_two_hoas["cuo"], "arccuo")
    actuary = _bring_up_hoa(devctl, admin_then_two_hoas["actuary"], "arcactuary")
    for name, sock in (("cuo", cuo), ("actuary", actuary)):
        assert landing_target(devctl, sock) != "vaultNavMenu.identifiersButton", (
            f"{name} must be a branded HOA (peeled nav)")

    for name, sock in (("cuo", cuo), ("actuary", actuary)):
        blob = _expose_and_export(devctl, sock, name)
        assert blob, f"{name} published no peer OOBI"
        import_peer_blob_via_ui(devctl, admin, blob, label=name)

    devctl(admin, "click", target="vaultNavMenu.settingsButton")
    rows = devctl(admin, "get_list_items", target="peerSettingsSection.peersList")
    items = rows.get("items") or rows.get("rows") or []
    assert len(items) >= 2, (
        f"admin should have paired with both HOAs; peers list shows {items}")


def test_the_admin_issues_and_grants_both_roles_live(admin_then_two_hoas):
    """Leg 3 — the whole membrane, with nothing hand-delivered.

    Each HOA ASKS for its role from its own onboarding home; the applications
    reach the admin's Notifications; the admin then loads each role schema into
    its own vault, issues the credential, and GRANTS it live over IPEX. Each HOA
    admits it from its own Notifications page, and its role gate — whose issuer
    is resolved from the EGF, not compiled in — opens the role's surface.

    Every prior role test short-circuits some part of this: `_build_test_admin`
    is an in-process party, `open_vault_holding_*_role` pushes the registry TEL
    down a raw socket the test opens itself, and `_bootstrap/sitecustomize.py`
    re-points the gate at that party. None of that is here. The only thing the
    pytest process does is click.
    """
    devctl = admin_then_two_hoas["devctl"]
    admin = admin_then_two_hoas["admin"]["sock"]
    egf = Path(admin_then_two_hoas["brand"]).parent / "egf"

    roles = (
        ("cuo", "arccuo", CUO_ROLE_SCHEMA_SAID,
         "Usurance Chief Underwriting Officer Role", "Underwriting"),
        ("actuary", "arcactuary", ACTUARY_ROLE_SCHEMA_SAID,
         "Usurance Actuary Role", "Actuarial"),
    )

    for name, vault, schema_said, schema_title, section in roles:
        sock = admin_then_two_hoas[name]["sock"]
        open_workspace_via_hoa_setup(devctl, sock, vault)
        set_peer_mode_via_ui(devctl, sock, port=free_port())
        import_peer_blob_via_ui(devctl, admin,
                                _expose_and_export(devctl, sock, name),
                                label=name)

    # Both peers must be REACHABLE before anything is sent. Pairing writes the
    # allowlist row synchronously; reachability is a probe cycle later, and
    # anything sent at a peer that has not answered yet fails as a transport
    # error attributed to whatever step was running.
    wait_for_peer_reachable(devctl, admin, count=len(roles))

    # Each HOA ASKS. This is the real trigger — the admin is responding to an
    # application, not pushing a role at a wallet that never applied. These
    # roles are apply-mode, so Request sends a bare IPEX apply with no form.
    for name, *_ in roles:
        request_role_via_hoa_ui(devctl, admin_then_two_hoas[name]["sock"], name)

    # …and the applications actually ARRIVE. The card going to "Requested" is
    # local state on the applicant; this is the receiving side. An apply is not
    # a credential grant, so it lands in Notifications, never under Received
    # Credentials.
    wait_for_admin_notifications(devctl, admin, count=len(roles))

    for name, _vault, schema_said, schema_title, section in roles:
        sock = admin_then_two_hoas[name]["sock"]

        loaded = load_issuable_schema_via_admin_ui(
            devctl, admin, egf / f"{schema_said}.json")
        assert loaded == schema_said, (
            f"the admin loaded {loaded}, not {name}'s role schema {schema_said}")

        issue_and_grant_role_via_admin_ui(
            devctl, admin, schema_prefix=schema_title, recipient_prefix=name)

        accepted = accept_grant_via_hoa_notifications(devctl, sock)
        assert accepted >= 1, (
            f"{name} admitted no grant. The credential left the admin — check "
            f"{admin_then_two_hoas[name]['log']} for 'exn' and 'admit'.")

        # The gate opens on GateRecheckDoer's tick, not synchronously.
        deadline = time.time() + 45.0
        while time.time() < deadline:
            if devctl(sock, "click", target=section).get("ok"):
                break
            time.sleep(1.5)
        else:
            raise AssertionError(
                f"{name} accepted the grant but the {section!r} section never "
                f"appeared. The gate resolves its issuer from the EGF — if the "
                f"brand's authority is not the wallet that granted this, it "
                f"never opens. Check the wallet log for 'gate' and 'egf.resolved'.")
