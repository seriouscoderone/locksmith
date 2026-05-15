# Micro App: Designer Plugin

**Date:** 2026-05-12
**Status:** Design spec (pre-implementation)
**Spec it builds on:** `2026-05-09-micro-app-template-authoring-and-data-model.md` (the artifact contract)

## 1. Goal and scope

The **Micro App: Designer** is a Locksmith plugin that lets a subject-matter expert author and edit `micro-app-template.json` artifacts directly, via a structured visual UI. It is the *direct-manipulation* counterpart to the conversational `micro-app-template-gen` skill: same artifact format, different mode.

The Designer reads and writes the canonical artifact defined in the data-model spec. It does not invent any new primitive, schema, or vocabulary. Anything the Designer can produce, a hand-written template can produce, and vice versa.

**In scope (v1):**

- A **Templates browser** entry surface listing every template the workspace knows about
- An **Overview** page per template — first-person mental-model card grid
- Eight **per-primitive editors** for the 8 primitives the data-model spec defines: Commands, Aggregates, Reactions, Workflows, Projections, Rules, Imports, Exports
- A **Validation panel** surfacing schema + semantic errors, navigable to the offending field
- A **JSON source view** as a power-user escape hatch with two-way sync
- A **Cross-reference back-pointer** mechanism so every primitive shows where it's consumed
- **Local file storage** of templates as JSON files under the vault directory
- **Import from file** + **+ New template** (blank) entry paths
- Plugin integration following the Locksmith plugin contract (`PluginBase`, entry point, pages, menu, LMDB store for plugin-local metadata)
- Tests: unit tests for data ops + the validation engine; visual smoke tests for every editor surface following the pattern in `tests/test_create_role_dialog_visual.py`

**Explicitly out of scope (v1, may land in later versions):**

- **Fork / version compare** UI — registered as a deferred feature; surface designed in mockup but not implemented
- **Walk-me-through wizard** mode — guided first-time-author flow; designed as a follow-up
- **Import via OOBI** — depends on the Ecosystem Viewer maturing its discovery surface; the button slot exists in v1 but is disabled
- **Publication / discovery / sharing** of finished templates — that's a Locksmith-core or Ecosystem-Viewer concern, not Designer
- **Deployment / running** of a micro-app — the Designer authors templates; the runtime is the broader wallet
- **Higher-Order Application (HOA) composition** — out of the Designer's surface entirely
- **Multi-user collaboration / merge** — single-author, single-workspace assumption
- **Real-time validation against external trust roots** — the Designer validates the artifact's *internal* shape and references; it does not contact remote AIDs or witnesses

The Designer is a Locksmith plugin like any other — it can be uninstalled, and a template can be authored by hand without it.

## 2. Three-artifact picture (recap)

| Artifact | Role |
|---|---|
| `micro-app-template-gen` (skill) | Conversational authoring path; produces a template by walking an author through structured prompts |
| **`Micro App: Designer`** (this plugin) | **Direct-manipulation authoring; produces and edits templates via a structured UI** |
| `Micro App: Ecosystem Viewer` (separate plugin) | Reads the corpus and renders emergent ecosystem relationships |

The three are independent. The Designer is one of three legal producers of conforming artifacts. The Ecosystem Viewer is a separate plugin that reads the Designer's outputs but does not depend on it being installed.

## 3. Architecture

### 3.1 Plugin shape (follows ecosystem_viewer)

The Designer follows the same shape as `locksmith.plugins.ecosystem_viewer`:

