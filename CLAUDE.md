# CLAUDE.md — Locksmith

Locksmith is a desktop **KERI key wallet** (PySide6 UI over a transport-agnostic `src/locksmith/core/`).
This file captures conventions and gotchas that aren't obvious from the code. Keep it short and accurate.

## Running tests

- Venv: `.venv/bin/python` at the repo root.
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

Field guide: `~/code/KERI-COMMUNICATION-MODEL.md`. The load-bearing rule: a witness `/` event POST returns
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

## Design docs

Specs/plans live in `docs/superpowers/{specs,plans}/`. Recent: publisher rebuild
(`2026-06-17-publisher-rebuild-kli*`), ConfirmDoer→Receiptor + keripy #1423 removal
(`2026-06-16-confirmdoer-migration-1423-removal*`).

## Infra note

The serverless KERI infrastructure (witnesses/mailboxes, the KEL oracle, Service-AID) lives in the **keripy
fork** (`~/code/keripy`, deployed via `keri_cdk`), not here. Locksmith depends on stock keripy APIs only.
