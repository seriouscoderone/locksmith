# -*- encoding: utf-8 -*-
"""Fixtures for the role-surface UI tests.

Reuses tests/integration/peer/conftest's wallet-spawning machinery verbatim: isolated
HOME per wallet, one devctl socket each, offscreen Qt, and the PYTHONPATH prepend that
stops the shared venv's editable .pth from silently testing the main checkout instead
of the tree under test.
"""
from __future__ import annotations

import json
import os
import pathlib
import socket
import subprocess
import tempfile
import time

import pytest

from tests.integration.peer.conftest import (           # noqa: F401
    _devctl as devctl, free_port, open_test_vault_via_ui, create_aid_via_ui, two_wallets,
)

_UI_TESTER = pathlib.Path.home() / ".locksmith" / "plugins" / "ui_tester"
_MISSING = (
    "locksmith-ui-tester is not installed at ~/.locksmith/plugins/ui_tester. "
    "The peer conftest skips on this, so an entire UI suite can report 'skipped' "
    "and read as green. Install it from ~/code/locksmith-ui-tester before treating "
    "this suite's result as evidence.")


@pytest.fixture(scope="session", autouse=True)
def _require_ui_tester():
    """Skip locally, FAIL in CI. A suite that ran nothing must never be reportable as
    a suite that passed — and CI is exactly where nobody reads the skip summary."""
    if _UI_TESTER.exists():
        return
    if os.environ.get("CI"):
        pytest.fail(_MISSING, pytrace=False)
    pytest.skip(_MISSING, allow_module_level=True)


# ---------------------------------------------------------------------------
# open_vault_holding_cuo_role — the one helper the peer conftest does not
# provide. A synthetic, in-process "test admin" KERI party (never the real
# usurance-admin — that AID belongs to a real, passcode-protected operator
# vault this suite must never touch, exactly the posture
# tests/integration/test_multi_role_e2e.py already documents and takes for
# its own in-process admin) genuinely issues a `cuo_role` ACDC through the
# same registry/TEL machinery `keri_serviceaid.providers.issue_credential`
# uses in production, then delivers it to the wallet over the SAME real peer
# TCP path tests/integration/peer/test_send.py proves, so the credential is
# admitted through the wallet's own real Kevery/Tevery/Verifier — no
# monkeypatched gate state, no faked `_held_credentials`.
#
# Delivery is deliberately split into TWO legs, each chosen after measuring
# why the obvious single-mechanism version fails:
#
# 1. **Registry TEL over the real peer wire, delivered separately from the
#    grant.** `keri_serviceaid.providers.frame_grant_for`'s embeds are
#    `acdc`/`iss`/`anc` only (`ipexGrantExn`'s shape) — the registry's OWN
#    `vcp` inception event is not among them. Locksmith's real send path
#    (`ServiceaidGrantDoer`, `serviceaid_bridge.py`) additionally calls
#    `credentialing.sendArtifacts`, which separately streams the issuer's
#    full KEL AND the registry's full TEL (`reger.clonePreIter(pre=regk)`)
#    over the same connection. Skipping that (measured) parks the credential
#    in a registry-missing escrow forever — `ipexing.AdmitDoer`'s own
#    internal `_wait_for(reger.saved...)` times out at 10s and emits
#    `admit_failed`, error "Timeout processing credential". So this helper
#    sends the registry's TEL (+ the credential's own TEL, harmless to
#    resend) as its own message(s) over `cuo_port` FIRST, giving the
#    wallet's real `Reactant`/Tevery time to land it before the grant ever
#    arrives.
#
# 2. **The grant itself travels through the file-based "Accept Credential
#    Issuance" flow, not the Notifications page.** Measured: the
#    Notifications page's Admit action opens `AcceptGrantDialog` via
#    `QDialog.exec()` (`_show_accept_grant_dialog`, `notifications/list.py`),
#    which blocks the SAME call stack `_op_click_row_action` runs in — the
#    devctl server has no other thread to accept a second connection while
#    that handler is still on the stack, so a synchronous test driver
#    blocked waiting for THAT response can never send the command that would
#    close the dialog: a real deadlock (confirmed: both the row-action call
#    and a background-thread rescue attempt timed out with the socket
#    server accepting nothing further). `AcceptCredentialDialog` ->
#    `AcceptGrantDialog`, reached from Received Credentials, opens both via
#    `.open()` (non-blocking) instead — that dialog only ever parses ONE
#    message (`Admitter.parse` calls `parseOne`), which is exactly why the
#    registry's TEL has to travel over the wire in leg 1 rather than being
#    bundled into this file.
#
#    That file-based path has its OWN hazard, neutralized in
#    `_bootstrap/sitecustomize.py` rather than here: a successful admit
#    (`save=True`, the file-based flow's only mode) fires
#    `AcceptGrantDialog._save_admit_to_file`, which opens the NATIVE
#    `QFileDialog.getSaveFileName(...)`. Under `QT_QPA_PLATFORM=offscreen`
#    that call has nothing to show and nothing that can dismiss it, and
#    because it runs SYNCHRONOUSLY inside the same `admit_complete` signal
#    emission that (via the earlier-connected `PluginManager` listener)
#    ALSO drives the credential gate's reveal, it freezes the vault's own
#    Doist mid-tick: the gate reveal itself still completes (it runs
#    first), but no doer scheduled afterward — including
#    `CuoMandatePage.submit()`'s own `vault.extend([...])` — ever gets
#    ticked again. See sitecustomize.py's patch 3.
# ---------------------------------------------------------------------------

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_CUO_ROLE_SCHEMA_PATH = (
    REPO_ROOT / "brands" / "usurance" / "egf"
    / "EIE7Wb01SJeYU4HNbzP2En2XyGZSkRtIElXX7MOLlSTH.json"
)
CUO_ROLE_SCHEMA_SAID = "EIE7Wb01SJeYU4HNbzP2En2XyGZSkRtIElXX7MOLlSTH"

# Task 5's sibling pin: same shape as CUO_ROLE_SCHEMA_SAID above, for the
# actuary's OWN gate credential. Verified against the bundled schema by
# tests/plugins/roles/test_pin_regression.py, same as the CUO one.
_ACTUARY_ROLE_SCHEMA_PATH = (
    REPO_ROOT / "brands" / "usurance" / "egf"
    / "EIGJb6GFT8bLi2nDuS4ekp6gSr8JqIcpPE9AKjiCClLY.json"
)
ACTUARY_ROLE_SCHEMA_SAID = "EIGJb6GFT8bLi2nDuS4ekp6gSr8JqIcpPE9AKjiCClLY"

# Task 6's sibling pin: the designer's own gate credential.
_PD_ROLE_SCHEMA_PATH = (
    REPO_ROOT / "brands" / "usurance" / "egf"
    / "EDYXGV5F6-AhKDAPC5-9kvUq0hB_P0P1WFTRkzdyf2A-.json"
)
PD_ROLE_SCHEMA_SAID = "EDYXGV5F6-AhKDAPC5-9kvUq0hB_P0P1WFTRkzdyf2A-"

# Task 6's other two: what the designer READS (product_mandate -- the edge far
# node it resolves; rate_program_attestation -- what it scans for) and what it
# WRITES (product_bundle). All verified against the bundled schemas by
# tests/plugins/roles/test_pin_regression.py, same as the role schemas above.
_PRODUCT_MANDATE_SCHEMA_PATH = (
    REPO_ROOT / "brands" / "usurance" / "egf"
    / "EFYdgrOvpXpxTkVSVl6dRs1lueELnH9cqxpctqwqpVr5.json"
)
PRODUCT_MANDATE_SCHEMA_SAID = "EFYdgrOvpXpxTkVSVl6dRs1lueELnH9cqxpctqwqpVr5"

_RATE_PROGRAM_ATTESTATION_SCHEMA_PATH = (
    REPO_ROOT / "brands" / "usurance" / "egf"
    / "EPaMxGLoFc6u1if3s367j5J547kLXKJbsztT-OE1gcHP.json"
)
RATE_PROGRAM_ATTESTATION_SCHEMA_SAID = "EPaMxGLoFc6u1if3s367j5J547kLXKJbsztT-OE1gcHP"

_PRODUCT_BUNDLE_SCHEMA_PATH = (
    REPO_ROOT / "brands" / "usurance" / "egf"
    / "EK4y4AX2Uo1d_Y20fyIeg3cZj09RjlvDUzkqXCf2xTL-.json"
)
PRODUCT_BUNDLE_SCHEMA_SAID = "EK4y4AX2Uo1d_Y20fyIeg3cZj09RjlvDUzkqXCf2xTL-"

# Deterministic, fixed salt for the synthetic test-admin party — NOT a secret,
# NOT the real usurance-admin (whose keys live in a real passcode-protected
# vault this suite never touches). The resulting AID is stable across runs
# (recompute with `keripy`'s `Habery(temp=True, salt=Salter(raw=...).qb64)` +
# `makeHab(wits=[], toad=0, version=Vrsn_1_0)` if this salt ever changes) and
# is what `_bootstrap/sitecustomize.py` pins into `CuoPlugin.required_credential`
# for any wallet this suite spawns.
_TEST_ADMIN_SALT = b"cuo_test_admin_01234"
_TEST_ADMIN_AID = "EHdNc8llEejNBzZm3br667fbhwkA8IPsPef-psuXeOm8"

