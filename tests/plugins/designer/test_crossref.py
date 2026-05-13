import pytest
from locksmith.plugins.designer.crossref import (
    CrossRef, CrossRefIndex, compute_crossrefs,
)


@pytest.fixture
def doc():
    return {
        "d": "E" + "A" * 43,
        "spec_version": "micro-app-template/0.1",
        "header": {
            "id": "test-app",
            "display_name": "Test App",
            "description": "Test",
            "version": "1.0",
            "expression_language": "UEL/1.0",
        },
        "role": {
            "id": "tester",
            "display_name": "Tester",
            "description": "Test role",
            "kind": "individual",
            "keri_infrastructure": {
                "witness_pool": False, "watcher_network": False,
                "mailbox": False, "acdc_registry": False,
            },
        },
        "credentials": {
            "imports": [],
            "exports": [
                {
                    "id": "license",
                    "name": "License",
                    "description": "A license credential.",
                    "envelope": {
                        "holder_role": "carrier",
                        "verifier_roles": [],
                        "edges": [],
                        "disclosure_mode": "selective",
                    },
                    "schema": {
                        "schema_said": "E" + "B" * 43,
                        "schema_path": "schemas/license.json",
                    },
                    "lifecycle": {
                        "states": ["pending", "active", "revoked"],
                        "initial": "pending",
                        "transitions": [
                            {
                                "id": "issue",
                                "from": "pending",
                                "to": "active",
                                "tel_primitive": "issue",
                                "via_workflow": "revoke_wf",
                                "condition_rule_ref": "solvency",
                            },
                        ],
                    },
                    "rule_refs": ["solvency"],
                }
            ],
        },
        "commands": [
            {
                "id": "issue_license",
                "name": "Issue License",
                "description": "Issues a license.",
                "route": "/issue",
                "payload_schema": {},
                "idempotency_key_expression": "applicant",
                "auth_preconditions": [{"rule_ref": "solvency"}],
                "emissions": [
                    {
                        "kind": "lifecycle_advance",
                        "exported_credential_id": "license",
                        "to_state": "active",
                    }
                ],
            }
        ],
        "aggregates": [],
        "reactions": [],
        "workflows": [
            {"id": "revoke_wf", "name": "Revoke", "description": "wf",
             "trigger": {"type": "manual"}, "steps": [
                 {"id": "s1", "name": "Step 1", "actor": "self"}
             ]}
        ],
        "projections": [],
        "rules": [
            {"id": "solvency", "type": "predicate", "title": "Solvency",
             "expression": "applicant.capital > 100", "language": "UEL/1.0",
             "purpose": "auth_precondition"},
        ],
    }


def test_compute_returns_crossref_index(doc):
    idx = compute_crossrefs(doc)
    assert isinstance(idx, CrossRefIndex)


def test_rule_consumed_by_command_and_export(doc):
    idx = compute_crossrefs(doc)
    consumers = idx.consumers_of("rule:solvency")
    surfaces = {c.surface for c in consumers}
    assert "commands" in surfaces
    assert "exports" in surfaces


def test_workflow_consumed_by_export(doc):
    idx = compute_crossrefs(doc)
    consumers = idx.consumers_of("workflow:revoke_wf")
    assert any(c.surface == "exports" for c in consumers)


def test_export_consumed_by_command(doc):
    idx = compute_crossrefs(doc)
    consumers = idx.consumers_of("export:license")
    assert any(c.surface == "commands" and c.primitive_label == "Issue License" for c in consumers)


def test_unknown_key_returns_empty_tuple(doc):
    idx = compute_crossrefs(doc)
    assert idx.consumers_of("rule:does-not-exist") == ()


def test_orphan_rule_has_no_consumers(doc):
    doc["rules"].append({"id": "orphan", "type": "legal_prose", "title": "Orphan",
                         "body": "nothing references this"})
    idx = compute_crossrefs(doc)
    assert idx.consumers_of("rule:orphan") == ()


def test_command_emission_credential_received_emits_import_key(doc):
    doc["commands"][0]["emissions"].append({
        "kind": "exchange",
        "exchange": {
            "kind": "credential",
            "verb": "grant",
            "imported_credential_id": "doi_charter",
        }
    })
    idx = compute_crossrefs(doc)
    assert idx.consumers_of("import:doi_charter")


def test_envelope_edge_emits_both_import_and_export_keys(doc):
    doc["credentials"]["exports"][0]["envelope"]["edges"].append({
        "edge_name": "authority",
        "credential_id": "carrier_license",
        "cardinality": "one",
        "operator": "authorizes",
    })
    idx = compute_crossrefs(doc)
    assert idx.consumers_of("export:carrier_license")
    assert idx.consumers_of("import:carrier_license")
