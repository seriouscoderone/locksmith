# -*- encoding: utf-8 -*-
"""Tests for locksmith.acdc.inspector — pure-Python, no Qt or vault required."""
from __future__ import annotations

import pytest

from locksmith.acdc import inspect_acdc, inspect_acdc_schema


# ---------------------------------------------------------------------------
# Instance inspection
# ---------------------------------------------------------------------------


def _minimal_acdc(**overrides):
    base = {
        "v": "ACDC10JSON000050_",
        "d": "EAaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "i": "EIssuerIssuerIssuerIssuerIssuerIssuerIssuer",
        "s": "ESchemaSchemaSchemaSchemaSchemaSchemaSchema",
    }
    base.update(overrides)
    return base


def test_minimal_acdc_classifies_as_metadata_public_untargeted():
    i = inspect_acdc(_minimal_acdc())
    assert i.is_private is False
    assert i.is_targeted is False
    assert i.issuee_aid is None
    assert i.disclosure_tier == "metadata"
    assert i.sections.attribute == "absent"
    assert i.sections.aggregate == "absent"
    assert i.sections.edges == "absent"
    assert i.sections.rules == "absent"


def test_acdc_with_u_field_is_private():
    i = inspect_acdc(_minimal_acdc(u="0AnonceXxxxxxxxxxxxxxxxxxx"))
    assert i.is_private is True
    assert i.nonce == "0AnonceXxxxxxxxxxxxxxxxxxx"


def test_acdc_with_attribute_block_having_i_is_targeted():
    a = {
        "d": "EAttribAttribAttribAttribAttribAttribAttrib",
        "i": "EIssueeIssueeIssueeIssueeIssueeIssueeIssuee",
        "name": "Alice",
    }
    i = inspect_acdc(_minimal_acdc(a=a))
    assert i.is_targeted is True
    assert i.issuee_aid == "EIssueeIssueeIssueeIssueeIssueeIssueeIssuee"
    assert i.sections.attribute == "full"


def test_acdc_with_compact_attribute_section_is_partial():
    i = inspect_acdc(_minimal_acdc(
        a="EAttribSAIDAttribSAIDAttribSAIDAttribSAIDAttribSAID",
        e={"d": "EEdgeEdgeEdgeEdgeEdgeEdgeEdgeEdgeEdgeEdge",
           "x": {"n": "ETargetTargetTargetTargetTargetTargetTarget",
                 "s": "ETargetSchemaTargetSchemaTargetSchemaTarget"}},
    ))
    assert i.sections.attribute == "compact"
    assert i.sections.edges == "full"
    # Mixed forms => partial
    assert i.disclosure_tier == "partial"


def test_acdc_with_aggregate_section_is_selective():
    i = inspect_acdc(_minimal_acdc(A={"d": "EAggrAggrAggrAggrAggrAggrAggrAggrAggrAggr"}))
    assert i.sections.aggregate == "full"
    assert i.disclosure_tier == "selective"


def test_inspect_acdc_extracts_edges_with_operator():
    i = inspect_acdc(_minimal_acdc(e={
        "d": "EEdgeEdgeEdgeEdgeEdgeEdgeEdgeEdgeEdgeEdge",
        "license": {
            "n": "ELicenseInstLicenseInstLicenseInstLicenseInst",
            "s": "ELicenseSchemaLicenseSchemaLicenseSchemaLic",
            "o": "I2I",
        },
    }))
    assert len(i.edges) == 1
    edge = i.edges[0]
    assert edge.is_edge is True
    assert edge.name == "license"
    assert edge.target_said == "ELicenseInstLicenseInstLicenseInstLicenseInst"
    assert edge.operator == "I2I"


def test_inspect_acdc_distinguishes_edge_groups_from_edges():
    # Edge-group: dict without `n`, contains nested edges
    i = inspect_acdc(_minimal_acdc(e={
        "d": "EEdgeEdgeEdgeEdgeEdgeEdgeEdgeEdgeEdgeEdge",
        "any_of": {
            "o": "OR",
            "license_a": {"n": "ELicAaaa", "s": "ESchAaaa"},
            "license_b": {"n": "ELicBbbb", "s": "ESchBbbb"},
        },
    }))
    assert len(i.edges) == 1
    group = i.edges[0]
    assert group.is_edge is False
    assert group.group_operator == "OR"
    assert len(group.nested) == 2
    assert all(e.is_edge for e in group.nested)


