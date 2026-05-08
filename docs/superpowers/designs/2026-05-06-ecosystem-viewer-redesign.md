# Ecosystem Viewer — Visual Redesign Spec

Date: 2026-05-06
Status: Design vision (pre-implementation)
Audience: the implementer (a separate Qt/PySide6 engineer) and the product owner

The product owner's brief in their own words:

> "I was hoping it would be more visually exciting or informative 'at a glance' using
> images/icons, space, lines, connections. I don't really want to see any of the
> single character elements, the UI should JUST focus on the DOMAIN of ACDCs and
> communicate things visually. I also envisioned more about the relationships at
> the ecosystem level in more of a graph or something."

This document is the design response to that brief. It is opinionated and committed
to a single direction. Where the ACDC spec
(`~/KERI/code/kswg-acdc-specification/spec/spec-body.md`) is the source of truth,
sections are cited inline. Where this document proposes a convention layer (e.g.
"ecosystem" itself is not a spec primitive), that is labeled as such.

The host platform is **PySide6 / Qt for Python** running as a desktop wallet —
not a browser. Every visual proposal here has been chosen so it can be implemented
with `QGraphicsView`, `QSvgRenderer`, `QPainter`, and Qt's built-in widget set.
No HTML/CSS, no DOM, no React.

---

## Section 1 — Design principles

These five principles govern every decision below. Each is decision-guiding, not a
platitude — when an implementer has a fork in the road, they should be able to
quote the principle that resolves it.

### 1.1 Domain language first; spec language is a developer affordance

A human looking at this UI should never see the strings `a`, `A`, `e`, `r`, `u`,
`o`, or `t` exposed as labels. Those are JSON field names from the ACDC spec
(`spec-body.md` §6 "Top-level fields"). They are a leak from the underlying serialization
into the human surface. The UI must talk in the spec's **conceptual** vocabulary
("attribute section", "edge", "nonce/private", "issuee"), and reserve the
field-letter vocabulary for a dedicated **Developer details** disclosure on each
detail page. Same content, different audiences, gated behind an explicit toggle.

Concrete consequence: rows like "yes · Targeted (a.i required)" do not appear in
the default view. They become "Targeted to a holder" with a small icon, no
field-name parenthetical. The field-name parenthetical only appears under
"Developer details".

### 1.2 Relationships are spatial, not textual

