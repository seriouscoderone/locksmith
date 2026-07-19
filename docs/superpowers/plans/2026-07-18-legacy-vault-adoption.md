# Legacy Vault Adoption on Launch — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make vaults created before the 2026-04-01 `rt/` repoint — dormant since, and therefore missing from the vault drawer — reappear automatically by backfilling their `rt/` entry on app launch.

**Architecture:** Add three Qt-free, module-level functions to `src/locksmith/core/apping.py` — a head-dir seam (`_vault_head_dirs`), a pure detector (`find_legacy_vaults`, rule `db ∩ ks ∩ mbx − rt`), and an idempotent adopter (`adopt_legacy_vaults`, `mkdir` the missing `rt/<base>/<name>`). Refactor `environments()` to share the seam, and call the adopter once from `LocksmithApplication.__init__` (before any `environments()` consumer runs). Store directory names and head roots are derived from the owning KERI classes, never hardcoded.

**Tech Stack:** Python 3, keripy (`keri.db.dbing.LMDBer`, `keri.app.keeping.Keeper`, `keri.app.storing.Mailboxer`), locksmith `LocksmithBaser`, pytest, `pathlib`.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-07-18-legacy-vault-adoption-design.md`.
- **Repo/branch:** `~/code/locksmith`, branch `development`.
- **Detection rule (verbatim):** name `N` under KERI root `H` with sub-base `B` is a legacy vault when `H/db/B/N`, `H/ks/B/N`, `H/mbx/B/N` all exist as directories and `H/rt/B/N` does not. (Here `H` already includes the `keri`/`.keri` segment; store names `db`/`ks`/`mbx`/`rt` are the last path segment of each owning class's `TailDirPath`.)
- **Head roots (verbatim keripy pairing):** `LMDBer.HeadDirPath`/`keri` (`/usr/local/var/keri`) preferred, `LMDBer.AltHeadDirPath`/`.keri` (`~/.keri`) fallback. Evaluate the rule per root; never mix stores across roots. Create `rt/` under the **same** root the vault's data lives in.
- **`environments()` stays a pure read of `rt/`** — only its head-dir sourcing changes.
- **Never hardcode tail/store path strings** — derive from `LMDBer`/`Keeper`/`Mailboxer`/`LocksmithBaser`.
- **The adopter must never raise into launch** — its call site swallows and logs.
- **Tests: offscreen-safe, pure-filesystem, focused file only.** No `tests/peer/`, no subprocess, no Qt widget construction. Run exactly:
  `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_apping_environments.py -q --import-mode=importlib`
- **Logging:** use the module's existing `logger = help.ogler.getLogger(__name__)`.

---

### Task 1: Head-dir seam, store-name constants, and `environments()` refactor

Introduce the shared seam and refactor `environments()` onto it with no behavior change (still a pure read of the first existing `rt/` root).

**Files:**
- Modify: `src/locksmith/core/apping.py` (imports ~lines 7-22; `environments()` at lines 638-661)
- Test: `tests/test_apping_environments.py` (create)

**Interfaces:**
- Consumes: `LocksmithBaser` (already imported); keripy `LMDBer`, `Keeper`, `Mailboxer`.
- Produces:
  - `_vault_head_dirs() -> list[Path]` — existing KERI roots (`…/keri`, `…/.keri`) in keripy preference order.
  - `_store_dir(root: Path, store_name: str, base: str = "") -> Path` — `root / store_name / base`.
  - Module constants `_DB_DIR`, `_KS_DIR`, `_MBX_DIR`, `_RT_DIR` (str: `"db"`, `"ks"`, `"mbx"`, `"rt"`).
  - `LocksmithApplication.environments()` — unchanged signature/return; now reads via the seam.

- [ ] **Step 1: Write the failing test**

Create `tests/test_apping_environments.py`:

```python
# -*- encoding: utf-8 -*-
"""Offscreen-safe, pure-filesystem tests for legacy-vault discovery/adoption.

Run: QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest \
        tests/test_apping_environments.py -q --import-mode=importlib
"""
from pathlib import Path
from types import SimpleNamespace

from locksmith.core import apping