def test_inspect_acdc_rules_flag_missing_legal_language():
    # Per spec: rule blocks REQUIRE l field. Inspector flags absence.
    i = inspect_acdc(_minimal_acdc(r={
        "d": "ERulesRulesRulesRulesRulesRulesRulesRulesRules",
        "good": {"l": "Compliant rule with legal language."},
        "bad": {"description": "missing l field"},
    }))
    by_name = {r.name: r for r in i.rules}
    assert by_name["good"].has_legal_language is True
    assert by_name["good"].legal_language == "Compliant rule with legal language."
    assert by_name["bad"].has_legal_language is False


def test_inspect_acdc_missing_required_field_raises():
    with pytest.raises(ValueError, match="missing required spec field"):
        inspect_acdc({"v": "x", "d": "y"})  # i is the first missing field; raises on it


def test_inspect_acdc_accepts_legacy_ri_or_spec_rd():
    i_legacy = inspect_acdc(_minimal_acdc(ri="ERegistryLegacyRiRiRiRiRiRiRiRiRiRiRi"))
    i_spec = inspect_acdc(_minimal_acdc(rd="ERegistrySpecRdRdRdRdRdRdRdRdRdRdRdRd"))
    assert i_legacy.registry_said == "ERegistryLegacyRiRiRiRiRiRiRiRiRiRiRi"
    assert i_spec.registry_said == "ERegistrySpecRdRdRdRdRdRdRdRdRdRdRdRd"


# ---------------------------------------------------------------------------
# Schema inspection
# ---------------------------------------------------------------------------


def _schema(**overrides):
    base = {
        "$id": "ESchemaSaidSchemaSaidSchemaSaidSchemaSaidSchemaSaid",
        "title": "ExampleCredential",
        "description": "Test schema",
        "credentialType": "ExampleCredentialV1",
        "version": "1.0.0",
        "type": "object",
        "properties": {
            "v": {"type": "string"},
            "d": {"type": "string"},
            "i": {"type": "string"},
            "s": {"type": "string"},
        },
        "required": ["v", "d", "i", "s"],
    }
    base.update(overrides)
    return base


def test_schema_inspection_metadata():
    s = inspect_acdc_schema(_schema())
    assert s.title == "ExampleCredential"
    assert s.credential_type == "ExampleCredentialV1"
    assert s.schema_version == "1.0.0"


def test_schema_inspection_detects_targeted_requirement():
    s = inspect_acdc_schema(_schema(properties={
        "v": {"type": "string"},
        "d": {"type": "string"},
        "i": {"type": "string"},
        "s": {"type": "string"},
        "a": {
            "oneOf": [
                {"type": "string"},
                {
                    "type": "object",
                    "required": ["d", "i"],
                    "properties": {"d": {"type": "string"}, "i": {"type": "string"}},
                },
            ],
        },
    }, required=["v", "d", "i", "s", "a"]))
    assert s.requires_targeted is True
    assert s.declared_sections.declares_attribute is True
    assert s.declared_sections.attribute_required is True


def test_schema_inspection_extracts_edge_with_locked_target_schema():
    s = inspect_acdc_schema(_schema(properties={
        "v": {"type": "string"},
        "d": {"type": "string"},
        "i": {"type": "string"},
        "s": {"type": "string"},
        "e": {
            "oneOf": [
                {"type": "string"},
                {
                    "type": "object",
                    "required": ["d", "license"],
                    "properties": {
                        "d": {"type": "string"},
                        "license": {
                            "type": "object",
                            "required": ["n", "s"],
                            "properties": {
                                "n": {"type": "string"},
                                "s": {"type": "string", "const": "ELockedTargetSchemaLockedTargetSchemaLockedTar"},
                                "o": {"type": "string", "enum": ["I2I", "DI2I"]},
                            },
                        },
                    },
                },
            ],
        },
    }, required=["v", "d", "i", "s", "e"]))
    assert len(s.edge_requirements) == 1
    edge = s.edge_requirements[0]
    assert edge.name == "license"
    assert edge.target_schema_said == "ELockedTargetSchemaLockedTargetSchemaLockedTar"
    assert edge.operator_constraint == ("I2I", "DI2I")


# ---------------------------------------------------------------------------
# Attribute field extraction
# ---------------------------------------------------------------------------


