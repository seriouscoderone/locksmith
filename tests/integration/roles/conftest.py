# -*- encoding: utf-8 -*-
"""Fixtures for the role-surface UI tests.

Reuses tests/integration/peer/conftest's wallet-spawning machinery verbatim: isolated
HOME per wallet, one devctl socket each, offscreen Qt, and the PYTHONPATH prepend that
stops the shared venv's editable .pth from silently testing the main checkout instead
of the tree under test.
"""
from __future__ import annotations

import os
import pathlib
import socket
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
_existing_pp = os.environ.get("PYTHONPATH")
os.environ["PYTHONPATH"] = (
    f"{_BOOTSTRAP_DIR}{os.pathsep}{_existing_pp}" if _existing_pp else _BOOTSTRAP_DIR
)


def _build_test_admin():
    """A real in-process KERI party: v1-pinned Habery + single unwitnessed
    AID + Regery — the same shape `test_multi_role_e2e.py`'s `_make_party`
    and `test_carrier_gate_e2e.py`'s admin/DOI parties use. Never touches a
    real vault or passcode."""
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

    # The ISSUER's own Habery must resolve the schema too
    # (Credentialer.validate), independent of the recipient wallet's own
    # copy pinned via sitecustomize.py's on_vault_opened patch.
    import json

    from keri.core import scheming
    from keri.kering import Kinds

    sad = json.loads(_CUO_ROLE_SCHEMA_PATH.read_text())
    schemer = scheming.Schemer(sed=sad, kind=Kinds.json)
    assert schemer.said == CUO_ROLE_SCHEMA_SAID, (
        f"bundle schema {CUO_ROLE_SCHEMA_SAID} does not verify")
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
) -> None:
    """Bring up a real vault + AID at `sock`, then make it GENUINELY hold an
    active, chain-verified `cuo_role` credential. See the module docstring
    above for the full design."""
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
        admin_hby.close()

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