def _mk(root: Path, store: str, name: str, base: str = "") -> Path:
    """Create root/store/base/name as a directory and return it."""
    d = root / store / base / name if base else root / store / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_environments_reads_rt_via_seam(tmp_path, monkeypatch):
    # A vault is "listed" iff it has an rt/ entry.
    _mk(tmp_path, "rt", "Alpha")
    _mk(tmp_path, "rt", "Beta")
    monkeypatch.setattr(apping, "_vault_head_dirs", lambda: [tmp_path])

    stub = SimpleNamespace(config=SimpleNamespace(base=""))
    names = apping.LocksmithApplication.environments(stub)

    assert names == ["Alpha", "Beta"]


def test_environments_empty_when_no_rt(tmp_path, monkeypatch):
    monkeypatch.setattr(apping, "_vault_head_dirs", lambda: [tmp_path])
    stub = SimpleNamespace(config=SimpleNamespace(base=""))
    assert apping.LocksmithApplication.environments(stub) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_apping_environments.py -q --import-mode=importlib`
Expected: FAIL — `AttributeError: module 'locksmith.core.apping' has no attribute '_vault_head_dirs'`.

- [ ] **Step 3: Add imports and constants**

In `src/locksmith/core/apping.py`, extend the keri imports (after line 9, `from keri import help`):

```python
from keri.app.keeping import Keeper
from keri.app.storing import Mailboxer
from keri.db.dbing import LMDBer
```

After the `logger = ...` line (line 24), add the store-name constants (derived from each owning class's `TailDirPath`, so nothing is hardcoded):

```python
# KERI on-disk store directory names, derived from the owning classes so they
# track upstream renames. Each vault gets a <store>/<base>/<name> dir per store.
_DB_DIR = Path(LMDBer.TailDirPath).name              # "db"   (KEL/history)
_KS_DIR = Path(Keeper.TailDirPath).name              # "ks"   (keystore)
_MBX_DIR = Path(Mailboxer.TailDirPath).name          # "mbx"  (mailbox)
_RT_DIR = Path(LocksmithBaser.TailDirPath).name      # "rt"   (Locksmith runtime db)
```

- [ ] **Step 4: Add the head-dir seam and `_store_dir` helper**

At **module level** — after the constants block from Step 3 and before `class LocksmithApplication` (line 210), so these are top-level functions, never nested in the class body — add:

```python
def _vault_head_dirs():
    """KERI roots (…/keri, …/.keri) that currently exist, in keripy order.

    Mirrors keri LMDBer head/tail pairing: the system head uses the ``keri``
    parent, the home head uses ``.keri``. Single source of truth for both
    ``environments()`` and ``adopt_legacy_vaults`` so the two never drift.
    Evaluated per call (not at import) so tests can point it at a tmp dir.
    """
    roots = (
        Path(LMDBer.HeadDirPath) / Path(LocksmithBaser.TailDirPath).parent,
        Path(LMDBer.AltHeadDirPath) / Path(LocksmithBaser.AltTailDirPath).parent,
    )
    return [root for root in roots if root.is_dir()]


def _store_dir(root, store_name, base=""):
    """Path to a KERI store dir under one root: ``root/store_name/base``."""
    base_path = Path(base) if base else Path()
    return root / store_name / base_path
```

- [ ] **Step 5: Refactor `environments()` onto the seam**

Replace the body of `environments` (lines 648-661) with:

```python
        base = getattr(self.config, "base", "") or ""
        for root in _vault_head_dirs():
            rt_home = _store_dir(root, _RT_DIR, base)
            if rt_home.is_dir():
                return sorted(
                    path.name for path in rt_home.iterdir() if path.is_dir()
                )
        return []
```

Also update the docstring's second paragraph to add: "Legacy vaults created before the `rt/` repoint are backfilled at launch by `adopt_legacy_vaults`, so this pure read still surfaces them."

- [ ] **Step 6: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_apping_environments.py -q --import-mode=importlib`
Expected: PASS (2 passed).

- [ ] **Step 7: Guard against regressions in the existing apping tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_apping_coordinator.py tests/test_apping_vault_delete.py -q --import-mode=importlib`
Expected: PASS (no behavior change to `environments()` for real head dirs).

- [ ] **Step 8: Commit**

```bash
cd ~/code/locksmith
git add src/locksmith/core/apping.py tests/test_apping_environments.py
git commit -m "refactor(vaults): share head-dir seam between environments() and adoption

