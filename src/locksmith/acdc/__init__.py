# -*- encoding: utf-8 -*-
"""
locksmith.acdc package

Domain-layer access to ACDC primitives. While keripy operates at the byte/field
level (Saider, SerderACDC, raw dict manipulation), real reasoning about
credentials needs the domain layer the spec defines: targeted vs untargeted,
public vs private, disclosure tier (metadata/partial/selective/full),
chain-of-authority operators, edges vs edge-groups, etc.

This module surfaces those concepts as first-class Python types. The two
sides:

- `inspector` (read-side): classify a parsed ACDC instance or schema
  document by its spec-defined domain properties. Used by the wallet's
  view dialogs, the ecosystem viewer plugin, and any code that wants to
  reason about a credential beyond "the raw bytes are valid."

- `builder` (write-side, planned): compose ACDCs in domain language
  ("targeted to X, blinded, with edge to Y under I2I authority") and
  emit the correct field map. Will be added when we start authoring
  credentials programmatically (Skill output, automated test fixtures).

Spec source of truth: ACDC spec body (kswg-acdc-specification/spec/spec-body.md).
Citations in inspector docstrings reference the relevant spec sections.
"""
from locksmith.acdc.inspector import (
    ACDCInspection,
    ACDCSchemaInspection,
    DisclosureTier,
    EdgeInspection,
    EdgeOperator,
    RuleInspection,
    SchemaEdgeRequirement,
    SectionForm,
    SectionsDeclared,
    SectionsPresent,
    inspect_acdc,
    inspect_acdc_schema,
)

__all__ = [
    "ACDCInspection",
    "ACDCSchemaInspection",
    "DisclosureTier",
    "EdgeInspection",
    "EdgeOperator",
    "RuleInspection",
    "SchemaEdgeRequirement",
    "SectionForm",
    "SectionsDeclared",
    "SectionsPresent",
    "inspect_acdc",
    "inspect_acdc_schema",
]
