# Multi-Instance Vaults Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users run multiple Locksmith instances simultaneously — one vault per instance, OS-dock-grouped — where opening an already-open vault focuses the existing instance instead of duplicating it.

**Architecture:** Each instance is a separate OS process opened on one vault (the vault name is the context key; no `HOME`/base fork). A new `InstanceCoordinator` (per-vault Qt `QLocalServer`) provides decentralized single-instance-per-vault coordination: a launch first tries to connect to the vault's server — if it connects, it tells the owner to raise its window and bows out; otherwise it claims the vault by listening. The LMDB write-lock is the safety backstop. Opening a vault while one is open switches in place; "Open in New Instance" spawns another process.

**Tech Stack:** Python, PySide6 (Qt6) incl. `QtNetwork.QLocalServer`/`QLocalSocket` and `QtCore.QProcess`, qasync, keripy (`help.ogler` logging), pytest + offscreen-Qt fixtures, dev-control Unix-socket UI harness.

**Spec:** `docs/superpowers/specs/2026-06-05-multi-instance-vaults-design.md`

**Conventions to follow:**
- Logger per module: `from keri import help` then `logger = help.ogler.getLogger(__name__)`.
- Structured log lines use dot-notation, e.g. `logger.info(f"instance.claim.granted vault={vault}")`.
- Widget object names use dotted `component.element` (e.g. `vaultDrawer.newInstanceButton`).
- Run unit tests: `pytest tests/ -v`. Run integration: `pytest -m integration tests/ -v`.

---

## File Structure

**New files:**
- `src/locksmith/core/instancing.py` — `vault_server_name()`, `find_free_port()`, `InstanceCoordinator`, `InstanceLauncher`. Single responsibility: cross-instance coordination + new-process launching. No UI imports.
- `tests/test_instancing.py` — unit tests for the above.
- `tests/integration/test_multi_instance.py` — harness-driven two-instance test.

**Modified files:**
- `src/locksmith/core/apping.py` — own an `InstanceCoordinator`; release the vault claim in `close_vault()`.
- `src/locksmith/ui/window.py` — wire a `_raise_to_front()` callback into the coordinator; add `open_vault_targeted()`.
- `src/locksmith/main.py` — parse `--vault <name>`; on startup focus an existing owner or open the target.
- `src/locksmith/ui/vaults/open.py` — claim before `open_hby`; on denial show "already open elsewhere".
- `src/locksmith/ui/vaults/drawer.py` — instance-aware rows (current / running-elsewhere / idle), split "Open ▾ → Open in New Instance" button, "Switch to" for running vaults, "＋ New Instance" header button.
- `src/locksmith/ui/vault/settings/peer_section.py` — default a free port on first setup; add a "Find free port" helper.

---

## Task 0: Establish a clean baseline

**Files:** none (verification only)

- [ ] **Step 1: Install deps in the worktree**

Run:
```bash
cd /Users/seriouscoderone/code/locksmith/.claude/worktrees/feat-multi-instance-vaults
pip install -e . 2>&1 | tail -5 || pip install -r requirements.txt 2>&1 | tail -5
```
Expected: installs without error (this is the `feat/multi-instance-vaults` worktree off `development`).

- [ ] **Step 2: Run the unit test suite to confirm green baseline**

Run: `pytest tests/ -q --ignore=tests/integration`
Expected: all pass (or a known-stable baseline). If anything fails, STOP and report — we must distinguish pre-existing failures from regressions before changing code.

---

## Task 1: Core helpers — `vault_server_name` and `find_free_port`

**Files:**
- Create: `src/locksmith/core/instancing.py`
- Test: `tests/test_instancing.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_instancing.py
import socket

from locksmith.core.instancing import vault_server_name, find_free_port


def test_vault_server_name_is_stable_and_unique():
    a1 = vault_server_name("/base", "treasurer")
    a2 = vault_server_name("/base", "treasurer")
    b = vault_server_name("/base", "auditor")
    c = vault_server_name("/other", "treasurer")
    assert a1 == a2                       # stable across calls
    assert a1 != b                        # different vault -> different name
    assert a1 != c                        # different base -> different name
    assert a1.startswith("host.keri.locksmith.vault.")


def test_find_free_port_returns_bindable_port():
    port = find_free_port(start=5621)
    # The returned port must be bindable right now.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", port))


def test_find_free_port_skips_occupied_port():
    # Occupy `start`, then assert find_free_port returns a different, higher port.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.bind(("", 0))
        taken = occupied.getsockname()[1]
        occupied.listen(1)
        got = find_free_port(start=taken)
        assert got != taken
        assert got >= taken
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_instancing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'locksmith.core.instancing'`.

- [ ] **Step 3: Implement the helpers**

```python
# src/locksmith/core/instancing.py
"""Cross-instance coordination and new-instance launching.

Multiple Locksmith processes can run at once, one open vault each. This
module provides:
  * vault_server_name() — a stable, unique QLocalServer name per vault.
  * find_free_port()    — pick a bindable TCP port (peer-listener default).
  * InstanceCoordinator — claim/release a vault via a per-vault local
    socket; deny + raise the owner when the vault is already open.
  * InstanceLauncher    — spawn a new OS process opened on a given vault.

The vault name is the context key — there is no HOME/base fork. All
vault state is already namespaced by vault name on disk.
"""
from __future__ import annotations

import hashlib
import socket

from keri import help

logger = help.ogler.getLogger(__name__)


def vault_server_name(base: str | None, vault: str) -> str:
    """Deterministic, collision-resistant local-socket name for a vault.

    Hashed to stay within local-socket name length/character limits and
    prefixed with the bundle id so it can't clash with other apps.
    """
    raw = f"{base or ''}\x00{vault}".encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()[:16]
    return f"host.keri.locksmith.vault.{digest}"


def find_free_port(start: int = 5621, host: str = "0.0.0.0", limit: int = 200) -> int:
    """Return the first bindable TCP port at/after ``start``.

    Falls back to ``start`` if none found in the scan window (the caller's
    bind will then surface the conflict through the existing red status).
    """
    bind_host = "" if host == "0.0.0.0" else host
    for port in range(start, start + limit):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((bind_host, port))
                return port
            except OSError:
                continue
    return start
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_instancing.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/core/instancing.py tests/test_instancing.py
git commit -m "feat(instancing): vault_server_name + find_free_port helpers"
```

