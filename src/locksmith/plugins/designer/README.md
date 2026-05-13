# Micro App: Designer

A Locksmith plugin for direct-manipulation authoring of
`micro-app-template.json` artifacts.

## What this is

The Designer is the visual counterpart to the conversational
`micro-app-template-gen` skill. Same canonical artifact format,
different mode: where the skill walks an author through structured
prompts, the Designer drops them straight into a structured editor
surface and lets them edit any primitive at any time.

Templates authored here conform to the contract defined in
`docs/superpowers/specs/2026-05-09-micro-app-template-authoring-and-data-model.md`
and validated against the meta-schema at
`docs/superpowers/specs/schemas/micro-app-template.schema.json`.

## Surfaces

The Designer ships 10 pages:

1. **Templates browser** — entry surface; cards in a 2-up grid keyed
   on `header.display_name`, `role.display_name`, role kind.
2. **Overview** — first-person mental-model card grid per template
   ("I am / I hold / I issue / I do / I respond to / I follow / I track /
   I see / I'm bound by").
3-10. **Per-primitive editors** — Commands, Aggregates, Reactions,
   Workflows, Projections, Rules, Imports, Exports.

Plus cross-cutting surfaces: a togglable **Validation panel**
(`widgets/validation_panel.py`) and a two-way bound **JSON source view**
(`widgets/json_source_view.py`).

Each per-primitive editor follows the same shape — `PrimitiveEditorShell`
on the outside (left rail with kind-color dots + identity strip + swappable
right pane), and a primitive-specific section pane on the inside.

## Storage

Templates live as JSON files under `keri/dgnr/templates/`:

- `templates/registered/<SAID>/` — finalized templates
- `templates/drafts/<local-id>/` — work-in-progress

The plugin maintains a per-vault LMDB index (`DesignerBaser`, tail dir
`keri/dgnr`) for fast Templates-browser rendering and last-opened
resume. The index is rebuildable from disk; loss of the LMDB does not
lose user data.

Tests may override the root via `vault.plugin_state["designer.root_override"]`.

## Validation

`ValidationEngine` wraps `locksmith.micro_app_template.validate` (JSON-
Schema meta-schema + cross-reference checks) and adds a `surface` field
to each issue so the validation panel can route the user back to the
right editor. Validation runs on open, on every visual edit (when wired),
and on save.

## Cross-references

`crossref.compute_crossrefs(doc)` produces a `CrossRefIndex` keyed by
`<kind>:<id>` (e.g. `rule:solvency_minimum`, `export:carrier_license`).
Every editor's "Used by" chip strip subscribes to its primitive's key
and lets the user navigate to consumers.

## What v1 doesn't ship

The spec calls out v2/v3 deferrals — these are NOT in v1:

- **Walk-me-through wizard** — guided first-time-author mode
- **Fork / version compare** — diff view across templates or versions
- **Import via OOBI** — depends on Ecosystem Viewer maturity (button
  exists but is disabled, tooltip "Coming in a future release")

Drilldown navigation from the Overview to a specific editor is wired
via signals but the `vault_page._show_page(...)` call to actually switch
the visible page is left for the host integration to provide; v1 logs
the request.

## Spec source of truth

See `docs/superpowers/specs/2026-05-12-designer-plugin.md` for the spec
and `docs/superpowers/plans/2026-05-12-designer-plugin-addendum.md` for
the canonical-schema field mapping used during implementation.
