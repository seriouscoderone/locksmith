# Locksmith wallet → KERI v2 base (v1-hold) — Stage 3 design

**Status:** design (execute after review) · **Date:** 2026-07-07
**Base:** locksmith `development`. Locksmith's `pyproject.toml` already pins
`keri @ git+https://github.com/seriouscoderone/keripy.git@development` — the fork branch
now carrying the v2 base. The installed venv is **stale v1** (`kering.Version == (1,0)`);
a fresh `pip install`/reinstall pulls the now-v2 fork.
**Depends on:** the fork's v2 base reconciliation — **SHIPPED** (serviceaid held v1;
`vrcsNew` registered node-private; cold-start `vcp` reload fix). This is **Stage 3** of that effort.
**Inputs:** the v2-sensitive surface survey (46 seams, 29 at-risk), the live interop
verification (below), and the federation/migration findings.

## The core insight: two orthogonal "v2" concerns

Locksmith's migration is governed by two **independent** version axes:

| Concern | Decision | Why |
|---|---|---|
| **Event serialization version** | **HELD at v1** (transitional) | v2 ACDC issuance/registry/IPEX is stubbed upstream; the CESR attachment-framing interop is version-sensitive; mirrors the serviceaid hold. Locksmith emits + parses v1 consistently. |
| **DB schema version** | **ADOPTED v2** (unavoidable) | The v2 keripy `Baser` is DB `2.0.0-dev6`; the wallet runs on it regardless of event version. Existing v1 vaults (DB `1.3.4`) hit the migration error on open. |

**Net: v1 events stored in a v2-schema DB.** The DB-schema axis is what makes vault
handling non-optional — Locksmith ships **auto-updates**, so a v2 build opens users'
existing v1 vaults.

## What's already established (do not re-litigate)

- **Fork Stages 1–2 SHIPPED** to `fork/development`: serviceaid + schema.keri.host held v1;
  `vrcsNew` registered (node-private); the `Regery.loadRegistries` cold-start `vcp` regression fixed.
  v2 ACDC issuance/registry/IPEX is stubbed upstream → v1 hold is the only option for the
  credential/IPEX layer (see `project_keri_v2_migration`).
- **Interop verification (v1 AID ↔ v2 witness), live against a throwaway v2 witness:**
  - ✅ v2 witnesses run; a v1 AID incepts correctly (valid `KERI10JSON` icp, witness in `b`);
    the v2 witness serves its endpoint and **accepts the v1 event over HTTP (202)**; v2 keripy
    **ingests v1 KELs** (also the serviceaid oracle test).
  - ⚠️ The one failure mode: the receipt round-trip died on **"Missing attached signature(s)"**
    at the witness — the **CESR attachment count-code version** mismatch (v2-default attachment
    framing leaking onto a v1 body). This is the recurring root cause of the whole migration.
  - **Mitigation already in Locksmith:** the mailbox parser is pinned to `Vrsn_1_0`
    (`indirecting.py:108`, comment: *"keripy v2 still emits KERI 1.0 attachment counters on
    streams"*), plus the `message_version()` helper (`remoting.py:36`). A hand-rolled `Receiptor`
    on the dev build couldn't keep framing consistently v1; Locksmith's real stack should.
    **→ Stage 3c closes this with the real wallet.**
- **Federation → v2 is destroy-and-replace** (the `DynamoDBer` has no in-place migration by
  design); witness AIDs survive (secret-backed keeper). Independent of this Stage; noted for the cutover.

## Goal

Locksmith runs correctly on the v2 keripy fork — **holding its own KERI events at v1**
(transitional, unit-removable), **adopting the v2 DB schema**, and **migrating existing v1 vaults
on open (with backup)** — with all tests green and the v1-AID/v2-witness interop proven using
Locksmith's real witnessing stack.

## Guiding principle

- **Event serialization: v1 hold.** No `Vrsn_2_0` for Locksmith's own events. Every pin carries a
  `# TRANSITIONAL: …` comment and lifts as a unit (grep `TRANSITIONAL`) jointly with serviceaid
  when upstream ships v2 registry+IPEX.
- **DB schema: v2.** Use **keripy's own migration mechanism** — do not hand-roll DB transforms
  (BE KERI NATIVE).
- **UX-first:** migration is visible, backed up, and reversible; a failed migration never silently
  bricks a wallet (`feedback_ux_first_deployment`).

## Scope

### Stage 3a — Outbound event pins (v1 hold)
Pin every seam that emits a KERI event/exn/credential to v1, grounded in the survey map:

- **`makeHab` (5):** `core/vaulting.py:76`, `core/habbing.py:498` + `:654` (InceptDoer),
  `plugins/kerifoundation/onboarding/service.py:1123` + `:1163`. Add `version=Vrsn_1_0`
  (`makeHab` does NOT inherit `hby.version`).
- **Exn builders (8):** `core/ipexing.py` grant/admit/multisig (`:100,:189,:334,:358,:711,:763`),
  `core/remoting.py:929` (challenge `exchange`), `core/credentialing.py:224`
  (`multisigRegistryInceptExn`). Frame v1 (`pvrsn=Vrsn_1_0`, no pathed embeds).
- **Credential issuance (8):** `core/credentialing.py` `Credentialer.create`/`Registry`/`Registrar`
  (`:203,:209,:217,:304,:375,:384,:398`), `core/vaulting.py:119`. Use the additive
  `Credentialer.create(version=Vrsn_1_0)` seam added in the fork; keep schemas at `ri`.
- **`Kevery`/`Tevery` (8):** `core/vaulting.py:142,:145`, `core/ipexing.py:133`,
  `core/indirecting.py:92`, `core/adjudication.py:197`, `core/credentialing.py:565`. Pass
  `version=Vrsn_1_0` where they construct/parse.

Prefer a small central hold where clean (as serviceaid used one autouse test fixture), but the
production seams (`vaulting`, `habbing`, `credentialing`) pin explicitly. Definition of done:
the pinned paths produce v1 events on the v2 keripy.

### Stage 3b — Vault DB migration (migrate-on-open, with backup)
On opening a vault whose DB schema is < current:
1. **Back up** the vault directory (KEL/reg/keystore) to a timestamped path before touching it.
2. Run **keripy's migrations** (`add_key_and_reg_state_schemas`, `hab_data_rename`, `rekey_habs`)
   to upgrade the DB to the v2 schema. Reuse keripy's migration runner (`kli migrate run` opens a
   `Baser`); wire the equivalent through Locksmith's vault-open path.
