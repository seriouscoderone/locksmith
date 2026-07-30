from keri_assistant.audit_schema import claimed_credential_refs, unconstrained_entity_fields
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


# --- claimed_credential_refs: the higher-confidence filter over the same candidate set ---
# unconstrained_entity_fields lists EVERY required free string a rule doesn't reach -- most of
# those are genuinely free text, and a human reviewer can't read a 55-row list to find the one
# real gap. claimed_credential_refs narrows to fields the TEMPLATE ITSELF claims are credential
# references, via two independent signals: (A) the field's own description names a SAID/digest/
# self-addressing identifier; (B) an undescribed field shares its leaf name with an (A) hit
# elsewhere in the same surface -- the same reference, missing the prose this time.

CLAIM_TEMPLATE = {
    "commands": [
        {
            "id": "issue_record", "name": "issue", "route": "/dom/cmd/issue_record",
            "authz": {"method": "open"},
            "payload_schema": {
                "type": "object", "additionalProperties": False,
                "required": ["source_id", "region"],
                "properties": {
                    "source_id": {"type": "string",
                                  "description": "SAID of the source record this issuance is based on."},
                    "region": {"type": "string"},  # free text, no SAID claim, no shared name
                }}},
        {
            "id": "amend_record", "name": "amend", "route": "/dom/cmd/amend_record",
            "authz": {"method": "open"},
            "payload_schema": {
                "type": "object", "additionalProperties": False,
                "required": ["source_id"],
                "properties": {
                    "source_id": {"type": "string"},  # undescribed twin of the A hit above
                }}},
    ],
}
CLAIM_SURF = build_micro_app_surface(CLAIM_TEMPLATE)


def test_a_field_described_as_a_said_is_reported_via_signal_a():
    found = claimed_credential_refs(CLAIM_SURF, G)
    assert ("issue_record", "source_id", "described as a SAID") in found


def test_an_undescribed_field_sharing_a_claimed_name_is_reported_via_signal_b():
    found = claimed_credential_refs(CLAIM_SURF, G)
    assert ("amend_record", "source_id",
            "shares a name with issue_record.source_id, which is described as a SAID") in found


def test_a_field_with_no_claiming_description_and_no_claiming_twin_is_not_reported():
    # region is free text with no SAID claim anywhere in the surface -- unconstrained_entity_fields
    # still lists it (that's the whole-list visibility), but the higher-confidence filter is right
    # to stay silent: nothing in the template claims it is a credential reference.
    found = claimed_credential_refs(CLAIM_SURF, G)
    assert not any(f[0] == "issue_record" and f[1] == "region" for f in found)
    assert ("issue_record", "region") in unconstrained_entity_fields(CLAIM_SURF, G)


def test_claimed_credential_refs_never_widens_beyond_unconstrained_entity_fields():
    pairs = {(v, p) for v, p, _ in claimed_credential_refs(CLAIM_SURF, G)}
    assert pairs <= set(unconstrained_entity_fields(CLAIM_SURF, G))


def test_a_field_already_grounded_by_name_is_not_reported_even_if_described_as_a_said():
    # a *_said field is already reached by grounded_set_for -- not a gap, regardless of what its
    # own description says
    surf = build_micro_app_surface({"commands": [{
        "id": "attest", "name": "attest", "route": "/dom/cmd/attest", "authz": {},
        "payload_schema": {"type": "object", "additionalProperties": False,
                           "required": ["subject_said"],
                           "properties": {"subject_said": {
                               "type": "string",
                               "description": "SAID of the subject credential."}}}}]})
    assert claimed_credential_refs(surf, G) == ()


# --- a required ARRAY of plain strings must be reached too, not just scalar strings ---
# The module docstring names a plural `_saids` field as the DECISIVE naming-convention miss
# precisely because `*_said` matches a scalar field name, not an array one -- and an array is the
# natural shape for such a plural. A detector that only reported `type: "string"` leaves would be
# structurally blind to exactly the shape its own docstring calls decisive. Covered synthetically
# here because neither vendored template happens to contain a plural `_saids` field -- see
# test_loop_real_templates.py for the explicit assertion pinning that fact against the real corpus.

def test_a_required_array_of_strings_named_as_a_plural_said_is_reported_by_both_functions():
    surf = build_micro_app_surface({"commands": [{
        "id": "seal", "name": "seal", "route": "/dom/cmd/seal", "authz": {},
        "payload_schema": {"type": "object", "additionalProperties": False,
                           "required": ["declaration_saids"],
                           "properties": {"declaration_saids": {
                               "type": "array",
                               "description": "Every declaration SAID the sub-manifest commits to.",
                               "items": {"type": "string"}}}}}]})
    assert ("seal", "declaration_saids") in unconstrained_entity_fields(surf, G)
    found = claimed_credential_refs(surf, G)
    assert ("seal", "declaration_saids", "described as a SAID") in found


def test_a_required_array_of_strings_with_an_enum_on_items_is_not_reported():
    # already constrained -- an enum on the array's items closes it exactly as an enum on a scalar
    # string field would
    surf = build_micro_app_surface({"commands": [{
        "id": "classify", "name": "classify", "route": "/dom/cmd/classify", "authz": {},
        "payload_schema": {"type": "object", "additionalProperties": False,
                           "required": ["kinds"],
                           "properties": {"kinds": {
                               "type": "array",
                               "items": {"type": "string", "enum": ["a", "b"]}}}}}]})
    assert unconstrained_entity_fields(surf, G) == ()
