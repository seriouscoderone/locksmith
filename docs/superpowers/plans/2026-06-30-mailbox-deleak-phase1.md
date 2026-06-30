# Mailbox De-leak (Phase 1 of 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every mailbox poll-target selection use keripy's canonical
`agenting.mailbox(hab, cid)` (mailbox-end-role first, witness-fallback) instead of
enumerating `hab.kever.wits`, so a vault hosting an AID polls the mailbox that AID
designated in its KEL — fixing federation retrieval where witnesses and mailboxes are
distinct AIDs.

**Architecture:** Two one-site code changes + one live gate. (1) concierge
`BindingController._ensure_mailbox_polled` resolves one mailbox via `agenting.mailbox`
and adds one poller for it. (2) Locksmith `Vault` auto-seeds its `db.mbx` registry from
`agenting.mailbox` for each local AID on vault-open, then its existing
`load_active_mailboxes` pass mounts the pollers. (3) A hard live-federation gate proves
the carrier's exn is now retrieved off `mailbox.keri.host` and a `carrier_license` issues.

**Tech Stack:** Python 3.14; keripy (`agenting.mailbox`, `hab.makeEndRole`, `db.mbx`
Komer); pytest (`--import-mode=importlib` for Locksmith); the witnessed federation e2e
harness in `locksmith-micro-app-designer`.

## Global Constraints

- **BE KERI NATIVE.** "Mailbox" is a KERI end-role primitive; witness-as-mailbox is the
  *fallback*, never the concept. Use `agenting.mailbox(hab, cid)` — never enumerate
  `kever.wits` as if witnesses *are* mailboxes.
- **One resolver, no new abstraction.** Use the existing keripy `agenting.mailbox`; do not
  wrap it in a new helper.
- **Phase 1 of 3.** Scope is ONLY the de-leak + its live gate. Do NOT build the
  `keri-serverless-mailbox` package (Phase 2) or any WebSocket infra (Phase 3).
- **Branches.** concierge changes on a new branch `feat/mailbox-deleak-phase1`
  (`~/code/concierge-api`); Locksmith changes on the existing `feat/unified-mailbox-architecture`
  (`~/code/locksmith`). Commit per repo; **do not push** unless the user asks.
- **keripy is NOT modified in Phase 1** (the `wss` loc scheme is Phase 2/3).
- **Locksmith pytest** always passes `--import-mode=importlib` (the `packaging/` shadow).
- **YAGNI:** `db.mbx` stays keyed by `eid` (its existing schema). Multiple AIDs sharing one
  mailbox EID → first-seeded wins (single-AID federation gate is unaffected). Do not
  re-key `db.mbx` in Phase 1 — see §Known limitations.

---

## File Structure

| File | Repo | Responsibility | Change |
|---|---|---|---|
| `src/concierge_api_local/binding.py` | concierge-api | Service-AID bind lifecycle | `_ensure_mailbox_polled` → one poller for `agenting.mailbox(hab, hab.pre)` |
| `tests/test_binding_controller.py` | concierge-api | binding unit tests | replace the witness-enumeration test with de-leak tests |
| `src/locksmith/core/vaulting.py` | locksmith | Vault lifecycle + mailbox registry | add `Vault.seed_kel_mailboxes`; call it in `NotificationToastDoer.enter` before `load_active_mailboxes` |
| `tests/test_mailbox_kel_seed.py` | locksmith | new | wallet auto-seed unit test |
| `tests/integration/microapp_in_vault_witnessed.sh` | locksmith-micro-app-designer | live gate (unchanged file, run with `WITNESS_PROFILE=federation`) | run only — no edit |

---

## Task 1: concierge — de-leak `_ensure_mailbox_polled`

**Files:**
- Modify: `~/code/concierge-api/src/concierge_api_local/binding.py:126-141`
- Test: `~/code/concierge-api/tests/test_binding_controller.py`

**Interfaces:**
- Consumes: keripy `agenting.mailbox(hab, cid) -> str|None` (role-first, witness-fallback,
  `keri/app/agenting.py:967`); `vault.mbx.add_poller(hab, eid, extra_topics=None)`;
  `runtime.command_topics: list[str]`.
- Produces: no new public surface; `_ensure_mailbox_polled(hab)` now mounts exactly one
  poller for the resolved mailbox EID (or none).

- [ ] **Step 1: Replace the obsolete witness-enumeration test with de-leak tests.**

In `tests/test_binding_controller.py`, **delete** `test_ensure_mailbox_polled_passes_command_topics`
(lines 29-40 — its `SimpleNamespace(kever=...)` fake hab has no `db.ends`/`kevers`, so it
cannot exercise `agenting.mailbox`) and add:

