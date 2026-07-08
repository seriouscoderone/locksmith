# Locksmith wallet → KERI v2 base (v1-hold) — Stage 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Real wallet/UI work runs in the MAIN session, never delegated to subagents** (per project rule — a subagent's "it launched" is unverifiable).

**Goal:** Make the Locksmith wallet run correctly on the v2 keripy fork — **holding its own KERI events at v1** (transitional, unit-removable), **adopting the v2 DB schema**, and **migrating existing v1 vaults on open (with backup)** — with all tests green and the v1-AID/v2-witness interop proven via the real `LocksmithReceiptor`.

**Architecture:** Two orthogonal axes — **event serialization HELD v1** (pin the outbound seams) and **DB schema ADOPTED v2** (migrate-on-open existing vaults). Sequence: the **validate-early interop gate (3c) FIRST** to de-risk the load-bearing assumption, then the **outbound v1 pins (3a)**, then **vault migrate-on-open (3b)**. Parsing/receipts are already v2-ready (`message_version` + v1-pinned mailbox parser) — keep + confirm.

**Tech Stack:** Locksmith (PySide6 wallet over a transport-agnostic `core/`), the keripy v2 fork (editable install), LMDB (`LocksmithBaser`), pytest + the Locksmith UI harness, a local `kli` v2 witness.

## Global Constraints

- **Base:** a fresh branch `feat/keri-v2-migration` off locksmith `development`; harness-first (`feedback_harness_first`).
- **Event serialization HELD v1:** every Locksmith-emitted event/exn/credential is pinned `version=Vrsn_1_0` (exns `pvrsn=Vrsn_1_0`). Every pin carries `# TRANSITIONAL: keripy v2 ACDC issuance/registry/IPEX not implemented upstream; lift as a unit when it ships.` and lifts jointly with serviceaid (grep `TRANSITIONAL`).
- **DB schema ADOPTED v2:** run on the v2 keripy `Baser`; existing v1 vaults are **migrated on open, WITH a backup first** — a failed migration restores the backup and surfaces a clear error, **never a silent brick**.
- **Use keripy's OWN migration mechanism** (BE KERI NATIVE) — no hand-rolled DB transforms.
- **ACDC schemas stay `ri`** (v1); no v2 ACDC features (bulk issuance, aggregate/blinded SAIDs).
- **keripy pin:** `keri @ git+…/seriouscoderone/keripy.git@development` (now v2). **Reinstall the Locksmith venv to the v2 fork** as part of validation — that reinstall is where breakage surfaces.
- **Testing:** UI flows via the Locksmith UI harness (real widgets, `objectName` selectors; `reference_ui_harness_cypress`); add structured log lines for state the harness can't observe (`feedback_testing_automated`). Hermetic core tests under `tests/`.
- **Do NOT push;** commit per task on the feature branch; merge only when asked.
- **Known-good reference:** the serviceaid v1-hold (fork `development`) — the additive `Credentialer.create(version=Vrsn_1_0)` seam, the pin pattern, and the interop findings are shipped there.

## File Structure

**3c — interop gate (run first):**
- Create: `tests/integration/test_v1_aid_v2_witness_receipt.py` (or a `.sh` harness driver) — real vault + local v2 witness, v1 AID witnessed via `LocksmithReceiptor`, assert toad receipts converge.

**3a — outbound v1 pins:**
- Modify: `core/vaulting.py` (makeHab :76; `Kevery`/`Tevery` :142,:145; credential infra :119), `core/habbing.py` (makeHab :498,:654 InceptDoer), `core/ipexing.py` (grant/admit/multisig exns; `Kevery`/`Tevery` :133), `core/credentialing.py` (`Credentialer.create`/`Registry`/`Registrar`; multisig-registry exn :224; Receiptor :565), `core/remoting.py` (challenge `exchange` :929), `core/adjudication.py` (`Kevery` :197), `plugins/kerifoundation/onboarding/service.py` (makeHab :1123,:1163).

**3b — vault migrate-on-open:**
- Create: `core/migrating.py` (new) — DB-version detection + backup + run keripy migrations. (Exact hook site + runner API pending the vault-open survey.)
- Modify: the vault-open path (`core/vaulting.py` / `core/apping.py`) to call migrate-on-open before the Habery opens; UI surface for the one-time upgrade + backup path.
- Test: `tests/**/test_vault_migration.py` + a captured **real v1-vault fixture**.