# Installed into every wallet's PYTHONPATH (module-level: this must be in
# place before `two_wallets` spawns anything, and pytest imports conftest.py
# before running any fixture in this package). See _bootstrap/sitecustomize.py
# for what it does and why it is inert for every OTHER locksmith process.
_BOOTSTRAP_DIR = str(pathlib.Path(__file__).resolve().parent / "_bootstrap")
os.environ["CUO_TEST_ADMIN_AID"] = _TEST_ADMIN_AID
os.environ["CUO_TEST_ROLE_SCHEMA_PATH"] = str(_CUO_ROLE_SCHEMA_PATH)
os.environ["ACTUARY_TEST_ROLE_SCHEMA_PATH"] = str(_ACTUARY_ROLE_SCHEMA_PATH)
os.environ["PD_TEST_ROLE_SCHEMA_PATH"] = str(_PD_ROLE_SCHEMA_PATH)
_existing_pp = os.environ.get("PYTHONPATH")
os.environ["PYTHONPATH"] = (
    f"{_BOOTSTRAP_DIR}{os.pathsep}{_existing_pp}" if _existing_pp else _BOOTSTRAP_DIR
)

#: Written by the sitecustomize.py mandate-export hook (patch 5) inside wallet
#: A's own process, read here (filesystem access to A's HOME is all the test
#: process has, since A is a separate subprocess) by `watch_cuo_mandate_via_peer`.
#: Kept as a literal string, cross-referenced with (not imported from)
#: sitecustomize.py's own copy -- see that file's module docstring entry 5.
_MANDATE_EXPORT_FILENAME = "_test_mandate_export.cesr"


def _build_test_admin():
    """A real in-process KERI party: v1-pinned Habery + single unwitnessed
    AID + Regery — the same shape `test_multi_role_e2e.py`'s `_make_party`
    and `test_carrier_gate_e2e.py`'s admin/DOI parties use. Never touches a
    real vault or passcode.

    Pins `cuo_role`'s, `actuary_role`'s AND (Task 6) `product_designer_role`'s
    schemas -- the EGF names the SAME admin AID as issuer of all three
    (`docs/superpowers/specs/2026-08-05-actuarial-hoa-c2-design.md` §4's role
    table; `ProductDesignerPlugin.required_credential` already hardcodes the
    SAME `USURANCE_ADMIN_AID` cuo/actuary do), so one test-admin party plays
    all three issuer roles rather than this suite standing up three.

    (Task 6) ALSO pins `product_mandate`'s and `rate_program_attestation`'s
    schemas. In REALITY those are CUO- and actuary-issued respectively, never
    by usurance-admin -- but Tasks 4 and 5 already prove those two roles' own
    UI flows for real (`declare_mandate_via_ui`, `open_vault_holding_actuary_
    role` + a live attest), so `deliver_rate_program_to_designer` (Task 6's own
    delivery recipe, this module further down) does not re-drive either a
    second time. It re-uses THIS SAME party to synthesize a mandate and an
    edge-linked attestation instead -- still through the real keripy issuance
    machinery (real registries, real TELs, real schema validation), just not
    ALSO routed through a second UI pass that would prove nothing new about
    the designer surface Task 6 actually owns."""
    from keri.app import habbing
    from keri.core import signing as coresigning
    from keri.kering import Vrsn_1_0
    from keri.vdr import credentialing

    hby = habbing.Habery(
        name="cuo_test_admin", temp=True,
        salt=coresigning.Salter(raw=_TEST_ADMIN_SALT).qb64,
    )
    hab = hby.makeHab(name="admin", transferable=True, wits=[], toad=0,
                      version=Vrsn_1_0)
    assert hab.pre == _TEST_ADMIN_AID, (
        f"test-admin AID drifted: got {hab.pre}, sitecustomize.py pins "
        f"{_TEST_ADMIN_AID} — recompute and update both.")
    rgy = credentialing.Regery(hby=hby, name="cuo_test_admin", temp=True)

    # The ISSUER's own Habery must resolve every schema it issues too
    # (Credentialer.validate), independent of the recipient wallet's own
    # copy pinned via sitecustomize.py's on_vault_opened patches.
    import json

    from keri.core import scheming
    from keri.kering import Kinds

    for schema_path, schema_said in (
        (_CUO_ROLE_SCHEMA_PATH, CUO_ROLE_SCHEMA_SAID),
        (_ACTUARY_ROLE_SCHEMA_PATH, ACTUARY_ROLE_SCHEMA_SAID),
        (_PD_ROLE_SCHEMA_PATH, PD_ROLE_SCHEMA_SAID),
        (_PRODUCT_MANDATE_SCHEMA_PATH, PRODUCT_MANDATE_SCHEMA_SAID),
        (_RATE_PROGRAM_ATTESTATION_SCHEMA_PATH, RATE_PROGRAM_ATTESTATION_SCHEMA_SAID),
    ):
        sad = json.loads(schema_path.read_text())
        schemer = scheming.Schemer(sed=sad, kind=Kinds.json)
        assert schemer.said == schema_said, (
            f"bundle schema {schema_said} does not verify")
        hby.db.schema.pin(keys=(schemer.said,), val=schemer)

    return hby, hab, rgy


def _expose_and_export(devctl, sock, alias: str) -> str:
    """Open View Identifier, toggle expose, pick "Peer (offline)", return the
    rendered CESR blob. Mirrors tests/integration/peer/test_send.py's
    `_expose_and_export` (that helper lives in a sibling TEST module, not the
    peer conftest, so it is re-derived here rather than imported across test
    files)."""
    devctl(sock, "click_row_action", row_text=alias, action="View")
    devctl(sock, "wait_for", target="viewIdentifierDialog.aidField",
          condition="visible", timeout_ms=3000)
    devctl(sock, "click", target="viewIdentifierDialog.exposeToggle")
    time.sleep(0.5)  # PublishPeerRoleDoer flush
    devctl(sock, "select", target="viewIdentifierDialog.oobiRoleCombo",
          value="Peer (offline)")
    devctl(sock, "wait_for", target="viewIdentifierDialog.oobiTokenLabel",
          condition="visible", timeout_ms=3000)
    return devctl(sock, "get_text",
                 target="viewIdentifierDialog.oobiTokenLabel")["text"]


