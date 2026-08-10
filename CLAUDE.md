# CLAUDE.md — Locksmith

Locksmith is a desktop **KERI key wallet** (PySide6 UI over a transport-agnostic `src/locksmith/core/`).
This file captures conventions and gotchas that aren't obvious from the code. Keep it short and accurate.

## Guiding principle: BE KERI NATIVE (LAW)

For any KERI-core or KERI-adjacent concept, use KERI's **own** primitives — never a generic substitute.
Canonical case: authz is **represented by credentials** (AIDs / ACDC edges / key-state, verified by
IPEX + KEL/TEL), **never computed** by a general expression language or app-logic predicate. Generic
expression languages are for non-KERI app logic only (validation, state guards, projections). If a
KERI-core concept is being handled non-natively, that's a smell — stop and find the primitive.
Full rationale: `../ugard/docs/canon/be-keri-native.md` (previously `docs/BE-KERI-NATIVE.md` in the `locksmith-micro-app-designer` repo).

## Running tests

- Venv: `.venv/bin/python` at the repo root.
- **Dev install:** `pip install -e .[test]` installs the runtime deps plus the test
  toolchain (`pytest`, `pytest-qt` for the `qtbot` fixture, and the publisher runtime
  deps `click`/`fido2`/`boto3` that `tests/integration/test_publisher_roundtrip.py`
  needs — it bootstraps `tools/publisher/src` onto `sys.path` rather than installing
  the publisher package). Do **not** plain `pip install -e tools/publisher` to get those:
  its unpinned upstream `keri` git dep conflicts with the fork pinned in `[project]`.
- **Restoring the `locksmith-publisher` CLI after a venv rebuild.** A fresh `pip install -e .`
  does NOT install the separate `tools/publisher/` package, so the `locksmith-publisher` console
  script disappears (off-CI publishing breaks with `No such file or directory`). Restore it with
  `pip install -e tools/publisher --no-deps` (the `--no-deps` avoids its stale **upstream** keri dep
  clobbering the fork) plus its runtime deps `pip install click boto3 fido2 requests` (none depend on
  keri). Then `.venv/bin/locksmith-publisher --help` works and the fork keri is untouched.
- **Plugin entry-point groups.** In-tree plugins are declared in TWO groups:
  `locksmith.plugins` (default-on) and `locksmith.plugins.composed` (loaded only when the
  active brand lists them under `[plugins] bundled`). The *group* carries that policy
  because it must be readable before the module is imported. After changing either group
  in `pyproject.toml`, **re-run `pip install -e .`** — entry-point metadata is snapshotted
  at install time, so a stale dist-info silently hides a plugin. See
  `docs/superpowers/specs/2026-07-25-plugin-origin-strategy-design.md`.
- **Always pass `--import-mode=importlib`.** The repo has a top-level `packaging/` directory (wix/installer
  assets) that otherwise shadows the real `packaging` library on `sys.path`, giving a spurious
  `ModuleNotFoundError: packaging.version`.
  Example: `.venv/bin/python -m pytest tests/unit/update -q --import-mode=importlib`
- The release **publisher** is a separate package under `tools/publisher/` with its own `pyproject.toml`
  (`pythonpath=["src","."]`); run its tests from `tools/publisher/`.
- **Worktree caveat:** the venv installs `locksmith` editable pointing at the MAIN checkout's `src/`. Tests
  run from a worktree root pick up the worktree's `src` via pytest's `pythonpath`, but code that bare-imports
  `locksmith` (e.g. publisher tests importing `locksmith.update`) resolves the MAIN tree. To validate
  cross-package changes against the real tree, merge to `development` and run there.
