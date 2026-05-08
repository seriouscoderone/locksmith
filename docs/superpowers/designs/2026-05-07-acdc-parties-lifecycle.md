# ACDC Parties & Lifecycle — Design Extension

Date: 2026-05-07
Status: Design vision (extends `2026-05-06-ecosystem-viewer-redesign.md`)
Audience: the implementer (a separate Qt/PySide6 engineer) and the product owner

This document extends the ecosystem-viewer redesign spec. It is **not** a
rewrite. Where the original doc covers visual vocabulary, page layouts,
graph design, or Qt facilities, this doc cross-references those sections
rather than restating them. References of the form "redesign §N" point at
`2026-05-06-ecosystem-viewer-redesign.md`. Spec citations (form: `spec
§N.M lines L-L'`) point at
`/Users/seriouscoderone/KERI/code/kswg-acdc-specification/spec/spec-body.md`.

---

## Section 1 — Goals & non-goals

### 1.1 The user-reported gap, restated

After phases A-D of the original redesign landed, the wallet's
developer/owner identified that the schema-detail page treats an ACDC
schema's *parties* as background detail. Specifically:

- **Issuer** (`i` at top level — spec §"Top-Level Fields" line 22; spec
  §"Autonomic IDentifier (AID) Fields" lines 93-95) is the AID making
  the claim. Required on every ACDC. The schema cannot constrain *who*
  the issuer is; that's an ecosystem-governance concern. But the fact
  that there *is always* an issuer, and that it carries cryptographic
  attribution, deserves first-class visual presence.

- **Issuee** (`i` inside `a` — spec §"Targeted Attribute Section" lines
  310-329) is the AID the credential is committed to. Present only for
  *targeted* ACDCs (spec §"Attribute Section Variants" lines 302-308).
  Untargeted ACDCs (spec §"Untargeted Attribute Section" lines 330-335)
  have no issuee. Surfaced today only by the targeting glyph (redesign
  §2.2), but the *role* of the issuee — "who is this credential about /
  for / to" — isn't given language.