```
src/locksmith/plugins/designer/
├── __init__.py
├── plugin.py          # DesignerPlugin(PluginBase), lifecycle, page wiring
├── pages.py           # Top-level pages: TemplatesBrowserPage, TemplateOverviewPage,
│                      #   plus one page per editor (CommandsEditorPage, …)
├── widgets/           # Reusable widgets: KindRail, FirstPersonCard,
│                      #   CrossRefChip, StateMachineDiagram, SwimlaneDiagram,
│                      #   ValidationBadge, JsonSourceView, …
├── dialogs.py         # Modal dialogs: CreateTemplateDialog, AddPrimitiveDialog, …
├── db.py              # DesignerBaser (per-vault LMDB) — drafts index, recent list,
│                      #   open-state, plugin settings
├── store.py           # File-on-disk template I/O (read, write, saidify,
│                      #   list-workspace)
├── validation.py      # ValidationEngine — meta-schema + semantic checks,
│                      #   returns ValidationReport
├── crossref.py        # Cross-reference computer — given a template, returns
│                      #   "where is X consumed" maps for every primitive
├── README.md
└── (unit + visual tests under tests/plugins/designer/)
```

Entry point in `pyproject.toml`:

```toml
[project.entry-points."locksmith.plugins"]
designer = "locksmith.plugins.designer.plugin:DesignerPlugin"
```

`plugin_id = "designer"`. The plugin uses `vault.plugin_state["designer"]` for runtime per-vault state and `LocksmithConfig.plugin_configs["designer"]` for any user-tunable settings.

### 3.2 Where templates live on disk

