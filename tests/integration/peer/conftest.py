"""Fixtures for two-wallet integration tests.

Spawns two Locksmith wallets in subprocesses with isolated HOME dirs,
matching the manual dev pattern documented in the spec:

- Wallet A: HOME=<tmpdir>/wallet_a, socket <tmpdir>/wallet_a/.locksmith-control.sock
- Wallet B: HOME=<tmpdir>/wallet_b, socket <tmpdir>/wallet_b/.locksmith-control.sock

Both wallets are launched with ``.venv/bin/python -m locksmith.main``.
The fixture symlinks the locksmith-ui-tester clone into each HOME so the
dev-control socket comes up on launch.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
HOST_PLUGINS_DIR = Path.home() / ".locksmith" / "plugins"


def _install_plugins(home: Path) -> None:
    """Copy the host's installed plugin set into <home>/.locksmith/plugins/.

    The plugin manager finds plugins via ``<plugins>/index.json``. We need
    both the index AND the clone directories it points at. Copying the
    whole directory is the most reliable way to get a working install
    inside the isolated HOME without re-running install logic.
    """
    if not HOST_PLUGINS_DIR.exists():
        pytest.skip(
            f"no plugin install on host at {HOST_PLUGINS_DIR}; "
            "integration tests require locksmith-ui-tester installed"
        )
    dest = home / ".locksmith" / "plugins"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return
    shutil.copytree(HOST_PLUGINS_DIR, dest, symlinks=False)


def _start_wallet(home: Path, log_path: Path) -> subprocess.Popen:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["QT_QPA_PLATFORM"] = "offscreen"
    # Run the tree under test, not whichever tree the shared venv points at.
    #
    # ``sys.executable`` is the interpreter running pytest — the venv python in
    # both the main checkout and any worktree — which is what makes these tests
    # runnable from a worktree at all (there is exactly one venv, at the main
    # checkout; see CLAUDE.md "Worktree venv isolation").
    #
    # But that alone silently tests the WRONG TREE: the venv's editable ``.pth``
    # holds an absolute path to the MAIN checkout's ``src``, so a bare
    # ``python -m locksmith.main`` imports the main tree's code no matter which
    # worktree pytest was invoked from. Prepending this repo root's ``src``
    # mirrors what pytest's ``pythonpath`` already does for in-process tests.
    # ``test_fixture_smoke.py`` asserts the wallet's own ``startup.identity
    # source=`` line so a regression here fails loudly instead of going green.
    src = str((REPO_ROOT / "src").resolve())
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{src}{os.pathsep}{existing}" if existing else src
    proc = subprocess.Popen(
        [sys.executable, "-m", "locksmith.main"],
        env=env,
        stdout=log_path.open("w"),
        stderr=subprocess.STDOUT,
        cwd=str(REPO_ROOT),
    )
    return proc


def _wait_for_socket(socket_path: Path, timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if socket_path.exists():
            try:
                sock = socket.socket(socket.AF_UNIX)
                sock.settimeout(1.0)
                sock.connect(str(socket_path))
                sock.close()
                return
            except OSError:
                pass
        time.sleep(0.5)
    raise TimeoutError(f"socket never appeared: {socket_path}")


def _devctl(socket_path: Path, op: str, **kwa) -> dict:
    sock = socket.socket(socket.AF_UNIX)
    # The CLIENT must outwait the SERVER, or a server-side poll is silently
    # capped by the client's patience. `wait_for` blocks up to its own
    # `timeout_ms` before replying and callers pass values up to 15000, so a
    # fixed 5s socket timeout turned every one of those into "5 seconds or
    # bust": green on an idle machine, TimeoutError under load, and the failure
    # points at the socket rather than at the condition that was still pending.
    # Give the server its full budget plus headroom for the round trip.
    budget_s = float(kwa.get("timeout_ms") or 0) / 1000.0
    sock.settimeout(max(5.0, budget_s + 5.0))
    sock.connect(str(socket_path))
    payload = json.dumps({"op": op, **kwa}).encode("utf-8") + b"\n"
    sock.sendall(payload)
    buf = b""
    while b"\n" not in buf:
        chunk = sock.recv(65536)
        if not chunk:
            break
        buf += chunk
    sock.close()
    return json.loads(buf.split(b"\n", 1)[0])


def free_port() -> int:
    """Allocate a free TCP port. The OS hands one out; we close the
    probe socket immediately and the port is then race-free as long as
    the caller binds it promptly.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def set_peer_mode_via_ui(
    devctl,
    sock: Path,
    port: int,
    advertised_host: str = "127.0.0.1",
    enabled: bool = True,
) -> None:
    """Drive Settings → Peer Mode the way a user would: navigate to the
    Settings page, set the toggle/port/advertised-host fields, click
    "Save and restart listener". Replaces the retired peer_set_mode
    devctl bypass.

    The port must be an explicit integer in [1024, 65535]; the QSpinBox
    range doesn't allow port=0 (OS-assigned). Use ``free_port()`` to
    get one. After apply, the wallet's peer doer restarts at the chosen
    port — exactly what restart_peer_mode would do from the bypass.
    """
    # Side-nav buttons are stamped with component-scoped objectNames so
    # the click goes to the QPushButton (not its inner QLabel, which
    # carries the same visible text but has no click handler).
    r = devctl(sock, "click", target="vaultNavMenu.settingsButton")
    assert r.get("ok"), f"navigate to Settings: {r}"
    r = devctl(sock, "wait_for",
               target="peerSettingsSection.enabledToggle",
               condition="visible", timeout_ms=3000)
    assert r.get("ok"), f"Settings page never showed the peer card: {r}"

    # Toggle to desired state (idempotent — only clicks if state differs).
    r = devctl(sock, "is_checked",
               target="peerSettingsSection.enabledToggle")
    assert r.get("ok"), r
    if r["checked"] != enabled:
        r = devctl(sock, "click",
                   target="peerSettingsSection.enabledToggle")
        assert r.get("ok"), r

    # Port: QSpinBox accepts numeric text via type op.
    r = devctl(sock, "type",
               target="peerSettingsSection.portSpin", text=str(port))
    assert r.get("ok"), f"set port: {r}"

    # Advertised host: editable QComboBox — type routes through line_edit.
    r = devctl(sock, "type",
               target="peerSettingsSection.advertisedCombo",
               text=advertised_host)
    assert r.get("ok"), f"set advertised_host: {r}"

    # Save + restart listener.
    r = devctl(sock, "click",
               target="peerSettingsSection.applyButton")
    assert r.get("ok"), f"click apply: {r}"

    # Listener restart needs a beat (the bypass restart_peer_mode is
    # synchronous; the UI uses QTimer.singleShot for the self-test).
    time.sleep(0.6)

    # Return to Identifiers so subsequent expose flows find the table.
    r = devctl(sock, "click", target="vaultNavMenu.identifiersButton")
    assert r.get("ok"), f"navigate back to Identifiers: {r}"


