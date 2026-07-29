"""The load-bearing safety invariant (design Global Constraints): no never-verb is ever
constructible into the surface, matchable, or dispatchable — regardless of the template."""
from keri_assistant.surface import build_micro_app_surface
from keri_assistant.matcher import match
from keri_assistant.neververbs import is_never_verb


HOSTILE_TEMPLATE = {
    "commands": [
        {"id": "rotate", "name": "rotate key", "route": "/keri/cmd/rotate_key",
         "payload_schema": {}, "authz": {"method": "open"}},
        {"id": "revoke", "name": "revoke it", "route": "/x/revoke_credential",
         "payload_schema": {}, "authz": {"method": "open"}},
        {"id": "admit", "name": "admit the grant", "route": "/ipex/admit",
         "payload_schema": {}, "authz": {"method": "open"}},
        {"id": "grant", "name": "grant the license", "route": "/ipex/grant",
         "payload_schema": {}, "authz": {"method": "open"}},
    ],
}


def test_no_never_verb_survives_surface_compilation():
    surf = build_micro_app_surface(HOSTILE_TEMPLATE)
    ids = {v.id for v in surf.verbs}
    assert ids == {"grant"}  # rotate/revoke/admit all dropped
    for route in surf.routes():
        assert not is_never_verb(route)


def test_never_verb_utterance_cannot_match():
    surf = build_micro_app_surface(HOSTILE_TEMPLATE)
    for phrase in ["rotate the key", "revoke it", "admit the grant"]:
        r = match(phrase, surf)
        assert r.verb is None or not is_never_verb(r.verb.route)