Extract _vault_head_dirs/_store_dir and store-name constants derived from
the owning KERI classes; environments() now reads rt/ via the seam with no
behavior change. Prep for legacy-vault adoption.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: `find_legacy_vaults` — the detector

Pure query implementing the detection rule. No writes.

**Files:**
- Modify: `src/locksmith/core/apping.py` (add below `_store_dir`)
- Test: `tests/test_apping_environments.py` (extend)

**Interfaces:**
- Consumes: `_vault_head_dirs`, `_store_dir`, `_DB_DIR`, `_KS_DIR`, `_MBX_DIR`, `_RT_DIR` (Task 1).
- Produces:
  - `_legacy_vault_names_in_root(root: Path, base: str = "") -> set[str]` — names matching the rule under one root.
  - `find_legacy_vaults(base: str = "", heads: list[Path] | None = None) -> list[str]` — sorted union across roots; `heads` overrides the seam for testing.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_apping_environments.py`:

```python
def test_find_detects_legacy_vault(tmp_path):
    # db + ks + mbx, no rt -> legacy vault.
    for store in ("db", "ks", "mbx"):
        _mk(tmp_path, store, "Utah State")
    assert apping.find_legacy_vaults(heads=[tmp_path]) == ["Utah State"]


def test_find_ignores_kli_junk(tmp_path):
    # db + ks only (no mbx) -> kli/test debris, never a vault.
    for store in ("db", "ks"):
        _mk(tmp_path, store, "anchoring-1774913659009")
    assert apping.find_legacy_vaults(heads=[tmp_path]) == []


def test_find_ignores_mailbox_only_orphan(tmp_path):
    _mk(tmp_path, "mbx", "stray")
    assert apping.find_legacy_vaults(heads=[tmp_path]) == []


def test_find_skips_already_adopted(tmp_path):
    for store in ("db", "ks", "mbx", "rt"):
        _mk(tmp_path, store, "Carrier")
    assert apping.find_legacy_vaults(heads=[tmp_path]) == []


