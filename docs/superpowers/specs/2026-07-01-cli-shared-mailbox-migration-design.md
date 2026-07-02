# CLI → Shared Mailbox Library Migration — Design

**Date:** 2026-07-01
**Status:** Approved design (brainstorming → this spec → implementation plan)
**Spans:** `keri-serverless-mailbox` (library) + `locksmith` (import refactor) + `concierge-api` (the migration)

## Problem

The concierge-api CLI's `microapp build --host` mounts mailbox retrieval with its own
standalone `keri.app.indirecting.MailboxDirector` (`cli/microapp.py:143-148`) — but it
**never calls `add_poller` on it**, so `processPollIter` drains an always-empty deck and
**0 messages are ever fetched** (the "frontier bug"). Meanwhile Locksmith already retrieves
mail via the shared `keri-serverless-mailbox` library (`MailboxClient` + `MailboxClientDoer`,
`indirecting.py:147 add_poller`), which we live-validated. The CLI predates the library and
was never migrated onto it.

The user's original architecture: **one mailbox-client library that both the CLI and
Locksmith use.** This migration realizes that — unifying the DOI (CLI) and Carrier (Locksmith)
on the same client and fixing the frontier bug by construction — which unblocks the
vision-complete Stage-2 flow (a witnessed DOI grants a `carrier_license` over
`mailbox.keri.host`; the Carrier wallet admits it).

## Goals

- The CLI host retrieves mailbox messages via the shared `keri-serverless-mailbox`
  `MailboxClient` (not its own director); the "0 messages" bug is gone.
- The durable cursor store is **shared** between CLI and Locksmith (no duplication, no
  in-memory-only fallback).
- The hermetic gate (`test_grant_license_e2e.py`) stays green; a focused test covers the new
  CLI mount.

## Non-Goals

- No change to the ServiceAid pipeline, the grant/issue logic, or `PostmanDeliverer` (the real
  deliverer already delivers over the mailbox).
- **No `LocalRuntime` `exc`-injection.** That belongs to a *different* scenario (hosting the
  Service-AID inside a Locksmith vault, per `~/.claude/plans/modular-dancing-thunder.md`). The
  standalone CLI host registers capture handlers on `hby.exc`, so `on_message` feeds `hby.exc`.
- No new mailbox transport; `mailbox.keri.host` + the shipped notify-and-fetch is the transport.
- The witnessed-DOI + Carrier grant run itself is the *next* effort (this migration enables it).

## Global Constraints

- **`keri-serverless-mailbox` stays Locksmith-free.** The promoted `DbTopsCursorStore` may
  depend only on stock keripy (`keri.db.basing` — `hby.db.tops`, a `TopicsRecord`). No
  `locksmith` import in the library, ever.
- **concierge-api stays Locksmith-free.** It gains a dep on `keri-serverless-mailbox` only
  (not on `locksmith`). Its `pyproject.toml` `dependencies` list currently is `[]`.
- Locksmith tests run with `--import-mode=importlib`.
- The DOI AID must have a `mailbox` end-role designated (`mailbox.keri.host`) and its KEL
  published to the mailbox — the already-shipped KEL-registration fix — for
  `agenting.mailbox(hab, hab.pre)` to resolve. Runtime prerequisite, not code in this migration.
- Branches: library `feat/promote-cursor-store` off `main`; locksmith `feat/cursor-store-from-lib`
  off `development`; concierge-api `feat/mailbox-shared-client` off `main`. Commit per repo; the
  library push (usuranceai) and any live run are user-gated.

## Component 1 — Library: promote `DbTopsCursorStore`

Move the durable cursor store into the library so both hosts import it.

- **New:** `keri-serverless-mailbox/src/keri_serverless_mailbox/cursor_store.py` — a
  `DbTopsCursorStore(db, pre)` implementing the `CursorStore` protocol (`get(eid, topic) ->
  int | None`, `set(eid, topic, idx) -> None`) over `db.tops` (keripy `TopicsRecord`, keyed by
  `(pre, eid)`). Behavior is byte-for-byte the current Locksmith class; only `keri.db.basing`
  is imported. Export it from the package `__init__`.
- Unit test in the library: `set` then `get` round-trips per `(eid, topic)`; unseen topic →
  `None`; two eids/topics don't collide. Uses a temp `Habery`/`Baser` for `db.tops`.