---

## Task 2: `InstanceCoordinator` — claim / release / probe / raise

**Files:**
- Modify: `src/locksmith/core/instancing.py`
- Test: `tests/test_instancing.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_instancing.py`:

```python
from locksmith.core.instancing import InstanceCoordinator


def test_claim_grants_when_unowned(qapp, tmp_path):
    coord = InstanceCoordinator(base=str(tmp_path))
    try:
        assert coord.claim("vaultA") is True
        # Idempotent: re-claiming a vault we already own returns True.
        assert coord.claim("vaultA") is True
    finally:
        coord.release_all()


def test_claim_denied_when_owned_by_another_coordinator(qapp, tmp_path):
    owner = InstanceCoordinator(base=str(tmp_path))
    raised = []
    owner.raise_window = lambda: raised.append(True)
    other = InstanceCoordinator(base=str(tmp_path))
    try:
        assert owner.claim("vaultA") is True
        # Second coordinator sees the vault as owned -> denied.
        assert other.claim("vaultA") is False
        qapp.processEvents()  # let the owner's newConnection fire
        qapp.processEvents()
        assert raised == [True]  # owner was asked to raise its window
    finally:
        owner.release_all()
        other.release_all()


def test_release_frees_the_vault_for_reclaim(qapp, tmp_path):
    a = InstanceCoordinator(base=str(tmp_path))
    b = InstanceCoordinator(base=str(tmp_path))
    try:
        assert a.claim("vaultA") is True
        a.release("vaultA")
        # After release, another coordinator can claim it.
        assert b.claim("vaultA") is True
    finally:
        a.release_all()
        b.release_all()


def test_probe_reports_running_state(qapp, tmp_path):
    owner = InstanceCoordinator(base=str(tmp_path))
    observer = InstanceCoordinator(base=str(tmp_path))
    try:
        assert observer.probe("vaultA") is False  # nobody owns it yet
        owner.claim("vaultA")
        assert observer.probe("vaultA") is True    # now owned
    finally:
        owner.release_all()
        observer.release_all()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_instancing.py -k "claim or release or probe" -v`
Expected: FAIL — `ImportError: cannot import name 'InstanceCoordinator'`.

- [ ] **Step 3: Implement `InstanceCoordinator`**

Append to `src/locksmith/core/instancing.py`:

```python
from PySide6.QtNetwork import QLocalServer, QLocalSocket

_CONNECT_TIMEOUT_MS = 200


class InstanceCoordinator:
    """Per-vault single-instance coordination over Qt local sockets.

    One coordinator lives per process. It can hold claims for more than
    one vault transiently (during a switch-in-place the new vault is
    claimed before the old one is released), so claims are tracked in a
    dict keyed by vault name.
    """

    def __init__(self, base: str | None = None, raise_window=None):
        self._base = base or ""
        self.raise_window = raise_window  # zero-arg callable, set by the window
        self._servers: dict[str, QLocalServer] = {}

    def _name(self, vault: str) -> str:
        return vault_server_name(self._base, vault)

    def request_raise(self, vault: str) -> bool:
        """Ask a running owner of ``vault`` to raise its window.

        Returns True if an owner answered (vault is open elsewhere).
        """
        sock = QLocalSocket()
        sock.connectToServer(self._name(vault))
        if sock.waitForConnected(_CONNECT_TIMEOUT_MS):
            logger.info(f"instance.raise.requested vault={vault}")
            sock.write(b"raise\n")
            sock.flush()
            sock.waitForBytesWritten(_CONNECT_TIMEOUT_MS)
            sock.disconnectFromServer()
            sock.close()
            return True
        sock.abort()
        return False

    def claim(self, vault: str) -> bool:
        """Become the owner of ``vault``. Returns False if already owned
        elsewhere (in which case the owner has been asked to raise)."""
        if vault in self._servers:
            return True  # idempotent — we already own it
        if self.request_raise(vault):
            logger.info(f"instance.claim.denied vault={vault}")
            return False
        name = self._name(vault)
        # Clear a stale socket file left by a crashed owner; safe because
        # no live listener answered request_raise above.
        QLocalServer.removeServer(name)
        server = QLocalServer()
        if not server.listen(name):
            logger.error(
                f"instance.claim.listen_failed vault={vault} "
                f"err={server.errorString()}"
            )
            return False
        server.newConnection.connect(lambda v=vault: self._on_incoming(v))
        self._servers[vault] = server
        logger.info(f"instance.claim.granted vault={vault}")
        return True

    def _on_incoming(self, vault: str) -> None:
        server = self._servers.get(vault)
        if server is None:
            return
        conn = server.nextPendingConnection()
        if conn is not None:
            conn.readAll()  # drain the "raise" payload
            conn.close()
        logger.info(f"instance.raise.received vault={vault}")
        if self.raise_window is not None:
            self.raise_window()

    def probe(self, vault: str) -> bool:
        """Non-owning liveness check used to render drawer badges."""
        if vault in self._servers:
            return True
        sock = QLocalSocket()
        sock.connectToServer(self._name(vault))
        ok = sock.waitForConnected(_CONNECT_TIMEOUT_MS)
        sock.abort()
        sock.close()
        return ok

    def release(self, vault: str) -> None:
        server = self._servers.pop(vault, None)
        if server is not None:
            server.close()
            QLocalServer.removeServer(self._name(vault))
            logger.info(f"instance.released vault={vault}")

    def release_all(self) -> None:
        for vault in list(self._servers):
            self.release(vault)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_instancing.py -v`
