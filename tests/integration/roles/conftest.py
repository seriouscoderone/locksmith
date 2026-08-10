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
    USURANCE_BRAND, _devctl as devctl, _spawn_wallets, free_port,
    open_test_vault_via_ui, create_aid_via_ui,
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


@pytest.fixture
def two_wallets():
    """Shadows `peer/conftest.py::two_wallets` FOR THIS PACKAGE, with the
    in-process-admin bootstrap armed.

    Every test in this directory issues role credentials from
    `_build_test_admin` and needs `_bootstrap/sitecustomize.py` to re-point the
    gates at it. That bootstrap used to arm itself for the whole pytest process
    — which meant it also armed wallets belonging to `peer/`, silently
    replacing their brand (see `peer/conftest.py::NO_TEST_BOOTSTRAP` for the two
    measurements). It is now off by default and opted into here, where it
    belongs. A same-named fixture in a nearer conftest wins, so these tests keep
    exactly the wallets they had.
    """
    with _spawn_wallets(["a", "b"], prefix="lspeer-", bootstrap=True) as wallets:
        yield {**wallets, "devctl": devctl}


@pytest.fixture
def two_hoa_wallets():
    """Same shadow as `two_wallets` above, for the BRANDED pair."""
    if not USURANCE_BRAND.is_file():
        pytest.skip(
            f"branded wallets need {USURANCE_BRAND}, which is gitignored and "
            f"built on demand. Run: .venv/bin/python scripts/brand_apply.py usurance"
        )
    with _spawn_wallets(["cuo", "actuary"], prefix="lshoa-",
                        brand=USURANCE_BRAND, bootstrap=True) as wallets:
        yield {**wallets, "devctl": devctl}


