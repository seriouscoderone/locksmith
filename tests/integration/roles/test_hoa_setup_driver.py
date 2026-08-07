# -*- encoding: utf-8 -*-
"""A branded HOA opens its workspace through its OWN first-run path.

`open_test_vault_via_ui` drives the vault drawer, which an onboarding brand does
not show on first run: it logs `hoa.first_run reason=no_workspace path=setup`
and mounts SetupPage instead (ui/window.py:401-403). Driving the wrong surface
left the HOA sitting on setup with no vault at all — indistinguishable, from
outside, from a broken ecosystem.
"""
import pytest

from tests.integration.peer.conftest import (  # noqa: F401 (fixture)
    admin_then_two_hoas, landing_target, open_vault_any_build,
)

pytestmark = pytest.mark.integration


def test_a_branded_hoa_opens_through_its_own_setup_page(admin_then_two_hoas):
    w = admin_then_two_hoas
    devctl, cuo = w["devctl"], w["cuo"]

    path = open_vault_any_build(devctl, cuo["sock"], "arccuo")

    assert path == "hoa-setup", (
        f"a branded HOA's first run must go through SetupPage, not the vault "
        f"drawer; the driver took the {path!r} path")
    assert landing_target(devctl, cuo["sock"]) != "vaultNavMenu.identifiersButton", (
        "expected a peeled HOA nav once the workspace exists")


def test_the_same_driver_still_opens_a_vanilla_wallet(admin_then_two_hoas):
    """The point of `open_vault_any_build` is that ONE call serves both builds,
    decided by what is on screen rather than by an env var — so the admin, which
    has no setup page, still goes through the drawer."""
    w = admin_then_two_hoas
    # The fixture already opened the admin's vault through the drawer; a second
    # wallet proves the branch, so assert on the surface it actually landed on.
    assert landing_target(w["devctl"], w["admin"]["sock"]) == \
        "vaultNavMenu.identifiersButton"
