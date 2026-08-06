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

Two devctl API corrections against the plan brief's illustrative snippet, confirmed
against the INSTALLED `locksmith_ui_tester.server` (not the README, which is stale):
`get_list_items` returns `{"items": [{"text": ..., "data": ...}, ...]}`, not a bare
list of strings, so the clicked item's text is `items[0]["text"]`; `is_visible` on a
target that does not exist returns `{"ok": True, "visible": False, "exists": False}`,
never `{"ok": False}` — the field to assert is `"visible"`, not `"ok"`.
"""
import time

import pytest

from tests.integration.roles.conftest import (
    declare_mandate_via_ui, open_vault_holding_actuary_role,
    watch_cuo_mandate_via_peer,
)


@pytest.mark.integration
def test_the_actuary_sees_a_watched_mandate_and_can_attest(two_wallets, parse_dir):
    devctl = two_wallets["devctl"]
    a, b = two_wallets["a"], two_wallets["b"]

    declare_mandate_via_ui(devctl, a["sock"])
    open_vault_holding_actuary_role(devctl, b["sock"])
    watch_cuo_mandate_via_peer(devctl, two_wallets)

    # the mandate arrives by WATCHING, so the assertion is on the actuary's list
    # filling without B ever being handed anything.
    #
    # `wait_for`'s own `timeout_ms` is a SERVER-side poll budget; devctl's
    # client socket (tests/integration/peer/conftest.py::_devctl) has an
    # independent, hardcoded 5.0s recv() timeout. Asking the server to poll
    # longer than that races a real TimeoutError on the client side before
    # the server ever gets to answer -- so every wait_for below stays under
    # it, and anything that may genuinely take longer (the watch loop itself
    # is a 1s-tock poll) is retried from the test side instead, the same
    # idiom conftest.py's own "Underwriting"/"Actuarial" menu-entry waits use.
    r = devctl(b["sock"], "wait_for", target="actuaryPage.observedMandates",
               condition="visible", timeout_ms=3000)
    assert r.get("ok"), r

    # The list widget is visible as soon as the page is (it is part of the
    # persistent layout, not gated on having items) — the watch itself is a
    # poll (ActuaryPage's own QTimer, 1s tock), so give it a few cycles rather
    # than trusting a single read the instant "visible" returns.
    deadline = time.time() + 15.0
    items = []
    while time.time() < deadline:
        r = devctl(b["sock"], "get_list_items", target="actuaryPage.observedMandates")
        assert r.get("ok"), r
        items = r["items"]
        if len(items) == 1:
            break
        time.sleep(0.5)
    assert len(items) == 1, f"observedMandates never settled to exactly one item: {items}"

    r = devctl(b["sock"], "click_list_item", target="actuaryPage.observedMandates",
               text=items[0]["text"])
    assert r.get("ok"), r

    # a real ipd-parse output directory, not a synthetic stand-in
    r = devctl(b["sock"], "type", target="actuaryPage.parseDir", text=str(parse_dir))
    assert r.get("ok"), r
    r = devctl(b["sock"], "click", target="actuaryPage.loadParse")
    assert r.get("ok"), r

    # the manifest SAID and workbook digest are shown as EVIDENCE; no rate table
    r = devctl(b["sock"], "get_text", target="actuaryPage.manifestSaid")
    assert r.get("ok") and r["text"].startswith("E"), r
    r = devctl(b["sock"], "get_text", target="actuaryPage.workbookDigest")
    assert r.get("ok") and r["text"].startswith("E"), r
    assert devctl(b["sock"], "is_visible",
                  target="actuaryPage.rateTable")["visible"] is False, \
        "no rate table may be rendered in any HOA surface"

    r = devctl(b["sock"], "click", target="actuaryPage.attest")
    assert r.get("ok"), r

    # See the observedMandates comment above for why this polls in short
    # (client-timeout-safe) hops instead of one long wait_for.
    deadline = time.time() + 15.0
    banner_visible = False
    while time.time() < deadline:
        r = devctl(b["sock"], "wait_for", target="actuaryPage.attestedBanner",
                   condition="visible", timeout_ms=3000)
        if r.get("ok"):
            banner_visible = True
            break
    assert banner_visible, f"attestedBanner never became visible: {r}"