- **Worktree venv isolation (agents: read this).** There is ONE venv, at the main checkout's `.venv`, and
  worktrees do not get their own. `__editable__.locksmith-*.pth` holds an **absolute** path to
  `<main>/src`, so it is a **shared mutable**: running `pip install -e .` from a worktree rewrites that
  `.pth` to the worktree's `src` and silently repoints the main checkout **and every other worktree** at
  your branch. With several worktrees live (`git worktree list`) that is a cross-contamination bomb, and
  it is easy to hit by accident because the plugin-entry-point note above *tells* you to re-run
  `pip install -e .`.
  Rules for work done in a worktree:
  1. **Default: do not run `pip install -e .` (or `pip install`/`pip uninstall` of anything) against the
     shared venv.** Running tests is fine — `pythonpath` already resolves the worktree's `src`.
  2. If the change **requires** a reinstall (adding/renaming a plugin entry-point group, changing deps),
     build an isolated venv **inside the worktree** (`python -m venv .venv && .venv/bin/pip install -e .[test]`)
     and use it. The pinned `keri` fork is a git dep, so expect a slow first install.
  3. If you deliberately touch the shared venv anyway, **say so explicitly in your final report** so the
     next agent knows the state changed.

## Driving the UI in tests — agents MAY type the fixture passcode

Locksmith's UI is machine-drivable: the `locksmith-ui-tester` plugin exposes a JSON-over-UNIX-socket
control surface (`click`, `type`, `select`, `wait_for`, `screenshot`, 17 ops total) that the
integration fixtures use to run real, multi-process wallet scenarios in seconds.

**Do not ask a human to enter passcodes for test runs.** The harness creates its own vaults, under a
throwaway tmpdir `HOME`, with a hardcoded fixture constant
(`DEFAULT_TEST_PASSCODE`, `tests/integration/peer/conftest.py:198`). Typing it is what the harness is
for, and it needs no permission — it is a checked-in constant, not a credential. `open_test_vault_via_ui()`
does the whole create-and-open flow for you.

The line: **fixture vault under an isolated `HOME` → type it freely. The owner's real vault
(`~/.keri`, `~/.locksmith`) or a passcode they told you → don't.** Needing the latter means the test is
wrong; build a fixture vault instead (`roles/conftest.py:221` `_build_test_admin` exists for exactly this).

Full guide — fixtures to reuse, the op/selector reference, how to make the windows visible, and the
traps (duplicate vault names deadlock the control socket; modals starve it): **`docs/development/ui-driven-testing.md`**.

## KERI communication model (read before touching witnessing / receipts)

Field guide: `~/code/ugard/docs/canon/keri-communication-model.md`. The load-bearing rule: a witness `/` event POST returns
**`204`**; the receipt comes back via the synchronous **`/receipts`** endpoint (keripy `agenting.Receiptor`)
or a mailbox SSE poll — **never on the event POST**. `agenting.WitnessReceiptor` encodes the direct-mode
"push the receipt back on the connection" model and **hangs over HTTP**. Collect receipts with
`Receiptor` / `vault.receiptor` — which is what `InceptDoer`, `RotateDoer`, and `ConfirmDoer` all do.

## macOS signing + notarization happen ONLY on CI (agents: read before "just building it")

**There are no Apple signing credentials on the developer machine, by design.** Don't go looking
for them, don't ask the owner for a profile name, and don't try to sign locally — all three have
burned a session already.

- `KC_PROFILE` is **derived, never chosen**: `release.ci.yml` sets it to the brand's bundle id
  (`packaging && python -m brandlib id bundle_id` → `host.keri.locksmith` / `com.usurance.wallet`).
  There is nothing to guess.
- That keychain profile **does not exist locally**. CI creates it per run with
  `xcrun notarytool store-credentials "$KC_PROFILE"` from the Apple secrets, and imports the
  Developer ID `.p12` from `secrets.DEVELOPER_ID_APP_CERT`. Locally,
  `xcrun notarytool history --keychain-profile <bundle-id>` answers
  *"No Keychain password item found"* — that is the expected, correct state.
- A Developer ID identity **being visible in `security find-identity`** does not mean it is usable:
  `codesign` from a non-interactive agent shell fails `errSecInternalComponent` because it cannot
  prompt for keychain access. The build still completes and PyInstaller's **ad-hoc** signature
  stays on the bundle, so `codesign -dv` reports `Signature=adhoc` / `TeamIdentifier=not set`.
  **Always check that, never assume a build signed.**