def open_vault_holding_cuo_role(
    devctl, sock, *, vault_name: str = "cuovault", alias: str = "cuo",
    admin_state: dict | None = None,
) -> None:
    """Bring up a real vault + AID at `sock`, then make it GENUINELY hold an
    active, chain-verified `cuo_role` credential. See the module docstring
    above for the full design.

    `admin_state`: when given, the (still-open) admin `Habery`/`Hab`/`Regery`
    that minted this credential — plus the credential's own SAID, the
    registry name, and the wallet's peer-listener port — are stashed into it
    INSTEAD of closing `admin_hby` (the caller then owns closing it). Needed
    by `revoke_cuo_role_and_deliver` (Task 7), which must later revoke THIS
    SAME registry entry: `_build_test_admin()` mints a fresh, EMPTY
    environment on every call — `temp=True` Haberies live under a freshly
    `tempfile.mkdtemp`ed directory each construction
    (`hio.base.filing.Filer.reopen`'s own temp-path branch), and
    `Habery.close()` always clears a temp resource regardless of its `clear`
    flag — so a second `_build_test_admin()` call would carry the SAME
    deterministic admin AID but NONE of this registry's TEL/credential
    state. Revoking through a re-derived admin party would therefore either
    crash (`registryByName` returns `None`) or, worse, silently mint+revoke
    an UNRELATED credential the wallet was never granted, leaving the real
    one (and its surface) untouched. Default `None` preserves the exact
    prior behavior (close immediately) for every other caller of this
    helper (`declare_mandate_via_ui` and its own callers)."""
    open_test_vault_via_ui(devctl, sock, name=vault_name)
    create_aid_via_ui(devctl, sock, alias=alias)
    cuo_port = free_port()
    from tests.integration.peer.conftest import (
        import_peer_blob_via_ui, set_peer_mode_via_ui,
    )
    set_peer_mode_via_ui(devctl, sock, port=cuo_port)
    cuo_blob = _expose_and_export(devctl, sock, alias)

    admin_hby, admin_hab, admin_rgy = _build_test_admin()
    try:
        from hio.base import doing
        from locksmith.peer.cesr_blob import export_peer_blob, import_peer_blob
        from locksmith.peer.publishing import PublishPeerRoleDoer

        # admin learns the wallet's key state (needed for `recp=` below) —
        # the imported AID IS the wallet's own prefix.
        cuo_pre = import_peer_blob(admin_hby, cuo_blob)

        # admin publishes its own peer role locally (witness-less: no
        # messenger/witness push — PublishPeerRoleDoer's own no_witnesses
        # path) so `export_peer_blob` below has an rpy to serve. The URL is
        # never dialed — the wallet never needs to reach admin back for this
        # recipe (no send-mode admit, see the module docstring).
        publish_doer = PublishPeerRoleDoer(
            hby=admin_hby, hab=admin_hab,
            url="tcp://127.0.0.1:1/", signal_bridge=None, allow=True,
        )
        doing.Doist(limit=2.0, tock=0.03125, real=False).do(doers=[publish_doer])

        # real registry-backed issuance — the SAME library function
        # `ServiceaidIssueDoer` wraps in production (serviceaid_bridge.py).
        from keri_serviceaid.providers import frame_grant_for, issue_credential

        registry_name = CUO_ROLE_SCHEMA_SAID
        said = issue_credential(
            admin_hby, admin_hab, admin_rgy,
            schema_said=CUO_ROLE_SCHEMA_SAID, recipient=cuo_pre,
            attributes={}, registry_name=registry_name,
        )
        _grant_said, grant_raw = frame_grant_for(
            admin_hby, admin_hab, admin_rgy,
            credential_said=said, recipient=cuo_pre, return_raw=True,
        )

        # Export admin's blob AFTER issuance, so it carries admin's CURRENT
        # KEL (registry-inception ixn + issuance ixn), not just inception —
        # `hab.replyToOobi` -> `replyEndRole` replays the FULL KEL as of the
        # call.
        admin_blob = export_peer_blob(admin_hab)
        import_peer_blob_via_ui(devctl, sock, admin_blob, label="admin")

        # The registry's own TEL (`vcp`) — NOT among frame_grant_for's
        # embeds — plus the credential's own TEL (redundant with the grant's
        # `iss` embed, harmless to resend). See module docstring point 1.
        registry = admin_rgy.registryByName(registry_name)
        artifact_stream = bytearray()
        for msg in admin_rgy.reger.clonePreIter(pre=registry.regk):
            artifact_stream.extend(msg)
        for msg in admin_rgy.reger.clonePreIter(pre=said):
            artifact_stream.extend(msg)
    finally:
        if admin_state is None:
            admin_hby.close()
        else:
            admin_state.update(
                hby=admin_hby, hab=admin_hab, rgy=admin_rgy,
                cred_said=said, registry_name=registry_name, port=cuo_port,
                # the wallet's own AID prefix — admin already resolved it
                # above; a LATER caller minting a second credential for the
                # SAME wallet (grant_actuary_role_to_cuo_wallet) needs it too,
                # and re-deriving it via a second import_peer_blob call does
                # NOT work for an already-known AID (parse_oobi_cesr's
                # `new_kevers` list is empty on a re-parse, so without an
                # `expect=` it reports `damaged_stream` even though nothing
                # is actually wrong — measured).
                holder_pre=cuo_pre,
            )

    # Deliver the registry's TEL over the real peer connection FIRST, as its
    # own message(s) — NOT bundled with the grant exn. Once the wallet's own
    # Tevery knows the registry, the grant's embedded `iss` verifies against
    # already-known state instead of escrowing on a missing registry.
    with socket.create_connection(("127.0.0.1", cuo_port), timeout=5.0) as s:
        s.sendall(bytes(artifact_stream))
    time.sleep(1.0)  # let the wallet's Reactant/Tevery land it

    # Now the grant exn ALONE, through the file-based Accept flow — every
    # dialog here opens via `.open()` (non-blocking), unlike the
    # Notifications page's Admit action (module docstring point 2), so
    # devctl keeps responding throughout.
    fd, cesr_path = tempfile.mkstemp(suffix=".cesr", prefix="cuo_role_grant_")
    with os.fdopen(fd, "wb") as f:
        f.write(grant_raw)

    r = devctl(sock, "click", target="vaultNavMenu.credentialsButton")
    assert r.get("ok"), f"expand Credentials submenu: {r}"
    r = devctl(sock, "click", target="vaultNavMenu.receivedCredentialsButton")
    assert r.get("ok"), f"navigate to Received Credentials: {r}"
    r = devctl(sock, "click", target="Accept Credential Issuance")
    assert r.get("ok"), f"open Accept Credential dialog: {r}"
    r = devctl(sock, "wait_for", target="File Path", condition="visible",
              timeout_ms=3000)
    assert r.get("ok"), f"Accept Credential dialog never appeared: {r}"
    r = devctl(sock, "type", target="File Path", text=cesr_path)
    assert r.get("ok"), f"type grant file path: {r}"
    r = devctl(sock, "click", target="Load")
    assert r.get("ok"), f"click Load: {r}"

    r = devctl(sock, "wait_for", target="Admit", condition="visible",
              timeout_ms=5000)
    assert r.get("ok"), f"AcceptGrantDialog never opened: {r}"
    r = devctl(sock, "click", target="Admit")
    assert r.get("ok"), f"click Admit: {r}"

    # The gate reveals the "Underwriting" menu entry + registers the page in
    # the vault's content stack, but registering a page does not make it the
    # CURRENT stack page — a person still clicks the new menu entry to open
    # it, exactly like any other role surface. Poll: the entry button has no
    # objectName (`CuoPlugin.get_menu_entry()` sets none), so it is selected
    # by its visible label text; the gate opening is itself asynchronous
    # (`AdmitDoer`'s own `admit_complete` -> `reevaluate_role_gates`), so the
    # button is not guaranteed to exist the instant "Admit" returns.
    deadline = time.time() + 15.0
    last = None
    while time.time() < deadline:
        r = devctl(sock, "click", target="Underwriting")
        if r.get("ok"):
            break
        last = r
        time.sleep(0.5)
    else:
        raise AssertionError(f"the Underwriting menu entry never appeared: {last}")


# ---------------------------------------------------------------------------
# Task 7 helpers: grant_actuary_role_to_cuo_wallet, _complete_revoke,
# revoke_cuo_role_and_deliver -- the cuo revocation slice (done-when #5).
# ---------------------------------------------------------------------------

