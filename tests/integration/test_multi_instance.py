"""End-to-end integration tests for single-instance-per-vault behavior.

Drives two real Locksmith processes that SHARE one config/data base
(same HOME) but listen on DISTINCT dev-control sockets, exactly the way
two instances launched by the same user on one machine would behave.
Every action AND every observation goes through real, user-visible
widgets via the generic dev-control harness (Cypress-like): no
feature-coupled RPC shortcuts. "Is a vault open here?" is read off the
real UI — ``vaultNavMenu.identifiersButton`` is visible only when a
vault is open. "WHICH vault?" is read off the visible toolbar label
``toolbar.vaultNameLabel`` (the open vault's name, or "" when none).

Covered:

1. focus-existing / no-duplicate-open
   Instance #1 opens vault "shared". Instance #2, looking at the same
   on-disk vault set, must NOT be able to duplicate-open it: the drawer
   surfaces the vault as already running in another instance and the
   real user action there (Switch to) raises the owner rather than
   opening a second copy. We assert instance #2 never ends up holding
   the vault (its identifiers nav button stays hidden and its toolbar
   vault-name label stays ""). As a belt-and-braces check we also
   exercise the Open path directly when the drawer still shows it (race
   window) and confirm the claim is denied.

2. switch-in-place
   A single instance opens vault A, then vault B, and ends up on B —
   one instance reused, no second process.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from tests.integration.peer.conftest import (
    REPO_ROOT,
    _devctl,
    _install_plugins,
    _wait_for_socket,
    open_test_vault_via_ui,
)

pytestmark = pytest.mark.integration


def _start_wallet_with_socket(home: Path, log_path: Path, socket_path: Path):
    """Spawn a wallet sharing ``home`` but with its OWN control socket.

    Same launch mechanics as the peer fixture's ``_start_wallet``
    (``python -m locksmith.main`` with HOME + offscreen Qt), with one
    twist: override LOCKSMITH_CONTROL_SOCKET so two processes under the
    SAME HOME don't fight over one socket (the dev-control server's
    default socket lives under HOME, which would collide for a shared
    HOME). Uses ``sys.executable`` — the venv interpreter running the
    test, which has locksmith installed editable — so it works from a
    git worktree that has no local ``.venv``.
    """
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["LOCKSMITH_CONTROL_SOCKET"] = str(socket_path)
    return subprocess.Popen(
        [sys.executable, "-m", "locksmith.main"],
        env=env,
        stdout=log_path.open("w"),
        stderr=subprocess.STDOUT,
        cwd=str(REPO_ROOT),
    )


@pytest.fixture
def two_instances_shared_base():
    """Two wallet processes sharing ONE config base (HOME), distinct sockets.

    Same spawn/teardown shape as the peer ``two_wallets`` fixture, except
    both processes get the same HOME so they see the same vaults on disk
    and compete for the same per-vault coordination socket. Short /tmp
    prefix keeps the UDS path under macOS's 104-char limit.
    """
    root = Path(tempfile.mkdtemp(prefix="lsinst-", dir="/tmp"))
    home = root / "shared_home"
    home.mkdir()
    _install_plugins(home)

    log_1 = root / "i1.log"
    log_2 = root / "i2.log"
    sock_1 = root / "i1.sock"
    sock_2 = root / "i2.sock"

    proc_1 = _start_wallet_with_socket(home, log_1, sock_1)
    proc_2 = _start_wallet_with_socket(home, log_2, sock_2)
    try:
        _wait_for_socket(sock_1)
        _wait_for_socket(sock_2)
        yield {
            "i1": {"home": home, "log": log_1, "sock": sock_1, "proc": proc_1},
            "i2": {"home": home, "log": log_2, "sock": sock_2, "proc": proc_2},
            "devctl": _devctl,
        }
    finally:
        for proc in (proc_1, proc_2):
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        shutil.rmtree(root, ignore_errors=True)


def _single_instance():
    """One wallet process with an isolated HOME + its own socket.

    Used by the switch-in-place test, which only needs a single instance.
    """
    root = Path(tempfile.mkdtemp(prefix="lsinst1-", dir="/tmp"))
    home = root / "home"
    home.mkdir()
    _install_plugins(home)
    log = root / "i.log"
    sock = root / "i.sock"
    proc = _start_wallet_with_socket(home, log, sock)
    _wait_for_socket(sock)
    return root, {"home": home, "log": log, "sock": sock, "proc": proc}


def _refresh_drawer(devctl, sock: Path) -> None:
    """Force the vault drawer to re-read the on-disk vault set + per-vault
    state. Navigating to the Plugins page (a real toolbar click) runs
    ``show_drawer_widgets`` → ``_refresh_vault_list`` the same way a user
    clicking around the app would. Then open the drawer.
    """
    r = devctl(sock, "click", target="toolbar_plugins_button")
    assert r.get("ok"), f"navigate to plugins (refresh drawer): {r}"
    # Open the drawer via the toolbar Vaults button.
    r = devctl(sock, "click", target="toolbar.vaultsButton")
    assert r.get("ok"), f"open vault drawer: {r}"


def _vault_open(devctl, sock: Path) -> bool:
    """Real-UI signal for 'a vault is open in this instance'.

    ``vaultNavMenu.identifiersButton`` is a nav button that exists/visible
    only while a vault is open, so its visibility is a faithful proxy for
    instance-holds-a-vault.
    """
    r = devctl(sock, "is_visible", target="vaultNavMenu.identifiersButton")
    return bool(r.get("visible"))


def _open_vault_name(devctl, sock: Path) -> str:
    """WHICH vault is open in this instance, read off the visible toolbar
    label ``toolbar.vaultNameLabel`` (the vault's name, or "" when none).
    """
    r = devctl(sock, "get_text", target="toolbar.vaultNameLabel")
    assert r.get("ok"), f"read toolbar.vaultNameLabel: {r}"
    return r.get("text", "")


def test_second_instance_cannot_duplicate_open_vault(two_instances_shared_base):
    devctl = two_instances_shared_base["devctl"]
    i1 = two_instances_shared_base["i1"]
    i2 = two_instances_shared_base["i2"]

    # Instance #1: create + open "shared". After this it owns the vault's
    # cross-instance claim; the UI reflects it via the visible toolbar
    # label and the identifiers nav button.
    open_test_vault_via_ui(devctl, i1["sock"], name="shared")
    assert _vault_open(devctl, i1["sock"]), "i1 should have a vault open"
    assert _open_vault_name(devctl, i1["sock"]) == "shared"

    # Instance #2: refresh its drawer so it sees the now-existing "shared"
    # vault and i1's live claim, then open the drawer.
    _refresh_drawer(devctl, i2["sock"])

    # i2 starts with no vault open (nav button hidden, label empty).
    assert not _vault_open(devctl, i2["sock"]), "i2 should start with no vault"
    assert _open_vault_name(devctl, i2["sock"]) == ""

    # The drawer classifies "shared" as running-in-another-instance, so it
    # renders a "Switch to" button (vaultDrawer.switchTo.<vault>) instead
    # of an Open button (vaultDrawer.open.<vault>). Detect which the drawer
    # presents and drive the real action.
    switch_present = devctl(
        i2["sock"], "is_visible", target="vaultDrawer.switchTo.shared",
    )
    open_present = devctl(
        i2["sock"], "is_visible", target="vaultDrawer.open.shared",
    )

    if switch_present.get("visible"):
        # Expected steady state: i2 sees the vault as running elsewhere.
        # The user action is "Switch to", which asks the owner (i1) to
        # raise its window — it must NOT open a second copy here.
        r = devctl(i2["sock"], "click", target="vaultDrawer.switchTo.shared")
        assert r.get("ok"), f"click Switch to: {r}"
        time.sleep(0.5)
    elif open_present.get("visible"):
        # Race window: i2's probe hadn't yet seen i1's claim, so the row
        # still shows Open. Driving it must hit the claim() denial in
        # OpenVaultDialog.open_vault and leave i2 without the vault.
        r = devctl(i2["sock"], "click", target="vaultDrawer.open.shared")
        assert r.get("ok"), f"click Open: {r}"
        # Open dialog appears — enter the passcode + click Open.
        r = devctl(i2["sock"], "wait_for",
                   target="openVaultDialog.passcodeField",
                   condition="visible", timeout_ms=3000)
        assert r.get("ok"), f"open dialog never appeared: {r}"
        from tests.integration.peer.conftest import DEFAULT_TEST_PASSCODE
        r = devctl(i2["sock"], "type",
                   target="openVaultDialog.passcodeField",
                   text=DEFAULT_TEST_PASSCODE)
        assert r.get("ok"), r
        r = devctl(i2["sock"], "click", target="openVaultDialog.openButton")
        assert r.get("ok"), r
        time.sleep(1.0)
    else:
        raise AssertionError(
            "drawer showed neither Switch to nor Open for 'shared'; "
            f"switch={switch_present} open={open_present}"
        )

    # The must-have: instance #2 did NOT duplicate-open the vault. Read it
    # off the real UI — no nav identifiers button, empty toolbar label.
    assert not _vault_open(devctl, i2["sock"]), (
        "instance #2 should not have opened 'shared' (single-instance-"
        "per-vault), but its identifiers nav button is visible"
    )
    assert _open_vault_name(devctl, i2["sock"]) == "", (
        "instance #2 toolbar should show no open vault, but the vault-name "
        "label is non-empty"
    )

    # Instance #1 still holds it.
    assert _vault_open(devctl, i1["sock"]), "i1 should still hold a vault"
    assert _open_vault_name(devctl, i1["sock"]) == "shared"


def test_switch_in_place_reuses_one_instance():
    root, i = _single_instance()
    try:
        devctl = _devctl
        sock = i["sock"]

        # Open vault A.
        open_test_vault_via_ui(devctl, sock, name="vaultone")
        assert _vault_open(devctl, sock), "vaultone should be open"
        assert _open_vault_name(devctl, sock) == "vaultone"

        # Switch in place: the real user flow to leave a vault is the
        # toolbar Lock button (the Vaults drawer button is hidden on the
        # vault page). Lock closes vaultone (releasing its claim) and
        # navigates HOME, which re-shows + refreshes the drawer. The Lock
        # button carries the "Close Vault" tooltip selector.
        r = devctl(sock, "click", target="Close Vault")
        assert r.get("ok"), f"click Lock (close vault): {r}"
        r = devctl(sock, "wait_for",
                   target="vaultNavMenu.identifiersButton",
                   condition="hidden", timeout_ms=10000)
        assert r.get("ok"), f"vault never closed after Lock: {r}"
        # Vault closed: the toolbar vault-name label clears.
        assert _open_vault_name(devctl, sock) == "", (
            "toolbar vault-name label should clear when the vault closes"
        )

        # Open the drawer (Vaults button is back on the home toolbar) and
        # create + open vault B in the SAME instance.
        r = devctl(sock, "click", target="toolbar.vaultsButton")
        assert r.get("ok"), f"open vault drawer: {r}"
        open_test_vault_via_ui(devctl, sock, name="vaulttwo")
        assert _vault_open(devctl, sock), "vaulttwo should be open"
        assert _open_vault_name(devctl, sock) == "vaulttwo"
    finally:
        i["proc"].terminate()
        try:
            i["proc"].wait(timeout=5)
        except subprocess.TimeoutExpired:
            i["proc"].kill()
        shutil.rmtree(root, ignore_errors=True)