DEFAULT_TEST_PASSCODE = "DoB2-e4Rr-gVOr-Nb1Y-7yBl-gI3n-i4cB-gf07"


def open_test_vault_via_ui(
    devctl,
    sock: Path,
    name: str,
    passcode: str = DEFAULT_TEST_PASSCODE,
) -> None:
    """Drive the vault drawer to create a vault the way a user would, which
    now auto-opens it (no second password prompt):

      1. Click "Initialize New Vault" → CreateVaultDialog.
      2. Type name + passcode, click Create. The vault is created on disk
         and immediately opened with the same passcode; the create dialog
         closes and the vault page mounts.

    Replaces the retired peer_open_test_vault devctl bypass. Same
    default passcode (the test passcode is a fixture, not a secret —
    every test wallet uses the same one because the HOME is isolated
    to a tmpdir).

    **``name`` must be unique across the two wallets.** The fixture's HOME
    isolation does NOT isolate the instance coordinator: it claims a
    QLocalServer named ``vault_server_name(config.base, vault)``
    (``core/instancing.py:70``), ``base`` is the same for both wallets, and
    local-socket names live in a system-wide namespace rather than under HOME.
    So two wallets opening the same vault name is genuinely "one vault, two
    processes" — the coordinator correctly denies the second claim, the wallet
    falls back to the modal passcode dialog, and that modal blocks its Qt event
    loop so the dev-control socket stops answering. The symptom is an opaque
    ``TimeoutError`` from the *next* devctl call, which points nowhere near the
    cause. Pass distinct names (``"ptest"`` / ``"ptest_b"``).
    """
    # --- Step 1+2: create ---
    r = devctl(sock, "click_list_item", text="Initialize New Vault")
    assert r.get("ok"), f"click Initialize New Vault: {r}"
    r = devctl(sock, "wait_for",
               target="createVaultDialog.nameField",
               condition="visible", timeout_ms=3000)
    assert r.get("ok"), f"Create Vault dialog never appeared: {r}"

    r = devctl(sock, "type",
               target="createVaultDialog.nameField", text=name)
    assert r.get("ok"), r
    r = devctl(sock, "type",
               target="createVaultDialog.passcodeField", text=passcode)
    assert r.get("ok"), r
    r = devctl(sock, "click",
               target="createVaultDialog.createButton")
    assert r.get("ok"), r

    # Wait for the create dialog to close.
    r = devctl(sock, "wait_for",
               target="createVaultDialog.nameField",
               condition="hidden", timeout_ms=10000)
    assert r.get("ok"), f"create dialog never closed: {r}"

    # The vault auto-opens after creation (no second password prompt): the
    # vault page mounts and the Identifiers nav button appears.
    r = devctl(sock, "wait_for",
               target="vaultNavMenu.identifiersButton",
               condition="visible", timeout_ms=10000)
    assert r.get("ok"), f"vault did not auto-open after create: {r}"


