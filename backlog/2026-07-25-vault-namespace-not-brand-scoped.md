# Vault namespace is not brand-scoped — every brand shares `~/.keri`

**Filed:** 2026-07-25 (root-caused while fixing the Usurance HOA blank first-run screen)
**Domain:** core vault storage (`core/apping.py:environments`, `core/habbing.py` open paths, branding)
**Severity:** design gap. Already caused one user-visible bug (below). Fixing it properly needs a
migration, so it was deliberately deferred rather than bolted on.

## Symptom / what it already broke
Every brand reads and writes the same KERI base (`~/.keri`), so `environments()` returns **other
brands'** vaults. Concretely, on this machine `~/.keri/rt/` held `Carrier`, `usurance-custody`, and
`Utah State` — none of them created by Usurance — yet the Usurance HOA build treated their presence
as "this machine already has vaults."

That made both HOA launch branches dead code: the first-run SetupPage was suppressed
(`ui/window.py`) and `bootstrap_default_environment` no-op'd (`core/bootstrapping.py`), so a peeled
HOA build landed on a blank page. Fixed at the launch layer in `c064d517` by resolving the brand's
**own** workspace (`hoa_workspace_vault()`) instead of "any vault" — but that is a targeted fix, not
the underlying repartition.

## Root cause
`[identity] data_dir` exists in every `brand.toml` (e.g. `"Usurance"`) but **nothing uses it for vault
storage**. The KERI base comes from `config.base` / `~/.keri` (`core/apping.py:376`,
`_vault_head_dirs()` / `_store_dir()`), with no brand component anywhere in the path.

Consequences beyond the fixed bug:
- A brand can enumerate, and potentially open, another brand's vaults.
- Vault-name collisions across brands are possible (two brands each wanting `Default`).
- "Reset this brand" / uninstall cannot cleanly scope to one brand's data.

## Fix sketch (needs design + migration — do not rush)
Introduce a brand-scoped vault root (e.g. `~/.keri/<data_dir>/` or `~/.<data_dir>/keri`) derived from
`[identity] data_dir`, with the reference `locksmith` brand keeping today's exact path so existing
installs are untouched.

Migration is the hard part and the reason this is filed rather than done:
- Existing vaults live in the shared base with no record of which brand made them. There may be no
  reliable way to attribute them — a Usurance-created vault and a Locksmith-created one are
  indistinguishable on disk today.
- Options: leave legacy vaults visible to the reference brand only (and let other brands start
  empty); or an explicit user-driven "adopt this workspace into <brand>" step. There is precedent for
  the adoption shape — see `adopt_legacy_vaults` (referenced in `environments()`'s docstring) and the
  legacy-vault-adoption spec (`docs/superpowers/specs/2026-07-18-legacy-vault-adoption-design.md`).
- Whatever is chosen, **never silently move or hide a user's existing vault** — these hold keys.

## Verify
1. Two brands each create a vault named `Default`; both persist independently and neither appears in
   the other's `environments()`.
2. Locksmith's resolved vault path is byte-identical to the pre-change path (no migration for the
   reference brand).
3. Upgrade test: a machine with pre-change vaults reaches the designed outcome with **zero** vault
   data lost or relocated without consent.
4. The HOA launch dispatcher still takes exactly one branch under the new scoping (the
   `test_hoa_workspace_resume.py` guard should keep holding).

## Related
- `[[2026-07-25-app-data-dir-hardcodes-locksmith]]` — same "brands share one location" theme for app
  data (logs/prefs). A single "brand data root" concept could serve both; design them together.
- `c064d517` — the launch-layer fix that made this harmless *for launch* while leaving cross-brand
  visibility intact.