```python
def test_ensure_mailbox_polled_polls_resolved_mailbox_role_not_witnesses(vault, tmp_path):
    """De-leak: poll the AID's DESIGNATED mailbox (its mailbox end-role) as exactly ONE
    poller — never one-per-witness. On a federation that separates witnesses and
    mailboxes, the command exn is deposited at the mailbox, not at a witness."""
    from types import SimpleNamespace
    from keri.kering import Roles
    calls = []
    vault.mbx = SimpleNamespace(
        add_poller=lambda hab, eid, extra_topics=None: calls.append((eid, extra_topics)))
    mbx_hab = vault.hby.makeHab(name="mailbox-svc")              # the dedicated mailbox AID
    doi = vault.hby.makeHab(name="state-doi")
    doi.makeEndRole(mbx_hab.pre, role=Roles.mailbox)             # designate it in the KEL
    ctl = BindingController(vault, _svc(), role_name="state-doi",
                            store_path=str(tmp_path / "b.json"))
    ctl.runtime = SimpleNamespace(command_topics=["insurance"])
    ctl._ensure_mailbox_polled(doi)
    assert calls == [(mbx_hab.pre, ["insurance"])]              # one poller, the mailbox role


def test_ensure_mailbox_polled_no_poller_when_no_mailbox_resolves(vault, tmp_path, monkeypatch):
    """No mailbox role and no witnesses -> agenting.mailbox returns None -> no poller."""
    from types import SimpleNamespace
    from keri.app import agenting
    calls = []
    vault.mbx = SimpleNamespace(
        add_poller=lambda hab, eid, extra_topics=None: calls.append((eid, extra_topics)))
    monkeypatch.setattr(agenting, "mailbox", lambda hab, cid: None)
    doi = vault.hby.makeHab(name="state-doi-none")
    ctl = BindingController(vault, _svc(), role_name="state-doi-none",
                            store_path=str(tmp_path / "b.json"))
    ctl.runtime = SimpleNamespace(command_topics=[])
    ctl._ensure_mailbox_polled(doi)
    assert calls == []
```

- [ ] **Step 2: Run the new tests to verify they fail.**

Run (from `~/code/concierge-api`):
```bash
.venv/bin/python -m pytest tests/test_binding_controller.py -q -k "resolved_mailbox_role or no_poller_when_no_mailbox" 2>&1 | tail -20
```
(If concierge has no local `.venv`, use the repo's configured interpreter per
`tools/publisher`/`pyproject` conventions; the publisher note in the root `CLAUDE.md`
applies to the publisher package, not concierge — run concierge tests from
`~/code/concierge-api`.)
Expected: FAIL — `test_..._resolved_mailbox_role_not_witnesses` fails because today's code
enumerates `hab.kever.wits` (it adds a poller for the witness, or none, not for the
mailbox-role EID).

- [ ] **Step 3: Implement the de-leak.**

In `src/concierge_api_local/binding.py`, replace `_ensure_mailbox_polled` (lines 126-141)
with:

```python
    def _ensure_mailbox_polled(self, hab) -> None:
        mbx = getattr(self.vault, "mbx", None)
        if mbx is None or not hasattr(mbx, "add_poller"):
            return
        # Also poll the Service-AID's command topics (route first-segment, e.g.
        # "insurance" for /insurance/cmd/*) so command exns forwarded under that
        # topic reach the runtime — the host's poller otherwise polls only its
        # standard topics (/receipt, /credential, ...).
        extra = list(getattr(self.runtime, "command_topics", []) or [])
        # Resolve the AID's mailbox the KERI-native way: its designated mailbox
        # end-role if any, else a witness (agenting.mailbox, role-first/witness-
        # fallback). Do NOT enumerate kever.wits as if witnesses ARE mailboxes — on a
        # federation that separates witnesses and mailboxes, the command exn is
        # deposited at the designated mailbox (e.g. mailbox.keri.host), not a witness.
        from keri.app import agenting
        eid = agenting.mailbox(hab, hab.pre)
        if eid is None:
            return
        try:
            mbx.add_poller(hab, eid, extra_topics=extra)
        except TypeError:
            mbx.add_poller(hab, eid)  # host add_poller predates extra_topics
        except Exception:
            pass
```

- [ ] **Step 4: Run the binding tests to verify they pass (no regressions).**

Run:
```bash
.venv/bin/python -m pytest tests/test_binding_controller.py -q 2>&1 | tail -20
```
Expected: PASS — the two new tests pass and the other binding tests
(`test_start_injects_host_exchanger`, `test_start_mounts_pump_then_stop_*`, etc.) stay
green.