3. **Cover Locksmith's custom LMDB stores** — audit `db/basing.py` `LocksmithBaser` and
   `plugins/kerifoundation/db/basing.py` `KFBaser`: determine whether the standard migrations touch
   their custom stores or whether custom migration steps are needed.
4. **UX:** a one-time "upgrading your vault" step in the UI; show the backup location; on failure,
   restore from backup and surface a clear error (never a silent brick).

Validate against a **real captured v1 vault fixture** early — migration MUST preserve AIDs,
credentials, peer connections, and settings.

### Stage 3c — Validate-early interop gate (run FIRST)
Before the bulk pinning, de-risk the load-bearing assumption:
- Stand up one **v2 witness** (local `kli witness demo --version 2.0 --base <fresh>` — fresh base
  avoids the v1-DB migration error).
- Open a **real Locksmith vault**, incept a **v1** AID witnessed by that v2 witness **via
  `LocksmithReceiptor`**, and assert toad receipts converge.
- This closes what the hand-rolled harness couldn't (the real stack frames v1 attachments
  consistently). **If it fails on attachment-framing**, the fix is localized: ensure the outbound
  `Poster`/`LocksmithReceiptor` frame v1 attachments; keep parsers at `Vrsn_1_0`.

### Parsing / receipts (keep + confirm — LOW risk)
Already v2-ready and load-bearing for mixed-version interop: `message_version()`
(`remoting.py:36`), mailbox parser pinned `Vrsn_1_0` (`indirecting.py:101-108`), receipts
hardcoded v1 (`receipting.py:224,:251`). Confirm no regressions; these are the INBOUND handlers
that make the v1-hold interop work.

## Testing

- **Interop gate (3c)** — real vault + v2 witness (the definitive receipt round-trip).
- **Vault migration** — real v1-vault fixture → v2 schema; assert AIDs/credentials/peers/settings preserved.
- **Locksmith UI harness** (real widgets, `objectName` selectors; `reference_ui_harness_cypress`) —
  vault open/migrate, incept, credential issue, peer + IPEX flows on the v2 base.
- **Hermetic core tests** (`tests/`) — pinned paths green.
- **Reinstall the Locksmith venv to the v2 fork** (the pin already points there) — this is where
  breakage surfaces; run the suite + harness against it.

## Non-goals

- v2-native events for Locksmith (blocked upstream; v1 hold).
- Migrating the federation (separate effort; destroy-replace).
- New v2 ACDC features (bulk issuance, aggregate/blinded SAIDs).

## Risks

- **Attachment-framing interop** (3c) — mitigated by Locksmith's existing v1-pinned inbound + the
  early gate; localized fix if it bites.
- **Custom-store migration coverage** (3b) — audit + real-vault validation before shipping.
- **keripy dev build (`2.0.0-dev6`) rough edges** in the witnessing/OOBI HTTP path — validate
  against it; may need to track an upstream fix rather than work around.
- **Auto-update ordering** — a v2 build must not reach users before 3b is proven, or existing
  vaults brick on open.

## Open questions (resolve at plan time)

1. Central hold mechanism for Locksmith (a single vault-level version default vs. per-call pins) —
   the fork used explicit pins + one autouse test fixture; confirm the production equivalent.
2. Exact keripy migration-runner reuse from within Locksmith's vault-open (call `kli`-level runner
   vs. invoke the migration classes directly).
3. Does 3c need only `wan` (toad 1) or a small multi-witness set to exercise toad convergence realistically?

## Branch / sequencing

- Fresh branch off locksmith `development` (e.g. `feat/keri-v2-migration`); harness-first per
  convention (`feedback_harness_first`).
- **Order:** 3c interop gate FIRST (de-risk) → 3a outbound pins → 3b vault migration → full
  validation (venv reinstall to v2, UI harness, hermetic, migration fixture).

## References

- Fork v2 spec + plan: `docs/superpowers/specs/2026-07-07-keri-v2-migration-design.md`,
  `docs/superpowers/plans/2026-07-07-keri-v2-migration.md` (shipped).
- Interop verification scripts: session scratchpad (`verify_v1_on_v2_receipt.py`, `collect_receipt.py`).
- Memory: `project_keri_v2_migration`, `project_peer_mode_shipped`, `project_phase5_shipped`
  (Sparkle auto-update), `reference_ui_harness_cypress`, `feedback_ux_first_deployment`,
  `feedback_harness_first`.