## Component 2 — Locksmith: import the store from the library

- `locksmith/src/locksmith/core/mailbox_cursor.py`: replace the local `DbTopsCursorStore`
  definition with a re-export `from keri_serverless_mailbox import DbTopsCursorStore` (keep the
  module path stable so `indirecting.py`'s import is unchanged), OR update `indirecting.py:177`
  to import from the library and delete the local module. Prefer the re-export to minimize
  churn and keep any other importers working.
- Verified by the existing `tests/test_mailbox_kel_seed.py` + `tests/test_core_remoting.py`
  (`--import-mode=importlib`) staying green — the cursor store's behavior is unchanged.

## Component 3 — concierge-api: mount the shared client

- `pyproject.toml`: add `keri-serverless-mailbox` to `dependencies`.
- `cli/microapp.py` `_host_runtime()`: **delete** the standalone `MailboxDirector` block
  (lines 143-148) and mount the library client instead. The mount mirrors Locksmith's director
  internals (a small local glue, since the CLI host is not a Locksmith vault):
  - Resolve the DOI's mailbox: `eid = agenting.mailbox(rt.hab, rt.hab.pre)`; if `None`, print a
    clear error ("DOI AID has no mailbox end-role designated") and exit non-zero.
  - A `bytearray` ims + a keripy `parsing.Parser` configured with the DOI's `kvy`/`tvy`/`vry`
    and `exc=rt.hby.exc` (the same parser wiring the old `MailboxDirector` used — it was built
    with `verifier=rt.cred_verifier, exc=rt.hby.exc`). Drive the parser as a doer so drained
    exns reach the ServiceAid capture handlers on `hby.exc`.
  - `client = MailboxClient(rt.hab, topics=["/receipt", "/credential", "/reply",
    *rt.command_topics], on_message=<append raw to the ims for the parser doer>,
    cursor_store=DbTopsCursorStore(rt.hby.db, rt.hab.pre))`.
  - Append `MailboxClientDoer(client)` (and the parser doer) to the host's doers; the existing
    `Doist` drives them.
  - The EXACT `parsing.Parser` constructor kwargs are confirmed against keripy in the plan
    (the survey noted `exc.processOneIter` does NOT exist; the correct path is a `Parser` fed
    the ims — the same mechanism Locksmith's `MailboxDirector` already uses).

## Data flow (after migration)

DOI host loads → `MailboxClient` resolves `mailbox.keri.host` (wss loc → `ServerlessStrategy`)
→ subscribes + drains the command topic → `on_message` appends raw bytes → the parser doer
feeds `hby.exc` → the ServiceAid capture handler fires → `pipeline.process` → grant issued →
`PostmanDeliverer` deposits the grant to the Carrier's mailbox.

## Testing

- **Library:** `DbTopsCursorStore` round-trip + isolation unit test (temp Habery).
- **concierge-api:** a focused test that `_host_runtime` (or an extracted mount helper) builds a
  `MailboxClient` with the expected `topics` (incl. `rt.command_topics`) and a
  `DbTopsCursorStore`, and that `on_message` routes bytes into `rt.hby.exc` (fake the client /
  inject a fake strategy; assert an exn reaches a capture handler). The hermetic
  `test_grant_license_e2e.py` stays unchanged and green (it bypasses this seam).
- **Locksmith:** existing mailbox/remoting suites green with the re-exported store.

## Risks / open decisions (resolved here)

- **`parsing.Parser` construction** — confirm exact kwargs against keripy in the plan; anchor on
  what the old `MailboxDirector` passed (`verifier=rt.cred_verifier, exc=rt.hby.exc`) plus the
  host's `kvy`/`tvy`. This is the one API detail to pin during implementation.
- **`db.tops` availability in the CLI host** — `rt.hby.db` is an open `Baser`, so `db.tops`
  exists; `DbTopsCursorStore` works unchanged. Durable across restarts (no re-delivery).
- **DOI mailbox prerequisite** — `agenting.mailbox` returns `None` without a designated mailbox
  end-role; the host errors clearly rather than silently idling (unlike today).
- **Cursor store location** — DECIDED: promote to the library (Approach A). Locksmith re-exports
  to avoid a second definition.
