# ConfirmDoer Receiptor Migration + #1423 Removal — Design

**Date:** 2026-06-16
**Status:** Approved (brainstorm complete; ready for implementation plan)
**Repos:** `locksmith` (ConfirmDoer migration + integration test) and the `keripy` fork (#1423 removal). Two coordinated branches.

## Goal

Eliminate the last locksmith code path that collects witness receipts over HTTP using the
direct-mode push model (`agenting.WitnessReceiptor`), which hangs forever against an HTTP/Lambda
witness; and delete the inert, misdiagnosis-born #1423 parser patch from the keripy fork. Both are
grounded in the verified KERI communication model: a witness `/` event POST returns **`204`**, and
receipts return via the synchronous **`/receipts`** endpoint (`agenting.Receiptor`) or via mailbox
SSE poll — never on the event-POST response.

## Background (verified, not assumed)

- The witness `/` endpoint (`keripy app/indirecting.py` `HttpEnd.on_post`) returns `204` for every
  key event (`icp/rot/ixn/dip/drt/exn/rpy`) and TEL ilk; the only `200`s on `/` are `OPTIONS` (CORS,
  no body) and `qry route="mbx"` (an SSE **stream**, not a CESR body). **Verified against
  `WebOfTrust/main` (tip `5820a07c`, fetched 2026-06-16)** via `git show WebOfTrust/main:src/keri/app/indirecting.py` — not our fork.
- PR #1423 (closed-not-merged upstream; maintainer Kent Bull labeled it *enhancement, not a bug*)
  added to `HTTPMessenger.responseDo` a block guarded by `if rep.status == 200 and rep.body:`. Because
  `HTTPMessenger` only ever POSTs events to `/` (→ `204`), that block **never fires** on an event
  POST. It is dead code that does not actually deliver receipts. It lives in our keripy fork as a
  single self-contained commit (`2184d0da4` on `development`; byte-identical twin `3cf7bfad` on the
  unmerged branch `fix/http-messenger-parser-wiring`).
- locksmith's primary flows (inception, single rotation, auth-fallback, credential/TEL issuance)
  already migrated to `Receiptor` (`LocksmithReceiptor`) under keri-foundation/locksmith#77. **One
  holdout remains:** `ConfirmDoer` (delegator confirming a delegate) at `core/habbing.py:1225` still
  uses `agenting.WitnessReceiptor` → hangs over HTTP, and #1423 cannot rescue it (the `/` POST is
  `204`). This path is currently untested over HTTP.

## Change 1 — ConfirmDoer migration (`locksmith/src/locksmith/core/habbing.py`)

`ConfirmDoer.__init__(self, app, ...)` already has `app`; it pulls collaborators off `app.vault.*`.
Add the shared receiptor alongside them (near the other `self.* = app.vault.*` assignments, ~line
1088-1103):

```python
        self.receiptor = app.vault.receiptor   # shared LocksmithReceiptor (sync /receipts)
```

In `confirmDo`, replace the `WitnessReceiptor` block (currently `habbing.py:1225-1233`):

```python
                            witDoer = agenting.WitnessReceiptor(hby=self.hby, auths=auths)
                            self.extend(doers=[witDoer])
                            self.toRemove.append(witDoer)  # type: ignore
                            yield self.tock

                            if hab.kever.wits:
                                witDoer.msgs.append(dict(pre=hab.pre, sn=cur+1))
                                while not witDoer.cues:
                                    _ = yield self.tock
```

with the `Receiptor` pattern already used by `RotateDoer` (`rotating.py:209`) and
`AuthenticateWitnessesDoer` (`rotating.py:405`):

```python
                            if hab.kever.wits:
                                yield from self.receiptor.receipt(hab.pre, sn=cur + 1, auths=auths)
```

- `LocksmithReceiptor.receipt(self, pre, sn=None, auths=None)` (`receipting.py:150`) takes `auths`,
  so the TOTP/witness-auth codes built at `habbing.py:1216-1223` are preserved unchanged.
- The `yield from` blocks until the synchronous `/receipts` round-trip completes and wigs land in
  `db.wigs` — same "wait for receipts before proceeding to the `witq.query` confirmation" semantics
  as the old cue-wait, but over the channel that actually delivers.
- `from keri.app import agenting` stays (still used for `agenting.WitnessInquisitor` at
  `habbing.py:1088`); only the `WitnessReceiptor` *usage* is removed. `cur` (set at `habbing.py:1208`)
  is **retained** — it still supplies `sn=cur + 1`. The `self.extend([witDoer])` /
  `self.toRemove.append(witDoer)` bookkeeping is removed along with `witDoer`.