def test_find_honors_base(tmp_path):
    for store in ("db", "ks", "mbx"):
        _mk(tmp_path, store, "Scoped", base="myorg")
    # A bare-root vault must NOT match when base is set.
    for store in ("db", "ks", "mbx"):
        _mk(tmp_path, store, "Bare")
    assert apping.find_legacy_vaults(base="myorg", heads=[tmp_path]) == ["Scoped"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_apping_environments.py -q --import-mode=importlib -k find`
Expected: FAIL — `AttributeError: ... has no attribute 'find_legacy_vaults'`.

- [ ] **Step 3: Implement the detector**

In `src/locksmith/core/apping.py`, at module level directly below `_store_dir` (still above `class LocksmithApplication`), add:

```python
def _legacy_vault_names_in_root(root, base=""):
    """Names under one KERI root matching db ∩ ks ∩ mbx − rt (the vaults
    created + opened at least once by a wallet-like app, not yet adopted)."""
    db_home = _store_dir(root, _DB_DIR, base)
    if not db_home.is_dir():
        return set()
    names = set()
    for entry in db_home.iterdir():
        name = entry.name
        if not entry.is_dir():
            continue
        if not (_store_dir(root, _KS_DIR, base) / name).is_dir():
            continue
        if not (_store_dir(root, _MBX_DIR, base) / name).is_dir():
            continue
        if (_store_dir(root, _RT_DIR, base) / name).is_dir():
            continue  # already adopted
        names.add(name)
    return names


def find_legacy_vaults(base="", heads=None):
    """Sorted names of un-adopted legacy vaults across KERI roots.

    Pure query — no writes, no Qt, no ``self``. Host-agnostic so a future
    Universal CLI can reuse the same predicate. ``heads`` overrides the
    head-dir seam for testing.
    """
    roots = heads if heads is not None else _vault_head_dirs()
    found = set()
    for root in roots:
        found |= _legacy_vault_names_in_root(root, base)
    return sorted(found)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_apping_environments.py -q --import-mode=importlib -k find`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
cd ~/code/locksmith
git add src/locksmith/core/apping.py tests/test_apping_environments.py
git commit -m "feat(vaults): detect legacy pre-rt vaults (db ∩ ks ∩ mbx − rt)

Host-agnostic find_legacy_vaults + per-root helper. Excludes kli/test
debris (no mbx) and already-adopted vaults; honors the config sub-base.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: `adopt_legacy_vaults` + launch hook

Backfill the missing `rt/` entries once per launch, and wire the call into `LocksmithApplication.__init__` before any `environments()` consumer.

**Files:**
- Modify: `src/locksmith/core/apping.py` (add adopter below `find_legacy_vaults`; hook in `__init__` after line 227 `self.config = config`)
- Test: `tests/test_apping_environments.py` (extend)

**Interfaces:**
- Consumes: `find_legacy_vaults`, `_legacy_vault_names_in_root`, `_store_dir`, `_RT_DIR`, `_vault_head_dirs` (Tasks 1-2).
- Produces: `adopt_legacy_vaults(base: str = "", heads: list[Path] | None = None) -> list[str]` — creates missing `rt/<base>/<name>` per root; returns adopted names; never raises.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_apping_environments.py`:

```python
def test_adopt_creates_rt_and_environments_lists_it(tmp_path, monkeypatch):
    for store in ("db", "ks", "mbx"):
        _mk(tmp_path, store, "Utah State")

    adopted = apping.adopt_legacy_vaults(heads=[tmp_path])
    assert adopted == ["Utah State"]
    assert (tmp_path / "rt" / "Utah State").is_dir()

    # Now the pure read surfaces it.
    monkeypatch.setattr(apping, "_vault_head_dirs", lambda: [tmp_path])
    stub = SimpleNamespace(config=SimpleNamespace(base=""))
    assert apping.LocksmithApplication.environments(stub) == ["Utah State"]


def test_adopt_is_idempotent(tmp_path):
    for store in ("db", "ks", "mbx"):
        _mk(tmp_path, store, "Carrier")

    assert apping.adopt_legacy_vaults(heads=[tmp_path]) == ["Carrier"]
    # Second run: nothing left to adopt.
    assert apping.adopt_legacy_vaults(heads=[tmp_path]) == []


def test_adopt_adopts_under_the_vaults_own_root(tmp_path):
    # Vault data lives under root_b; root_a exists but is empty. rt/ must be
    # created under root_b, not root_a.
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    for store in ("db", "ks", "mbx"):
        _mk(root_b, store, "Homeowner")

    adopted = apping.adopt_legacy_vaults(heads=[root_a, root_b])

    assert adopted == ["Homeowner"]
    assert (root_b / "rt" / "Homeowner").is_dir()
    assert not (root_a / "rt" / "Homeowner").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_apping_environments.py -q --import-mode=importlib -k adopt`
Expected: FAIL — `AttributeError: ... has no attribute 'adopt_legacy_vaults'`.

- [ ] **Step 3: Implement the adopter**

In `src/locksmith/core/apping.py`, at module level directly below `find_legacy_vaults` (still above `class LocksmithApplication`), add:

```python
def adopt_legacy_vaults(base="", heads=None):
    """Backfill the missing rt/<base>/<name> dir for each legacy vault so it
    reappears in the drawer. Idempotent; adopts within each vault's own root;
    per-name failures are logged and skipped. Returns the adopted names.

    Host-agnostic (no Qt, no ``self``). The LMDB files inside rt/ are created
    later by the normal vault-open path — this only creates the directory,
    exactly like the manual `mkdir ~/.keri/rt/<name>` workaround.
    """
    roots = heads if heads is not None else _vault_head_dirs()
    adopted = []
    for root in roots:
        for name in sorted(_legacy_vault_names_in_root(root, base)):
            rt_dir = _store_dir(root, _RT_DIR, base) / name
            try:
                rt_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                logger.warning("adopt_legacy_vaults: failed to adopt %r: %s",
                               name, exc)
                continue
            adopted.append(name)
            logger.info("adopt_legacy_vaults: adopted legacy vault %r -> %s",
                        name, rt_dir)
    if adopted:
        logger.info("adopt_legacy_vaults: adopted %d legacy vault(s): %s",
                    len(adopted), adopted)
    return adopted
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_apping_environments.py -q --import-mode=importlib -k adopt`
Expected: PASS (3 passed).

- [ ] **Step 5: Wire the launch hook**

In `LocksmithApplication.__init__`, immediately after line 227 (`self.config = config`), add:

```python
        # Adopt vaults created before the rt/ repoint (dormant since) so they
        # reappear in the drawer. Runs before the onboarding gate, drawer, and
        # HOA bootstrap all read environments(). Never allowed to block launch.
        try:
            adopt_legacy_vaults(base=getattr(self.config, "base", "") or "")
        except Exception:  # noqa: BLE001 - launch must survive any fs anomaly
            logger.exception("adopt_legacy_vaults failed; continuing launch")
```

- [ ] **Step 6: Run the full focused file**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_apping_environments.py -q --import-mode=importlib`
Expected: PASS (10 passed).

- [ ] **Step 7: Guard the existing apping tests again**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_apping_coordinator.py tests/test_apping_vault_delete.py -q --import-mode=importlib`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
cd ~/code/locksmith
git add src/locksmith/core/apping.py tests/test_apping_environments.py
git commit -m "feat(vaults): adopt legacy pre-rt vaults on launch

adopt_legacy_vaults backfills rt/<base>/<name> for dormant vaults matching
db ∩ ks ∩ mbx − rt, within each vault's own KERI root; called once from
LocksmithApplication.__init__ (before drawer/onboarding/bootstrap read
environments()), wrapped so no fs anomaly blocks launch. Fixes the
stranded Utah State DOI / Carrier vaults.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Manual verification (post-implementation, on the dev host)

Real end-to-end check that the stranded vaults return, using the actual `~/.keri` (not tmp):

- [ ] Before: confirm the orphan is absent — `ls ~/.keri/rt/ | grep -i carrier` prints nothing while `ls ~/.keri/db/ ~/.keri/ks/ ~/.keri/mbx/ | grep -i carrier` shows it in all three.
- [ ] Run the adopter against the real tree from a REPL (read-only apart from creating `rt/` dirs):
  `QT_QPA_PLATFORM=offscreen .venv/bin/python -c "from locksmith.core.apping import adopt_legacy_vaults; print(adopt_legacy_vaults())"`
  Expected: prints a list including `Carrier`, `doi`, `fred-vault`, `joseph`, `rose`, `ryan-custody`, `usurance-custody`, `witv2test`, … (not `Utah State`, already backfilled manually).
- [ ] After: `ls ~/.keri/rt/` now contains those names; re-running the command prints `[]` (idempotent).
- [ ] Launch the app; confirm the adopted vaults appear in the drawer and open. (`screencapture` is blocked on this host — verify by interaction, not screenshot.)

## Self-Review

**Spec coverage:**
- Detection rule (`db ∩ ks ∩ mbx − rt`, per-root, class-derived paths) → Task 2 (`_legacy_vault_names_in_root`, `find_legacy_vaults`) + Task 1 constants.
- Adopt-on-launch approach → Task 3 (`adopt_legacy_vaults` + `__init__` hook).
- `_vault_head_dirs` / `find_legacy_vaults` / `adopt_legacy_vaults` components → Tasks 1/2/3.
- `environments()` minimal change (shared seam, pure read) → Task 1.
- Host-agnostic / Qt-free (CLI-mirror seam) → all three functions are module-level, no `self`/PySide → Tasks 1-3.
- Error handling (never block launch; per-name skip) → Task 3 Steps 3+5.
- Test cases 1-7 → Task 1 (7, +empty), Task 2 (2/3/5/6 + find-half of 1), Task 3 (adopt-half of 1, 4, + own-root coverage of the per-root rule).
- Framework implications section → out of scope by design; no task, correctly.

**Placeholder scan:** none — every code/test step shows complete content and exact commands with expected output.

**Type/name consistency:** `_vault_head_dirs`, `_store_dir`, `_DB_DIR`/`_KS_DIR`/`_MBX_DIR`/`_RT_DIR`, `_legacy_vault_names_in_root`, `find_legacy_vaults`, `adopt_legacy_vaults` are spelled identically across definitions, call sites, and tests. `environments()` signature/return unchanged. `heads` override param consistent across `find_legacy_vaults`/`adopt_legacy_vaults`.

**Note vs spec:** the spec sketched `_vault_head_dirs(base="")`; the plan drops the unused `base` param (head roots are base-independent — `base` is applied downstream in `_store_dir`). Deliberate refinement, behavior-equivalent.
```
