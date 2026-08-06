# -*- encoding: utf-8 -*-
"""Done-when #5, at the surface: the nav entry and page must actually disappear.

The in-process e2e (test_multi_role_e2e.py::
test_revoking_the_cuo_credential_removes_exactly_the_cuo_surface) asserts the
manager's bookkeeping (`_active_roles`, a `DestroyingSurfaceHost`'s `.pages`
dict); it does not, and cannot, prove a HUMAN sees the nav entry/page leave
the screen -- that host is a test double, not a rendered window. This test
drives the REAL UI in a real wallet subprocess and waits out
`GateRecheckDoer`'s 2-second tock rather than restarting the app -- "without
a restart" is the claim, and a restart would re-run `on_vault_opened`'s own
gate evaluation, silently hiding a bug where only THAT initial-open path
(not the live poll) reacts to a revocation.

Also grants a SIBLING gated role (`actuary_role`) to the SAME identity before
revoking `cuo_role`, so "removes exactly the revoked surface" is provable at
the UI layer too -- not merely "some page vanished after a revoke," but "the
OTHER active role's page, on the SAME vault, did not."
"""
import pytest

from tests.integration.roles.conftest import (
    grant_actuary_role_to_cuo_wallet,
    open_vault_holding_cuo_role,
    revoke_cuo_role_and_deliver,
)


@pytest.mark.integration
def test_revoking_cuo_removes_its_surface_without_a_restart(two_wallets):
    devctl = two_wallets["devctl"]
    b = two_wallets["b"]

    admin_state: dict = {}
    open_vault_holding_cuo_role(devctl, b["sock"], admin_state=admin_state)
    r = devctl(b["sock"], "wait_for", target="cuoMandatePage",
               condition="visible", timeout_ms=10000)
    assert r.get("ok"), r

    # A sibling gated role on the SAME identity/vault -- so the revoke below
    # proves SELECTIVITY at the real UI layer, not merely "a page vanished."
    grant_actuary_role_to_cuo_wallet(devctl, b["sock"], admin_state)
    r = devctl(b["sock"], "wait_for", target="actuaryPage",
               condition="visible", timeout_ms=10000)
    assert r.get("ok"), r

    revoke_cuo_role_and_deliver(admin_state)      # issuer-side + delivery

    # GateRecheckDoer's default tock is 2.0s; allow a few cycles, no restart.
    r = devctl(b["sock"], "wait_for", target="cuoMandatePage",
               condition="hidden", timeout_ms=15000)
    assert r.get("ok"), r

    # ...and the sibling surface, on the SAME identity, is untouched.
    r = devctl(b["sock"], "is_visible", target="actuaryPage")
    assert r.get("ok") and r.get("visible"), r
