# KERI Foundation plugin missing from frozen builds (PyInstaller entry-point gap)

**Filed:** 2026-07-09 (found while inspecting the shipped 0.2.20 build)
**Domain:** packaging (PyInstaller specs) — same class as the brand.json bundling (3fa50af) + SSL-cert (401cccd) frozen-app gaps
**Severity:** the bundled KERI Foundation plugin is absent from EVERY shipped build (0.2.18–0.2.21). Not a code regression; source runs are fine. Affects both brands. Not release-*blocking* (the cert-fix release 0.2.21 ships without it), but the plugin is invisible to users until fixed.

## Symptom
In a frozen build, the vault sidebar has **no "KERI Foundation" entry**. (Micro App Designer still appears — it loads from `~/.locksmith/plugins/index.json`, a different path.)

## Root cause — TWO missing pieces, both in the specs
The KF plugin is a **purely bundled entry-point plugin** — declared in `pyproject.toml`:
```
[project.entry-points."locksmith.plugins"]
kerifoundation = "locksmith.plugins.kerifoundation.plugin:KeriFoundationPlugin"
```
and NOT in `~/.locksmith/plugins/index.json`. Its only discovery path is
`importlib.metadata.entry_points(group="locksmith.plugins")` (`src/locksmith/plugins/manager.py:120`, `_discover_from_entry_points`). In the frozen app that fails twice:

1. **Entry-point metadata not bundled.** The specs have no `copy_metadata`, so PyInstaller strips the `Locksmith` dist-info → `entry_points(group="locksmith.plugins")` returns an empty set → KF never discovered.
2. **Module code not bundled.** `locksmith.plugins.kerifoundation` is not statically imported anywhere in the app and is not in `hiddenimports`, so PyInstaller's static analysis never pulls it in. Even if (1) were fixed, `ep.load()` would raise `ModuleNotFoundError`.

## Fix (both specs: `packaging/Locksmith.macos.spec` and `packaging/Locksmith.windows.spec`)
```python
from PyInstaller.utils.hooks import copy_metadata, collect_submodules
# ... in datas:
datas += copy_metadata("Locksmith")          # bundle the entry-point metadata
# ... in hiddenimports:
hiddenimports += collect_submodules("locksmith.plugins.kerifoundation")
```
(`collect_submodules` pulls plugin.py + onboarding/db/identifiers/witnesses/watchers; a bare
`"locksmith.plugins.kerifoundation.plugin"` hiddenimport also works since PyInstaller follows its
imports, but collect_submodules is safest.)

Scope note: `kerifoundation` is currently the ONLY bundled `[project.entry-points."locksmith.plugins"]` entry — this fix covers it. If more bundled entry-point plugins are added later, `copy_metadata` already covers metadata; extend `hiddenimports`/`collect_submodules` per plugin.

## Verify
1. `scripts/devbuild-macos.sh` (unsigned local build; run `brand_apply.py --brand <brand>` first if testing a brand) → open a vault (passcode `noble` on most local vaults) → confirm **"KERI Foundation"** now appears in the sidebar with its own icon.
2. Regression test (extend `tests/unit/branding/test_spec_brand_values.py` or add a spec test): assert both specs' text contains `copy_metadata(` and `kerifoundation` in `hiddenimports`/`collect_submodules` — cheap guard so this can't silently regress (mirrors the existing release-triad datas test).

## Repro
Build a frozen app with the current specs (`scripts/devbuild-macos.sh`), open a vault → the KERI Foundation sidebar entry is absent. From source (`.venv/bin/python -m locksmith.main`) it IS present — because the editable install carries the dist-info + the module is importable.

## Related
- brand.json bundling fix (commit `3fa50af`) and the SSL-cert fix (`401cccd`) are the same "works from source, broken frozen" class. A broader audit of "what else does source have that the frozen app doesn't" may be worthwhile (e.g. any other importlib.metadata / dynamic-import usage).
