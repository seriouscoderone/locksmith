# Driving the Locksmith UI in tests (agents: read this before you ask for a passcode)

**You do not need a human to type passcodes.** The test harness creates its own
vaults, with its own passcode, in its own throwaway `HOME`. Typing that passcode
is what the harness is *for*. Asking the owner to enter one by hand — for every
run, all day — is the failure mode this document exists to end.

The line, stated once:

| Situation | Verdict |
|---|---|
| A vault the harness just created under a tmpdir `HOME`, opened with `DEFAULT_TEST_PASSCODE` | **Do it.** No permission needed, ever. |
| A vault in the owner's real `~/.keri` / `~/.locksmith` | **Don't.** Ask, or use a fixture vault instead. |
| A passcode the owner told you, pasted into a real wallet | **Don't.** That's their credential, not a fixture. |

The fixture passcode is not a secret. It is a hardcoded constant checked into
this repo, used by every test wallet, and safe precisely because the `HOME` is
isolated:

```python
# tests/integration/peer/conftest.py:198
DEFAULT_TEST_PASSCODE = "DoB2-e4Rr-gVOr-Nb1Y-7yBl-gI3n-i4cB-gf07"
```

If a task needs the owner's real vault, that is a signal the test is wrong —
build a fixture vault instead. See "When you genuinely need a real vault" below.

---

## What the harness actually is

`locksmith-ui-tester` (`~/code/locksmith-ui-tester`, repo
`seriouscoderone/locksmith-ui-tester`) is an installed Locksmith **plugin**. While
a wallet is open it runs a `DevControlServer` on a UNIX socket
(`~/.locksmith-control.sock`, overridable with `LOCKSMITH_CONTROL_SOCKET`) that
accepts newline-delimited JSON:

```
client → server:  {"op": "type", "target": "createVaultDialog.passcodeField", "text": "..."}\n
server → client:  {"ok": true, "wrote_to": "QLineEdit"}\n
```

Every op executes as a **direct Qt call on the main thread** — `setText()`,
`click()` — not synthesized input events. That is why a full multi-wallet
credential exchange runs in seconds. There is no human-speed robot anywhere in
this stack, and no reason for a test cycle to take longer than the code under
test.

Tests spawn wallets with `QT_QPA_PLATFORM=offscreen`, so nothing draws on
screen. See "Watching the UI" if you want to see it.

---

## Prerequisites

1. **The plugin must be installed on the host** at `~/.locksmith/plugins/`. The
   fixtures copy that directory into each isolated `HOME`
   (`_install_plugins`, `peer/conftest.py:34`). If it is missing, peer tests
   `pytest.skip` and the roles suite skips locally / **fails in CI**
   (`roles/conftest.py:34`) — a suite that ran nothing must never report green.
2. **Run from the repo venv**: `.venv/bin/python -m pytest`.
3. **Always pass `--import-mode=importlib`** — the top-level `packaging/`
   directory otherwise shadows the real `packaging` library.

```bash
.venv/bin/python -m pytest tests/integration/peer -q --import-mode=importlib
```

---

## The fastest path: reuse a fixture

Do not hand-roll process spawning. Three fixtures already exist:

| Fixture | Where | Gives you |
|---|---|---|
| `two_wallets` | `tests/integration/peer/conftest.py:449` | Two wallets `a`/`b`, isolated `HOME` each, plus `devctl` |
| `four_wallets` | `tests/integration/roles/conftest.py:45` | Three role wallets — `cuo`, `actuary`, `designer` |
| `two_instances_shared_base` | `tests/integration/test_multi_instance.py` | Two processes sharing ONE `HOME` (instance-coordination tests) |

Each wallet entry is `{"home", "log", "sock", "proc"}`. A complete test:

```python
import pytest
from tests.integration.peer.conftest import open_test_vault_via_ui, create_aid_via_ui

pytestmark = pytest.mark.integration

def test_something_via_real_ui(two_wallets):
    devctl = two_wallets["devctl"]
    sock = two_wallets["a"]["sock"]

    open_test_vault_via_ui(devctl, sock, "mytest")   # types the passcode for you
    create_aid_via_ui(devctl, sock, "alice")

    r = devctl(sock, "get_table_rows", target="identifiersTable")
    assert any("alice" in str(row) for row in r["rows"])
```

