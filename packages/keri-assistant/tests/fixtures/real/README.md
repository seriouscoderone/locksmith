# Real micro-app template fixtures

**No longer verbatim.** Both files started as copies of two templates from `ugard/docs/micro-apps/`,
vendored so tests never depend on a sibling repo path. On 2026-08-02 (plan Task 18, commit `cd5eb105`)
both were migrated in place to track this repo's own template model: `tel_primitive`, `lifecycle_advance`
and the outbound `verb` were removed; `via_command`, `mints_credential_id` and `refuse` were added. Both
files still declare the **top-level** `spec_version: micro-app-template/0.1` — the migration did not bump
it, so it no longer describes what the files actually carry.

*Corrected 2026-08-02 (fix round 2): this paragraph said "their **header** still declares
`spec_version`". It does not. `spec_version` is a top-level field; `header` carries a different,
similarly-named `version` (the bundle's own authoring version — `1.2` here and `1.0` in
`actuary_attests_product_rating.json`), which the migration also left alone. Two fields, two meanings,
and pointing at the wrong one sends whoever fixes it editing the wrong line.*

**Do not refresh these by re-copying from `ugard/docs/micro-apps/`.** That corpus is being deleted and
re-authored (see ugard's `backlog/2026-07-31-delete-and-reauthor-the-ipc-corpus.md`); it will look
"newer" than these fixtures indefinitely because it is frozen pending rewrite. Copying it over these
files would silently revert the 2026-08-02 migration and reintroduce the deleted vocabulary. If the
upstream shape changes again once the corpus is re-authored, treat adopting it as a deliberate decision —
re-derive these fixtures on purpose and update this note — not a mechanical refresh.

**The 2026-08-02 migration did not sweep `payload_mapping`.** Both files still carry it (a field a prior,
separate wave — 2026-07-28 — deleted from the current template model): 7 occurrences in
`regulator_grants_carrier_license.json`, 16 in `actuary_attests_product_rating.json`. That was in scope
for a different task and is out of scope here; nothing in this repo validates these files against the
micro-app-template meta-schema, so the suite does not catch it, but do not read either file as a clean,
current-model example — they would fail meta-schema validation today. Fixing that is content repair, not
a documentation fix, and is intentionally left to whoever re-authors the corpus.

The AIDs and SAIDs inside are **test values**, not production identifiers.

- `regulator_grants_carrier_license.json` — State DOI (`role.kind: government`) granting a carrier licence.
  5 commands, every one with `counterparty_role: carrier`, all `authz.method: open` (so no pinned
  `schema_said`). `grant_license` declares **2** emissions (`exchange`, `aggregate_event`) and a
  `holder_aid` payload field. This template is why the never-verb floor was narrowed: its
  `revoke_license` was being silently dropped.
- `actuary_attests_product_rating.json` — credential-gated (`authz.method: credential` with `schema_said`
  + `issuer`), which is the only one of the two that exercises the pinned-`schema_said` path.

Both files were scanned before vendoring: no emails, URLs, or personal identifiers appear in either
template.