**Keep + confirm (low risk):** `core/remoting.py:36` (`message_version`), `core/indirecting.py:101-108` (mailbox parser pinned `Vrsn_1_0`), `core/receipting.py` (v1 receipts).

---

## Grounding (from the vault-open survey)

- **Vault-open:** `core/habbing.py:open_hby()` (91-136) constructs `hby = habbing.Habery(name=…, bran=…, base=base, salt=…)` at :128; `Habery.__init__` auto-calls `setup()` → `Baser.reload()`, which raises `DatabaseError("Database migrations must be run. DB version … current …")` (keripy `basing.py:1347`) on a stale schema. The error propagates uncaught to the UI.
- **Programmatic migration runner:** `Baser.migrate()` (keripy `basing.py:1371`) runs pending migrations; it is NOT auto-run on reopen. `Baser.current` (property) reports whether migrations are pending. `MIGRATIONS = [("0.6.8",["hab_data_rename"]),("1.0.0",["add_key_and_reg_state_schemas"]),("1.2.0",["rekey_habs"])]`. Pattern: `db = Baser(name, base, temp=False, reopen=False); db.reopen(); (db.current or db.migrate())`.
- **Custom stores** — `LocksmithBaser` (`idm`,`mbx`,`pluginSettings`,`peer*`) and `KFBaser` (`accounts`,`witnesses`,…) are all `Komer` (JSON, schema-agnostic) → stock migrations don't touch them; safe. `LocksmithBaser`/`KFBaser` extend `LMDBer` (not `Baser`) and don't run the version check, so **only the Habery's stock `Baser` (the KEL db, `~/.keri/db/<name>`) triggers the migration**; the Regery's `Reger` should be checked too.
- **On-disk vault dirs (backup targets):** `~/.keri/db/<name>` (KEL), `~/.keri/rt/<name>` (LocksmithBaser), `~/.keri/kf/<name>` (KFBaser), `~/.keri/<name>` (keystore/Regery/config) — or the `/usr/local/var/keri/…` head. Name/base from `LocksmithConfig`.

---

## Task 1: Establish the v2 baseline (venv → v2 fork; inventory breakage)

**Files:** none (environment + notes)

**Interfaces:** Produces a v2 Locksmith venv and a captured list of what breaks — the work-list the later tasks close.

- [ ] **Step 1:** Point the Locksmith venv's keri at the v2 fork (editable-local, matching the tree the fork migration shipped on):
  `cd /Users/seriouscoderone/code/locksmith && .venv/bin/pip install -e /Users/seriouscoderone/code/keripy`
- [ ] **Step 2:** Confirm v2: `.venv/bin/python -c "from keri import kering; print(kering.Version)"` → `Versionage(major=2, minor=0)`.
- [ ] **Step 3:** Run the hermetic suite, capture failures: `.venv/bin/python -m pytest tests -q --import-mode=importlib 2>&1 | tail -40`. Record the failing tests + errors in the ledger (this is the baseline the pins/migration must clear). Expect inception/exn/credential + DB-open failures.
- [ ] **Step 4:** Commit the baseline note (no code): `git commit --allow-empty -m "chore(v2): pin locksmith venv to the v2 keripy fork; record baseline breakage"`.

## Task 2: Pin hab inception to v1

**Files:**
- Modify: `core/vaulting.py:76` (Vault settings hab), `core/habbing.py:498`, `:654` (InceptDoer), `plugins/kerifoundation/onboarding/service.py:1123`, `:1163`
- Test: `tests/…test_hab_inception_v1` (new or extend an existing vaulting/habbing test)

**Interfaces:**
- Consumes: `hby.makeHab(name=…, …, version=Vrsn_1_0)` — `makeHab` does NOT inherit `hby.version` (verified in the fork work).
- Produces: every Locksmith-created hab incepts a v1 (`KERI10JSON`) icp. Task 3's interop gate + Task 6's credential path rely on this.

- [ ] **Step 1: Write the failing test** — assert a vault-created hab is v1:

```python
def test_vault_hab_incepts_v1(tmp_vault):
    hab = tmp_vault.hby.makeHab(name="probe", transferable=True)  # via the code path under test
    assert hab.kever.serder.sad["v"].startswith("KERI10JSON"), "hab must incept v1 while held"
```

