"""Tests for micro-app-template validation."""
from __future__ import annotations

from pathlib import Path

import pytest

from locksmith.micro_app_template.validate import (
    ValidationError,
    validate_against_meta_schema,
    validate_cross_references,
    validate_template,
)


# Path to the meta-schema (built in Tasks 4-8).
META_SCHEMA = Path(__file__).parent.parent.parent / "docs/superpowers/specs/schemas/micro-app-template.schema.json"


def test_minimal_valid_template_passes_meta_schema(minimal_valid_template, fixtures_dir):
    # This test asserts the schema accepts the minimal fixture once the
    # schema exists. It will be enabled fully in Task 4.
    if not META_SCHEMA.exists():
        pytest.skip("meta-schema not yet built")
    errors = validate_against_meta_schema(minimal_valid_template, META_SCHEMA)
    assert errors == []


def test_missing_d_field_fails(minimal_valid_template):
    if not META_SCHEMA.exists():
        pytest.skip("meta-schema not yet built")
    bad = dict(minimal_valid_template)
    del bad["d"]
    errors = validate_against_meta_schema(bad, META_SCHEMA)
    assert any("'d'" in e.message or "d " in e.message for e in errors)


def test_dangling_rule_ref_caught_by_xref():
    doc = {
        "rules": [{"id": "real-rule", "type": "legal_prose", "title": "X", "body": "y"}],
        "credentials": {
            "held": [],
            "issued": [
                {
                    "id": "cred-a",
                    "name": "Cred A",
                    "description": "x",
                    "envelope": {"holder_role": "x", "verifier_roles": [], "edges": [], "disclosure_mode": "full"},
                    "schema": {"schema_said": "E" + "x" * 43, "schema_path": "schemas/a.json"},
                    "lifecycle": {"states": ["active"], "initial": "active", "transitions": []},
                    "rule_refs": ["does-not-exist"],
                    "value_flow": {"implied_credentials": []},
                }
            ],
        },
    }
    errors = validate_cross_references(doc)
    assert any("does-not-exist" in e.message for e in errors)


def test_validate_template_combines_meta_and_xref(minimal_valid_template):
    if not META_SCHEMA.exists():
        pytest.skip("meta-schema not yet built")
    result = validate_template(minimal_valid_template, META_SCHEMA)
    assert result.is_valid
    assert result.errors == []


def test_validate_template_returns_typed_result(minimal_valid_template):
    if not META_SCHEMA.exists():
        pytest.skip("meta-schema not yet built")
    bad = dict(minimal_valid_template)
    del bad["role"]
    result = validate_template(bad, META_SCHEMA)
    assert not result.is_valid
    assert len(result.errors) > 0
    assert all(isinstance(e, ValidationError) for e in result.errors)


def test_meta_schema_file_exists():
    assert META_SCHEMA.exists(), f"meta-schema not found at {META_SCHEMA}"


def test_meta_schema_is_valid_jsonschema():
    import json
    import jsonschema
    with open(META_SCHEMA) as f:
        schema = json.load(f)
    jsonschema.Draft202012Validator.check_schema(schema)


def test_minimal_template_validates_against_meta_schema(minimal_valid_template):
    errors = validate_against_meta_schema(minimal_valid_template, META_SCHEMA)
    assert errors == [], f"unexpected errors: {[e.message for e in errors]}"


def test_wrong_kind_fails(minimal_valid_template):
    minimal_valid_template["role"]["kind"] = "not_a_real_kind"
    errors = validate_against_meta_schema(minimal_valid_template, META_SCHEMA)
    assert any("kind" in e.path or "kind" in e.message for e in errors)


def test_missing_required_top_level_fails(minimal_valid_template):
    del minimal_valid_template["role"]
    errors = validate_against_meta_schema(minimal_valid_template, META_SCHEMA)
    assert any("role" in e.message for e in errors)


import pytest
from locksmith.micro_app_template.xref import validate_xrefs


