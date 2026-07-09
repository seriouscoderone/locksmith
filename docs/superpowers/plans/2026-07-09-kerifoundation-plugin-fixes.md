# KERI Foundation Plugin Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the KERI Foundation plugin a brand-independent icon and stop the onboarding page from crashing when the vault database is closed.

**Architecture:** Two independent tracks. Track A copies the Locksmith reference symbol into a KF-owned asset path (`assets/kerifoundation/`) that `scripts/brand_apply.py` provably never stages, bundles it into the Qt resource blob, and repoints the plugin through a single module constant. Track B hardens the shared `list_eligible_local_identifiers` helper to return `[]` on a closed database (defense-in-depth, TDD), then a main-session real-wallet spike diagnoses and fixes the production trigger.

**Tech Stack:** Python 3.14, PySide6 (`pyside6-rcc` 6.10.3 for the Qt resource bundle), keri 2.0.0-dev6, pytest.

## Global Constraints

- Branch: `fix/kerifoundation-plugin` (already created off `development`; the spec commit `941f244` is its first commit). Do **not** push; do **not** work on `development` directly.
- Run every pytest invocation with `--import-mode=importlib` (repo has a top-level `packaging/` dir that otherwise shadows the `packaging` library). Interpreter: `.venv/bin/python`.
- The KF icon asset MUST live **outside** `assets/custom/` — `brand_apply.py` only ever writes into `assets/custom/`, `src/locksmith/release/`, and `packaging/`, so a path outside `assets/custom/` is immune to brand staging. Putting it under `assets/custom/` reintroduces the leak.
- The KF mark is the committed Locksmith reference symbol `assets/custom/SymbolLogo.svg` (5997 bytes), copied byte-for-byte. Do not author a new mark.
- Commit-message trailers (every commit):
  ```
  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01Q2VVcBXPMPfy75MqXPo8kn
  ```
- `src/locksmith/resources_rc.py` is a generated, git-tracked blob — regenerate it with `pyside6-rcc` and commit the regenerated file; never hand-edit it.
- Real-wallet / UI work (Task 3) runs in the **main session**, never a subagent. Kill only PIDs you spawn (no broad `pkill locksmith.main`).

---

### Task 1: Brand-independent KF icon (Track A)

**Files:**
- Create: `assets/kerifoundation/SymbolLogo.svg` (byte copy of `assets/custom/SymbolLogo.svg`)
- Modify: `resources.qrc` (add one `<file>` line under `<qresource prefix="/">`)
- Regenerate: `src/locksmith/resources_rc.py` (via `pyside6-rcc`)
- Modify: `src/locksmith/plugins/kerifoundation/plugin.py` (add `KF_ICON_RESOURCE` constant; use at the two icon sites — current lines `318` and `665`)
- Test: `tests/unit/branding/test_kf_icon_brand_independent.py`

**Interfaces:**
- Produces: module constant `locksmith.plugins.kerifoundation.plugin.KF_ICON_RESOURCE: str == ":/assets/kerifoundation/SymbolLogo.svg"`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/branding/test_kf_icon_brand_independent.py`:

```python
"""The KERI Foundation plugin icon must not be a brand-staged asset.

Regression: the plugin used :/assets/custom/SymbolLogo.svg, which brand_apply.py
overwrites per brand, so the KF entry showed the active brand's logo (the
Usurance eye in a Usurance build) instead of KERI Foundation's own mark.
"""
import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_kf_icon_resource_is_not_brand_staged():
    from locksmith.plugins.kerifoundation import plugin

    # The plugin exposes a single source of truth for its icon path.
    assert plugin.KF_ICON_RESOURCE == ":/assets/kerifoundation/SymbolLogo.svg"
    # It must NOT live under assets/custom/ — that is the brand-staging dir.
    assert "assets/custom/" not in plugin.KF_ICON_RESOURCE


def test_kf_icon_asset_file_exists_outside_custom():
    asset = REPO_ROOT / "assets" / "kerifoundation" / "SymbolLogo.svg"
    assert asset.is_file(), "KF-owned icon asset missing"
    # Byte-identical to the committed Locksmith reference symbol.
    reference = REPO_ROOT / "assets" / "custom" / "SymbolLogo.svg"
    assert asset.read_bytes() == reference.read_bytes()