`open_test_vault_via_ui` (`peer/conftest.py:201`) is the whole passcode story:
it clicks "Initialize New Vault", types the name and `DEFAULT_TEST_PASSCODE`,
clicks Create, and waits for the vault page to mount. The vault auto-opens after
creation — there is no second prompt.

Other ready-made drivers in the same file: `create_aid_via_ui`,
`expose_aid_via_ui`, `import_peer_blob_via_ui`, `set_peer_mode_via_ui`. The roles
conftest adds `declare_mandate_via_ui`, `attest_rate_program_via_ui`,
`grant_actuary_role_to_cuo_wallet`, and more. **Check for an existing driver
before writing one.**

---

## devctl op reference

Read from `locksmith_ui_tester/server.py` — the plugin README lists only 8 of
these and is stale. All ops take `target` unless noted.

| Op | Args | Returns / notes |
|---|---|---|
| `ping` | — | liveness |
| `screenshot` | `path`, `target?` | PNG of the window, or of one widget/dialog |
| `tree` | — | every visible widget: type, rect, text, tooltip. **Your primary discovery tool** |
| `current_page` | — | current vault sub-page key |
| `click` | `target` | by objectName / text / tooltip / `Type:N` |
| `click_list_item` | `text` | item in a `QListWidget` by its text |
| `click_table_row` | `target`, row selector | emits both `cellPressed` and `cellClicked` |
| `click_row_action` | `row_text`, `action` | the action button in a matching table row |
| `type` | `target`, `text` | into a `QLineEdit` |
| `select` | `target`, `index` or value | `QComboBox` |
| `get_text` | `target` | widget text |
| `is_checked` | `target` | checkable state (widget must be *checkable*, not merely enabled) |
| `is_visible` | `target` | distinguishes "absent" from "present but hidden" |
| `wait_for` | `target`, `condition`, `timeout_ms` | `visible` (default) or `hidden`; polls 50ms, default 5000ms |
| `count` | `target` | number of visible matches — "list has N entries" |
| `get_list_items` | `target` | list contents |
| `get_table_rows` | `target` | table contents |

### Selector grammar

Resolution order, first match wins (`server.py:799`):

1. exact `objectName` — **always prefer this**
2. exact `.text()`
3. exact `.toolTip()` (icon buttons)
4. `label_text` / `_label_text` (floating-label fields)
5. `Type:N` — the N-th visible widget of that class, e.g. `QLineEdit:0`

`occurrence=N` picks the N-th structurally identical match when a dialog has
two identical widgets.

**If a widget has no `objectName`, add one** in the same commit as the test.
That is normal, expected maintenance — the codebase is full of them
(`createVaultDialog.passcodeField`, `grantCredentialDialog.grantButton`). A test
that relies on `QLineEdit:3` breaks the next time someone adds a field.

### Waiting

Use `wait_for`, not `time.sleep`, for anything with a deterministic end state
(dialog opened/closed, page mounted). Reserve sleeps for genuinely asynchronous
network settling, and comment why.

---

## Watching the UI (debugging only)

The fixtures hard-assign `env["QT_QPA_PLATFORM"] = "offscreen"`
(`peer/conftest.py:57`, `test_multi_instance.py:67`), so **no env var can make
them visible from outside**. To watch a run, drop the key at the `Popen`
boundary with a throwaway pytest plugin — no repo edit, nothing to revert:

```python
# qpa_visible.py  (anywhere on PYTHONPATH)
import subprocess
_real = subprocess.Popen

class _Visible(_real):
    def __init__(self, args, *rest, **kw):
        env = kw.get("env")
        if env is not None and "locksmith.main" in " ".join(map(str, args)):
            env = dict(env); env.pop("QT_QPA_PLATFORM", None); kw["env"] = env
        super().__init__(args, *rest, **kw)

subprocess.Popen = _Visible
```

```bash
PYTHONPATH=/path/to/plugin .venv/bin/python -m pytest tests/integration/peer/test_fixture_smoke.py \
  -q --import-mode=importlib -p qpa_visible -s
```

Real windows appear. Expect flashes — a two-wallet test completes in ~4s.

Also useful: `LOCKSMITH_KEEP_TEST_HOMES=1` keeps every wallet `HOME` and
`<name>.log` after teardown instead of deleting them. Wallet logs are where
integration failures are actually diagnosed, and pytest truncates them out of
assertion messages.

