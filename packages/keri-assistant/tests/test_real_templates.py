"""The compiler must work on the real corpus, not just the synthetic fixture."""
import json
import pathlib

import pytest
from keri_assistant.actionschema import CLARIFY, UNSUPPORTED, build_proposal_schema
from keri_assistant.grounding import Grounding
from keri_assistant.surface import build_micro_app_surface

REAL = pathlib.Path(__file__).parent / "fixtures" / "real"
CARRIER = json.loads((REAL / "regulator_grants_carrier_license.json").read_text())
ACTUARY = json.loads((REAL / "actuary_attests_product_rating.json").read_text())

DOI = "EDoi000000000000000000000000000000000000000"


def _ids(schema):
    """The set of verb_id consts across `oneOf`, raising if two alternatives share one.

    A set comprehension silently COLLAPSES a duplicate const -- the same blind spot as the
    `_alts` dict helper in test_actionschema.py. See that file's `__`-prefix guard test.
    """
    consts = [a["properties"]["verb_id"]["const"] for a in schema["oneOf"]]
    assert len(consts) == len(set(consts)), f"duplicate verb_id const(s): {consts}"
    return set(consts)


def test_carrier_template_compiles_all_five_commands():
    surf = build_micro_app_surface(CARRIER)
    ids = {v.id for v in surf.verbs if v.kind == "exchange"}
    assert ids == {"grant_license", "spurn_application", "suspend_license",
                   "reinstate_license", "revoke_license"}


def test_revoke_license_is_present_the_defect_this_fixture_caught():
    surf = build_micro_app_surface(CARRIER)
    assert surf.by_id("revoke_license") is not None


def test_carrier_projections_become_query_verbs():
    surf = build_micro_app_surface(CARRIER)
    assert {v.id for v in surf.verbs if v.kind == "query"} == {
        "pending_applications", "active_licenses_in_state"}


def test_carrier_proposal_schema_grounds_every_receiver_and_payload_aid():
    surf = build_micro_app_surface(CARRIER)
    g = Grounding(known_aids=frozenset({DOI}), allowed_schema_saids=frozenset())
    schema = build_proposal_schema(surf, g)
    assert CLARIFY in _ids(schema) and UNSUPPORTED in _ids(schema)
    for alt in schema["oneOf"]:
        props = alt["properties"]
        if "receiver_aid" in props:
            assert props["receiver_aid"] == {"enum": [DOI]}
        payload_props = props.get("payload", {}).get("properties", {})
        for name, sub in payload_props.items():
            if name.lower().endswith("_aid"):
                assert sub == {"enum": [DOI]}, f"{name} left ungrounded"


def test_all_five_carrier_commands_compile_and_every_entity_field_is_grounded():
    # The sibling test above grounds only known_aids, so suspend/reinstate/revoke are (correctly)
    # omitted for want of a grounded license_said — leaving it sweeping just 2 of 5 commands. Ground
    # a credential SAID too so all five compile, and only then assert the "every entity field is
    # grounded" claim across the whole template.
    LICENSE = "ELicense00000000000000000000000000000000000"
    surf = build_micro_app_surface(CARRIER)
    g = Grounding(known_aids=frozenset({DOI}), allowed_schema_saids=frozenset(),
                  known_credential_saids=frozenset({LICENSE}))
    schema = build_proposal_schema(surf, g)
    compiled = _ids(schema) - {CLARIFY, UNSUPPORTED}
    assert compiled == {"grant_license", "spurn_application", "suspend_license",
                        "reinstate_license", "revoke_license"}
    for alt in schema["oneOf"]:
        for name, sub in alt["properties"].get("payload", {}).get("properties", {}).items():
            low = name.lower()
            if low == "aid" or low.endswith("_aid"):
                assert sub == {"enum": [DOI]}, f"{name} left ungrounded"
            elif low == "said" or low.endswith("_said"):
                assert sub == {"enum": [LICENSE]}, f"{name} left ungrounded"


def test_actuary_template_exercises_the_pinned_schema_said_path():
    surf = build_micro_app_surface(ACTUARY)
    pinned = [v for v in surf.verbs if v.schema_said is not None]
    assert pinned, "expected credential-gated commands to carry a pinned schema_said"
    said = pinned[0].schema_said
    g = Grounding(known_aids=frozenset({DOI}), allowed_schema_saids=frozenset({said}))
    alt = {a["properties"]["verb_id"]["const"]: a
           for a in build_proposal_schema(surf, g)["oneOf"]}[pinned[0].id]
    assert alt["properties"]["schema_said"] == {"const": said}


def test_actuary_commands_are_omitted_when_their_schema_is_not_grounded():
    surf = build_micro_app_surface(ACTUARY)
    empty = Grounding(known_aids=frozenset({DOI}), allowed_schema_saids=frozenset())
    ids = _ids(build_proposal_schema(surf, empty))
    for verb in surf.verbs:
        if verb.kind == "exchange" and verb.schema_said is not None:
            assert verb.id not in ids


def test_authz_credential_method_is_carried_verbatim_as_opaque_data_on_the_verb():
    # I-3: this checks CARRIAGE only -- that authz survives onto the Verb unmodified -- not that
    # the compiler never READS/evaluates it (schema_said IS read, legitimately, to pin a const;
    # see test_proposal_invariants.test_authz_method_and_issuer_are_never_read_only_schema_said_
    # is_read_to_pin_a_const for the actual never-read invariant, swept and asserted there).
    surf = build_micro_app_surface(ACTUARY)
    gated = [v for v in surf.verbs if v.authz.get("method") == "credential"]
    assert gated, "expected credential-gated commands"
    assert "issuer" in gated[0].authz     # carried verbatim as opaque data
