# Permitted-Issuer Edges in the Ecosystem Graph — Design Extension

Date: 2026-05-07
Status: Design vision (extends `2026-05-06-ecosystem-viewer-redesign.md`
and `2026-05-07-acdc-parties-lifecycle.md`)
Audience: the implementer (a separate Qt/PySide6 engineer) and the
product owner

This document is an addendum responding to a single product question
about the ecosystem graph view. References of the form "redesign §N"
point at `2026-05-06-ecosystem-viewer-redesign.md`; "lifecycle §N"
points at `2026-05-07-acdc-parties-lifecycle.md`. Spec citations point
at `~/KERI/code/kswg-acdc-specification/spec/spec-body.md`.

---

## Section 1 — What's being asked & why it matters

### 1.1 The user's question, restated

> In the graph view, would it make sense to have an "issues" line from
> the intended issuer of a credential? The ACDC itself has no "intended
> issuer" — but the ecosystem (EGF) does. Should we capture that data?
> Could the graph view itself host a drag-to-draw affordance that adds
> an intended issuer to a credential?

The user is right on every count. There **is** an "intended-issuer"
notion, it lives at the ecosystem layer (not on individual ACDCs or
schemas), and the data is already captured — Stage 9 added
`EcosystemRecord.permitted_issuers: dict[str, list[str]]` (see
`db.py:54, 226-279`). The List tab surfaces it via per-schema chip
rows with `+`/`×` affordances (`pages.py:2113-2228`); the side panel
shows it as a clickable list when a schema is selected
(`graph_view.py:613-636`). What is **missing** is any visual edge in
the canvas itself that says "AID X is an permitted issuer of
schema S in this ecosystem."

### 1.2 Why an edge belongs on the canvas

The graph view's whole pitch (redesign §1.4) is that *relationships
are spatial, not textual*. Right now the graph honors that for
chain-of-authority but not for issuance. An issuer node sits in the
bottom row; a schema sits above it; nothing connects them. The user
has to click a schema and read a side-panel chip list to learn "Acme
Health permittedly issues Patient Consent in this ecosystem." A
textual fallback on a page whose principle says otherwise.

The data exists. The edge can finally be drawn.

### 1.3 Spec/convention discipline

- **Issuer** (top-level `i`) is an ACDC spec primitive — a
  *per-instance* fact about who signed a specific credential. **Not**
  what the new edge represents.
- **"Permitted issuer of schema S in ecosystem E"** is a pure
  *convention overlay*. The spec has no such notion; the EGF layer is
  where governance asserts it. Mark as such in code comments.
- **Membership** (redesign §5.4) is also a convention, less specific
  than permitted-issuer. See §2.4 below for how the two relate.

---

## Section 2 — Visual treatment of permitted-issuer edges

### 2.1 Design constraints

The new edge style must distinguish from two existing line treatments
and one prospective one:

1. **Chain-of-authority edges** between schemas: solid (or DI2I dashed)
   arrows with operator-aware decorations (redesign §2.5). Color:
   `TEXT_SECONDARY` neutral, brightening to `PRIMARY` on hover. Carry
   labels and arrowheads.
2. **Membership edges** schema↔issuer: dotted lines, no arrowhead,
   light color (redesign §5.4). Currently latent (`MembershipEdge`
   exists but is not instantiated — see `graph_items.py:764-800` and
   `graph_view.py:518-531` for the deliberately commented-out block).
3. **Feedback edges** (cycle-breakers in Sugiyama layout, redesign
   §5.5): curved up-arrows with a slight red tint.

