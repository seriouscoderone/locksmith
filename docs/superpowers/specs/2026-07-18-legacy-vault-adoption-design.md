# Legacy Vault Adoption on Launch — Design

**Date:** 2026-07-18
**Repo:** locksmith (`development`)
**Status:** Approved (design), pending implementation plan
**Owner:** Joseph Hunsaker

## Problem

`LocksmithApplication.environments()` (`src/locksmith/core/apping.py`) lists the vault
drawer solely from Locksmith's runtime-database directory (`/usr/local/var/keri/rt/<base>`
or `~/.keri/rt/<base>`). A vault created **before** the drawer was repointed to `rt/`
(commit `904f2578`, 2026-04-01) that has **not** been reopened since has no `rt/<name>`
entry, so it is invisible in the drawer. Because the drawer is the only way to open a
vault, such a vault can never be opened — and therefore never earns its `rt/` entry — from
the UI. It is permanently stranded.

Confirmed real cases on the development host: the `Utah State` DOI vault and `Carrier`,
both needed for the HOA #2 demo. They exist under `~/.keri/db/`, `~/.keri/ks/`, and
`~/.keri/mbx/` but have no `~/.keri/rt/` entry. The demo was unblocked with a manual
`mkdir -p ~/.keri/rt/"Utah State"`; this design makes that automatic and correct.

### Why the drawer lists `rt/` and not `db/`

`db/` is shared: command-line KERI tools (`kli`) and test scripts write scratch
environments there too. The development host has ~1785 `db/` entries, nearly all junk
(`anchoring-…`, `bad-sig-kli-…`). The 2026-04-01 repoint to `rt/` was deliberate — only
Locksmith writes `rt/`, so witnesses and `kli` debris stay out of the drawer. The fix must
preserve that property: it must surface real dormant vaults **without** reintroducing junk.

### Why it stayed latent until now

A vault created after 2026-04-01 gets its `rt/` entry the moment `create.py` auto-opens it;
a pre-April vault reopened after the repoint got one lazily on that open. The steady-state
population self-heals. Only a vault that is **both** older than the repoint **and** dormant
since is stranded — exposed now because the HOA #2 demo needed two specific long-dormant
vaults.

## Detection rule

A directory name `N` is a **legacy Locksmith vault** under a given KERI head dir `H`
(with configured sub-base `B`, empty by default) when all of:

- `H/keri/db/B/N` is a directory (the KEL/history database exists), **and**
- `H/keri/ks/B/N` is a directory (the keystore / private keys exist), **and**
- `H/keri/mbx/B/N` is a directory (a mailbox exists → the vault was opened at least once
  as a wallet/agent), **and**
- `H/keri/rt/B/N` does **not** exist (not yet adopted).

`db ∩ ks ∩ mbx` is the discriminator: it means "created by a wallet-like app **and** opened
at least once." On the development host it matches exactly the real vaults (13 including
`Utah State`, `Carrier`) and **zero** of the ~1780 `kli`/test entries, which have `db`+`ks`
but no `mbx`. All checks are pure directory `is_dir()` tests — no LMDB opens, no locks.

**Known limitation (documented, accepted):** a locally-run witness or agent also creates a
mailbox, so it would match. None exist under the development host's HOME today, and any
false adoption is reversible by deleting the stray `rt/<name>` directory. Any heuristic
strong enough to exclude `kli` junk necessarily also excludes non-mailbox keystores; this
is the deliberate trade the owner approved.

Head-dir handling mirrors keripy `LMDBer`: `/usr/local/var` is preferred, `~` is the
fallback. The rule is evaluated **per head dir** — `db/ks/mbx/rt` for a given `N` are all
resolved under the *same* `H` — so the two install layouts never cross-contaminate. Tail
paths are taken from the owning classes, never hardcoded: `keri/rt` from
`LocksmithBaser.TailDirPath`/`AltTailDirPath`, `keri/db` from keripy `dbing.LMDBer`,
`keri/ks` from keripy `keeping.Keeper`, `keri/mbx` from keripy `storing.Mailboxer`.

