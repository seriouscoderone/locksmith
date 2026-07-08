# KERI v2 Base Reconciliation — keripy Fork Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconcile the keripy fork's custom code with the upstream v2 (full-CESR) base — **holding** the `keri_serviceaid` framework + schema.keri.host on **v1** (a documented, transitional pin, because keripy's v2 ACDC issuance/registry/IPEX primitives are stubs) while **adopting v2** for the one piece that is genuinely v2-ready: the witness receipt-store (`vrcsNew`).

**Architecture:** The upstream merge (`452b102c`) flipped `src/keri/kering.py` defaults to version 2.0 + kind CESR. **Investigation (2026-07-07, receipts in the spec) proved keripy's v2 ACDC *issuance* path does not exist yet** — `proving.credential` hardcodes the v1 `ri` label (untouched by the merge), `vdr/` is `Vrsn_1_0`-pinned, and `acdc/registering.py`/`ipexing.py`/`regbasing.py` are empty stubs; only v2 *message builders* (`acdc/messaging.py`) exist. **Stage 1** therefore pins the framework's hab-inception, credential build, and exn framing back to v1 (clearly commented, tracked for lift) so the suite is green on the v2 base. **Stage 2** registers the new indexed transferable-receipt store `vrcsNew` (added upstream to `basing.py` but absent from the fork's DynamoDBer store-set) while keeping it node-private (out of `SHARED_KEL_STORES`), preserving `Receiptor` toad convergence.

**Tech Stack:** keripy fork (`development @ b8630d45`), KERI v2 base, the `keri_serviceaid` framework (held v1), `DynamoDBer` (moto tests), CDK `schema_host` synth tests, pytest.

## Global Constraints

- **Base:** a fresh branch `feat/keri-v2-base-reconcile` off keripy `development @ b8630d45` (upstream merged + `MaxNamedDBs 100→200`; the exploratory v1-pins were reverted — this plan re-introduces them deliberately + completes them).
- **Stage 1 = transitional v1 HOLD, not a dodge.** Every `Vrsn_1_0` / `Kinds.json` pin MUST carry a comment: `# TRANSITIONAL: keripy v2 ACDC issuance/registry/IPEX not implemented upstream (acdc/registering.py, ipexing.py stubs; vc/proving.py:79 hardcodes ri). Lift when upstream ships v2 registry+IPEX.` The pins are a set, removable as a unit later.
- **schemas stay `ri`** (v1 registry field). Do NOT change to `rd` — that is the v2 field, and we are holding v1.
- **Stage 2 = v2-native.** `vrcsNew` MUST be registered in the DynamoDBer store-set and MUST NOT be added to `SHARED_KEL_STORES` (`src/keri/app/lambding.py:67`). Pooling receipt write-logs collapses witnesses' receipts to one and breaks `Receiptor` toad convergence.
- **Out of scope:** any v2 ACDC issuance/registry/IPEX work (upstream-blocked); ACDC v2 features (bulk issuance, aggregate/blinded SAIDs); the `acdc/*.py` stub modules.
- **Authoritative reference for v2 wire behavior** (Stage 2): the `keri:cesr`/`keri:spec`/`keri:acdc` skills.
- **Tests:** `cd /Users/seriouscoderone/code/keripy && PYTHONPATH=. .venv/bin/python -m pytest … --import-mode=importlib` (the fork venv has `moto`).
- **Do NOT push.** keripy pushes → seriouscoderone fork only, never WebOfTrust/origin. Commit per task; merge only when the user asks.
- **Known pre-existing failures (NOT this branch):** `tests/cdk/test_federation_config`, `tests/cdk/test_keri_host_app`. Verify they fail identically with changes stashed; do not attribute to this branch.
- **Reference:** the reverted diagnostic commits (`1b41009b` makeHab v1, `cfbba21d` test habs v1, `bd03ec72` test exns v1 JSON) are the known-good shape for Tasks 1 & 3, recoverable via `git reflog`. The diagnosis is `~/code/keripy/.superpowers/sdd/upstream-sync-diagnosis.md`.

---

## Stage 1 — Hold `keri_serviceaid` + schema.keri.host on v1 (transitional)

### Task 1: Pin hab inception + KEL parse to v1 (unblock the fixture cascade)

**Files:**
- Modify: `tests/serviceaid/conftest.py` (`recipient_pre` lines 39-54; `issuer_hby`; any `makeHab`)
- Modify: any `keri_serviceaid/` code path that calls `makeHab` without a version
- Test: `tests/serviceaid/test_providers_credgate.py` (consumes `recipient_pre`)

**Interfaces:**
- Consumes: `Habery.makeHab(name, transferable=, version=)` — **`makeHab` does NOT inherit `hby.version`** (diagnosis), so it must be passed `version=Vrsn_1_0` explicitly; `parsing.Parser(kvy=…, version=Vrsn_1_0)`.
- Produces: framework/test habs incept v1 bodies that the v1-pinned parser reads correctly; `recipient_pre` lands in `issuer_hby.kevers`. ~14 downstream tests depend on this (diagnosis #1/#4).

- [ ] **Step 1: Run the failing test.** `PYTHONPATH=. .venv/bin/python -m pytest tests/serviceaid/test_providers_credgate.py -v --import-mode=importlib` → FAIL: the v2 `makeHab` body + v1 count-code attachments mis-parse → `recipient_pre` never lands in `kevers`.

- [ ] **Step 2: Pin `makeHab` to v1 in the fixture** (and any other setup hab). Import `from keri.kering import Vrsn_1_0`; the fixture keeps its existing `Parser(..., version=Vrsn_1_0)`:

```python
@pytest.fixture
def recipient_pre(issuer_hby):
    rcp_hby = Habery(name="rcp", temp=True, salt=Salter(raw=b'fedcba9876543210').qb64)
    # TRANSITIONAL: keripy v2 ACDC issuance/registry/IPEX not implemented upstream
    # (acdc/registering.py, ipexing.py stubs). Hold v1. makeHab does NOT inherit
    # hby.version, so pin the event body explicitly. Lift when upstream ships v2.
    hab = rcp_hby.makeHab(name="rcp", transferable=True, version=Vrsn_1_0)
    pre = hab.pre
    kel = hab.replay()
    rcp_hby.close()
    parsing.Parser(kvy=issuer_hby.kvy, version=Vrsn_1_0).parse(ims=bytearray(kel))
    issuer_hby.kvy.processEscrows()
    assert pre in issuer_hby.kevers
    return pre
```

- [ ] **Step 3: Pin every other `makeHab`** the framework/tests call for setup (grep `makeHab` under `keri_serviceaid/` and `tests/serviceaid/`), adding `version=Vrsn_1_0` + the TRANSITIONAL comment.

- [ ] **Step 4: Run to verify pass** — `test_providers_credgate.py` gets past the fixture and passes.

- [ ] **Step 5: Commit.**

```bash
git add tests/serviceaid/conftest.py keri_serviceaid/
git commit -m "fix(serviceaid): pin hab inception to v1 on the v2 base (transitional; makeHab ignores hby.version)"
```

### Task 2: Pin the credential build + grant exn to v1 (the DEEP `ri` seam)

**Files:**
- Modify: `keri_serviceaid/providers/issue.py` (credential build 115-117; `ipexGrantExn` 190-191, 214-215)
- Modify (only if chosen): `src/keri/vdr/credentialing.py` (`Credentialer.create` — add a `version=` passthrough)
- Test: `tests/serviceaid/test_providers_issue.py`

**Interfaces:**
- Consumes: `Credentialer.create(regname, recp, schema, source, rules, data, private=False, …)` (credentialing.py:863) — forwards **no** version to `proving.credential`; `proving.credential(…, version:Version=Version, kind:Kinds=Kinds.json)` (proving.py:20-31) which **hardcodes `vc["ri"]=status`** (proving.py:79-80) and rides the v2 module default → `SerializeError: Unallowed extra field(s)=['ri']`; `protocoling.ipexGrantExn(hab, recp, message, acdc, iss, anc, dt, pvrsn=, gvrsn=)`.
- Produces: `IpexGrantIssuer.issue(reply, ctx)` returns a **v1** ACDC (with `ri`) inside a **v1 JSON** grant exn. Task 3 handles the deliver/parse path.

- [ ] **Step 1: Write the failing test.**

```python
def test_issue_produces_valid_v1_acdc_with_ri(issuer_hby, recipient_pre, rating_schema):
    grant_bytes, creder = issue_and_return_creder(issuer_hby, recipient_pre, rating_schema)
    assert "ri" in creder.sad and "rd" not in creder.sad      # held at v1
    assert creder.said                                        # serialized without SerializeError
```

- [ ] **Step 2: Run to verify it fails** — `SerializeError: Unallowed extra field(s)=['ri']` (the v2 `SerderACDC` rejecting the v1 label that `proving.credential` emitted).

- [ ] **Step 3: Pin the credential to v1.** Pick the smaller, more-removable change (both are proven by the diagnosis):
  - **(A) framework-only:** if `Credentialer.create` only *builds* the creder (does not also drive the TEL `iss`), replace its call in `issue.py` with `proving.credential(..., version=Vrsn_1_0)` and issue that. Otherwise —
  - **(B) core passthrough (preferred if create() also issues):** add `version: Version = Version` to `Credentialer.create` and forward it to its internal `credential(...)` call (credentialing.py ~891); in `issue.py` pass `version=Vrsn_1_0`.
  Add the TRANSITIONAL comment at the pin. Then pin both `ipexGrantExn` calls (issue.py:190-191, 214-215): pass `pvrsn=Vrsn_1_0, gvrsn=Vrsn_1_0` so the grant exn is v1 (not the v2 CESR-native default). **Do not touch the schemas** — `ri` is correct for a v1 ACDC.

- [ ] **Step 4: Run to verify pass** — the credential builds, carries `ri`, serializes cleanly.

- [ ] **Step 5: Commit.**

```bash
git add keri_serviceaid/providers/issue.py src/keri/vdr/credentialing.py tests/serviceaid/test_providers_issue.py
git commit -m "fix(serviceaid): pin ACDC issuance + grant exn to v1 (transitional; v2 issuance stubbed upstream)"
```

### Task 3: Pin test exns to v1 JSON

**Files:**
- Modify: `tests/serviceaid/_exn.py`
- Test: `tests/serviceaid/test_providers_deliver.py`

**Interfaces:**
- Consumes: `keri.core.eventing.exchange` / `keri.peer.exchanging.exchange` (the framework's v1-pinned `hby.psr` parser expects v1 JSON exns).
- Produces: `_exn.py` builds v1 JSON exns; the deliver path round-trips without `InvalidCodeError`/`DeserializeError`.

- [ ] **Step 1: Run the failing test** — `test_providers_deliver.py` → `InvalidCodeError 1AAG` or `DeserializeError -FAp0O…` (a v2 CESR-native exn parsed as v1 JSON).

- [ ] **Step 2: Build test exns as v1 JSON** in `_exn.py`: pass `kind=Kinds.json, version=Vrsn_1_0` (mirror the reverted `bd03ec72`), with the TRANSITIONAL comment.

- [ ] **Step 3: Run to verify pass** — `test_providers_deliver.py` passes.

- [ ] **Step 4: Commit.**

```bash
git add tests/serviceaid/_exn.py
git commit -m "test(serviceaid): build test exns as v1 JSON to match the v1-held framework parser (transitional)"
```

### Task 4: Green the full serviceaid suite + schema_host CDK/e2e at v1; document the hold

**Files:**
- Modify: any residual `tests/serviceaid/*.py`; add a `tests/serviceaid/conftest.py` module-level comment documenting the hold
- Test: full `tests/serviceaid/` + `tests/cdk/test_schema_host_*`

**Interfaces:**
- Consumes: Tasks 1-3.
- Produces: the entire hermetic serviceaid suite + schema.keri.host synth green on the v2 base, framework held v1, every pin documented.

- [ ] **Step 1: Run the full suite** — `PYTHONPATH=. .venv/bin/python -m pytest tests/serviceaid -q --import-mode=importlib`. Target: the diagnosis reached 75 passed with Tasks 1&3 alone; Task 2 clears the remaining `ri` failures. Capture any stragglers.

- [ ] **Step 2: Fix residual v1-assertion mismatches** — a test asserting a stale byte pattern or version string gets the v1 shape. If any test genuinely needs v2, that is out of scope (framework is held v1) — note it, don't force it.

- [ ] **Step 3: Run the schema_host synth + strict-schema e2e** — `pytest tests/cdk/test_schema_host_stack.py tests/cdk/test_schema_host_app.py tests/serviceaid/test_pipeline_publish_e2e.py tests/serviceaid/test_schema_host_handler_e2e.py -q --import-mode=importlib` → green (issuance validates against the strict `publication_receipt` schema at v1).

- [ ] **Step 4: Audit the pins** — `grep -rn "Vrsn_1_0\|Kinds.json" keri_serviceaid/ tests/serviceaid/` : every hit carries the TRANSITIONAL comment (or is inherent). Add a header comment in `conftest.py` summarizing the hold + the lift condition + the tracking pointer (this plan + the spec).

- [ ] **Step 5: Confirm the pre-existing-failure baseline** — `pytest tests/cdk/test_federation_config.py tests/cdk/test_keri_host_app.py` fail identically with changes `git stash`ed; note in the ledger.

- [ ] **Step 6: Commit.**

```bash
git add tests/serviceaid/ examples/schema_host
git commit -m "test(serviceaid): suite green on the v2 base with framework held v1; pins documented + tracked"
```

---

## Stage 2 — Adopt v2 for the witness receipt-store (`vrcsNew`, node-private)

### Task 5: Register `vrcsnew.` in `BASER_STORES` (keep OUT of `SHARED_KEL_STORES`)

**Files:**
- Modify: `src/keri/app/lambding.py` (`BASER_STORES` lines 34-60)
- Test: `tests/app/test_lambding_stores.py` (new) or extend `tests/serviceaid/test_runtime_v2.py`

**Interfaces:**
- Consumes: `basing.py:951` `self.vrcsNew = subing.CesrIoSetSuber(db=self, subkey='vrcsnew.', klas=indexing.Siger)`; `DynamoDBer.open(stores=…)` auto-creates a handle per name (dynamodbing.py:305-315).
- Produces: a DynamoDBer opened with `BASER_STORES` has a `vrcsnew.` handle; `SHARED_KEL_STORES` stays disjoint from it (node-private, like `vrcs.`).

- [ ] **Step 1: Write the failing test.**

```python
def test_vrcsnew_registered_and_node_private():
    from keri.app.lambding import BASER_STORES, SHARED_KEL_STORES
    assert "vrcsnew." in BASER_STORES
    assert "vrcsnew." not in SHARED_KEL_STORES   # per-witness write-log; sharing breaks toad convergence
    assert "vrcs." not in SHARED_KEL_STORES       # invariant unchanged
```

- [ ] **Step 2: Run to verify it fails** — `vrcsnew.` not yet in `BASER_STORES`.

- [ ] **Step 3: Add `"vrcsnew."` to `BASER_STORES`** adjacent to `"vrcs."`, with a comment; do NOT touch `SHARED_KEL_STORES`:

```python
    "sigs.",   "wigs.",   "rcts.",   "ures.",   "vrcs.",
    "vrcsnew.",  # v2 indexed transferable-receipt store (basing.py:951); per-witness
                 # WRITE-LOG like vrcs. — NEVER add to SHARED_KEL_STORES (pooling
                 # collapses witnesses' receipts to one -> breaks Receiptor toad).
```

- [ ] **Step 4: Verify a DynamoDBer actually creates the handle** (moto):

```python
def test_dynamodber_creates_vrcsnew():
    from keri.app.lambding import BASER_STORES
    from keri.db.dynamodbing import DynamoDBer
    from moto import mock_aws
    with mock_aws():
        db = DynamoDBer.open(name="wit", stores=BASER_STORES, table_name="t", clear=True)
        assert any("vrcsnew" in s for s in db._stores)
```

- [ ] **Step 5: Run to verify pass + commit.**

```bash
git add src/keri/app/lambding.py tests/app/test_lambding_stores.py
git commit -m "feat(v2): register vrcsNew in DynamoDBer store-set (node-private, out of SHARED_KEL_STORES)"
```

### Task 6: Re-prove oracle key-state pooling + receipt-log privacy

**Files:**
- Modify: `tests/serviceaid/test_runtime_v2.py` (`test_cross_habery_oracle_read_kever_visible`, lines 68-110)
- Test: same

**Interfaces:**
- Consumes: Task 5 (`vrcsnew.` registered, node-private); the shared-KEL oracle (`SHARED_KEL_STORES` pools key-state only).
- Produces: the hermetic proof that key-state pools cross-namespace while receipt write-logs (`vrcs.`/`vrcsnew.`) stay node-private — the property that protects `Receiptor` toad convergence.

- [ ] **Step 1: Confirm the oracle test still passes** — it builds a producer hab (v1-pinned per Task 1, `Parser(version=Vrsn_1_0)` correct) and reads key-state cross-service. Run it; it should pass unchanged after Task 1.

- [ ] **Step 2: Add the receipt-log-privacy assertion** so a future edit that pools a receipt store fails loudly:

```python
    from keri.app.lambding import SHARED_KEL_STORES
    assert {"vrcs.", "vrcsnew.", "wigs.", "rcts."}.isdisjoint(SHARED_KEL_STORES)
```

- [ ] **Step 3: Run to verify pass.**

- [ ] **Step 4: Record the live re-validation as a DEPLOY GATE** (not hermetic): after merge, re-run the 3-of-5 witness receipt round-trip on the live CDK federation (see `project_sam_to_cdk_cutover`; the locksmith `tests/integration/test_confirmdoer_receipts_over_http.py`). Also flag the **v1-framework / v2-witness boundary** (v1 serviceaid AIDs receipted by v2 witnesses) for live validation at schema.keri.host inception. Note both in the ledger.

- [ ] **Step 5: Commit.**

```bash
git add tests/serviceaid/test_runtime_v2.py
git commit -m "test(v2): assert oracle pools key-state while receipt write-logs (incl vrcsNew) stay node-private"
```

---

## Self-Review

**1. Spec coverage.** Stage 1 (hold v1): fixture/inception pin = Task 1; credential+grant-exn pin (the DEEP `ri` seam) = Task 2; test-exn pin = Task 3; suite + schema_host green + documented hold = Task 4. Stage 2 (v2 receipt-store): `vrcsNew` registration = Task 5; convergence/privacy re-proof = Task 6. Schemas correctly stay `ri`. v2 ACDC issuance is out of scope (upstream-blocked). Covered.

**2. Placeholder scan.** Task 2 Step 3 offers two proven approaches (A framework-only / B core passthrough) with a concrete decision rule (does `create()` also drive the TEL `iss`?) — not a placeholder; the byte-level target (`ri` present, no `SerializeError`) is exact. Other tasks carry literal code, commands, and expected failures.

**3. Type/name consistency.** `ri` held throughout (never `rd`); `Vrsn_1_0`/`Kinds.json` are the pins; `makeHab(version=)`, `proving.credential(version, kind)`, `Credentialer.create(...)`, `ipexGrantExn(pvrsn, gvrsn)`, `BASER_STORES`/`SHARED_KEL_STORES` (app/lambding.py), `DynamoDBer.open(stores=…)` — all match the survey.

**Notes (carry to the reviewer):** (a) every `Vrsn_1_0` pin must carry the TRANSITIONAL comment + lift condition — a pin without it is a review defect. (b) The whole v1-pin set is designed to lift as a unit when upstream ships v2 registry+IPEX — a future "resume Stage 1 v2" plan. (c) Implementer subagents may stamp a Sonnet co-author trailer; project convention is the Opus trailer — reconcile at squash/merge. (d) Fix commits re-run their covering test file and report the command + output.
