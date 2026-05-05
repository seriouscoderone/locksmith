# -*- encoding: utf-8 -*-
"""
locksmith.acdc.inspector module

Read-side domain classification for ACDCs and ACDC schemas. Takes a parsed
field map (dict) and returns dataclasses describing the credential at the
ACDC spec's domain layer.

Spec primitives surfaced here (each citation against ACDC spec body):

- Top-level field set: [v, t, d, u, i, rd, s, a, A, e, r] in order;
  required: [v, d, i, s]; `a` and `A` are mutually exclusive
- Variants: public vs private (governed by presence of `u` UUID/nonce field)
- Targeting: targeted ACDC has issuee AID committed in `a.i`; untargeted
  ACDCs have no issuee binding
- Per-section forms: compact (replaced by section's SAID string) vs full
  (in-line block content, with its own `d` SAID)
- Graduated disclosure tiers: metadata < partial < selective < full
- Edges: object in `e` block where `n` field is present; targets a
  chained credential. Unary operator `o` may be I2I (default for
  targeted), NI2I, DI2I, or NOT
- Edge-groups: object in `e` block where `n` is absent; contains nested
  edges/groups. M-ary operator may be AND (default), OR, NAND, NOR,
  AVG, WAVG
- Rules: each rule block REQUIRES an `l` (legal language) field

Convention overlay (clearly distinguished where present):
- `disclosure_tier` is a derived single-name classification synthesized
  from per-section forms; the spec defines the underlying mechanism but
  doesn't assign a single label per ACDC
- `is_private` / `is_public` is named by us; the spec talks about the
  presence/absence of `u` directly. Same fact, different vocabulary
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

SectionForm = Literal["compact", "full", "absent"]
"""Per-section presentation form. `compact` means the section is just the
SAID string referencing the block; `full` means the inline block content."""

DisclosureTier = Literal["metadata", "partial", "selective", "full"]
"""Graduated disclosure tier (per ACDC spec disclosure model).

- metadata: only top-level identity fields; no section content
- partial: some sections fully disclosed, others compact
- selective: aggregate `A` section present (individual attribute disclosure)
- full: every section disclosed in full form
"""

EdgeOperator = Literal["I2I", "NI2I", "DI2I", "NOT"]
"""Unary edge operators per ACDC spec. I2I is default for targeted ACDCs."""

EdgeGroupOperator = Literal["AND", "OR", "NAND", "NOR", "AVG", "WAVG"]
"""M-ary edge-group operators per ACDC spec. AND is default."""


# ---------------------------------------------------------------------------
# Inspection result for a single ACDC instance
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EdgeInspection:
    """A single edge or edge-group within an ACDC's `e` section.

    Spec discriminator: an edge MUST have an `n` field; an edge-group
    MUST NOT. Edge-groups contain nested edges/groups in their own
    properties.
    """
    name: str
    is_edge: bool
    """True if this is an edge (has `n`); False if edge-group."""

    # Edge fields (when is_edge=True)
    target_said: str | None = None
    """The chained credential's SAID — `n` field. Required for edges."""
    target_schema_said: str | None = None
    """The chained credential's schema SAID — `s` field. Required for edges."""
    operator: str | None = None
    """The unary `o` operator, if explicitly set. None means default I2I
    applies for targeted ACDCs."""

    # Edge-group fields (when is_edge=False)
    group_operator: str | None = None
    """The m-ary group operator. None means default AND applies."""
    nested: tuple[EdgeInspection, ...] = ()
    """Nested edges and edge-groups within this edge-group."""


@dataclass(frozen=True)
class RuleInspection:
    """A single rule block within an ACDC's `r` section.

    Spec invariant: every rule block REQUIRES an `l` (legal language)
    field. Inspector flags absence so callers can surface schema bugs.
    """
    name: str
    has_legal_language: bool
    legal_language: str | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class SectionsPresent:
    """Per-section presence + form for an ACDC instance."""
    attribute: SectionForm    # `a` field
    aggregate: SectionForm    # `A` field (mutually exclusive with attribute)
    edges: SectionForm        # `e` field
    rules: SectionForm        # `r` field