- [ ] **Step 2: Run → FAIL** (on the v2 venv, `makeHab` defaults v2: `KERICAACAA…`).
- [ ] **Step 3: Pin each `makeHab`** — add `version=Vrsn_1_0` + the `# TRANSITIONAL:` comment. Import `from keri.kering import Vrsn_1_0` where missing. Example (`core/vaulting.py:76`):

```python
hab = self.hby.makeHab(name=self.pluginSettings.locksmith_alias,
                       transferable=True, ns="settings", version=Vrsn_1_0)
```

- [ ] **Step 4: Run → PASS.** Spot-check `core/habbing.py` InceptDoer + KF onboarding sites the same way.
- [ ] **Step 5: Commit** `git commit -m "fix(v2): pin hab inception to v1 (transitional)"`.

## Task 3: Interop gate — v1 AID witnessed by a v2 witness via `LocksmithReceiptor`  *(MAIN SESSION)*

**Files:**
- Create: `tests/integration/test_v1_aid_v2_witness_receipt.py` (headless-vault driver, like `test_confirmdoer_receipts_over_http.py`)

**Interfaces:**
- Consumes: Task 2 (v1 inception); `LocksmithReceiptor` (`core/receipting.py`); a local v2 witness.
- Produces: **the definitive interop proof** — the fork work verified up to the CESR attachment-framing boundary; this closes it with the real wallet stack.

- [ ] **Step 1:** Start a throwaway v2 witness: `cd ~/code/keripy && PYTHONPATH=. .venv/bin/kli witness demo --version 2.0 --base <fresh> --loglevel INFO` (background). `wan` = `BBilc4-L3tFUnfM_wJr4S4OJanAv_VmF_dJNN6vkf2Ha` on http 5642. (Fresh `--base` avoids the v1-DB migration error.)
- [ ] **Step 2: Write the test** — headless `Vault` on a raw `Doist`; incept a **v1** AID with `wits=[wan]`, `toad=1`; resolve wan's OOBI through the vault's resolver (so the loc is recorded — the gap my hand-harness hit); drive `LocksmithReceiptor`; assert the wig lands (`hby.db.getWigs`/the receipt store shows ≥1). Add a structured log line reporting the receipt count (`feedback_testing_automated`).
- [ ] **Step 3: Run.** If green → interop CONFIRMED; record it. If it fails on "Missing attached signature(s)" (attachment framing), apply the localized fix: ensure the outbound `Poster`/`LocksmithReceiptor` frame v1 attachments (`Vrsn_1_0`) and parsers stay pinned; re-run.
- [ ] **Step 4:** Stop the witness (targeted: `pkill -f "witness demo …<fresh base>"`).
- [ ] **Step 5: Commit** the gate test + any framing fix.

## Task 4: Pin `Kevery`/`Tevery` construction to v1

**Files:** Modify `core/vaulting.py:142`,`:145`, `core/ipexing.py:133`, `core/indirecting.py:92`, `core/adjudication.py:197`, `core/credentialing.py:565`
**Interfaces:** Produces v1-consistent event/TEL processing on the v2 base.

- [ ] **Step 1:** Add `version=Vrsn_1_0` to each `Kevery(...)`/`Tevery(...)` construction (+ TRANSITIONAL comment). e.g. `core/vaulting.py:142`: `self.kvy = eventing.Kevery(db=hby.db, lax=True, local=False, rvy=self.rvy, cues=self.cues, version=Vrsn_1_0)`.
- [ ] **Step 2:** Run the affected tests (mailbox/indirecting, adjudication, ipex) → green.
- [ ] **Step 3: Commit** `git commit -m "fix(v2): pin Kevery/Tevery to v1 (transitional)"`.

## Task 5: Pin IPEX + challenge exns to v1

**Files:** Modify `core/ipexing.py` (`ipexGrantExn`/`ipexAdmitExn` `:100,:189,:334,:711`; `multisigExn` `:358,:763`), `core/remoting.py:929` (`exchange`), `core/credentialing.py:224` (`multisigRegistryInceptExn`)
**Interfaces:** Produces v1 exns (JSON, no pathed embeds), matching the v1-pinned parser.