def create_aid_via_ui(devctl, sock: Path, alias: str) -> None:
    """Drive the Add Identifier dialog: open via "Add Identifier" toolbar
    button, type alias into the FloatingLabelLineEdit, click Create.

    Replaces the retired peer_create_test_aid devctl bypass. Uses all
    dialog defaults (key chain / salty key type, 1 signing key, 1
    rotation key, no witnesses, toad=0) — same shape as the bypass made.
    """
    # The Identifiers page table has an "Add Identifier" LocksmithButton
    # in its header; click by visible text.
    r = devctl(sock, "click", target="vaultNavMenu.identifiersButton")
    assert r.get("ok"), r
    r = devctl(sock, "click", target="Add Identifier")
    assert r.get("ok"), f"open Add Identifier dialog: {r}"

    r = devctl(sock, "wait_for",
               target="createIdentifierDialog.aliasField",
               condition="visible", timeout_ms=3000)
    assert r.get("ok"), f"Add Identifier dialog never appeared: {r}"

    r = devctl(sock, "type",
               target="createIdentifierDialog.aliasField", text=alias)
    assert r.get("ok"), r

    r = devctl(sock, "click",
               target="createIdentifierDialog.createButton")
    assert r.get("ok"), r

    # Dialog closes when InceptDoer signals identifier_created. For a
    # witness-less AID this is synchronous — usually fast, but give it
    # a few seconds in case the doist is busy.
    r = devctl(sock, "wait_for",
               target="createIdentifierDialog.aliasField",
               condition="hidden", timeout_ms=5000)
    assert r.get("ok"), f"create dialog never closed: {r}"


def import_peer_blob_via_ui(
    devctl,
    sock: Path,
    blob: str,
    label: str | None = None,
) -> None:
    """Drive Settings → "Pair new peer" → paste blob → Pair button.

    Replaces the retired peer_import_blob devctl bypass. The dialog
    accepts either a witness-served OOBI URL or a witness-less
    locksmith-peer-oobi:v1: blob; this helper covers the blob path.
    On success the dialog closes (Pair clicks accept()); on failure the
    error_label fills in. The caller can check the peer list afterwards.
    """
    # Settings holds the Pair-new-peer entry point. Navigate first.
    r = devctl(sock, "click", target="vaultNavMenu.settingsButton")
    assert r.get("ok"), f"navigate to Settings: {r}"
    r = devctl(sock, "wait_for",
               target="peerSettingsSection.addPeerButton",
               condition="visible", timeout_ms=3000)
    assert r.get("ok"), r

    r = devctl(sock, "click",
               target="peerSettingsSection.addPeerButton")
    assert r.get("ok"), f"open Add Peer dialog: {r}"
    r = devctl(sock, "wait_for",
               target="addPeerDialog.oobiInput",
               condition="visible", timeout_ms=3000)
    assert r.get("ok"), f"Add Peer dialog never appeared: {r}"

    r = devctl(sock, "type",
               target="addPeerDialog.oobiInput", text=blob)
    assert r.get("ok"), f"paste blob into OOBI input: {r}"

    if label:
        r = devctl(sock, "type",
                   target="addPeerDialog.labelInput", text=label)
        assert r.get("ok"), f"type label: {r}"

    r = devctl(sock, "click", target="addPeerDialog.pairButton")
    assert r.get("ok"), f"click Pair: {r}"

    # Dialog closes on success; if it stays open, the error_label has
    # the diagnostic. Wait for it to disappear and surface the error
    # if it doesn't.
    r = devctl(sock, "wait_for",
               target="addPeerDialog.oobiInput",
               condition="hidden", timeout_ms=3000)
    if not r.get("ok"):
        err = devctl(sock, "get_text", target="addPeerDialog.errorLabel")
        raise AssertionError(
            f"Pair dialog didn't close — likely error: "
            f"{err.get('text', '?')!r}"
        )

    # Return to Identifiers so subsequent UI interactions land on a
    # familiar page.
    r = devctl(sock, "click", target="vaultNavMenu.identifiersButton")
    assert r.get("ok"), r


