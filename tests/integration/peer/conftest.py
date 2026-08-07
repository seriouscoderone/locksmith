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

import contextlib
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



#: Nav entries a vault can land on once it has mounted, most specific first.
#: A build is identified by WHICH of these exists, not by an env var — the
#: drivers then work against vanilla and HOA alike.
#:
#:   vanilla Locksmith  -> identifiers, settings, credentials, ...
#:   branded HOA        -> home, notifications, settings ONLY (HoaVaultPage.
#:                         _register_core_pages peels the rest; Settings stays
#:                         because peer transport is configured there and
#:                         nowhere else)
LANDING_TARGETS = (
    "vaultNavMenu.identifiersButton",   # vanilla
    "vaultNavMenu.homeButton",          # HOA shell
    "vaultNavMenu.settingsButton",      # present in BOTH — last-resort probe
)

_LANDING_CACHE: dict = {}


def landing_target(devctl, sock, timeout_ms: int = 10000) -> str:
    """The nav entry THIS wallet lands on, discovered once per socket.

    Waiting on `vaultNavMenu.identifiersButton` is what every driver used to
    do, and it is a vanilla-only assumption: a peeled HOA has no identifiers
    page, so the wait times out and the failure reads "vault did not auto-open"
    when the vault opened perfectly well.

    Probes in order and returns the first that appears. The whole budget is
    spent on the first candidate only if nothing else is up yet, so a vanilla
    wallet still resolves immediately.
    """
    key = str(sock)
    if key in _LANDING_CACHE:
        return _LANDING_CACHE[key]

    deadline = time.time() + timeout_ms / 1000.0
    last = None
    while time.time() < deadline:
        for target in LANDING_TARGETS:
            r = devctl(sock, "is_visible", target=target)
            if r.get("ok") and r.get("visible"):
                _LANDING_CACHE[key] = target
                return target
            last = r
        time.sleep(0.2)

    raise AssertionError(
        f"no landing page appeared within {timeout_ms}ms — tried "
        f"{list(LANDING_TARGETS)}; last probe: {last}"
    )


def wait_for_vault_open(devctl, sock, timeout_ms: int = 10000) -> str:
    """Block until a vault has mounted in whatever build this is."""
    return landing_target(devctl, sock, timeout_ms=timeout_ms)


#: Where to place spawned wallet windows, as "x,y;x,y;..." — one origin per
#: wallet, applied in spawn order and cycled if there are more wallets than
#: origins. Unset by default, so CI and offscreen runs are unaffected.
#: Set it when WATCHING a run on a multi-monitor desk, e.g. two 1920x1080s
#: side by side plus an ultrawide above:
#:     LOCKSMITH_TEST_WIN_ORIGINS="-1920,0;0,0;0,-1080"
WIN_ORIGINS_ENV = "LOCKSMITH_TEST_WIN_ORIGINS"


def _win_origins() -> list[str]:
    raw = os.environ.get(WIN_ORIGINS_ENV, "").strip()
    return [o.strip() for o in raw.split(";") if o.strip()] if raw else []