- So the local path is a **test build, not a release build**:
  `LOCKSMITH_LOCAL_TEST_BUILD=1 bash packaging/build-macos.sh` skips Developer ID signing and
  notarization and produces everything else identically — PyInstaller bundle, Sparkle.framework,
  the brand's DMG window. Right for checking a cut; refused by Gatekeeper anywhere else.
  `scripts/devbuild-macos.sh` is the older, narrower variant (unsigned `.app`, **no DMG**).
- Real artifacts come from the `release.ci.yml` brand matrix, triggered by **creating a GitHub
  Release** (not by pushing a tag). Publishing (appcast + KEL anchor) is off-CI and belongs to the
  owner's long-lived PUBLISHER session.

## Release publisher + update verification

- The publisher (`tools/publisher/`) is a thin pipeline over keripy **`kli`**: `kli incept` / `kli interact`
  + a **programmatic `Receiptor`** for receipt collection (NOT `kli --receipt-endpoint` — that broke on the
  v2 base; see `backlog/2026-07-28-kli-oobi-resolve-persists-nothing-on-v2.md` for the related v2 trap:
  `kli oobi resolve` exits 0 but persists no loc/end records) + `publish.anchor_release` (KEL export via
  `db.clonePreIter`, wigs inline) + `appcast.build_appcast` + `s3 upload_release`. The release seal anchored
  in the ixn `a` field is `{"release": {"v": <ver>, "artifacts": [{"platform": <p>, "sha256": <hex>}, ...]}}`.
- The verifier (`src/locksmith/update/verify.py`, `update/kel_replay.py`) replays the published `kel.cesr`
  (Kevery + `db.wigs` toad check) and binds the downloaded artifact's digest. It is correct — don't break it.
- **Privacy / config injection — no personal domains or AIDs are committed.** The trust anchor
  (`src/locksmith/release/publisher_anchor.json`) and the federation/CDN `deploy_config.json` are
  **gitignored**; committed `*.example.json` templates carry only `example.com` placeholders; the real files
  are build-injected (`$LOCKSMITH_PUBLISHER_ANCHOR` / `$LOCKSMITH_DEPLOY_CONFIG`, else the gitignored file,
  else the example). CI/release builds MUST inject the real files (the PyInstaller specs assume the path).
- The in-app updater verify gate (`core/apping.py`) is wired but stays **dark** (non-enforcing) until a real
  publisher anchor is injected.
- **NEVER relabel `keri.__version__`.** keripy gates DB open on `db.version == __version__`
  (`keri/db/basing.py` `Baser.current`): existing keystores/vaults were created under the current string,
  and any change drops them out of the exact-match path into the migration gate → `DatabaseError:
  Database migrations must be run` → the publisher keystore AND every shipped user vault fail to open.
  So the keripy fork's `__version__` MUST stay `2.0.0-dev6`. The **fork identity** is carried Locksmith-side
  instead: `build_info.KERIPY_COMMIT` (stamped by the build scripts from the `keri @ …@<sha>` pin in
  `pyproject`), shown in About/logs as `keripy: kerihost @ <sha> (KERI 2.0)`. Pin keri by exact commit
  (not `@development`) for reproducible builds.
- **Multi-brand cuts (Phase 3).** One signed `vX.Y.Z` tag builds BOTH brands via the `brand` matrix in
  `release.ci.yml`; each brand's DMG/MSI lands under its own S3 prefix (`releases/…` for locksmith,
  `usurance/releases/…` for usurance). Publishing (appcast + KEL anchor) stays off-CI and is run **once per
  brand**: `LOCKSMITH_BRAND=<brand> locksmith-publisher anchor …` then `… publish …`, so each brand's appcast
  (its `[urls].appcast_*`) points at that brand's artifacts.

## Design docs

Specs/plans live in `docs/superpowers/{specs,plans}/`. Recent: publisher rebuild
(`2026-06-17-publisher-rebuild-kli*`), ConfirmDoer→Receiptor + keripy #1423 removal
(`2026-06-16-confirmdoer-migration-1423-removal*`).

## Infra note

The serverless KERI infrastructure (witnesses/mailboxes, the KEL oracle, Service-AID) lives in the **keripy
fork** (`~/code/keripy`, deployed via `keri_cdk`), not here. Locksmith depends on stock keripy APIs only.