Expected: PASS (all tests, including Task 1's).

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/core/instancing.py tests/test_instancing.py
git commit -m "feat(instancing): InstanceCoordinator claim/release/probe/raise"
```

---

## Task 3: `InstanceLauncher` — spawn a new process on a vault

**Files:**
- Modify: `src/locksmith/core/instancing.py`
- Test: `tests/test_instancing.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_instancing.py`:

```python
from unittest.mock import patch

from locksmith.core import instancing


def test_launch_new_dev_mode_uses_module_invocation(qapp):
    with patch.object(instancing.sys, "frozen", False, create=True), \
         patch.object(instancing.QProcess, "startDetached", return_value=(True, 0)) as sd:
        instancing.InstanceLauncher.launch_new("treasurer")
    sd.assert_called_once()
    args = sd.call_args[0]
    # dev mode: python -m locksmith.main --vault treasurer
    assert args[1] == ["-m", "locksmith.main", "--vault", "treasurer"]


def test_launch_new_without_vault_omits_vault_arg(qapp):
    with patch.object(instancing.sys, "frozen", False, create=True), \
         patch.object(instancing.QProcess, "startDetached", return_value=(True, 0)) as sd:
        instancing.InstanceLauncher.launch_new(None)
    args = sd.call_args[0]
    assert args[1] == ["-m", "locksmith.main"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_instancing.py -k launch_new -v`
Expected: FAIL — `AttributeError: module 'locksmith.core.instancing' has no attribute 'sys'` (and no `InstanceLauncher`).

- [ ] **Step 3: Implement `InstanceLauncher`**

At the top of `src/locksmith/core/instancing.py` add `import sys` and `from pathlib import Path`, and `from PySide6.QtCore import QProcess`. Then append:

```python
class InstanceLauncher:
    """Spawn a new OS process of this app, optionally opened on a vault.

    Mirrors the plugin-restart relaunch pattern in
    ``ui/window.py::_handle_restart_requested`` (QProcess.startDetached),
    extended with a ``--vault`` argument.
    """

    @staticmethod
    def launch_new(vault: str | None = None) -> None:
        extra = ["--vault", vault] if vault else []
        if getattr(sys, "frozen", False):
            if sys.platform == "darwin":
                # sys.executable -> .../Locksmith.app/Contents/MacOS/Locksmith
                app_bundle = str(Path(sys.executable).parents[2])
                QProcess.startDetached("open", ["-n", app_bundle, "--args"] + extra)
                logger.info(f"instance.launch.spawned platform=macos vault={vault}")
                return
            QProcess.startDetached(sys.executable, sys.argv[1:] + extra)
        else:
            QProcess.startDetached(sys.executable, ["-m", "locksmith.main"] + extra)
        logger.info(f"instance.launch.spawned platform={sys.platform} vault={vault}")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_instancing.py -k launch_new -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/core/instancing.py tests/test_instancing.py
git commit -m "feat(instancing): InstanceLauncher.launch_new for new-process spawn"
```

---

## Task 4: Own the coordinator in `LocksmithApplication`; release on close

**Files:**
- Modify: `src/locksmith/core/apping.py` (constructor ~line 46-64; `close_vault` lines 114-151)
- Modify: `src/locksmith/ui/window.py` (constructor ~line 46; add `_raise_to_front`)
- Test: `tests/test_apping_coordinator.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_apping_coordinator.py
from types import SimpleNamespace

from locksmith.core.apping import LocksmithApplication
from locksmith.core.instancing import InstanceCoordinator


def test_application_constructs_a_coordinator(qapp, tmp_path):
    config = SimpleNamespace(base=str(tmp_path))
    app = LocksmithApplication(config=config)
    assert isinstance(app.coordinator, InstanceCoordinator)


def test_close_vault_releases_the_coordinator_claim(qapp, tmp_path):
    config = SimpleNamespace(base=str(tmp_path))
    app = LocksmithApplication(config=config)
    # Simulate an open vault holding a claim.
    app.coordinator.claim("treasurer")
    app.name = "treasurer"
    app.vault = SimpleNamespace(db=None, plugin_manager=None)
    app.qtask = SimpleNamespace(shutdown=lambda: None, cleanup=lambda: None)
    app.plugin_manager = SimpleNamespace(on_vault_closed=lambda v: None)

    app.close_vault()

    # The vault's local-socket server must have been released.
    assert app.coordinator.probe("treasurer") is False
```

> Note: `LocksmithApplication.__init__` builds a real `PluginManager`; if that errors under the test config, pass a minimal config that satisfies it (the existing `tests/test_open_vault_dialog.py` uses `SimpleNamespace(base=..., salt=None)` as a model). Adjust the `config` namespace fields here to match what the constructor reads.

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_apping_coordinator.py -v`
Expected: FAIL — `AttributeError: 'LocksmithApplication' object has no attribute 'coordinator'`.

- [ ] **Step 3: Construct the coordinator in `LocksmithApplication.__init__`**

In `src/locksmith/core/apping.py`, add the import near the other core imports:

```python
from locksmith.core.instancing import InstanceCoordinator
```

In `__init__`, immediately after `self.config = config` (currently ~line 40), add:

```python
        # Cross-instance coordination (single-instance-per-vault). The
        # window sets `coordinator.raise_window` once it exists so an
        # incoming "raise" request can bring this window to the front.
        self.coordinator = InstanceCoordinator(
            base=getattr(self.config, "base", None)
        )
```

- [ ] **Step 4: Release the claim in `close_vault`**

In `src/locksmith/core/apping.py::close_vault` (lines 114-151), capture the name before it is cleared and release the claim. Add this immediately after `logger.info(f"Closing vault: {self.name}")` (line ~117):

```python
        closing_name = self.name
```

Then, just before the final `logger.info("Vault closed")` (after all references are cleared at line ~149), add:

```python
        if closing_name is not None:
            self.coordinator.release(closing_name)
```

- [ ] **Step 5: Wire the window's raise callback**

In `src/locksmith/ui/window.py`, in `LocksmithWindow.__init__`, immediately after `self.app = LocksmithApplication(config=config)` (line ~46), add:

```python
        # Let an incoming "open this vault" request from another launch
        # raise this window to the front (VS Code focus-existing behavior).
        self.app.coordinator.raise_window = self._raise_to_front
```

Add this method to `LocksmithWindow` (place near the other top-level methods, e.g. after `__init__`):

```python
    def _raise_to_front(self) -> None:
        """Bring this window to the foreground and request user attention."""
        from PySide6.QtWidgets import QApplication
        self.show()
        self.setWindowState(
            (self.windowState() & ~Qt.WindowMinimized) | Qt.WindowActive
        )
        self.raise_()
        self.activateWindow()
        QApplication.alert(self)
        logger.info("instance.window.raised")
```

> `Qt` is already imported in `window.py` (used elsewhere). If not, add `from PySide6.QtCore import Qt`.

- [ ] **Step 6: Run the test to verify it passes**

Run: `pytest tests/test_apping_coordinator.py -v`
Expected: PASS (2 tests). Also run `pytest tests/test_instancing.py -v` to confirm no regression.

- [ ] **Step 7: Commit**

```bash
git add src/locksmith/core/apping.py src/locksmith/ui/window.py tests/test_apping_coordinator.py
git commit -m "feat(instancing): app owns coordinator; release claim on close; window raise callback"
```

---

## Task 5: `--vault` startup arg — focus existing or open target

**Files:**
- Modify: `src/locksmith/main.py` (startup block, lines ~88-106)
- Modify: `src/locksmith/ui/window.py` (add `open_vault_targeted`)
- Test: `tests/test_main_args.py`

- [ ] **Step 1: Write the failing test (arg parsing helper)**

To keep `main.py` testable without launching Qt, extract a tiny pure parser.

```python
# tests/test_main_args.py
from locksmith.main import parse_vault_arg


def test_parse_vault_arg_present():
    assert parse_vault_arg(["prog", "--vault", "treasurer"]) == "treasurer"


def test_parse_vault_arg_absent():
    assert parse_vault_arg(["prog"]) is None


def test_parse_vault_arg_ignores_trailing_flag_without_value():
    assert parse_vault_arg(["prog", "--vault"]) is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_main_args.py -v`
Expected: FAIL — `ImportError: cannot import name 'parse_vault_arg'`.

- [ ] **Step 3: Add the parser and startup wiring in `main.py`**

In `src/locksmith/main.py`, add this module-level function (above the `if __name__ == "__main__":` block, after `logger = ...`):

```python
def parse_vault_arg(argv: list[str]) -> str | None:
    """Return the value of ``--vault <name>`` from argv, or None."""
    if "--vault" in argv:
        i = argv.index("--vault")
        if i + 1 < len(argv):
            return argv[i + 1]
    return None
```

Then, inside `if __name__ == "__main__":`, replace the window-creation/show section (currently `window = LocksmithWindow(config)` / `window.show()`) with:

```python
    config = LocksmithConfig.get_instance()
    window = LocksmithWindow(config)
    window.show()

    target_vault = parse_vault_arg(sys.argv)
    if target_vault:
        # If another instance already owns this vault, raise it and exit —
        # never open a duplicate (also protects the LMDB single-writer).
        if window.app.coordinator.request_raise(target_vault):
            logger.info(f"instance.startup.focused_existing vault={target_vault}")
            sys.exit(0)
        logger.info(f"instance.startup.opening vault={target_vault}")
        window.open_vault_targeted(target_vault)
```

> Leave the existing `with loop: sys.exit(loop.run_forever())` block as-is after this.

- [ ] **Step 4: Add `open_vault_targeted` to the window**

In `src/locksmith/ui/window.py`, add:

```python
    def open_vault_targeted(self, vault_name: str) -> None:
        """Present the passcode dialog for a specific vault (used by the
        ``--vault`` launch path). The dialog performs the actual claim."""
        self.vault_drawer.show_open_vault_dialog(vault_name)
```

> `self.vault_drawer` is created in `__init__` (line ~141) and already exposes `show_open_vault_dialog(vault_name)` (drawer.py line ~483).

- [ ] **Step 5: Run the test to verify it passes**

Run: `pytest tests/test_main_args.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add src/locksmith/main.py src/locksmith/ui/window.py tests/test_main_args.py
git commit -m "feat(instancing): --vault startup arg focuses existing or opens target"
```

---

## Task 6: Claim before opening the keystore (switch-in-place)

**Files:**
- Modify: `src/locksmith/ui/vaults/open.py` (`open_vault`, before `open_hby` at line 192)
- Test: `tests/test_open_vault_claim.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_open_vault_claim.py
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtWidgets import QWidget

from locksmith.core.instancing import InstanceCoordinator
from locksmith.ui.vaults import open as open_module
from locksmith.ui.vaults.open import OpenVaultDialog


def _make_dialog(qapp, tmp_path, coordinator):
    parent = QWidget()
    parent.app = SimpleNamespace(coordinator=coordinator)
    config = SimpleNamespace(base=str(tmp_path), salt=None)
    with patch.object(open_module.otping, "has_otp_configured", return_value=False):
        return OpenVaultDialog(vault_name="treasurer", parent=parent, config=config), parent


def test_open_vault_aborts_when_vault_owned_elsewhere(qapp, tmp_path):
    owner = InstanceCoordinator(base=str(tmp_path))
    owner.claim("treasurer")  # vault already open in "another instance"
    this_instance = InstanceCoordinator(base=str(tmp_path))
    dialog, parent = _make_dialog(qapp, tmp_path, this_instance)
    try:
        with patch.object(open_module, "open_hby") as open_hby, \
             patch.object(dialog, "show_error") as show_error:
            dialog.open_vault()
            open_hby.assert_not_called()       # never touched the keystore
            show_error.assert_called_once()    # surfaced "already open elsewhere"
    finally:
        owner.release_all()
        this_instance.release_all()
        dialog.close()
        parent.close()


def test_open_vault_claims_when_unowned(qapp, tmp_path):
    this_instance = InstanceCoordinator(base=str(tmp_path))
    dialog, parent = _make_dialog(qapp, tmp_path, this_instance)
    try:
        with patch.object(open_module, "keystore_exists", return_value=True), \
             patch.object(open_module, "is_vault_encrypted", return_value=False), \
             patch.object(open_module, "open_hby", return_value=("vault", "qtask")) as open_hby:
            parent = dialog._parent_window
            parent.app.open_vault = lambda **kw: None
            dialog.open_vault()
            open_hby.assert_called_once()                       # proceeded to open
            assert this_instance.probe("treasurer") is True    # claim is held
    finally:
        this_instance.release_all()
        dialog.close()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_open_vault_claim.py -v`
Expected: FAIL — `open_hby` is called even when the vault is owned elsewhere (claim guard not present yet).

- [ ] **Step 3: Add the claim guard in `open_vault`**

In `src/locksmith/ui/vaults/open.py::open_vault`, immediately after the keystore-exists check (after line 174, before the `is_vault_encrypted` call) — i.e. once we know the vault exists but before touching its LMDB — insert:

```python
            # Single-instance-per-vault: claim before opening the keystore.
            # If another instance already owns it, the owner has been
            # raised; do not open a duplicate (also guards the LMDB writer).
            if not self.app.coordinator.claim(self.vault_name):
                logger.info(
                    f"instance.open.denied vault={self.vault_name}"
                )
                self.show_error(
                    "This vault is already open in another instance."
                )
                return
```

> Placement detail: it must come before `open_hby(...)` at line 192. Putting it right after `keystore_exists` (line 172-174) is correct. The subsequent `self.app.open_vault(...)` at line 201 internally calls `close_vault()`, which releases the *previous* vault's claim — giving claim-before-release ordering automatically.

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_open_vault_claim.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/ui/vaults/open.py tests/test_open_vault_claim.py
git commit -m "feat(instancing): claim vault before opening keystore; deny when open elsewhere"
```

---

## Task 7: Peer-port deconfliction

**Files:**
- Modify: `src/locksmith/ui/vault/settings/peer_section.py` (`_load` lines 250-261; `_build` row 2 around lines 116-132)
- Test: `tests/test_peer_section_port.py`

Background: `PeerModeSettings.port` defaults to 5621 for every vault, and the spin box hardcodes 5621 (`peer_section.py:123`). Two concurrently open vaults would both try to bind 5621. The existing `_sync_status_from_doer` already shows a red "Couldn't bind — port in use" dot, so collision is *surfaced*; this task prevents it for new setups and adds a one-click fix.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_peer_section_port.py
import socket
from types import SimpleNamespace
from unittest.mock import MagicMock

from locksmith.ui.vault.settings.peer_section import PeerSettingsSection


def _vault_with_no_saved_settings():
    db = SimpleNamespace()
    db.peerSettings = MagicMock()
    db.peerSettings.get.return_value = None          # first-time setup
    db.peerHealth = MagicMock()
    db.peerHealth.get.return_value = None
    vault = SimpleNamespace(db=db, hby=None, peer_doer=None)
    return vault


def test_first_time_setup_defaults_to_a_free_port(qapp):
    # Occupy 5621 so the default would collide.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        # Monkeypatch find_free_port by occupying then asserting != occupied
        s.listen(1)
        vault = _vault_with_no_saved_settings()
        section = PeerSettingsSection(vault)
        try:
            # No saved settings -> the spin should hold a bindable port.
            port = section.port_spin.value()
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind(("", port))  # must be bindable
        finally:
            section.deleteLater()


def test_find_free_port_button_updates_spin(qapp):
    vault = _vault_with_no_saved_settings()
    section = PeerSettingsSection(vault)
    try:
        section.port_spin.setValue(5621)
        section._on_find_free_port()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("", section.port_spin.value()))  # bindable
    finally:
        section.deleteLater()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_peer_section_port.py -v`
Expected: FAIL — `_on_find_free_port` does not exist; and `_load` does not set a free default.

- [ ] **Step 3: Default a free port on first setup + add the helper**

In `src/locksmith/ui/vault/settings/peer_section.py`, add the import near the top:

```python
from locksmith.core.instancing import find_free_port
```

In `_load` (lines 250-261), handle the first-time (`rec is None`) case by defaulting the spin to a free port instead of returning early:

```python
    def _load(self) -> None:
        rec = self._vault.db.peerSettings.get(keys=("default",))
        if rec is None:
            # First-time setup: pick a free port so two concurrently open
            # vaults don't both grab the hardcoded 5621 default.
            self.port_spin.setValue(find_free_port(start=5621))
            return
        self.enabled_toggle.setChecked(rec.enabled)
        self.port_spin.setValue(rec.port)
        idx = self.bind_combo.findData(rec.bind_host)
        if idx >= 0:
            self.bind_combo.setCurrentIndex(idx)
        if rec.advertised_host:
            self.advertised_combo.setCurrentText(rec.advertised_host)
        self._sync_status_from_doer()
```

In `_build`, in Row 2 (lines 116-132) right after the `self.port_spin` is added (after line 125), add a "Find free port" button:

```python
        self.find_port_button = LocksmithButton("Find free port")
        self.find_port_button.setObjectName("peerSettingsSection.findPortButton")
        self.find_port_button.clicked.connect(self._on_find_free_port)
        row2.addWidget(self.find_port_button)
```

Add the handler method (near `_on_apply`):

```python
    def _on_find_free_port(self) -> None:
        port = find_free_port(start=self.port_spin.value())
        self.port_spin.setValue(port)
        logger.info(f"peer.settings.free_port_suggested port={port}")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_peer_section_port.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/ui/vault/settings/peer_section.py tests/test_peer_section_port.py
git commit -m "feat(peer): default a free listener port on first setup + Find free port button"
```

---

## Task 8: Instance-aware vault drawer

**Files:**
- Modify: `src/locksmith/ui/vaults/drawer.py` (`_refresh_vault_list` lines 385-401; add row-widget builder; add header button)
- Test: `tests/test_vault_drawer_instances.py`

Goal: each vault row shows its state and the right actions:
- **current** (open in this instance): "● Open here" + `current` tag
- **running** (open elsewhere): "◆ Running in another instance" + **Switch to** button → `coordinator.request_raise(vault)`
- **idle**: split button — **Open** (switch-in-place via `show_open_vault_dialog`) + **▾** → **Open in New Instance** (`InstanceLauncher.launch_new(vault)`)
Plus a "＋ New Instance" button in the drawer header → `InstanceLauncher.launch_new(None)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_vault_drawer_instances.py
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QMainWindow

from locksmith.ui.vaults.drawer import VaultDrawer


def _make_window(vaults, current, probe_running):
    win = QMainWindow()
    coord = SimpleNamespace(
        probe=lambda v: v in probe_running,
        request_raise=MagicMock(return_value=True),
    )
    win.app = SimpleNamespace(
        environments=lambda: vaults,
        name=current,
        coordinator=coord,
        config=SimpleNamespace(base="/tmp"),
    )
    return win, coord


def test_row_state_classification(qapp):
    win, coord = _make_window(
        vaults=["treasurer", "auditor", "notary"],
        current="treasurer",
        probe_running={"auditor"},
    )
    toolbar = SimpleNamespace(height=lambda: 0)
    drawer = VaultDrawer(parent=win, toolbar_ref=toolbar)
    try:
        assert drawer._vault_state("treasurer") == "current"
        assert drawer._vault_state("auditor") == "running"
        assert drawer._vault_state("notary") == "idle"
    finally:
        drawer.deleteLater()
        win.close()


def test_open_in_new_instance_launches_process(qapp):
    win, coord = _make_window(["notary"], current=None, probe_running=set())
    toolbar = SimpleNamespace(height=lambda: 0)
    drawer = VaultDrawer(parent=win, toolbar_ref=toolbar)
    try:
        with patch("locksmith.ui.vaults.drawer.InstanceLauncher") as launcher:
            drawer._open_in_new_instance("notary")
            launcher.launch_new.assert_called_once_with("notary")
    finally:
        drawer.deleteLater()
        win.close()


def test_switch_to_raises_running_instance(qapp):
    win, coord = _make_window(["auditor"], current=None, probe_running={"auditor"})
    toolbar = SimpleNamespace(height=lambda: 0)
    drawer = VaultDrawer(parent=win, toolbar_ref=toolbar)
    try:
        drawer._switch_to_running("auditor")
        coord.request_raise.assert_called_once_with("auditor")
    finally:
        drawer.deleteLater()
        win.close()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_vault_drawer_instances.py -v`
Expected: FAIL — `_vault_state`, `_open_in_new_instance`, `_switch_to_running` do not exist.

- [ ] **Step 3: Add state classification + action handlers + import**

In `src/locksmith/ui/vaults/drawer.py`, add the import near the top:

```python
from locksmith.core.instancing import InstanceLauncher
```

Add these methods to `VaultDrawer`:

```python
    def _vault_state(self, vault_name: str) -> str:
        """Classify a vault row: 'current', 'running', or 'idle'."""
        if self.app.name == vault_name:
            return "current"
        if self.app.coordinator.probe(vault_name):
            return "running"
        return "idle"

    def _open_in_new_instance(self, vault_name: str) -> None:
        logger.info(f"instance.drawer.open_new vault={vault_name}")
        InstanceLauncher.launch_new(vault_name)

    def _switch_to_running(self, vault_name: str) -> None:
        logger.info(f"instance.drawer.switch_to vault={vault_name}")
        self.app.coordinator.request_raise(vault_name)

    def _new_instance(self) -> None:
        logger.info("instance.drawer.new_instance")
        InstanceLauncher.launch_new(None)
```

- [ ] **Step 4: Run the classification/handler tests to verify they pass**

Run: `pytest tests/test_vault_drawer_instances.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Render instance-aware rows in `_refresh_vault_list`**

Replace `_refresh_vault_list` (lines 385-401) so each item uses a custom row widget (mirroring `peer_section._build_peer_row`'s `setItemWidget` pattern). Replace the body with:

```python
    def _refresh_vault_list(self):
        """Refresh the vault list with per-instance state and actions."""
        self.vault_list.clear()
        for vault_name in sorted(self.app.environments(), key=str.lower):
            state = self._vault_state(vault_name)
            item = QListWidgetItem()
            row = self._build_vault_row(vault_name, state)
            item.setSizeHint(row.sizeHint())
            self.vault_list.addItem(item)
            self.vault_list.setItemWidget(item, row)
        query = self.search_field.text() if hasattr(self, "search_field") else ""
        self._filter_vaults(query)
```

Add the row builder. Use `LocksmithButton`/`LocksmithInvertedButton` (already used in this codebase) and a `QMenu` for the split-button dropdown:

```python
    def _build_vault_row(self, vault_name: str, state: str):
        from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QToolButton
        from locksmith.ui.toolkit.widgets import LocksmithButton

        row = QFrame()
        row.setObjectName(f"vaultDrawer.row.{vault_name}")
        h = QHBoxLayout(row)
        h.setContentsMargins(10, 8, 10, 8)
        h.setSpacing(8)

        name_col = QVBoxLayout()
        name_label = QLabel(vault_name)
        name_font = QFont()
        name_font.setPointSize(14)
        name_label.setFont(name_font)
        name_col.addWidget(name_label)
        status = QLabel({
            "current": "● Open in this instance",
            "running": "◆ Running in another instance",
            "idle": "Not open",
        }[state])
        status.setStyleSheet("color: #6E7074; font-size: 11px;")
        name_col.addWidget(status)
        h.addLayout(name_col)
        h.addStretch()

        if state == "current":
            tag = QLabel("current")
            tag.setStyleSheet("color: #9CA3AF; font-size: 11px;")
            h.addWidget(tag)
        elif state == "running":
            switch_btn = LocksmithButton("Switch to")
            switch_btn.setObjectName(f"vaultDrawer.switchTo.{vault_name}")
            switch_btn.clicked.connect(lambda _=False, v=vault_name: self._switch_to_running(v))
            h.addWidget(switch_btn)
        else:  # idle — split button: Open ▾ Open in New Instance
            open_btn = LocksmithButton("Open")
            open_btn.setObjectName(f"vaultDrawer.open.{vault_name}")
            open_btn.clicked.connect(lambda _=False, v=vault_name: self.show_open_vault_dialog(v))
            h.addWidget(open_btn)

            more = QToolButton()
            more.setObjectName(f"vaultDrawer.openMenu.{vault_name}")
            more.setText("▾")
            more.setPopupMode(QToolButton.InstantPopup)
            menu = QMenu(more)
            act = menu.addAction("Open in New Instance")
            act.triggered.connect(lambda _=False, v=vault_name: self._open_in_new_instance(v))
            more.setMenu(menu)
            h.addWidget(more)

        return row
```

> The existing `show_open_vault_dialog` closes the drawer and opens the passcode dialog; clicking **Open** thus switches in place after the passcode (Task 6's claim handles already-open-elsewhere). Keep the existing `vault_list` itemClicked handler if present, but since each row now owns its buttons, remove or neutralize any prior whole-row click-to-open wiring so clicks don't double-fire. Check `drawer.py` for an existing `itemClicked`/`_on_vault_item_clicked` connection and disconnect it.

- [ ] **Step 6: Add the "＋ New Instance" header button**

Find where the drawer header is built (the "Vaults" header / `new_vault_button_container` at line ~159). Next to the existing new-vault control, add:

```python
        self.new_instance_button = LocksmithButton("＋ New Instance")
        self.new_instance_button.setObjectName("vaultDrawer.newInstanceButton")
        self.new_instance_button.clicked.connect(self._new_instance)
```
and add it to the same header layout that holds `new_vault_button_container`.

> `LocksmithButton` is imported in this file already if used elsewhere; if not, add `from locksmith.ui.toolkit.widgets import LocksmithButton` at the top.

- [ ] **Step 7: Run the full drawer test + smoke the UI imports**

Run: `pytest tests/test_vault_drawer_instances.py -v && python -c "import locksmith.ui.vaults.drawer"`
Expected: PASS and a clean import (no syntax/import errors).

- [ ] **Step 8: Commit**

```bash
git add src/locksmith/ui/vaults/drawer.py tests/test_vault_drawer_instances.py
git commit -m "feat(instancing): instance-aware vault drawer rows + New Instance launcher"
```

---

## Task 9: End-to-end harness test — focus-existing + switch-in-place

**Files:**
- Create: `tests/integration/test_multi_instance.py`
- Possibly modify: the dev-control op handler (to expose current-vault state) — locate first.

This follows the project rule: fully automated + log-assisted, harness behaves like a human (drive real widgets via the dev-control Unix socket). Model the structure on `tests/integration/peer/test_export_blob_via_ui.py` and its `conftest.py` helpers (`_devctl`, `open_test_vault_via_ui`, `free_port`, the `two_wallets` fixture).

- [ ] **Step 1: Understand the existing two-process fixture**

Run: `sed -n '1,140p' tests/integration/peer/conftest.py`
Expected: read how `two_wallets` spawns two wallet subprocesses, what env/args it passes, and how `_devctl(sock, op, **kw)` talks to each. Note: the multi-instance test needs both instances to **share one base directory** (so they enumerate the same vault), unlike the peer test which isolates them. Identify the env var or config knob that sets the base (`config.base`; see `apping.environments()` reading `LocksmithBaser.TailDirPath` under `config.base`).

- [ ] **Step 2: Confirm or add a "current vault" dev-control op**

Search: `grep -rn "def \|\"op\"\|elif op" tests/ src/ --include=*.py | grep -i "devctl\|dev_control\|control" | head -40`
We need a way to assert which vault an instance has open. If a `get_current_vault` (or similar) op exists, use it. If not, add one to the dev-control op handler:

```python
# in the dev-control op dispatch (wherever existing ops like "click"/"get_text" are handled):
elif op == "get_current_vault":
    return {"ok": True, "vault": getattr(window.app, "name", None)}
```
Locate the handler by searching for an existing op string, e.g. `grep -rn '"get_text"' src/`.

- [ ] **Step 3: Write the integration test**

```python
# tests/integration/test_multi_instance.py
"""Two instances sharing one base. Verifies single-instance-per-vault:
opening a vault already open in instance #1 from instance #2 focuses #1
and does NOT open a duplicate; switch-in-place reuses one instance.
"""
import time
import pytest

# Reuse the shared-base, two-instance fixture added in conftest (Step 4).
pytestmark = pytest.mark.integration


def test_second_instance_cannot_duplicate_open_vault(two_instances_shared_base):
    devctl = two_instances_shared_base["devctl"]
    i1 = two_instances_shared_base["i1"]
    i2 = two_instances_shared_base["i2"]

    # Instance #1 opens vault "shared".
    from tests.integration.peer.conftest import open_test_vault_via_ui
    open_test_vault_via_ui(devctl, i1["sock"], name="shared")
    r = devctl(i1["sock"], "get_current_vault")
    assert r == {"ok": True, "vault": "shared"}, r

    # Instance #2 tries to open the same vault via the drawer's Open button.
    devctl(i2["sock"], "click", target="toolbar_vaults_button")  # open drawer
    devctl(i2["sock"], "wait_for", target="vaultDrawer.open.shared",
           condition="visible", timeout_ms=3000)
    devctl(i2["sock"], "click", target="vaultDrawer.open.shared")
    time.sleep(0.8)  # let the claim + raise round-trip complete

    # Instance #2 must NOT have opened the vault (it's owned by #1).
    r = devctl(i2["sock"], "get_current_vault")
    assert r == {"ok": True, "vault": None}, r


def test_switch_in_place_reuses_one_instance(two_instances_shared_base):
    devctl = two_instances_shared_base["devctl"]
    i1 = two_instances_shared_base["i1"]
    from tests.integration.peer.conftest import open_test_vault_via_ui

    open_test_vault_via_ui(devctl, i1["sock"], name="vaultone")
    assert devctl(i1["sock"], "get_current_vault")["vault"] == "vaultone"

    # Open a different, idle vault from the same instance -> switches in place.
    open_test_vault_via_ui(devctl, i1["sock"], name="vaulttwo")
    assert devctl(i1["sock"], "get_current_vault")["vault"] == "vaulttwo"
```

- [ ] **Step 4: Add the `two_instances_shared_base` fixture**

In `tests/integration/test_multi_instance.py` (or a local `conftest.py` in `tests/integration/`), adapt the existing `two_wallets` fixture to spawn **two** instances pointing at the **same** base dir. Copy the spawn/teardown logic from `tests/integration/peer/conftest.py::two_wallets`, changing only: (a) one shared `base=tmp_path` for both, (b) distinct dev-control socket paths per instance. Reuse its `_devctl`:

```python
import pytest
from tests.integration.peer.conftest import _devctl  # reuse the socket client

@pytest.fixture
def two_instances_shared_base(tmp_path):
    # Adapt from peer/conftest.py::two_wallets — SAME base for both procs.
    # ... spawn instance #1 (sock1), instance #2 (sock2), both with
    #     config base = str(tmp_path), each with its own --dev-control sock ...
    # yield {"devctl": _devctl, "i1": {"sock": sock1}, "i2": {"sock": sock2}}
    # ... terminate both procs in teardown ...
    raise NotImplementedError(
        "Copy two_wallets spawn/teardown from peer/conftest.py; share one base."
    )
```
Replace the `NotImplementedError` body with the adapted spawn code from `two_wallets` (Step 1 told you its exact shape). The only semantic change vs `two_wallets` is the shared base.

- [ ] **Step 5: Run the integration test**

Run: `pytest -m integration tests/integration/test_multi_instance.py -v`
Expected: PASS. Both instances launch sharing one base; #2 cannot duplicate #1's open vault; switch-in-place keeps a single instance on the latest vault.

- [ ] **Step 6: Commit**

```bash
git add tests/integration/test_multi_instance.py tests/integration/conftest.py src/  # include dev-control op if added
git commit -m "test(instancing): e2e two-instance focus-existing + switch-in-place"
```

---

## Task 10: Full-suite verification + manual smoke

**Files:** none (verification)

- [ ] **Step 1: Run the entire unit suite**

Run: `pytest tests/ -q --ignore=tests/integration`
Expected: all green, no regressions from the baseline in Task 0.

- [ ] **Step 2: Run the integration suite**

Run: `pytest -m integration tests/ -q`
Expected: green (or matches the known-stable integration baseline plus the new test passing).

- [ ] **Step 3: Manual smoke (dev mode)**

Run two real instances and confirm the dock groups them and focus-existing works:
```bash
python -m locksmith.main &            # instance A — open vault "alpha" via the drawer
python -m locksmith.main --vault alpha  # should raise instance A, not open a duplicate
python -m locksmith.main --vault beta   # opens beta in a new instance
```
Expected: launching `--vault alpha` while A holds it brings A to the front and the new process exits (`instance.startup.focused_existing` in logs); `--vault beta` opens a second live instance; both share one dock icon.

- [ ] **Step 4: Finalize**

Use the `superpowers:finishing-a-development-branch` skill to choose how to integrate (merge / PR / cleanup). The branch is `feat/multi-instance-vaults`; per project convention it targets `development`.

---

## Self-Review Notes (author checklist — completed)

- **Spec coverage:** process model (Tasks 3,5), Approach-A coordination (Tasks 1,2), claim-before-release switch-in-place (Tasks 4,6), `--vault` + focus-existing (Task 5), peer-port deconfliction (Task 7), instance-aware drawer + New Instance entry points (Task 8), structured logs throughout, testing incl. e2e harness (Task 9). Window title `Locksmith | <vault>` already implemented (`window.py:513`, reset at `:374`) — no task needed; verified during smoke (Task 10 Step 3).
- **Type consistency:** coordinator API is consistent across tasks — `claim`, `release`, `release_all`, `probe`, `request_raise`, `raise_window`; launcher `InstanceLauncher.launch_new`; helpers `vault_server_name`, `find_free_port`.
- **Placeholders:** the only deliberate "fill from existing code" is Task 9 Step 4's fixture, which is an explicit copy-and-adapt of a real fixture (`two_wallets`) read in Step 1 — not a vague TODO. The dev-control op in Step 2 includes complete code and a locate command.
- **Deviation from mock:** the approved mock placed "New Instance" in the top toolbar; the plan places it in the vault drawer header (grounded in real drawer code, avoids guessing toolbar icon assets). Functionally identical entry point — confirm acceptable during review or move to toolbar as a follow-up.