def _start_wallet(home: Path, log_path: Path, brand: Path | None = None,
                  win_pos: str | None = None,
                  extra_env: dict[str, str] | None = None) -> subprocess.Popen:
    env = os.environ.copy()
    env["HOME"] = str(home)
    if brand is not None:
        # Spawns a BRANDED app, i.e. one that loads HoaShellPlugin. Vanilla
        # wallets do not register the HOA's own doers at all, so any test of
        # HOA behaviour run without this passes or fails for the wrong reason.
        env["LOCKSMITH_BRAND_CONFIG"] = str(brand)
    if extra_env:
        env.update(extra_env)
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
    argv = [sys.executable, "-m", "locksmith.main"]
    if win_pos:
        argv += ["--win-pos", win_pos]
    proc = subprocess.Popen(
        argv,
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

    # Return to the wallet's landing page so subsequent flows start from a
    # known nav state. In vanilla that is Identifiers (where the expose flows
    # find their table); a peeled HOA has no such page and lands on home.
    landing = landing_target(devctl, sock)
    r = devctl(sock, "click", target=landing)
    assert r.get("ok"), f"navigate back to {landing}: {r}"


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
    # Brand-aware: a peeled HOA has no identifiers page, so waiting on it
    # reported "vault did not auto-open" for a vault that opened fine.
    landing = landing_target(devctl, sock, timeout_ms=15000)
    r = devctl(sock, "wait_for",
               target=landing,
               condition="visible", timeout_ms=10000)
    assert r.get("ok"), f"vault did not auto-open after create: {r}"


def create_aid_via_ui(devctl, sock: Path, alias: str) -> None:
    """Drive the Add Identifier dialog: open via "Add Identifier" toolbar
    button, type alias into the FloatingLabelLineEdit, click Create.

    Replaces the retired peer_create_test_aid devctl bypass. Uses all
    dialog defaults (key chain / salty key type, 1 signing key, 1
    rotation key, no witnesses, toad=0) — same shape as the bypass made.
    """
    # A peeled HOA has no Identifiers page and MINTS ITS OWN identifier when
    # the vault opens (HoaShellPlugin._ensure_default_identifier), so there is
    # nothing here to drive and nothing to create. Returning early is the
    # brand-aware equivalent of "the wallet now has an identity" — the
    # postcondition every caller actually depends on.
    if landing_target(devctl, sock) != "vaultNavMenu.identifiersButton":
        return

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

    # RETRY the click, do not just wait longer on one. The peer settings card
    # rebuilds itself on its own tick (it re-probes reachability and re-renders
    # the paired list), so a click can land on a button that is being replaced
    # — the click reports ok and nothing opens. Re-clicking is what actually
    # recovers; a longer single wait just fails more slowly.
    # NEVER click blind. An earlier version of this loop re-clicked every
    # three seconds without checking, and each click opened ANOTHER AddPeerDialog
    # — ten stacked copies of the same modal piling up on screen, which is both
    # a mess to watch and the reason the wait kept failing (the selector can
    # resolve to a covered instance). So: probe first, click only when nothing
    # is open, and dismiss whatever we opened before trying again.
    r = {"error": "not attempted"}
    deadline = time.time() + 30.0
    while time.time() < deadline:
        probe = devctl(sock, "is_visible", target="addPeerDialog.oobiInput")
        if probe.get("ok") and probe.get("visible"):
            r = {"ok": True, "already_open": True}
            break

        devctl(sock, "click", target="peerSettingsSection.addPeerButton")
        r = devctl(sock, "wait_for",
                   target="addPeerDialog.oobiInput",
                   condition="visible", timeout_ms=3000)
        if r.get("ok"):
            break

        # Leave no orphan behind before the next attempt.
        devctl(sock, "click", target="addPeerDialog.cancelButton")
        time.sleep(1.0)
    if not r.get("ok"):
        # Screenshot before theorising (docs/development/ui-driven-testing.md):
        # a dialog that does not appear after a successful click is either
        # stacked behind a stale one or was never constructed, and the widget
        # tree distinguishes those in one look.
        shot = Path(tempfile.gettempdir()) / "addpeer_failure.png"
        devctl(sock, "screenshot", path=str(shot))
        tree = devctl(sock, "tree")
        names = [w.get("objectName") or w.get("type")
                 for w in (tree.get("widgets") or [])][:40]
        raise AssertionError(
            f"Add Peer dialog never appeared: {r}\nscreenshot: {shot}\n"
            f"visible widgets: {names}"
        )

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

    # Return to whatever page this build lands on, so subsequent UI
    # interactions start from a known nav state.
    landing = landing_target(devctl, sock)
    r = devctl(sock, "click", target=landing)
    assert r.get("ok"), f"navigate back to {landing}: {r}"


#: Health phrases `peer/health.py::summarize_health_for_ui` renders on the
#: peers list, keyed by the dot colour a watcher actually sees.
_PEER_REACHABLE_PREFIX = "reachable ("
_PEER_UNPROBED = "not yet probed"


def wait_for_peer_reachable(devctl, sock: Path, *, count: int = 1,
                            timeout_s: float = 90.0) -> list[str]:
    """Block until `count` peers render a GREEN dot, and return their phrases.

    Pairing writes the allowlist record synchronously, but reachability is
    established by `PeerHealthMonitorDoer` on its own cycle — so the instant
    after Pair the row reads "not yet probed" (grey) and every send made
    against it is a guess. Watching a run, this is the moment where the dot is
    still grey and the harness has already moved on; the failure then surfaces
    several steps later, attributed to whatever step happened to be running.

    Polled through the widget tree because the row is a custom
    `setItemWidget` render with NO item text (`peer_section.py::_refresh_peers_list`
    says so explicitly), which is why `get_list_items` reports blanks and the
    pairing test can only count rows. The phrase lives in a QLabel, so `tree`
    sees it.

    Set LOCKSMITH_PEER_PROBE_INTERVAL low in the wallet's env or this waits a
    full default cycle (60s ±25%) for a peer paired mid-cycle.
    """
    devctl(sock, "click", target="vaultNavMenu.settingsButton")
    deadline = time.time() + timeout_s
    seen: list[str] = []
    while time.time() < deadline:
        tree = devctl(sock, "tree")
        texts = [(w.get("text") or "") for w in (tree.get("widgets") or [])]
        seen = [t for t in texts if t.startswith(_PEER_REACHABLE_PREFIX)]
        if len(seen) >= count:
            return seen
        time.sleep(2.0)
    unprobed = sum(1 for t in texts if t == _PEER_UNPROBED)
    raise AssertionError(
        f"only {len(seen)} of {count} peers went green within {timeout_s}s "
        f"({unprobed} still {_PEER_UNPROBED!r}). Either the far side is not "
        f"listening, or the record's endpoint_url is wrong — both render "
        f"identically here. Phrases on screen: "
        f"{[t for t in texts if 'probe' in t or 'reachable' in t or 'down' in t]}"
    )


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
def _spawn_wallets(names: list[str], prefix: str = "lspeer-", brand=None):
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
            origins = _win_origins()
            # `brand` may be one value for every wallet, or a {name: path|None}
            # map for a MIXED fleet — e.g. a vanilla admin issuing credentials
            # to branded HOAs, which is the real shape of this ecosystem.
            wallet_brand = brand.get(name) if isinstance(brand, dict) else brand
            proc = _start_wallet(
                home, log, brand=wallet_brand,
                win_pos=origins[len(procs) % len(origins)] if origins else None,
            )
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


#: The built usurance brand. GITIGNORED (`.gitignore:244`) — produced by
#: `scripts/brand_apply.py`, not checked in.
USURANCE_BRAND = REPO_ROOT / "src" / "locksmith" / "release" / "usurance" / "brand.json"


@pytest.fixture
def two_hoa_wallets():
    """Two BRANDED wallets — i.e. two real HOAs, not two vanilla Locksmiths.

    `two_wallets` spawns vanilla wallets, where `HoaShellPlugin` never loads and
    therefore the HOA's own doers are never registered. A test of HOA behaviour
    run on that fixture exercises nothing and still reports green, which is how
    a completely dead peer-sync survived this suite.

    Skips LOUDLY when the brand has not been built, rather than silently falling
    back to vanilla — a suite that ran nothing must never look like a pass.
    """
    if not USURANCE_BRAND.is_file():
        pytest.skip(
            f"branded wallets need {USURANCE_BRAND}, which is gitignored and "
            f"built on demand. Run: .venv/bin/python scripts/brand_apply.py usurance"
        )
    with _spawn_wallets(["cuo", "actuary"], prefix="lshoa-",
                        brand=USURANCE_BRAND) as wallets:
        yield {**wallets, "devctl": _devctl}


def accept_grant_via_hoa_notifications(devctl, sock, *, timeout_s: float = 45.0) -> int:
    """Accept every pending IPEX grant on a BRANDED HOA's Notifications page.

    The HOA equivalent of vanilla's Credentials -> Received -> Accept flow,
    which is unreachable here: a peeled HOA has no `vaultNavMenu.credentialsButton`
    at all, and incoming grants surface on Notifications instead.

    Crucially this path is DRIVABLE where vanilla's is not. `four_wallets`'
    own docstring records why a live grant cannot be accepted through the
    vanilla UI — `notifications/list.py::_show_accept_grant_dialog` admits via
    `QDialog.exec()`, a MODAL call that blocks the same Qt main thread the
    devctl server dispatches on, so the harness deadlocks. The HOA page has no
    `exec()`: `hoaNotifications.acceptButton` calls `_accept(row)` directly,
    which schedules `make_admit_doer` on the vault's doer runner and returns.
    That is what makes an end-to-end HOA credential test possible at all.

    Returns how many grants were accepted. Polls rather than sleeping blindly:
    a grant arrives over the network, so the row's appearance is asynchronous,
    but each accept has a deterministic end state (the row loses its button).
    """
    r = devctl(sock, "click", target="vaultNavMenu.notificationsButton")
    assert r.get("ok"), f"navigate to HOA Notifications: {r}"

    accepted = 0
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        # on_show refreshes on every navigation, so re-entering the page is
        # how a newly-arrived grant becomes visible.
        devctl(sock, "click", target="vaultNavMenu.notificationsButton")
        r = devctl(sock, "count", target="hoaNotifications.acceptButton")
        pending = r.get("count", 0) if r.get("ok") else 0
        if pending:
            click = devctl(sock, "click", target="hoaNotifications.acceptButton")
            assert click.get("ok"), f"click Accept: {click}"
            accepted += 1
            # The admit is scheduled on the doer runner, not run inline; give
            # it a tick to land before re-reading the list.
            time.sleep(1.0)
            continue
        if accepted:
            return accepted
        time.sleep(1.0)

    if accepted:
        return accepted
    raise AssertionError(
        f"no grant appeared on HOA Notifications within {timeout_s}s. The page "
        "shows 'hoaNotifications.emptyLabel' when there is nothing to accept — "
        "check the wallet log for an inbound /exn/ipex/grant."
    )


@pytest.fixture
def admin_and_two_hoas():
    """A VANILLA admin wallet plus two branded HOAs — cuo and actuary.

    The shape the ecosystem actually has: a Locksmith operator issues role
    credentials, and persona-shaped HOAs consume them. Every leg runs through a
    real UI in a real process — nothing is issued in-process on the test's
    behalf.

    `four_wallets` explains why this could not be done before: the RECEIVING
    side of a live grant surfaced only on vanilla's Notifications page, whose
    admit goes through `QDialog.exec()` — a modal on the Qt main thread the
    devctl server dispatches on, so the harness deadlocked. That blocker is
    specific to a VANILLA recipient. Vanilla ISSUING and GRANTING was always
    drivable (issueCredentialDialog / grantCredentialDialog carry stable
    objectNames), and an HOA recipient admits without any modal at all. So
    vanilla-admin -> HOA-recipient is precisely the combination that works.
    """
    if not USURANCE_BRAND.is_file():
        pytest.skip(
            f"branded wallets need {USURANCE_BRAND}, which is gitignored and "
            f"built on demand. Run: .venv/bin/python scripts/brand_apply.py usurance"
        )
    brands = {"admin": None, "cuo": USURANCE_BRAND, "actuary": USURANCE_BRAND}
    with _spawn_wallets(["admin", "cuo", "actuary"], prefix="lsarc-",
                        brand=brands) as wallets:
        yield {**wallets, "devctl": _devctl}


#: Turns OFF `tests/integration/roles/_bootstrap/sitecustomize.py` for one
#: spawned wallet. That bootstrap is enabled PROCESS-WIDE — `roles/conftest.py`
#: sets `CUO_TEST_ADMIN_AID` and prepends `_bootstrap/` to `PYTHONPATH` at module
#: import — so every wallet spawned by any test in `roles/` silently has its
#: brand REPLACED: usurance assets, the real usurance `egf_document_said`, and
#: role gates re-pointed at an in-process fake admin.
#:
#: Measured: `admin_then_two_hoas`'s VANILLA admin (spawned with brand=None)
#: logged `egf.resolved said=EEtxdiMWf1… authorities=['EGjm-X1JMz-…']` out of a
#: directory named `cuo_brand_source_…`. The hijack overrode both the injected
#: test brand AND the absence of one — which is to say it overrode the exact
#: thing `build_test_brand` exists to control. This fixture owns its ecosystem;
#: it must not inherit that.
#: …and probe peers every 5s instead of every 60s, so `wait_for_peer_reachable`
#: resolves in seconds rather than a full default cycle.
NO_TEST_BOOTSTRAP = {"LOCKSMITH_TEST_NO_BOOTSTRAP": "1",
                     "LOCKSMITH_PEER_PROBE_INTERVAL": "5"}


@contextlib.contextmanager
def _spawn_one(name: str, root: Path, brand: Path | None, idx: int):
    """Spawn a single wallet into `root/name`, honouring window placement."""
    home = root / name
    home.mkdir(exist_ok=True)
    _install_plugins(home)
    log = root / f"{name}.log"
    origins = _win_origins()
    proc = _start_wallet(home, log, brand=brand,
                         extra_env=NO_TEST_BOOTSTRAP,
                         win_pos=origins[idx % len(origins)] if origins else None)
    entry = {"home": home, "log": log,
             "sock": home / ".locksmith-control.sock", "proc": proc}
    try:
        _wait_for_socket(entry["sock"])
        yield entry
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture
def admin_then_two_hoas():
    """A vanilla admin, then two HOAs that TRUST IT — spawned in that order.

    They cannot be spawned together. A branded HOA trusts exactly the authority
    AID pinned in its EGF, and that AID does not exist until the admin wallet is
    running and has made one. So: bring the admin up, take its AID and its OOBI
    from its own UI, derive an EGF rooted at it, and only then launch the HOAs
    against that brand.

    This is why the shipped usurance brand cannot be used for an end-to-end HOA
    test: it pins the real `usurance-admin` (EGjm-X1JMz-...), whose passcode the
    suite must never touch. Same reason `_build_test_admin` exists, one level up
    — the suite owns its ecosystem, not just its admin.

    Yields {"admin", "cuo", "actuary", "devctl", "admin_aid", "brand"}; the
    caller drives the admin's own UI to create the AID before the HOAs exist.
    """
    from tests.integration.peer.testegf import build_test_brand

    if not USURANCE_BRAND.is_file():
        pytest.skip(
            f"needs {USURANCE_BRAND} (gitignored; build with "
            f"scripts/brand_apply.py usurance) as the template brand")

    root = Path(tempfile.mkdtemp(prefix="lsarc-"))
    keep = os.environ.get("LOCKSMITH_KEEP_TEST_HOMES")
    try:
        with _spawn_one("admin", root, None, 0) as admin:
            open_test_vault_via_ui(_devctl, admin["sock"], "arcadmin")
            create_aid_via_ui(_devctl, admin["sock"], "admin")
            set_peer_mode_via_ui(_devctl, admin["sock"], port=free_port())

            aid, token = _admin_identity(_devctl, admin["sock"])
            brand = build_test_brand(root / "brand", admin_aid=aid,
                                     admin_oobi_token=token,
                                     src_brand=USURANCE_BRAND)

            with _spawn_one("cuo", root, brand, 1) as cuo, \
                    _spawn_one("actuary", root, brand, 2) as actuary:
                yield {"admin": admin, "cuo": cuo, "actuary": actuary,
                       "devctl": _devctl, "admin_aid": aid, "brand": brand}
    finally:
        if keep:
            print(f"\n[admin_then_two_hoas] logs kept at {root}")
        else:
            shutil.rmtree(root, ignore_errors=True)


def _admin_identity(devctl, sock) -> tuple[str, str]:
    """(aid, peer-oobi token) for the admin's own identifier, read from its UI.

    The admin is VANILLA, so nothing exposes its AID for peer mode on its
    behalf: `ensure_direct_transport`'s auto-expose is an HOA behaviour, driven
    by HoaShellPlugin. A vanilla wallet exposes through the View Identifier
    dialog, which is exactly what `_expose_and_export` drives — and it
    deliberately leaves that dialog open, so the AID can be read from it
    afterwards.

    Deliberately UI-sourced: the token is base64 over exactly the bytes an EGF
    `oobis/<aid>.cesr` holds, so the fixture needs no keystore access and no
    passcode to publish its authority.
    """
    from tests.integration.roles.conftest import _expose_and_export

    token = _expose_and_export(devctl, sock, "admin")
    assert token, "admin published no peer OOBI after being exposed"

    r = devctl(sock, "get_text", target="viewIdentifierDialog.aidField")
    aid = (r.get("text") or "").strip() if r.get("ok") else ""
    assert aid.startswith("E"), (
        f"could not read the admin's AID from the open View Identifier "
        f"dialog: {r}")

    # CLOSE IT. `_expose_and_export` leaves the dialog open on purpose so the
    # AID can be read out of it — but nothing closed it afterwards, and it
    # covers the page for the rest of the run. Every later click on this wallet
    # then lands behind a dialog: a target resolves, the click reports ok, and
    # the thing it was supposed to open is invisible. That is what "Add Peer
    # dialog never appeared" was.
    devctl(sock, "click", target="Close")
    devctl(sock, "wait_for", target="viewIdentifierDialog.aidField",
           condition="hidden", timeout_ms=5000)
    return aid, token


#: What a branded HOA lands on before any vault exists.
SETUP_PAGE_FIELD = "setupPage.nameField"


def open_workspace_via_hoa_setup(devctl, sock, name: str,
                                 passcode: str = DEFAULT_TEST_PASSCODE,
                                 timeout_ms: int = 20000) -> None:
    """Drive a branded HOA's FIRST-RUN setup page to create its workspace.

    An onboarding brand does not show the vault drawer on first run: it logs
    `hoa.first_run reason=no_workspace path=setup` and mounts `SetupPage`
    instead (ui/window.py:401-403). So `open_test_vault_via_ui`, which clicks
    "Initialize New Vault" in the drawer, drives a surface that is not there —
    and the HOA sits on setup with no vault, no EGF resolved and nothing
    paired, which reads exactly like a broken ecosystem.

    Submit is gated on name + matching passcodes (`_update_validity`), so all
    three fields are filled before clicking; typing only the passcode leaves the
    button disabled and the click silently does nothing.
    """
    r = devctl(sock, "wait_for", target=SETUP_PAGE_FIELD,
               condition="visible", timeout_ms=timeout_ms)
    assert r.get("ok"), f"HOA setup page never appeared: {r}"

    for target, text in (("setupPage.nameField", name),
                         ("setupPage.passcodeField", passcode),
                         ("setupPage.confirmField", passcode)):
        r = devctl(sock, "type", target=target, text=text)
        assert r.get("ok"), f"fill {target}: {r}"

    r = devctl(sock, "click", target="setupPage.submitButton")
    assert r.get("ok"), f"click setup submit: {r}"

    # Workspace creation incepts an identifier and brings transport up, so the
    # landing page arrives asynchronously.
    r = devctl(sock, "wait_for", target=SETUP_PAGE_FIELD,
               condition="hidden", timeout_ms=timeout_ms)
    assert r.get("ok"), (
        f"setup page never closed — submit is gated on name + matching "
        f"passcodes; is one field empty? {r}")
    landing_target(devctl, sock, timeout_ms=timeout_ms)


def open_vault_any_build(devctl, sock, name: str,
                         passcode: str = DEFAULT_TEST_PASSCODE) -> str:
    """Open a workspace whatever build this is; returns which path was taken.

    Branded HOA on first run -> the setup page. Everything else -> the vault
    drawer. Decided by what is ON SCREEN, not by an env var, so it stays right
    for a brand this harness has never seen.
    """
    probe = devctl(sock, "is_visible", target=SETUP_PAGE_FIELD)
    if probe.get("ok") and probe.get("visible"):
        open_workspace_via_hoa_setup(devctl, sock, name, passcode)
        return "hoa-setup"
    open_test_vault_via_ui(devctl, sock, name, passcode)
    return "vault-drawer"