def test_brand_apply_never_stages_the_kf_asset(tmp_path):
    """Running brand_apply for a brand that ships a SymbolLogo leaves a
    kerifoundation-path asset untouched."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    sys.path.insert(0, str(REPO_ROOT / "packaging"))
    brand_apply = importlib.import_module("brand_apply")

    # Minimal fake repo tree with a brand that ships SymbolLogo.svg.
    (tmp_path / "assets" / "custom").mkdir(parents=True)
    (tmp_path / "assets" / "custom" / "SymbolLogo.svg").write_text("LOCKSMITH-SYMBOL")
    (tmp_path / "assets" / "kerifoundation").mkdir(parents=True)
    kf_asset = tmp_path / "assets" / "kerifoundation" / "SymbolLogo.svg"
    kf_asset.write_text("KF-OWNED-MARK")
    (tmp_path / "packaging" / "wix").mkdir(parents=True)
    (tmp_path / "packaging" / "dmg").mkdir(parents=True)
    (tmp_path / "packaging" / "wix" / "Locksmith.wxs.in").write_text(
        '<Package Name="@@NAME@@" UpgradeCode="@@UPGRADE_CODE@@" />')
    (tmp_path / "src" / "locksmith" / "release").mkdir(parents=True)
    brand = tmp_path / "brands" / "acme"
    brand.mkdir(parents=True)
    (brand / "brand.toml").write_text(
        (REPO_ROOT / "brands" / "example" / "brand.toml").read_text()
        .replace('id            = "example"', 'id            = "acme"')
        .replace("Example Vault", "Acme"))
    (brand / "SymbolLogo.svg").write_text("ACME-SYMBOL")

    report = brand_apply.apply("acme", tmp_path, check=False)

    # The active brand's symbol landed in assets/custom/, as designed...
    assert (tmp_path / "assets" / "custom" / "SymbolLogo.svg").read_text() == "ACME-SYMBOL"
    assert "SymbolLogo.svg" in report["staged_assets"]
    # ...but the KF-owned asset outside assets/custom/ is untouched.
    assert kf_asset.read_text() == "KF-OWNED-MARK"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/branding/test_kf_icon_brand_independent.py -q --import-mode=importlib`
Expected: FAIL — `AttributeError: module 'locksmith.plugins.kerifoundation.plugin' has no attribute 'KF_ICON_RESOURCE'` and the asset-file test fails (file absent).

- [ ] **Step 3: Create the KF-owned asset**

```bash
mkdir -p assets/kerifoundation
cp assets/custom/SymbolLogo.svg assets/kerifoundation/SymbolLogo.svg
```

- [ ] **Step 4: Add the asset to the Qt resource bundle**

In `resources.qrc`, add this line immediately after `<qresource prefix="/">` (line 2), before `<file>assets/cloud_lock.svg</file>`:

```xml
        <file>assets/kerifoundation/SymbolLogo.svg</file>
```

Then regenerate the compiled bundle:

```bash
.venv/bin/pyside6-rcc resources.qrc -o src/locksmith/resources_rc.py
```

- [ ] **Step 5: Add the constant and repoint the two icon sites**

In `src/locksmith/plugins/kerifoundation/plugin.py`, add a module constant directly after the `logger = help.ogler.getLogger(__name__)` line (line 42):

```python
# KERI Foundation is a distinct third-party plugin and must keep its own
# identity regardless of the active white-label brand. This asset lives
# OUTSIDE assets/custom/, so scripts/brand_apply.py never overwrites it.
KF_ICON_RESOURCE = ":/assets/kerifoundation/SymbolLogo.svg"
```

Change `get_menu_entry` (currently line 318):

```python
    def get_menu_entry(self) -> MenuButton:
        icon = QIcon(KF_ICON_RESOURCE)
        return MenuButton(icon=icon, label="KERI Foundation")
```

Change `_build_logo_widget` (currently line 665):

```python
        pixmap = QPixmap(KF_ICON_RESOURCE)
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/branding/test_kf_icon_brand_independent.py -q --import-mode=importlib`
Expected: PASS (3 passed).

- [ ] **Step 7: Confirm no unrelated breakage**

Run: `.venv/bin/python -m pytest tests/unit/branding tests/test_kerifoundation_witnesses.py -q --import-mode=importlib`
Expected: PASS (existing brand + KF tests still green).

- [ ] **Step 8: Commit**

```bash
git add assets/kerifoundation/SymbolLogo.svg resources.qrc src/locksmith/resources_rc.py \
        src/locksmith/plugins/kerifoundation/plugin.py \
        tests/unit/branding/test_kf_icon_brand_independent.py
git commit -m "fix(kerifoundation): brand-independent plugin icon

The KF plugin drew its icon from :/assets/custom/SymbolLogo.svg, which
brand_apply.py overwrites per brand, so the entry showed the active brand's
logo. Snapshot the Locksmith reference symbol into a KF-owned path outside
assets/custom/ (immune to brand staging) and reference it via KF_ICON_RESOURCE.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Q2VVcBXPMPfy75MqXPo8kn"
```

---

### Task 2: Harden `list_eligible_local_identifiers` against a closed db (Track B)

**Files:**
- Modify: `src/locksmith/core/habbing.py:301-339` (add a closed-db guard after `hby = app.vault.hby`)
- Test: `tests/test_list_eligible_local_identifiers.py`

**Interfaces:**
- Consumes: `locksmith.core.habbing.list_eligible_local_identifiers(app) -> list[dict]` (existing; keys `alias`, `prefix`).
- Produces: same signature; new behavior — returns `[]` (no raise) when the vault Habery's LMDB env is closed (`hby.db is None` or `hby.db.env is None`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_list_eligible_local_identifiers.py`:

```python
"""list_eligible_local_identifiers must tolerate a closed vault database.

