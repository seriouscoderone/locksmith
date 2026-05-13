# -*- encoding: utf-8 -*-
"""Validation adapter: wraps locksmith.micro_app_template.validate."""
from __future__ import annotations

from pathlib import Path

import pytest

from locksmith.plugins.designer.validation import (
    ValidationEngine,
    ValidationIssue,
    ValidationReport,
    surface_from_path,
)

META_SCHEMA = (
    Path(__file__).resolve().parents[3]
    / "docs" / "superpowers" / "specs" / "schemas"
    / "micro-app-template.schema.json"
)


VALID_FIXTURE = {
    "d": "E" + "A" * 43,
    "spec_version": "micro-app-template/0.1",
    "header": {
        "id": "test-app",
        "display_name": "Test App",
        "description": "A test application",
        "version": "1.0",
        "expression_language": "UEL/1.0",
    },
    "role": {
        "id": "r1",
        "display_name": "Tester",
        "description": "A test role",
        "kind": "individual",
        "keri_infrastructure": {
            "witness_pool": False,
            "watcher_network": False,
            "mailbox": False,
            "acdc_registry": False,
        },
    },
    "credentials": {"imports": [], "exports": []},
    "commands": [],
    "aggregates": [],
    "reactions": [],
    "workflows": [],
    "projections": [],
    "rules": [],
}


def test_surface_from_path_covers_all_primitives():
    assert surface_from_path("/commands/0/inputs") == "commands"
    assert surface_from_path("/credentials/imports/0") == "imports"
    assert surface_from_path("/credentials/exports/2/lifecycle") == "exports"
    assert surface_from_path("/workflows/1/steps") == "workflows"
    assert surface_from_path("/projections/0") == "projections"
    assert surface_from_path("/rules/3/body") == "rules"
    assert surface_from_path("/aggregates/0") == "aggregates"
    assert surface_from_path("/reactions/1/effect") == "reactions"
    assert surface_from_path("/header/label") == "overview"
    assert surface_from_path("/role/name") == "overview"
    assert surface_from_path("/d") == "overview"
    assert surface_from_path("") == "overview"


def test_validate_returns_clean_report_for_valid_doc():
    engine = ValidationEngine(meta_schema_path=META_SCHEMA)
    report = engine.validate(VALID_FIXTURE)
    assert isinstance(report, ValidationReport)
    assert report.is_valid is True
    assert report.errors == ()
    assert report.warnings == ()


def test_validate_returns_errors_for_missing_required():
    engine = ValidationEngine(meta_schema_path=META_SCHEMA)
    bad = {k: v for k, v in VALID_FIXTURE.items() if k != "header"}
    report = engine.validate(bad)
    assert report.is_valid is False
    assert len(report.errors) >= 1
    # Surfaces should route the missing-required error to "overview"
    # (the place the header is edited).
    assert any(e.surface == "overview" for e in report.errors)


def test_validate_routes_xref_error_to_correct_surface():
    engine = ValidationEngine(meta_schema_path=META_SCHEMA)
    doc = dict(VALID_FIXTURE)
    doc["credentials"] = {
        "imports": [],
        "exports": [
            {
                "id": "ex1",
                "name": "Test Cred",
                "schema_said": "E" + "B" * 43,
                "issuer_role_id": "r1",
                "issuee_role_id": "r2",
                "rule_refs": ["nonexistent-rule"],
                "lifecycle": {"transitions": []},
            }
        ],
    }
    report = engine.validate(doc)
    matching = [
        e for e in report.errors
        if e.surface == "exports" and "rule" in e.message.lower()
    ]
    assert matching, f"Expected a rule xref error on exports surface, got {report.errors}"


def test_json_pointer_path_starts_with_slash():
    engine = ValidationEngine(meta_schema_path=META_SCHEMA)
    bad = {k: v for k, v in VALID_FIXTURE.items() if k != "header"}
    report = engine.validate(bad)
    for issue in report.errors:
        assert issue.path == "" or issue.path.startswith("/"), \
            f"path {issue.path!r} not JSON-pointer normalized"
