# KERI v2 (full-CESR) migration — fork custom code + Locksmith

**Status:** design (execute next session) · **Date:** 2026-07-07
**Base:** keripy fork `development @ b8630d45` (upstream `origin/main` merged in `452b102c` + `MaxNamedDBs 100→200` in `b8630d45`; the 3 exploratory v1-pin commits were reverted).
**Inputs:** the upstream-commit survey (range `d9e9c6c6..origin/main`, 108 commits — see References), the diagnosis (`~/code/keripy/.superpowers/sdd/upstream-sync-diagnosis.md`), and direct guidance from a KERI core dev (quoted below).

## What "KERI v2" actually is (core-dev framing — read this first)

Per a KERI core maintainer (2026-07-07), quoted:

- *"Right now it's really only to make sure it's KERI **v2 compliant** which is mostly done. The ACDC v2 stuff will come over the next couple months as those features are developed. **They don't exist yet.**"*
- *"It's about making keripy **actually compliant with the KERI spec**, which until v2 it actually has not been. So there's stuff in the spec that keripy didn't actually do, mostly related to **message serialization (full cesr), parsing, and attachments**. I don't think we have a definitive list of what that means but **the commits should tell a pretty clear story**."*
- *"it's **keripy v2 which is actually keri spec v1**."*
- *"We recently changed the **global defaults in keripy (`kering.py`) to version 2.0, and default kind to `cesr`**, which triggers different behavior for messages, parsers, etc. So that's where you'll want to start looking."*

**Consequences for this migration:**
1. This is **not a new protocol** and **not new ACDC features**. It is keripy finally implementing **KERI spec v1** correctly — chiefly **full-CESR message serialization, parsing, and attachments**. "keripy v2" ≙ "KERI spec v1 compliant."
2. **ACDC v2 features (bulk issuance, aggregate/blinded SAIDs, the new `keri/acdc/*.py` stub modules) DO NOT EXIST YET → OUT OF SCOPE.** We do not adopt them. Our job is compliance, not new features.
3. **The `keri` plugin skills (`keri:cesr`, `keri:spec`, `keri:acdc`) are spec-based**, and since keripy-v2 is keripy *catching up to that spec*, **the skills are now the authoritative reference for correct v2 wire behavior.** Where keripy's older code and the skills/spec disagree, **the spec defines "compliant."** Execution must cross-check against these skills, not assume pre-v2 keripy was right.

## Root cause of the breakage (survey + diagnosis)

Upstream flipped the global defaults in `src/keri/kering.py` (and `serdering.py`/`eventing.py`) to **`version = 2.0`** and **`kind = CESR`** (was `1.0` / JSON). Every event/exn/credential-creation path now produces **v2 full-CESR binary by default** unless a caller explicitly passes a version/kind.

Our fork's `keri_serviceaid` framework passed **no** version/kind, so it **silently rode v2** and broke where our code/tests/schemas still assumed v1-JSON. The diagnosis isolated the breakage to a **single root cause** hitting exactly these seams (verdict: **bounded**):

1. **`makeHab`** does not inherit `hby.version` → habs incept as v2; the `recipient_pre` test fixture's `replay()`→parse round-trip broke (v2 body + still-v1 attachment framing → parser reads the sig group wrong → 14 of 17 failures cascaded from here).
2. **`exchange()` / `protocoling.ipexGrantExn`** default `kind=CESR` → v2 CESR-native exns; v2 also **forbids pathed embeds**. (The `1AAG` `InvalidCodeError` and `-FAp` `DeserializeError` were v1/v2 framing collisions in test exns.)
3. **`proving.credential()` (via `Credentialer.create`)** defaults to v2, where the ACDC **registry field renamed `ri` → `rd`** → a v2 ACDC rejects `ri` (`Unallowed extra field(s)=['ri']`). All remaining failures converge here.

Also relevant (not hit by the no-backer serviceaid tests, but real for the deploy/witness path): the **receipt-storage refactor** — transferable receipts moved from flat `vrcs` to indexed `vrcsNew`, and the counter code `TransReceiptQuadruples` (`-D`/`-N`) was renamed `TransReceiptIdxSigGroups`.

## Goal + guiding principle

Make the fork's custom code (the `keri_serviceaid` framework, the custom `DynamoDBer`, the shared-KEL oracle), its tests, and (staged) the Locksmith wallet **produce and consume v2 full-CESR messages, spec-compliant**, with all tests green **on the v2 defaults** — i.e. **v2-native**, NOT by pinning `Vrsn_1_0`.

**Principle:** do NOT pass `version=Vrsn_1_0` to dodge the change (that keeps us non-compliant — the opposite of the goal). Instead make our code/tests/schemas correct for v2. Pinning is only acceptable as a temporary, clearly-commented transitional step if a stage cannot otherwise proceed, and must be removed before the stage is "done."

## Scope (staged)

### Stage 1 — `keri_serviceaid` + schema.keri.host → v2-native + green
The bounded core. Work items (grounded in the diagnosis seams + the `keri:cesr`/`keri:acdc` skills):

