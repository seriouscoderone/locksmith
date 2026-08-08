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
import time
from pathlib import Path

import pytest

from tests.integration.peer.conftest import (  # noqa: F401 (fixture)
    accept_grant_via_hoa_notifications, admin_then_two_hoas, create_aid_via_ui,
    free_port, import_peer_blob_via_ui, landing_target, open_test_vault_via_ui,
    open_workspace_via_hoa_setup, set_peer_mode_via_ui, wait_for_peer_reachable,
)
from tests.integration.roles.conftest import (
    ACTUARY_ROLE_SCHEMA_SAID, CUO_ROLE_SCHEMA_SAID, PD_ROLE_SCHEMA_SAID,
    _export_current_blob,
    _expose_and_export, issue_and_grant_role_via_admin_ui,
    load_issuable_schema_via_admin_ui, request_role_via_hoa_ui,
    submit_mandate_form_via_ui, wait_for_admin_notifications,
    _run_ipd_parse, attest_rate_program_via_ui,
)

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


@pytest.mark.parametrize("admin_then_two_hoas",
                         [["cuo", "actuary", "product_designer"]], indirect=True)
def test_the_admin_issues_and_grants_both_roles_live(admin_then_two_hoas, tmp_path):
    """Leg 3 — the whole membrane, with nothing hand-delivered.

    Each HOA ASKS for its role from its own onboarding home; the applications
    reach the admin's Notifications; the admin then loads each role schema into
    its own vault, issues the credential, and GRANTS it live over IPEX. Each HOA
    admits it from its own Notifications page, and its role gate — whose issuer
    is resolved from the EGF, not compiled in — opens the role's surface.

    Every prior role test short-circuits some part of this: `_build_test_admin`
    is an in-process party, `open_vault_holding_*_role` pushes the registry TEL
    down a raw socket the test opens itself, and `_bootstrap/sitecustomize.py`
    re-points the gate at that party. None of that is here. The only thing the
    pytest process does is click.
    """
    devctl = admin_then_two_hoas["devctl"]
    admin = admin_then_two_hoas["admin"]["sock"]
    egf = Path(admin_then_two_hoas["brand"]).parent / "egf"

    roles = (
        ("cuo", "arccuo", CUO_ROLE_SCHEMA_SAID,
         "Usurance Chief Underwriting Officer Role", "Underwriting"),
        ("actuary", "arcactuary", ACTUARY_ROLE_SCHEMA_SAID,
         "Usurance Actuary Role", "Actuarial"),
        # Named for the EGF ROLE ID, not the persona's nickname. The first
        # element is used three ways — wallet key, pairing label, and the role
        # requested via `roleCard.requestButton.<role_id>` — so "designer" fails
        # at the third: the EGF calls this role `product_designer`.
        ("product_designer", "arcdesigner", PD_ROLE_SCHEMA_SAID,
         "Usurance Insurance Product Designer Role", "Insurance Product Design"),
    )

    for name, vault, schema_said, schema_title, section in roles:
        sock = admin_then_two_hoas[name]["sock"]
        open_workspace_via_hoa_setup(devctl, sock, vault)
        set_peer_mode_via_ui(devctl, sock, port=free_port())
        import_peer_blob_via_ui(devctl, admin,
                                _expose_and_export(devctl, sock, name),
                                label=name)

    # Both peers must be REACHABLE before anything is sent. Pairing writes the
    # allowlist row synchronously; reachability is a probe cycle later, and
    # anything sent at a peer that has not answered yet fails as a transport
    # error attributed to whatever step was running.
    wait_for_peer_reachable(devctl, admin, count=len(roles))

    # Each HOA ASKS. This is the real trigger — the admin is responding to an
    # application, not pushing a role at a wallet that never applied. These
    # roles are apply-mode, so Request sends a bare IPEX apply with no form.
    for name, *_ in roles:
        request_role_via_hoa_ui(devctl, admin_then_two_hoas[name]["sock"], name)

    # …and the applications actually ARRIVE. The card going to "Requested" is
    # local state on the applicant; this is the receiving side. An apply is not
    # a credential grant, so it lands in Notifications, never under Received
    # Credentials.
    wait_for_admin_notifications(devctl, admin, count=len(roles))

    for name, _vault, schema_said, schema_title, section in roles:
        sock = admin_then_two_hoas[name]["sock"]

        loaded = load_issuable_schema_via_admin_ui(
            devctl, admin, egf / f"{schema_said}.json")
        assert loaded == schema_said, (
            f"the admin loaded {loaded}, not {name}'s role schema {schema_said}")

        issue_and_grant_role_via_admin_ui(
            devctl, admin, schema_prefix=schema_title, recipient_prefix=name)

        # This HOA APPLIED, so it admits the matching grant on its own the
        # moment it arrives — measured as `admit-back delivery failed
        # (non-fatal)` then a "Credential accepted" toast, with no row ever
        # rendered to click. Demanding a manual accept asserted the absence of
        # a feature.
        #
        # Kept as a SHORT probe rather than dropped, so a build that does
        # surface a row still gets it clicked. The budget is 5s, not the 45s
        # default: waiting the full window for a row that by design never comes
        # cost ~90s a run, which is visible as a dead pause between roles. The
        # gate opening below is the real proof the credential landed, and it
        # polls on its own.
        accept_grant_via_hoa_notifications(devctl, sock, require=False,
                                           timeout_s=5.0)

        # The gate opens on GateRecheckDoer's tick, not synchronously.
        deadline = time.time() + 45.0
        while time.time() < deadline:
            if devctl(sock, "click", target=section).get("ok"):
                break
            time.sleep(1.5)
        else:
            raise AssertionError(
                f"{name} accepted the grant but the {section!r} section never "
                f"appeared. The gate resolves its issuer from the EGF — if the "
                f"brand's authority is not the wallet that granted this, it "
                f"never opens. Check the wallet log for 'gate' and 'egf.resolved'.")

    # ---- the membrane: the CUO declares, the actuary RETRIEVES -------------
    cuo, actuary = (admin_then_two_hoas["cuo"]["sock"],
                    admin_then_two_hoas["actuary"]["sock"])

    # ONE-WAY on purpose. The actuary learns how to reach the CUO; the CUO is
    # never told how to reach the actuary and is never asked to send anything.
    # That is the whole claim — the actuary does the asking. It works because
    # the `bar` returns on the SAME socket the `pro` arrived on, and because the
    # peer allowlist gates `exn` only, never `pro` (the prod carries the asker's
    # KEL as an introduction, so it is not dropped as "Unknown sender").
    #
    # Consequence worth expecting: the CUO's peer list stays empty and its dot
    # never goes green. Correct, not a missing pairing.
    import_peer_blob_via_ui(devctl, actuary,
                            _export_current_blob(devctl, cuo, "cuo"),
                            label="cuo")
    wait_for_peer_reachable(devctl, actuary, count=1)

    devctl(cuo, "click", target="Underwriting")
    submit_mandate_form_via_ui(devctl, cuo)

    # Nothing is pushed. The actuary's own `PeerSyncDoer` syncs the CUO's KEL,
    # finds the mandate's anchoring seal, sends a `pro`, and ingests the `bar`.
    # It ticks every 5s, so this is polled, not slept through.
    devctl(actuary, "click", target="Actuarial")
    deadline, rows = time.time() + 120.0, None
    while time.time() < deadline:
        rows = (devctl(actuary, "get_list_items",
                       target="actuaryPage.observedMandates").get("items")) or []
        if rows:
            break
        time.sleep(3.0)

    assert rows, (
        "the actuary never retrieved the mandate. NOTHING pushed it, so an "
        "empty list means the ask, the answer, or the storing of the body "
        "failed — and all three look identical from here. The wallet logs "
        "separate them: the actuary should log "
        "'peer_sync.sent … what=pro/sealed', and the CUO should log "
        "'Prod: disclosing'. Whichever is missing names the half that broke.\n"
        f"  actuary: {admin_then_two_hoas['actuary']['log']}\n"
        f"  cuo:     {admin_then_two_hoas['cuo']['log']}")

    # ---- the actuary ATTESTS, against the mandate it actually observed -----
    #
    # The SAID comes off the list row's UserRole data, not its label: the label
    # is elided to 12 chars for reading, and `ipd-parse` needs the whole thing
    # (`--product-mandate <SAID>`, writing to `<out>/<lob>/<juris>/<said>`).
    # A parse answers ONE mandate, so parsing against a placeholder would attest
    # to a program that answers nothing this CUO declared.
    mandate_said = (rows[0].get("data") or "").strip()
    assert mandate_said.startswith("E"), (
        f"the observed row carries no mandate SAID in its UserRole data: "
        f"{rows[0]}")

    parse_dir = _run_ipd_parse(tmp_path / "parse", product_mandate=mandate_said)
    attest_rate_program_via_ui(devctl, actuary, parse_dir)

    # ---- the designer receives the program and ASSEMBLES -------------------
    #
    # Paired at BOTH the actuary and the CUO, and one-way at each. The actuary
    # is where the attestation is anchored; the CUO is where the mandate it
    # chains to is anchored, and `Verifier.verifyChain` needs that node in this
    # wallet's own `reger.saved` before an edge may point at it. A designer
    # watching only the actuary would retrieve the program and be unable to
    # verify it.
    designer = admin_then_two_hoas["product_designer"]["sock"]
    for label, sock in (("actuary", actuary), ("cuo", cuo)):
        import_peer_blob_via_ui(devctl, designer,
                                _export_current_blob(devctl, sock, label),
                                label=label)
    wait_for_peer_reachable(devctl, designer, count=2)

    devctl(designer, "click", target="Insurance Product Design")
    deadline, programs = time.time() + 150.0, None
    while time.time() < deadline:
        r = devctl(designer, "get_table_rows",
                   target="designerPage.receivedPrograms")
        programs = r.get("rows") or []
        if programs:
            break
        time.sleep(3.0)

    assert programs, (
        "the designer never received the rate program. Nothing pushed it — the "
        "designer's own watch has to find the attestation anchored in the "
        "ACTUARY's KEL, retrieve the body, fetch its TEL, and then chain it to "
        "the mandate anchored in the CUO's. The page reads `reger.schms` and "
        "requires `reger.saved`, so a body held but not indexed is invisible "
        "here.\n"
        f"  designer: {admin_then_two_hoas['product_designer']['log']}\n"
        f"  actuary:  {admin_then_two_hoas['actuary']['log']}")

    # `click_table_row` matches a row by any CELL'S TEXT, not by index — there
    # is no `row=` selector. Passing one selected nothing, which left
    # `designerPage.assemble` disabled (it starts that way and is enabled by
    # `_on_row_clicked`), and devctl reported the resulting click on a DISABLED
    # button as `ok` — so the whole leg looked driven and did nothing.
    cell = next((str(v) for v in programs[0].values() if str(v).strip()), "")
    assert cell, f"the received-programs row has no text to select by: {programs[0]}"
    r = devctl(designer, "click_table_row",
               target="designerPage.receivedPrograms", text=cell)
    assert r.get("ok"), f"select the received program row ({cell!r}): {r}"

    # RETRY the assemble, do not click once and wait.
    #
    # A program row appears as soon as the ATTESTATION is retrieved and indexed.
    # The bundle, though, chains to the MANDATE, and `Verifier.verifyChain`
    # needs that node in this wallet's own `reger.saved` WITH a current TEL
    # state — two more asynchronous arrivals from a DIFFERENT peer. So Assemble
    # becomes clickable strictly before it can succeed.
    #
    # Measured, one run of each outcome: the mandate's TEL landed in time and
    # the bundle minted; the next run it had not, and the issuance died with
    # `Failure to verify credential ... chain mandate(...)` /
    # `TEL event ... did not complete`. Nothing is minted on that path, so
    # re-clicking cannot double-issue.
    #
    # (The enabled-state assertion stays inside the loop: devctl reports a click
    # on a DISABLED button as ok, so without it a failed row selection reads as
    # a successful click.)
    deadline, said = time.time() + 120.0, ""
    while time.time() < deadline:
        r = devctl(designer, "click", target="designerPage.assemble")
        assert r.get("ok"), f"click Assemble: {r}"
        assert (r.get("clicked") or {}).get("enabled"), (
            f"Assemble was DISABLED when clicked, so nothing ran — the row "
            f"selection did not take: {r}")
        if devctl(designer, "wait_for", target="designerPage.bundleSaid",
                  condition="visible", timeout_ms=4000).get("ok"):
            said = (devctl(designer, "get_text",
                           target="designerPage.bundleSaid").get("text") or "")
            if "E" in said:
                break
        time.sleep(4.0)

    assert "E" in said, (
        "Assemble never produced a bundle SAID. The program row was there, so "
        "the attestation arrived — the bundle additionally chains to the "
        "MANDATE, which must be in this wallet's own reger.saved with a current "
        "TEL state. Check the designer log for 'chain mandate(' and "
        f"'did not complete'.\n"
        f"  designer: {admin_then_two_hoas['product_designer']['log']}")
