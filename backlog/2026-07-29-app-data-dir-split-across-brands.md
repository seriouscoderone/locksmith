# App-data paths are half brand-scoped: the diagnostic log follows the brand, the verification log and staging do not

**Status:** backlog · **Raised:** 2026-07-29 · **Priority:** low (cosmetic today; a support-diagnosis trap once a second brand ships updates)

## What we saw

Adding the per-brand rotating diagnostic log
(`2026-07-29-grant-send-reports-success-while-undeliverable.md` item 3)
introduced `branding.app_data_dir()` and pointed `update/file_logging.py` at it.
The two OTHER consumers of the same idea still hardcode `"Locksmith"` in
`update/log.py:_app_data_base`:

- `update/log.py:default_log_path()` → `<…>/Locksmith/verification.log`
- `update/staging.py` → `<…>/Locksmith/staging`

So a Usurance install now writes `…/Usurance/logs/usurance.log` while its
update-verification history and staged downloads land under `…/Locksmith/`.
Anyone diagnosing a Usurance update failure looks in the Usurance directory,
finds the app log but no verification history, and concludes the gate never ran.

Deliberately not fixed with the log change: moving `verification.log` orphans
the persisted `VerificationResult` the Release Verification dialog reloads
(`load_last_verification_result`), and moving `staging` touches paths the
native updater hands to Sparkle/WinSparkle. Both want their own change with an
install-upgrade story, not a drive-by.

## The actual work

1. Route `update/log.py` and `update/staging.py` through
   `branding.app_data_dir()`.
2. Decide the upgrade behavior per path: migrate-on-first-read (copy the old
   file if the new one is absent) for `verification.log`; for `staging`, a stale
   directory under the old name is disposable, so plain adoption is fine.
3. Confirm the Windows uninstaller/MSI cleanup still targets the right
   directory for a non-reference brand.

## Evidence / references

- `core/branding.py:app_data_dir()` (added 2026-07-29)
- `update/file_logging.py` (uses it) vs `update/log.py:40-53`,
  `update/staging.py:68-74` (hardcode `Locksmith`)
- Related: `project_white_label_branding_engine` — same "brand config, never a
  framework hardcode" rule this violates