def expose_aid_via_ui(devctl, sock: Path, alias: str) -> None:
    """Drive the View Identifier "Expose over peer mode" toggle the way
    a user would: click the row action, wait for the dialog, click the
    toggle, assert it's checked, close the dialog.

    Use this from tests that need an AID exposed for peer mode as setup,
    when the test isn't itself exercising the expose UI. Equivalent to
    the retired `peer_expose_aid` devctl bypass, minus the bypass —
    actually walks the widgets a real user would touch.
    """
    r = devctl(sock, "click_row_action", row_text=alias, action="View")
    assert r.get("ok"), f"open View Identifier dialog for {alias!r}: {r}"
    r = devctl(sock, "wait_for",
               target="viewIdentifierDialog.aidField",
               condition="visible", timeout_ms=3000)
    assert r.get("ok"), f"View Identifier dialog never opened for {alias!r}: {r}"

    # If already exposed, leave it (idempotent — matches the bypass).
    r = devctl(sock, "is_checked", target="viewIdentifierDialog.exposeToggle")
    assert r.get("ok"), r
    if not r["checked"]:
        r = devctl(sock, "click", target="viewIdentifierDialog.exposeToggle")
        assert r.get("ok"), f"toggle expose for {alias!r}: {r}"
        r = devctl(sock, "is_checked", target="viewIdentifierDialog.exposeToggle")
        assert r == {"ok": True, "checked": True}, r
        # Publish doer needs a beat to write the role/loc rpys.
        time.sleep(0.5)

    # Close the dialog so subsequent test interactions aren't blocked.
    r = devctl(sock, "click", target="Close")
    # Don't assert — some dialog variants close on Escape, not Close button.
    # The next interaction will fail loudly if the dialog is still modal.


@contextmanager
def _spawn_wallets(names: list[str], prefix: str = "lspeer-"):
    """Spawn one Locksmith wallet subprocess per name, each with its own isolated
    HOME + devctl socket. Generalizes what used to be `two_wallets`'s own inline
    two-copy spawn loop, so a THIRD (or Nth) named wallet is one more list entry,
    not a third copy-pasted block — `four_wallets`
    (`tests/integration/roles/conftest.py`) is this same generator called with three
    names, not a fork of this one.

    A context manager, not a fixture itself: yields ``{name: {"home", "log", "sock",
    "proc"}, ...}`` once every socket is live, and on exit terminates every process
    and (unless ``LOCKSMITH_KEEP_TEST_HOMES`` is set) removes the shared tmpdir —
    exactly `two_wallets`'s prior try/finally shape, now parameterized over names.
    """
    # pytest's tmp_path lives under /private/var/folders/... which on macOS easily
    # exceeds the 104-char UDS path limit when we put a .locksmith-control.sock
    # inside it. Allocate our own short prefix.
    root = Path(tempfile.mkdtemp(prefix=prefix, dir="/tmp"))
    wallets: dict[str, dict] = {}
    procs: list[subprocess.Popen] = []
    try:
        for name in names:
            home = root / name
            home.mkdir()
            _install_plugins(home)
            log = root / f"{name}.log"
            proc = _start_wallet(home, log)
            procs.append(proc)
            wallets[name] = {
                "home": home, "log": log,
                "sock": home / ".locksmith-control.sock", "proc": proc,
            }

        for w in wallets.values():
            _wait_for_socket(w["sock"])

        yield wallets
    finally:
        for proc in procs:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        # Failures here are usually diagnosed from the wallets' logs, and pytest
        # truncates them out of assertion messages. Set LOCKSMITH_KEEP_TEST_HOMES
        # to keep every HOME (and <name>.log) for inspection.
        if os.environ.get("LOCKSMITH_KEEP_TEST_HOMES"):
            print(f"\n[wallets:{','.join(names)}] logs kept at {root}")
        else:
            shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def two_wallets():
    with _spawn_wallets(["a", "b"], prefix="lspeer-") as wallets:
        yield {**wallets, "devctl": _devctl}
