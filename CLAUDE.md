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
  the publisher package). Do **not** `pip install -e tools/publisher` to get those:
  its unpinned upstream `keri` git dep conflicts with the fork pinned in `[project]`.
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

## KERI communication model (read before touching witnessing / receipts)

Field guide: `~/code/ugard/docs/canon/keri-communication-model.md`. The load-bearing rule: a witness `/` event POST returns
**`204`**; the receipt comes back via the synchronous **`/receipts`** endpoint (keripy `agenting.Receiptor`)
or a mailbox SSE poll — **never on the event POST**. `agenting.WitnessReceiptor` encodes the direct-mode
"push the receipt back on the connection" model and **hangs over HTTP**. Collect receipts with
`Receiptor` / `vault.receiptor` — which is what `InceptDoer`, `RotateDoer`, and `ConfirmDoer` all do.

## Release publisher + update verification

- The publisher (`tools/publisher/`) is a thin pipeline over keripy **`kli`**: `kli incept` / `kli interact`
  (ALWAYS `--receipt-endpoint`, which routes to `Receiptor`) + `publish.anchor_release` (KEL export via
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