Permitted-issuance is semantically the "strongest" of the
issuer↔schema relationships — stronger than mere membership ("this AID
is in this ecosystem at all"), and richer than membership because it
asserts *role*, not just presence. It deserves a treatment that reads
as the more specific, more committed relationship.

### 2.2 Recommendation: solid issuance line, teal, with a small "issues" arrowhead

**Stroke:** 1.25px solid line (slightly thinner than chain-of-authority
edges at 1.5px — these aren't the headline relationship of the canvas,
but they aren't meant to whisper either).

**Color:** `#0D9488` teal — the same teal already in the palette for
"this credential carries machinery you should look at" (redesign §2.4
aggregate dot, §3.2 lifecycle revocable). Reusing it is intentional:
this edge says "this AID *is the machinery* by which credentials of
this schema enter the ecosystem." It rhymes color-wise with the
clockface lifecycle glyph on a registry-backed schema, which sometimes
appears at the same node.

**Direction:** issuer → schema, with a small **open** (hollow)
triangular arrowhead at the schema end. The hollow arrowhead is the
signal that this is a *capability* assertion ("X is allowed to issue
S"), not an *event* ("X did issue S"). Solid arrowheads are reserved
for chain-of-authority (which models a constraint on actually-issued
credentials).

**Anchor points:** issuer `top_anchor()` → schema `bottom_anchor()`.
Issuer nodes already pin to the bottom row in the Sugiyama layout
(redesign §5.5; `graph_view.py:481`), so issuance lines naturally rise
upward. Schemas the issuer is permitted for will be in higher
layers; a small Bézier curve (control point biased toward vertical)
keeps the edge from crossing other schema nodes when a schema sits
several layers up.

**No label by default.** The edge meaning is entirely "issues" —
there's no operator variation to disambiguate, unlike chain-of-
authority. Tooltip on hover spells out: `"<alias>  issues  <schema
title>  in this ecosystem"`. If we ever need to name the relationship
visually (we don't yet), a small italicized `issues` pill at the
midpoint can be added — but defer.

**Hover treatment.** Edge brightens to a saturated teal (`#0F766E`)
and bumps to 1.75px. Both endpoints get a subtle glow ring — the
issuer and schema both light up so the user can see "this edge
connects these two specific nodes" even when the canvas is dense.

**Selection-aware dimming.** When a schema is selected, all
permitted-issuer edges *not* incident on that schema fade to
20% opacity; edges incident on the selected schema stay full. Same
behavior when an issuer is selected. This converts the edge layer
from a static decoration into a focus tool — selecting the schema
becomes "show me who's authorized to issue this," and selecting the
issuer becomes "show me what this AID is allowed to issue."

### 2.3 ASCII mockup

```
                  ┌──────────────┐                ┌──────────────┐
                  │              │  parent        │              │
                  │ Patient      ├───────────────▶│ Provider     │
                  │ Consent     ◁│  I2I (default) │ Authoriz.    │
                  │              │                │              │
                  └──────┬───────┘                └──────┬───────┘
                         ╲                               ╱
                          ╲    teal,                    ╱
                           ╲   hollow ▷                ╱
                            ╲                         ╱
                             ╲                       ╱
                              ▽                     ▽
                            ╭─────╮             ╭─────╮
                            │  ✱  │             │  ✱  │
                            ╰─────╯             ╰─────╯
                          Acme Health         GLEIF Root
                          (issues Patient     (issues Provider
                           Consent)            Authoriz.)
```

Compare to chain-of-authority (solid black arrow, `TEXT_SECONDARY`,
filled arrowhead, label pill at midpoint) and membership (dotted, no
arrowhead, no color signal). The three styles encode three orthogonal
relationships, each readable at a glance:

```
   chain-of-authority:   ───────────────▶   (solid, black, filled head)
   permitted-issues: ╲╲╲╲╲╲╲╲╲╲╲╲╲▷    (solid, teal, hollow head)
   membership (latent):  · · · · · · ·     (dotted, gray, no head)
```

### 2.4 Permitted-issuance subsumes membership

**Recommendation: drop membership edges entirely as a runtime concept.**

`MembershipEdge` was always a fallback for lacking per-schema
specificity (see the deferred block at `graph_view.py:518-531`). With
permitted-issuer edges available, all-pairs membership lines are
both noisier and *less informative* than what we can now draw. "This
AID is a member" is already communicated by the issuer node's mere
presence on the canvas — we don't need a second edge to assert it.

Concrete:
- Keep the `MembershipEdge` class (tested, working — don't delete).
- Do **not** instantiate it in `_build_scene`. Update the deferred-block
  comment to point at this design as the rationale.
- An isolated issuer (member but not permitted for anything) is
  fine; the side panel explains the role gap when the user selects it.
- "Member but unassigned" highlights, if ever needed, become a node
  badge — not a new edge type.

### 2.5 Density mitigations when issuance edges proliferate

Three mitigations against the "bottom-up forest of teal lines competing
with top-down chain-of-authority arrows" scenario:

1. **Z-order:** issuance at `setZValue(-1.5)` (between membership at -2
   and chain at -1). Chain edges always render on top.
2. **Default opacity 60%:** when nothing is selected, issuance edges
   are a softer underlay; chain-of-authority is the loud story.
   Hover/selection brings incident edges to 100% (per §2.2).
3. **Barycentric bottom-row reordering:** order the pinned issuer row
   by mean x of their permittedly-issued schemas — the same
   barycentric pass already used for inner Sugiyama layers. ~5 LOC in
   `layout.py`. Visual payoff is large: each issuer's edges rise
   mostly straight up, minimizing crossings without any new layout
   algorithm.

---

## Section 3 — Drag-to-create UX

### 3.1 The user's proposal, evaluated

The user asked: should the graph itself host a drag-to-draw affordance
that creates an permitted-issuer assignment? "Drag a line from
issuer to schema, drop, that's the new edge."

Two things are true at once:
1. Drag-to-create is the right *spatial* primitive for "I want to
   assert a relationship between these two things." It's the gesture
   that matches the resulting visual change. Cognitively coherent.
2. The List tab already has a working `+` affordance with a menu
   (`pages.py:2230-2242`). It's discoverable, accessible, keyboard-
   addressable, and works fine. Adding a second mechanism is real
   surface-area cost.

### 3.2 Recommendation: ship drag-to-create as the **graph view's
primary** mechanism; keep the List tab's `+` as the **List view's**
mechanism.

The two mechanisms aren't parallel — they live in different views of
the same data. The graph is for spatial work; the List is for tabular
work. Each view should have the affordance native to its mode. The
shared invariant is the underlying data: both call
`EcosystemBaser.add_permitted_issuer(eco, said, aid)` (db.py:262).
A user who creates a relationship in either view sees it instantly in
the other.

This is **not** "support both" punting. It's: drag-to-create is the
single primary mechanism *in the graph view*; the `+` chip is the
single primary mechanism *in the list view*. Neither mechanism appears
in the other view.

### 3.3 The drag interaction, in detail

**What triggers drag mode.** The graph already uses
`QGraphicsView.ScrollHandDrag` for pan (`graph_view.py:143`), so
unmodified left-drag on empty canvas is taken. The new gesture must
not conflict.

Recommendation: **drag from an issuer node** initiates issuance-edge
drawing. Because issuer nodes have `event.accept()` in their
`mousePressEvent` already (`graph_items.py:725-730`), pan never
triggers when the press lands on an issuer. We extend the press-to-
emit-clicked behavior into a press-and-move-then-release gesture:

- Press on issuer + immediate release (no movement) → click as today
  (selects, populates side panel).
- Press on issuer + move > 4px → enter draw mode, render rubber-band
  line from issuer's `top_anchor()` to current cursor.
- Release → if cursor is over a SchemaNode, commit; else cancel.

The 4px threshold is the standard Qt drag-distance (`QApplication
.startDragDistance()`). This means: if you click an issuer normally,
nothing changes — the drag only starts if you actually begin moving
the mouse. No modifier key, no mode toggle, no menu command.

Schema-to-issuer drag is **not** supported. Direction is fixed
(issuer → schema). This matches the data model (an issuer authorizes
itself to issue a schema; the schema is passive). It also avoids the
"which way does this edge mean" ambiguity that bidirectional drag
would force on the user.

**Visual feedback during drag.**

- A **rubber-band line** in the new permitted-issuer style
  (teal, 1.25px solid, hollow open arrowhead at the cursor end). Same
  visual idiom as the committed edge so the user sees what they're
  about to make.
- All schema nodes go into a **snap-target** state: schemas the
  issuer is *not yet permitted for* gain a 2px teal `dashed` ring
  pulse (subtle 1Hz alpha 60% ↔ 100%). Schemas the issuer **already**
  issues are dimmed to 40% opacity with a small "✓" badge in the
  top-right of the node — the snap to "already done" is a no-op, and
  the user should see that.
- Schemas with `ghost=True` (unresolved targets) are non-snappable —
  rendered with the standard non-snap opacity reduction. You can't
  permittedly-issue a schema that isn't even in the wallet.
- The cursor under drag is `Qt.CrossCursor` (a familiar "I'm drawing"
  affordance, not the pan hand or pointing-hand).

**Snap behavior on hover.** As the cursor enters a SchemaNode's
`shape()` during drag, the rubber-band's endpoint snaps to that
schema's `bottom_anchor()` and the schema's pulse-ring goes solid
teal. This gives the user a confident "yes, this is the target"
moment before they release.

**On release.**

- If the cursor is over an eligible (non-ghost, not-already-issued)
  schema → call `add_permitted_issuer(eco, said, aid)` immediately,
  no confirmation dialog. The action is reversible (see deletion
  below) and the user has had visual confirmation throughout the drag.
  Confirmations on reversible actions are friction.
- If the cursor is over an already-issued schema → no-op, brief
  toast: "Acme Health already issues Patient Consent in this
  ecosystem."
- If the cursor is over a ghost schema → no-op, brief toast: "Add this
  schema to your wallet first."
- If the cursor is over empty canvas or a non-schema item → cancel,
  rubber-band fades out over 120ms, no state change, no toast.

**How the user knows it worked.** The rubber-band morphs into the
committed edge in place (no flash, no animation) and the next render
of the side panel reflects the new data. The new edge inherits the
"selected schema" focus state if a schema is currently selected.

**Removing an edge.**

Three options were considered:

1. Drag the existing edge off into empty canvas. Discoverable in
   theory; easy to do by accident in practice (one stray drag deletes
   data). Reject.
2. Right-click the edge → context menu → "Remove permitted-
   issuance." Discoverable, low-risk. **Recommended.**
3. Click edge to select + Delete key. Works but requires the canvas
   to have first-class edge selection, which we don't have today
   (chain edges aren't selectable). Adding it just for this feels
   like over-investment.

**Recommendation: right-click context menu is the primary deletion
path on the canvas.** Single menu item: "Remove permitted-issuer
from <Issuer alias>." Deletion is immediate (no confirm), with a
reversible toast: "Removed. [Undo]" — toast lingers 6s, [Undo] calls
`add_permitted_issuer` to restore.

The chip's `×` button in the List tab and side panel remains — those
are the per-mode native deletion paths.

**Conflict reconciliation with existing canvas interactions.**

| Gesture | Today | After this change |
|---|---|---|
| Click empty canvas | Pan start (ScrollHandDrag) | Unchanged |
| Drag empty canvas | Pan | Unchanged |
| Click schema | Select | Unchanged |
| Drag from schema | Pan (event propagates) | Unchanged — schemas don't initiate draw |
| Click issuer | Select | Unchanged (drag distance < 4px) |
| Drag from issuer | Pan (event propagates) | **New: draw issuance edge** |
| Right-click anywhere | (no context menu today) | New: edge → "Remove"; node → existing context menu (redesign §5.6); empty → no-op for v1 |
| Ctrl+wheel | Zoom | Unchanged |

The only meaningful change to existing behavior is that dragging from
an issuer node no longer pans the canvas — it draws an edge. Since
issuer nodes are 56px circles in the bottom row, this is a small
fraction of the canvas's draggable surface; pan is still available
everywhere else. If a user wants to pan starting from over an issuer
node, they can pan from any nearby empty area.

### 3.4 Rejected alternatives

- **Bidirectional drag (schema → issuer too).** Two gestures for one
  operation = surface confusion. The data model is asymmetric (schemas
  have permitted *issuers*, not vice versa); pick one direction
  and let the gesture match the rendered edge direction.
- **Modifier-key gesture (Shift+drag from any node).** Undiscoverable.
  Press-on-issuer-then-drag is already unambiguous via the
  4px-threshold pattern users intuit from drag-to-rearrange UIs.
- **Mode toggle on the toolbar ("Edit relationships" button).** Adds
  two clicks per session and forces every other gesture to be
  re-disambiguated by mode. The whole pitch of the canvas affordance
  is *low-friction data entry*.

---

## Section 4 — What data does this need that doesn't exist yet?

### 4.1 The data model is sufficient as-is

`EcosystemRecord.permitted_issuers` (db.py:54) is exactly the
right shape: `dict[str, list[str]]` mapping `schema_said → [aid, …]`.
The four CRUD methods exist:

- `permitted_issuers_for(eco, schema_said)` (db.py:226)
- `set_permitted_issuers(eco, schema_said, aids)` (db.py:237)
- `add_permitted_issuer(eco, schema_said, aid)` (db.py:262)
- `remove_permitted_issuer(eco, schema_said, aid)` (db.py:270)

The graph view drag handler calls `add_permitted_issuer` directly
(via the existing `add_permitted_issuer_clicked` signal pattern
from `pages.py:1819`, plumbed through to the active page).

Validation already exists: `set_permitted_issuers` (db.py:249-254)
rejects AIDs not in `eco.issuer_aids`. The drag UX makes this
unreachable in practice (you can only drag from issuer nodes that
are already in the ecosystem), but the runtime check is the right
defense in depth.

### 4.2 Minor additions needed

- **Two new signals on `EcosystemGraphView`:**
  `add_permitted_issuer_requested(eco_name, schema_said, aid)` and
  `remove_permitted_issuer_requested(eco_name, schema_said, aid)`.
  Connect to the same `EcosystemDetailPage` slots that the List tab's
  chip signals already drive. Zero new business logic.
- **A `set_snap_target_state(state)` method on `IssuerNode` and
  `SchemaNode`,** with `state ∈ {"eligible","already","ineligible","off"}`.
  Touches `paint()` to overlay the pulse ring during drag. No other
  node-state changes; the rubber-band line itself is a temporary
  scene item, not a node concern.
- **No new `EcosystemBaser` methods.** Re-use existing CRUD.
- **No new `EcosystemRecord` fields.** Data model unchanged.

---

## Section 5 — Implementation hints (briefly)

This is **not** a code spec. The Qt patterns, with pitfalls.

### 5.1 Use scene mouse events, not Qt drag-and-drop

The user's proposal says "drag a line." That is **not** Qt's
`QDrag`/`QMimeData` framework — that framework is for inter-widget
clipboard-like data transport (drag a file from a file manager). What
we want is intra-scene mouse-event tracking, which is its own thing:

- On `IssuerNode.mousePressEvent`, record the press position and tell
  the scene "if movement exceeds 4px, start drawing."
- Override `EcosystemGraphView` (or its inner `_GraphView`)
  `mouseMoveEvent` to: detect the threshold crossing, create a
  `QGraphicsLineItem` at the issuer's `top_anchor()` reaching the
  current cursor scene position, redraw on every move.
- Override `mouseReleaseEvent` to commit or cancel.

Pitfall: `QGraphicsView` translates view coordinates → scene
coordinates via `mapToScene(event.position().toPoint())`. The
rubber-band line lives in scene coordinates; translate every cursor
position. Mixing view-coords and scene-coords is the easy way to make
the rubber-band drift away from the cursor.

Pitfall: Qt's `ScrollHandDrag` mode also reads mouse events. If our
override calls `super().mouseMoveEvent()` after we've started drawing,
the canvas pans simultaneously. Solution: when in drag-to-draw state,
return early from `mouseMoveEvent` after updating the line. Restore
super-delegation only when not drawing.

### 5.2 Snap-target detection on release

`QGraphicsScene.itemAt(scene_pos, transform)` returns the topmost item
at a scene point. Pitfall: if the rubber-band line is in the scene at
release time, `itemAt` may return *the rubber-band itself* because
it's the topmost item under the cursor. Two fixes (pick one):
- Set the rubber-band's `setAcceptedMouseButtons(Qt.NoButton)` and
  `setFlag(ItemIgnoresTransformations, False)` plus
  `setEnabled(False)` so it's ignored in hit tests. **Preferred.**
- Remove the rubber-band from the scene before calling `itemAt`. Works
  but is fiddlier and creates a single-frame visual gap.

### 5.3 The pulse-ring on snap-target schemas

Implement as a `QPropertyAnimation` on a custom `QObject` property
attached to each `SchemaNode`, animating an alpha float between 0.6
and 1.0 over 1000ms with `setLoopCount(-1)`, used in `paint()` to
modulate the ring's pen alpha. Standard Locksmith animation pattern
(redesign §6.7). Killed when snap state ends.

### 5.4 Right-click context menu for edge deletion

Override `EdgeIssuanceLine.contextMenuEvent(QGraphicsSceneContextMenuEvent)`.
Build a `QMenu` with one item; on triggered, emit a
`remove_requested` signal carrying `(issuer_aid, schema_said)`. The
view connects this to `remove_permitted_issuer_requested`.

The new edge subclass — call it `PermittedIssuerEdge` for parallelism with
`EdgeLine` and `MembershipEdge` — sits next to those in
`graph_items.py`. Constructor signature mirrors `MembershipEdge`:
`source: IssuerNode, target: SchemaNode`. Anchor logic is `source
.top_anchor()` → `target.bottom_anchor()`. The `paint()` differs from
`MembershipEdge`'s dotted style (use solid teal pen with hollow
arrowhead per §2.2 above).

### 5.5 Pitfalls to call out

- Don't override `keyPressEvent` for Delete-on-edges in v1; edge
  selection isn't a thing in this view yet. Right-click is enough.
- Don't animate the rubber-band → committed-edge transition. Just
  remove the rubber-band and add the `PermittedIssuerEdge`. Morph animation
  is busywork.
- Don't auto-relayout on edge creation. A relayout would jump every
  node, disorienting the user mid-thought. New edges just appear; the
  user hits [↺ relayout] when they want a clean canvas.

---

## Section 6 — Open questions

### 6.1 Should drag-to-create be available even before any permitted-issuer edges exist?

Yes. The empty-state hint (`graph_view.py:257-284`) currently treats
"members with no chain-of-authority" as a sparse case. It does not
mention permitted-issuer. Recommend adding a faint third hint
when `n_real_schemas >= 1 and n_issuers >= 1 and total_issuance_edges
== 0`: "Tip: drag from an issuer to a schema to mark them as the
permitted issuer in this ecosystem."

This is discoverability for the new gesture, not a blocking question
— the gesture works regardless of the hint.

### 6.2 Should the graph view ever show non-permitted issuance — i.e., "this AID has actually issued credentials of this schema in the wild" — as a separate edge style?

Tempting. The data exists in `vault.rgy` (TEL state). It would create
a third category of issuer-↔-schema relationship: permitted-only
(EGF says yes, no concrete issuance yet), permitted + actual (EGF
says yes, has issued at least one credential), and actual-only (has
issued credentials but EGF doesn't list them as permitted — the
verifier-relevant case for fraud detection).

**Recommendation: defer to a future stage.** This extension's job is
to surface the EGF permitted mapping. Actual-issuance overlays are
a separate feature with their own design discussion (and they belong
on the credential-detail page first, per lifecycle §5, before being
backported into the ecosystem graph). If we want a forward-pointer:
when actual-issuance lands, the visual treatment could be a small dot
or count badge near the issuance edge's midpoint, not a separate edge
— "permitted + actual" remains one relationship, not two.

### 6.3 Keyboard accessibility for drag-to-create

Drag is mouse-only. Keyboard-only and screen-reader users fall back
to the `+` chip in the side panel; that affordance should become
keyboard-reachable when schema-selection-via-keyboard lands as a
future feature. The accessibility gap predates this extension and is
not blocking.

### 6.4 Multi-select drag (one issuer → several schemas)

Tempting power-user feature; rejected for v1. Designing a clear
"intermediate vs commit" state for through-drag is hard, and iterating
single drags is fine at the scales we expect (<30 schemas/eco).

---

## Section 7 — Summary of recommended deltas

For the implementer, the concrete diff against the current codebase:

1. **`src/locksmith/plugins/ecosystem_viewer/graph_items.py`:** add
   an `PermittedIssuerEdge` class next to `EdgeLine` and `MembershipEdge`.
   Constructor takes `source: IssuerNode, target: SchemaNode`. Paints
   solid 1.25px teal `#0D9488` line, hollow open triangular arrowhead
   at target. `setZValue(-1.5)`. Implements `contextMenuEvent` for
   right-click "Remove permitted-issuer." Add `set_snap_target_state`
   methods on `IssuerNode` and `SchemaNode` for the during-drag visual.
2. **`src/locksmith/plugins/ecosystem_viewer/graph_view.py`:** in
   `_build_scene`, after step 7 (chain edges), add step 7b: build
   `PermittedIssuerEdge` instances from `eco.permitted_issuers`. Add
   bottom-row barycentric reordering input from permitted-issuer
   bipartite (§2.5 mitigation 3). Implement drag-to-create state
   machine in `_GraphView.mousePressEvent/mouseMoveEvent/
   mouseReleaseEvent`, gated on press landing on an `IssuerNode`. Add
   the two new signals (`add_permitted_issuer_requested`,
   `remove_permitted_issuer_requested`). Add the third empty-state
   hint per §6.1.
3. **`src/locksmith/plugins/ecosystem_viewer/pages.py`:** wire the new
   graph-view signals to the same handler slots that the List tab's
   chip signals already drive. Zero new handler code.
4. **`src/locksmith/plugins/ecosystem_viewer/layout.py`:** add an
   optional `bottom_row_ordering_edges` parameter to `LayoutOptions`
   (or a sibling) so `EcosystemGraphView` can pass permitted-
   issuance edges as the bipartite reordering input for the pinned
   bottom row. ~15 LOC.
5. **No asset commissioning needed.** The teal color and hollow
   arrowhead are painted directly in `paint()`. The pulse-ring uses
   `QPropertyAnimation` per redesign §6.7.
6. **No data-model changes.** `EcosystemRecord.permitted_issuers`
   is the right hook.

The implementation cost is real but contained: roughly 200-300 LOC
across the four files, no new dependencies, no schema migrations.