## Approach: adopt on launch

Chosen over two alternatives:

- **Union inside `environments()`** (read-only, no writes) — rejected: the heuristic would
  run on every listing forever, matched junk would show forever (never converges), and any
  other reader of `rt/` still misses legacy vaults.
- **One-time migration with a completion marker** — rejected: a vault restored from backup
  or copied from another machine *after* the marker is written stays invisible — the exact
  bug, recurring.

Adopt-on-launch backfills the missing `rt/<name>` directory once per launch for every name
matching the detection rule. `environments()` stays a pure read of `rt/`. It is
self-healing (a restored backup reappears on the next launch) and converges: once a vault
is adopted and opened, it is fully `rt/`-native and the heuristic never touches it again.
This does for dormant legacy vaults exactly what a normal open already does for every other
vault.

## Components

### 1. `_vault_head_dirs(base="") -> list[Path]` (module-level helper, `apping.py`)

Returns the candidate KERI head dirs (`/usr/local/var`, `~`) that currently exist, in
keripy preference order, evaluated per call (not at import). Single source of truth for
both `environments()` and the adopter, so the two can never drift. `base` is the configured
sub-base.

### 2. `find_legacy_vaults(base="", heads=None) -> list[str]` (module-level, `apping.py`)

Pure query. Applies the detection rule across the head dirs and returns the sorted names of
un-adopted legacy vaults. `heads` overrides the head dirs for testing. **No Qt, no `self`,
no PySide import, no side effects** — a host-agnostic function so a future Universal CLI can
reuse the same predicate rather than reinventing one (see Framework implications).

### 3. `adopt_legacy_vaults(base="", heads=None) -> list[str]` (module-level, `apping.py`)

Calls `find_legacy_vaults`, then for each name creates the missing `rt/<base>/<name>`
directory (`Path.mkdir(parents=True, exist_ok=True)` — the same effect as the manual
workaround; the LMDB files inside are created later by the normal open path). Logs each
adoption and a one-line summary. Per-name failures are caught, logged, and skipped; the
whole function is wrapped so it can never raise into app startup. Returns the adopted names.
Also host-agnostic (no Qt/`self`).

### 4. Hook in `LocksmithApplication.__init__`

After `self.config` is set (~line 227), call
`adopt_legacy_vaults(base=getattr(self.config, "base", "") or "")` inside a
try/except that logs and swallows any error. `LocksmithApplication` is constructed at
`ui/window.py:68`, which runs **before** the onboarding gate (`window.py:232`), the drawer
(`ui/vaults/drawer.py:439`), and the HOA bootstrap (`core/bootstrapping.py:85`) — so all
three `environments()` consumers observe adopted vaults with **no changes to them**.

### 5. `environments()` — minimal change

Refactored only to source its head dirs from `_vault_head_dirs()` (shared seam). Behavior
is otherwise unchanged: still a pure read of `rt/`. Docstring gains a one-line note that
legacy vaults are adopted at launch by `adopt_legacy_vaults`.

## Data flow

```
LocksmithApplication.__init__
  └─ adopt_legacy_vaults(base)
       └─ find_legacy_vaults(base)  →  [names matching db∩ks∩mbx − rt]
       └─ for name: mkdir rt/<base>/<name>
  … later, unchanged …
  window onboarding gate / drawer / bootstrap
       └─ environments()  →  reads rt/  →  now includes adopted vaults
```

## Error handling

- Missing head dirs → treated as empty; never an error.
- A candidate present in `db`+`ks`+`mbx` but not adoptable (e.g. `rt/` mkdir fails on a
  permission error) → logged, skipped, launch continues.
- The entire adopt step is wrapped at the call site so no filesystem anomaly can block app
  startup. Worst case: the drawer is exactly as it is today (missing the legacy vault), plus
  a log line.

## Testing

New focused file `tests/test_apping_environments.py` (matches the `tests/test_apping_*.py`
convention). **Offscreen-safe, pure-filesystem, no Qt widgets, no `tests/peer/`, no
subprocess.** Runs as:

