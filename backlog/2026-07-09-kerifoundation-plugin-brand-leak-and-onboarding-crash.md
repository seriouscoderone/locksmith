# KERI Foundation plugin: white-label leak + onboarding crash

**Filed:** 2026-07-09 (found while visually testing the Usurance source build)
**Owner:** the agent working the v2 / plugins / branding area
**Reporter note (product constraint):** *The embedded KERI Foundation plugin must NOT be part of the white-labeling* — it is a distinct third-party plugin and must keep its own identity regardless of the active brand.

Two separate problems, both visible on the "KERI Foundation" sidebar entry in a **Usurance** run.

---

## Issue 1 — KERI Foundation icon is white-labeled (brand leak)

**Symptom:** In the Usurance app, the "KERI Foundation" sidebar entry shows the **Usurance** eye/logo. It should show KERI Foundation's own icon, never the active brand's.

**Root cause:** the plugin renders its icon from the **brand-staged** asset `:/assets/custom/SymbolLogo.svg`, which `scripts/brand_apply.py` overwrites per brand (it's in `staged_assets`: `SymbolLogo.svg`, …). Two spots:

- `src/locksmith/plugins/kerifoundation/plugin.py:318`
  ```python
  icon = QIcon(":/assets/custom/SymbolLogo.svg")
  return MenuButton(icon=icon, label="KERI Foundation")
  ```
- `src/locksmith/plugins/kerifoundation/plugin.py:665` (in `_build_logo_widget`, the plugin submenu header)
  ```python
  pixmap = QPixmap(":/assets/custom/SymbolLogo.svg")
  ```

Because `:/assets/custom/SymbolLogo.svg` is the *brand* symbol, the KF plugin adopts whatever brand `brand_apply` last staged.

**Fix direction:** give the KF plugin its **own** icon asset that `brand_apply` does NOT touch — e.g. a dedicated static resource like `:/assets/kerifoundation/logo.svg` (add the real KERI Foundation mark under a path outside `assets/custom/`, which is the white-label staging dir). Replace both `:/assets/custom/SymbolLogo.svg` references above with it. Confirm `brand_apply.py`'s staged-asset set never includes the KF asset. Add a regression test asserting the KF plugin's icon path is brand-independent (not under `assets/custom/`).

**Open product question (please confirm with the reporter):** should the KERI Foundation plugin even be *present* in non-`locksmith` brands (e.g. Usurance) at all, or only in the reference Locksmith brand? This doc fixes the *branding leak*; whether to gate plugin *presence* by brand is a separate decision.

---

## Issue 2 — Clicking "KERI Foundation" does nothing (it crashes)

**Symptom:** clicking the entry appears to do nothing. It actually throws and the page never renders.

**Root cause (from the running Usurance app log):**
```
File "src/locksmith/ui/vault/page.py", line 208, in _on_plugin_entry_clicked
File "src/locksmith/plugins/kerifoundation/plugin.py", line 308, in get_setup_page
File "src/locksmith/plugins/kerifoundation/onboarding/page.py", line 547, in on_show
File "src/locksmith/plugins/kerifoundation/onboarding/page.py", line 573, in _populate_account_choices
AttributeError: 'NoneType' object has no attribute 'begin'
```
`on_show` → `_populate_account_choices()` (page.py:573) → `list_eligible_local_identifiers(self._app)` calls `.begin()` (an LMDB/keri txn) on a `None`. Something the KF onboarding page expects (a keri db/hby/store) is `None`.

Context: the vault under test was `Carrier` with `status='pending_onboarding'`, `chosen_destination='kf_onboarding'` (from the KF entry-decision log line just before the traceback). So it happens on the pending-onboarding path when populating the account/AID selector.

**Fix direction:**
1. In `src/locksmith/plugins/kerifoundation/onboarding/page.py:573` (`_populate_account_choices`) and `list_eligible_local_identifiers`, find what `.begin()` is called on and why it's `None` (likely a keri store/env not opened, or a v2 keripy API change in how local identifiers are enumerated — the tree is now on the **KERI-v2 keripy base** `6ab5019e`, so this may be the same v1/v2 surface as the `feat/keri-v2-migration` work).
2. Reproduce quickly without the UI: open a vault (e.g. `carrier2`, passcode `noble`) and call `list_eligible_local_identifiers(app)` / the KF onboarding `_populate_account_choices` path.
3. Not brand-specific — reproduces in the Locksmith brand too (it's a KF-plugin/v2 bug, independent of Issue 1).

---

## How to reproduce (both)
Source-run the app on a vault (Usurance run makes Issue 1 obvious; either brand shows Issue 2):
```
.venv/bin/python -m locksmith.main
```
Open a vault (most local vaults use passcode `noble`), open the "KERI Foundation" plugin entry. Issue 1 = wrong (brand) icon; Issue 2 = click throws `AttributeError: 'NoneType' ... 'begin'` (page doesn't render).

Neither blocks the v0.2.20 build/release mechanics, but Issue 1 (brand leak) is a white-label correctness bug and Issue 2 makes the KF plugin unusable.
