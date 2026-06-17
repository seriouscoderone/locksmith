# ConfirmDoer Receiptor Migration + #1423 Removal — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate locksmith `ConfirmDoer` from the broken-over-HTTP `agenting.WitnessReceiptor` to the shared `Receiptor` (`vault.receiptor`), prove it with a real-witness delegation integration test, and delete the inert #1423 `HTTPMessenger` parser patch from the keripy fork.

**Architecture:** Two coordinated branches. (1) locksmith: a ~6-line change in `core/habbing.py` (`ConfirmDoer` uses `vault.receiptor.receipt(...)` instead of constructing a `WitnessReceiptor`), guarded by a new delegation integration test that stands up a *real* keripy witness over HTTP and asserts the delegator's anchoring event collects witness receipts (`db.wigs`) without hanging. (2) keripy fork: strip the #1423 hunks from `HTTPMessenger.responseDo` + delete its test, restoring byte-identity with `WebOfTrust/main`. Land locksmith first, then keripy.

**Tech Stack:** Python 3, keripy (`agenting.Receiptor`, `indirecting.setupWitness`), `hio.base.doing.Doist`, pytest. Spec: `docs/superpowers/specs/2026-06-16-confirmdoer-migration-1423-removal-design.md`.

**Verified communication-model fact (the why):** the witness `/` event POST returns `204` (`keripy indirecting.py HttpEnd.on_post`, confirmed on `WebOfTrust/main` tip `5820a07c`); receipts return on the `/receipts` 200 body, which `Receiptor` posts to and parses. `WitnessReceiptor` busy-waits on `db.wigs` expecting a TCP-style push that HTTP never provides → hangs. #1423's `if rep.status == 200 and rep.body:` block in `HTTPMessenger.responseDo` never fires (the `/` POST is `204`), so it is dead code.

---

## File Structure

**locksmith (branch `feat/confirmdoer-receiptor`, worktree off `development`):**
- Modify: `src/locksmith/core/habbing.py` — `ConfirmDoer.__init__` (add `self.receiptor`) and `confirmDo` (replace the `WitnessReceiptor` block at ~`:1225-1233`).
- Create: `tests/integration/test_confirmdoer_receipts_over_http.py` — the delegation integration test (marked `@pytest.mark.integration`).

**keripy fork (branch `chore/remove-1423`, worktree off `development`):**
- Modify: `src/keri/app/agenting.py` — `HTTPMessenger.responseDo` (strip the parse block + revert docstring).
- Modify: `tests/app/test_agenting.py` — delete `test_http_messenger_routes_response_through_parser`.

---

### Task 0: Worktrees + clean baselines

**Files:** none (environment).

- [ ] **Step 1: locksmith worktree + venv**
```bash
cd /Users/seriouscoderone/code/locksmith
git worktree add .worktrees/confirmdoer-receiptor -b feat/confirmdoer-receiptor development
cd .worktrees/confirmdoer-receiptor
python3 -m venv .venv
.venv/bin/pip install -U pip -q
.venv/bin/pip install -e /Users/seriouscoderone/code/keripy -q   # the keripy FORK (editable) — provides setupWitness etc.
.venv/bin/pip install -e . -q
.venv/bin/pip install pytest pytest-asyncio -q
```
Confirm `.worktrees` is gitignored: `git check-ignore .worktrees` (locksmith already ignores it; if not, add + commit).