def _schema_with_attributes(props: dict, required_attrs: list[str]):
    """Helper: build a schema whose attribute block declares the given properties."""
    return _schema(
        properties={
            "v": {"type": "string"},
            "d": {"type": "string"},
            "i": {"type": "string"},
            "s": {"type": "string"},
            "a": {
                "oneOf": [
                    {"type": "string"},
                    {
                        "type": "object",
                        "required": ["d", "i", "dt"] + required_attrs,
                        "properties": {
                            "d": {"type": "string"},
                            "i": {"type": "string"},
                            "dt": {"type": "string", "format": "date-time"},
                            **props,
                        },
                    },
                ],
            },
        },
        required=["v", "d", "i", "s", "a"],
    )


def test_attribute_fields_extracted_with_basic_string():
    s = inspect_acdc_schema(_schema_with_attributes(
        props={
            "licenseNumber": {
                "type": "string",
                "description": "Unique license number",
            },
        },
        required_attrs=["licenseNumber"],
    ))
    assert len(s.attribute_fields) == 1
    f = s.attribute_fields[0]
    assert f.name == "licenseNumber"
    assert f.type_label == "string"
    assert f.description == "Unique license number"
    assert f.required is True
    assert f.enum_values is None
    assert f.format is None


def test_attribute_field_optional_when_not_in_required_list():
    s = inspect_acdc_schema(_schema_with_attributes(
        props={
            "memo": {"type": "string", "description": "Optional memo"},
        },
        required_attrs=[],
    ))
    assert len(s.attribute_fields) == 1
    assert s.attribute_fields[0].required is False


def test_attribute_field_array_with_enum_items():
    s = inspect_acdc_schema(_schema_with_attributes(
        props={
            "linesOfAuthority": {
                "type": "array",
                "items": {"type": "string", "enum": ["P&C", "Life", "Health"]},
                "minItems": 1,
                "description": "Lines of authority covered",
            },
        },
        required_attrs=["linesOfAuthority"],
    ))
    f = s.attribute_fields[0]
    assert f.type_label == "array<string>"
    assert f.enum_values == ("P&C", "Life", "Health")
    assert f.min_items == 1


def test_attribute_field_string_with_format_renders_format_label():
    s = inspect_acdc_schema(_schema_with_attributes(
        props={
            "issuedDate": {"type": "string", "format": "date"},
            "issuedAt":  {"type": "string", "format": "date-time"},
            "homepage":  {"type": "string", "format": "uri"},
        },
        required_attrs=[],
    ))
    by_name = {f.name: f for f in s.attribute_fields}
    assert by_name["issuedDate"].type_label == "date"
    assert by_name["issuedDate"].format == "date"
    assert by_name["issuedAt"].type_label == "datetime"
    assert by_name["homepage"].type_label == "URL"


def test_attribute_field_string_with_enum_directly():
    s = inspect_acdc_schema(_schema_with_attributes(
        props={
            "state": {
                "type": "string",
                "enum": ["CA", "TX", "NY"],
                "minLength": 2,
                "maxLength": 2,
            },
        },
        required_attrs=["state"],
    ))
    f = s.attribute_fields[0]
    assert f.type_label == "string"
    assert f.enum_values == ("CA", "TX", "NY")
    assert f.min_length == 2
    assert f.max_length == 2


def test_attribute_field_skips_protocol_fields_d_i_dt():
    """The d/i/dt fields are ACDC-protocol-defined in every attribute block.
    They aren't user-meaningful schema fields, so the inspector should skip them."""
    s = inspect_acdc_schema(_schema_with_attributes(
        props={
            "name": {"type": "string"},
        },
        required_attrs=["name"],
    ))
    names = [f.name for f in s.attribute_fields]
    assert "d" not in names
    assert "i" not in names
    assert "dt" not in names
    assert "name" in names


def test_schema_with_no_attribute_block_has_empty_attribute_fields():
    s = inspect_acdc_schema(_schema())  # _schema has no `a` section declared
    assert s.attribute_fields == ()


def test_attribute_field_unknown_type_falls_back_gracefully():
    s = inspect_acdc_schema(_schema_with_attributes(
        props={
            "weird": {"description": "no type declared"},
        },
        required_attrs=[],
    ))
    f = s.attribute_fields[0]
    assert f.name == "weird"
    assert f.type_label == "unknown"