```
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest \
  tests/test_apping_environments.py -q --import-mode=importlib
```

Each test builds a fake KERI head dir under `tmp_path` (creating `keri/db/…`, `keri/ks/…`,
`keri/mbx/…`, `keri/rt/…` subdirs as needed) and drives the module functions directly with
`heads=[tmp_path]` (and a `base` where relevant). Cases:

1. **Adopts a legacy vault** — `db`+`ks`+`mbx`, no `rt` → `find_legacy_vaults` returns it;
   `adopt_legacy_vaults` creates `rt/<name>`; a subsequent `find` returns `[]`.
2. **Ignores `kli` junk** — `db`+`ks` only (no `mbx`) → never adopted.
3. **Ignores mailbox-only orphan** — `mbx` only → never adopted.
4. **Idempotent** — a second `adopt_legacy_vaults` run is a no-op and returns `[]`.
5. **Already-`rt` vault untouched** — full `db`+`ks`+`mbx`+`rt` → not in `find` output.
6. **Honors `base`** — vaults under `keri/db/<base>/…` etc. are matched/adopted under
   `rt/<base>/…`, and a bare-root vault is not matched when `base` is set.
7. **`environments()` reflects adoption** — after adopting into a `tmp_path` head, calling
   `environments()` lists the adopted name. To stay Qt-free, this invokes `environments()`
   against a minimal duck-typed stub exposing only `.config.base` (i.e.
   `LocksmithApplication.environments(stub)`), with `_vault_head_dirs` monkeypatched to
   return `[tmp_path]`. No `LocksmithApplication.__init__`, no Qt window is constructed.

No coverage of `LocksmithApplication.__init__` wiring via a live window (that path pulls in
Qt/bootstrap and is covered by existing app tests); the unit tests exercise the module
functions the hook delegates to.

## Framework implications (Universal CLI mirror) — noted future work, out of scope

Locksmith is the Universal App; the Universal Micro-App CLI (`concierge_api_local/cli/`) is
intended to mirror it. Today the CLI is **path-addressed** — it opens a keystore named
explicitly via `--vault-path` + `--aid` using stock keripy `Habery` (not `LocksmithBaser`),
and never *lists/discovers* vaults. So `/rt` cannot currently cause CLI divergence: only a
surface that scans a directory to discover vaults is affected, and the drawer is the only
such surface.

Divergence appears **when the CLI grows discovery** (a `list` / `open-by-name` command that
"mirrors Locksmith"):

1. **List divergence** — if the CLI discovers from `db/` while Locksmith reads `rt/`, the
   two show different vault sets. Both must use one shared predicate, not per-surface
   heuristics.
2. **Create divergence (this bug, mirrored)** — a vault the CLI creates via stock `Habery`
   gets `db`+`ks` but no `rt/`, so it is invisible in the drawer until adopted. The
   adopt-on-launch fix rescues a CLI vault *once it has been hosted* (a mailbox appears); a
   build-only keystore is not adopted — arguably correct (not a user vault), but this is the
   seam to be aware of.

**Durable fix (future, framework-level):** when vault lifecycle unifies, a persistent vault
created by any Universal surface should *write* its `rt/` entry on creation, so both surfaces
share one **native** source of truth and the heuristic adopter degrades to a legacy-only
migration. The natural home for a shared discovery/predicate function is the planned EGF
substrate library (`docs/superpowers/plans/2026-07-16-egf-substrate-library-cli.md`), not
locksmith. This design keeps `find_legacy_vaults`/`adopt_legacy_vaults` Qt-free and
dependency-light so they can be lifted there later; it does **not** build CLI discovery now
(YAGNI).

## Out of scope

- CLI-side vault discovery, and any shared cross-repo substrate library (future work above).
- Cleaning up or migrating the ~1780 `kli`/test `db/` entries.
- Changing how vaults are created or opened; changing `LocksmithBaser`.
- Any change to `environments()` behavior beyond the shared head-dir seam.
```