Templates are JSON files. The plugin uses the standard locksmith tail-dir convention (`keri/<short-name>` / `.keri/<short-name>`, matching `LocksmithBaser`'s `keri/rt`, the kerifoundation plugin's `keri/locksmith`, and the ecosystem_viewer plugin's `keri/ecosys`). The Designer's tail dir is **`keri/dgnr`** (head path: `~/`).

Under that tail dir:

```
<keri base>/dgnr/
├── <vault.name>.lmdb          # DesignerBaser LMDB (one per vault)
└── templates/
    ├── registered/
    │   └── <SAID>/
    │       ├── micro-app-template.json
    │       └── metadata.json
    └── drafts/
        └── <local-id>/
            ├── micro-app-template.json
            └── metadata.json
```

The `templates/` tree is shared across vaults — a template authored in one vault is visible from another. This is intentional: templates are public-shaped artifacts (eventually published; not vault-scoped secrets), and authors expect their workspace to persist when they switch vaults. The `DesignerBaser` index is per-vault and tracks vault-local concerns (last-opened, dirty drafts the user wants to resume).

- **Registered** = the template has been saidified and finalized at least once. Directory is named by the artifact's `d` (SAID).
- **Drafts** = work-in-progress that hasn't been saidified yet. Directory is named by a UUID `<local-id>`. The artifact's `d` field is empty or holds the last-known SAID before the draft diverged.

Promoting a draft to registered = compute the SAID, move the directory, regenerate the `d` field. This is a single explicit user action ("Finalize"), not implicit on every edit.

`DesignerBaser` keeps an LMDB index for fast Templates-browser rendering: `(local-id-or-SAID) → {label, role_kind, validation_summary, modified_at, source}`. The index is a cache rebuilt from disk on plugin startup and updated on every save; loss of the LMDB does not lose data.

### 3.3 Where templates come from

Three entry paths in v1:

1. **`+ New template`** — opens a blank draft, drops the author directly on the Overview page
2. **`⬇ Import file`** — file picker, parses, validates, lands in `drafts/` (or `registered/` if it already has a valid `d` and parses cleanly)
3. **(disabled in v1)** `🌐 Import via OOBI` — slot exists, button shows tooltip "Coming in a future release"

The `+ New template` path may optionally launch the deferred walk-me-through wizard once that's built; for v1 it just lands on Overview with the role / header empty.

### 3.4 Plugin-local schema validation

The Designer ships a copy of the meta-schema derived from the data-model spec (delivered as a separate follow-on artifact per §11 of that spec). The meta-schema is read at plugin load. `validation.py`'s `ValidationEngine` runs every template through it on open, on every visual edit, and on every save. It does *not* call out to remote validators or to keripy schema infrastructure — this is structural validation of the artifact, not of any deployed credential.

`ValidationEngine` returns a `ValidationReport` shaped:

```python
@dataclass(frozen=True)
class ValidationIssue:
    severity: Literal["error", "warning"]
    code: str               # stable machine code
    message: str            # human-readable text
    path: str               # JSON pointer to the offending field, e.g. "/commands/2/inputs"
    surface: str            # which editor surface should show it, e.g. "commands"

@dataclass(frozen=True)
class ValidationReport:
    issues: tuple[ValidationIssue, ...]
    is_valid: bool          # no errors (warnings allowed)
```

Issues drive: (a) the per-card validation badge on Overview, (b) the validation panel, (c) inline error chips on each editor surface. Clicking an issue in the validation panel navigates to the offending editor and scrolls to the field at `path`.

### 3.5 Cross-reference computation

`crossref.py` computes a single `CrossRefIndex` per loaded template:

```python
@dataclass(frozen=True)
class CrossRefIndex:
    consumers_of: dict[str, tuple[CrossRef, ...]]  # "key" → who consumes it
    referenced_in: dict[str, tuple[CrossRef, ...]] # "key" → where it appears

@dataclass(frozen=True)
class CrossRef:
    surface: str            # "commands" | "workflows" | "rules" | …
    primitive_label: str    # human label of the consumer, e.g. "Issue License"
    primitive_path: str     # JSON pointer to the consumer entry
```

"Key" is a stable id within the template: a command's id, an import's role+credential pair, an aggregate's name. The index is recomputed on every visual edit (cheap; templates are kilobytes).

Every editor surface displays the `consumers_of` view for whatever the user has selected, rendered as the "Used by …" chip strip in the mockups. Clicking a chip navigates to that consumer.

### 3.6 Two-way JSON source view

The JSON source view shows the live artifact as formatted JSON in a read/write text editor. Edits are debounced (~300ms); on each debounce the JSON is re-parsed and validated:

- If it parses + validates: the visual editors update, no warning shown
- If it parses but has validation errors: the visual editors update with red issue badges, the JSON view shows error gutters
- If it fails to parse: the visual editors freeze on the last good state, the JSON view shows a parse-error banner; saving from the JSON view is disabled until parse recovers

The visual editors are the canonical writer; their changes update the in-memory JSON model, which re-renders the JSON view. Round-tripping is value-preserving (whitespace and key ordering are normalised; comments are not supported because JSON, period).

This is a deliberate "JSON is the model" architecture — the visual editors are projections of the model, not separate state. Same model object backs every surface.

## 4. The surfaces (mockup-locked)

The Designer follows a **Profile + drilldown** shell pattern: a Templates browser at the top, then one Overview page per template, with detail editors reachable from the Overview. Every detail editor is a peer; navigation among them is via the Overview, the sidebar, or breadcrumbs.

### 4.1 Templates browser (entry surface)

Three regions:

1. **Toolbar:** Title strip with template count + validity summary on the left; action buttons on the right: `⬇ Import file`, `🌐 Import via OOBI` (disabled v1), `+ New template`.
2. **Filter strip:** Facet chips for validation state, role kind, ecosystem affinity tags; a sort selector on the right (default: recently modified).
3. **Grid of template cards:** 2-up grid. Each card shows: role icon + kind, label, version chip, validation badge, description, ecosystem tags, primitive counts (e.g. "4 commands · 3 workflows"), SAID prefix (or `DRAFT`), modified timestamp, and optional cross-template chips ("↔ pairs with state-doi", "↪ forked from EKWa…").

Clicking a card → Overview for that template. Drafts have a dashed border + "▶ Resume" affordance.

### 4.2 Overview (first-person card grid)

The Overview is **mental-model first**. The author sees their role through a grid of first-person cards, each summarising one primitive group from the *role's own perspective*:

| Card | First-person framing | Edits which primitive |
|---|---|---|
| Role | "I am …" | `role` |
| Held credentials | "I hold …" | `credentials.imports` |
| Issued credentials | "I issue …" | `credentials.exports` |
| Commands | "I do …" | `commands` |
| Reactions | "I respond to …" | `reactions` |
| Workflows | "I follow …" | `workflows` |
| Aggregates | "I track …" | `aggregates` |
| Projections | "I see …" | `projections` |
| Rules | "I'm bound by …" | `rules` |

Each card shows: a primitive count, the top 2-3 entries inline, a `+ Add` affordance, and a `Cross-refs ↗` link if the primitive is referenced elsewhere. Clicking the card title or any entry navigates to the corresponding detail editor.

The header strip at the top of Overview shows: template label, role chip, SAID (truncated), version, validation status pill, and a kebab menu with Save / Finalize / Export file / Duplicate / Delete actions.

### 4.3 Per-primitive detail editors (8 surfaces)

All eight follow the same shell:

- **Identity strip** at top: breadcrumb back to Overview, template label, surface label (e.g. "Commands")
- **Left rail:** Typed list of primitives of this kind. Each row has a kind-color dot, a human label, and a validation badge if it has issues. `+ Add` at the bottom.
- **Right pane:** sectioned form for the selected entry. Sections vary per surface but always include: identity (label + id), structure (the primitive's defining fields), and a **"Used by"** strip listing cross-references.

The sections per surface:

| Surface | Sections in the right pane |
|---|---|
| **Commands** | Identity · Inputs · Effects (which TEL ops fire, which exn messages send) · Pre/post conditions (rules referenced) · Used by |
| **Aggregates** | Identity · Source events · Fold expression · Cardinality (singleton / collection) · Used by |
| **Reactions** | Identity · Trigger (which incoming exn / IPEX verb / TEL transition) · Effect (which command runs, which projection updates) · Used by |
| **Workflows** | Identity · Roles involved · Swimlane SVG diagram (self-vs-counterparty, with IPEX verb arrows) · Step list · Used by |
| **Projections** | Identity · Source aggregates / events · Render template (UEL fold expression) · **Live preview pane** (sample events folded into rendered output) · Used by |
| **Rules** | Identity · Kind (legal-prose / predicate / computation / validation / behavioural-expectation) — color-coded · Body · Attaches to (which command / workflow / credential) · Used by |
| **Imports** | Identity · Issuer role · Credential schema · Required vs optional · Disclosure tier · Used by |
| **Exports** | Identity · Issuee role · Credential schema · **TEL state-machine SVG diagram** (issue=orange, update=teal, revoke=pink) · Custom states · Used by |

Visual language is consistent across editors:

- **Kind-color rail dots** so the list is scannable by type at a glance
- **TEL primitive color coding:** orange = issue, teal = update, pink = revoke — wherever those verbs surface
- **Cross-reference chips** at the bottom of every right pane, navigable
- **Inline `+ Add` rows** within sections that hold collections (e.g. "+ Add input" inside a Command's Inputs section), so common edits don't require dialog popups

**Role and Header editing** do not get their own full detail pages in v1. They are edited via modal dialogs reachable from the Overview's "I am" card (Role) and the Overview header strip (Header — label, description, version). This keeps the surface count low and reflects that both primitives have small field sets and are typically set once at template creation, not iteratively refined.

### 4.4 Validation panel

A togglable side-panel reachable from the toolbar in any surface. Shows `ValidationReport.issues` grouped by surface, severity-sorted:

```
ERRORS (3)
  commands/
    ⛔ Command "Approve Application" references undefined rule "min-capital-100M"
       → /commands/2/preconditions/0
    ⛔ Command "Issue License" has no exports declared as effects
       → /commands/3/effects
  exports/
    ⛔ Export "Carrier License" has no issuance command
       → /credentials/exports/0

WARNINGS (1)
  rules/
    ⚠ Rule "min-capital-100M" defined but never referenced
       → /rules/3
```

Clicking an issue navigates to that editor and scrolls/focuses the field at the JSON pointer. The panel re-computes on every edit.

### 4.5 JSON source view

Toggle in the toolbar of any editor or the Overview. Side-by-side or full-screen. Read/write monospace editor showing the live artifact JSON. Two-way bound per §3.6.

## 5. Data flow summary

```
┌──────────────────────────────────────────────────────────────────────┐
│ User edits a field in (e.g.) Commands editor                          │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
              ┌────────────▼──────────────┐
              │ Update in-memory model    │
              │   (dict-shaped JSON)      │
              └────────────┬──────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
┌───────▼──────┐  ┌────────▼────────┐  ┌─────▼────────────┐
│ Re-validate  │  │ Re-cross-ref    │  │ Re-render every  │
│ (validation. │  │ (crossref.py)   │  │ editor surface   │
│  py)         │  │                 │  │ subscribed to    │
└───────┬──────┘  └────────┬────────┘  │ this model       │
        │                  │            └──────────────────┘
        └──────────┬───────┘
                   ▼
        ┌─────────────────────┐
        │ Update badges,      │
        │ panel, cross-refs   │
        └─────────────────────┘
```

Saves are explicit (Save button + Cmd-S). Save writes the JSON to disk under the appropriate `drafts/<local-id>/` or `registered/<SAID>/` directory and refreshes the `DesignerBaser` index.

**SAID handling:** `d` is computed via the same recipe as the data-model spec mandates (Blake3-256 via keripy's `Saider.saidify` with the `d` field zeroed before hashing). The plugin recomputes `d` only on "Finalize", never silently on edit, because users need to be able to track work-in-progress without churning their identifier. Drafts may carry an empty `d` or the stale prior `d`; the Finalize action recomputes and (if the path's SAID changes) renames the directory.

## 6. Plugin integration

### 6.1 PluginBase implementation

```python
class DesignerPlugin(PluginBase):
    @property
    def plugin_id(self) -> str:
        return "designer"

    def initialize(self, app):
        # Load meta-schema, build pages, wire signals
        ...

    def on_vault_opened(self, vault):
        # Open DesignerBaser (tail dir keri/dgnr, named after vault.hby.name)
        # Scan templates/ directory, rebuild index, populate Templates browser
        ...

    def on_vault_closed(self, vault, *, clear=False):
        # Flush pending saves, close DB, clear plugin_state
        # If clear=True, also rm -rf the templates/ directory for this vault
        ...

    def get_menu_entry(self) -> MenuButton:
        # "Designer" sidebar entry with hammer/template icon
        ...

    def get_menu_section(self) -> list[QWidget]:
        # Submenu: "Templates", "Validation", "JSON view" (the last two
        # disabled when no template is open)
        ...

    def get_pages(self) -> dict[str, QWidget]:
        # TemplatesBrowserPage, TemplateOverviewPage,
        # plus one detail editor page per primitive (8 pages)
        ...

    def get_doers(self) -> list[doing.Doer]:
        # v1: empty — no background work yet.
        # (Future v2: a Doer watching templates/ for external edits.)
        return []
```

The Designer registers 10 page keys in `VaultPage`'s `content_stack`:

```
designer.templates
designer.overview
designer.commands
designer.aggregates
designer.reactions
designer.workflows
designer.projections
designer.rules
designer.imports
designer.exports
```

### 6.2 plugin_state usage

`vault.plugin_state["designer"]` holds runtime state for the open vault:

```python
{
    "open_template_id": str | None,     # local-id or SAID currently being edited
    "model": dict | None,               # in-memory JSON model
    "validation": ValidationReport,
    "crossrefs": CrossRefIndex,
    "dirty": bool,                       # unsaved changes flag
}
```

Closing a template clears these (after prompting for unsaved changes).

### 6.3 Settings

`LocksmithConfig.plugin_configs["designer"]` v1 supports:

```yaml
designer:
  default_view: overview        # "overview" | "json" | "last"
  auto_save: false              # if true, save on every edit (off by default)
  walk_through_on_new: false    # for the deferred wizard
```

All keys are optional with the defaults above.

## 7. Testing strategy

The locksmith repo's testing model (per `CLAUDE.md`):

- **Unit tests** for pure-logic modules: `store.py`, `validation.py`, `crossref.py`. Run under `QT_QPA_PLATFORM=offscreen pytest`.
- **Visual smoke tests** for every editor surface following `tests/test_create_role_dialog_visual.py`:
  - Render the page with a fixture template
  - Assert structural state (widget tree contains expected entries, badges, chips)
  - Resize to a stable size, `qapp.processEvents()`, wait for any animations, `widget.grab()` → PNG to `tests/_screenshots/designer/`
  - Human review or LLM-vision review of the PNG

Fixture templates required:
- `fixtures/regulator-grants-carrier-license.json` (valid, no warnings)
- `fixtures/carrier-license-application.json` (valid, with imports)
- `fixtures/broken-references.json` (multiple validation errors of every kind)
- `fixtures/draft-untitled.json` (skeletal, no SAID, drives walk-through wizard later)

The fixtures double as the seed corpus for manual exploration during development.

## 8. Phasing

**v1 (this spec):** Templates browser + Overview + 8 detail editors + validation panel + JSON source view + cross-references + file-on-disk storage + plugin integration + tests.

**v2 (separate spec, not now):** Walk-me-through wizard mode.

**v3 (separate spec):** Fork / version compare view; Import via OOBI (depends on Ecosystem Viewer maturing).

**v4 (separate spec, far future):** Multi-user / collaborative authoring; remote-trust validation hooks.

Each phase ships independently. v1 is shippable without v2/v3/v4. The mockups for v2 (walk-through) and v3 (fork compare) exist as design artifacts but are not in this spec's scope.

## 9. Open questions (to revisit during plan-writing)

1. **Meta-schema delivery.** The data-model spec marked the meta-schema as a follow-on artifact (§11). The Designer needs it at plugin load. If the meta-schema isn't yet authored, the Designer plan must include authoring it as a prerequisite task — that may belong upstream of this plugin.
2. **`uel` evaluator availability.** Projection live-preview and aggregate fold expressions need a UEL/1.0 evaluator. The cheat-sheet (committed in the followups branch) defines the surface; an actual evaluator implementation may not exist yet. If not, the live-preview pane is a v1 wishlist item, and we fall back to "show the expression text only, no preview" until an evaluator lands. Decide during planning.
3. **Validation engine reuse.** The Ecosystem Viewer already has `locksmith.acdc.inspector` for ACDC schema validation. The Designer's `validation.py` validates the *template artifact*, not the ACDCs it references — so they're disjoint. But if the Designer wants to validate import/export ACDC references against actual schemas in `vault.hby.db.schema`, that's an integration point worth flagging.
4. **Workspace location.** Templates currently land under the vault's keri base path. If a user wants to share templates across vaults, this needs revisiting — likely a per-user (not per-vault) templates dir, but YAGNI for v1.

## 10. Appendix: mockup references (informative)

The visual design for every v1 surface is mocked at:

```
.superpowers/brainstorm/<session>/content/
├── shell-shapes.html              # Shell pattern survey (Profile + drilldown won)
├── templates-browser.html         # §4.1 entry surface
├── overview-page.html             # §4.2 Overview (v1 — canonical)
├── commands-editor.html           # §4.3 Commands
├── exports-editor.html            # §4.3 Exports + state-machine SVG
├── workflows-editor.html          # §4.3 Workflows + swimlane SVG
├── rules-editor.html              # §4.3 Rules + typed left rail + cross-refs
├── projections-editor.html        # §4.3 Projections + live preview
└── remaining-editors-gallery.html # §4.3 Reactions / Imports / Aggregates
```

The mockup HTMLs are ephemeral brainstorming artifacts in a session directory, not committed assets. This spec is the durable record of what was decided.