def grant_actuary_role_to_cuo_wallet(devctl, sock, admin_state: dict) -> None:
    """Grant a SECOND gated role -- `actuary_role` -- to the SAME wallet/AID
    `open_vault_holding_cuo_role` (called with `admin_state=`) already
    granted `cuo_role` to, using the SAME live admin session (continuing
    its KEL forward) rather than a fresh `_build_test_admin()` party or a
    second real peer pairing. Exists so a revocation test can prove
    SELECTIVITY at the real UI layer: a sibling gated surface on the SAME
    identity must survive revoking a DIFFERENT role -- a claim a second
    wallet cannot demonstrate (a different OS process is independent by
    construction, not by the revocation code's own selectivity).

    Two measured constraints shape this, both real app-level behaviors this
    helper works AROUND rather than through:

    1. A FRESH `_build_test_admin()` party would carry the SAME
       deterministic `_TEST_ADMIN_AID` (both plugins' `required_credential`
       trust ONLY that AID -- sitecustomize.py patches 2 and 4) but its OWN
       independent KEL, starting again at inception. Delivering ITS
       registry-inception `ixn` to a wallet that already knows this AID's
       KEL through a HIGHER sn (from the cuo grant) would be a KEL FORK, not
       an extension. So this reuses `admin_state`'s SAME live
       Habery/Hab/Regery, continuing its KEL forward instead.
    2. `AddPeerDialog` refuses to re-pair an AID the vault already has as a
       contact ("This peer is already paired with this vault.", measured in
       `add_dialog.py::_on_pair_clicked`) -- so this does NOT re-run
       `import_peer_blob_via_ui`. Admin's KEL growth (the actuary
       registry-inception + issuance `ixn`s) is instead delivered as raw
       bytes over the SAME peer connection already open
       (`admin_state["port"]`), landed by the wallet's own real Kevery --
       the identical mechanism `revoke_cuo_role_and_deliver` (below) uses to
       deliver a revocation without re-pairing.

    Runs a SECOND "Accept Credential Issuance" -> "Accept Credential Grant"
    cycle on this wallet (the first was cuo's own grant, inside
    `open_vault_holding_cuo_role`). Both dialogs are `LocksmithDialog`
    subclasses whose `.close()`/`.accept()` HIDE rather than destroy (no
    `WA_DeleteOnClose` -- see `dialogs.py`'s `showEvent`/`closeEvent`), so
    the first cycle's now-hidden instances are still in the tree when this
    second cycle opens its own -- the SAME not-destroyed-on-close shape as
    `ViewIdentifierDialog`/`AddPeerDialog` elsewhere in this file. `wait_for`
    (visibility-UNFILTERED `_find_widget_any`) therefore needs an
    `occurrence` override to select the live (second-created) instance --
    see the two wait_for calls below for the EXACT index each selector
    needs (they differ: a label-text selector matches twice per dialog
    instance, an objectName/button-text selector once). `type`/`click`
    (visibility-FILTERED `_find_widget`, and with NO occurrence support at
    all -- see `_export_current_blob`'s docstring) already exclude the
    hidden stale ones, so they need no override.

    Leaves the wallet navigated to `actuaryPage` (mirrors
    `open_vault_holding_actuary_role`'s own tail poll). Does NOT close
    `admin_state["hby"]` -- the caller (here, `revoke_cuo_role_and_deliver`,
    called afterward) owns that."""
    admin_hby = admin_state["hby"]
    admin_hab = admin_state["hab"]
    admin_rgy = admin_state["rgy"]
    port = admin_state["port"]
    # Admin already resolved this wallet's key state during the cuo grant
    # (`open_vault_holding_cuo_role`'s own `cuo_pre = import_peer_blob(...)`)
    # and `admin_state` carries it forward as `holder_pre`. Re-deriving it
    # via a SECOND `import_peer_blob` call does NOT work for an
    # already-known AID: `parse_oobi_cesr`'s `new_kevers` list is empty on a
    # re-parse (nothing NEW landed), and without an explicit `expect=` that
    # reads as `damaged_stream` even though nothing is actually wrong
    # (measured) — so this reuses the prefix rather than re-importing it.
    actuary_pre = admin_state["holder_pre"]

    from keri_serviceaid.providers import frame_grant_for, issue_credential
    from locksmith.core.credentialing import outputKEL

    registry_name = ACTUARY_ROLE_SCHEMA_SAID
    said = issue_credential(
        admin_hby, admin_hab, admin_rgy,
        schema_said=ACTUARY_ROLE_SCHEMA_SAID, recipient=actuary_pre,
        attributes={}, registry_name=registry_name,
    )
    _grant_said, grant_raw = frame_grant_for(
        admin_hby, admin_hab, admin_rgy,
        credential_said=said, recipient=actuary_pre, return_raw=True,
    )

    # Admin's OWN KEL (now carrying the actuary registry-inception +
    # issuance ixns, ON TOP of cuo's own) + the actuary registry's TEL + the
    # actuary credential's own TEL -- all over the wire, no re-pairing.
    registry = admin_rgy.registryByName(registry_name)
    artifact_stream = bytearray()
    artifact_stream.extend(outputKEL(admin_hby, admin_hab.pre))
    for msg in admin_rgy.reger.clonePreIter(pre=registry.regk):
        artifact_stream.extend(msg)
    for msg in admin_rgy.reger.clonePreIter(pre=said):
        artifact_stream.extend(msg)

    with socket.create_connection(("127.0.0.1", port), timeout=5.0) as s:
        s.sendall(bytes(artifact_stream))
    time.sleep(1.0)  # let the wallet's Reactant/Kevery/Tevery land it

    fd, cesr_path = tempfile.mkstemp(
        suffix=".cesr", prefix="actuary_role_grant_sibling_")
    with os.fdopen(fd, "wb") as f:
        f.write(grant_raw)

    # open_vault_holding_cuo_role's own tail leaves the wallet on
    # CuoMandatePage, reached by clicking "Underwriting" while the nav's own
    # state still reads "in credentials" -- the SAME VaultNavMenu desync
    # watch_cuo_mandate_via_peer's docstring documents (its own back-button
    # never became visible). The credentials submenu's OWN back button pops
    # to the top-level menu, where `vaultNavMenu.credentialsButton` exists
    # to click again below.
    devctl(sock, "click", target="vaultNavMenu.credentialsBackButton")

    r = devctl(sock, "click", target="vaultNavMenu.credentialsButton")
    assert r.get("ok"), f"expand Credentials submenu (sibling grant): {r}"
    r = devctl(sock, "click", target="vaultNavMenu.receivedCredentialsButton")
    assert r.get("ok"), f"navigate to Received Credentials (sibling grant): {r}"
    r = devctl(sock, "click", target="Accept Credential Issuance")
    assert r.get("ok"), f"open Accept Credential dialog (sibling grant): {r}"
    # occurrence=2, NOT 1: "File Path" is a plain LABEL-TEXT selector (no
    # objectName), and FloatingLabelLineEdit yields TWO matches per dialog
    # instance for such a selector -- the inner QLabel's `.text()` AND the
    # wrapper widget's own `_label_text` attribute (`_find_widget_any`
    # checks both) -- so ONE stale AcceptCredentialDialog (cuo's own, from
    # `open_vault_holding_cuo_role`) contributes matches at indices 0-1, and
    # this second, live dialog's own pair starts at index 2 (measured: a
    # `count`/`is_visible` sweep showed occurrence 0 and 1 both
    # `visible=False`, occurrence 2 `visible=True`). objectName-selected
    # targets elsewhere in this file (e.g. `viewIdentifierDialog.aidField`)
    # only ever get ONE match per instance, hence occurrence=1 there.
    r = devctl(sock, "wait_for", target="File Path", condition="visible",
              timeout_ms=3000, occurrence=2)
    assert r.get("ok"), f"Accept Credential dialog (sibling grant) never appeared: {r}"
    r = devctl(sock, "type", target="File Path", text=cesr_path)
    assert r.get("ok"), f"type grant file path (sibling grant): {r}"
    r = devctl(sock, "click", target="Load")
    assert r.get("ok"), f"click Load (sibling grant): {r}"

    # "Admit" is a plain LocksmithButton (`.text()` only, no label_text
    # duplicate), so it gets exactly ONE match per instance -- occurrence=1
    # skips cuo's own now-stale AcceptGrantDialog and lands on this live one.
    r = devctl(sock, "wait_for", target="Admit", condition="visible",
              timeout_ms=5000, occurrence=1)
    assert r.get("ok"), f"AcceptGrantDialog (sibling grant) never opened: {r}"
    r = devctl(sock, "click", target="Admit")
    assert r.get("ok"), f"click Admit (sibling grant): {r}"

    # Mirrors open_vault_holding_actuary_role's own tail poll.
    deadline = time.time() + 15.0
    last = None
    while time.time() < deadline:
        r = devctl(sock, "click", target="Actuarial")
        if r.get("ok"):
            break
        last = r
        time.sleep(0.5)
    else:
        raise AssertionError(
            f"the Actuarial menu entry never appeared (sibling grant): {last}")


def _complete_revoke(rgy, registrar, pre, sn, rounds: int = 64) -> None:
    """Pump the no-backer TEL revoke escrow on a virtual-time Doist until the
    `rev` event is committed. Re-derived (not imported) from
    `test_carrier_gate_e2e.py`'s own `_complete` -- same cross-test-module
    convention this file's other sibling-test re-derivations already follow
    (see `_expose_and_export`'s docstring) -- narrowed to the registrar-only
    path a revoke needs (no verifier/credentialer args, unlike issuance)."""
    from hio.base import doing

    doist = doing.Doist(real=False, tock=1.0)
    deeds = doist.enter(doers=[registrar])
    try:
        for _ in range(rounds):
            if registrar.complete(pre=pre, sn=sn):
                return
            rgy.processEscrows()
            doist.recur(deeds=deeds)
        raise AssertionError(f"TEL revoke did not complete: pre={pre} sn={sn}")
    finally:
        doist.exit(deeds=deeds)


def revoke_cuo_role_and_deliver(admin_state: dict) -> None:
    """Revoke the `cuo_role` credential `open_vault_holding_cuo_role` (called
    with `admin_state=`) already granted to a wallet, and deliver the
    revocation over a real peer connection -- the two Task-7 recipes, BOTH
    load-bearing. Takes no `devctl`/`two_wallets`: this drives no UI, only
    the admin-side issuer machinery + the wire delivery the recipient
    wallet's OWN Reactant lands on its own (the UI test that calls this
    separately `wait_for`s the visible effect on its own socket).

    Issuer side, following `test_carrier_gate_e2e.py:616`'s `_revoke`
    EXACTLY: `registry.revoke()` -> `SealEvent` -> version-pinned
    `hab.interact()` -> `Registrar.revoke()`. Skipping the interact leaves
    the TEL unanchored -- `registrar.complete()` never returns True (there is
    no anchoring seal in `admin_hab`'s KEL for `_complete_revoke` to find),
    so the revocation would be invisible to any holder however delivered.

    Holder side, mirroring `test_multi_role_e2e.py:183`'s `_deliver_rev`
    idiom (issuer KEL + credential TEL) -- except these bytes travel over
    the SAME real peer TCP connection `open_vault_holding_cuo_role` already
    opened wallet B's listener on (`admin_state["port"]`), landed by wallet
    B's OWN real Reactant/Kevery/Tevery in its own subprocess, not parsed
    in-process. Reusing that port for a SECOND delivery is a proven pattern
    in this file already -- `deliver_rate_program_to_designer` sends two
    separate messages to the same `designer_port` across two legs.

    Requires `admin_state` to be the SAME dict `open_vault_holding_cuo_role`
    populated (its `hby`/`hab`/`rgy` must still be the live party that
    minted the credential wallet B holds -- see that function's own
    docstring for why a fresh `_build_test_admin()` party cannot stand in).
    Closes `admin_state["hby"]` when done -- this is the one-shot consumer
    of the state that function stashed."""
    from keri.app import grouping
    from keri.core import eventing, serdering
    from keri.help import helping
    from keri.kering import Vrsn_1_0
    from keri.vdr import credentialing

    from locksmith.core.credentialing import outputKEL, outputTEL

    admin_hby = admin_state["hby"]
    admin_hab = admin_state["hab"]
    admin_rgy = admin_state["rgy"]
    said = admin_state["cred_said"]
    registry_name = admin_state["registry_name"]
    port = admin_state["port"]

    try:
        registry = admin_rgy.registryByName(registry_name)
        assert registry is not None, (
            f"registry {registry_name!r} not found in the SAME admin party "
            "that minted the credential -- admin_state must come from the "
            "matching open_vault_holding_cuo_role(admin_state=...) call")
        counselor = grouping.Counselor(hby=admin_hby)
        registrar = credentialing.Registrar(
            hby=admin_hby, rgy=admin_rgy, counselor=counselor)
        creder = admin_rgy.reger.cloneCred(said=said)[0]
        rserder = registry.revoke(said=said, dt=helping.nowIso8601())
        rseal = eventing.SealEvent(rserder.pre, rserder.snh, rserder.said)
        rseal = dict(i=rseal.i, s=rseal.s, d=rseal.d)
        anc = admin_hab.interact(data=[rseal], version=Vrsn_1_0)
        registrar.revoke(creder=creder, rserder=rserder,
                         anc=serdering.SerderKERI(raw=bytes(anc)))
        _complete_revoke(admin_rgy, registrar, rserder.pre, rserder.sn)

        stream = bytearray()
        stream.extend(outputKEL(admin_hby, admin_hab.pre))
        stream.extend(outputTEL(admin_rgy, said))
    finally:
        admin_hby.close()

    with socket.create_connection(("127.0.0.1", port), timeout=5.0) as s:
        s.sendall(bytes(stream))
    time.sleep(1.0)  # let wallet B's Reactant/Kevery/Tevery land the revoke