- **Self-issued / self-attested** is the case where issuer and issuee
  resolve to the same AID (or, for an untargeted ACDC, where the issuer
  is making a claim about themselves). The spec doesn't reify this as a
  variant — it's an instance-level fact derivable by string-comparing
  `i` and `a.i`. But it has different trust semantics ("an attestation
  about oneself" vs "a credential bestowed by another"), and that
  difference matters for the user's mental model.

- **Registry-backed vs. registryless** (`rd` at top level — spec §"Registry
  SAID Field" lines 83-85; spec §"Transaction event logs (TELs) as ACDC
  state registries" lines 1914+) is orthogonal to issuer/issuee. A
  registry-backed credential has a TEL with revocable issuance state; a
  registryless credential is a one-shot anchored claim. Today the schema
  detail page mentions this in a developer-flavored "requires registry"
  row. The lifecycle implication ("can this be revoked?") is the
  user-facing question; the field name is the leak.

### 1.2 Goals

1. Give **issuer** and **issuee** first-class visual roles wherever a
   schema or credential is rendered, with a vocabulary that distinguishes
   them at a glance — same visual axis ("who"), different roles
   ("from whom" vs "to whom").

2. Surface **self-issued** as an instance-level badge on credential
   renderings, not on schema renderings. A schema *cannot* tell you
   whether instances will be self-issued — that's runtime data. Don't
   pretend otherwise.

3. Replace the developer-flavored registry row with a **lifecycle
   primitive** that says, in domain language, "this credential has a
   revocation surface" or "this credential cannot be revoked." The
   distinction is decision-relevant for verifiers; the field name is not.

4. Use the existing visual-vocabulary discipline (redesign §2): one
   channel per axis, no chip soup, glyphs that are recognizable at small
   sizes.

### 1.3 Non-goals

- **Not redesigning the at-a-glance card** (redesign §4.3). That card's
  job is the *intrinsic* schema axes: variant, targeting, disclosure,
  sections. Parties and lifecycle are a separate concern; they get
  their own card and their own header. (See §4.2 below for why a single
  unified "everything" card is wrong.)

- **Not building an issuer-detail page.** The original redesign §8.1
  raises this as an open question; it stays open. This extension only
  surfaces issuer/issuee *roles* on existing pages.

- **Not modeling the issuer's KEL state** in the schema detail page.
  That belongs on the issuer-detail page (see §7.3 below for the open
  question).

- **Not reifying "self-issued" as a schema-level concept.** It's an
  instance-level derived fact and we will not invent a schema flag for it.

- **Not exposing TEL message types or sealing semantics.** "Has a
  revocation surface" is the user-facing primitive; "this is a `rip`
  event sealed in a KEL at sn N" is developer-details territory.

---

## Section 2 — Spec-grounded definitions

For each of the four concepts, a precise restatement of what the spec
says, followed by an explicit note on what level (schema vs instance)
the concept lives at.

### 2.1 Issuer

**Spec definition.** Top-level `i` field (spec §"Top-Level Fields"
line 22). Required (line 36: "The following fields are REQUIRED `[v, d,
i, s]`"). Value is an AID — a self-certifying identifier whose key state
is established via KERI (spec §"Autonomic IDentifier (AID) Fields" lines
93-95). The issuer is the controller of that AID.

**Layer.** Both. The schema cannot know which AID will issue an instance,
so `ACDCSchemaInspection` has no `issuer` field — and shouldn't. A
specific instance (rendered by `ACDCInspection.issuer_aid`) names a
specific issuer AID. The *concept* of "every ACDC has an issuer" is
schema-relevant though: any rendering of a schema must communicate that
issued credentials will name an issuer, even if the specific identity is
unknown until an instance exists.

**Convention overlay.** None. "Issuer" is the spec's term (spec line
22, §"Targeted Attribute Section" lines 314, 318; throughout). We use
it verbatim.

### 2.2 Issuee

**Spec definition.** `i` field nested inside the attribute block `a` —
spec §"Targeted Attribute Section" lines 310-329. Presence makes the
ACDC *targeted* (spec §"Attribute Section Variants" lines 302-308).
Spec line 316: "the `i` field designates the Issuee AID, i.e., Target."
Spec line 318: "The ACDC MUST be 'issued by' an Issuer and MUST be
'issued to' an Issuee. This precise terminology does not bias or color
the role (function) an Issuee plays in using an ACDC."

Spec line 320: "the presence of an Issuee, `i`, field means that the
associated Issuee MAY make permitted verifiable presentations or
disclosures of the ACDC." Spec line 324: "the Issuer MAY use the ACDC
as a contractual vehicle for conveying authorization to the Issuee. This
enables verifiable delegation chains of authority because the Issuee in
one ACDC may become the Issuer of another ACDC."

**Layer.** Both, but with a critical distinction. The schema can require
that conforming instances be targeted (`requires_targeted` in
`ACDCSchemaInspection`), but it cannot name a specific issuee — that's
runtime. The schema-level fact is "instances will commit to an issuee
AID"; the instance-level fact is "this credential was issued to AID X."

**Convention overlay.** None on the term itself; "Issuee" is the spec's
term (spec lines 314, 316, 318, throughout). The spec acknowledges
synonyms (spec line 316: "an Issuee MAY be called the Holder; in others,
the Subject of the ACDC"). The redesign will stick with "Issuee" as the
canonical surface label, with "(holder)" as a parenthetical clarifier
in tooltips, because synonyms drift across ecosystems but "Issuee" is
spec-stable.

### 2.3 Self-issued / self-attested

**Spec definition.** *No spec primitive.* The spec does not define
"self-issued" as a distinct variant. It is derivable as an
instance-level equality:

- For a *targeted* ACDC: `instance.issuer_aid == instance.issuee_aid`
  (i.e., top-level `i` equals attribute-block `a.i`).
- For an *untargeted* ACDC: there is no issuee, so "self-issued" is
  better named **self-attestation**. Every untargeted ACDC is by
  construction a claim the issuer is making, possibly about themselves
  but more often about external state ("I, sensor-AID, observed
  temperature 42°C at time T"). Spec line 332-334 calls this an
  "undirected verifiable attestation or observation by the Issuer."

**Layer.** Instance-level only. Cannot be classified at the schema
level. `ACDCSchemaInspection` correctly omits this; `ACDCInspection`
*does not currently expose it* but should (see §3.5 — implementation
note). Adding a derived property `is_self_issued: bool` to
`ACDCInspection` is the right inspector change to drive the badge. The
inspector should also expose `is_self_attested: bool` for the
untargeted case (always true for untargeted, false otherwise) so the UI
can distinguish the two cases.

**Convention overlay.** Yes — the *names* "self-issued" and "self-
attested" are this wallet's framing. The spec talks about the equality
of two AID fields, not a labeled variant. We adopt these names because
they communicate the trust posture in plain English, and we mark them
as convention overlays in code comments per the README's spec-vs-
convention discipline.

### 2.4 Registry-backed vs registryless

**Spec definition.** Top-level `rd` field — spec §"Registry SAID Field"
lines 83-85. Optional (not in the required set on line 36). Value is the
SAID of a TEL's Registry-Inception event (spec §"Registry SAID, `rd`
field" lines 2017-2019). Spec line 2019: "The Registry SAID enables a
verifiable globally unique reference to the Registry (TEL). Update
events MUST include the Registry SAID, `rd` field so that they can be
verifiably associated with the Registry (TEL)."

The TEL provides revocation semantics (spec §"Verifiable Container/Credential
Registry" line 1950: "A Registry that tracks the dynamic issuance and
revocation state of an ACDC is called a Revocation Registry"). Without a
TEL anchor, the credential has no surface for state change after
issuance — it is a one-shot claim, valid as-issued.

Legacy keripy 1.3.4 still emits `ri`; the spec is `rd`. Inspector accepts
both (`inspector.py:295`).

**Layer.** Both. The schema can require `rd` (`requires_registry` in
`ACDCSchemaInspection`); an instance has a concrete `registry_said` (in
`ACDCInspection`). The *current* TEL state (issued / revoked / blinded)
is neither schema-level nor instance-static — it requires reading the
TEL itself, which is plugin-stage-7-or-8 work (see §5 below).

**Convention overlay.** Names yes, mechanism no. "Registry-backed"
versus "registryless" are friendlier than "has `rd` field" / "lacks
`rd` field" — the former is decision-relevant for a verifier
("could this be revoked?"), the latter is structural. We mark these
names as convention overlays.

---

## Section 3 — Visual vocabulary additions

These augment redesign §2. Do not introduce duplicate metaphors; where a
new concept overlaps an existing glyph (e.g., issuer sigil — redesign
§2.8), extend rather than replace.

### 3.1 Issuer vs. issuee — a single visual axis with two roles

Both issuer and issuee are AIDs. Both render as the §2.8 sigil-in-
circle node where they appear as nodes in a graph or contact card. Where
they appear *together* on the same surface (a credential rendering
showing "from X to Y"), they need to be visually distinguished as
*roles*, not as different node types.

**Recommendation: directional ribbon decoration.** A small triangular
ribbon attached to the bottom-left or bottom-right of the sigil circle:

- **Issuer (from):** ribbon on the bottom-right, pointing right
  (outflow direction). Color: same `TEXT_PRIMARY` neutral as the sigil
  outline (or `PRIMARY` orange if it's the user's own AID, per §2.8).
- **Issuee (to):** ribbon on the bottom-left, pointing left (inflow
  direction). Color: same neutral.

In layout terms, this means a self-issued credential's single AID
renders as a sigil-circle with **both ribbons attached** (an outflow on
the right and an inflow on the left, reading as "this AID points at
itself"). This visual encoding falls naturally out of the directional-
ribbon convention — see §3.3 for the dedicated self-issued treatment
that builds on it.

This is a deliberately small visual change. The existing sigil node
stays the same shape and size; a 6×8px ribbon is a side decoration that
reads at every zoom level the original node reads at. No new node type;
no shape-language fork between issuer and issuee circles.

```
   issuer          issuee          self-issued
   .──────.        .──────.        .──────.
   │  ✱   │        │  ✱   │        │  ✱   │
   '──────'─▷    ◁─'──────'      ◁─'──────'─▷
```

The ribbon is a **role decoration**, not part of the AID identity. This
keeps the underlying sigil-circle stable across all surfaces — when an
issuer appears on the overview's issuers column with no role context,
no ribbon. When the same AID appears on a credential card as the
issuer, the ribbon attaches.

### 3.2 Lifecycle: registry-backed vs registryless

This is the replacement for the v1 "Registry (rd/ri)" row. The visual
metaphor needs to convey *state-changeability* over time, not just
"has a TEL."

**Recommendation: a small clockface glyph.**

- **Registry-backed (revocable):** a clockface circle with a single
  hand at 12 o'clock. The hand suggests "this can move" — state can
  change after issuance. Color: teal `#0D9488` (matching the aggregate-
  section dot from redesign §2.4 and the v1 placeholder color, by
  symmetry — both are "this credential has more going on than meets the
  eye"). On hover/tooltip: "Revocable via TEL."
- **Registryless (one-shot):** an open-bottom circle (a circle with the
  bottom 90° arc removed) with a small dot in the center. Reads as
  "anchored point, no clockwork attached" — there is no machinery for
  later state change. Color: `TEXT_SECONDARY` neutral. Tooltip: "Cannot
  be revoked; valid as-issued."

The asymmetry in glyph weight is intentional: registry-backed has the
extra mechanism, registryless is the bare-anchored case. A user who
learns "more rings = more lifecycle machinery" reads the
revocability axis at a glance.

**Position.** Bottom-right corner of schema cards, *adjacent to* (not
replacing) the four-dot section fingerprint (§2.4). The section
fingerprint's 24×24 grid sits flush against the card's right edge; the
14px lifecycle glyph sits to its immediate left, with a 4px gap. On
graph-view schema nodes, same position. On the schema-detail hero
header (§4.2 below), 32px size next to the variant glyph.

### 3.3 Self-issued — instance-level only

Spec primitive: none. Convention: yes.

**Recommendation: a circular self-pointer arrow,** drawn as a small
loop badge that overlays the issuer-sigil node. Specifically: a 270°
arc from the bottom-right of the sigil circle, returning to the bottom-
left, with a small arrowhead at the return — the visual idiom of
"recursion" or "self-loop" from graph theory. Color: `PRIMARY` orange
when displayed (it always indicates the *user's own self-attestation*
when self-issued credentials originate from the user, but for non-self
self-issued credentials authored by other AIDs, color stays `TEXT_DARK`).

```
    ╭───╮
    │   │
   .─────.
   │  ✱  │
   '─────'──╯  self-issued: the loop returns to source
```

For self-attested *untargeted* credentials, there is no issuee node to
point back from, so the badge degrades to a small "≡" (identity)
overlay in the bottom-right of the issuer-sigil node, with tooltip:
"Self-attestation — the issuer is the only party named."

This badge appears **only in credential-instance renderings**
(stage-7-plus surface), never on schema cards. The schema cannot know
whether instances will be self-issued. If we ever reach a state where a
schema effectively *forces* self-issuance (e.g., it's targeted but the
ecosystem governance specifies the issuer must equal the issuee — an
EGF fact, not a schema fact), that's still ecosystem-governance-overlay
information, not schema-intrinsic, and would need a separate "EGF
overlay" badge — out of scope here.

### 3.4 Color and shape conventions, summarized

Adding to redesign §2:

| Axis | Channel | States | Notes |
|---|---|---|---|
| Issuer/issuee role | Ribbon position | from-right / to-left / both | New (§3.1). Role decoration on existing sigil-circle node. |
| Lifecycle | Glyph (clockface vs open-arc) | revocable / one-shot | New (§3.2). Color teal / neutral. |
| Self-issued | Loop overlay | present / absent | New (§3.3). Instance-level only. Color orange when self. |

No new color is introduced — the §3.2 teal already exists in the
redesign palette. No new shape-language for nodes — sigil-circle stays
the canonical AID node.

### 3.5 New SVG asset list (extending redesign §7)

Following redesign §7 conventions: SVG, 24×24 viewBox unless noted, 2px
stroke weight, re-tintable via `QPainter` SourceIn pattern.

| # | Name | Metaphor | Format / Size | Source | Notes |
|---|---|---|---|---|---|
| 7.23 | `lifecycle_revocable.svg` | Clockface, single hand at 12 | SVG 24×24 | New | §3.2 registry-backed lifecycle. Re-tints to teal `#0D9488`. |
| 7.24 | `lifecycle_oneshot.svg` | Open-bottom circle with center dot | SVG 24×24 | New | §3.2 registryless lifecycle. Re-tints to `TEXT_SECONDARY`. |
| 7.25 | `role_ribbon_from.svg` | Right-pointing 6×8 triangle | SVG 12×12 | New | §3.1 issuer-role decoration. |
| 7.26 | `role_ribbon_to.svg` | Left-pointing 6×8 triangle | SVG 12×12 | New | §3.1 issuee-role decoration. |
| 7.27 | `self_issued_loop.svg` | 270° arc with arrowhead returning to source | SVG 24×24 | New | §3.3 self-issued badge (instance-level). |
| 7.28 | `self_attested_identity.svg` | Identity glyph (≡) | SVG 16×16 | New | §3.3 fallback for untargeted self-attestation. |

**Estimated new SVG assets to commission: 6** (7.23-7.28). The role
ribbons (7.25, 7.26) are small enough they could be drawn directly in
`paint()` (no asset), but having them as SVG keeps the `acdc/icons.py`
catalog uniform with how role decorations are referenced from code.

Add the corresponding constants to `src/locksmith/acdc/icons.py`:

```python
# Lifecycle — registry-backed vs registryless (§3.2)
ICON_LIFECYCLE_REVOCABLE = ":/assets/material-icons/lifecycle_revocable.svg"
ICON_LIFECYCLE_ONESHOT = ":/assets/material-icons/lifecycle_oneshot.svg"

# AID role decorations (§3.1)
ICON_ROLE_RIBBON_FROM = ":/assets/material-icons/role_ribbon_from.svg"
ICON_ROLE_RIBBON_TO = ":/assets/material-icons/role_ribbon_to.svg"

# Self-issued / self-attested (§3.3) — instance-level
ICON_SELF_ISSUED_LOOP = ":/assets/material-icons/self_issued_loop.svg"
ICON_SELF_ATTESTED_IDENTITY = ":/assets/material-icons/self_attested_identity.svg"
```

Module docstrings should mark the self-* glyphs as **instance-level
only** so future developers don't paint them on schema cards.

---

## Section 4 — Where these surfaces appear

Page-by-page recommendations. Each subsection identifies what to add,
what to reshape, and what to leave alone.

### 4.1 Overview page (redesign §3)

**Schema cards (§3.2 of redesign).** Add the §3.2 lifecycle glyph next
to the four-dot section fingerprint in the bottom-right. Do *not* add
issuer-role decorations — the overview's schema cards are schema-level
and have no issuer context.

**Issuer cards (§3.2 of redesign).** No change. The issuer card already
shows the sigil-circle (redesign §2.8) and contextual stats (sn,
witnesses). Do *not* attach a from-ribbon: the overview's issuer column
is a directory of issuers, not a credential-flow context. Role
decorations are reserved for surfaces where the AID is presented *in a
role*.

**Ecosystem tiles (§3.2 of redesign).** No change. Tile counts ("5
schemas · 3 issuers") already say what's needed at this level.

### 4.2 Schema detail page (redesign §4)

This is the page where the v1 placeholder lives, and where the most
restructuring needs to happen. The parties and lifecycle deserve to be
*two separate cards*, not one combined card. Reasoning:

- **Parties** are about *who participates* in instances of this schema
  — issuer (always), issuee (if targeted). It's a "people" axis.
- **Lifecycle** is about *what can happen to instances over time* —
  revocable vs not. It's a "time" axis.

Conflating them (as the v1 "Parties & lifecycle" does) creates a card
that scans as "miscellaneous facts" rather than two coherent stories.
Splitting them gives each a focused header.

**Recommended order on the schema detail page** (from top to bottom):

1. Hero header (existing — redesign §4.2). Add lifecycle glyph next to
   the variant glyph at 32px (§3.2). The hero gets the *headline*
   posture: variant + lifecycle. No issuer/issuee here — those need
   their own card.
2. At-a-glance card (existing — redesign §4.3). No change — this is
   the intrinsic-shape card.
3. **NEW: Parties card** (replaces issuer/issuee rows of v1
   placeholder; see ASCII below).
4. **NEW: Lifecycle card** (replaces registry row of v1 placeholder).
5. Attributes card (existing). No change.
6. Chain of authority card (existing — redesign §4.4). No change.
7. My note card (existing — redesign §4.5). No change.

#### Parties card layout

```
┌─ Parties ────────────────────────────────────────────────────────┐
│                                                                  │
│  ╭───╮                          ╭───╮                            │
│  │ ✱ │─▷ Issuer                ◁│ ✱ │  Issuee                    │
│  ╰───╯                          ╰───╯                            │
│  Always present. Every          Required by this schema —        │
│  credential names a single      instances commit to a holder     │
│  issuer AID at top-level.       AID inside their attribute       │
│  This schema cannot constrain   block. Untargeted attestations   │
│  who that is — that's an        cannot conform.                  │
│  ecosystem-governance concern.                                   │
│                                                                  │
│  ⓘ When the issuer's AID equals the issuee's AID, the credential │
│    is **self-issued**. (See an actual credential to find out.)   │
└──────────────────────────────────────────────────────────────────┘
```

Two side-by-side columns, each headed by an AID-sigil glyph with the
appropriate role ribbon (§3.1). This is the schema-level surface, so
neither glyph names a specific AID — they are *role placeholders*. The
sigil interior is rendered with a faint hatched fill (~25% alpha) to
read as "stand-in for whoever fills this role in instances," visually
distinct from a concrete-AID sigil rendering.

If the schema is **untargeted** (`requires_targeted` is False), the
right column changes to:

```
│  ╭···╮                                                          │
│  ┊   ┊  No issuee                                               │
│  ╰···╯                                                          │
│  This schema declares no issuee — instances are untargeted      │
│  attestations from the issuer to the world ("to whom it may     │
│  concern"). Any verifier can read by SAID; no holder is bound.  │
```

(Dashed circle: "absent role.")

The footer line about self-issued is **always present on the schema
page** — it's a forward-pointing teaching note that explains a
concept the user will encounter when they later view an instance. It
does *not* claim that this schema's instances will be self-issued.

#### Lifecycle card layout

```
┌─ Lifecycle ──────────────────────────────────────────────────────┐
│                                                                  │
│  ◯  Revocable                                                    │
│      This schema requires registry anchoring (rd). Issued        │
│      credentials live in a TEL — the issuer can append a         │
│      revocation event to mark a specific credential revoked.     │
│      Verifiers should consult the TEL state, not just the SAID.  │
│                                                                  │
│  ⓘ Current TEL state is per-credential. The schema only          │
│    establishes that one exists.                                  │
└──────────────────────────────────────────────────────────────────┘
```

(Where ◯ is the §3.2 clockface glyph at 32px.)

Or, for registryless schemas:

```
┌─ Lifecycle ──────────────────────────────────────────────────────┐
│                                                                  │
│  ◔  One-shot                                                     │
│      No registry. Issued credentials are anchored once and       │
│      cannot be revoked. The issuer's signature commits to the    │
│      credential as-issued; verifiers trust it on its face.       │
│                                                                  │
│  ⓘ This is appropriate for non-revocable attestations (e.g., a   │
│    measurement, a transcript) but not for entitlements that      │
│    must support withdrawal.                                      │
└──────────────────────────────────────────────────────────────────┘
```

(Where ◔ is the §3.2 open-bottom circle.)

The lifecycle card is intentionally **single-row, single-fact**. There
is one decision-relevant piece of information per schema: revocable or
not. Padding the card with secondary detail dilutes the primitive.

#### Field-name leak removed

The v1 card had row labels like "Issuer (i)", "Issuee (a.i)",
"Registry (rd/ri)". Per redesign §1.1 ("domain language first"), these
labels should be banished from the default view. The new cards use no
field names. Field names appear in Developer details (redesign §4.6) —
add a line under the existing "Field-level structure" subsection that
spells out: "Issuer: top-level `i` (required). Issuee: nested `a.i`
(present iff schema requires targeting). Registry: top-level `rd`
(legacy `ri`)."

### 4.3 Ecosystem detail page — graph view (redesign §5)

**Side panel (redesign §5.6).** The v1 added a one-line lifecycle hint
("Lifecycle: registry-backed (revocable via TEL)"). Replace this with a
two-glyph row that follows the §3.2 vocabulary, drawn at 14px:

```
... existing classification glyph row (variant, targeting, disclosure)...
   ◯ revocable    [or]    ◔ one-shot
... existing edges sections, permitted issuers, ...
```

Same metaphor as the schema-detail lifecycle card, but at chip scale.
Tooltip restates the explanation. The text-heavy "Lifecycle:
registry-backed (revocable via TEL)" disappears in favor of the glyph;
the spec-leak word "TEL" only appears in tooltip-on-hover.

**Schema nodes on the canvas (redesign §5.3).** Add the §3.2 lifecycle
glyph at 12px in the bottom-left of the schema node, mirroring the
section fingerprint's bottom-right position. This makes a schema node
read in four corners:

- top-left: variant (open vs hatched circle, §2.1)
- top-right: SAID glyph (§2.7) + disclosure tier (§2.3)
- bottom-left: **lifecycle (NEW — §3.2)**
- bottom-right: section fingerprint (§2.4)

This is the edge of acceptable density on a 140×80 node — past 4
corners we'd need to grow nodes. But "is this revocable?" is one of the
core questions a verifier asks at glance, and it earns its corner.

**Issuer nodes on the canvas (redesign §5.3).** No role decorations
here. The graph-view *membership* edges (dotted lines, redesign §5.4)
between issuers and schemas already convey "this AID issues these
schemas." Adding from-ribbons would double-encode the same fact and
visually compete with the membership lines.

**Edges between schemas (redesign §5.5).** No change. Chain-of-
authority is its own axis with its own treatment (§2.5, §2.6).

### 4.4 Ecosystem detail page — list view (redesign §5.2)

When the user toggles to list mode, the rows for each schema should
include a small lifecycle column. A two-character cue (◯ or ◔) at the
right edge of each row, inline with the existing classification glyphs,
is sufficient. Tooltip on hover gives the explanation. Keep the v1
text-heavy "Lifecycle: registry-backed" out of the list view — it
breaks list-row rhythm.

---

## Section 5 — Credential-detail page (anticipated)

The plugin doesn't yet render individual credential instances (stages
7-8 territory). When that surface lands, it is the *primary venue* for
parties + lifecycle as concrete facts rather than schema-level
abstractions.

### 5.1 What changes from schema-detail to credential-detail

A schema-detail page renders abstract roles ("issuer will be present");
a credential-detail page renders concrete facts ("issuer is AID
EAcm…vK, alias 'Acme Health'"). This means:

- The Parties card on credential-detail shows two **specific** sigil-
  circles, each labeled with the AID's alias and truncated AID. The
  ribbons (§3.1) are present — left ribbon for issuee, right ribbon for
  issuer. Each is clickable, navigating to issuer-detail (or, in v1,
  the popover from redesign §8.1).
- For an **untargeted** instance, the right column is a single sigil-
  circle (issuer only) with from-ribbon, and the left column reads "No
  issuee — this is an attestation, not a credential to a holder."
- For a **self-issued** instance, both columns show the *same* AID, and
  the §3.3 self-issued loop badge overlays the layout (drawn between
  the two columns, as a recursive arrow connecting them). Header text:
  "Self-issued: the issuer is also the issuee. Treat as an attestation
  by this AID about itself."
- The Lifecycle card now has live state: "Revocable, currently issued"
  (status read from TEL — issued / revoked / blinded). Color the status
  cue green for issued, red for revoked, gray for blinded-state. The
  "currently issued" line is *the* user-facing answer to the question
  "is this credential still valid?"

### 5.2 ASCII mockup (credential-detail Parties + Lifecycle)

```
┌─ Parties ────────────────────────────────────────────────────────┐
│                                                                  │
│  ╭───╮                          ╭───╮                            │
│  │ ✱ │─▷ Acme Health           ◁│ ✱ │  jane.doe.medical          │
│  ╰───╯  EAcm…vK · sn 14         ╰───╯  EJa…dr · sn 3              │
│  Issuer                          Issuee                          │
│                                                                  │
│   [→ Open issuer]                 [→ Open issuee]                │
└──────────────────────────────────────────────────────────────────┘

┌─ Lifecycle ──────────────────────────────────────────────────────┐
│                                                                  │
│  ◯  Revocable · Currently issued                                 │
│      Anchored in TEL EReg…7A as of 2026-04-12. No revocation     │
│      event recorded. Last verified against the registry 2m ago.  │
│                                                                  │
│  [↻ Refresh status]                                              │
└──────────────────────────────────────────────────────────────────┘
```

(Self-issued case:)

```
┌─ Parties ────────────────────────────────────────────────────────┐
│                                                                  │
│           ╭───╮                                                   │
│         ╭─│ ✱ │─╮     Self-issued                                │
│         │ ╰───╯ │     Acme Health (EAcm…vK · sn 14) — this AID   │
│         ╰───◯───╯     attests this credential about itself.      │
│                                                                  │
│           [→ Open AID]                                            │
└──────────────────────────────────────────────────────────────────┘
```

(Single sigil with the §3.3 loop badge overlaid, no left/right
ribbons.)

### 5.3 Inspector requirements driven by this page

`ACDCInspection` should expose:

- `is_self_issued: bool` — True iff `is_targeted` and `issuer_aid ==
  issuee_aid`. Convention overlay; document as such in the dataclass
  docstring.
- `is_self_attested: bool` — True iff *not* `is_targeted` (every
  untargeted credential is by construction a self-attestation by its
  issuer). Convention overlay; same docstring discipline.

The TEL-state read ("currently issued / revoked / blinded") is *not* an
inspector concern; it requires reading the registry, which lives in
`vault.rgy.reger`. That belongs in a separate helper alongside the
credential-detail page implementation, with a clear interface like
`fetch_tel_state(rgy, registry_said) -> Literal["issued", "revoked",
"blinded", "unknown"]`. Keep the inspector pure-domain — schema and
field-map only.

---

## Section 6 — What the v1 placeholder gets wrong (or right)

Code reviewed: `_build_parties_lifecycle_card` in
`src/locksmith/plugins/ecosystem_viewer/pages.py:898-979`,
`_build_party_row` in `pages.py:981-1028`, and the lifecycle one-liner
in `src/locksmith/plugins/ecosystem_viewer/side_panel.py:223-236`.

### 6.1 What it gets right

- **Surfacing all three concepts at all** — issuer, issuee, registry —
  is the correct response to the user-reported gap. Pre-v1, none of
  these had a home on the schema-detail page.
- **The accent-bar-on-left treatment** in `_build_party_row` is a good
  pattern. It lets the eye scan rows quickly without the rows reading
  as their own cards. Reuse this pattern for the new Parties card's
  internal rows where applicable.
- **Color choice for revocable = teal `#0D9488`** matches the
  aggregate-section dot from redesign §2.4. That symmetry is good —
  teal is the wallet's "this credential has machinery you should look
  at" color. Keep it.
- **The side-panel one-line lifecycle hint** is the right *idea* — the
  graph view's side panel needs a lifecycle cue.

### 6.2 What it gets wrong

- **Field-name leakage in row labels.** "Issuer (i)", "Issuee (a.i)",
  "Registry (rd/ri)" violate redesign §1.1 ("Forbidden in this card:
  the strings `a`, `A`, `e`, `r`, `u`, `t`, `i`, `o`."). The
  parenthetical field names should disappear from the default view.
  See §4.2 above for the replacement.
- **Bundling issuer/issuee/registry into one card.** Parties (people
  axis) and lifecycle (time axis) are different stories. The card's
  title "Parties & lifecycle" already concedes the bundling — the user
  has to mentally split the card's contents into two narratives. Split
  the card.
- **No visual primitive for issuer or issuee.** The row labels are text
  only. This is the single biggest miss: redesign §2 establishes that
  axes get glyphs, not text labels. Adding the §3.1 sigil-circles with
  role ribbons gives parties the visual treatment the rest of the
  vocabulary already enjoys.
- **The "self-issued" concept is mentioned in the Issuee row's body
  copy but has no first-class treatment.** Self-issued is a critical
  trust-posture distinction; tucking it into a paragraph buries it.
  See §3.3 for the dedicated badge (instance-level only — the
  schema-detail mention is necessarily forward-looking).
- **The side-panel one-liner is text-heavy where the rest of the
  panel is glyph-heavy.** "Lifecycle: registry-backed (revocable via
  TEL)" reads as a different visual register than the existing
  classification glyph row above it. Replace with the §3.2 glyph row.
- **Registry row uses the parenthetical "(rd/ri)" — same field-leak
  problem.** Drop the parenthetical from the user-facing surface; keep
  it in Developer details only.

### 6.3 Net judgment

The v1 placeholder is the right *shape* of response (a card that
surfaces these concepts), at roughly the right *position* (between the
at-a-glance card and the chain-of-authority card). Its problems are
specific and fixable: split the card in two, replace text labels with
glyphs, defer field names to Developer details. These are the
right-iteration targets, not a re-think.

---

## Section 7 — Open questions

Genuine ambiguities not resolved above. Each routed with a
recommendation where one is available.

### 7.1 Should the schema-detail Parties card link to *known* issuers in this ecosystem?

The schema-detail page already has a chain-of-authority section
(redesign §4.4). It does not currently surface "known issuers of this
schema in this wallet." The graph view's side panel does (via the
Stage 9 "Permitted issuers" section).

Should the schema-detail Parties card include a section like "Known
issuers in your wallet: [Acme Health] [GLEIF Root]"?

**Recommendation:** yes, but as a small chip row at the bottom of the
Parties card, not as a separate card. The chips reuse the issuer-card
visual language (sigil-circle + alias). Each chip is clickable and
opens the issuer popover (per redesign §8.1). When there are no known
issuers, the row reads "No known issuers of this schema in your wallet
yet." This bridges the schema-detail to the ecosystem-graph "who
issues" question without requiring a separate page.

### 7.2 Should "self-attested" appear on the schema-detail page for untargeted schemas?

An untargeted schema's instances are by construction self-attestations.
This is a schema-level fact (untargeted ⇒ all instances are
self-attestations). Should the schema-detail Parties card mention it?

**Recommendation:** yes, but as a one-line annotation on the "No
issuee" column (see §4.2 above), not as a separate badge. The schema
*intrinsically* implies self-attestation; calling it a "badge" risks
over-claiming. The one-liner "instances are untargeted attestations
from the issuer to the world" already conveys it; expand to "...also
called self-attestations." The badge stays reserved for instance
renderings (§3.3, §5.1).

### 7.3 What's the right surface for issuer KEL state?

A credential's issuer has KEL state — sequence number, witnesses, key
state, recent rotations. The verifier might care about this. The
ecosystem-graph side panel shows some of it for issuer nodes (alias,
AID, sn). The schema-detail page does not. The credential-detail page
(stage 7+) will need to.

**Recommendation:** route via redesign §8.1's open question. When the
issuer-detail popover/page is built, it should be reachable from any
sigil-circle anywhere — the credential-detail Parties card, the
graph-view side panel, the ecosystem overview's issuer column. Make the
sigil-circle a uniformly clickable affordance (already a Qt
`PointingHandCursor` per redesign §3.4). KEL state belongs in the
issuer surface, not duplicated on every page that names an issuer.

### 7.4 Should current TEL state (issued vs revoked) appear on a *schema* card anywhere?

No — TEL state is per-credential. A schema-card can never know "is this
revoked," because schemas are pre-instance. Tempting to show "23 issued
/ 4 revoked" aggregates per schema, but that's a different feature
(aggregate analytics) and outside this design extension.

**Recommendation:** explicit no for v1 of this extension. The
credential-detail page (§5) is the right surface for TEL state. If
aggregate analytics arrive later, they belong on a new card, not on the
parties or lifecycle cards.

### 7.5 What's the shape of the inspector change?

§3.3 and §5.3 imply two new fields on `ACDCInspection`:

- `is_self_issued: bool`
- `is_self_attested: bool`

Both are derived; both are convention overlays. Should they live in the
inspector dataclass at all, or be computed at the call site?

**Recommendation:** put them on the dataclass. The pattern of the
existing inspector is to surface derived domain facts (is_private,
is_targeted, disclosure_tier are all derived) so consumers don't have
to re-derive. Adding the two self-* properties continues that pattern,
keeps the credential-detail UI free of derivation logic, and provides a
single tested place where the equality semantics of issuer-vs-issuee
AIDs lives.

The inspector docstring needs to clearly mark these as convention
overlays per the README's spec-vs-convention discipline.

### 7.6 Should "registryless = no revocation" be softened?

A pedantic verifier might note: even a registry-backed credential has
no revocation surface *until* a revocation event is appended; even a
registryless credential could in principle be invalidated by an
out-of-band ecosystem mechanism. Should the lifecycle card hedge?

**Recommendation:** no. The user-facing primitive is "is there any
mechanism by which this credential's state could change after
issuance?" — and registry presence is the only ACDC-spec primitive
that answers it. Out-of-band ecosystem mechanisms exist but are EGF
overlays, not ACDC primitives, and don't belong in the
parties+lifecycle vocabulary. Keep the language crisp.

### 7.7 How does this interact with the "delegated chains" semantics in spec line 324?

Spec line 324 notes that a targeted credential's issuee may become the
issuer of another credential — verifiable delegation chains. This is
fundamentally a *cross-credential* property (the chain spans two ACDCs)
and is captured by the chain-of-authority graph (redesign §4.4 / §5).
It is not a new role to surface in the Parties card.

**Recommendation:** no change. The chain-of-authority card already
visualizes delegation via DI2I edges and edge-group structure; the
Parties card's job is single-credential parties. Don't conflate the
single-credential and multi-credential views.

### 7.8 Should self-issued have its own color?

§3.3 proposes orange for self-issued credentials authored by the user,
neutral otherwise. But "the user's self-issued credential" is doubly
about the user (it's mine, and it's about me) — a stronger color
treatment might be warranted (e.g., a subtle background tint on the
whole credential card).

**Recommendation:** start with the badge-only treatment. If user
testing reveals self-issued credentials are hard to spot, escalate to a
faint background tint (4% `PRIMARY` orange) on the credential card's
header in v2. Avoid stacking color emphasis — the existing variant
glyph already carries color, the §3.1 ribbons may carry orange for
self-AIDs, and a third color cue risks chip-soup again.

---

## Section 8 — Summary of recommended deltas

For the implementer, the concrete diff against the current codebase:

1. **`src/locksmith/acdc/inspector.py`:** add `is_self_issued: bool`
   and `is_self_attested: bool` to `ACDCInspection` (frozen dataclass —
   add as new fields, populate in `inspect_acdc`). Document both as
   convention overlays.
2. **`src/locksmith/acdc/icons.py`:** add the six new constants from
   §3.5 (lifecycle revocable/oneshot, role ribbons from/to, self-issued
   loop, self-attested identity).
3. **Asset commissioning:** 6 new SVGs per §3.5 (7.23-7.28).
4. **`src/locksmith/plugins/ecosystem_viewer/pages.py`:** split the
   existing `_build_parties_lifecycle_card` into two methods:
   `_build_parties_card` (§4.2) and `_build_lifecycle_card` (§4.2).
   Drop the field-name parentheticals from row labels. Add the §3.1
   role-decorated sigil placeholders. Add the §7.1 known-issuers chip
   row at the bottom of the Parties card. Add the lifecycle glyph at
   32px to the schema-detail hero header next to the variant glyph.
5. **`src/locksmith/plugins/ecosystem_viewer/side_panel.py`:** replace
   the text-heavy `lifecycle_lbl` (lines 223-236) with a glyph cell
   using `ICON_LIFECYCLE_REVOCABLE` / `ICON_LIFECYCLE_ONESHOT` at
   14px, following the existing classification-glyph row's
   `_build_classification_row` pattern. Tooltip carries the prose.
6. **`src/locksmith/plugins/ecosystem_viewer/graph_items.py` (or
   wherever schema nodes are painted):** add the §3.2 lifecycle glyph
   in the schema node's bottom-left corner at 12px. This requires a
   `paint()` change per redesign §6.2.
7. **Developer details (redesign §4.6):** add a sentence under the
   Field-level structure subsection naming the field-letters of the
   parties and registry concepts (per §4.2 above).
8. **Forward to credential-detail (stage 7+):** the §5 mockup is the
   binding spec for that page's Parties and Lifecycle treatment when
   it's built. The inspector changes from item 1 are the prerequisites.