- [ ] **Step 1: Write/adjust the failing test** — a grant exn round-trips v1 through the framework (no `InvalidCodeError`/`DeserializeError`).
- [ ] **Step 2: Run → FAIL** (v2 CESR-native exn).
- [ ] **Step 3:** Pass `pvrsn=Vrsn_1_0` to each `ipexGrantExn`/`ipexAdmitExn`; for `exchange()` pass `version=Vrsn_1_0, kind=Kinds.json`; for `multisigExn`/`multisigRegistryInceptExn` pin per their signatures (+ TRANSITIONAL).
- [ ] **Step 4: Run → PASS** (ipex tests green).
- [ ] **Step 5: Commit.**

## Task 6: Pin credential issuance + registry to v1

**Files:** Modify `core/credentialing.py` (`Credentialer.create` call `:375`; `Registry`/`Registrar` `:203,:209,:217,:304,:384,:398`), `core/vaulting.py:119`
**Interfaces:** Consumes the fork's additive `Credentialer.create(version=Vrsn_1_0)` seam. Produces a v1 ACDC (`ri`) + v1 registry (`vcp`).

- [ ] **Step 1: Write the failing test** — issuing a credential yields a v1 ACDC with `ri` (no `SerializeError: Unallowed extra field(s)=['ri']`).
- [ ] **Step 2: Run → FAIL** (`ri` rejected at v2 default).
- [ ] **Step 3:** Pass `version=Vrsn_1_0` to `credentialer.create(...)` (`:375`); ensure the registry/hab are v1 (Task 2 covers the hab → registry inherits v1). Keep schemas at `ri`. TRANSITIONAL comments.
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit.**

## Task 7: `core/migrating.py` — detect + back up + migrate (hermetic)

**Files:**
- Create: `core/migrating.py`
- Test: `tests/…/test_vault_migration.py` + a captured **real v1-vault fixture** (a tarball of a pre-v2 vault checked into `tests/fixtures/`)

**Interfaces:**
- Consumes: keripy `Baser(name, base, temp=False, reopen=False)`, `.reopen()`, `.current`, `.migrate()`.
- Produces: `ensure_migrated(name, base, *, backup_root=None, stamp=None) -> Path | None` — returns the backup path if it migrated, else None. Task 8 calls it before `Habery(...)`.

- [ ] **Step 1: Write the failing test** — unpack the v1-vault fixture into a temp `~/.keri`, call `ensure_migrated(name, base)`, assert (a) a backup was created, (b) `Baser(...).reopen().current` is now True, (c) the habs/credentials survive (open a `Habery` cleanly + the AID + a credential are present).
- [ ] **Step 2: Run → FAIL** (no module).
- [ ] **Step 3: Implement `core/migrating.py`:**

```python
"""Migrate a vault's KERI DB schema to the running keripy version, backing up first.
TRANSITIONAL/UX: Locksmith auto-updates, so a v2 build opens users' v1 vaults; migrate
on open and never brick — a failed migration restores the backup and surfaces the error."""
from __future__ import annotations
import shutil, tarfile
from pathlib import Path
from keri.db.basing import Baser
from keri.help import helping

# vault dirs (relative to the keri head dir) keyed by store; see the vault-open survey
_SUBDIRS = ("db", "rt", "kf", "")   # "" = keystore/Regery/config under keri/<name>

def _keri_head() -> Path:
    p = Path("/usr/local/var/keri")
    return p if p.is_dir() else (Path.home() / ".keri")

def _vault_paths(name: str) -> list[Path]:
    head = _keri_head()
    out = []
    for sub in _SUBDIRS:
        d = (head / sub / name) if sub else (head / name)
        if d.exists():
            out.append(d)
    return out

def backup_vault(name: str, *, backup_root: Path | None = None, stamp: str | None = None) -> Path:
    stamp = stamp or helping.nowIso8601().replace(":", "").replace(".", "")
    root = backup_root or (Path.home() / ".locksmith" / "backups")
    root.mkdir(parents=True, exist_ok=True)
    tarpath = root / f"{name}-v1-backup-{stamp}.tar.gz"
    with tarfile.open(tarpath, "w:gz") as tar:
        for d in _vault_paths(name):
            tar.add(d, arcname=str(d.relative_to(_keri_head())))
    return tarpath

def ensure_migrated(name: str, base: str = "", *, backup_root: Path | None = None,
                    stamp: str | None = None) -> Path | None:
    """If the vault's KEL Baser has pending migrations, back up then migrate. Returns the
    backup path if it migrated, else None."""
    db = Baser(name=name, base=base, temp=False, reopen=False)
    db.reopen()
    try:
        if db.current:
            return None
        backup = backup_vault(name, backup_root=backup_root, stamp=stamp)
    finally:
        db.close()
    # migrate on a freshly reopened Baser (migrate() expects an open db)
    db = Baser(name=name, base=base, temp=False, reopen=False)
    db.reopen()
    try:
        db.migrate()
    finally:
        db.close()
    return backup
```