Chain-of-authority between schemas is the most distinctive thing about ACDCs
versus flat verifiable credentials. The spec models this as the `e` edges section
(spec §6.5). A list-of-text rendering of "edge `parent` → schema `EFm…2x`" buries
the structure that the spec is *trying* to make explicit. Therefore: edges
are rendered as drawn lines on a 2D canvas wherever space allows. Tabular
listings exist only as a fallback for screens that cannot accommodate a graph
(e.g. the schema-detail page can't host a full ecosystem graph, but it must
host a small per-schema "neighborhood" diagram of just that schema's edges).

### 1.3 Variant carries color; targeting carries silhouette; disclosure carries icon-fill

When a single artifact can be classified along several orthogonal axes, picking
*one channel per axis* keeps the encoding readable instead of a soup of badges.
This redesign uses three independent visual channels:

- **Color** = privacy variant (public vs private). Cool blue = public; deep
  indigo with a subtle hatch = private. (Color picks justified in §2.1.)
- **Silhouette / shape** = targeting (targeted vs untargeted). Targeted nodes
  have a notched right edge representing "delivered to someone"; untargeted
  nodes are flat-edged "broadcasts". Silhouette is preserved across all sizes
  including small chips.
- **Icon fill** = disclosure tier. An icon shaped like a stack of three
  rectangles ("layers"), with 1, 2, 3, or 4 layers filled to indicate metadata
  / partial / selective / full disclosure (spec §10).

Section presence (attribute / aggregate / edges / rules) is communicated by
**small corner glyphs** on schema cards, not by chips. Glyphs scale better than
text when ten schemas share a screen.

### 1.4 The graph is the ecosystem's primary representation

The ecosystem detail page opens to the graph view by default. A list/table view
is available as a secondary tab but is not the default. This is the inverse of
the current implementation. The product owner has explicitly asked for "more about
the relationships at the ecosystem level in more of a graph or something" — the
graph is not an alternative view; it is the page.

### 1.5 Restrained density — this is a focused desktop tool, not a marketing surface

The desktop wallet user is doing focused work: inspecting a schema before
accepting a presentation, mapping out who issues what in their ecosystem,
verifying chain-of-authority. They are not browsing for entertainment.
"Visually exciting" in this context means *legible at a glance and richly
informative*, not animated, not gradient-heavy, not maximalist. We use a
restrained palette (the existing `colors` module plus 3-4 domain-specific
accents), generous whitespace, and one strong typographic hierarchy per
page. Animation is reserved for state transitions (fading in a freshly-loaded
node) and graph layout — never for decoration.

---

## Section 2 — ACDC domain visual vocabulary

This section defines the visual atoms that recur across all three pages. The
implementer should produce these as a small reusable widget/icon library
(suggested location: `src/locksmith/plugins/ecosystem_viewer/visuals/`) so all
three pages render identical metaphors.

### 2.1 Variant: public vs private credential

Spec reference: §6.4 "Top-level UUID `u`". A private credential includes a
high-entropy nonce so that the SAID is not correlatable across presentations;
a public credential has no `u` field and its SAID alone identifies the content.

- **Icon concept.** A circle. Public: open circle, hairline stroke. Private:
  same circle filled with a fine diagonal hatch (representing entropy/noise).
  This metaphor reads as "transparent" vs "obscured" without being literal
  (no padlocks, which are already used elsewhere in Locksmith). A novice can
  understand "the cross-hatch one is the obscured/non-correlatable kind"
  without reading the label.
- **Color treatment.** Public = `#3B82F6` (existing `BLUE_ACCENT`). Private =
  `#312E81` (deep indigo — propose adding as `INDIGO_PRIVATE`). The privacy
  color is darker/heavier to convey "weighted, careful". The hatch fill uses
  the indigo at 40% alpha over white.
- **Position/shape.** Top-left corner of the schema node/card, 18px square.
  Always present (every ACDC has a privacy posture, even if implicit). Never
  appears as a chip — too important to be one chip among many.

### 2.2 Targeting: targeted vs untargeted

Spec reference: §6.6.1 "Issuee identifier in attribute section". A targeted
credential has `a.i` set to a specific issuee AID; an untargeted credential
omits issuee.

- **Icon concept.** Two small overlapping silhouettes for targeted (issuer
  + issuee, like a handoff). One silhouette for untargeted (issuer alone,
  broadcasting). This is the icon used in chips, tooltips, and badge form.
- **Color treatment.** No color signal here — targeting is encoded in shape.
  Both states are the same neutral `TEXT_DARK`.
- **Position/shape.** Encoded **into the schema-node silhouette itself** in
  the graph view: targeted schema nodes have a small triangular notch cut
  from the right edge (the "destination" pointer). Untargeted nodes are
  rounded rectangles with no notch. This is the most distinctive shape choice
  in the whole design — the notch is recognizable from across the screen at
  any zoom level. In list/card contexts where a notched silhouette is too
  fancy, the targeting state degrades to a 16px badge ("two silhouettes" vs
  "one silhouette") in the card header.

### 2.3 Disclosure tier: metadata / partial / selective / full

Spec reference: §10 "Graduated disclosure". A schema's possible disclosure
postures: metadata-only (just SAID / type), partial (some attributes redacted),
selective (uses the `A` aggregate section so individual attributes can be
disclosed independently), and full (everything).

- **Icon concept.** A 4-layer stack glyph — four small horizontal bars
  arranged like a ziggurat. The number of *filled* bars indicates the
  highest tier this schema supports:
  - 1 filled = metadata (lonely top bar)
  - 2 filled = partial
  - 3 filled = selective (only meaningful when `A` is declared)
  - 4 filled = full
  Selective has a special treatment: the third bar is split into 3 little
  segments to evoke "individually-disclosable", visually distinct from
  partial's solid bar.
- **Color treatment.** All bars in the same neutral `TEXT_DARK`. Filled bars
  are solid; unfilled bars are hairline outlines. No color encoding — color
  is reserved for variant.
- **Position/shape.** 14px-tall glyph, top-right corner of schema cards/nodes.
  Tooltip on hover spells out "Selective disclosure (uses aggregate section)".
  This is convention layered on the spec — the spec describes the *capabilities*,
  this glyph describes the *highest capability supported*.

### 2.4 Section presence: attribute / aggregate / edges / rules

Spec reference: §6.5 "Top-level sections `a`, `A`, `e`, `r`". These four sections
each carry semantic meaning independent of disclosure (rules section, for
example, indicates a Ricardian contract is part of the credential).

- **Icon concept.** A 2×2 mini-grid of small dots at the bottom-right of a
  schema node, one dot per section. Filled dot = section present; empty dot =
  section absent. The dots are positioned in a stable layout: top-left =
  attribute, top-right = aggregate, bottom-left = edges, bottom-right = rules.
  This means a glance at the dot pattern reads as a quick fingerprint of "what
  shape of credential this is".
- **Color treatment.** Each filled dot uses a different domain hue:
  - attribute = neutral `TEXT_PRIMARY` (the default, the "body")
  - aggregate = teal (propose `#0D9488`, "selective-disclosure capable")
  - edges = orange `PRIMARY` (chain-of-authority is a Locksmith primary feature)
  - rules = warning yellow `WARNING_YELLOW` (Ricardian contract — read it!)
  The yellow for rules acts as a "watch out, this credential carries terms"
  signal.
- **Position/shape.** A 24×24 region in the bottom-right of the schema node
  with the four dots laid out in a fixed grid. Stable position and color
  means a user learns to read the fingerprint quickly: "filled top-left and
  bottom-left" = "attribute + edges" = "a chained targeted ACDC".

### 2.5 Edge operators (chain-of-authority): I2I / NI2I / DI2I / NOT

Spec reference: §6.5.3 "Edges section, unary operator `o`". I2I (default for
targeted credentials) = issuer-of-this must be the issuee-of-the-edge-target.
NI2I = relaxed (issuer-of-this need not match). DI2I = delegated. NOT = inverted.

These are properties of an *edge* (a line in the graph), not of a node.

- **Icon concept.** All edges are arrows pointing from the chained-from
  schema to the chained-to schema. Operator is encoded in **the line itself**:
  - **I2I** (default targeted): solid line, single arrowhead. This is the
    "you'd expect this" visual — solid and unadorned.
  - **NI2I**: solid line, but with a small hollow circle at the source end
    (read as "loose coupling at the issuer end"). Single arrowhead.
  - **DI2I**: dashed line with a single arrowhead. Dashes evoke delegation
    ("via an intermediary"). Spec calls out delegated chains as a special
    case worth flagging.
  - **NOT**: solid line with a small "Ø" symbol mid-line and a hollow
    arrowhead. The Ø is borrowed from set-theory "negation". The hollow
    arrowhead reinforces that the relationship is inverted.
- **Color treatment.** All edge operators draw in the same neutral edge color
  (`TEXT_PRIMARY`) by default. On hover, the hovered edge brightens to
  `PRIMARY` orange. NOT edges always carry a subtle red tint
  (`#991B1B` at 30% alpha) to signal "this is a negation, look twice".
- **Position/shape.** Edge labels (the field name like `parent`) appear at
  the line's midpoint in a small "tag" pill. Operator is implied by line
  treatment. Hover shows full tooltip: "I2I — issuer of this credential
  must be the issuee of `parent`".

### 2.6 Edge-group operators: AND / OR / NAND / NOR / AVG / WAVG

Spec reference: §6.5.3 "Edges section, m-ary operator `o`". When multiple
edges in an edges section participate in a group, the m-ary operator
combines them.

- **Icon concept.** When two or more edges share a group, they emerge from
  a small **junction node** drawn as a tiny labeled hexagon on the source
  schema's outline. The junction's label is the operator name (`AND`, `OR`,
  `NAND`, `NOR`, `AVG`, `WAVG`). All edges in the group originate from this
  junction.
- **Color treatment.** AND junctions are `TEXT_PRIMARY` (the default).
  OR junctions are teal (matching the aggregate dot — "selectivity"-flavored).
  NAND/NOR junctions inherit the red tint from §2.5 NOT (negation).
  AVG/WAVG are a desaturated purple (`#6D5DDB`) — these are statistical
  combinators, semantically distinct from the boolean ones.
- **Position/shape.** 12px hexagon with the operator letters inside, attached
  flush to the source schema's notched edge. Single-edge groups don't render
  a junction (the implicit AND of one is just a line).

### 2.7 Schema identity (SAID)

- **Icon concept.** A small "fingerprint dot" — three concentric arcs (like
  the iOS Touch-ID-glyph reduced to a rangefinder). This signals "content
  hash / unique fingerprint". Used wherever a SAID is shown without elision.
- **Color treatment.** Neutral `TEXT_SECONDARY`. SAIDs themselves render in
  monospace, truncated to 12 chars + ellipsis, with a click-to-copy button
  that briefly flashes green on success.
- **Position/shape.** 12px glyph immediately preceding any SAID rendering,
  always paired with the truncated SAID text.

### 2.8 Issuer AID and KEL state

- **Icon concept.** Issuer AIDs render as **circular nodes** in the graph
  (intentionally shape-distinct from schemas, which are notched/flat
  rectangles). Inside the circle: a small KERI-flavored sigil — an asterisk
  drawn from rotated line segments, suggestive of the multi-key signing
  threshold. A small numeric badge in the bottom-right shows the AID's
  current sequence number.
- **Color treatment.** Transferable AIDs render with `TEXT_PRIMARY` outline
  (full agency, can rotate). Non-transferable AIDs (witness-shaped) render
  with a dashed `TEXT_SECONDARY` outline (limited agency). If the AID is one
  of *the user's own*, the inner sigil is `PRIMARY` orange — instantly
  recognizable as "me / mine" on the graph.
- **Position/shape.** 56px circle in the graph view (versus the schema
  rectangle at ~140px wide × 80px tall — schemas are bigger because they
  carry more info, AIDs are simpler). On hover: a tooltip with alias,
  full AID, sn, witness count, TOAD.

---

## Section 3 — Overview page mockup

The overview page is what the user sees when they navigate to the plugin.
The redesign treats it as a **personal map of what this wallet has
discovered** — three layers of artifacts, each with a distinct visual
personality, with the user's own ecosystems leading.

### 3.1 Layout: top-down hero + two-column index

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Ecosystem Viewer                                                            │
│  Your map of schemas, issuers, and the credentials that flow between them.   │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─ MY ECOSYSTEMS ──────────────────────────────────────── [+ New eco… ]──┐  │
│  │                                                                        │  │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐         │  │
│  │  │ ◆  Acme Health  │  │ ◆  GLEIF vLEI   │  │ + Define a new  │         │  │
│  │  │    5 schemas    │  │    2 schemas    │  │   ecosystem     │         │  │
│  │  │    3 issuers    │  │    7 issuers    │  │                 │         │  │
│  │  │  ┌──┬──┬──┐ +2  │  │  ┌──┬──┐        │  │                 │         │  │
│  │  │  │  │  │  │     │  │  │  │  │        │  │                 │         │  │
│  │  │  └──┴──┴──┘     │  │  └──┴──┘        │  │                 │         │  │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘         │  │
│  │                                                                        │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌─ KNOWN SCHEMAS ─────────────────┐ ┌─ KNOWN ISSUERS ──────────────────┐    │
│  │ search…                         │ │ search…                          │    │
│  │                                 │ │                                  │    │
│  │ ┌─ Patient Consent ──── ▥ ─┐    │ │ ╭─ Acme Health Provider ──╮      │    │
│  │ │ v1 · Patient Consent…   │    │ │ │ ✱  EOP_…vK    sn 14      │      │    │
│  │ │ ◐ targeted │ ▤ partial  │    │ │ │ 3 wits · me-known        │      │    │
│  │ │ ●○○● a · e              │    │ │ ╰──────────────────────────╯      │    │
│  │ └─────────────────────────┘    │ │                                  │    │
│  │                                 │ │ ╭─ GLEIF Root ─────────────╮     │    │
│  │ ┌─ Lab Order ────────── ▥ ─┐    │ │ │ ✱  EBA…rZ    sn  8       │     │    │
│  │ │ v2 · Lab Order …        │    │ │ │ 5 wits                   │     │    │
│  │ │ ◑ private  │ ▤ partial  │    │ │ ╰──────────────────────────╯     │    │
│  │ │ ●●○● a · A · r          │    │ │                                  │    │
│  │ └─────────────────────────┘    │ │                                  │    │
│  └─────────────────────────────────┘ └──────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────────┘
```

The layout has three vertically-stacked regions:

1. **Hero ribbon: My ecosystems.** Horizontal scrolling row of ecosystem
   tiles plus a "create" tile at the end. Ecosystems are first-class because
   they are the user's own organizing artifact. Each tile shows the ecosystem
   name, member counts, and a tiny **constellation preview** — the bottom 3
   rows of the tile contain miniature schema-shape thumbnails arranged in
   their actual graph positions, capped at 6 visible with "+N" overflow.
   Hovering animates a faint pulse on the thumbnails. Clicking opens the
   ecosystem detail page (which opens to the graph view).

2. **Two-column index.** Below the ecosystems ribbon, a 50/50 split:
   - Left column: known schemas as compact cards (each ~180×88px), one card
     per row, scrollable.
   - Right column: known issuer AIDs as compact "contact tile" cards.

   The two columns are visually distinct *by shape language*: schema cards
   are rectangular with sharp corners and the §2 dot/glyph fingerprint;
   issuer cards are rounded with a circular avatar (the §2.8 sigil) on
   the left.

### 3.2 Card visual specifications

**Ecosystem tile (240×180px):**

- Top-left: a 16px diamond glyph (◆) in `PRIMARY` orange. This is the
  ecosystem icon — diamond for "user-defined collection".
- Title: ecosystem name, `TEXT_PRIMARY`, 16px, weight 600.
- Counts: "5 schemas · 3 issuers" in `TEXT_SECONDARY`, 12px.
- Bottom: a constellation preview — a small QGraphicsView (read-only,
  no pan/zoom, no interaction) showing up to 6 schema thumbnails (28px
  rounded notched rectangles, no inner detail) laid out using the same
  algorithm as the full graph (§5.3). If there are more than 6, a "+N"
  badge floats over the last visible thumbnail.
- Hover: the constellation pulses (faint scale 1.0→1.04→1.0 over 600ms,
  ease-in-out, looped while hovered). Card border lightens to `BLUE_BORDER`.
- Click: navigate to ecosystem detail page (graph view).

**Schema card (full row width × 88px):**

- Top-left: §2.1 variant glyph (open or hatched circle).
- Title: schema title, 14px, weight 600.
- Subtitle: schema version + credentialType, 12px, `TEXT_SECONDARY`.
- Below subtitle: §2.2 targeting badge (one or two silhouettes) +
  §2.3 disclosure-tier glyph + §2.4 four-dot section fingerprint, on
  one row, all 14px.
- Top-right: §2.7 SAID-fingerprint glyph + truncated SAID + copy button.
- Hover: card background shifts to `BACKGROUND_TABLE_ROW_HOVER`.
- Click: navigate to schema detail page.

**Issuer card (full column width × 76px):**

- Left: 48px §2.8 issuer-AID circle with sigil.
- Right: alias (14px weight 600), AID truncated (12px monospace),
  one-line stats: "sn 14 · 3 witnesses · transferable" in 11px
  `TEXT_SECONDARY`.
- Right-edge: small chevron `>` to indicate clickable (future: opens
  contact detail; for now no-op or shows the same data in an expanded
  popover — TBD, see §8).

### 3.3 Empty states

- **No vault open:** the hero ribbon shows a single full-width tile
  reading "Unlock a vault to see your map." No schemas/issuers section.
- **Vault open but no schemas:** schemas column shows an illustrated empty
  state — a faint dotted outline of a generic schema card with text:
  "No schemas yet. Add one via Credentials → Schemas → Add."
- **Vault open but no ecosystems:** the only tile in the hero ribbon is
  the "+ Define a new ecosystem" tile, which expands to fill more of
  the ribbon and gains a sentence of explainer text: "Group schemas and
  issuers that work together — your private trust map."
- **Vault open but no issuers:** issuers column shows the analogous
  illustrated empty state.

### 3.4 Hover and click affordances

All clickable surfaces show `Qt.PointingHandCursor`. Hovered cards animate
their background change in 120ms ease-out (Qt
`QPropertyAnimation` on a `QColor`-backed property of the card's
background palette). Hovering a schema card highlights any ecosystem
tiles that contain that schema with a 2px `BLUE_BORDER` ring — a
"reverse correlation" affordance the current UI lacks.

---

## Section 4 — Schema detail page mockup

The schema detail page is where the spec-field-name leakage is currently worst.
The redesign banishes those names from the default view entirely.

### 4.1 Layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  ‹ Back to overview                                              ⚙ Developer │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │  ◐                                                                   │    │
│  │      Patient Consent  v1                                             │    │
│  │      Records a patient's consent to release medical info.            │    │
│  │                                                                      │    │
│  │      ◷ EHsx…m1Y                  [copy]                              │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─ At a glance ───────────────────────────────────────────────────────┐     │
│  │                                                                     │     │
│  │   ◐  Private          ◐  Targeted to a holder                       │     │
│  │      Non-correlatable    Commits to a specific issuee AID           │     │
│  │                                                                     │     │
│  │   ▥  Partial disclosure       ●○○●  Attribute + edges                │     │
│  │      Some attributes redactable   No aggregate; no rules            │     │
│  │                                                                     │     │
│  └─────────────────────────────────────────────────────────────────────┘     │
│                                                                              │
│  ┌─ Chain of authority ─────────────────────────────────────────────────┐    │
│  │                                                                      │    │
│  │      ┌──────────────┐                ┌──────────────┐                │    │
│  │      │              │   parent       │              │                │    │
│  │      │ Patient      ├───────────────▶│ Provider     │                │    │
│  │      │ Consent     ◁│   I2I (default)│ Authoriz.    │                │    │
│  │      │              │                │              │                │    │
│  │      └──────────────┘                └──────────────┘                │    │
│  │                                            │                         │    │
│  │                                            │ chartered_by            │    │
│  │                                            │ DI2I (delegated)        │    │
│  │                                            ▼ (dashed)                │    │
│  │                                      ┌──────────────┐                │    │
│  │                                      │ State        │                │    │
│  │                                      │ License      │                │    │
│  │                                      │              │                │    │
│  │                                      └──────────────┘                │    │
│  │                                                                      │    │
│  │   This schema requires 1 incoming edge (`parent`) and 1 outgoing.    │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─ My note ────────────────────────────────────────────[ Edit annotation ]┐ │
│  │ "Used by Acme Health for patient onboarding. Issued by their main      │ │
│  │  AID per the BAA we signed in Q1."                                     │ │
│  │                                                                        │ │
│  │ Tags: [ acme ] [ patient-flow ] [ onboarded ]                          │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ▼ Developer details (raw schema, field-level structure, JSON)               │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Hero header

A full-width white card. Left side: the §2.1 variant glyph rendered at
56px (large — it's the credential's identity color/posture). Right side:

- Title (32px weight 600), version (16px `TEXT_SECONDARY`).
- One-line description (14px, `TEXT_DARK`).
- §2.7 SAID glyph + truncated SAID + copy button, 12px monospace.

No spec field names. No "credentialType: …" prefix. The rendered title
*is* the credential type.

### 4.3 "At a glance" classification card

A 2×2 grid of icon-and-label pairs. Each pair is rendered with:

- Left: 32px icon from §2 (variant, targeting, disclosure tier, sections fingerprint).
- Right: a primary label (14px weight 600) + secondary explanatory line
  (12px `TEXT_SECONDARY`).

Forbidden in this card: the strings `a`, `A`, `e`, `r`, `u`, `t`, `i`,
`o`. Forbidden phrases: "(a.i required)", "(u required)", "yes", "no".

What replaces "yes/no" rows: a primary statement plus context.
"Targeted to a holder / Commits to a specific issuee AID" is the
replacement for "yes · Targeted (a.i required)". The `a.i` field
reference appears only under Developer details.

### 4.4 "Chain of authority" mini-graph

A small `QGraphicsView` (height ~280px, full card width) showing this
schema as a notched node, plus its declared edge targets as adjacent
notched nodes. Edges drawn with the §2.5 line treatments and §2.6
junctions. Edge labels rendered in the small pill at the line's midpoint.

If no edges declared: the card is replaced with an "Untethered" callout —
"This schema declares no edges to other schemas. It stands alone."

If one or more edge targets are *not in the wallet*, those nodes render
as ghost outlines with a small `?` glyph. Tooltip: "Schema not yet
imported into this wallet."

Click any other-schema node: navigate to that schema's detail page.

### 4.5 "My note" annotation card

The user's annotation surfaces prominently — same visual weight as
the at-a-glance card. If empty, the card shows "Add a note about how
you use this schema" with an inviting placeholder treatment (no italic
"(no note yet)" — that reads as a bug). The "Edit annotation" button
is in the card's top-right, inline with the title.

Tags render as small pill chips, `BACKGROUND_SELECTION` background.

### 4.6 Developer details disclosure

Collapsed by default. Header: a single line `▼ Developer details
(raw schema, field-level structure, JSON)`. Clicking expands an inline
section with three sub-sections:

1. **Field-level structure.** This is where the original "Required ACDC
   variant" / "Declared sections" / "Edge requirements" tables live, with
   their full single-letter spec field names visible. Same data as
   today's `_build_requirements_section`, `_build_sections_section`,
   `_build_edges_section` — just hidden from the default view.
2. **Raw SAID / version / credentialType.** Full-length unredacted SAID,
   schema version, credentialType identifier.
3. **Raw JSON.** The existing `QPlainTextEdit` block.

Toggle: a separate global "Developer mode" toggle is also available in
the page's top-right (next to the Back link), which when on, expands
this disclosure on every detail page automatically. Setting persisted
in `LocksmithConfig.plugin_configs[plugin_id]["developer_mode"]`.

---

## Section 5 — Ecosystem detail page + the graph view

This is the flagship of the redesign and the product owner's headline ask.

### 5.1 Layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  ‹ Back to overview                                          ⚙ Developer    │
├──────────────────────────────────────────────────────────────────────────────┤
│  ◆  Acme Health Ecosystem                                                    │
│     Schemas + issuers used by Acme Health partners                          │
│                                                                              │
│  [ Graph ]  [ List ]                                          [ + Add… ]    │
├──────────────────────────────────────────────────────────────────────────────┤
│ ┌────────────────────────────────────────────────────────────┐ ┌──────────┐ │
│ │                                                            │ │ DETAILS  │ │
│ │                       ┌──────────┐                         │ │          │ │
│ │                       │ State    │                         │ │ Selected:│ │
│ │                       │ License  │ ◐ private               │ │          │ │
│ │                       └────┬─────┘ ▤ partial               │ │ Patient  │ │
│ │                            │                               │ │ Consent  │ │
│ │                            │ chartered_by                  │ │          │ │
│ │                            │ DI2I (dashed)                 │ │ v1       │ │
│ │                            ▼                               │ │          │ │
│ │                       ┌──────────┐                         │ │ ◐ priv   │ │
│ │                ┌──────│ Provider │──────┐                  │ │ ◷ targ   │ │
│ │                │      │ Auth.    │      │                  │ │ ▥ part   │ │
│ │                │      └────┬─────┘      │                  │ │          │ │
│ │                │ parent    │ owns       │                  │ │ Issued  │ │
│ │                │           │            │                  │ │ by:     │ │
│ │                ▼           ▼            ▼                  │ │ ✱ Acme  │ │
│ │          ┌──────────┐  ┌──────────┐ ┌──────────┐           │ │  Health │ │
│ │          │ Patient  │  │ Lab      │ │ Rx       │           │ │         │ │
│ │          │ Consent ◁│  │ Order   ◁│ │ Order   ◁│           │ │         │ │
│ │          └──────────┘  └──────────┘ └──────────┘           │ │ [Open  ]│ │
│ │              │                                             │ │ [detail]│ │
│ │              │ issued_to (untargeted edge — rare)          │ └──────────┘ │
│ │              ▼                                             │              │
│ │             ✱ Patient (issuer)                              │             │
│ │                                                            │              │
│ │                                                            │              │
│ │  ⓘ 5 schemas · 4 chain-edges · 1 unresolved target          │             │
│ │  [+] [-]  100%  [⊞ fit]  [↺ relayout]                       │             │
│ └────────────────────────────────────────────────────────────┘              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 The two view modes

A tabbed control near the top: **Graph** (default) and **List**.

**Graph** is the new flagship. **List** is the today-style list of
schema/AID members, retained for accessibility, copy-paste workflows,
and large ecosystems where the graph becomes too dense.

### 5.3 Graph node design

**Schema nodes.** ~140×80px notched rounded rectangle (notch on right
edge if §2.2 targeted; flat right if untargeted). Inside:

- Top row: title (13px weight 600, single line, ellipsis) + version.
- Middle row: §2.1 variant glyph + §2.3 disclosure-tier glyph.
- Bottom-right: §2.4 four-dot section fingerprint.
- Top-right: §2.7 small SAID glyph (no SAID text in the node — too small
  for legibility; SAID shown in the side panel on selection).

Schema nodes use `WHITE` fill, 1.5px `BORDER` stroke. Selected: 2.5px
`BLUE_SELECTION` stroke + faint `BLUE_SELECTION_BG` fill. Hovered:
1.5px `PRIMARY` stroke. The selected/hover is mutually exclusive with
selection — selection persists across hover.

**Issuer AID nodes.** 56px circle (per §2.8). Inside: KERI sigil glyph,
small alias label below the circle (13px, single line, ellipsis at
~14 chars). On the bottom-right of the circle: a tiny "sn N" badge.
A user's own AID has the orange `PRIMARY` sigil (per §2.8).

The visual contrast between schemas (notched rectangles, ~140px wide)
and issuers (~56px circles) is intentional and load-bearing for the
"glance" requirement: you can tell at a distance whether a node is a
schema or an issuer by shape alone.

### 5.4 Graph edge design

Edges between schemas are drawn per §2.5 (operator → line treatment).
Edge groups use §2.6 junctions. Edges between schemas and issuers are
**dotted**, never solid — they are not chain-of-authority but membership
("this issuer is part of this ecosystem and issues credentials of these
schemas if known"). Membership edges are drawn lightly so they don't
dominate the chain-of-authority story.

If two schemas have edges in both directions (rare but possible in
recursive structures), draw two parallel curved arcs rather than
overlapping straight lines.

### 5.5 Layout algorithm — primary: hierarchical

**Recommended:** Sugiyama-style layered (hierarchical) layout, top-to-bottom
or left-to-right (orientation: top-to-bottom by default, configurable).
The reason: chain-of-authority is fundamentally a directed acyclic
relationship in well-formed ecosystems. Chartering authorities (root-of-trust
schemas) belong at the top; downstream operational credentials belong
toward the bottom. Sugiyama makes this readable.

Implementation: pure-Python topological sort + greedy per-layer ordering
(minimize crossings via barycentric reordering for one or two passes).
This is ~150 lines of plain Python — no graphviz dependency required.
A `dataclasses.dataclass`-based intermediate representation feeds both
the layout pass and the QGraphicsScene placement.

If the ecosystem's edge graph contains cycles (unlikely but legal), the
layout breaks the cycle by treating the longest back-edge as a "feedback"
edge and routes it as a curved up-arrow rendered with a slight red tint.

**Secondary mode:** force-directed (spring-embedder). Toggleable via the
[↺ relayout] button's right-click menu. Useful for non-hierarchical
exploration ("which clusters are dense"). Not the default.

**Tertiary mode (future):** user-arranged. Drag a node, lock its position,
persist coordinates in `EcosystemBaser`. Out of scope for v1; called out
in §8.

Issuer AID nodes are placed in their own row at the very bottom of the
hierarchical layout (or right edge if left-to-right), connected by
dotted membership edges to the schemas they issue.

### 5.6 Interaction model

- **Pan:** click-and-drag empty canvas; or use Qt's built-in
  `QGraphicsView` drag mode `ScrollHandDrag`.
- **Zoom:** Ctrl+wheel (or pinch on trackpad). Range 25%–400%. Show
  current zoom % in the bottom toolbar.
- **Fit:** [⊞ fit] button auto-zooms to bounding rect of all nodes
  with 40px padding.
- **Hover a node:** node lifts (1px `PRIMARY` stroke, drop-shadow at 4px),
  tooltip with full title + truncated SAID (for schemas) or alias + AID
  (for issuers). Tooltip is a `QGraphicsTextItem` painted on top, not
  Qt's native tooltip — gives consistent styling.
- **Hover an edge:** edge brightens to `PRIMARY`; small tooltip near
  cursor explains the operator: "DI2I — delegated chain (issuer of
  this credential's chain proceeds through a delegated AID)".
- **Click a node:** select it; right-side details panel slides in
  showing the node's full info (title, description, SAID with copy,
  the §2 classification icons large, list of incoming/outgoing edges
  with click-throughs to those schemas, list of known issuers of this
  schema in this ecosystem, "Open detail" button to navigate to the
  schema detail page).
- **Double-click a node:** navigate directly to its detail page (same
  as overview-card behavior).
- **Right-click a node:** context menu — "Open detail page", "Copy SAID",
  "Remove from ecosystem", "Annotate" (calls `edit_annotation_clicked`).
- **Click empty canvas:** deselect; details panel collapses.

### 5.7 Information density

**On the node face by default:**
- Schema: title, version, variant glyph, disclosure-tier glyph, section
  fingerprint, small SAID glyph.
- Issuer: sigil, alias, sn badge.

**On hover (additive):**
- Tooltip with full title + truncated SAID (schema) or full alias + AID
  (issuer).

**On selection (in side panel):**
- Full title, description, full SAID with copy button.
- Each §2 classification rendered at large size with explanatory text
  (same content as schema-detail "At a glance" card, condensed).
- Outgoing/incoming edges as a small ordered list, each with operator
  treatment indicator and click-to-navigate.
- Issuer AIDs known to issue this schema, as small avatar-and-alias rows.
- Annotation snippet (first 200 chars).
- "Open full detail page" button.

Selection panel slides in from the right at ~280px wide. Slide animation
180ms, ease-out. Panel can be pinned (then graph canvas shrinks) or
floating (overlays right edge of canvas with translucent backdrop).
Default: floating.

### 5.8 Bottom canvas toolbar

- ⓘ stats line: "5 schemas · 4 chain-edges · 1 unresolved target"
- [+] / [-] zoom buttons (also Ctrl+wheel)
- "100%" zoom percentage label (click to reset to 100%)
- [⊞ fit] fit-to-content
- [↺ relayout] re-run layout (preserves manual locks if any; right-click
  for layout-mode chooser: hierarchical vs force-directed)

### 5.9 Empty/sparse states

- **Ecosystem with zero members:** the graph canvas shows an illustrated
  "Drop members in to start mapping" empty state — a faint dotted outline
  of where a schema node would go, and a centered call-to-action button
  "Add your first schema or issuer".
- **Ecosystem with one member:** the single node centers on the canvas
  at 100% zoom. A muted explanatory line below the node: "This ecosystem
  has only one member. Add more to see chain-of-authority."
- **Ecosystem with members but zero edges between them:** all nodes are
  laid out in a flat horizontal/vertical row (one rank in the Sugiyama
  layout collapses to flat). A muted line: "These members declare no
  chain-of-authority between each other. Their relationships are flat."
- **Ecosystem with edges to schemas not in the wallet:** out-of-wallet
  schemas render as ghost nodes (dashed outline, 50% opacity, no internal
  glyphs, just title + "?"). Stats line counts them as "N unresolved
  target(s)" — clicking an unresolved node shows a popover with the SAID
  and "Add this schema to your wallet" CTA.

---

## Section 6 — Implementation hints for the Qt implementer

For each visual feature, the Qt facility that delivers it.

### 6.1 Icons (§2.1, §2.2, §2.3, §2.4, §2.7, §2.8)

- **`QSvgRenderer`** or **`QSvgWidget`** for icon assets. Custom SVG
  files added to `assets/material-icons/` (or a new
  `assets/ecosystem-viewer/` subdir to namespace plugin assets). Icons
  re-tinted at runtime by rendering the SVG to a `QPixmap` and using
  `QPainter.setCompositionMode(CompositionMode_SourceIn)` over a
  filled rectangle in the desired color — standard Locksmith pattern.
- For the §2.4 four-dot section fingerprint: don't ship as SVG; draw
  with `QPainter` directly in the schema-card/-node `paintEvent` /
  `paint()` so the dot states can be computed from the inspection
  data per-render without proliferating SVG variants.
- The §2.1 cross-hatch fill for private credentials: implement as a
  reusable `QBrush` with `Qt.BDiagPattern` or
  `Qt.FDiagPattern` over a base color — much cheaper than an SVG.

### 6.2 The graph canvas (§5)

- **`QGraphicsView` + `QGraphicsScene`.** The view is embedded in
  the EcosystemDetailPage's central widget. Drag mode
  `QGraphicsView.ScrollHandDrag` for pan; override
  `wheelEvent` for Ctrl+wheel zoom (transform via
  `scale(factor, factor)`).
- **Schema nodes: subclass `QGraphicsObject`** (not `QGraphicsItem`) so
  they can emit signals (clicked, hover-entered) cleanly. Implement
  `boundingRect()` and `paint(QPainter, QStyleOptionGraphicsItem, QWidget)`.
  The notched-rectangle path is built once per node from a
  `QPainterPath` (rounded rect with a triangular notch on the right)
  and reused on every paint.
- **Issuer nodes: subclass `QGraphicsObject`**, simpler `paint()` —
  draw the circle + sigil + sn badge.
- **Edges: subclass `QGraphicsPathItem`** (or `QGraphicsObject`-with-
  manual-path for hover signals). The path is a `QPainterPath` with a
  cubic Bézier curve from source-edge to target-edge for non-orthogonal
  edges, or a routed orthogonal path for cleaner Sugiyama layouts.
  Arrowhead is drawn in `paint()` by computing the tangent at the path's
  end point and drawing a small triangle / hollow triangle / Ø symbol
  per operator (§2.5).
- **Selection rendering** is built into `QGraphicsItem` —
  `setFlag(ItemIsSelectable)` + override `paint()` to check
  `option->state & QStyle::State_Selected`.
- **Tooltips** on graph nodes: don't use Qt's tooltip system (timing
  is uncontrollable). Instead, hover-track in `hoverEnterEvent` and
  add a `QGraphicsTextItem` to the scene at cursor position, remove it
  on `hoverLeaveEvent`. This gives full styling control.

### 6.3 Layout algorithm (§5.5)

- **Sugiyama implementation as a small Python helper** in
  `src/locksmith/plugins/ecosystem_viewer/layout.py`. Layers from
  `graphlib.TopologicalSorter` (stdlib). Per-layer ordering: barycentric
  reordering (compute average rank of each node's neighbors in the
  adjacent layer, sort by that, two passes). No external dependency.
- Force-directed mode: 100-iteration Fruchterman-Reingold in pure
  Python, called only when toggled. Acceptable performance up to
  ~200 nodes per ecosystem (we don't expect bigger).

### 6.4 Side details panel (§5.6)

- A `QWidget` child of `EcosystemDetailPage`, positioned via
  `QHBoxLayout` to the right of the QGraphicsView.
- Slide animation: `QPropertyAnimation` on the panel's `maximumWidth`
  property, 180ms, `QEasingCurve.OutCubic`. When collapsed, width is 0;
  when open, width is 280px.
- Inside the panel: a `QScrollArea` wrapping a vertically-stacked layout
  of the same atom widgets used in §4 (variant glyph + label, etc.) —
  reuse, don't redesign.

### 6.5 Card-based pages (§3, §4)

- All cards: `QFrame` with `setObjectName(...)` and a stylesheet target
  via `QFrame#objectName { ... }`. Avoid stylesheet inheritance to child
  `QLabel`s — set background `transparent` on labels in the same rule.
- Schema-card paint of the four-dot fingerprint: subclass `QFrame`
  (e.g. `SchemaCardWidget`), override `paintEvent`, and in addition to
  whatever the stylesheet renders, draw the four dots with `QPainter`
  in the `paintEvent` using event coordinates.

### 6.6 Stylesheets

- Use Qt stylesheets for **colors, borders, border-radii, padding** only.
- Do **not** use stylesheets for layout (positioning of children).
  Layouts are always `QHBoxLayout` / `QVBoxLayout` / `QGridLayout`.
- Hover rules via `:hover` pseudo-selector are fine for cards.
- Selected/active rules via `:focus` / object-property-based selectors
  work but are finicky — for graph items, do this in `paint()` not
  stylesheet.

### 6.7 Animations (§3.4, §5.6)

- All animations: `QPropertyAnimation`. Targets:
  - Card hover bg color: animate the background-role color via a
    custom `QObject` property + `QPropertyAnimation`.
  - Constellation pulse: animate a `scale` property on the constellation
    `QGraphicsView`'s transform, looped via `setLoopCount(-1)` while
    hovered, killed on leave.
  - Slide-in panel: `QPropertyAnimation` on `maximumWidth`.
- No animations on graph layout transitions in v1 — nodes snap to new
  positions on relayout. Animated relayout is a v2 polish item (§8).

### 6.8 Developer-mode toggle persistence (§4.6)

- The plugin reads/writes its own block of
  `LocksmithConfig.plugin_configs[plugin_id]`. Toggle changes are
  persisted via the standard config save path. The toggle widget is
  a `LocksmithToggle` from `ui/toolkit/widgets/toggle.py`.

### 6.9 Things explicitly NOT to do

- Do not use `QWebEngineView` to render any of this. Adding Chromium to
  a Qt desktop wallet is overkill, ships ~150MB extra, and breaks code
  signing on macOS notarization. Everything here is implementable with
  native Qt drawing.
- Do not use a third-party graph-layout library that ships its own
  binary (graphviz, OGDF, etc.). The hand-rolled Sugiyama is small
  enough to maintain in-tree.
- Do not introduce a new icon set if existing `material-icons` covers
  the metaphor. Section 7 audits the mapping.

---

## Section 7 — Iconography asset list

Format for all: **SVG**, 24×24 viewBox by default (re-tintable with the
existing `QPainter` SourceIn pattern), with a few exceptions noted as
"painted, not SVG" — those are drawn directly in `paint()` because they
encode runtime data.

| # | Name | Metaphor | Format / Size | Source | Notes |
|---|---|---|---|---|---|
| 7.1 | `privacy_public.svg` | Open thin-stroke circle | SVG 24×24 | New | §2.1 public variant glyph. |
| 7.2 | `privacy_private.svg` | Hatched-fill circle (diagonal lines) | SVG 24×24 | New | §2.1 private variant glyph. Hatch pattern as path lines, not as stroke pattern, so re-tinting works. |
| 7.3 | `targeting_targeted.svg` | Two overlapping silhouettes | SVG 24×24 | New | §2.2 targeted badge. |
| 7.4 | `targeting_untargeted.svg` | One silhouette, broadcasting waves | SVG 24×24 | New | §2.2 untargeted badge. |
| 7.5 | `disclosure_tier.svg` | 4-bar ziggurat with 1/2/3/4 bars filled | Painted, not SVG | New helper widget | §2.3. Renders dynamically from inspection data; not an SVG. Subclass `QWidget` with custom paint, expose `tier: int` property. |
| 7.6 | `section_fingerprint.svg` | 2×2 dot grid | Painted, not SVG | New helper widget | §2.4. Same rationale as 7.5 — runtime data. |
| 7.7 | `said_fingerprint.svg` | Three concentric arcs (rangefinder) | SVG 16×16 | New | §2.7. |
| 7.8 | `issuer_sigil.svg` | KERI sigil — 6-spoke asterisk | SVG 24×24 | New | §2.8. Inner glyph for issuer-AID circles. Re-tints to PRIMARY orange for self-AIDs. |
| 7.9 | `ecosystem_diamond.svg` | Filled diamond (◆) | SVG 24×24 | New (or reuse `hive.svg`?) | §3.2 ecosystem-tile glyph. Could reuse existing `hive.svg` as an alternative — both convey "collection". Recommend evaluating both. |
| 7.10 | `op_i2i_arrow.svg` | Solid arrowhead | Painted in QGraphicsPathItem | n/a | §2.5. Drawn in `paint()`, not asset. |
| 7.11 | `op_di2i_dash.svg` | Dashed line + solid arrowhead | Painted | n/a | §2.5. `QPen` with `Qt.DashLine`. |
| 7.12 | `op_not_negation.svg` | Ø symbol overlay | Painted | n/a | §2.5. Paint Ø at line midpoint. |
| 7.13 | `junction_and.svg` | "AND" hexagon | Painted | n/a | §2.6. |
| 7.14 | `junction_or.svg` | "OR" hexagon (teal) | Painted | n/a | §2.6. |
| 7.15 | (etc. NAND, NOR, AVG, WAVG) | Operator hexagons | Painted | n/a | §2.6. All painted, sharing one template. |
| 7.16 | `developer_mode.svg` | Cog/wrench (settings) | Reuse `tune.svg` | Existing | §4.6 developer-mode toggle. |
| 7.17 | `copy.svg` | Copy-to-clipboard | Reuse `content_copy.svg` | Existing | SAID copy buttons. |
| 7.18 | `back_arrow.svg` | Left chevron | Reuse `chevron_left.svg` | Existing | Page back button. |
| 7.19 | `add_plus.svg` | Plus | Reuse `add.svg` | Existing | New ecosystem CTA. |
| 7.20 | `fit_to_content.svg` | Fit-frame icon | New | New | §5.8 graph toolbar [⊞ fit]. |
| 7.21 | `relayout.svg` | Curved-arrow refresh | Reuse `refresh.svg` | Existing | §5.8 graph toolbar [↺]. |
| 7.22 | `unresolved.svg` | "?" inside dashed circle | New | New | §5.9 ghost-node inner glyph. |

Estimated **new** SVG assets to commission: **9** (7.1–7.4, 7.7, 7.8, 7.9, 7.20, 7.22).
The runtime-painted glyphs (7.5, 7.6, 7.10–7.15) are implementer work,
not asset-design work.

For visual consistency: all new SVG icons should be drawn at 2px stroke
weight on a 24×24 viewBox with a 2px inner padding, centered, no fill
unless stated. This matches the existing `material-icons` family.

---

## Section 8 — Open questions

Genuine ambiguities the design did not resolve. Each requires either a
product-owner decision or an implementer judgment call.

### 8.1 Should the issuer card on the overview be clickable?

The current implementation has no issuer-detail page. The redesign's
issuer cards have a chevron `>` implying clickability, but where do they
go? Options:

- A new "Issuer detail" page in this plugin showing the AID's KEL summary
  (sn, witness list, key state, recent rotations) plus the schemas they
  are known to issue in this wallet.
- A deep-link to the existing wallet Contacts page for that AID.
- No-op for v1 — chevron removed.

**Recommendation:** v1 = a small popover (not a full page) on click,
showing alias, AID, sn, witnesses, ecosystems they're a member of.
Full issuer-detail page deferred.

### 8.2 Persistent node positions in the graph?

The Sugiyama layout is recomputed on every render. If a user finds the
auto-layout unsatisfactory, they currently have no escape. Should v1
allow drag-to-rearrange with persistence?

**Recommendation for product owner:** v1 ships with auto-only layout.
Persisted manual layout deferred to v2. Justification: persistence
schema in `EcosystemBaser` has to be designed; cycle-breaking and merge
behavior on new nodes is non-trivial.

### 8.3 Filtering and search in the graph?

Big ecosystems will have many nodes. Should the graph view support a
search box that highlights matches and dims non-matches? Or filter by
section/variant/tier?

**Recommendation:** v1 ships with a search box in the graph toolbar
(highlight-only, no filtering). Faceted filtering deferred. Search
input is a simple text-match against schema title and AID alias.

### 8.4 Ecosystem-level annotations?

Schema annotations exist (§4.5). Issuer annotations exist in the inspector
data model. Ecosystem-level annotations don't yet — should they? An
ecosystem note on the detail page would round out the annotation story.

**Recommendation:** yes, add an "About this ecosystem" annotation card
next to the graph (in the same right-side area, below the selection
panel when not selecting). Reuse the existing annotation flow.

### 8.5 Exporting the graph?

A power user might want to export the ecosystem graph as a PNG/SVG to
share in a doc. Easy with `QGraphicsScene.render(QPainter)`. In scope
for v1?

**Recommendation:** out of scope for v1. Easy to add later
(estimated <50 LOC); not on the critical path for the redesign.

### 8.6 What happens when the same SAID appears in multiple ecosystems?

A schema can be a member of multiple user-defined ecosystems (it's just
a `(name, said)` tuple in `EcosystemBaser`). The overview hover-correlation
in §3.4 highlights *all* matching ecosystems — but in the schema detail
page, should we show which ecosystems this schema participates in?

**Recommendation:** yes, add a small "In ecosystems: [Acme] [GLEIF]"
chip row at the bottom of the schema-detail header. Each chip clicks
through to that ecosystem's graph view, with the current schema
auto-selected.

### 8.7 Color accessibility?

The §2 design uses color to convey privacy variant, edge-operator junctions,
section dot colors. We have not validated against color-blindness
(deuteranopia/protanopia/tritanopia). The dual-channel design (color +
shape/icon) means none of the encodings are *only* color — the variant
glyph is also shape-different (open vs hatched), the section fingerprint
positions are stable so a user can read by position not color, edge
operators are line-treatment-different not color-different. So the
design should degrade gracefully. But: confirm with a product-owner
review against simulated color-blind palettes before shipping.

### 8.8 Density vs whitespace tuning

The mockups specify 14px / 12px type sizes and ~140×80 schema nodes.
On a 13" laptop screen at 1440×900 effective resolution, this fits
comfortably; on a 27" 4K external monitor, the design might feel too
small. v1 ships at the values stated; v2 could add a "compact / cozy /
roomy" density preference mirroring other Locksmith tooling. Out of
scope for the redesign decision.
