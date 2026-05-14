import json
from pathlib import Path


FIXTURE = (Path(__file__).parent / "fixtures"
           / "regulator-grants-carrier-license.json")


def test_fixture_has_four_commands():
    doc = json.loads(FIXTURE.read_text())
    ids = {c["id"] for c in doc["commands"]}
    assert ids == {"grant_license", "suspend_license",
                   "reinstate_license", "revoke_license"}


def test_fixture_has_two_reactions():
    doc = json.loads(FIXTURE.read_text())
    ids = {r["id"] for r in doc["reactions"]}
    assert ids == {"on_application_received", "on_application_withdrawn"}


def test_fixture_has_three_workflows():
    doc = json.loads(FIXTURE.read_text())
    ids = {w["id"] for w in doc["workflows"]}
    assert ids == {"license_grant_workflow",
                   "license_suspension_workflow",
                   "license_revocation_workflow"}


def test_fixture_has_two_projections():
    doc = json.loads(FIXTURE.read_text())
    ids = {p["id"] for p in doc["projections"]}
    assert ids == {"pending_applications", "active_licensees"}


def test_fixture_has_seven_rules_spanning_four_types():
    doc = json.loads(FIXTURE.read_text())
    assert len(doc["rules"]) == 7
    types = {r["type"] for r in doc["rules"]}
    assert types == {"legal_prose", "predicate", "validation", "binding_link"}


def test_fixture_validates_against_meta_schema():
    from locksmith.micro_app_template.validate import validate_template
    doc = json.loads(FIXTURE.read_text())
    schema_path = (Path(__file__).parents[3] / "docs" / "superpowers"
                   / "specs" / "schemas" / "micro-app-template.schema.json")
    result = validate_template(doc, schema_path)
    assert result.is_valid, f"unexpected validation errors: {result.errors}"