- [ ] **Step 4: Run → PASS.** Confirm the fixture vault's AID + credential survive migration.
- [ ] **Step 5:** Verify the Regery/Reger doesn't independently need migration (open the Regery post-migrate); if it does, add its migrate call. Note the finding.
- [ ] **Step 6: Commit.**

## Task 8: Hook migrate-on-open into `open_hby` + UI surface  *(MAIN SESSION)*

**Files:** Modify `core/habbing.py:open_hby` (before `:128`), + the vault-open UI (`core/apping.py`/the open flow)
**Interfaces:** Consumes `migrating.ensure_migrated`. Produces: opening a v1 vault backs up + migrates then opens cleanly; the UI shows a one-time "upgrading your vault" step + the backup path.

- [ ] **Step 1:** In `open_hby`, before constructing the `Habery`, call `ensure_migrated(name, base)`; if it returned a backup path, log + (via a callback/signal) surface the one-time UI notice with the backup path. Then construct the `Habery` (now `current`).
- [ ] **Step 2:** Wrap in try/except: on migration failure, restore the backup and raise a clear `VaultMigrationError` the UI shows (no silent brick).
- [ ] **Step 3: Integration test** — open the v1-vault fixture through `open_hby`, assert the vault opens, AID/credentials present, backup exists.
- [ ] **Step 4: UI harness** — drive the real open flow on a migrated vault; assert the upgrade notice renders (`objectName` selector) and the vault opens.
- [ ] **Step 5: Commit.**

## Task 9: Full validation on v2

**Files:** none (validation) + any residual test fixups
**Interfaces:** Consumes Tasks 1-8. Produces: green suite + harness on the v2 venv; documented hold.

- [ ] **Step 1:** Full hermetic suite on the v2 venv: `.venv/bin/python -m pytest tests -q --import-mode=importlib` → green (bar documented pre-existing skips). Fix residual v1-assertion mismatches (assert v2/v1 shapes correctly; don't unpin).
- [ ] **Step 2:** Audit pins: `grep -rn "Vrsn_1_0\|Kinds.json" src/locksmith/` — every framework pin carries a TRANSITIONAL comment; add a header note pointing to this plan.
- [ ] **Step 3:** UI harness smoke: open/migrate a vault, incept, issue a credential, a peer/IPEX round-trip — green on v2.
- [ ] **Step 4:** Confirm the interop gate (Task 3) + migration fixture (Task 7/8) still pass.
- [ ] **Step 5: Commit** the final green state + ledger note.

---

## Self-Review

**1. Spec coverage.** 3a outbound pins = Tasks 2 (inception), 4 (Kevery/Tevery), 5 (exns), 6 (credential). 3b vault migration = Tasks 7 (helper) + 8 (hook + UI). 3c interop gate = Task 3 (sequenced after the inception pin it depends on, still before the bulk — preserves validate-early). Two-axis framing honored (events pinned v1; DB migrated to v2). Parsing/receipts kept (confirmed in Task 9). venv→v2 baseline = Task 1. Covered.

**2. Placeholder scan.** `core/migrating.py` is complete code; pins are concrete `file:line` + example edits; the real-wallet tasks (3, 8) are structured harness steps (inherently main-session, not transcribable unit code) with concrete commands + assertions. The v1-vault fixture (Task 7) is a real captured artifact, not a stub.

**3. Type/name consistency.** `ensure_migrated(name, base, *, backup_root, stamp) -> Path|None` used consistently (Task 7 defines, Task 8 consumes); `Vrsn_1_0`/`pvrsn`/`Kinds.json` consistent with the fork seams; `Baser.reopen()/.current/.migrate()` per the survey.

**Notes for the reviewer:** (a) real-wallet/UI tasks (3, 8, 9 harness) run in the MAIN session — a subagent's "it worked" is unverifiable here. (b) The v1-vault fixture must be a genuinely pre-v2 vault (capture one before the venv flip, or from a tagged old build). (c) Every pin lifts as a unit with serviceaid when upstream ships v2 registry+IPEX.
