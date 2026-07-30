from keri_assistant.surface import Verb, CommandSurface, build_micro_app_surface
from tests.fixtures.sample_template import SAMPLE_TEMPLATE


def test_commands_and_projections_become_verbs():
    surf = build_micro_app_surface(SAMPLE_TEMPLATE)
    ids = {v.id for v in surf.verbs}
    assert "submit_quote" in ids
    assert "create_application" in ids
    assert "issued_credentials" in ids  # projection -> query verb


def test_never_verb_command_is_excluded():
    surf = build_micro_app_surface(SAMPLE_TEMPLATE)
    assert surf.by_id("rotate_signing_key") is None
    assert "/keri/cmd/rotate_key" not in surf.routes()


def test_never_verb_projection_is_structurally_excluded():
    # A1: the projections[] loop carries its OWN never-verb guard, not just commands[]'s -- the
    # look-alike above uses a *command* with a `/keri/cmd/rotate_key` route, which the commands[]
    # guard catches for an unrelated reason and would still pass even if this guard were deleted.
    surf = build_micro_app_surface({"commands": [], "projections": [{"id": "rotate"},
                                                                     {"id": "passcode"}]})
    assert surf.verbs == ()


def test_command_verb_fields():
    surf = build_micro_app_surface(SAMPLE_TEMPLATE)
    v = surf.by_id("submit_quote")
    assert v.route == "/insurance/cmd/submit_quote"
    assert v.kind == "exchange"
    assert v.schema_said == "ESchemaQuote0000000000000000000000000000000"
    assert v.counterparty_role == "broker"
    assert "quote" in v.phrasings and "submit" in v.phrasings


def test_projection_verb_is_query_kind():
    surf = build_micro_app_surface(SAMPLE_TEMPLATE)
    v = surf.by_id("issued_credentials")
    assert v.kind == "query"
    assert v.route == "/qry/issued_credentials"


def test_authz_is_carried_as_opaque_data_not_evaluated():
    surf = build_micro_app_surface(SAMPLE_TEMPLATE)
    v = surf.by_id("submit_quote")
    assert v.authz == {"method": "credential", "schema_said": "ESchemaQuote0000000000000000000000000000000"}


def test_routes_returns_frozenset_of_surviving_routes():
    surf = build_micro_app_surface(SAMPLE_TEMPLATE)
    assert surf.routes() == frozenset({
        "/insurance/cmd/submit_quote", "/insurance/cmd/create_application", "/qry/issued_credentials",
    })