- [ ] **Step 5: Run the full concierge suite + hermetic gate to confirm no regression.**

Run:
```bash
.venv/bin/python -m pytest tests/ -q 2>&1 | tail -15
bash tests/integration/grant_license_e2e.sh 2>&1 | tail -5
```
Expected: full suite green; `grant_license_e2e.sh` prints its PASS line (the hermetic gate
stubs transport, so the de-leak does not affect it).

- [ ] **Step 6: Commit (concierge, on its own branch).**

```bash
cd ~/code/concierge-api && git checkout -b feat/mailbox-deleak-phase1
git add src/concierge_api_local/binding.py tests/test_binding_controller.py
git commit -m "fix(binding): poll the AID's resolved mailbox (agenting.mailbox), not its witnesses

De-leak: _ensure_mailbox_polled enumerated hab.kever.wits, so on a federation that
separates witnesses and mailboxes the vault polled witnesses (which don't serve /mbx)
while the command exn sat in the designated mailbox -> 0 retrieval. Resolve one mailbox
via agenting.mailbox (role-first, witness-fallback) and add a single poller for it.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Locksmith — auto-seed `db.mbx` from the KEL on vault-open

**Files:**
- Modify: `~/code/locksmith/src/locksmith/core/vaulting.py` (add `Vault.seed_kel_mailboxes`
  after `activate_mailbox`, ~line 244; call it in `NotificationToastDoer.enter`, line 319)
- Test: `~/code/locksmith/tests/test_mailbox_kel_seed.py` (new)

**Interfaces:**
- Consumes: `agenting.mailbox(hab, cid) -> str|None`; `self.hby.habs` (dict of local habs);
  `self.db.mbx.get(keys=(eid,))` / `.pin(keys=(eid,), val=MailboxListener)`;
  `MailboxListener(cid, eid, name)` (`locksmith/db/basing.py:51`, already imported at
  `vaulting.py:37`).
- Produces: `Vault.seed_kel_mailboxes(self) -> None` — idempotent; pins a `db.mbx` entry for
  each local AID's KEL-resolved mailbox EID that is not already registered. The existing
  `load_active_mailboxes` then mounts the pollers.

- [ ] **Step 1: Write the failing test.**

Create `~/code/locksmith/tests/test_mailbox_kel_seed.py`:

```python
"""Vault.seed_kel_mailboxes — auto-seed db.mbx from each local AID's KEL-designated
mailbox (agenting.mailbox, role-first/witness-fallback), so the wallet polls the mailbox
the AID designated in its OWN KEL without a manual UI designation."""
from types import SimpleNamespace

from hio.base import doing
from keri.app import habbing
from keri.core import signing
from keri.kering import Roles
from keri.recording import EndpointRecord
from keri.vdr import credentialing

from locksmith.core import vaulting
from locksmith.db.basing import LocksmithBaser


class _NoTurret(doing.DoDoer):
    def __init__(self, *a, **k):
        super().__init__(doers=[])


def test_seed_kel_mailboxes_pins_designated_mailbox(monkeypatch, tmp_path):
    monkeypatch.setattr(vaulting, "LocksmithBaser",
                        lambda name, reopen=True: LocksmithBaser(
                            name=f"{name}-locksmith", headDirPath=str(tmp_path), reopen=reopen))
    monkeypatch.setattr(vaulting, "TurretDoer", _NoTurret)

    hby = habbing.Habery(name="vault-seed", temp=True,
                         salt=signing.Salter(raw=b'0123456789abcdef').qb64)
    rgy = credentialing.Regery(hby=hby, name=hby.name, temp=True)
    vault = None
    try:
        vault = vaulting.Vault(app=SimpleNamespace(), hby=hby, rgy=rgy)
        mbx_hab = hby.makeHab(name="mailbox-svc")               # the dedicated mailbox AID
        doi = hby.makeHab(name="state-doi")
        doi.db.ends.pin(keys=(doi.pre, Roles.mailbox, mbx_hab.pre),  # designate the mailbox
                        val=EndpointRecord(allowed=True))            # end-role (makeEndRole
        #                                                              alone doesn't persist to db.ends)

        vault.seed_kel_mailboxes()

        seeded = vault.db.mbx.get(keys=(mbx_hab.pre,))
        assert seeded is not None, "db.mbx was not seeded from the AID's KEL mailbox role"
        assert seeded.cid == doi.pre
        assert seeded.eid == mbx_hab.pre
    finally:
        if vault is not None:
            vault.db.close()
            vault.rep.mbx.close()
            vault.notifier.noter.close()
        rgy.close()
        hby.close()