# ---------------------------------------------------------------------------
# Task 5 helpers: declare_mandate_via_ui, open_vault_holding_actuary_role,
# watch_cuo_mandate_via_peer — the actuary observes-and-attests slice.
# ---------------------------------------------------------------------------

def declare_mandate_via_ui(devctl, sock) -> None:
    """The CUO declares a mandate through the real form.

    Extracted from Task 4's own test body (`test_cuo_mandate_via_ui.py`) so
    Task 5 can drive the SAME slice as its opening leg rather than re-deriving
    it — that test now calls this too, so there is exactly one copy of the
    form-filling recipe. Opens a fresh vault + AID + `cuo_role` grant (via
    `open_vault_holding_cuo_role`, alias "cuo") and submits design §6's five
    fields, waiting for the real issuance to complete."""
    open_vault_holding_cuo_role(devctl, sock)

    r = devctl(sock, "wait_for", target="cuoMandatePage",
               condition="visible", timeout_ms=5000)
    assert r.get("ok"), r

    for target, value in [
        ("cuoMandatePage.lineOfBusiness", "Auto"),
        ("cuoMandatePage.jurisdiction", "UT"),
        ("cuoMandatePage.coverages", "BI,PD"),
        ("cuoMandatePage.effectiveWindow", "2027-01-01/2027-12-31"),
        ("cuoMandatePage.thesis", "Rate adequacy restoration."),
    ]:
        r = devctl(sock, "type", target=target, text=value)
        assert r.get("ok"), (target, r)

    r = devctl(sock, "is_checked", target="cuoMandatePage.submit")
    assert r.get("ok"), r

    r = devctl(sock, "click", target="cuoMandatePage.submit")
    assert r.get("ok"), r

    r = devctl(sock, "wait_for", target="cuoMandatePage.declaredBanner",
               condition="visible", timeout_ms=10000)
    assert r.get("ok"), r


def open_vault_holding_actuary_role(
    devctl, sock, *, vault_name: str = "actuaryvault", alias: str = "actuary",
) -> None:
    """Sibling of `open_vault_holding_cuo_role` — same recipe, `actuary_role`
    credential. See that function's module-level docstring for the full design
    (the two-leg delivery, and why each leg is shaped the way it is); nothing
    here differs except which schema/registry/menu-entry is used."""
    open_test_vault_via_ui(devctl, sock, name=vault_name)
    create_aid_via_ui(devctl, sock, alias=alias)
    actuary_port = free_port()
    from tests.integration.peer.conftest import (
        import_peer_blob_via_ui, set_peer_mode_via_ui,
    )
    set_peer_mode_via_ui(devctl, sock, port=actuary_port)
    actuary_blob = _expose_and_export(devctl, sock, alias)

    admin_hby, admin_hab, admin_rgy = _build_test_admin()
    try:
        from hio.base import doing
        from locksmith.peer.cesr_blob import export_peer_blob, import_peer_blob
        from locksmith.peer.publishing import PublishPeerRoleDoer

        actuary_pre = import_peer_blob(admin_hby, actuary_blob)

        publish_doer = PublishPeerRoleDoer(
            hby=admin_hby, hab=admin_hab,
            url="tcp://127.0.0.1:1/", signal_bridge=None, allow=True,
        )
        doing.Doist(limit=2.0, tock=0.03125, real=False).do(doers=[publish_doer])

        from keri_serviceaid.providers import frame_grant_for, issue_credential

        registry_name = ACTUARY_ROLE_SCHEMA_SAID
        said = issue_credential(
            admin_hby, admin_hab, admin_rgy,
            schema_said=ACTUARY_ROLE_SCHEMA_SAID, recipient=actuary_pre,
            attributes={}, registry_name=registry_name,
        )
        _grant_said, grant_raw = frame_grant_for(
            admin_hby, admin_hab, admin_rgy,
            credential_said=said, recipient=actuary_pre, return_raw=True,
        )

        admin_blob = export_peer_blob(admin_hab)
        import_peer_blob_via_ui(devctl, sock, admin_blob, label="admin")

        registry = admin_rgy.registryByName(registry_name)
        artifact_stream = bytearray()
        for msg in admin_rgy.reger.clonePreIter(pre=registry.regk):
            artifact_stream.extend(msg)
        for msg in admin_rgy.reger.clonePreIter(pre=said):
            artifact_stream.extend(msg)
    finally:
        admin_hby.close()

    with socket.create_connection(("127.0.0.1", actuary_port), timeout=5.0) as s:
        s.sendall(bytes(artifact_stream))
    time.sleep(1.0)  # let the wallet's Reactant/Tevery land it

    fd, cesr_path = tempfile.mkstemp(suffix=".cesr", prefix="actuary_role_grant_")
    with os.fdopen(fd, "wb") as f:
        f.write(grant_raw)

    r = devctl(sock, "click", target="vaultNavMenu.credentialsButton")
    assert r.get("ok"), f"expand Credentials submenu: {r}"
    r = devctl(sock, "click", target="vaultNavMenu.receivedCredentialsButton")
    assert r.get("ok"), f"navigate to Received Credentials: {r}"
    r = devctl(sock, "click", target="Accept Credential Issuance")
    assert r.get("ok"), f"open Accept Credential dialog: {r}"
    r = devctl(sock, "wait_for", target="File Path", condition="visible",
              timeout_ms=3000)
    assert r.get("ok"), f"Accept Credential dialog never appeared: {r}"
    r = devctl(sock, "type", target="File Path", text=cesr_path)
    assert r.get("ok"), f"type grant file path: {r}"
    r = devctl(sock, "click", target="Load")
    assert r.get("ok"), f"click Load: {r}"

    r = devctl(sock, "wait_for", target="Admit", condition="visible",
              timeout_ms=5000)
    assert r.get("ok"), f"AcceptGrantDialog never opened: {r}"
    r = devctl(sock, "click", target="Admit")
    assert r.get("ok"), f"click Admit: {r}"

    # Mirrors open_vault_holding_cuo_role's own poll — ActuaryPlugin's menu
    # entry has no objectName either (get_menu_entry sets none), and the gate
    # opening is asynchronous.
    deadline = time.time() + 15.0
    last = None
    while time.time() < deadline:
        r = devctl(sock, "click", target="Actuarial")
        if r.get("ok"):
            break
        last = r
        time.sleep(0.5)
    else:
        raise AssertionError(f"the Actuarial menu entry never appeared: {last}")