---

## Driving a BRANDED HOA (not just vanilla)

Every fixture and driver in this file was written for vanilla Locksmith. A
branded HOA differs in three ways that each look like a broken app from outside:

| difference | what to use |
|---|---|
| no Identifiers/Credentials nav (peeled to Settings) | `landing_target(devctl, sock)` — probes identifiers / home / settings |
| no vault drawer on first run; mounts `SetupPage` | `open_vault_any_build(devctl, sock, name)` |
| grants surface on Notifications, not Credentials | `accept_grant_via_hoa_notifications(devctl, sock)` |

The HOA's accept path is DRIVABLE where vanilla's is not: vanilla admits via
`QDialog.exec()`, a modal on the thread devctl dispatches on, so the harness
deadlocks. The HOA page has no `exec()`. That is what makes a vanilla-admin ->
HOA-recipient test possible at all.

An HOA also trusts only the authority its EGF pins, so a spawned test admin's
grants satisfy nothing until you mint an ecosystem the suite owns —
`tests/integration/peer/testegf.py` and the `admin_then_two_hoas` fixture. It
spawns in two phases because it must: the EGF cannot be derived until the admin
holds an AID.

To WATCH a run across monitors, set `LOCKSMITH_TEST_WIN_ORIGINS="x,y;x,y;..."`
(one origin per wallet, in spawn order) alongside `-p qpa_visible`.

## Traps that cost hours

- **Vault names must be unique across wallets.** `HOME` isolation does *not*
  isolate the instance coordinator: it claims a `QLocalServer` named
  `vault_server_name(base, vault)` (`core/instancing.py:70`), and local-socket
  names live in a **system-wide** namespace. Two wallets opening the same vault
  name is genuinely "one vault, two processes" — the second claim is denied, the
  wallet falls back to the **modal** passcode dialog, and that modal blocks its
  Qt event loop so the control socket stops answering. The symptom is an opaque
  `TimeoutError` from the *next* devctl call, pointing nowhere near the cause.
  Use distinct names (`"ptest"` / `"ptest_b"`).
- **A modal dialog starves the control socket.** Any unexpected modal hangs the
  harness. If devctl goes silent, screenshot before you theorize.
- **The `integration` marker is declared "opt-in" but nothing enforces it.**
  There is no `addopts` deselecting it, so a bare `pytest` runs the full
  multi-wallet suite (~4 min, ~29 spawned processes). Scope your runs to a path.
- **Worktree venv is a shared mutable.** There is ONE venv, at the main
  checkout. Running tests from a worktree is fine (`pythonpath` resolves the
  worktree's `src`), but do **not** `pip install -e .` from a worktree — it
  rewrites the editable `.pth` and repoints every other worktree at your branch.
  See CLAUDE.md § Running tests.
- **The plugin README is stale.** It documents 8 ops; the server implements 17.
  Read `server.py`.
- **Never blind-retry a dialog click.** A retry loop that re-clicks without
  checking opened TEN stacked `AddPeerDialog`s. Probe `is_visible` first; click
  only when nothing is open; dismiss before retrying.
- **macOS UNIX sockets cap at ~104 chars.** pytest's `tmp_path` is too deep for
  the devctl socket — the wallet starts and the socket never appears. Use a short
  `mkdtemp` prefix (the fixtures do).
- **A wallet with no `LOCKSMITH_BRAND_CONFIG` is not fully vanilla.**
  `load_brand()` falls back to the packaged `release/brand.json` (`egf: {}`, so
  functionally vanilla), but `_brand_source_dir` is `release/` — it renders with
  whatever assets `brand_apply` last baked. Expect Usurance icons on a "vanilla"
  wallet in this checkout.
- **`ensure_direct_transport`'s auto-expose is HOA-only.** A vanilla wallet is
  exposed through its View Identifier dialog, not automatically.

---

## When you genuinely need a real vault

Almost never. If a test needs an identity with real history, build it in the
fixture rather than borrowing the owner's: `roles/conftest.py:221`
(`_build_test_admin`) constructs a test admin AID precisely so the suite never
touches `usurance-admin`, which is a real, passcode-protected operator identity.
Follow that pattern. If you conclude you truly cannot, stop and ask the owner —
with the specific reason the fixture path fails.
