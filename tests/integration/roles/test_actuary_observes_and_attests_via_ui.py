"""Wallet A's CUO declares; wallet B's actuary SEES it by watching, then attests.

The observation leg is the thesis: B is never sent the mandate — it watches A's KEL,
retrieves the body, and confirms it re-derives to the sealed SAID (C1's chain). The UI
test's job is to prove that reaches a human surface.

`PARSE_DIR` (the `parse_dir` fixture, `tests/integration/roles/conftest.py`) is a REAL
`ipd-parse` output tree: `~/code/ugard/insurance-product/parser`'s own venv runs
`python -m ipd.parse_cli` against the real fixture workbook
(`tests/fixtures/TestExcel_01.xlsm`), exactly the invocation
`ugard/tests/corpus/test_actuarial_trio.py` records. It is genuinely NOT a synthetic
stand-in — the manifest SAID this test asserts commits to the parsed shards' actual
bytes AND the source workbook's own bytes (`ipd.manifest.build_manifest`, reimplemented
byte-for-byte in `actuary/page.py` rather than imported across repos — see that
module's docstring). The one thing this fixture adds beyond what `ipd-parse` itself
writes is a `.workbook_source.json` sidecar naming the workbook's path: `ipd-parse`
does not record the source workbook's location in its own output (measured — no field
in `index.json` names it), so every real invocation has always supplied it out-of-band
alongside `--out`, and `ActuaryPage._resolve_workbook`'s documented convention is this
sidecar. The sidecar carries a real path, not a fabricated digest, and it is excluded
by name from the manifest's own shard walk.

The load-and-attest closing leg now lives in `attest_rate_program_via_ui`
(`tests/integration/roles/conftest.py`) — extracted by Task 8 so the four-app arc
(`test_four_app_arc_via_ui.py`) can drive this exact same leg rather than re-deriving
it. This test is what proves that helper still does what it says (see that helper's
own docstring for the two devctl API corrections against the plan brief's illustrative
snippet).
"""
import pytest

from tests.integration.roles.conftest import (
    attest_rate_program_via_ui, declare_mandate_via_ui,
    open_vault_holding_actuary_role, watch_cuo_mandate_via_peer,
)


@pytest.mark.integration
def test_the_actuary_sees_a_watched_mandate_and_can_attest(two_wallets, parse_dir):
    devctl = two_wallets["devctl"]
    a, b = two_wallets["a"], two_wallets["b"]

    declare_mandate_via_ui(devctl, a["sock"])
    open_vault_holding_actuary_role(devctl, b["sock"])
    watch_cuo_mandate_via_peer(devctl, two_wallets)

    # the mandate arrives by WATCHING, so the assertion is on the actuary's list
    # filling without B ever being handed anything — attest_rate_program_via_ui's
    # own preconditions match exactly what the three calls above just set up.
    attest_rate_program_via_ui(devctl, b["sock"], parse_dir)
