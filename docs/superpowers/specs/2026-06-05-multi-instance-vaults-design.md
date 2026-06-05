# Multi-Instance Vaults — Design Spec

**Date:** 2026-06-05
**Branch:** `feat/multi-instance-vaults` (worktree off `development`)
**Status:** Approved design, ready for implementation planning

## Summary

Let users run **multiple instances of Locksmith simultaneously**, each opened on a
different **vault**, the way VS Code runs multiple windows or Chrome runs multiple
profiles. The OS dock/taskbar groups them under one app icon automatically (same
bundle). Each instance is a separate OS process with its own open vault, its own
peer-mode TCP listener, and its own keystore.

A **vault is the "context"/"role"** — the unit a single instance opens. There is **no
change to `HOME` or the data base directory**: storage is already vault-scoped (keyed
by vault name), so the vault name *is* the context key.

The two genuinely new pieces of behavior:

1. **Single-instance-per-vault coordination** — opening a vault that is already open
   in another instance focuses that instance instead of launching a duplicate (the
   VS Code "open folder → raise existing window" behavior). This also guarantees two
   processes never write the same LMDB environment.
2. **Peer-port deconfliction** — two concurrently open vaults must not both bind the
   default peer port 5621.

## Background / current state (verified)

- App is Python + PySide6 (Qt6) + qasync; entry point `src/locksmith/main.py`.
- **No single-instance enforcement** today, and no UI to launch a second instance.
- A vault = one keripy `Habery`, opened as `Habery(name=<vault>, base=<base>)` in
  `src/locksmith/core/habbing.py`. The base defaults to `~/.keri` (overridable via
  `LocksmithConfig.base`).
- **State is already vault-scoped** and safe for concurrent *different*-vault access:
  - keripy keystore: `<base>/<vault>/` (separate LMDB per vault)
  - `LocksmithBaser` (`keri/rt`): instantiated `name=self.hby.name` → separate LMDB
    (`src/locksmith/core/vaulting.py:66`)
  - OTP secrets (`keri/locksmith`): vault-scoped
  - plugin enable-list: per-vault path (`<keri_base>/locksmith/plugin-enable.json`)
  - plugin index (`~/.locksmith/plugins/index.json`): global but already file-locked
    for atomic multi-process access
- **Collision risks for concurrent instances:**
  - peer listener port: per-vault setting but **defaults to 5621** for every vault
    (`src/locksmith/peer/records.py`)
  - no coordination mechanism for single-instance-per-vault
- Vault selection UI exists: a right-side **vault drawer**
  (`src/locksmith/ui/vaults/drawer.py`) listing vaults enumerated from the `keri/rt`
  directory; opening prompts for passcode + optional 2FA (`OpenVaultDialog`).
- A **relaunch mechanism already exists** (used for plugin updates,
  `src/locksmith/ui/window.py:343`) that spawns a new process with the same args.
- macOS bundle does **not** set `LSMultipleInstancesProhibited`, so `open -n` can
  launch a second instance.

## Decisions

- **Unit of an instance:** one vault per instance. ✅
- **Process model:** separate OS processes (true instances), not multiple windows in
  one process. OS handles dock/taskbar grouping. ✅
- **Coordination mechanism:** **Approach A — per-vault `QLocalServer`** (decentralized;
  each vault is its own coordination channel; LMDB write-lock as backstop). ✅
- **Default open behavior:** **switch in place** (close current vault, open the picked
  one in the same instance). "Open in new instance" is an explicit action. ✅
- **No `HOME`/base fork:** vault name is the context key. ✅
- **Secondary action UI:** **split button** — primary `Open` (switch-in-place) with a
  `▾` caret dropdown for `Open in New Instance`. ✅

## Architecture

### New module: `src/locksmith/core/instancing.py`

**`InstanceCoordinator`** — owns the per-vault `QLocalServer` lifecycle for the vault
this instance currently holds.

- **Server name derivation:** `locksmith.vault.<hash(base + name)>`, prefixed with the
  app bundle id (`host.keri.locksmith`) to avoid cross-app collisions. Hashed to stay
  within local-socket name length/character limits and to be stable across launches.
- **`claim(vault) -> bool`:**
  1. `QLocalSocket.connectToServer(name)` with a short timeout.
  2. **Connects** → another live instance owns the vault → send a `raise` message →
     return `False`.
  3. **Fails to connect** → `QLocalServer.removeServer(name)` (clears a stale socket
     left by a crashed owner; safe because no live listener answered) → `listen(name)`
     → return `True`. `listen` is atomic, so simultaneous claims have exactly one
     winner.
- **Incoming connection handler** (someone tried to open *our* vault): bring our window
  forward — `show(); raise_(); activateWindow()` — and request user attention
  (`QApplication.alert` / platform dock bounce). This is the "focus existing" behavior.
- **`release()`:** `QLocalServer.close()` + `removeServer(name)` when the vault closes.
- **`probe(vault) -> bool`:** non-owning liveness check (a `connectToServer` that
  disconnects immediately) used by the drawer to render "running in another instance"
  badges. Cheap because local sockets answer immediately.

### New: `InstanceLauncher` (in `instancing.py` or alongside it)