Regression (KF onboarding crash): when the vault Habery's LMDB env is closed,
keri's LMDBer sets env=None, so getTopItemIter -> env.begin() raised
AttributeError: 'NoneType' object has no attribute 'begin' straight into the UI.
"""
from types import SimpleNamespace

from keri.app import habbing
from keri.core import signing
from keri.kering import Vrsn_1_0

from locksmith.core.habbing import list_eligible_local_identifiers


def _app_with(hby):
    return SimpleNamespace(vault=SimpleNamespace(hby=hby))


def test_returns_empty_when_vault_db_closed():
    hby = habbing.Habery(
        name="closedtest", bran="A" * 21,
        salt=signing.Salter(raw=b"0123456789abcdef").qb64,
        temp=True, version=Vrsn_1_0,
    )
    hby.makeHab(name="alice", isith="1", icount=1, transferable=True,
                version=Vrsn_1_0)
    hby.close()  # keri LMDBer.close() sets db.env = None

    assert list_eligible_local_identifiers(_app_with(hby)) == []


def test_lists_root_identifiers_when_open():
    hby = habbing.Habery(
        name="opentest", bran="B" * 21,
        salt=signing.Salter(raw=b"fedcba9876543210").qb64,
        temp=True, version=Vrsn_1_0,
    )
    try:
        hby.makeHab(name="alice", isith="1", icount=1, transferable=True,
                    version=Vrsn_1_0)
        aliases = {item["alias"]
                   for item in list_eligible_local_identifiers(_app_with(hby))}
        assert "alice" in aliases
    finally:
        hby.close()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_list_eligible_local_identifiers.py -q --import-mode=importlib`
Expected: `test_returns_empty_when_vault_db_closed` FAILS with `AttributeError: 'NoneType' object has no attribute 'begin'`; `test_lists_root_identifiers_when_open` PASSES.

- [ ] **Step 3: Add the closed-db guard**

In `src/locksmith/core/habbing.py`, in `list_eligible_local_identifiers`, insert the guard between `hby = app.vault.hby` (currently line 319) and the `for` loop (currently line 320):

```python
    hby = app.vault.hby
    if getattr(hby, "db", None) is None or getattr(hby.db, "env", None) is None:
        logger.info("Eligible local identifier load skipped: vault database is closed")
        return identifiers

    for (ns, alias), prefix in hby.db.names.getTopItemIter(keys=()):
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_list_eligible_local_identifiers.py -q --import-mode=importlib`
Expected: PASS (2 passed).

- [ ] **Step 5: Confirm callers still pass**

The helper has three UI callers; run the KF onboarding UI suite as the closest coverage:

Run: `.venv/bin/python -m pytest tests/test_kerifoundation_onboarding_ui.py -q --import-mode=importlib`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/locksmith/core/habbing.py tests/test_list_eligible_local_identifiers.py
git commit -m "fix(habbing): tolerate a closed vault db in list_eligible_local_identifiers

When the vault Habery's LMDB env is closed (env=None), getTopItemIter ->
env.begin() raised AttributeError into the UI (KF onboarding crash). Guard the
closed-db case the same as vault-unavailable: log and return []. Defense-in-depth;
the production trigger is diagnosed separately.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Q2VVcBXPMPfy75MqXPo8kn"
```

---

### Task 3: Diagnose and fix the production trigger (Track B — main session)

This task is a systematic-debugging spike, run in the **main session** (real wallet). Task 2's guard stops the crash; this task finds *why* the vault db is closed on the pending-onboarding path and applies the smallest correct source fix (if the guard alone leaves a real defect, e.g. the KF page silently shows an empty AID list when identifiers exist).

**Files (investigation surface — the fix lands in whichever the diagnosis implicates):**
- `src/locksmith/plugins/kerifoundation/plugin.py` (`get_setup_page` → `on_show`, currently line 290/308)
- `src/locksmith/plugins/kerifoundation/onboarding/page.py` (`on_show` → `_populate_account_choices`, currently line 544/563)
- `src/locksmith/core/apping.py` (`open_vault` / `close_vault`, currently line 414/442)
- `src/locksmith/core/vaulting.py` (Habery/db lifecycle)

- [ ] **Step 1: Reproduce (Phase 1 — root cause investigation)**

Launch the app in the main session and reproduce per the backlog:

```bash
.venv/bin/python -m locksmith.main
```

Open vault `carrier2` (passcode `noble`) — or any `carrier` vault whose KF account status is `pending_onboarding` — and click the "KERI Foundation" sidebar entry. Confirm the traceback (`AttributeError: 'NoneType' object has no attribute 'begin'` from `onboarding/page.py` → `_populate_account_choices`) is now caught by Task 2's guard (page renders, possibly with an empty AID list). Capture the KF plugin log lines emitted just before the render (the entry-decision / status-transition INFO lines).

- [ ] **Step 2: Identify which `app.vault.hby` the page sees**

Add temporary instrumentation (a `logger.info`) at the top of `list_eligible_local_identifiers` logging `id(app)`, `id(getattr(app, "vault", None))`, `getattr(app.vault, "hby", None)` name, and `hby.db.env is None`. Re-run Step 1. Determine which of these holds:
  - (a) `app.vault` is a **stale/different** vault than the active one (the KF page captured an old `self._app` or `self._app.vault`);
  - (b) the **active** vault's `hby` is closed at click time (an open/close transition, or a v2 migrate-on-open window left it closed);
  - (c) the db is open but a different object than expected.

Write the finding (one paragraph) into the spec's "Architecture → Why the crash" section, replacing the "trigger is unknown" note.

- [ ] **Step 3: Apply the smallest correct source fix (Phase 4)**

Based on Step 2:
  - If (a): fix the KF plugin so `on_show` / `_populate_account_choices` enumerates against the **currently active** `app.vault` (refresh the reference), not a captured stale one. The fix site is `onboarding/page.py` (`set_app` / `on_show`) or `plugin.py` (`get_setup_page`).
  - If (b): fix the open sequence so the KF onboarding destination is not shown until the Habery is open, or so `open_vault` does not leave `hby` closed on the pending-onboarding path (`apping.py` / `vaulting.py`).
  - If (c): correct the object the page reads.

Remove the Step 2 instrumentation. If the diagnosis shows Task 2's guard is the complete and correct fix (the db is legitimately transiently closed and an empty list is the right UX), record that conclusion and skip the source edit — do **not** invent a fix for a non-defect.

- [ ] **Step 4: Add a regression test for the source fix**

If Step 3 changed source, add a test near `tests/test_kerifoundation_onboarding_ui.py` that fails without the fix and passes with it (e.g. `on_show` enumerates the active vault's identifiers; or the KF onboarding destination is gated on an open db). Write the test first (watch it fail), then confirm it passes:

Run: `.venv/bin/python -m pytest tests/test_kerifoundation_onboarding_ui.py -q --import-mode=importlib`
Expected: PASS.

- [ ] **Step 5: Manual verification (both tracks)**

In the running app (main session):
  - **Track A:** with a Usurance build (`LOCKSMITH_BRAND=usurance .venv/bin/python scripts/brand_apply.py` then run), the "KERI Foundation" entry shows the KERI Foundation reference mark, not the Usurance eye. Restore the tree afterward (`git checkout -- assets/custom src/locksmith/resources_rc.py src/locksmith/release` or re-run brand_apply for `locksmith`) so the working tree is not left staged on Usurance.
  - **Track B:** clicking "KERI Foundation" on the `pending_onboarding` vault renders the onboarding page (no traceback), and the AID selector is correctly populated.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "fix(kerifoundation): render onboarding page against the open vault db

<one line naming the diagnosed trigger from Step 2>. Adds a regression test.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Q2VVcBXPMPfy75MqXPo8kn"
```

(If Step 3 concluded no source fix is needed, skip this commit — Task 2 already shipped the fix — and note that conclusion in the final report.)

---

## Final verification

```bash
.venv/bin/python -m pytest \
  tests/unit/branding \
  tests/test_list_eligible_local_identifiers.py \
  tests/test_kerifoundation_onboarding_ui.py \
  -q --import-mode=importlib
```
Expected: all green. Then the manual real-wallet checks in Task 3 Step 5.