def _export_current_blob(devctl, sock, alias: str) -> str:
    """Re-export `alias`'s CURRENT peer-OOBI blob, safe to call AFTER it is
    already exposed (unlike `_expose_and_export`, which unconditionally clicks
    the expose toggle and would therefore TOGGLE IT OFF on a second call).
    `hab.replyToOobi` -> `replyEndRole` replays the FULL KEL as of the call
    (see `open_vault_holding_cuo_role`'s own docstring), so calling this AFTER
    more KEL events have landed (e.g. after declaring a mandate) picks up the
    growth — which is the entire point of calling it a second time.

    (Task 5 finding) `ViewIdentifierDialog`'s own `Close` button hides rather
    than destroys it (no `deleteLater()`), so a SECOND "View" open leaves TWO
    `viewIdentifierDialog.*`-named widget sets alive in the tree at once — the
    first permanently `visible=False`. This alias's SECOND-ever View open
    (the first was `_expose_and_export`'s, during initial role setup) always
    leaves exactly this pair, which is why the occurrence indices below are
    hardcoded rather than derived. **The two devctl finders disagree on what
    they count**, measured directly (`server.py`'s `_find_widget` vs
    `_find_widget_any`): `wait_for`/`is_visible` use `_find_widget_any`, which
    does NOT filter by visibility, so BOTH dialogs are in its match list and
    the live one is `occurrence=1`. `is_checked`/`select`/`get_text` use
    `_find_widget`, which filters to visible widgets ONLY -- the stale dialog
    never enters that list at all, so the (one and only) live widget is
    `occurrence=0`. Passing `occurrence=1` to one of THESE, by analogy with
    `wait_for`, silently resolves nothing (measured: "widget not found")."""
    devctl(sock, "click_row_action", row_text=alias, action="View")
    r = devctl(sock, "wait_for", target="viewIdentifierDialog.aidField",
              condition="visible", timeout_ms=3000, occurrence=1)
    assert r.get("ok"), f"View Identifier dialog never opened for {alias!r}: {r}"

    r = devctl(sock, "is_checked", target="viewIdentifierDialog.exposeToggle",
              occurrence=0)
    assert r.get("ok"), r
    if not r["checked"]:
        # Should never fire in practice (the alias was already exposed by
        # _expose_and_export) -- fail loudly rather than clicking, since
        # _op_click has no occurrence support at all (see conftest module
        # docstring's sibling note) and could hit either dialog.
        raise AssertionError(
            f"{alias!r} was not already exposed -- _export_current_blob only "
            "handles the already-exposed case")

    r = devctl(sock, "select", target="viewIdentifierDialog.oobiRoleCombo",
              value="Peer (offline)", occurrence=0)
    assert r.get("ok"), r
    r = devctl(sock, "wait_for", target="viewIdentifierDialog.oobiTokenLabel",
              condition="visible", timeout_ms=3000, occurrence=1)
    assert r.get("ok"), r
    text = devctl(sock, "get_text", target="viewIdentifierDialog.oobiTokenLabel",
                 occurrence=0)["text"]

    # Deliberately no "Close" click: _op_click has no occurrence support, so
    # it would resolve first-match (the stale, already-inert dialog from
    # _expose_and_export) rather than this live one -- a harmless no-op, but
    # not an honest "closed the dialog" either. Leaving the live dialog open
    # is harmless; nothing downstream in this suite depends on this page.
    return text


def _import_peer_blob_second_time(devctl, sock, blob: str, label: str | None = None) -> None:
    """Sibling of `tests.integration.peer.conftest.import_peer_blob_via_ui`
    for a wallet's SECOND "Add Peer" pairing (`b["sock"]` here already paired
    with "admin" during `open_vault_holding_actuary_role`). Not a copy for
    its own sake: `AddPeerDialog` is the same not-destroyed-on-close shape as
    `ViewIdentifierDialog` (see `_export_current_blob`'s docstring), so a
    second open leaves the same live-vs-stale pair, and the shared helper
    takes no `occurrence` to select between them. Only the ONE `wait_for`
    call needs `occurrence=1` -- `_op_type`/`_op_click` resolve through
    `_find_widget`, which is visible-only-filtered, so the stale copy is
    never a candidate for them in the first place and the default
    occurrence=0 already lands on the live widget."""
    r = devctl(sock, "click", target="vaultNavMenu.settingsButton")
    assert r.get("ok"), f"navigate to Settings: {r}"
    r = devctl(sock, "wait_for", target="peerSettingsSection.addPeerButton",
              condition="visible", timeout_ms=3000)
    assert r.get("ok"), r

    r = devctl(sock, "click", target="peerSettingsSection.addPeerButton")
    assert r.get("ok"), f"open Add Peer dialog: {r}"
    r = devctl(sock, "wait_for", target="addPeerDialog.oobiInput",
              condition="visible", timeout_ms=3000, occurrence=1)
    assert r.get("ok"), f"Add Peer dialog never appeared: {r}"

    r = devctl(sock, "type", target="addPeerDialog.oobiInput", text=blob)
    assert r.get("ok"), f"paste blob into OOBI input: {r}"

    if label:
        r = devctl(sock, "type", target="addPeerDialog.labelInput", text=label)
        assert r.get("ok"), f"type label: {r}"

    r = devctl(sock, "click", target="addPeerDialog.pairButton")
    assert r.get("ok"), f"click Pair: {r}"

    r = devctl(sock, "wait_for", target="addPeerDialog.oobiInput",
              condition="hidden", timeout_ms=3000, occurrence=1)
    if not r.get("ok"):
        err = devctl(sock, "get_text", target="addPeerDialog.errorLabel")
        raise AssertionError(
            f"Pair dialog didn't close — likely error: {err.get('text', '?')!r}")

    r = devctl(sock, "click", target="vaultNavMenu.identifiersButton")
    assert r.get("ok"), r


def watch_cuo_mandate_via_peer(devctl, two_wallets) -> None:
    """B watches A's KEL for the mandate A already declared.

    Two real deliveries, neither of them a grant (a mandate has none — see
    `cuo/page.py`'s own module docstring):

    1. **The KEL leg.** B pairs with A over a real peer-OOBI blob, re-exported
       AFTER the declare (so it carries the mandate's anchoring `ixn`, not just
       inception) — `import_peer_blob_via_ui` replays A's full KEL into B's
       own `hby.kevers`/db via B's REAL Kevery, exactly the mechanism
       `open_vault_holding_cuo_role` already relies on for the admin's KEL.
       This alone is "the watch": `ActuaryPage`'s own `AnchorWatcher` scan
       finds the seal the moment it is locally known — nothing about the SCAN
       is test-only.

    2. **The body leg.** The registry TEL, the credential's own TEL, and the
       credential's raw ACDC + its anchoring proof — the real
       `keri.vdr.credentialing.sendCredential` recipe — pushed over a real
       peer TCP connection into B, landed by B's REAL `Reactant`/`Verifier`
       (see `directing.py`'s `vry=self.verifier` fix; without it this message
       is silently dropped). The ONLY test-only step is how these bytes leave
       wallet A's process at all: A is a separately-driven GUI subprocess, so
       nothing in the pytest process can reach into it directly. See
       `_bootstrap/sitecustomize.py`'s patch 5, which runs INSIDE A's process
       (hooked on `CuoMandatePage._show_declared`) and writes the SAME bytes
       `sendArtifacts`/`sendCredential` would stream over a postman to a file
       under A's own HOME; this function reads that file (filesystem access is
       all the test process has to a sibling subprocess) and pushes it over
       the wire exactly as A itself would have, had this transport already
       grown a `pro`/`bar` responder (design's own open item — see
       `keri.app.prodding`).
    """
    a, b = two_wallets["a"], two_wallets["b"]

    # open_vault_holding_actuary_role ends on the actuary role's OWN plugin
    # page, reached by clicking "Actuarial" while the CREDENTIALS submenu
    # (Received Credentials -> Accept flow) was still the nav's active state.
    # (Task 5 finding) VaultNavMenu desyncs here: the STACKED CONTENT switches
    # to ActuaryPlaceholderPage (plugin_section_clicked's page-switch listener
    # runs), but the NAV WIDGET's own state stays "in credentials" --
    # `push_plugin_menu`'s own back button (`vaultNavMenu.actuaryAutoBackButton`)
    # never becomes visible, because nothing exits `_in_credentials_menu`
    # first. The credentials submenu's OWN back button is still live, though
    # (measured: visible in the widget tree throughout), and clicking it pops
    # to the top-level menu via the credentials code path regardless of the
    # plugin-page mismatch -- restoring Identifiers/Settings/Credentials.
    devctl(b["sock"], "click", target="vaultNavMenu.credentialsBackButton")

    b_port = free_port()
    from tests.integration.peer.conftest import (
        import_peer_blob_via_ui, set_peer_mode_via_ui,
    )
    set_peer_mode_via_ui(devctl, b["sock"], port=b_port)

    # Same desync on wallet A: declare_mandate_via_ui ends on CuoMandatePage,
    # reached the same way (a credentials-submenu-era click on its own plugin
    # section), so the identifiers table isn't the current page yet either.
    devctl(a["sock"], "click", target="vaultNavMenu.credentialsBackButton")
    devctl(a["sock"], "click", target="vaultNavMenu.identifiersButton")

    cuo_blob = _export_current_blob(devctl, a["sock"], "cuo")
    _import_peer_blob_second_time(devctl, b["sock"], cuo_blob, label="cuo")

    export_path = a["home"] / _MANDATE_EXPORT_FILENAME
    deadline = time.time() + 15.0
    while not export_path.is_file() and time.time() < deadline:
        time.sleep(0.2)
    assert export_path.is_file(), (
        f"the mandate-export sitecustomize.py hook never wrote {export_path} — "
        "did declare_mandate_via_ui actually complete first?")
    artifact = export_path.read_bytes()
    assert artifact, f"{export_path} exists but is empty"

    with socket.create_connection(("127.0.0.1", b_port), timeout=5.0) as s:
        s.sendall(artifact)
    time.sleep(1.0)  # let B's Reactant/Kevery/Tevery/Verifier land it

    # The pairing dance above leaves B on Identifiers (_import_peer_blob_
    # second_time's own last step, mirroring the shared helper it stands in
    # for). Return to the actuary's own surface -- same poll shape as
    # open_vault_holding_cuo_role's "Underwriting" wait, since the gate/
    # section-switch is asynchronous here too.
    deadline = time.time() + 15.0
    last = None
    while time.time() < deadline:
        r = devctl(b["sock"], "click", target="Actuarial")
        if r.get("ok"):
            break
        last = r
        time.sleep(0.5)
    else:
        raise AssertionError(f"the Actuarial menu entry never appeared: {last}")


