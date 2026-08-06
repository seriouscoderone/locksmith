"""The CUO declares a mandate through the real form, driven over devctl.

Every step a person touches is a real widget interaction: navigate to the revealed
surface, type each field, submit. Selection is by objectName, which is why the page
must name its widgets (see the plan's Global Constraints)."""
import pytest

from tests.integration.roles.conftest import open_vault_holding_cuo_role


@pytest.mark.integration
def test_the_cuo_can_declare_a_mandate_through_the_form(two_wallets):
    devctl = two_wallets["devctl"]
    a = two_wallets["a"]

    open_vault_holding_cuo_role(devctl, a["sock"])       # see Step 4

    r = devctl(a["sock"], "wait_for", target="cuoMandatePage",
               condition="visible", timeout_ms=5000)
    assert r.get("ok"), r

    for target, value in [
        ("cuoMandatePage.lineOfBusiness", "Auto"),
        ("cuoMandatePage.jurisdiction", "UT"),
        ("cuoMandatePage.coverages", "BI,PD"),
        ("cuoMandatePage.effectiveWindow", "2027-01-01/2027-12-31"),
        ("cuoMandatePage.thesis", "Rate adequacy restoration."),
    ]:
        r = devctl(a["sock"], "type", target=target, text=value)
        assert r.get("ok"), (target, r)

    r = devctl(a["sock"], "is_checked", target="cuoMandatePage.submit")
    assert r.get("ok"), r

    r = devctl(a["sock"], "click", target="cuoMandatePage.submit")
    assert r.get("ok"), r

    r = devctl(a["sock"], "wait_for", target="cuoMandatePage.declaredBanner",
               condition="visible", timeout_ms=10000)
    assert r.get("ok"), r
