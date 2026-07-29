"""Pin the compiled surface for the sample template so accidental drift in the builder
(phrasings, routes, kinds, dropped verbs) is caught."""
from keri_assistant.surface import build_micro_app_surface
from tests.fixtures.sample_template import SAMPLE_TEMPLATE


def test_golden_surface_snapshot():
    surf = build_micro_app_surface(SAMPLE_TEMPLATE)
    snapshot = sorted(
        (v.id, v.route, v.kind, v.schema_said, v.counterparty_role, tuple(sorted(v.phrasings)))
        for v in surf.verbs
    )
    assert snapshot == [
        ("create_application", "/insurance/cmd/create_application", "exchange", None, None,
         ("application", "create")),
        ("issued_credentials", "/qry/issued_credentials", "query", None, None,
         ("credentials", "issued")),
        ("submit_quote", "/insurance/cmd/submit_quote", "exchange",
         "ESchemaQuote0000000000000000000000000000000", "broker",
         ("quote", "submit")),
    ]
