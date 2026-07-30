"""Load-bearing guarantees of the grounded proposal schema (design spec 4.1/7/8.1)."""
import pytest
from keri_assistant.actionschema import CLARIFY, UNSUPPORTED, build_proposal_schema
from keri_assistant.enforcement import EnforcementStrength, SoftEnforcementError, require_hard
from keri_assistant.grounding import Grounding
from keri_assistant.neververbs import is_never_verb
from keri_assistant.proposal import GrammarViolation, parse_proposal
from keri_assistant.surface import build_micro_app_surface

HOSTILE_TEMPLATE = {
    "commands": [
        # framework-floor operations (own key material / secrets) — MUST be excluded
        {"id": "rotate", "name": "rotate key", "route": "/keri/cmd/rotate_key",
         "payload_schema": {}, "authz": {"method": "open"}},
        {"id": "reveal", "name": "show the seed", "route": "/vault/seed-display",
         "payload_schema": {}, "authz": {"method": "open"}},
        {"id": "deleg", "name": "delegate authority", "route": "/x/delegate_authority",
         "payload_schema": {}, "authz": {"method": "open"}},
        # legitimate domain verbs that merely RESEMBLE KERI ops — MUST be proposable (spec §9.5)
        {"id": "revoke_license", "name": "revoke the license",
         "route": "/insurance/cmd/revoke_license", "payload_schema": {}, "authz": {"method": "open"}},
        {"id": "admit_grant", "name": "admit the grant", "route": "/ipex/admit",
         "payload_schema": {}, "authz": {"method": "open"}},
        {"id": "grant_ok", "name": "grant the license", "route": "/ipex/grant",
         "payload_schema": {}, "authz": {"method": "open"}},
    ],
}
G_ANY = Grounding(known_aids=frozenset({"EAid00000000000000000000000000000000000000"}),
                  allowed_schema_saids=frozenset())


def _ids(schema):
    return {a["properties"]["verb_id"]["const"] for a in schema["oneOf"]}


def test_floor_operations_cannot_appear_as_proposal_alternatives():
    surf = build_micro_app_surface(HOSTILE_TEMPLATE)
    ids = _ids(build_proposal_schema(surf, G_ANY))
    assert ids == {"revoke_license", "admit_grant", "grant_ok", CLARIFY, UNSUPPORTED}
    for verb in surf.verbs:
        assert not is_never_verb(verb.route)


def test_domain_verbs_resembling_keri_ops_ARE_proposable():
    # regression guard for the real defect: /insurance/cmd/revoke_license was silently dropped
    surf = build_micro_app_surface(HOSTILE_TEMPLATE)
    p = parse_proposal({"verb_id": "revoke_license", "payload": {}}, surf, G_ANY)
    assert p.status == "intent"
    assert p.intent.route == "/insurance/cmd/revoke_license"


def test_a_floor_verb_proposal_cannot_be_parsed_even_if_a_backend_emits_one():
    surf = build_micro_app_surface(HOSTILE_TEMPLATE)
    for forged in ("rotate", "reveal", "deleg"):
        with pytest.raises(GrammarViolation):
            parse_proposal({"verb_id": forged, "payload": {}}, surf, G_ANY)


def test_every_receiver_enum_in_the_schema_contains_only_grounded_aids():
    surf = build_micro_app_surface(HOSTILE_TEMPLATE)
    schema = build_proposal_schema(surf, G_ANY)
    for alt in schema["oneOf"]:
        enum = alt["properties"].get("receiver_aid", {}).get("enum")
        if enum is not None:
            assert set(enum) <= set(G_ANY.known_aids)
            assert enum, "an empty enum is unsatisfiable — the alternative should be omitted"


def test_authority_bearing_proposals_refuse_soft_enforcement():
    require_hard(EnforcementStrength.HARD)          # allowed
    with pytest.raises(SoftEnforcementError):
        require_hard(EnforcementStrength.SOFT)      # refused


def test_authz_is_never_interpreted_by_the_schema_compiler():
    # two templates identical except for authz method must compile to the same schema
    import copy
    a = copy.deepcopy(HOSTILE_TEMPLATE)
    b = copy.deepcopy(HOSTILE_TEMPLATE)
    b["commands"][3]["authz"] = {"method": "credential", "issuer": "EWhoever"}
    sa = build_proposal_schema(build_micro_app_surface(a), G_ANY)
    sb = build_proposal_schema(build_micro_app_surface(b), G_ANY)
    assert sa == sb