# ---------------------------------------------------------------------------
# The real `ipd-parse` output fixture. Mirrors ugard's own
# tests/corpus/test_actuarial_trio.py (`_parser_python`/`parse_dir`) — that
# file cannot be imported across repos, so the recipe is re-derived here
# rather than shared. Genuinely NOT a synthetic stand-in: the manifest
# `ActuaryPage.load_parse` computes commits to the parsed shards AND the
# source workbook's own bytes, and a fabricated directory would erase exactly
# the property this test exists to demonstrate.
# ---------------------------------------------------------------------------

_UGARD_ROOT = pathlib.Path.home() / "code" / "ugard"
_PARSER_DIR = _UGARD_ROOT / "insurance-product" / "parser"
_WORKBOOK = _PARSER_DIR / "tests" / "fixtures" / "TestExcel_01.xlsm"
_PARSE_ARGS = ["--line-of-business", "L", "--jurisdiction", "WI",
              "--version", "1.0", "--filing-date", "2022-05-01",
              "--action", "sandbox"]
_WORKBOOK_SIDECAR_NAME = ".workbook_source.json"  # must match actuary/page.py's own


def _parser_python() -> str:
    """An interpreter that can import `openpyxl`, or a loud failure.

    keripy's venv — which this suite runs under, because it is the only one
    with `keri` — has no `openpyxl`, and the parser's own venv has no `keri`.
    So the parse is shelled out to the parser's own venv. NOT skipped when
    absent, mirroring ugard's own `_parser_python`: a skip here would silently
    reduce this test to exactly the synthetic-fixture shortcut it exists to
    prove is not what happened.
    """
    candidate = _PARSER_DIR / ".venv" / "bin" / "python"
    if candidate.is_file():
        return str(candidate)
    raise RuntimeError(
        "no interpreter with openpyxl found at "
        f"{_PARSER_DIR}/.venv/bin/python. The ipd parser needs its own venv:\n"
        f"  python3 -m venv {_PARSER_DIR}/.venv && "
        f"{_PARSER_DIR}/.venv/bin/pip install -e {_PARSER_DIR}")


def _run_ipd_parse(out: pathlib.Path) -> pathlib.Path:
    """Run a REAL `ipd-parse` against the fixture workbook into `out`, write the
    `.workbook_source.json` sidecar `ActuaryPage._resolve_workbook` looks for (see
    that module's docstring for why the sidecar convention exists: real `ipd-parse`
    does not itself record the source workbook's location), and return the shard
    directory.

    Factored out of the `parse_dir` fixture below (Task 6) so `deliver_rate_program_
    to_designer` -- which the designer-assembly test does not request a `parse_dir`
    fixture into, by the test's own signature -- can obtain the SAME real tree
    without a fixture-scoped `tmp_path_factory`. Both callers run the identical
    `ipd-parse` invocation; only the destination directory differs.
    """
    if not _WORKBOOK.is_file():
        raise RuntimeError(f"fixture workbook missing: {_WORKBOOK}")
    proc = subprocess.run(
        [_parser_python(), "-m", "ipd.parse_cli", "--workbook", str(_WORKBOOK),
         *_PARSE_ARGS, "--out", str(out)],
        capture_output=True, text=True,
        env={"PYTHONPATH": str(_PARSER_DIR / "src"), "PATH": "/usr/bin:/bin"})
    assert proc.returncode == 0, f"ipd-parse failed:\n{proc.stdout}\n{proc.stderr}"
    shards = out / "L" / "WI" / "1.0"
    assert shards.is_dir(), f"ipd-parse wrote no {shards.relative_to(out)}"

    (shards / _WORKBOOK_SIDECAR_NAME).write_text(
        json.dumps({"workbook_path": str(_WORKBOOK)}))
    return shards


@pytest.fixture(scope="session")
def parse_dir(tmp_path_factory):
    """A REAL `ipd-parse` output tree for the fixture workbook, PLUS the
    `.workbook_source.json` sidecar `ActuaryPage._resolve_workbook` looks for
    (see that module's docstring for why the sidecar convention exists: real
    `ipd-parse` does not itself record the source workbook's location).

    Session-scoped: one parse serves every test in this suite; the shape it
    produces (`L/WI/1.0/` with a `risk-value-tables/` subdirectory) is exactly
    what a top-level-only directory scan would silently miss.
    """
    return _run_ipd_parse(tmp_path_factory.mktemp("parse"))


# ---------------------------------------------------------------------------
# Task 6: deliver_rate_program_to_designer -- the designer's receive leg.
# ---------------------------------------------------------------------------