@pytest.mark.parametrize("doc,expected_substring", [
    # rule_ref in commands auth_preconditions
    (
        {
            "rules": [],
            "commands": [{
                "id": "c1", "name": "c", "description": "c", "route": "/x/cmd/c",
                "payload_schema": {}, "idempotency_key_expression": "hash(p)", "emissions": [],
                "auth_preconditions": [{"rule_ref": "missing-rule"}],
            }],
        },
        "missing-rule",
    ),
    # via_workflow on lifecycle transition
    (
        {
            "rules": [],
            "workflows": [],
            "credentials": {"held": [], "issued": [{
                "id": "c1", "name": "n", "description": "d",
                "envelope": {"holder_role": "r", "verifier_roles": [], "edges": [], "disclosure_mode": "full"},
                "schema": {"schema_said": "E" + "x" * 43, "schema_path": "schemas/c.json"},
                "lifecycle": {"states": ["a"], "initial": "a", "transitions": [
                    {"id": "t1", "from": "a", "to": "a", "tel_primitive": "issue", "via_workflow": "missing-workflow"}
                ]},
                "rule_refs": [],
                "value_flow": {"implied_credentials": []},
            }]},
        },
        "missing-workflow",
    ),
    # workflow step command_id reference
    (
        {
            "commands": [],
            "workflows": [{
                "id": "w1", "name": "w", "description": "d",
                "trigger": {"type": "manual"},
                "steps": [{"id": "s1", "name": "s", "actor": "self", "command_id": "missing-command"}],
            }],
        },
        "missing-command",
    ),
    # reaction trigger credential_held_id
    (
        {
            "credentials": {"held": [], "issued": []},
            "reactions": [{
                "id": "r1", "description": "r",
                "trigger": {"type": "credential_received", "credential_held_id": "missing-held"},
                "emissions": [],
            }],
        },
        "missing-held",
    ),
    # aggregate invariant rule_ref
    (
        {
            "rules": [],
            "aggregates": [{
                "id": "a1", "description": "a", "inception_event_type": "x",
                "state_schema": {}, "initial_state": {}, "log_scope": "private",
                "invariants": [{"rule_ref": "missing-rule"}],
            }],
        },
        "missing-rule",
    ),
    # projection access row_filter_rule_ref
    (
        {
            "rules": [],
            "projections": [{
                "id": "p1", "name": "p", "description": "p",
                "source_events": ["e1"], "output_schema": {}, "fold_expression": "state",
                "access": {"row_filter_rule_ref": "missing-rule"},
            }],
        },
        "missing-rule",
    ),
    # rule binding_link links
    (
        {
            "rules": [
                {"id": "r1", "type": "binding_link", "title": "L",
                 "links": [{"rule_id": "missing-rule"}]},
            ],
        },
        "missing-rule",
    ),
    # command emission lifecycle_advance credential_issued_id
    (
        {
            "credentials": {"held": [], "issued": []},
            "commands": [{
                "id": "c1", "name": "c", "description": "c", "route": "/x/cmd/c",
                "payload_schema": {}, "idempotency_key_expression": "hash(p)",
                "emissions": [{"kind": "lifecycle_advance", "credential_issued_id": "missing-issued", "to_state": "active"}],
            }],
        },
        "missing-issued",
    ),
    # command emission aggregate_event aggregate_id
    (
        {
            "aggregates": [],
            "commands": [{
                "id": "c1", "name": "c", "description": "c", "route": "/x/cmd/c",
                "payload_schema": {}, "idempotency_key_expression": "hash(p)",
                "emissions": [{"kind": "aggregate_event", "aggregate_id": "missing-agg", "event_type": "e", "payload_mapping": "m"}],
            }],
        },
        "missing-agg",
    ),
])
def test_xref_catches_dangling_reference(doc, expected_substring):
    errors = validate_xrefs(doc)
    assert any(expected_substring in e.message for e in errors), (
        f"expected substring {expected_substring!r} not in any error: {[e.message for e in errors]}"
    )


def test_xref_passes_on_consistent_doc():
    """A document with all references resolving should produce no xref errors."""
    doc = {
        "rules": [{"id": "r1", "type": "legal_prose", "title": "T", "body": "B"}],
        "credentials": {
            "held": [{"id": "h1", "expected_schema_said": "E" + "x" * 43}],
            "issued": [],
        },
        "commands": [],
        "aggregates": [],
        "reactions": [],
        "workflows": [],
        "projections": [],
    }
    errors = validate_xrefs(doc)
    assert errors == []


def test_credentials_fixture_validates(fixtures_dir):
    import json
    with open(fixtures_dir / "credentials_valid.json") as f:
        doc = json.load(f)
    errors = validate_against_meta_schema(doc, META_SCHEMA)
    assert errors == [], f"unexpected: {[e.message for e in errors]}"


def test_invalid_edge_operator_fails(fixtures_dir):
    import json
    with open(fixtures_dir / "credentials_valid.json") as f:
        doc = json.load(f)
    doc["credentials"]["issued"][0]["envelope"]["edges"][0]["operator"] = "not_a_real_operator"
    errors = validate_against_meta_schema(doc, META_SCHEMA)
    assert any("operator" in e.path or "operator" in e.message for e in errors)


def test_invalid_disclosure_mode_fails(fixtures_dir):
    import json
    with open(fixtures_dir / "credentials_valid.json") as f:
        doc = json.load(f)
    doc["credentials"]["issued"][0]["envelope"]["disclosure_mode"] = "secret"
    errors = validate_against_meta_schema(doc, META_SCHEMA)
    assert any("disclosure_mode" in e.path or "secret" in e.message for e in errors)


def test_invalid_tel_primitive_fails(fixtures_dir):
    import json
    with open(fixtures_dir / "credentials_valid.json") as f:
        doc = json.load(f)
    doc["credentials"]["issued"][0]["lifecycle"]["transitions"][0]["tel_primitive"] = "delete"
    errors = validate_against_meta_schema(doc, META_SCHEMA)
    assert any("tel_primitive" in e.path or "delete" in e.message for e in errors)


def test_schema_path_must_be_in_schemas_dir(fixtures_dir):
    import json
    with open(fixtures_dir / "credentials_valid.json") as f:
        doc = json.load(f)
    doc["credentials"]["issued"][0]["schema"]["schema_path"] = "elsewhere/policy.json"
    errors = validate_against_meta_schema(doc, META_SCHEMA)
    assert any("schema_path" in e.path for e in errors)