`launch_new(vault | None)` spawns a new OS process of the same app, reusing/extending
the existing relaunch code at `src/locksmith/ui/window.py:343`:

- macOS frozen: `open -n <App>.app --args --vault <id>` (`-n` forces a new process)
- Windows/Linux frozen: `subprocess.Popen([exe, "--vault", id])`
- dev: re-exec `python -m locksmith --vault <id>`

`vault is None` → launches a fresh instance that starts at Home.

### `main.py` argument handling

- Parse `--vault <id>` (and bare launch = start at Home, as today).
- On `--vault`: after the passcode prompt, route the open through the coordinator
  (see Open flow). If the claim is denied (already open elsewhere), the owner was
  already raised by `claim`; this process exits cleanly.

### Open flow (claim-before-release, switch-in-place)

Opening vault **V** from the drawer/dialog:

1. `claim(V)` **while the old vault is still open**.
2. **Granted** → release+close the old vault (which calls its `release()`), open V,
   set window title `Locksmith — <V>`, start V's peer listener.
3. **Denied** → the owner instance was raised by `claim`; show a toast
   *"V is already open in another instance"*; keep the current vault open.

This ordering means there is never a window where the old vault is closed but the new
one failed to open.

**"Open in New Instance"** simply calls `InstanceLauncher.launch_new(V)`. The child
process runs its *own* `claim(V)`, so it too honors single-instance-per-vault: if V is
already open, the child raises the owner and exits.

### Peer-port deconfliction

- **New default:** when peer mode is **first enabled** for a vault, auto-select a free
  port by probing upward from 5621 and persist it in that vault's `PeerModeSettings`.
  Existing vaults keep whatever port they already have.
- **Bind failure at startup does not silently rebind** — the advertised port is baked
  into published OOBI/role-location records, so silently changing it would break peer
  discovery. Instead, surface an actionable error in the peer settings section
  (`src/locksmith/ui/vault/settings/peer_section.py`): *"Port N is in use, possibly by
  another open vault"* with a **"pick a free port"** helper button.

### UI changes

- **Window title** reflects the open vault: `Locksmith — <vault>`; `Locksmith` when no
  vault is open. (`src/locksmith/ui/window.py`)
- **Vault drawer** (`src/locksmith/ui/vaults/drawer.py`):
  - Each row shows status: **● Open in this instance** (current),
    **◆ Running in another instance** (with a **Switch to ↗** button that focuses the
    owning instance via `claim`'s raise path), or **Not open**.
  - Header summary: e.g. *"3 vaults · 2 running"*.
  - Idle rows use a **split button**: primary **Open** (switch-in-place) + **▾** caret
    dropdown with **Open in New Instance ↗**.
  - Running detection uses `InstanceCoordinator.probe()` per row on drawer open.
- **Toolbar**: a **＋ New Instance** button → `launch_new(None)` (fresh instance at
  Home).

## Error handling

- **Claim race:** atomic `listen` chooses one winner; loser falls back to connect+raise.
  LMDB write-lock is the final backstop — if two processes ever opened the same vault,
  the second LMDB writer errors; surface as a fatal *"vault busy"* and close.
- **Stale socket (crashed owner):** `connect` fails (no listener) → `removeServer` +
  `listen` recovers. The dead process's LMDB lock is released by the OS on process death.
- **Launch failure** (`open -n`/Popen fails): toast + structured log; no state change.
- **Peer port bind failure:** surfaced in the peer section as above; no corruption.

## Testing

Per project rule: **fully automated + log-assisted**, harness behaves like a human
(click + screenshot + type real widgets; no RPC shortcuts).

- **Unit (`InstanceCoordinator`):** claim → grant, claim → deny when owned,
  stale-socket recovery, deterministic name derivation, `probe` liveness. Use temp
  socket names.
- **Integration (dev-control harness, real UI):**
  - Launch instance #1, open vault A. Launch instance #2, attempt to open A → assert #2
    raises #1 and exits. Verify via structured logs:
    `instance.claim.granted`, `instance.claim.denied`, `instance.raise.requested`,
    `instance.raise.received`.
  - Switch-in-place: open A then B in the same instance → assert A released, B claimed
    (`instance.release` + `instance.claim.granted`).
  - "Open in New Instance" on an idle vault → assert a second process starts and claims.
  - Peer port: enable peer mode on two vaults → assert distinct ports auto-selected;
    force a collision → assert the actionable error log/UI state.
- **Structured log lines** added for every coordination event so automation can assert
  state it can't otherwise observe.

## Out of scope (YAGNI for v1)

- Multiple windows *within* one instance (we use separate processes).
- A central supervisor/launcher process (Approach C) — rejected.
- Cross-machine instance awareness.
- Persisting/restoring the set of open instances across app restarts (could be a later
  "reopen last session" feature).
- Per-instance theming or window-geometry persistence.

## Open naming question (non-blocking)

User-facing label for the action and concept. Candidates: **"New Instance"** (precise),
"New Window" (familiar but technically inaccurate), "Workspace"/"Space". Current mockups
use **"New Instance"** / **"Open in New Instance"**. To be finalized during
implementation; does not affect architecture.