```

- [ ] **Step 2: Run the test to verify it fails.**

Run (from `~/code/locksmith`):
```bash
.venv/bin/python -m pytest tests/test_mailbox_kel_seed.py -q --import-mode=importlib 2>&1 | tail -20
```
Expected: FAIL with `AttributeError: 'Vault' object has no attribute 'seed_kel_mailboxes'`.

- [ ] **Step 3: Implement `seed_kel_mailboxes` and wire it into vault-open.**

In `src/locksmith/core/vaulting.py`, add this method immediately after `activate_mailbox`
(it ends at line 244):

```python
    def seed_kel_mailboxes(self):
        """Auto-seed db.mbx from each local AID's KEL-designated mailbox.

        KERI-native target resolution (agenting.mailbox: the AID's mailbox end-role if
        designated, else a witness). Pins a db.mbx entry for each AID whose mailbox
        resolves and isn't already registered, so load_active_mailboxes then mounts a
        poller for the mailbox the AID designated in its OWN KEL — instead of relying on
        a manual UI designation that was never seeded. Explicit designations already in
        db.mbx are left untouched (overrides). Idempotent.
        """
        from keri.app import agenting
        for hab in self.hby.habs.values():
            eid = agenting.mailbox(hab, hab.pre)
            if eid is None:
                continue
            if self.db.mbx.get(keys=(eid,)) is not None:
                continue  # explicit designation or a prior seed already owns this EID
            self.db.mbx.pin(keys=(eid,),
                            val=MailboxListener(cid=hab.pre, eid=eid, name=eid))
```

Then in `NotificationToastDoer.enter` (line 314-319), call it before `load_active_mailboxes`:

```python
    def enter(self, **kwa):
        """Called when doer starts."""
        logger.info("NotificationToastDoer started")
        # Initialize with the most recent notification to avoid showing old ones
        self._update_last_notification()
        self.vault.seed_kel_mailboxes()        # auto-seed KEL-designated mailboxes first
        self.vault.load_active_mailboxes()
```

- [ ] **Step 4: Run the test to verify it passes.**

Run:
```bash
.venv/bin/python -m pytest tests/test_mailbox_kel_seed.py -q --import-mode=importlib 2>&1 | tail -20
```
Expected: PASS.

- [ ] **Step 5: Run the existing mailbox + vault tests to confirm no regression.**

Run:
```bash
.venv/bin/python -m pytest tests/test_mailbox_poller_topics.py tests/test_keri_v2_compat.py tests/test_mailbox_kel_seed.py -q --import-mode=importlib 2>&1 | tail -20
```
Expected: PASS (no regressions in the existing mailbox/poller and headless-vault tests).

- [ ] **Step 6: Commit (Locksmith, on `feat/unified-mailbox-architecture`).**

```bash
cd ~/code/locksmith   # already on feat/unified-mailbox-architecture
git add src/locksmith/core/vaulting.py tests/test_mailbox_kel_seed.py
git commit -m "feat(vault): auto-seed db.mbx from each AID's KEL-designated mailbox on open

On vault-open, resolve each local AID's mailbox via agenting.mailbox (role-first,
witness-fallback) and seed db.mbx, so the wallet polls the mailbox the AID designated in
its own KEL without a manual UI designation. load_active_mailboxes then mounts the
pollers. Explicit UI designations remain as overrides; idempotent.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Live federation verification gate (the Phase-1 acceptance)

**Files:**
- Run only: `~/code/locksmith-micro-app-designer/tests/integration/microapp_in_vault_witnessed.sh`
  (`WITNESS_PROFILE=federation`) and `microapp_in_vault_e2e.sh` (hermetic).
- Record: `~/code/locksmith-micro-app-designer/.superpowers/sdd/progress.md` (append the result).

**Interfaces:**
- Consumes the Task 1 (concierge) + Task 2 (locksmith) changes. The witnessed host
  (`_witnessed_vault_host.py`) drives `BindingController.start()` → the de-leaked
  `_ensure_mailbox_polled`, so the vault now polls `mailbox.keri.host` (the DOI's mailbox
  end-role), not the 5 witnesses. The editable `locksmith` install resolves to
  `~/code/locksmith` (the branch working tree); concierge resolves from `$CONCIERGE/src`
  (its branch). Confirm both branches are checked out before running.

- [ ] **Step 1: Confirm both code changes are live to the harness.**