- **ACDC field `ri` → `rd`.** Update our ACDC schemas to the v2 field name: **`examples/schema_host/schema/publication_receipt.json`** (`required` + `properties` currently carry `ri`) and **`examples/gated_retrieval/schema/gated_record.json`**. Confirm the exact v2 ACDC top-level field set against `keri:acdc` (there may be more than just `ri→rd`). Re-saidify any schema whose content changes.
- **Issuance leaf goes v2.** In `keri_serviceaid/providers/issue.py`, let the credential build v2 (don't pin v1); ensure the receipt attributes + our `publication_receipt` schema match the v2 ACDC shape; frame `ipexGrantExn` for v2 (no v1 embeds).
- **Exn framing v2.** Audit every `exchange()`/`ipexGrantExn`/exn-build path in the framework for v2 correctness (no pathed embeds; `kind=cesr`).
- **Tests + fixtures → v2 assertions (the bulk).** Update `tests/serviceaid/` (conftest fixtures incl. `recipient_pre`, the ~15 test files) to build and assert **v2** shapes — mirroring how upstream adapted its own test suite. The `recipient_pre` fixture's `makeHab`/`replay`/parse must round-trip v2.
- **Definition of done:** the hermetic serviceaid suite + the `schema_host` CDK tests pass **on v2 defaults, with no `Vrsn_1_0` pins**; the strict-schema issuance e2e still proves issuance (now v2).

### Stage 2 — custom `DynamoDBer` + shared-KEL oracle (receipt-store reconciliation)
The sneaky one — not covered by Stage 1's no-backer tests, but load-bearing for the live witness/mailbox/deploy path.

- Reconcile the receipt refactor (`vrcs` → `vrcsNew` / `TransReceiptIdxSigGroups`) in the fork's `src/keri/db/dynamodbing.py` `DynamoDBer` (which mirrors keripy's Baser store set) and in the shared-KEL oracle's `SHARED_KEL_STORES` narrowing (memory: the oracle was narrowed to key-state + reachability; verify `vrcsNew` classification vs. the per-witness write-logs that must stay node-private for `Receiptor` toad convergence).
- Re-validate **witness-receipt convergence** end-to-end (this is the exact property the shared-KEL narrowing protects — see `project_kel_public_shared_oracle` / `project_sam_to_cdk_cutover`).

### Stage 3 — Locksmith wallet → v2 (separate repo, fast-follow)
Its own spec/plan. Locksmith depends on stock keripy APIs; a v2 fork pulls it along. Scope + sequence after Stages 1–2 land. (Not detailed here.)

## Non-goals
- **No ACDC v2 features** (bulk issuance, aggregate/blinded SAIDs) — they don't exist upstream yet.
- **No adoption of the new `keri/acdc/*.py` stub modules** — future scaffolding, irrelevant to compliance.
- **No v1-pinning as the end state** — pinning is anti-compliance; only a temporary, commented crutch if unavoidable, removed before stage-done.
- **No rollback of the upstream merge** — we want v2.

## Grounding method (how execution decides "correct")
1. Start from `kering.py` (the version 2.0 / `kind=cesr` defaults) and follow the commits (`git log d9e9c6c6..origin/main`) for the "clear story."
2. For wire format (full-CESR serialization, parsing, attachments, count/group codes, SAID derivation, ACDC sections/fields), **treat the `keri:cesr` / `keri:spec` / `keri:acdc` skills as authoritative** — they are spec-based and now align with v2. Cross-check keripy behavior against them; where they differ, the spec is "compliant."
3. Use the diagnosis report (`upstream-sync-diagnosis.md`) as the seam map for Stage 1.

## Verification
- Stage 1: `cd ~/code/keripy && PYTHONPATH=. .venv/bin/python -m pytest tests/serviceaid tests/cdk/test_schema_host_stack.py tests/cdk/test_schema_host_app.py -q` → green, **with zero `Vrsn_1_0` pins** in the framework. Confirm messages are v2 full-CESR (kind=cesr) by inspection.
- Stage 2: witness-receipt convergence re-proven (the shared-KEL oracle probe / a receipt round-trip); the live-deploy `DEPLOY_RUNBOOK` still valid.
- Full keripy suite: a broad run is the fork maintainer's separate gate — note (do not silently assume) any pre-existing failures. (Known pre-existing: `tests/cdk/test_federation_config`, `test_keri_host_app` — a committed-config/privacy check, unrelated.)

## Open questions (resolve at next-session brainstorm)
1. **v2-native everywhere vs. any transitional shim** — confirm we take v2 defaults straight (recommended) rather than an explicit-`Vrsn_2_0`-param style.
2. **Depth of the Stage 2 DynamoDBer/oracle receipt-store work** — is `vrcsNew` a key-state store (shareable) or a per-witness write-log (must stay node-private)? This decides the `SHARED_KEL_STORES` change and must not break `Receiptor` toad convergence.
3. **Exact v2 ACDC field set** — is it only `ri→rd`, or are there other top-level/section field changes per `keri:acdc`? (Affects our schemas.)
4. **Locksmith staging** — sequence + scope of Stage 3.

## References
- Diagnosis: `~/code/keripy/.superpowers/sdd/upstream-sync-diagnosis.md` (the seam map + bounded verdict).
- Execution ledger: `~/code/keripy/.superpowers/sdd/progress.md` (upstream-sync section).
- Upstream range: merge-base `d9e9c6c6` → `origin/main` (108 commits). Key files: `src/keri/kering.py` (defaults), `src/keri/core/serdering.py`/`eventing.py`/`coring.py`/`counting.py` (CESR/v2), `src/keri/db/basing.py` (`vrcsNew`), `src/keri/vc/protocoling.py`, `src/keri/vdr/credentialing.py`.
- Skills (authoritative for v2 wire format): `keri:cesr`, `keri:spec`, `keri:acdc`.
- Related memory: `project_kel_public_shared_oracle`, `project_sam_to_cdk_cutover`, `reference_keri_communication_model`.

## Repos / branches
- keripy fork: a fresh branch off `development @ b8630d45` (e.g. `feat/keri-v2-migration`); commit per stage/task; **do not push** without approval; keripy pushes → seriouscoderone fork only.
- Locksmith: Stage 3, its own branch, later.