@dataclass(frozen=True)
class ACDCInspection:
    """Domain-layer classification of a parsed ACDC instance.

    All identifying fields preserved; convention layer (e.g. `is_private`)
    derived from spec primitives (`u` field presence).
    """

    # --- Identity (spec-required: [v, d, i, s])
    version_string: str               # `v`
    said: str                          # `d`
    issuer_aid: str                    # `i`
    schema_said: str                   # `s`

    # --- Optional spec-defined header fields
    message_type: str | None           # `t` — ACDC variant (acm/act/acg)
    nonce: str | None                  # `u` — UUID, presence => private variant
    registry_said: str | None          # `rd` (or `ri` legacy) — TEL registry SAID

    # --- Variant classification (convention names over spec primitives)
    is_private: bool
    """True if `u` field is present. Private ACDCs have a per-issuance
    nonce that prevents SAID-based correlation across presentations."""

    # --- Targeting (convention names; spec mechanism is a.i presence)
    is_targeted: bool
    """True if the attribute block declares an issuee AID (`a.i`)."""
    issuee_aid: str | None
    """Issuee AID if targeted; None otherwise."""

    # --- Per-section form
    sections: SectionsPresent

    # --- Disclosure classification (derived; convention overlay)
    disclosure_tier: DisclosureTier

    # --- Section content (only populated where section is present in full form)
    edges: tuple[EdgeInspection, ...]
    rules: tuple[RuleInspection, ...]

    # --- Cryptographic commitments (KERI-native: prior, command, etc. live
    # in event payloads, not the ACDC itself; we don't surface those here)

    # --- Raw access
    raw: dict[str, Any]


# ---------------------------------------------------------------------------
# Inspection result for an ACDC schema document
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SchemaEdgeRequirement:
    """An edge declared in an ACDC schema's `e` section structure.

    The schema author may lock the chained schema's SAID via JSON Schema
    `const`, may require a specific operator via enum, etc. Inspector
    surfaces what the schema demands of conforming instances.
    """
    name: str
    description: str
    target_schema_said: str | None
    """Locked target schema SAID via `s.const` constraint, if present."""
    operator_constraint: tuple[str, ...] | None
    """Permitted operator values via `o.enum` constraint, if present.
    None means no constraint (any spec operator allowed, default I2I applies)."""
    operator_locked: str | None
    """Locked operator via `o.const`, if present (stronger than enum)."""
    requires_operator: bool
    """Whether `o` is in the edge's required field list."""


@dataclass(frozen=True)
class SectionsDeclared:
    """Per-section declaration status in a schema."""
    declares_attribute: bool
    attribute_required: bool
    declares_aggregate: bool
    aggregate_required: bool
    declares_edges: bool
    edges_required: bool
    declares_rules: bool
    rules_required: bool


@dataclass(frozen=True)
class ACDCSchemaInspection:
    """Domain-layer classification of an ACDC schema document.

    Tells callers what kind of credentials this schema admits without
    needing to see any actual instance.
    """
    schema_said: str                     # `$id` (top-level)
    title: str
    description: str
    credential_type: str | None          # custom convention field on most ACDC schemas
    schema_version: str | None           # custom convention field

    declared_sections: SectionsDeclared

    # Variant requirements derivable from required-fields list
    requires_nonce: bool
    """Schema requires `u`; instances will be private."""
    requires_targeted: bool
    """Schema's attribute block requires `i`; instances will be targeted."""
    requires_registry: bool
    """Schema requires `rd`/`ri`; instances must be in a TEL registry."""
    requires_message_type: bool
    """Schema requires `t`."""

    edge_requirements: tuple[SchemaEdgeRequirement, ...]
    rule_keys_declared: tuple[str, ...]

    raw: dict[str, Any]


# ---------------------------------------------------------------------------
# Inspection functions
# ---------------------------------------------------------------------------


def inspect_acdc(parsed: dict[str, Any]) -> ACDCInspection:
    """Classify a parsed ACDC instance by spec-defined domain properties.

    Args:
        parsed: the ACDC field map (e.g. SerderACDC.sad, or a dict from
                Reger.cloneCreds output's `sad` key).

    Returns:
        An ACDCInspection capturing variant, targeting, sections, edges,
        rules, and disclosure tier.
    """
    # --- Required identity fields (spec REQUIRES v, d, i, s; raise if missing)
    version_string = _must(parsed, "v")
    said = _must(parsed, "d")
    issuer_aid = _must(parsed, "i")
    schema_said = _must(parsed, "s")

    # --- Optional header fields
    message_type = parsed.get("t")
    nonce = parsed.get("u")
    # Latest spec uses `rd`; keripy 1.3.4 still emits `ri`. Accept both.
    registry_said = parsed.get("rd") or parsed.get("ri")

    # --- Variant: presence of u => private (per ACDC spec privacy mechanism)
    is_private = nonce is not None

    # --- Targeting + per-section forms
    sections, issuee_aid = _classify_sections(parsed)

    # --- Edges (only if e is in full form)
    edges: tuple[EdgeInspection, ...] = ()
    if sections.edges == "full":
        edges_block = parsed.get("e", {})
        if isinstance(edges_block, dict):
            edges = _inspect_edges(edges_block)

    # --- Rules (only if r is in full form)
    rules: tuple[RuleInspection, ...] = ()
    if sections.rules == "full":
        rules_block = parsed.get("r", {})
        if isinstance(rules_block, dict):
            rules = _inspect_rules(rules_block)

    # --- Disclosure tier (derived from per-section forms)
    disclosure_tier = _derive_disclosure_tier(sections)

    return ACDCInspection(
        version_string=version_string,
        said=said,
        issuer_aid=issuer_aid,
        schema_said=schema_said,
        message_type=message_type,
        nonce=nonce,
        registry_said=registry_said,
        is_private=is_private,
        is_targeted=sections.attribute != "absent" and issuee_aid is not None,
        issuee_aid=issuee_aid,
        sections=sections,
        disclosure_tier=disclosure_tier,
        edges=edges,
        rules=rules,
        raw=parsed,
    )


