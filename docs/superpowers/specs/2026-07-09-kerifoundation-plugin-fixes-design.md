# KERI Foundation plugin: brand-independent identity + onboarding-crash fix

**Date:** 2026-07-09
**Source:** `backlog/2026-07-09-kerifoundation-plugin-brand-leak-and-onboarding-crash.md`
**Base:** KERI-v2 keripy base (`keri 2.0.0-dev6`), Locksmith `development`.

## Problem

Two independent defects on the "KERI Foundation" sidebar entry, both surfaced while
visually testing the **Usurance** source build.

1. **Brand leak.** The KF plugin renders its icon from the brand-staged asset
   `:/assets/custom/SymbolLogo.svg`, which `scripts/brand_apply.py` overwrites per
   brand (and recompiles into the Qt resource bundle). So the KF entry adopts the
   *active brand's* symbol — the Usurance eye in a Usurance build. It should always
   show KERI Foundation's own mark. Two references: `plugin.py:318`
   (`get_menu_entry`) and `plugin.py:665` (`_build_logo_widget`).

2. **Onboarding crash.** Clicking the entry on a `pending_onboarding` vault throws
   `AttributeError: 'NoneType' object has no attribute 'begin'` from
   `onboarding/page.py:573` → `list_eligible_local_identifiers(self._app)`. `.begin()`
   is `self.env.begin()` inside keri's `LMDBer`, so the vault's keri db
   (`app.vault.hby.db.env`) is `None` — i.e. the Habery is closed at the moment the
   page enumerates identifiers. The page never renders.

## Product decisions (settled)

- **KF plugin presence:** stays present in **every** brand (Usurance included) with
  its **own** identity. No presence gating by brand. (Reporter constraint: "a
  distinct third-party plugin [that] must keep its own identity regardless of the
  active brand.")
- **KF mark source:** the **Locksmith / keri.host reference symbol**, which today is
  the committed `assets/custom/SymbolLogo.svg` (5997 bytes; distinct from Usurance's
  25258-byte mark). Locksmith is the reference brand — its `brand.toml` ships no image
  files, so the baseline `assets/custom/*` *is* the Locksmith identity. No KF-specific
  mark has ever existed in git history or sibling repos; this reference symbol is the
  correct KERI-Foundation identity and is captured into a KF-owned path.

## Scope

One spec, **two independent tracks**. Either can ship alone:

- **Track A (Brand leak)** — unblocked today; pure asset + reference change.
- **Track B (Onboarding crash)** — investigate-then-fix; needs a live repro first.

## Architecture

### How branding works (grounding for Track A)

`brand_apply.py` reads `brands/<brand>/brand.toml` and, for the asset keys in
`_ASSET_KEYS` (`app_icon_*`, `splash`, `symbol_logo*`, `name_logo*`, `full_logo*`),
copies the brand's files **into `assets/custom/`** and recompiles
`src/locksmith/resources_rc.py`. It writes **only** into `assets/custom/`,
`src/locksmith/release/`, and `packaging/` — never anywhere else. Therefore any asset
placed under a **new** path outside `assets/custom/` (e.g. `assets/kerifoundation/`)
is provably immune to brand staging.

The KF plugin's other `:/assets/custom/*.png` glyphs (`identifiers.png`, etc.) are
**not** in `_ASSET_KEYS`, so brand_apply never stages them — they don't leak. Only the
`SymbolLogo.svg` references are affected. (Backlog identified exactly these two.)

### Why the crash (grounding for Track B)

`app.vault.hby.db.env is None` means the vault's Habery LMDB env is closed. The only
code that closes it is `AppCore.close_vault()` (`apping.py:470`, `self.hby.close()`),
which runs at the top of `open_vault()` (`apping.py:424`). So the crash implies the KF
onboarding page is enumerating identifiers against a vault whose db is closed — a
stale `self._app.vault`, a mid-transition open/close, or a v2 migrate-on-open window.
The exact trigger is unknown until reproduced, so Track B is investigate-then-fix, not
a blind guard.

## Track A — Brand-independent KF icon

**Approach:** snapshot the committed Locksmith reference symbol into a KF-owned path
`brand_apply` never touches, add it to the Qt resource bundle, and repoint the plugin.

1. **New asset.** Copy `assets/custom/SymbolLogo.svg` →
   `assets/kerifoundation/SymbolLogo.svg` (byte-identical to today's committed
   Locksmith symbol).
2. **Bundle it.** Add `<file>assets/kerifoundation/SymbolLogo.svg</file>` to
   `resources.qrc` under `<qresource prefix="/">`, and recompile
   `src/locksmith/resources_rc.py` with the venv's `pyside6-rcc`.
3. **Repoint references.** In `src/locksmith/plugins/kerifoundation/plugin.py`, change
   both `QIcon(":/assets/custom/SymbolLogo.svg")` (`:318`) and
   `QPixmap(":/assets/custom/SymbolLogo.svg")` (`:665`) to
   `:/assets/kerifoundation/SymbolLogo.svg`.

**Rejected alternative:** read the `brands/locksmith/` asset at runtime. The locksmith
reference brand ships no image file (its baseline is `assets/custom/`), so there is
nothing to read; a committed KF-owned copy is simpler and self-contained.

**Tests** (`tests/unit/branding/`, mirroring `test_brand_apply.py`):
- Assert the KF plugin's icon resource path is **not** under `assets/custom/` (i.e. the
  plugin references the KF-owned path). Guards against a regression that repoints it
  back at a staged asset.