def deliver_rate_program_to_designer(devctl, two_wallets) -> None:
    """Bring up wallet B holding `product_designer_role`, then land a REAL,
    schema-valid, edge-linked `rate_program_attestation` in its own registry --
    genuinely admitted through B's own Kevery/Tevery/Verifier, never faked.

    Uses ONLY wallet B. Tasks 4 and 5 already prove the CUO-declares
    (`declare_mandate_via_ui`) and actuary-watches-and-attests
    (`open_vault_holding_actuary_role` + `watch_cuo_mandate_via_peer` + a live
    attest) legs for real, through genuine UI, in genuine separate wallet
    processes. Re-driving either a second time here would prove nothing new
    about the DESIGNER surface this task owns, and would multiply this
    delivery's cross-process/dialog-reopening surface (a THIRD "Add Peer"
    pairing, a SECOND "Accept Credential Issuance" cycle) for zero additional
    coverage. So `_build_test_admin`'s SAME synthetic party (extended, see its
    own docstring) stands in for the CUO and the actuary too here, minting a
    `product_mandate` and an NI2I-edged `rate_program_attestation` through the
    SAME real keripy issuance machinery (real registries, real TELs, real
    schema validation) `open_vault_holding_cuo_role`/`open_vault_holding_
    actuary_role` already use to grant role credentials.

    Delivery is split by TARGETING, not by credential type:

    - `product_designer_role` is TARGETED (the gate credential) -- delivered
      as a real IPEX grant, admitted through the SAME file-based Accept flow
      Task 4/5's role helpers use (`_expose_and_export` -> pair -> registry
      TEL over the wire -> "Accept Credential Issuance" -> Admit).
    - `product_mandate` and `rate_program_attestation` are BOTH untargeted
      (neither schema's `a` block has an `i` -- see `cuo/page.py`'s and
      `actuary/page.py`'s own module docstrings) -- delivered as bare ACDC
      messages over the SAME peer connection, the mechanic `directing.py`'s
      `vry=self.verifier` fix (Task 5) makes land at all and
      `sitecustomize.py`'s mandate-export hook (patch 5) already mirrors for
      wallet A. No second grant, no second Accept-dialog cycle, and no risk
      of `AcceptGrantDialog`'s own not-destroyed-on-close reopening hazard
      (Task 5 finding 3, `ViewIdentifierDialog`/`AddPeerDialog`'s sibling) --
      untargeted credentials never needed IPEX in the first place; the
      micro-app template's `on_rate_program_received` reaction names `grant`
      as ONE valid transport, not the only one, and `ProductDesignerPage`
      itself is transport-agnostic (it scans `reger` for anything schema-
      matching and `saved`, whichever way it arrived).

    ORDERING IS LOAD-BEARING. Everything is minted and both delivery streams
    are built as plain bytes BEFORE any bytes cross the wire, then sent in
    this order:

    1. Pair B with the admin's peer-OOBI blob, exported AFTER every mint
       below completes -- so ONE pairing carries the admin's COMPLETE KEL
       (every registry-inception and credential-issuance `ixn`), avoiding any
       need to re-pair for each later event (mirrors `open_vault_holding_
       cuo_role`'s own "export AFTER issuance" rule).
    2. Push the registry + credential TELs for ALL THREE credentials in one
       stream (harmless to deliver early; TEL processing needs no schema).
    3. Admit the `product_designer_role` grant via the file-based Accept
       flow. This is what constructs `ProductDesignerPage` (the gate opening
       registers it) and, via its own `__init__`, pins `product_mandate`'s
       and `rate_program_attestation`'s schemas into B's `hby.db.schema`.
    4. ONLY NOW push the mandate's and the attestation's own bare ACDC + their
       SealSourceTriples anchoring proof. Pushing them before step 3 would
       park them in `reger.mse` (missing-schema escrow) -- and NOTHING pumps
       `Verifier.processEscrows()` on the peer-connection path
       (`directing.py`'s own `escrowDo` only re-drives `kevery`/`tvy`,
       measured, not assumed), so an out-of-order push would sit escrowed
       forever rather than eventually landing.
    """
    b = two_wallets["b"]

    open_test_vault_via_ui(devctl, b["sock"], name="designervault")
    create_aid_via_ui(devctl, b["sock"], alias="designer")
    designer_port = free_port()
    from tests.integration.peer.conftest import (
        import_peer_blob_via_ui, set_peer_mode_via_ui,
    )
    set_peer_mode_via_ui(devctl, b["sock"], port=designer_port)
    designer_blob = _expose_and_export(devctl, b["sock"], "designer")

    admin_hby, admin_hab, admin_rgy = _build_test_admin()
    try:
        from hio.base import doing
        from keri.core import Codens, Counter
        from keri.kering import Vrsn_1_0
        from locksmith.peer.cesr_blob import export_peer_blob, import_peer_blob
        from locksmith.peer.publishing import PublishPeerRoleDoer

        designer_pre = import_peer_blob(admin_hby, designer_blob)

        publish_doer = PublishPeerRoleDoer(
            hby=admin_hby, hab=admin_hab,
            url="tcp://127.0.0.1:1/", signal_bridge=None, allow=True,
        )
        doing.Doist(limit=2.0, tock=0.03125, real=False).do(doers=[publish_doer])

        from keri_serviceaid.providers import frame_grant_for, issue_credential

        # -- product_designer_role: TARGETED, the gate credential -----------
        pd_said = issue_credential(
            admin_hby, admin_hab, admin_rgy,
            schema_said=PD_ROLE_SCHEMA_SAID, recipient=designer_pre,
            attributes={}, registry_name=PD_ROLE_SCHEMA_SAID,
        )
        _pd_grant_said, pd_grant_raw = frame_grant_for(
            admin_hby, admin_hab, admin_rgy,
            credential_said=pd_said, recipient=designer_pre, return_raw=True,
        )

        # -- product_mandate: UNTARGETED, the scope the program is written for.
        # Mirrors declare_mandate_via_ui's own payload shape (cuo/page.py's
        # _build_payload) -- a real, schema-valid mandate, just minted here
        # rather than through wallet A's own UI (see this function's own
        # docstring for why).
        mandate_said = issue_credential(
            admin_hby, admin_hab, admin_rgy,
            schema_said=PRODUCT_MANDATE_SCHEMA_SAID, recipient=None,
            attributes={
                "line_of_business": "auto",
                "jurisdiction": "US-UT",
                "coverages": ["BI", "PD"],
                "window_opens": "2027-01-01",
                "window_closes": "2027-12-31",
                "thesis": "Rate adequacy restoration.",
            },
            registry_name=PRODUCT_MANDATE_SCHEMA_SAID,
        )

        # -- rate_program_attestation: UNTARGETED, NI2I-edged to the mandate.
        # A REAL ipd-parse output tree (not the session `parse_dir` fixture --
        # this test's own signature does not request it, see _run_ipd_parse's
        # docstring), so the manifest SAID genuinely commits to parsed shard
        # bytes and the source workbook's own bytes, exactly like
        # ActuaryPage.load_parse computes.
        parse_root = pathlib.Path(tempfile.mkdtemp(prefix="designer_parse_"))
        shards = _run_ipd_parse(parse_root)
        from locksmith.plugins.actuary.page import _build_manifest, _manifest_said

        manifest = _build_manifest(shards, _WORKBOOK)
        manifest_said = _manifest_said(manifest)

        attestation_said = issue_credential(
            admin_hby, admin_hab, admin_rgy,
            schema_said=RATE_PROGRAM_ATTESTATION_SCHEMA_SAID, recipient=None,
            attributes={
                "manifest_said": manifest_said,
                "version": "1.0",
                "filing_date": time.strftime("%Y-%m-%d"),
                "action": "Sandbox",
            },
            registry_name=RATE_PROGRAM_ATTESTATION_SCHEMA_SAID,
            edges={
                "mandate": {
                    "cred_said": mandate_said,
                    "schema_said": PRODUCT_MANDATE_SCHEMA_SAID,
                    "operator": "NI2I",
                },
            },
        )

        # Export admin's blob AFTER every mint above, so pairing carries its
        # COMPLETE KEL in one shot -- see the module docstring.
        admin_blob = export_peer_blob(admin_hab)

        # Leg 1: registry + credential TELs for all three, one combined
        # stream. Registries before their own credentials (clonePreIter
        # iteration order), same shape as open_vault_holding_cuo_role's leg 1.
        tel_stream = bytearray()
        for schema_said, cred_said in (
            (PD_ROLE_SCHEMA_SAID, pd_said),
            (PRODUCT_MANDATE_SCHEMA_SAID, mandate_said),
            (RATE_PROGRAM_ATTESTATION_SCHEMA_SAID, attestation_said),
        ):
            registry = admin_rgy.registryByName(schema_said)
            for msg in admin_rgy.reger.clonePreIter(pre=registry.regk):
                tel_stream.extend(msg)
            for msg in admin_rgy.reger.clonePreIter(pre=cred_said):
                tel_stream.extend(msg)

        # Leg 2 (sent LATER, after product_designer_role is admitted and its
        # page has pinned both schemas -- see the module docstring): the
        # mandate's and the attestation's own bare ACDC + SealSourceTriples
        # anchoring proof, the exact recipe `sitecustomize.py`'s
        # `_export_mandate_artifact` mirrors for wallet A (itself mirroring
        # `keri.vdr.credentialing.sendCredential`).
        bare_acdc_stream = bytearray()
        for cred_said in (mandate_said, attestation_said):
            _, prefixer, seqner, saider = admin_rgy.reger.cloneCred(cred_said)
            creder = admin_rgy.reger.creds.get(keys=(cred_said,))
            atc = bytearray(
                Counter(Codens.SealSourceTriples, count=1, version=Vrsn_1_0).qb64b)
            atc.extend(prefixer.qb64b)
            atc.extend(seqner.qb64b)
            atc.extend(saider.qb64b)
            bare_acdc_stream.extend(bytes(creder.raw))
            bare_acdc_stream.extend(atc)
    finally:
        admin_hby.close()

    import_peer_blob_via_ui(devctl, b["sock"], admin_blob, label="admin")

    with socket.create_connection(("127.0.0.1", designer_port), timeout=5.0) as s:
        s.sendall(bytes(tel_stream))
    time.sleep(1.0)  # let B's Reactant/Tevery land the registries + TELs

    # -- deliver product_designer_role via the SAME file-based Accept flow
    # Task 4/5's role helpers use --------------------------------------------
    fd, cesr_path = tempfile.mkstemp(suffix=".cesr", prefix="pd_role_grant_")
    with os.fdopen(fd, "wb") as f:
        f.write(pd_grant_raw)

    r = devctl(b["sock"], "click", target="vaultNavMenu.credentialsButton")
    assert r.get("ok"), f"expand Credentials submenu: {r}"
    r = devctl(b["sock"], "click", target="vaultNavMenu.receivedCredentialsButton")
    assert r.get("ok"), f"navigate to Received Credentials: {r}"
    r = devctl(b["sock"], "click", target="Accept Credential Issuance")
    assert r.get("ok"), f"open Accept Credential dialog: {r}"
    r = devctl(b["sock"], "wait_for", target="File Path", condition="visible",
              timeout_ms=3000)
    assert r.get("ok"), f"Accept Credential dialog never appeared: {r}"
    r = devctl(b["sock"], "type", target="File Path", text=cesr_path)
    assert r.get("ok"), f"type grant file path: {r}"
    r = devctl(b["sock"], "click", target="Load")
    assert r.get("ok"), f"click Load: {r}"

    r = devctl(b["sock"], "wait_for", target="Admit", condition="visible",
              timeout_ms=5000)
    assert r.get("ok"), f"AcceptGrantDialog never opened: {r}"
    r = devctl(b["sock"], "click", target="Admit")
    assert r.get("ok"), f"click Admit: {r}"

    # The gate reveal + page construction (which pins the mandate/attestation
    # schemas) is asynchronous, same caveat as the "Underwriting"/"Actuarial"
    # polls above.
    deadline = time.time() + 15.0
    last = None
    while time.time() < deadline:
        r = devctl(b["sock"], "click", target="Insurance Product Design")
        if r.get("ok"):
            break
        last = r
        time.sleep(0.5)
    else:
        raise AssertionError(
            f"the Insurance Product Design menu entry never appeared: {last}")

    # -- leg 2: NOW the mandate's and the attestation's own bare ACDCs -------
    with socket.create_connection(("127.0.0.1", designer_port), timeout=5.0) as s:
        s.sendall(bytes(bare_acdc_stream))
    time.sleep(1.0)  # let B's Reactant/Verifier land + chain-verify both
