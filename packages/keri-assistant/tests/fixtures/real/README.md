# Real micro-app template fixtures

Verbatim copies from `ugard/docs/micro-apps/` (spec_version `micro-app-template/0.1`), vendored so tests
never depend on a sibling repo path. The AIDs and SAIDs inside are **test values**, not production
identifiers. Refresh by re-copying if the upstream templates change shape.

- `regulator_grants_carrier_license.json` — State DOI (`role.kind: government`) granting a carrier licence.
  5 commands, every one with `counterparty_role: carrier`, all `authz.method: open` (so no pinned
  `schema_said`). `grant_license` declares **3** emissions and a `holder_aid` payload field.
  This template is why the never-verb floor was narrowed: its `revoke_license` was being silently dropped.
- `actuary_attests_product_rating.json` — credential-gated (`authz.method: credential` with `schema_said`
  + `issuer`), which is the only one of the two that exercises the pinned-`schema_said` path.

Both files were scanned before vendoring: no emails, URLs, or personal identifiers appear in either
template.