def inspect_acdc_schema(schema: dict[str, Any]) -> ACDCSchemaInspection:
    """Classify an ACDC schema document by what credentials it admits.

    Args:
        schema: the saidified ACDC schema (a dict, with `$id` populated).

    Returns:
        An ACDCSchemaInspection summarizing required ACDC fields, declared
        sections, and edge requirements.
    """
    schema_said = schema.get("$id", "")
    title = schema.get("title", "")
    description = schema.get("description", "")
    credential_type = schema.get("credentialType")
    schema_version = schema.get("version")

    required = set(schema.get("required", []))
    properties = schema.get("properties", {})

    # Section declaration status
    sections_declared = SectionsDeclared(
        declares_attribute="a" in properties,
        attribute_required="a" in required,
        declares_aggregate="A" in properties,
        aggregate_required="A" in required,
        declares_edges="e" in properties,
        edges_required="e" in required,
        declares_rules="r" in properties,
        rules_required="r" in required,
    )

    requires_nonce = "u" in required
    requires_message_type = "t" in required
    # Legacy keripy uses ri; spec is rd. Either being required counts.
    requires_registry = "rd" in required or "ri" in required
    requires_targeted = _attribute_block_requires_issuee(properties.get("a"))

    edge_requirements = _inspect_schema_edges(properties.get("e"))
    rule_keys_declared = _inspect_schema_rules(properties.get("r"))

    return ACDCSchemaInspection(
        schema_said=schema_said,
        title=title,
        description=description,
        credential_type=credential_type,
        schema_version=schema_version,
        declared_sections=sections_declared,
        requires_nonce=requires_nonce,
        requires_targeted=requires_targeted,
        requires_registry=requires_registry,
        requires_message_type=requires_message_type,
        edge_requirements=edge_requirements,
        rule_keys_declared=rule_keys_declared,
        raw=schema,
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _must(parsed: dict[str, Any], field_name: str) -> str:
    """Read a required ACDC top-level field; raise if missing.

    Per spec, required fields are [v, d, i, s]. Anything else is optional.
    """
    if field_name not in parsed:
        raise ValueError(
            f"ACDC missing required spec field '{field_name}'; "
            f"spec-required set is [v, d, i, s]"
        )
    return parsed[field_name]


def _classify_sections(
    parsed: dict[str, Any],
) -> tuple[SectionsPresent, str | None]:
    """Classify per-section presence/form and extract issuee if targeted.

    Per spec, `a` (attribute) and `A` (aggregate) are mutually exclusive.
    """
    a_section = parsed.get("a")
    big_a_section = parsed.get("A")
    e_section = parsed.get("e")
    r_section = parsed.get("r")

    attribute_form = _section_form(a_section)
    aggregate_form = _section_form(big_a_section)
    edges_form = _section_form(e_section)
    rules_form = _section_form(r_section)

    # Issuee AID lives in a.i for targeted ACDCs (only meaningful when a is full)
    issuee_aid: str | None = None
    if attribute_form == "full" and isinstance(a_section, dict):
        issuee_aid = a_section.get("i")

    return (
        SectionsPresent(
            attribute=attribute_form,
            aggregate=aggregate_form,
            edges=edges_form,
            rules=rules_form,
        ),
        issuee_aid,
    )


def _section_form(value: Any) -> SectionForm:
    """Classify a section value as compact (string SAID), full (dict), or absent."""
    if value is None:
        return "absent"
    if isinstance(value, str):
        return "compact"
    if isinstance(value, dict):
        return "full"
    return "absent"


def _derive_disclosure_tier(sections: SectionsPresent) -> DisclosureTier:
    """Derive the graduated disclosure tier from per-section forms.

    Convention overlay: spec defines the underlying mechanisms but doesn't
    assign a single tier label per instance. This is our synthesis.
    """
    # Selective: the aggregate-disclosable A section is in full form
    if sections.aggregate == "full":
        return "selective"

    # Count non-absent sections by form
    section_forms = (
        sections.attribute,
        sections.aggregate,
        sections.edges,
        sections.rules,
    )
    present = [f for f in section_forms if f != "absent"]
    full = [f for f in section_forms if f == "full"]

    if not present:
        # Only headers, no content sections => metadata
        return "metadata"
    if len(full) == len(present):
        # Every present section is full
        return "full"
    if not full:
        # Every present section is compact => still metadata-ish
        return "metadata"
    # Mix of compact and full
    return "partial"


def _inspect_edges(edges_block: dict[str, Any]) -> tuple[EdgeInspection, ...]:
    """Walk the edges block, classifying each entry as edge or edge-group.

    Per spec: an edge MUST have `n` (chained credential SAID); edge-groups
    MUST NOT. The `d` field is the section's own SAID — skip it.
    """
    out: list[EdgeInspection] = []
    for name, value in edges_block.items():
        if name == "d" or not isinstance(value, dict):
            continue
        if "n" in value:
            # Edge
            out.append(EdgeInspection(
                name=name,
                is_edge=True,
                target_said=value.get("n"),
                target_schema_said=value.get("s"),
                operator=value.get("o"),
            ))
        else:
            # Edge-group: nested edges/groups
            nested = _inspect_edges(value)
            out.append(EdgeInspection(
                name=name,
                is_edge=False,
                group_operator=value.get("o"),
                nested=nested,
            ))
    return tuple(out)


def _inspect_rules(rules_block: dict[str, Any]) -> tuple[RuleInspection, ...]:
    """Walk the rules block.

    Per spec, every rule block REQUIRES an `l` (legal language) field.
    """
    out: list[RuleInspection] = []
    for name, value in rules_block.items():
        if name == "d" or not isinstance(value, dict):
            continue
        legal = value.get("l")
        out.append(RuleInspection(
            name=name,
            has_legal_language=legal is not None,
            legal_language=legal if isinstance(legal, str) else None,
            raw=value,
        ))
    return tuple(out)


def _attribute_block_requires_issuee(a_property: Any) -> bool:
    """Inspect a schema's `a` property declaration to see if `i` is required.

    Standard ACDC pattern uses `oneOf` with [SAID-string, full-block]; the
    full block declares `properties` and `required`. We look at the full
    branch for the `i` requirement.
    """
    if not isinstance(a_property, dict):
        return False
    one_of = a_property.get("oneOf", [])
    for branch in one_of:
        if not isinstance(branch, dict) or branch.get("type") != "object":
            continue
        if "i" in branch.get("required", []):
            return True
    return False


def _inspect_schema_edges(e_property: Any) -> tuple[SchemaEdgeRequirement, ...]:
    """Walk a schema's `e` property to extract edge declarations.

    Looks for the full-block branch in the `oneOf`, then iterates its
    properties (excluding `d`) to find each declared edge.
    """
    if not isinstance(e_property, dict):
        return ()
    one_of = e_property.get("oneOf", [])
    out: list[SchemaEdgeRequirement] = []
    for branch in one_of:
        if not isinstance(branch, dict) or branch.get("type") != "object":
            continue
        edge_props = branch.get("properties", {})
        for name, prop in edge_props.items():
            if name == "d" or not isinstance(prop, dict):
                continue
            if prop.get("type") != "object":
                continue
            inner_props = prop.get("properties", {})
            inner_required = set(prop.get("required", []))

            target_schema_said = None
            s_def = inner_props.get("s")
            if isinstance(s_def, dict) and "const" in s_def:
                target_schema_said = s_def["const"]

            operator_constraint: tuple[str, ...] | None = None
            operator_locked = None
            o_def = inner_props.get("o")
            if isinstance(o_def, dict):
                if "const" in o_def:
                    operator_locked = o_def["const"]
                elif "enum" in o_def and isinstance(o_def["enum"], list):
                    operator_constraint = tuple(o_def["enum"])

            out.append(SchemaEdgeRequirement(
                name=name,
                description=prop.get("description", name),
                target_schema_said=target_schema_said,
                operator_constraint=operator_constraint,
                operator_locked=operator_locked,
                requires_operator="o" in inner_required,
            ))
    return tuple(out)


def _inspect_schema_rules(r_property: Any) -> tuple[str, ...]:
    """Extract the rule keys declared in a schema's `r` section.

    The schema may declare specific rule blocks by key; an instance is
    expected to populate those (each with the spec-required `l` field).
    """
    if not isinstance(r_property, dict):
        return ()
    one_of = r_property.get("oneOf", [])
    for branch in one_of:
        if not isinstance(branch, dict) or branch.get("type") != "object":
            continue
        rule_props = branch.get("properties", {})
        return tuple(name for name in rule_props.keys() if name != "d")
    return ()
