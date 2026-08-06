"""The CUO declares a mandate through the real form, driven over devctl.

Every step a person touches is a real widget interaction: navigate to the revealed
surface, type each field, submit. Selection is by objectName, which is why the page
must name its widgets (see the plan's Global Constraints).

The form-filling body itself now lives in `declare_mandate_via_ui`
(tests/integration/roles/conftest.py) — extracted by Task 5 so the actuary slice can
reuse this exact same opening leg rather than re-deriving it. This test is what proves
that helper still does what it says."""
import pytest

from tests.integration.roles.conftest import declare_mandate_via_ui


@pytest.mark.integration
def test_the_cuo_can_declare_a_mandate_through_the_form(two_wallets):
    devctl = two_wallets["devctl"]
    a = two_wallets["a"]

    declare_mandate_via_ui(devctl, a["sock"])
