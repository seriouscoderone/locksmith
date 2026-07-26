# `_app_data_base()` hardcodes "Locksmith" — every brand writes into Locksmith's app-data dir

**Filed:** 2026-07-25 (found while debugging the Usurance HOA first-run blank screen)
**Domain:** branding / app data paths (`src/locksmith/update/log.py`)
**Severity:** brand leak. Not user-breaking today, but it silently co-mingles brands' data and
sent us hunting for Usurance logs in the wrong place during a live debug.

## Symptom
A Usurance build writes its logs and `verification.log` into
`~/Library/Application Support/**Locksmith**/`, not a Usurance-specific directory. Two brands
running on one machine share one log directory and one `verification.log`.

## Root cause
`src/locksmith/update/log.py:_app_data_base()` returns a **literal** per-platform path:

```python
if sysname == "Darwin":
    return Path.home() / "Library" / "Application Support" / "Locksmith"
elif sysname == "Windows":
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Locksmith"
else:
    return Path.home() / ".local" / "share" / "locksmith"
```

The brand manifest already declares the intended name — `[identity] data_dir` (e.g. `"Usurance"`)
— but nothing reads it here. `update/file_logging.py:58` derives `log_dir` from this function, so
the leak covers logs plus the verification log.

## Fix sketch
Make it brand-aware off `brand()` / `[identity] data_dir`, defaulting to the reference brand's
`Locksmith` when unset (so the Locksmith brand's path is unchanged).

**This is a data-relocation change — treat it as such.** Existing installs have logs, prefs, and
`verification.log` under the old path; after the change a non-locksmith brand would appear to
"lose" its history. Decide deliberately between:
- **Migrate**: on first launch, move/copy the old brand-agnostic dir into the new brand dir.
- **Read-through**: prefer the new path, fall back to the legacy path when the new one is absent.
- **Leave logs, split only new writes**: simplest, but leaves a permanently confusing split.

Whatever is chosen, keep `Locksmith`'s effective path byte-identical to today.

## Verify
1. Launch each brand from source (`LOCKSMITH_BRAND_CONFIG=…/<brand>/brand.json`) and assert the log
   dir is brand-specific.
2. A unit test parameterized over brands asserting `_app_data_base()` follows `[identity] data_dir`,
   and that `locksmith` still resolves to the historical path.
3. Whichever migration strategy is chosen, a test for the upgrade path (old dir present → expected
   outcome).

## Related
- `[[2026-07-25-vault-namespace-not-brand-scoped]]` — the same "brands share one location" theme, for
  KERI vaults rather than app data. Consider designing both together; a single "brand data root"
  concept could serve both.
- The HOA first-run bug (`c064d517`) was the same class of assumption at the vault layer: code
  treating a brand-agnostic global as if it were this brand's.