Run:
```bash
git -C ~/code/concierge-api rev-parse --abbrev-ref HEAD   # expect feat/mailbox-deleak-phase1
git -C ~/code/locksmith     rev-parse --abbrev-ref HEAD   # expect feat/unified-mailbox-architecture
```
Expected: the two feature branches. (If concierge isn't on its branch, `git checkout
feat/mailbox-deleak-phase1` first.)

- [ ] **Step 2: Run the live federation gate.**

Run:
```bash
cd ~/code/locksmith-micro-app-designer
WITNESS_PROFILE=federation bash tests/integration/microapp_in_vault_witnessed.sh 2>&1 | sed -E 's/[BDEC][A-Za-z0-9_-]{43}/<AID44>/g' | tail -25
```
Expected (PASS path): the host log shows `pollers=1` (one poller, for the mailbox — not 5
witnesses), the vault pulls the carrier's exn, and the script prints
`PASS: witnessed roundtrip — carrier mailed -> vault polled -> carrier_license issued`
(exit 0).

**Decision gate (record whichever occurs):**
- **PASS** → Phase 1's acceptance is met: federation retrieval works on the current SSE
  infra. Proceed to Step 3.
- **PARTIAL despite `pollers=1` on the mailbox** (vault still pulls 0 off
  `mailbox.keri.host`) → the de-leak is correct and lands, but this proves the serverless
  **held-open SSE does not deliver the drain to a standard Poller** — i.e. WS notify-and-
  fetch (Phase 3) is *required* for federation retrieval, not merely a cost optimization.
  This is a valid, important outcome: **the Phase-1 CODE still merges** (it is correct and
  fixes demo/standard mailboxes), and the "live federation retrieval" acceptance is then
  formally satisfied by Phase 3. Record this explicitly and surface it to the user — do
  NOT loop trying to force SSE retrieval off the serverless mailbox.

- [ ] **Step 3: Demo + hermetic regression check.**

Run:
```bash
cd ~/code/locksmith-micro-app-designer
bash tests/integration/microapp_in_vault_e2e.sh 2>&1 | tail -3      # hermetic, must PASS
bash tests/integration/microapp_in_vault_witnessed.sh 2>&1 | sed -E 's/[BDEC][A-Za-z0-9_-]{43}/<AID44>/g' | tail -6   # demo profile
```
Expected: the hermetic in-vault gate prints its PASS line. The demo profile behaves no
worse than its documented pre-existing state (the demo-witness serve-poll gap is an env
issue, not a regression of this change); with the de-leak the demo DOI's mailbox role IS
its witness, so `pollers=1` for that witness.

- [ ] **Step 4: Record the result in the SDD ledger and commit it.**

Append a dated section to `~/code/locksmith-micro-app-designer/.superpowers/sdd/progress.md`
recording: the federation gate outcome (PASS or PARTIAL-with-diagnosis from Step 2),
`pollers=1`, the hermetic-gate PASS, and the concierge+locksmith commit short-SHAs. Then:
```bash
cd ~/code/locksmith-micro-app-designer
git add .superpowers/sdd/progress.md
git commit -m "chore(ledger): record Phase 1 mailbox de-leak federation verification result

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```
(The ledger is git-ignored scratch in some setups; if `git add` reports it ignored, skip
the commit and just leave the updated ledger file — its content is the durable record.)

---

## Known limitations (Phase 1, intentional — do not fix here)

- **`db.mbx` keyed by `eid`.** If multiple local AIDs designate the *same* mailbox EID,
  only the first-seeded `(cid, eid)` is registered. The single-AID federation gate is
  unaffected. Re-keying `db.mbx` to `(cid, eid)` is a possible Phase-2 follow-up (the
  `keri-serverless-mailbox` client owns per-(cid,eid) subscriptions), not Phase 1.
- **Multiple designated mailbox roles per AID:** `agenting.mailbox` returns the first
  allowed; polling several designated mailboxes is deferred (spec §4.1, §9.5).

## Self-Review

- **Spec coverage:** §4.1 concierge fix → Task 1; §4.1 wallet auto-seed → Task 2; §6 Phase-1
  live gate + §11 Phase-1 testing → Task 3 (with both PASS/PARTIAL outcomes mapped). No
  Phase-2/3 scope leaked in.
- **Placeholder scan:** none — every code/step shows concrete code and exact commands.
- **Type consistency:** `agenting.mailbox(hab, cid) -> str|None` used identically in Tasks 1
  and 2; `MailboxListener(cid, eid, name)` matches `basing.py:51`; `db.mbx.get/.pin(keys=
  (eid,))` matches existing `vaulting.py` usage; `add_poller(hab, eid, extra_topics=)`
  matches `indirecting.py:154`.
