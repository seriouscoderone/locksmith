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
import pytest

from tests.integration.peer.conftest import (  # noqa: F401 (fixture)
    admin_then_two_hoas, create_aid_via_ui, free_port, import_peer_blob_via_ui,
    landing_target, open_test_vault_via_ui, set_peer_mode_via_ui,
)
from tests.integration.roles.conftest import _expose_and_export

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