@pytest.fixture
def four_wallets():
    """Three REAL, separately-driven Locksmith application processes — cuo, actuary,
    designer — the roles this plan built a UI surface for. Generalizes `two_wallets`'s
    (`tests/integration/peer/conftest.py`) spawn loop via the shared `_spawn_wallets`
    context manager rather than copy-pasting it a third/fourth time.

    Named `four_wallets`, not `three_wallets`, because the ARC it drives
    (`test_four_app_arc_via_ui.py`) is the parent design's four-ROLE milestone —
    admin, cuo, actuary, designer. There is deliberately no `"admin"` key here: a
    real fourth Locksmith process CAN issue and Grant a credential through its own
    real UI (`IssueCredentialDialog`/`GrantCredentialDialog` both carry stable
    devctl objectNames already, e.g. `issueCredentialDialog.issueButton`,
    `grantCredentialDialog.grantButton` — this plan never had to add them), but the
    RECEIVING side of that live grant cannot be driven the same way: an incoming
    grant surfaces only on the recipient's Notifications page, and
    `notifications/list.py::_show_accept_grant_dialog` admits it via `QDialog.exec()`
    — a MODAL call that blocks the same Qt-main-thread stack the devctl server
    dispatches commands on. `open_vault_holding_cuo_role`'s own module docstring
    (point 2, above) already measured this exact deadlock for a different dialog
    pair and chose the file-based Accept flow instead for exactly this reason; a
    real admin process granting live over IPEX hits the identical wall on the
    recipient's side, with no file-based alternative available for a LIVE grant (the
    file-based flow admits a `.cesr` the caller already has on disk, not a message
    that just arrived over a socket). So admin's three role grants are driven
    through the SAME in-process issuance recipe `open_vault_holding_cuo_role` /
    `open_vault_holding_actuary_role` / `deliver_rate_program_to_designer` already
    use and this plan already proved (Tasks 4/5/6) — not a fourth spawned process.
    See `test_four_app_arc_via_ui.py`'s own module docstring for exactly how each
    leg of the arc is driven and which one substitution this makes.
    """
    # bootstrap=True: THIS suite is what `_bootstrap/sitecustomize.py` exists
    # for — it re-points the role gates at `_build_test_admin`'s in-process
    # party. It is off by default for every other fixture (see
    # `peer/conftest.py::NO_TEST_BOOTSTRAP`), because merely collecting a file
    # from this package arms it process-wide.
    with _spawn_wallets(["cuo", "actuary", "designer"], prefix="lsroles-",
                        bootstrap=True) as wallets:
        yield {**wallets, "devctl": devctl}


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
    # A peeled HOA has no Identifiers page and so no View Identifier dialog.
    # It exposes the default AID for peer mode automatically
    # (core/direct_transport.py:101 — `ensure_direct_transport`), and Settings
    # renders the resulting OOBI in a readable field, so the HOA path is a read
    # rather than a drive.
    from tests.integration.peer.conftest import landing_target

    if landing_target(devctl, sock) != "vaultNavMenu.identifiersButton":
        # POLLED, not read once. Bringing transport up is asynchronous and
        # self-healing: `_bring_up_direct_transport` finds no hab on its first
        # attempt (the default identifier is still being incepted — the log says
        # `direct_transport.no_hab` and that is EXPECTED) and retries on a
        # QTimer until it succeeds. Only then is the AID exposed and an OOBI
        # renderable. Re-navigates each round because the card rebuilds itself
        # on its own tick.
        deadline = time.time() + 30.0
        while time.time() < deadline:
            devctl(sock, "click", target="vaultNavMenu.settingsButton")
            for candidate in (alias, "default"):
                r = devctl(sock, "get_text",
                           target=f"peerSettingsSection.oobiToken.{candidate}")
                if r.get("ok") and r.get("text"):
                    return r["text"]
            time.sleep(1.0)
        raise AssertionError(
            f"no readable peer OOBI in Settings for {alias!r} or 'default' "
            "after 30s. The HOA auto-exposes its default AID once transport is "
            "up, so this means the retry chain never succeeded — check the "
            "wallet log for 'direct_transport'."
        )

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

    # A peeled HOA has no Credentials page — inbound grants surface on its own
    # Notifications page, whose Accept is non-modal and therefore drivable
    # (vanilla's admit goes through QDialog.exec(), which deadlocks devctl; see
    # accept_grant_via_hoa_notifications). The grant is already on the wire by
    # this point, so the HOA path needs no file at all.
    from tests.integration.peer.conftest import (
        accept_grant_via_hoa_notifications, landing_target,
    )

    if landing_target(devctl, sock) != "vaultNavMenu.identifiersButton":
        # The grant must reach the wallet OVER THE WIRE here. Vanilla hands it
        # over as a file because its admit dialog is modal and the file flow is
        # the only non-blocking way in; the HOA has no such dialog and no
        # Credentials page to load a file from, so the grant is delivered the
        # way a real issuer would deliver it — the same connection the TEL just
        # went down — and surfaces as a notification.
        with socket.create_connection(("127.0.0.1", cuo_port), timeout=5.0) as s:
            s.sendall(bytes(grant_raw))
        accept_grant_via_hoa_notifications(devctl, sock)

        # The admit is SCHEDULED on the vault's doer runner, and the role gate
        # re-evaluates on GateRecheckDoer's own tick — so the plugin section
        # appears some seconds after Accept returns, not synchronously. Poll for
        # it rather than assuming, then enter it exactly as vanilla does.
        deadline = time.time() + 45.0
        while time.time() < deadline:
            r = devctl(sock, "click", target="Underwriting")
            if r.get("ok"):
                # Entering a plugin section PUSHES its submenu, leaving the
                # top-level entries (Settings, where peer mode and Add Peer
                # live) unreachable. Pop it so the caller lands on a usable
                # nav, exactly as the vanilla flow pops the credentials
                # submenu.
                devctl(sock, "click",
                       target="vaultNavMenu.cuoAutoBackButton")
                return
            time.sleep(1.5)
        raise AssertionError(
            "the 'Underwriting' section never appeared after accepting the "
            "cuo_role grant — the credential admitted but the role gate never "
            "opened. Check the wallet log for 'gate' and 'admit'."
        )

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
    `open_vault_holding_cuo_role`).

    HISTORY, same as `_export_current_blob`'s: both dialogs are `LocksmithDialog`
    subclasses, and `LocksmithDialog.close()/accept()` used to HIDE rather than
    destroy, so the first cycle's instances were still in the tree when the second
    opened its own. The two `wait_for` calls below therefore carried `occurrence`
    overrides to reach the live copy, at DIFFERENT indices -- a label-text selector
    matches twice per dialog instance (`_find_widget_any` checks the inner QLabel's
    `.text()` AND `FloatingLabelLineEdit`'s own `_label_text`) while a button-text
    selector matches once.

    `LocksmithDialog.__init__` now sets `WA_DeleteOnClose`
    (`ui/toolkit/widgets/dialogs.py:125`), so the stale instances are gone and every
    one of those indices shifted to 0 -- which made them select nothing, failing as
    "timeout waiting for 'File Path' to be visible". The overrides are removed
    rather than renumbered: there is one dialog alive, so the default is correct and
    stays correct.

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
    # No occurrence override: with WA_DeleteOnClose there is exactly one live
    # AcceptCredentialDialog, so this label-text selector's own pair of matches
    # starts at index 0. (It was occurrence=2, skipping the stale dialog's pair --
    # see the docstring.)
    r = devctl(sock, "wait_for", target="File Path", condition="visible",
              timeout_ms=3000)
    assert r.get("ok"), f"Accept Credential dialog (sibling grant) never appeared: {r}"
    r = devctl(sock, "type", target="File Path", text=cesr_path)
    assert r.get("ok"), f"type grant file path (sibling grant): {r}"
    r = devctl(sock, "click", target="Load")
    assert r.get("ok"), f"click Load (sibling grant): {r}"

    # "Admit" is a plain LocksmithButton (`.text()` only, no label_text
    # duplicate), so ONE match per instance -- and with only the live
    # AcceptGrantDialog in the tree, that match is index 0. (It was occurrence=1,
    # skipping cuo's stale dialog.)
    r = devctl(sock, "wait_for", target="Admit", condition="visible",
              timeout_ms=5000)
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
    submit_mandate_form_via_ui(devctl, sock)


def submit_mandate_form_via_ui(devctl, sock) -> None:
    """Fill and submit the CUO mandate form, through the review dialog, and
    wait for the mandate to actually finish issuing.

    Split out of `declare_mandate_via_ui`, which begins by calling
    `open_vault_holding_cuo_role` — the legacy recipe: an in-process fake admin
    issuing the credential and the test pushing the registry TEL down a raw
    socket. A CUO that got its role the real way (applied, was granted, admitted)
    must not run that again; it would mint a SECOND cuo_role from a different
    issuer. So the form-filling lives here and both paths share one copy.

    Rewritten 2026-08-08 for the schema-driven form. Four things changed and
    each is deliberate:

    * `effectiveWindow` split into `windowOpens`/`windowCloses`, named for the
      schema fields rather than the old fiction of one box holding two.
    * `lineOfBusiness` is a combo, so it is driven with `select`, not `type`.
    * The `is_checked` assertion is gone. The submit button no longer encodes
      validity -- it stays ENABLED while the form is invalid, because
      ux-patterns.md puts required errors on submit and a disabled button makes
      that submit unreachable. Readiness is now asserted by the review dialog
      opening.
    * One extra click: the read-back must be confirmed before anything is
      signed.

    A comma still commits a coverage token, so "BI,PD" keeps working.

    One thing did NOT change, and must not be dropped even though it looks
    redundant with the confirm click: the final wait on
    `cuoMandatePage.declaredBanner`. `mandateReviewDialog.confirm` only STARTS
    the anchor -- `CuoMandatePage._confirm_review` schedules a
    `ServiceaidIssueDoer` on the vault's doer bus and returns immediately; the
    credential is actually issued on later ticks of the Qt/hio event loop, and
    only `_show_declared` (fired off the doer's `credential_issued` event)
    paints the banner and closes the review dialog. Two of this helper's
    callers only get away without waiting for that by accident:
    `watch_cuo_mandate_via_peer` and the admin-grants-both-roles arc each poll
    a slower downstream effect (an exported artifact file, the actuary's
    observed-mandates list) for many seconds afterward, and that poll happens
    to absorb the issuance delay too. `test_cuo_mandate_via_ui.py` has no such
    poll -- it calls this helper and asserts nothing else -- so without this
    wait it would report green even if the mandate never finished issuing at
    all.
    """
    r = devctl(sock, "wait_for", target="cuoMandatePage",
               condition="visible", timeout_ms=5000)
    assert r.get("ok"), r

    r = devctl(sock, "select", target="cuoMandatePage.lineOfBusiness", value="auto")
    assert r.get("ok"), f"choose the line of business: {r}"

    for target, value in (
        ("cuoMandatePage.jurisdiction", "US-UT"),
        ("cuoMandatePage.coverages", "BI,PD"),
        ("cuoMandatePage.windowOpens", "01/01/2027"),
        ("cuoMandatePage.windowCloses", "12/31/2027"),
        ("cuoMandatePage.thesis", "Rate adequacy restoration."),
    ):
        r = devctl(sock, "type", target=target, text=value)
        assert r.get("ok"), (target, r)

    # devctl 0.2.0 refuses a disabled target, so a click that reports ok landed.
    r = devctl(sock, "click", target="cuoMandatePage.submit")
    assert r.get("ok"), f"open the read-back: {r}"

    # The read-back is open once the acknowledgement is there. Waiting on the
    # PRIMARY here would be wrong now: it is deliberately disabled until the
    # acknowledgement is given, so "disabled" no longer means "the form still has
    # errors" -- it is the modal's correct opening state.
    r = devctl(sock, "wait_for", target="mandateReviewDialog.ack",
               condition="visible", timeout_ms=5000)
    assert r.get("ok"), (
        f"the review dialog never opened, so the form still has errors: {r}")

    # Give the acknowledgement, exactly as a CUO must. This is the step that makes
    # the primary reachable at all; the assertion below is what proves the gate is
    # real rather than decorative.
    r = devctl(sock, "click", target="mandateReviewDialog.ack")
    assert r.get("ok"), f"acknowledge before signing: {r}"

    r = devctl(sock, "wait_for", target="mandateReviewDialog.confirm",
               condition="enabled", timeout_ms=5000)
    assert r.get("ok"), (
        f"the acknowledgement did not release the primary: {r}")

    # devctl 0.2.0 refuses a disabled target, so a click that reports ok landed.
    r = devctl(sock, "click", target="mandateReviewDialog.confirm")
    assert r.get("ok"), f"confirm the read-back: {r}"

    r = devctl(sock, "wait_for", target="cuoMandatePage.declaredBanner",
               condition="visible", timeout_ms=10000)
    assert r.get("ok"), f"the mandate never finished issuing after confirm: {r}"


def attest_rate_program_via_ui(devctl, sock, parse_dir) -> None:
    """The actuary loads a REAL `ipd-parse` output tree against the mandate it is
    ALREADY watching, and attests. Extracted from Task 5's own test body
    (`test_actuary_observes_and_attests_via_ui.py`) so Task 8's four-app arc can
    drive the SAME closing leg rather than re-deriving it — that test now calls
    this too, so there is exactly one copy of the load-and-attest recipe. See
    `parse_dir`'s own docstring for why the fixture tree is a genuine `ipd-parse`
    run, never a synthetic stand-in.

    Preconditions (both already true after `open_vault_holding_actuary_role` +
    `watch_cuo_mandate_via_peer`): `sock` is on `actuaryPage`, and exactly one
    mandate has landed in `actuaryPage.observedMandates` by watching — this
    function does not itself grant the actuary role or perform the watch.

    Two devctl API corrections against the plan brief's illustrative snippet,
    confirmed against the INSTALLED `locksmith_ui_tester.server` (not the README,
    which is stale): `get_list_items` returns `{"items": [{"text": ..., "data":
    ...}, ...]}`, not a bare list of strings, so the clicked item's text is
    `items[0]["text"]`; `is_visible` on a target that does not exist returns
    `{"ok": True, "visible": False, "exists": False}`, never `{"ok": False}` —
    the field to assert is `"visible"`, not `"ok"`.
    """
    r = devctl(sock, "wait_for", target="actuaryPage.observedMandates",
               condition="visible", timeout_ms=3000)
    assert r.get("ok"), r

    # The list widget is visible as soon as the page is (it is part of the
    # persistent layout, not gated on having items) — the watch itself is a
    # poll (ActuaryPage's own QTimer, 1s tock), so give it a few cycles rather
    # than trusting a single read the instant "visible" returns.
    #
    # `wait_for`'s own `timeout_ms` is a SERVER-side poll budget; devctl's
    # client socket (tests/integration/peer/conftest.py::_devctl) has an
    # independent, hardcoded 5.0s recv() timeout. Asking the server to poll
    # longer than that races a real TimeoutError on the client side before
    # the server ever gets to answer -- so every wait_for below stays under
    # it, and anything that may genuinely take longer is retried from the
    # test side instead, the same idiom conftest.py's own "Underwriting"/
    # "Actuarial" menu-entry waits use.
    deadline = time.time() + 15.0
    items = []
    while time.time() < deadline:
        r = devctl(sock, "get_list_items", target="actuaryPage.observedMandates")
        assert r.get("ok"), r
        items = r["items"]
        if len(items) == 1:
            break
        time.sleep(0.5)
    assert len(items) == 1, f"observedMandates never settled to exactly one item: {items}"

    r = devctl(sock, "click_list_item", target="actuaryPage.observedMandates",
               text=items[0]["text"])
    assert r.get("ok"), r

    # a real ipd-parse output directory, not a synthetic stand-in
    r = devctl(sock, "type", target="actuaryPage.parseDir", text=str(parse_dir))
    assert r.get("ok"), r
    r = devctl(sock, "click", target="actuaryPage.loadParse")
    assert r.get("ok"), r

    # the manifest SAID and workbook digest are shown as EVIDENCE; no rate table
    r = devctl(sock, "get_text", target="actuaryPage.manifestSaid")
    assert r.get("ok") and r["text"].startswith("E"), r
    r = devctl(sock, "get_text", target="actuaryPage.workbookDigest")
    assert r.get("ok") and r["text"].startswith("E"), r
    assert devctl(sock, "is_visible",
                  target="actuaryPage.rateTable")["visible"] is False, \
        "no rate table may be rendered in any HOA surface"

    # The three the actuary asserts. All schema-required; `version` has no
    # default, so the gate holds until it is given.
    r = devctl(sock, "type", target="actuaryPage.version", text="2027.1")
    assert r.get("ok"), f"name the rate program version: {r}"

    r = devctl(sock, "wait_for", target="actuaryPage.attest",
               condition="enabled", timeout_ms=5000)
    assert r.get("ok"), f"the version did not release the review gate: {r}"

    # The page primary now opens the READ-BACK; it no longer mints. Nothing on
    # the page can reach `vault.extend` any more, which is the point of the gate.
    r = devctl(sock, "click", target="actuaryPage.attest")
    assert r.get("ok"), f"open the attestation read-back: {r}"

    r = devctl(sock, "wait_for", target="attestDrawer.ack",
               condition="visible", timeout_ms=5000)
    assert r.get("ok"), f"the read-back drawer never opened: {r}"

    # Acknowledge, exactly as an actuary must. The assertion below is what proves
    # the gate is real rather than decorative: the confirm is unreachable until
    # this lands.
    r = devctl(sock, "click", target="attestDrawer.ack")
    assert r.get("ok"), f"acknowledge before attesting: {r}"

    r = devctl(sock, "wait_for", target="attestDrawer.confirm",
               condition="enabled", timeout_ms=5000)
    assert r.get("ok"), f"the acknowledgement did not release the confirm: {r}"

    r = devctl(sock, "click", target="attestDrawer.confirm")
    assert r.get("ok"), r

    # See the observedMandates comment above for why this polls in short
    # (client-timeout-safe) hops instead of one long wait_for.
    deadline = time.time() + 15.0
    banner_visible = False
    while time.time() < deadline:
        r = devctl(sock, "wait_for", target="actuaryPage.attestedBanner",
                   condition="visible", timeout_ms=3000)
        if r.get("ok"):
            banner_visible = True
            break
    assert banner_visible, f"attestedBanner never became visible: {r}"


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

    # Same brand split as open_vault_holding_cuo_role: a peeled HOA has no
    # Credentials page, so the grant goes over the wire and is accepted from
    # Notifications (non-modal, hence drivable) instead of via a file dialog.
    from tests.integration.peer.conftest import (
        accept_grant_via_hoa_notifications, landing_target,
    )

    if landing_target(devctl, sock) != "vaultNavMenu.identifiersButton":
        with socket.create_connection(("127.0.0.1", actuary_port), timeout=5.0) as s:
            s.sendall(bytes(grant_raw))
        accept_grant_via_hoa_notifications(devctl, sock)

        # The role gate opens on GateRecheckDoer's tick, not synchronously.
        deadline = time.time() + 45.0
        while time.time() < deadline:
            if devctl(sock, "click", target="Actuarial").get("ok"):
                # Entering a plugin section PUSHES its submenu, leaving the
                # top-level entries (Settings, where peer mode and Add Peer
                # live) unreachable. Pop it so the caller lands on a usable
                # nav, exactly as the vanilla flow pops the credentials
                # submenu.
                devctl(sock, "click",
                       target="vaultNavMenu.actuaryAutoBackButton")
                return
            time.sleep(1.5)
        raise AssertionError(
            "the 'Actuarial' section never appeared after accepting the "
            "actuary_role grant — check the wallet log for 'gate' and 'admit'."
        )

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

    HISTORY, because it explains why this reads so plainly now. This helper used
    to pass `occurrence=1` to its `wait_for` calls: `ViewIdentifierDialog`'s Close
    button hid rather than destroyed it, so a SECOND "View" open left TWO
    `viewIdentifierDialog.*`-named widget sets alive at once, and the two devctl
    finders disagreed about them -- `wait_for` uses `_find_widget_any`, which does
    NOT filter by visibility, so the live dialog was match 1, while
    `is_checked`/`select`/`get_text` use the visible-only `_find_widget`, where it
    was match 0.

    `LocksmithDialog.__init__` now sets `WA_DeleteOnClose`
    (`ui/toolkit/widgets/dialogs.py:125`), which `ViewIdentifierDialog` inherits,
    so the stale copy no longer exists and BOTH finders see exactly one widget.
    Which turned `occurrence=1` into a selector that resolves nothing -- the
    "View Identifier dialog never opened for 'cuo'" failure. The indices are gone
    rather than renumbered: with one dialog alive there is nothing to index."""
    # Peeled HOA: no Identifiers page, no View Identifier dialog. Its own OOBI
    # is rendered in Settings and read the same way _expose_and_export reads it,
    # so both callers share one brand split.
    from tests.integration.peer.conftest import landing_target

    if landing_target(devctl, sock) != "vaultNavMenu.identifiersButton":
        return _expose_and_export(devctl, sock, alias)

    devctl(sock, "click_row_action", row_text=alias, action="View")
    r = devctl(sock, "wait_for", target="viewIdentifierDialog.aidField",
              condition="visible", timeout_ms=3000)
    assert r.get("ok"), f"View Identifier dialog never opened for {alias!r}: {r}"

    r = devctl(sock, "is_checked", target="viewIdentifierDialog.exposeToggle")
    assert r.get("ok"), r
    if not r["checked"]:
        # Should never fire in practice -- the alias was already exposed by
        # _expose_and_export. Fail loudly rather than clicking: this helper's
        # contract is the already-exposed case, and clicking the toggle here
        # would turn exposure OFF.
        raise AssertionError(
            f"{alias!r} was not already exposed -- _export_current_blob only "
            "handles the already-exposed case")

    r = devctl(sock, "select", target="viewIdentifierDialog.oobiRoleCombo",
              value="Peer (offline)")
    assert r.get("ok"), r
    r = devctl(sock, "wait_for", target="viewIdentifierDialog.oobiTokenLabel",
              condition="visible", timeout_ms=3000)
    assert r.get("ok"), r
    text = devctl(sock, "get_text",
                  target="viewIdentifierDialog.oobiTokenLabel")["text"]

    # Close it, and mean it. This used to be skipped because `_op_click` takes no
    # occurrence and would have resolved the stale copy; with WA_DeleteOnClose the
    # Close actually DESTROYS the dialog, so there is nothing to be ambiguous
    # about -- and a dialog left open is what made the next open ambiguous.
    # `target="Close"` is a label-text selector (the button carries no
    # objectName), matching tests/integration/peer/conftest.py:600. Not asserted
    # there or here: some dialog variants close on Escape instead, and the next
    # interaction fails loudly if this one is still modal.
    devctl(sock, "click", target="Close")
    return text


def _import_peer_blob_second_time(devctl, sock, blob: str, label: str | None = None) -> None:
    """A wallet's SECOND "Add Peer" pairing (`b["sock"]` here already paired with
    "admin" during `open_vault_holding_actuary_role`).

    This was a near-copy of `tests.integration.peer.conftest.import_peer_blob_via_ui`
    for exactly one reason: `AddPeerDialog` was not destroyed on close, so a second
    open left a live-vs-stale pair and the two `wait_for` calls needed
    `occurrence=1` to reach the live one, which the shared helper does not offer.

    `AddPeerDialog` now sets `WA_DeleteOnClose` (`ui/vault/peers/add_dialog.py:48`),
    so there is no stale copy and no index to pass. It delegates to the shared
    helper, which is strictly better than this copy was: it probes before clicking
    and retries, because the peer settings card rebuilds on its own tick and a
    click can land on a button being replaced.

    Kept as a named wrapper rather than deleted so the call sites keep saying
    "second pairing" -- and so the navigation tail below, which the shared helper
    has no reason to do, stays with the caller that needs it.
    """
    from tests.integration.peer.conftest import import_peer_blob_via_ui

    import_peer_blob_via_ui(devctl, sock, blob, label=label)

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
              "--filing-date", "2022-05-01", "--action", "sandbox"]

#: A parse now answers a SPECIFIC product mandate: `ipd-parse` replaced
#: `--version` with `--product-mandate <SAID>` and writes to
#: `<out>/<lob>/<juris>/<said>` instead of `<out>/<lob>/<juris>/<version>`
#: (ugard `insurance-product/parser/src/ipd/cli/parse.py`). The harness
#: still passed `--version 1.0`, so both tests that use `parse_dir` errored
#: before spawning a single wallet:
#:     ipd-parse: error: the following arguments are required: --product-mandate
#: Standalone callers pass this placeholder; the four-window arc passes the SAID
#: the CUO actually declared, which is the point of the CLI change.
_PLACEHOLDER_MANDATE_SAID = "EAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
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


def _run_ipd_parse(out: pathlib.Path,
                   product_mandate: str = _PLACEHOLDER_MANDATE_SAID) -> pathlib.Path:
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
        # `ipd.cli.parse`, not the retired `ipd.parse_cli`: ugard moved the CLI
        # under a `cli/` package (its [project.scripts] is the source of truth:
        # `ipd-parse = "ipd.cli.parse:main"`). The old path failed as
        # "No module named ipd.parse_cli" during FIXTURE SETUP, which reads as
        # an environment problem and hid the whole four-window arc test.
        [_parser_python(), "-m", "ipd.cli.parse", "--workbook", str(_WORKBOOK),
         *_PARSE_ARGS, "--product-mandate", product_mandate,
         "--out", str(out)],
        capture_output=True, text=True,
        env={"PYTHONPATH": str(_PARSER_DIR / "src"), "PATH": "/usr/bin:/bin"})
    assert proc.returncode == 0, f"ipd-parse failed:\n{proc.stdout}\n{proc.stderr}"
    shards = out / "L" / "WI" / product_mandate
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


# ---------------------------------------------------------------------------
# The REAL issuing side: a running vanilla admin, driven through its own UI.
#
# Everything above this line issues role credentials from `_build_test_admin`,
# an in-process KERI party. That was the right call while a live grant could not
# be admitted (`test_four_app_arc_via_ui`'s docstring measures the deadlock: a
# vanilla recipient's Notifications page admits through three `QDialog.exec()`
# calls, which block the very Qt main thread devctl dispatches on). A BRANDED
# HOA has no such modal — `hoaNotifications.acceptButton` calls `_accept(row)`
# directly — so vanilla-issuer -> HOA-recipient is the combination that works,
# and these helpers drive it.
# ---------------------------------------------------------------------------

def _select_combo_by_prefix(devctl, sock, target: str, prefix: str,
                            limit: int = 16) -> str:
    """Select the first combo entry whose visible text starts with `prefix`.

    `select` matches a `value` by EXACT text, and these combos render
    "<alias> (<44-char AID>)" — an AID the caller does not have. Walking the
    indices and reading back `selected_text` is the only way to pick a row by
    the part that is knowable.

    It also guards devctl's sharpest edge: `select` does NOT range-check
    `index`. Selecting past the end returns ok with `selected_text: ''`, which
    is how a Grant went out with `recipient=None` and failed downstream in
    `ServiceaidGrantDoer` with "expected str instance, NoneType found".
    """
    seen = []
    for i in range(limit):
        r = devctl(sock, "select", target=target, index=i)
        text = (r.get("selected_text") or "") if r.get("ok") else ""
        if not text:
            break                     # past the end — see the docstring
        seen.append(text)
        if text.startswith(prefix):
            return text
    raise AssertionError(
        f"no entry starting with {prefix!r} in {target}; saw {seen}")


def load_issuable_schema_via_admin_ui(devctl, sock, schema_path: pathlib.Path) -> str:
    """Load a schema into a VANILLA wallet AND create its issuance registry.

    Returns the SAID the dialog extracted, so the caller can assert it is the
    one it meant to load rather than trusting the file path.

    The registry is not optional: `IssueCredentialDialog._populate_schema_dropdown`
    skips every schema without one (`if not rgy.registryByName(said): continue`),
    so a schema loaded with the box unchecked is present, listed on the Schemas
    page as `Issuable: No`, and silently absent from the Issue dialog.
    """
    devctl(sock, "click", target="vaultNavMenu.credentialsButton")
    devctl(sock, "click", target="vaultNavMenu.schemaButton")
    r = devctl(sock, "click", target="Add Schema")
    assert r.get("ok"), f"open Add Schema: {r}"
    r = devctl(sock, "wait_for", target="File", condition="visible",
               timeout_ms=5000)
    assert r.get("ok"), f"Add Schema dialog never appeared: {r}"

    devctl(sock, "click", target="File")
    r = devctl(sock, "type", target="File Path", text=str(schema_path))
    assert r.get("ok"), f"type schema path: {r}"
    # The SAID is extracted from the file by a textChanged handler; it is the
    # dialog's own read of what it is about to load.
    deadline, said = time.time() + 10.0, ""
    while time.time() < deadline:
        said = (devctl(sock, "get_text", target="SAID").get("text") or "").strip()
        if said:
            break
        time.sleep(0.5)
    assert said.startswith("E"), (
        f"the dialog extracted no SAID from {schema_path} — Load would fail "
        f"with 'Missing field: SAID'")

    devctl(sock, "click", target="Use for Credential Issuance")
    r = devctl(sock, "select", target="Issuer", index=1)
    assert r.get("ok") and r.get("selected_text"), (
        f"no issuer identifier to create the registry under: {r}")
    r = devctl(sock, "click", target="Load Schema")
    assert r.get("ok"), f"click Load Schema: {r}"

    # The dialog closing IS the completion signal — `LoadSchemaDoer` emits
    # `schema_loaded` and `AddSchemaDialog` accepts. Deterministic and fast:
    # measured at well under a second for an unwitnessed issuer.
    #
    # This used to poll the Schemas table for a row containing `said`, which
    # could NEVER match: SAID is a HIDDEN key on that table (its visible columns
    # are Schema Name / Version / Issuable / Issuer / Description), exactly as on
    # the Issued list. So the loop burned its full 30s budget and then fell
    # through to `return said` anyway — a silent 30s per schema, twice per run,
    # proving nothing. It was visible only as an unexplained pause on screen.
    r = devctl(sock, "wait_for", target="File", condition="hidden",
               timeout_ms=30000)
    assert r.get("ok"), (
        f"Add Schema dialog never closed — the load failed: {r}")

    # And confirm the registry actually exists, which is the whole point of
    # ticking the box: `IssueCredentialDialog` skips every schema without one.
    devctl(sock, "click", target="vaultNavMenu.schemaButton")
    deadline, rows = time.time() + 15.0, None
    while time.time() < deadline:
        r = devctl(sock, "get_table_rows", target="table.CredentialSchemas")
        rows = r.get("rows")
        if rows and any(row.get("Issuable") == "Yes" for row in rows):
            return said
        time.sleep(0.5)
    raise AssertionError(
        f"{schema_path.name} loaded but no schema on the page reports "
        f"Issuable=Yes, so the registry was not created. The Issue dialog "
        f"skips every schema without one and would silently not list it. "
        f"Rows: {rows}")


def issue_and_grant_role_via_admin_ui(devctl, sock, *, schema_prefix: str,
                                      recipient_prefix: str) -> None:
    """Issue `schema_prefix` to `recipient_prefix` and GRANT it live over IPEX.

    Both legs run in the admin's real UI: `IssueCredentialDialog` mints the ACDC
    into the schema's registry, then the Issued row's Grant action sends it.
    Grant defaults to "Send" — a live exn to the recipient's peer endpoint —
    not the file-based Save path the older helpers rely on.
    """
    devctl(sock, "click", target="vaultNavMenu.credentialsButton")
    devctl(sock, "click", target="vaultNavMenu.issuedCredentialsButton")
    r = devctl(sock, "click", target="Issue Credential")
    assert r.get("ok"), f"open Issue Credential: {r}"
    r = devctl(sock, "wait_for", target="issueCredentialDialog.schemaCombo",
               condition="visible", timeout_ms=5000)
    assert r.get("ok"), f"Issue dialog never appeared: {r}"

    _select_combo_by_prefix(devctl, sock, "issueCredentialDialog.schemaCombo",
                            schema_prefix)
    _select_combo_by_prefix(devctl, sock, "issueCredentialDialog.recipientCombo",
                            recipient_prefix)
    r = devctl(sock, "click", target="issueCredentialDialog.issueButton")
    assert r.get("ok"), f"click Issue: {r}"
    r = devctl(sock, "wait_for", target="issueCredentialDialog.schemaCombo",
               condition="hidden", timeout_ms=30000)
    assert r.get("ok"), f"Issue dialog never closed — issuance failed: {r}"

    devctl(sock, "click", target="vaultNavMenu.issuedCredentialsButton")
    r = devctl(sock, "click_row_action", row_text=schema_prefix, action="Grant")
    assert r.get("ok"), f"Grant row action for {schema_prefix!r}: {r}"
    r = devctl(sock, "wait_for", target="grantCredentialDialog.grantButton",
               condition="visible", timeout_ms=5000)
    assert r.get("ok"), f"Grant dialog never appeared: {r}"

    # Do NOT select here. Unlike the Issue dialog, this combo has no
    # "Select a recipient..." placeholder row: `_populate_recipients` fills it
    # from index 0 and pre-selects the credential's OWN recipient. Selecting
    # index 1 picked a row past the end, devctl reported ok with empty text,
    # and the grant went out with `recipient=None`.
    pre = devctl(sock, "get_text", target="grantCredentialDialog.recipientCombo")
    assert (pre.get("text") or "").startswith(recipient_prefix), (
        f"Grant dialog pre-selected {pre.get('text')!r}, not {recipient_prefix!r}")

    r = devctl(sock, "click", target="grantCredentialDialog.grantButton")
    assert r.get("ok"), f"click Grant: {r}"
    r = devctl(sock, "wait_for", target="grantCredentialDialog.grantButton",
               condition="hidden", timeout_ms=30000)
    assert r.get("ok"), f"Grant dialog never closed — the send failed: {r}"


def request_role_via_hoa_ui(devctl, sock, role_id: str,
                            timeout_s: float = 30.0) -> None:
    """The HOA ASKS for a role, from its own onboarding home.

    This is the real trigger, and the reason the admin has anything to respond
    to. These roles are APPLY-MODE (`role.onboarding.apply_mode` — no
    `request_micro_app_said`), so there is no form and no
    `onboarding.submitButton`: `OnboardingHomePage._on_card_request` calls
    `on_apply(role_id)`, which derives the apply plan, seeds the role's schemas,
    and sends a bare IPEX apply to the authority the EGF selects.
    (`onboarding.submitButton` belongs to the FORM path, for roles that carry a
    submit-application micro-app.)

    The end state is the card losing its Request button — a PENDING card renders
    no button at all (`RoleCard._build`), so this is exact rather than a sleep.
    """
    devctl(sock, "click", target="vaultNavMenu.homeButton")
    target = f"roleCard.requestButton.{role_id}"
    r = devctl(sock, "wait_for", target=target, condition="visible",
               timeout_ms=15000)
    assert r.get("ok"), (
        f"no Request button for role {role_id!r} on the onboarding home: {r}. "
        f"Either the EGF does not carry that role, or the card is not in the "
        f"AVAILABLE state (an already-granted role renders Open, not Request).")

    r = devctl(sock, "click", target=target)
    assert r.get("ok"), f"click Request for {role_id!r}: {r}"

    r = devctl(sock, "wait_for", target=target, condition="hidden",
               timeout_ms=int(timeout_s * 1000))
    assert r.get("ok"), (
        f"role {role_id!r} never left AVAILABLE after Request — the apply was "
        f"not sent. Check the wallet log for 'apply' and 'peer.send'.")


def wait_for_admin_notifications(devctl, sock, *, count: int,
                                 timeout_s: float = 60.0) -> list:
    """Block until the admin's Notifications page shows `count` rows.

    An IPEX *apply* is not a credential grant, so it never appears under
    Received Credentials — it surfaces here. Asserting on it is what makes the
    request leg a real cross-process claim rather than a local UI state change:
    the applicant's card going to "Requested" only proves the applicant sent
    something.
    """
    # Two different doors. A peeled HOA has a nav entry; a VANILLA wallet has
    # only the toolbar button (`window._toolbar_config` sets
    # show_notifications_button, and the nav has no such item). Try the nav
    # first, fall back to the toolbar, and fail loudly if neither opens.
    deadline, rows, opened = time.time() + timeout_s, None, False
    while time.time() < deadline:
        # RE-OPEN each pass. The page renders from a snapshot taken when it is
        # shown, so a row that lands after that is not picked up — polling
        # `get_table_rows` on an already-open page reads the same stale render
        # forever. Measured: two applies delivered, table still reporting zero
        # rows sixty seconds later.
        for target in ("vaultNavMenu.notificationsButton",
                       "toolbar.notificationsButton"):
            if devctl(sock, "click", target=target).get("ok"):
                opened = True
                break
        rows = (devctl(sock, "get_table_rows",
                       target="table.Notifications").get("rows")) or []
        if len(rows) >= count:
            return rows
        time.sleep(1.0)
    if not opened:
        raise AssertionError(
            "could not reach the Notifications page by either door "
            "(vaultNavMenu.notificationsButton / toolbar.notificationsButton)")
    raise AssertionError(
        f"the admin saw {len(rows or [])} of {count} expected applications. "
        f"Each HOA reported its apply as sent, so this is the receiving side: "
        f"check the admin log for 'peer.recv.delivered' and 'New notification "
        f"detected'. Rows: {rows}")
