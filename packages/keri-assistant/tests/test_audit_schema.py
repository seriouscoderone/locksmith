from keri_assistant.audit_schema import unconstrained_entity_fields
from keri_assistant.grounding import Grounding
from keri_assistant.surface import build_micro_app_surface

DOI = "EDoi000000000000000000000000000000000000000"
G = Grounding(known_aids=frozenset({DOI}), allowed_schema_saids=frozenset())

TEMPLATE = {
    "commands": [{
        "id": "issue_record", "name": "issue", "route": "/dom/cmd/issue_record",
        "counterparty_role": "reviewer", "authz": {"method": "open"},
        "payload_schema": {
            "type": "object", "additionalProperties": False,
            "required": ["source_id", "subject_aid", "region"],
            "properties": {
                "source_id": {"type": "string"},        # documented as a SAID, escapes the convention
                "subject_aid": {"type": "string"},      # grounded
                "region": {"type": "string"},           # genuinely free text
                "note": {"type": "string"},             # optional, free text
            }}}],
}
SURF = build_micro_app_surface(TEMPLATE)


def test_reports_required_free_string_fields_that_no_rule_reaches():
    found = unconstrained_entity_fields(SURF, G)
    assert ("issue_record", "source_id") in found
    assert ("issue_record", "region") in found


def test_does_not_report_fields_the_grounding_already_constrains():
    assert ("issue_record", "subject_aid") not in unconstrained_entity_fields(SURF, G)


def test_does_not_report_optional_fields():
    # only required fields can force a signature over an invented value
    assert ("issue_record", "note") not in unconstrained_entity_fields(SURF, G)


def test_output_is_sorted_and_deterministic():
    found = unconstrained_entity_fields(SURF, G)
    assert list(found) == sorted(found)
    assert found == unconstrained_entity_fields(SURF, G)


def test_reports_nested_required_fields_by_path():
    surf = build_micro_app_surface({"commands": [{
        "id": "ingest", "name": "ingest", "route": "/ins/cmd/ingest", "authz": {},
        "payload_schema": {"type": "object", "additionalProperties": False, "required": ["wrap"],
                           "properties": {"wrap": {"type": "object", "additionalProperties": False,
                                                   "required": ["ref"],
                                                   "properties": {"ref": {"type": "string"}}}}}}]})
    assert ("ingest", "wrap.ref") in unconstrained_entity_fields(surf, G)


def test_query_verbs_are_not_reported():
    surf = build_micro_app_surface({"commands": [], "projections": [{"id": "b", "name": "B"}]})
    assert unconstrained_entity_fields(surf, G) == ()
