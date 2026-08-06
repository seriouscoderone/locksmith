# -*- encoding: utf-8 -*-
"""The whole membrane, driven end to end across three running applications.

The CUO declares; the actuary SEES it by watching (never sent) and attests from a
real `ipd-parse` run; the designer assembles. This is the parent design's done-when
#3, and until now it existed only as a runbook
(`docs/demos/2026-08-actuarial-four-app-runbook.md`).

**Why this is `four_wallets` (three real processes) and not four spawned
processes, stated precisely rather than left to be discovered:**

`admin` is not one of `four_wallets`'s spawned processes. A real fourth Locksmith
process genuinely CAN issue and Grant a role credential through its own real UI —
`IssueCredentialDialog`/`GrantCredentialDialog` already carry stable devctl
objectNames (`issueCredentialDialog.issueButton`, `grantCredentialDialog.
recipientCombo`, `grantCredentialDialog.grantButton`, ...), pre-dating this plan, so
that half is genuinely drivable. What is NOT drivable is the RECEIVING side: a live
IPEX grant surfaces on the recipient's Notifications page, and
`notifications/list.py::_show_accept_grant_dialog` admits it through THREE separate
`QDialog.exec()` calls — a MODAL call that blocks the very Qt-main-thread stack the
devctl server dispatches every command on. `open_vault_holding_cuo_role`'s own module
docstring (this package's `conftest.py`, point 2) already measured this exact
deadlock for a different dialog pair (`AcceptGrantDialog` reached from Notifications,
vs. the SAME dialog reached from Received Credentials) and chose the file-based
Accept flow specifically to avoid it — "both the row-action call and a
background-thread rescue attempt timed out with the socket server accepting nothing
further." A real admin process granting LIVE over IPEX drives the recipient into the
identical wall, and there is no file-based escape hatch for a grant that just arrived
over a socket (the file-based flow admits a `.cesr` the caller already has on disk —
`Granter.grant()`'s own `_save_grant` path does not call `credentialing.
sendArtifacts`, so a SAVED grant also lacks the registry TEL a fresh recipient needs,
unlike a live SEND, which does call it).

So: admin's three role grants (`cuo_role`, `actuary_role`, `product_designer_role`)
are driven through the SAME in-process issuance recipe `open_vault_holding_cuo_role` /
`open_vault_holding_actuary_role` / `deliver_rate_program_to_designer` already use and
Tasks 4/5/6 already proved — real registries, real TELs, real schema validation, real
admit UI on the RECEIVING side (the file-based Accept flow) — just not a FOURTH
spawned GUI process on the issuing side. The manual runbook (`docs/demos/
2026-08-actuarial-four-app-runbook.md`) drives that same leg through a real admin
window instead, because a human clicking through a modal dialog is not blocked by
this deadlock — only a synchronous single-threaded automation client is.

**The designer's rate program is a SEPARATE credential, not a live relay of the
mandate this test's own CUO leg declares or the attestation its own actuary leg
mints.** `deliver_rate_program_to_designer` mints a structurally-equivalent mandate +
edge-linked attestation through the same in-process admin recipe (Task 6's own
established choice — see that helper's docstring: "Re-driving [the CUO/actuary UI
flows] a second time here would prove nothing new about the DESIGNER surface Task 6
actually owns"). Relaying the SAME mandate/attestation from a live actuary process to
a live designer process would need new infrastructure this plan does not build (the
actuary's own `attest()` mints locally with `recipient=None`, per `actuary/page.py`
— an untargeted credential; the real production path for reaching another wallet is
the SAME Issue→Grant→Notifications-Admit mechanic that is undrivable above). This
test therefore proves each of the three real UI surfaces genuinely does its own job
(declare / watch-and-attest / receive-and-assemble) against a real, schema-valid,
chain-verified credential — not that one single mandate's SAID is traceable end to
end across all three windows. See the runbook for the fully-relayed version, driven
by hand.

A screenshot per real app is the milestone's evidence, written to
`/tmp/four-app-{cuo,actuary,designer}.png` — three, not four; there is no fourth GUI
window in this automated arc for the reason above.
"""
import time

import pytest

from tests.integration.roles.conftest import (
    attest_rate_program_via_ui, declare_mandate_via_ui,
    deliver_rate_program_to_designer, open_vault_holding_actuary_role,
    watch_cuo_mandate_via_peer,
)


@pytest.mark.integration
def test_the_four_applications_complete_the_arc(four_wallets, parse_dir):
    devctl = four_wallets["devctl"]
    cuo, actuary, designer = (four_wallets[k] for k in ("cuo", "actuary", "designer"))

    # Leg 1 — admin grants cuo_role (in-process recipe, see module docstring) and
    # the CUO declares a real mandate through the real form. No send happens here
    # by design: a mandate is watched, never handed over.
    declare_mandate_via_ui(devctl, cuo["sock"])
    r = devctl(cuo["sock"], "screenshot", path="/tmp/four-app-cuo.png")
    assert r.get("ok"), r

    # Leg 2 — admin grants actuary_role (in-process recipe) and the actuary WATCHES
    # (never sent) the CUO's KEL for the mandate, then attests from a real
    # ipd-parse run.
    open_vault_holding_actuary_role(devctl, actuary["sock"])
    watch_cuo_mandate_via_peer(devctl, {"a": cuo, "b": actuary})
    attest_rate_program_via_ui(devctl, actuary["sock"], parse_dir)
    r = devctl(actuary["sock"], "screenshot", path="/tmp/four-app-actuary.png")
    assert r.get("ok"), r

    # Leg 3 — admin grants product_designer_role and delivers a
    # structurally-equivalent rate program (see module docstring for why this is a
    # SEPARATE credential, not a live relay of leg 1/2's own mandate/attestation);
    # the designer assembles a bundle from it through the real UI.
    deliver_rate_program_to_designer(devctl, {"b": designer})

    r = devctl(designer["sock"], "wait_for", target="designerPage.receivedPrograms",
               condition="visible", timeout_ms=15000)
    assert r.get("ok"), r

    # The scan is a poll (ProductDesignerPage's own 1s-tock QTimer) — give it a
    # few cycles rather than trusting a single read the instant "visible" returns.
    deadline = time.time() + 15.0
    rows = []
    while time.time() < deadline:
        r = devctl(designer["sock"], "get_table_rows", target="designerPage.receivedPrograms")
        assert r.get("ok"), r
        rows = r["rows"]
        if len(rows) == 1:
            break
        time.sleep(0.5)
    assert len(rows) == 1, f"receivedPrograms never settled to exactly one row: {rows}"
    row = rows[0]

    mandate_cell = row.get("Mandate", "")
    assert mandate_cell and str(mandate_cell).startswith("E"), \
        f"the mandate edge must be shown, not blank: {row}"

    attestation_said = row["Attestation"]
    assert attestation_said.startswith("E"), row

    r = devctl(designer["sock"], "click_table_row", target="designerPage.receivedPrograms",
               text=attestation_said)
    assert r.get("ok"), r
    r = devctl(designer["sock"], "click", target="designerPage.assemble")
    assert r.get("ok"), r
    r = devctl(designer["sock"], "wait_for", target="designerPage.bundleSaid",
               condition="visible", timeout_ms=15000)
    assert r.get("ok"), r

    said = devctl(designer["sock"], "get_text", target="designerPage.bundleSaid")
    assert said.get("ok") and said["text"].startswith("E"), said   # the SAID is the identity

    r = devctl(designer["sock"], "screenshot", path="/tmp/four-app-designer.png")
    assert r.get("ok"), r