- [ ] **Step 2: locksmith baseline green** (the #77 regression guard must already pass)
Run: `.venv/bin/python -m pytest tests/test_incept_doer_uses_receiptor.py -q`
Expected: PASS. Note the count.

- [ ] **Step 3: keripy fork worktree** (for Task 3; the fork's main checkout already has a working venv via the oracle work — reuse a fresh worktree venv to stay isolated)
```bash
cd /Users/seriouscoderone/code/keripy
git worktree add .worktrees/remove-1423 -b chore/remove-1423 development
cd .worktrees/remove-1423
python3.14 -m venv .venv
.venv/bin/pip install -U pip -q && .venv/bin/pip install -e . -q && .venv/bin/pip install pytest pytest-asyncio aws-cdk-lib constructs moto boto3 -q
mkdir -p keri_cdk/layers/keri_runtime/python && echo "placeholder" > keri_cdk/layers/keri_runtime/README.txt
```

- [ ] **Step 4: keripy baseline** — confirm #1423 is present (so removal is meaningful):
Run: `.venv/bin/python -m pytest tests/app/test_agenting.py::test_http_messenger_routes_response_through_parser -q`
Expected: PASS (the #1423 test exists on `development`).

---

### Task 1: Delegation integration test (RED)

**Files:**
- Create: `tests/integration/test_confirmdoer_receipts_over_http.py` (in the locksmith worktree)

**Reference material (read these in the keripy fork before writing — they are the proven templates):**
- `/Users/seriouscoderone/code/keripy/tests/app/test_delegating.py:17-128` — real witness via `setupWitness` + delegator/delegate + delegator anchors via `palHab.rotate(data=[dict(i=, s=, d=)])` + the manual `Doist.recur()`/`time.sleep` loop.
- `/Users/seriouscoderone/code/keripy/tests/app/test_agenting.py:17-110` — `setupWitness(alias="wan", hby=wanHby, tcpPort=..., httpPort=5642, **kwa)` and polling `db.wigs.get(keys=(preb, saidb))` for receipts.
- `/Users/seriouscoderone/code/keripy/tests/conftest.py:27-33,121-163` — the `WitnessUrls` table (witness `wan` ⇒ `http://127.0.0.1:5642/`) and `DbSeed.seedWitEnds(db, witHabs, protocols, ...)` which seeds the controller's `.ends`/`.locs` so it can resolve the witness HTTP endpoint.

- [ ] **Step 1a: Implement the `_seed_wit_ends` helper first.** The receipt path needs the delegator db to resolve the witness URL (`agenting.httpClient` → `hab.fetchUrls(eid=wit, scheme=http/https)`). Implement `_seed_wit_ends(ctrl_db, wit_hab)` one of two concrete ways:
  - **Preferred — reproduce `DbSeed.seedWitEnds`:** open `/Users/seriouscoderone/code/keripy/tests/conftest.py:121-163`, read the `seedWitEnds` body and the `WitnessUrls` table (`:27-33`), and copy its end-role + loc-scheme `rpy`-seeding logic into `_seed_wit_ends`. This requires the witness to be named `wan` at `httpPort 5642` (already set via `WIT_ALIAS`/`WIT_HTTP_PORT`).
  - **Alternative — OOBI resolve:** add `keri.app.oobiing.Oobiery(hby=dgrHby)` to the doist, queue `dgrHby.db.oobis.put` for `http://127.0.0.1:5642/oobi/{witHab.pre}/controller`, and let resolution populate `.ends`/`.locs` (then `_seed_wit_ends` is a no-op and you wait for `witHab.pre` endpoints to appear).

  Verify the witness URL resolves before proceeding: `dgr.fetchUrls(eid=witHab.pre, scheme="http")` returns the `http://127.0.0.1:5642/` location.

- [ ] **Step 1b: Write the rest of the integration test.** Create `tests/integration/test_confirmdoer_receipts_over_http.py`:

```python
"""Integration test (issue #77 / keripy #1422): ConfirmDoer must collect the
delegator's witness receipts over HTTP via the shared Receiptor, not the
direct-mode WitnessReceiptor (which hangs against a 204-on-/ witness).

Stands up a REAL keripy witness over HTTP. With the pre-migration WitnessReceiptor
the delegator's anchoring ixn never gets wigs (the witness '/' POST is 204), so the
final assertion fails within the Doist budget. After the migration the receipt
rides '/receipts' and wigs land.
"""
import time
from types import SimpleNamespace

import pytest
from hio.base import doing, tyming
from keri.app import habbing, indirecting, forwarding
from keri.core import coring, parsing, eventing
from keri.db import dbing

from locksmith.core import habbing as lh
from locksmith.core.receipting import LocksmithReceiptor

WIT_HTTP_PORT = 5642          # matches keripy WitnessUrls "wan:http"
WIT_ALIAS = "wan"            # ditto


def _seed_wit_ends(ctrl_db, wit_hab):
    """Seed the controller db's .ends/.locs so agenting.httpClient can resolve the
    witness's HTTP URL. AUTHORED IN STEP 1 below — keep this raise as a fail-loud
    marker until then."""
    raise NotImplementedError("implement in Task 1 Step 1")


@pytest.mark.integration
def test_confirmdoer_collects_delegator_receipts_over_http():
    salt = b"0123456789abcdef"
    with habbing.openHby(name="withby", salt=coring.Salter(raw=b"witsaltwitsalt00").qb64) as witHby, \
            habbing.openHby(name="delegator", salt=coring.Salter(raw=salt).qb64) as dgrHby, \
            habbing.openHby(name="delegate", salt=coring.Salter(raw=b"delegatedelegate").qb64) as delHby:

        # --- real witness over HTTP only (tcpPort=None) ---
        witDoers = indirecting.setupWitness(alias=WIT_ALIAS, hby=witHby,
                                            tcpPort=None, httpPort=WIT_HTTP_PORT)
        witHab = witHby.habByName(WIT_ALIAS)

        # --- delegator D, witnessed by the witness ---
        dgr = dgrHby.makeHab(name="D", transferable=True, wits=[witHab.pre], toad=1)
        _seed_wit_ends(dgrHby.db, witHab)

        # --- delegate produces a dip pointing at D; seed it into D's db.evts ---
        dele = delHby.makeHab(name="G", transferable=True, delpre=dgr.pre)
        dipser = dele.kever.serder
        # put the dip event into D's hby so ConfirmDoer.confirmDo can read it
        parsing.Parser(kvy=eventing.Kevery(db=dgrHby.db, local=True)).parseOne(
            ims=bytearray(dele.makeOwnInception()))

        # --- fake locksmith vault: real hby + real receiptor; stub the rest ---
        receiptor = LocksmithReceiptor(hby=dgrHby)
        vault = SimpleNamespace(
            hby=dgrHby, hbyDoer=habbing.HaberyDoer(habery=dgrHby),
            receiptor=receiptor, postman=forwarding.Poster(hby=dgrHby),
            counselor=SimpleNamespace(), notifier=SimpleNamespace(),
            mux=SimpleNamespace(), exc=SimpleNamespace(), mbx=SimpleNamespace(),
        )
        app = SimpleNamespace(vault=vault)

        confirm = lh.ConfirmDoer(app=app, alias="D",
                                 escrowed=[(dele.pre, 0, dipser.said)],
                                 interact=True, auto=True)

        doers = list(witDoers) + [receiptor, confirm]
        doist = doing.Doist(limit=10.0, tock=0.03125, doers=doers)
        doist.enter()
        tymer = tyming.Tymer(tymth=doist.tymen(), duration=doist.limit)
        # run until D's anchoring ixn (sn=1) is witnessed, or the budget expires
        dgkey = dbing.dgKey(dgr.pre.encode(), dgr.kever.serder.saidb)
        while not tymer.expired:
            doist.recur()
            time.sleep(doist.tock)
            kev = dgrHby.kevers[dgr.pre]
            if kev.sner.num >= 1:
                dgkey = dbing.dgKey(dgr.pre.encode(), kev.serder.saidb)
                if len(dgrHby.db.getWigs(dgkey)) >= 1:
                    break
        doist.exit()

        kev = dgrHby.kevers[dgr.pre]
        assert kev.sner.num >= 1, "delegator never produced its anchoring ixn"
        dgkey = dbing.dgKey(dgr.pre.encode(), kev.serder.saidb)
        wigs = dgrHby.db.getWigs(dgkey)
        assert len(wigs) >= 1, (
            "delegator anchoring event collected no witness receipts over HTTP — "
            "ConfirmDoer is still on the WitnessReceiptor (push) path that hangs "
            "against a 204-on-/ witness (issue #77)"
        )
```

> **Implementer note (this is integration code — iterate against real behavior):** the
> happy-path constructions above are taken from the verified keripy templates, but three
> spots commonly need adjustment when first run; budget a debug pass:
> 1. **`_seed_wit_ends`** — reproduce `DbSeed.seedWitEnds` (keripy `tests/conftest.py:121-163`); the witness MUST be name `wan` at `httpPort 5642` to match the `WitnessUrls` table, or seed the loc/end replies explicitly. If `DbSeed` is importable from keripy tests on the venv path, `from tests.conftest import DbSeed` and call it directly.
> 2. **Receipt catch-up** — `LocksmithReceiptor` catches the witness up on the KEL before receipting (`receipting.py:catchup`); if `db.wigs` stays empty, confirm the delegator's `icp` was itself receipted first (you may need to run a receipt for `sn=0` before the anchor, mirroring how vaulting witnesses the inception).
> 3. **`getWigs`/`dgKey` exact API** — verify against `keripy/src/keri/db/basing.py` (`db.getWigs(dgkey)` vs `db.wigs.get(...)`); use whichever the installed keripy exposes.
>
> **Hard fallback (time-box ~60 min):** if the real-witness fixture proves too fragile,
> swap the witness for a minimal Falcon stub app (route `/` → `204`; route `/receipts` →
> `200` with a pre-built `rct` for the posted event) served via `hio.core.http.Server`,
> per the spec's documented fallback. Keep the same assertions.

- [ ] **Step 2: Run against CURRENT code — expect RED.**
Run: `.venv/bin/python -m pytest tests/integration/test_confirmdoer_receipts_over_http.py -q -m integration`
Expected: FAIL on the final assertion `len(wigs) >= 1` (the pre-migration `WitnessReceiptor` path never fills `db.wigs` over HTTP; the loop exhausts the 10s budget). If it ERRORs instead of FAILs, fix the fixture per the implementer note until the failure is specifically "no wigs collected."

- [ ] **Step 3: Commit the RED test**
```bash
git add tests/integration/test_confirmdoer_receipts_over_http.py
git commit -m "test: failing delegation integration test for ConfirmDoer receipts over HTTP (#77)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: ConfirmDoer migration (GREEN)

**Files:**
- Modify: `src/locksmith/core/habbing.py` (`ConfirmDoer.__init__` ~`:1083-1110`; `confirmDo` ~`:1225-1233`)

- [ ] **Step 1: Add the shared receiptor in `__init__`.** In `ConfirmDoer.__init__`, alongside the other `self.* = app.vault.*` assignments (immediately after `self.mbx = app.vault.mbx` at ~`:1103`), add:
```python
        self.receiptor = app.vault.receiptor
```

- [ ] **Step 2: Replace the WitnessReceiptor block in `confirmDo`.** Replace exactly this block (currently ~`:1225-1233`):
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
with:
```python
                            if hab.kever.wits:
                                yield from self.receiptor.receipt(hab.pre, sn=cur + 1, auths=auths)
```
Leave everything else (`cur = hab.kever.sner.num`, the `auths` build, the `anchor`/`interact`/`rotate`, the later `witq.query` confirmation, `delegables.rem`, `return True`) unchanged. The `from keri.app import ... agenting` import inside `confirmDo` stays (still used for `agenting.WitnessInquisitor` in `__init__`). `cur` is still used (`sn=cur + 1`).

- [ ] **Step 3: Run the integration test — expect GREEN.**
Run: `.venv/bin/python -m pytest tests/integration/test_confirmdoer_receipts_over_http.py -q -m integration`
Expected: PASS (the receipt now rides `/receipts`; wigs land).

- [ ] **Step 4: Run the #77 regression guard + any ConfirmDoer-adjacent tests for no regression.**
Run: `.venv/bin/python -m pytest tests/test_incept_doer_uses_receiptor.py tests/test_rotate_try_then_fallback.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add src/locksmith/core/habbing.py
git commit -m "fix(confirm): ConfirmDoer collects receipts via vault.receiptor, not WitnessReceiptor (#77)

The delegator-confirm path was the last WitnessReceiptor caller; over HTTP it
busy-waits on db.wigs for a push that never comes (witness '/' POST is 204) and
hangs. Use the shared Receiptor (sync /receipts), matching InceptDoer/RotateDoer.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Remove the #1423 patch from the keripy fork

**Files (in the keripy worktree `~/code/keripy/.worktrees/remove-1423`):**
- Modify: `src/keri/app/agenting.py` (`HTTPMessenger.responseDo`)
- Modify: `tests/app/test_agenting.py` (delete the #1423 test)

- [ ] **Step 1: Strip the parse block + revert the docstring.** In `HTTPMessenger.responseDo`, remove the block (currently ~`:921-925`):
```python
                if rep.status == 200 and rep.body:
                    try:
                        self.hab.psr.parseOne(ims=bytearray(rep.body))
                    except Exception as ex:
                        logger.warning("HTTPMessenger response parse failed: %s", ex)
```
and replace the expanded misdiagnosis docstring (currently ~`:898-912`) with the stock one-liner:
```python
        """Doer loop that processes HTTP responses from the client and adds them into `sent` cues."""
```

- [ ] **Step 2: Delete the #1423 test.** Remove `test_http_messenger_routes_response_through_parser` from `tests/app/test_agenting.py` (the whole function, ~`:240-310+`).

- [ ] **Step 3: Verify byte-identity with upstream.**
Run: `git -C /Users/seriouscoderone/code/keripy fetch WebOfTrust main && git diff WebOfTrust/main -- src/keri/app/agenting.py tests/app/test_agenting.py`
Expected: EMPTY (both files now match `WebOfTrust/main`).

- [ ] **Step 4: Run keripy suites for no regression.**
Run: `.venv/bin/python -m pytest tests/app/test_agenting.py tests/db tests/cdk tests/handlers -q`
Expected: PASS (the #1423 test is gone; nothing else depended on the block).

- [ ] **Step 5: Commit**
```bash
git add src/keri/app/agenting.py tests/app/test_agenting.py
git commit -m "revert: drop inert #1423 HTTPMessenger response-parser patch

The witness '/' event POST returns 204 (verified on WebOfTrust/main), so the
rep.status==200 block never fired. The receipt path is Receiptor (/receipts);
HTTPMessenger is a sender. Restores byte-identity with upstream. See keripy#1422.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Merge, cleanup, final verification

- [ ] **Step 1: Merge locksmith → `development`** (direct, matching the project pattern). From the locksmith main checkout:
```bash
git -C /Users/seriouscoderone/code/locksmith merge --ff-only feat/confirmdoer-receiptor
```
(If `development` advanced and ff is impossible, do a no-ff merge.)

- [ ] **Step 2: Merge keripy fork → `development`.**
```bash
git -C /Users/seriouscoderone/code/keripy merge --ff-only chore/remove-1423
```

- [ ] **Step 3: Cleanup worktrees + branches.**
```bash
git -C /Users/seriouscoderone/code/locksmith worktree remove --force .worktrees/confirmdoer-receiptor
git -C /Users/seriouscoderone/code/locksmith branch -d feat/confirmdoer-receiptor
git -C /Users/seriouscoderone/code/keripy worktree remove --force .worktrees/remove-1423
git -C /Users/seriouscoderone/code/keripy branch -d chore/remove-1423
# delete the now-obsolete parked #1423 branch + restore a pristine reference checkout
git -C /Users/seriouscoderone/code/keripy branch -D fix/http-messenger-parser-wiring
git -C /Users/seriouscoderone/KERI/code/keripy checkout WebOfTrust/main
```
(`fix/http-messenger-parser-wiring` is the #1423 twin; safe to delete now that #1423 is reverted. The `~/KERI/code/keripy` checkout was parked on it — restore it to upstream.)

- [ ] **Step 4: Final verification.** locksmith suite + keripy suites green on `development`; `git -C ~/code/keripy diff WebOfTrust/main -- src/keri/app/agenting.py` empty. Do NOT push (pushing `development` to `fork` is a separate, user-initiated step).

---

## Completion

Update memory: note keri-foundation/locksmith#77 fully closed (ConfirmDoer was the last holdout) and #1423 reverted from the fork. Flag the still-open `pyproject.toml` keripy pin (upstream vs fork) as the remaining follow-up — explicitly out of scope here.
