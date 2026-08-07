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
that works, and this file is what that unlocks.

Built leg by leg, each asserted before the next is added:

  1. the fleet comes up mixed (vanilla admin + two HOAs)          [asserted]
  2. the admin pairs OUTWARD with both HOAs                        [asserted]
  3. the admin issues + grants each role over the wire
  4. each HOA accepts from its own Notifications page
  5. the CUO declares a mandate
  6. the actuary's watch retrieves it by prodding

Legs 3-6 land as they are proven; nothing here asserts a step that has not
actually been driven.
"""
import pytest

from tests.integration.peer.conftest import (  # noqa: F401 (fixture)
    admin_and_two_hoas, create_aid_via_ui, free_port, import_peer_blob_via_ui,
    landing_target, open_test_vault_via_ui, set_peer_mode_via_ui,
)
from tests.integration.roles.conftest import _expose_and_export

pytestmark = pytest.mark.integration


def _bring_up(devctl, wallets, name, vault_name):
    """Open a vault and put the wallet on the air, whatever build it is."""
    sock = wallets[name]["sock"]
    open_test_vault_via_ui(devctl, sock, vault_name)
    # An HOA mints its own identifier on vault open; vanilla needs one made.
    create_aid_via_ui(devctl, sock, name)
    set_peer_mode_via_ui(devctl, sock, port=free_port())
    return sock


def test_the_admin_pairs_outward_with_both_hoas(admin_and_two_hoas):
    """Leg 2. The ADMIN does the pairing, which is what makes this tractable:
    a peeled HOA's own Add Peer dialog is awkward to drive, but nothing needs
    it — an HOA only has to PUBLISH its OOBI, which Settings now renders in a
    readable field, and the vanilla admin imports it through the dialog that
    has always worked.
    """
    devctl = admin_and_two_hoas["devctl"]

    admin = _bring_up(devctl, admin_and_two_hoas, "admin", "arcadmin")
    cuo = _bring_up(devctl, admin_and_two_hoas, "cuo", "arccuo")
    actuary = _bring_up(devctl, admin_and_two_hoas, "actuary", "arcactuary")

    assert landing_target(devctl, admin) == "vaultNavMenu.identifiersButton"
    for hoa in (cuo, actuary):
        assert landing_target(devctl, hoa) != "vaultNavMenu.identifiersButton"

    # Each HOA publishes its own OOBI; the admin imports both.
    for name, sock in (("cuo", cuo), ("actuary", actuary)):
        blob = _expose_and_export(devctl, sock, name)
        assert blob, f"{name} published no peer OOBI"
        import_peer_blob_via_ui(devctl, admin, blob, label=name)

    rows = devctl(admin, "get_list_items", target="peerSettingsSection.peersList")
    items = rows.get("items") or rows.get("rows") or []
    assert len(items) >= 2, (
        f"admin should have paired with both HOAs; peers list shows {items}")
