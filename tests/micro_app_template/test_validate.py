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
