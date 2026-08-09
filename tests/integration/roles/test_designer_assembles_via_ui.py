# -*- encoding: utf-8 -*-
"""The designer receives a rate program and assembles a bundle, through real widgets.

Each row shows its issuer and the mandate it chains to, read from credential_edges —
the EDGE is the link, so no payload property restates it. That is also why this test
asserts the mandate column is populated: if the envelope's credential_edges never
reached the fold, the column is empty and the row is silently wrong (B22's shape).

Two devctl API corrections against the plan brief's illustrative snippet, confirmed
against the INSTALLED `locksmith_ui_tester.server` (not the README, which is stale —
same posture as `test_actuary_observes_and_attests_via_ui.py`'s own corrections):
`get_table_rows` returns `{"rows": [{header: cell_text, ...}, ...]}` — a list of
DICTS keyed by column header, not a list of plain cell values — so a cell-value check
must iterate `row.values()`, not `row` itself (iterating a dict yields its KEYS).
`click_table_row` reads `text=`, not `row_text=` (that kwarg belongs to
`click_row_action`, a different op) — and it matches a cell's FULL text exactly, so
the value passed must be the untruncated Attestation-column SAID, not `row[0]`
(meaningless on a dict — dict indexing by the int `0` raises `KeyError`).
"""
import time

import pytest


@pytest.mark.integration
def test_the_designer_assembles_a_bundle_from_a_received_program(two_wallets):
    devctl = two_wallets["devctl"]
    b = two_wallets["b"]

    from tests.integration.roles.conftest import deliver_rate_program_to_designer

    deliver_rate_program_to_designer(devctl, two_wallets)

    r = devctl(b["sock"], "wait_for", target="designerPage.receivedPrograms",
               condition="visible", timeout_ms=15000)
    assert r.get("ok"), r

    # The scan is a poll (ProductDesignerPage's own 1s-tock QTimer), same idiom
    # as the actuary's watch loop -- give it a few cycles rather than trusting
    # a single read the instant "visible" returns.
    deadline_scan = time.time() + 15.0
    rows = []
    while time.time() < deadline_scan:
        r = devctl(b["sock"], "get_table_rows", target="designerPage.receivedPrograms")
        assert r.get("ok"), r
        rows = r["rows"]
        if len(rows) == 1:
            break
        time.sleep(0.5)
    assert len(rows) == 1, f"receivedPrograms never settled to exactly one row: {rows}"
    row = rows[0]

    cells = list(row.values())
    assert any(str(c).startswith("E") for c in cells), \
        f"the issuer column must carry a real AID: {row}"
    mandate_cell = row.get("Mandate", "")
    assert mandate_cell and str(mandate_cell).startswith("E"), \
        f"the mandate edge must be shown, not blank: {row}"

    attestation_said = row["Attestation"]
    assert attestation_said.startswith("E"), row

    r = devctl(b["sock"], "click_table_row", target="designerPage.receivedPrograms",
               text=attestation_said)
    assert r.get("ok"), r
    r = devctl(b["sock"], "click", target="designerPage.assemble")
    assert r.get("ok"), r

    # The mint is behind a read-back now: `assemble` opens a confirmation naming
    # the mandate and every program in the set, because assembly acts on a
    # mandate GROUP and the row highlight never showed that. Non-modal on
    # purpose -- a modal `exec()` blocks the Qt main-thread stack devctl
    # dispatches on, which is the deadlock this package's conftest already
    # documents for the accept-grant dialogs.
    assert devctl(b["sock"], "wait_for", target="designerPage.confirmAssemble",
                  condition="enabled", timeout_ms=15000).get("ok"), (
        "the assembly read-back never opened")
    r = devctl(b["sock"], "click", target="designerPage.confirmAssemble")
    assert r.get("ok"), f"confirm the assembly read-back: {r}"
    r = devctl(b["sock"], "wait_for", target="designerPage.bundleSaid",
               condition="visible", timeout_ms=15000)
    assert r.get("ok"), r

    r = devctl(b["sock"], "get_text", target="designerPage.bundleSaid")
    assert r.get("ok") and r["text"].startswith("E"), r   # the SAID is the identity

    # publishing and completeness are out of scope since the parent design
    assert devctl(b["sock"], "is_visible",
                  target="designerPage.publish")["visible"] is False
