# Serverless-mailbox v2 query fix + vault doer-crash resilience

**Date:** 2026-07-09
**Source:** `backlog/2026-07-09-serverless-mailbox-v2-query-serializeerror.md`
**Base:** KERI-v2 keripy base (`keri 2.0.0-dev6`). Spans two repos:
`keri-serverless-mailbox` (usuranceai) + `locksmith` (seriouscoderone).

## Problem

On the v2 base, opening any vault whose AID has a mailbox end-role crashes the vault's
background loop ~1s after open, leaving the vault database closed (`hby.db.env is None`)
while `app.vault` still references it. Every db-reading UI action then degrades (this
surfaced first as the KERI Foundation onboarding crash, now guarded). Two layers:

- **L1 — the trigger.** The serverless-mailbox poller builds a `qry r=/mbx` whose
  `topics` map is keyed by slash-prefixed topic names (`/receipt`, `/replay`, …). On the
  v2 default (`version=Version` v2, `kind=cesr`), `hab.query`/`eventing.query` serialize
  CESR-native, and keri's `Labeler` rejects a `/`-prefixed map label:
  `InvalidValueError: Invalid label=b'/receipt'` → `SerializeError`. Confirmed by live
  repro (carrier2) and headless: default(v2) raises; `version=Vrsn_1_0, kind=Kinds.json`
  serializes clean v1 JSON.
- **L2 — the blast radius.** The vault is a single `Vault` DoDoer on one Doist
  (`vaulting.py:505` `run_vault_controller`). The poller is a nested sub-doer. Its
  exception propagates out of `doist.recur()`; `QtTask.run` (`core/tasking.py:82`) logs,
  stops the timer, and **re-raises**. As the crashed generator stack unwinds, the `Vault`
  DoDoer's doers are closed and `HaberyDoer` cleanup calls `hby.close()` (env→None), yet
  `AppCore.close_vault()` never runs — so `app.vault` keeps referencing a dead vault. One
  background doer's failure silently kills the whole vault db.

## Scope

Fix all three:
- **L1:** v1-pin both mailbox query builders (package).
- **L2a:** isolate the poller doer so its exception can't escape to the vault Doist
  (package).
- **L2b:** a vault-level backstop so any doer crash tears the vault down *honestly*
  (orderly close, `app.vault` cleared, UI notice) instead of leaving a live-but-dead
  reference (Locksmith core).

## L1 — v1-pin the mailbox query builders

Both query builders in `keri-serverless-mailbox` must serialize v1 JSON. The mailbox
wire protocol keys query `topics` by slash-prefixed labels, which are illegal as v2 CESR
map labels; v1 JSON is the compatible serialization and matches the ecosystem's existing
v1-hold (grep `TRANSITIONAL`).

- `src/keri_serverless_mailbox/fetch.py:83` (`build_and_post`):
  `querier.query(pre=hab.pre, src=eid, route="mbx", query=q, version=Vrsn_1_0, kind=Kinds.json)`
- `src/keri_serverless_mailbox/serverless.py:113` (WS subscribe envelope): same v1 pin.
- Add `from keri.kering import Vrsn_1_0, Kinds` and a `# TRANSITIONAL (KERI v2 v1-hold)`
  comment at each site. `hab.query` passes `**kwa` straight to `eventing.query`, which
  accepts `version=` and `kind=`, so the pin threads through unchanged.

*Rejected:* re-representing topics so labels are v2-legal (no slashes) — that changes the
deployed wire contract on the live federation servers *and* every client; far too
invasive for a serialization-compatibility fix. v1 JSON is minimal and consistent.

## L2a — isolate the poller doer (package)

The mailbox client doer must not let a poll-cycle exception escape into the host's Doist.
In `src/keri_serverless_mailbox/client.py` (`MailboxClientDoer.runDo`, the `yield from
strategy.run(...)` at :50), wrap the strategy run so any exception is caught, logged with
context, and ends *this doer* cleanly (the poller stops; it does not propagate). A
degraded/stopped poller is acceptable; a poller that kills its host is not. Result: when
a poll cycle fails, the host Doist keeps ticking and the host's Habery stays open.

## L2b — vault-level doer-crash backstop (Locksmith)

Independently of the mailbox, a doer crash reaching `QtTask` must not leave a
live-but-dead `app.vault`. The exception does not identify which nested deed failed, so
surgical deed-removal is out; instead make the failure honest:

- `src/locksmith/core/tasking.py`: `QtTask.__init__` gains an optional `on_error=None`
  callback. In `run`'s `except Exception` branch (currently log + stop timer + re-raise),
  when `on_error` is set: log, stop the timer, and call `on_error(exc)` **instead of**
  re-raising. When `on_error` is None: preserve today's behavior (re-raise) so existing
  tests/callers are unchanged.
- `src/locksmith/core/vaulting.py` `run_vault_controller`: pass an `on_error` that
  triggers an orderly vault teardown via the app (`app.close_vault()`), so `app.vault`
  is cleared and the db is closed cleanly, plus a one-time UI notice that the vault
  closed due to an internal error and should be reopened. (Clearing `app.vault` means the
  existing first guard in `list_eligible_local_identifiers` — and every `app.vault`-None
  check — already handles the closed state gracefully.)

## Cross-repo mechanics + branch strategy

- **Package** (`~/code/keri-serverless-mailbox`, origin usuranceai): branch off `main`;
  L1 + L2a. Bump the package version. Package tests: `.venv` at locksmith root, pytest
  `pythonpath=[src, ../keripy]`, `pip install -e` the branch before its tests.
- **Locksmith** (seriouscoderone): branch off `development`; L2b + re-pin the
  `keri-serverless-mailbox` dependency to the new package commit. For dev validation,
  editable-install the package branch into the Locksmith venv.
- **Gated final steps (do NOT do without explicit user OK):** push the package to
  usuranceai (gh auth switch → push → restore), and commit the Locksmith dependency
  re-pin to the pushed commit. Local validation uses the editable install.

## Testing

- **Package (L1):** unit test asserting each built `/mbx` query is v1 JSON
  (`bytes(msg).startswith(b'{"v":"KERI10JSON')`), for both `build_and_post` and the
  subscribe-envelope path; a real (temp) v1 Habery, no mock.
- **Package (L2a):** unit test — a `MailboxClientDoer` whose strategy raises does NOT
  propagate out of its `do` (the host driver keeps running); assert the doer stops and
  the exception is swallowed+logged, not raised.
- **Locksmith (L2b):** unit test on `QtTask` — with `on_error` set, a doer that raises
  triggers `on_error(exc)` and `run` does not re-raise; with `on_error=None`, it still
  re-raises (unchanged). A `run_vault_controller`-level test that the `on_error` path
  calls the app's teardown.
- **Live real-wallet validation (main session, the acceptance gate):** relaunch the dev
  wallet, open `carrier2` (passcode `noble`); confirm (a) NO `SerializeError` in the log,
  (b) the vault db stays open — Identifiers shows the `primary` AID and the KF onboarding
  page lists it (not an empty selector), (c) the mailbox poll runs (a `/mbx` query is
  posted). Then, to exercise L2b, inject a deliberately-crashing doer in a throwaway
  build and confirm the vault closes honestly (notice shown, `app.vault` cleared) rather
  than silently dying.

## Out of scope

- Moving the mailbox wire protocol to v2-native topic labels (federation-wide change).
- Lifting the broader v1-hold (tracked separately; L1's pin lifts jointly with it).
- The KF onboarding guard + brand-independent icon (already shipped, `56ff421`).