## Change 2 — #1423 removal (`keripy` fork `src/keri/app/agenting.py`)

In `HTTPMessenger.responseDo`:
- Remove the parse block (currently `agenting.py:921-925`):
  ```python
                  if rep.status == 200 and rep.body:
                      try:
                          self.hab.psr.parseOne(ims=bytearray(rep.body))
                      except Exception as ex:
                          logger.warning("HTTPMessenger response parse failed: %s", ex)
  ```
- Restore the stock one-line docstring (revert the misdiagnosis docstring at `agenting.py:898-912`)
  to: `"""Doer loop that processes HTTP responses from the client and adds them into `sent` cues."""`
- Delete `test_http_messenger_routes_response_through_parser` from `tests/app/test_agenting.py`.

Result: `src/keri/app/agenting.py` and `tests/app/test_agenting.py` become byte-identical to
`WebOfTrust/main`. No other keripy code depends on the block (the only `HTTPMessenger` production
caller, `witnesserFrom`/`messengerFrom`, consumes `self.sent`, not parser side-effects).

## Change 3 — Integration test (`locksmith/tests/`)

A **full delegation integration test** that reproduces the real failure shape and proves the fix.

- **Fixture:** a real keripy witness via `keri.app.indirecting.setupWitness` on a local HTTP port
  (so receipts ride real HTTP `/receipts`, and `/` returns the real `204`); plus a locksmith vault
  `app` (reuse the existing locksmith vault test fixtures). Borrow keripy delegation patterns
  (`tests/app/test_delegating.py`) where they compose.
- **Scenario:** delegator `D` (witnessed by the test witness) approves a delegate `G`'s delegated
  event. Construct `ConfirmDoer(app, alias=D, escrowed=[(G.pre, sn, edig)], interact=True,
  auto=True)` and run it to completion under a `Doist`/`DoDoer`.
- **Assertions:** after the run, the delegator's anchoring interaction event has
  `len(D.db.wigs.get(dgkey)) >= toad` (the receipt arrived from the real witness over HTTP), and the
  delegate event is committed (present/advanced in `hby.kevers[G.pre]`). The test completes within a
  bounded tick budget — i.e. it does **not** hang.
- **Negative-control note (documented in the test):** the same scenario against the pre-migration
  `WitnessReceiptor` path would never satisfy `db.wigs` (the `/` POST is `204`) and would exhaust the
  tick budget — that is the regression this test guards.
- If a full real-witness fixture proves disproportionately fragile during implementation, the
  fallback is a minimal Falcon stub witness (`204` on `/`, canned `rct` on `/receipts`); the plan
  should attempt the real witness first and only fall back with an explicit note.

## Sequencing & cleanup

1. Land the **locksmith** migration + integration test first (so no code references the broken
   pattern), direct-merge to locksmith `development`.
2. Then remove **#1423** from the keripy fork, direct-merge to keripy `development`.
3. Cleanup: delete the parked keripy branch `fix/http-messenger-parser-wiring`; run
   `git checkout WebOfTrust/main` in `~/KERI/code/keripy` to restore a pristine reference checkout.

## Testing / verification

- locksmith: full suite green, including the new delegation integration test **and** the existing
  `tests/test_incept_doer_uses_receiptor.py` (#77 regression guard).
- keripy fork: `tests/app tests/cdk tests/handlers tests/db tests/serviceaid` green after the strip;
  confirm `git diff WebOfTrust/main -- src/keri/app/agenting.py tests/app/test_agenting.py` is empty.

## Out of scope (flagged separately)

- The `locksmith/pyproject.toml:33` keripy dependency pin (currently `WebOfTrust/keripy` upstream,
  while the dev box runs the editable fork). That fork-vs-upstream divergence is a larger decision
  and is **not** part of this change. Migrating `ConfirmDoer` to `Receiptor` removes its dependence on
  the fork-only #1423 patch, so this change is correct regardless of how the pin is later resolved.

## Provenance

Grounded in `~/code/KERI-COMMUNICATION-MODEL.md`, the WebOfTrust/keripy #1422/#1423 issue+PR, the
maintainer (Kent Bull) Discord exchange (HTTPMessenger is a sender; use `Receiptor`; not a bug,
"enhancement"), and direct reads of authoritative `WebOfTrust/main` code (tip `5820a07c`).