- Assert `brand_apply.apply("usurance", repo_root, check=False)` leaves
  `assets/kerifoundation/SymbolLogo.svg` byte-identical (not in `staged_assets`) —
  proving no leak. Run against a temp copy of the tree so it doesn't dirty the working
  tree.

## Track B — Onboarding crash

**Approach:** investigate → fix at source → harden the shared helper (defense-in-depth).

1. **Reproduce headlessly.** On vault `carrier2` (passcode `noble`) or a `carrier`
   vault in `status='pending_onboarding'`, drive
   `KFOnboardingPage._populate_account_choices` /
   `list_eligible_local_identifiers(app)` and instrument exactly where the Habery env
   becomes `None`. Distinguish among: stale `self._app.vault`; a close/open transition;
   a v2 migrate-on-open window. This is main-session real-wallet work (not a subagent).
2. **Fix at source.** Apply the smallest correct fix for the trigger the repro reveals
   (e.g. the KF page must not enumerate against a closed/other vault; or the open
   sequence must not leave the Habery closed on the pending-onboarding path).
3. **Harden the shared helper.** `list_eligible_local_identifiers` (in
   `src/locksmith/core/habbing.py:301`, called from three UI sites:
   `ui/vault/credentials/issued/issue.py`, `ui/vault/credentials/schema/add.py`, and
   the KF onboarding page) must treat a **not-open db** the same as "vault
   unavailable": extend the existing guard so that when the Habery db env is closed
   (`getattr(hby, "db", None) is None or hby.db.env is None`) it logs and returns `[]`
   rather than letting `.begin()` raise into the UI.

**Tests:**
- Unit: `list_eligible_local_identifiers(app)` returns `[]` (no raise) when
  `app.vault.hby` is a Habery whose db has been closed. No existing coverage for this
  helper.
- Regression (near `tests/test_kerifoundation_onboarding_ui.py`): `on_show` /
  `_populate_account_choices` does not raise when the vault db is closed.
- Plus whatever targeted test the source fix (step 2) warrants once the trigger is
  known.

## Data flow / error handling

- Track A changes only which compiled-in resource the KF plugin references; no runtime
  data flow change. Failure mode (missing/empty pixmap) is already handled by the
  existing `if not pixmap.isNull()` guard at `plugin.py:666`.
- Track B's helper hardening converts a hard crash into a graceful empty list + a log
  line, consistent with the helper's existing "vault or habery unavailable" branch.

## Verification

```
.venv/bin/python -m pytest \
  tests/unit/branding \
  tests/test_kerifoundation_onboarding_ui.py \
  <new helper + regression tests> \
  -q --import-mode=importlib
```

Manual real-wallet check (main session):
- **Track A:** a Usurance run shows the KERI Foundation mark on the KF entry, not the
  Usurance eye; a Locksmith run is unchanged.
- **Track B:** clicking "KERI Foundation" on a `pending_onboarding` vault renders the
  onboarding page instead of throwing.

## Out of scope

- Presence-gating the KF plugin by brand (decided against).
- Sourcing an official/bespoke KERI Foundation logo distinct from the Locksmith
  reference symbol (the reference symbol is the agreed identity; a future bespoke mark
  is a drop-in replacement at the same KF-owned path).
- Broader audit of other plugins for brand leaks (none found; only KF referenced a
  staged asset).
