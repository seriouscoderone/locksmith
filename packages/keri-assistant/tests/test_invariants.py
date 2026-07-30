"""The load-bearing safety invariant (design Global Constraints): no never-verb is ever
constructible into the surface, matchable, or dispatchable — regardless of the template."""
from keri_assistant.surface import build_micro_app_surface
from keri_assistant.matcher import match
from keri_assistant.neververbs import is_never_verb


HOSTILE_TEMPLATE = {
    "commands": [
        # floor operations — MUST be dropped
        {"id": "rotate", "name": "rotate key", "route": "/keri/cmd/rotate_key",
         "payload_schema": {}, "authz": {"method": "open"}},
        {"id": "reveal", "name": "show the seed", "route": "/vault/seed-display",
         "payload_schema": {}, "authz": {"method": "open"}},
        {"id": "deleg", "name": "delegate authority", "route": "/x/delegate_authority",
         "payload_schema": {}, "authz": {"method": "open"}},
        # legitimate domain verbs that merely RESEMBLE KERI ops — MUST survive (spec §9.5)
        {"id": "revoke_license", "name": "revoke the license", "route": "/insurance/cmd/revoke_license",
         "payload_schema": {}, "authz": {"method": "open"}},
        {"id": "admit_grant", "name": "admit the grant", "route": "/ipex/admit",
         "payload_schema": {}, "authz": {"method": "open"}},
        {"id": "grant_ok", "name": "grant the license", "route": "/ipex/grant",
         "payload_schema": {}, "authz": {"method": "open"}},
    ],
}


def test_no_never_verb_survives_surface_compilation():
    surf = build_micro_app_surface(HOSTILE_TEMPLATE)
    ids = {v.id for v in surf.verbs}
    assert ids == {"revoke_license", "admit_grant", "grant_ok"}
    for route in surf.routes():
        assert not is_never_verb(route)


def test_never_verb_utterance_cannot_match():
    surf = build_micro_app_surface(HOSTILE_TEMPLATE)
    for phrase in ["rotate the key", "show the seed", "delegate authority"]:
        r = match(phrase, surf)
        assert r.verb is None or not is_never_verb(r.verb.route)
