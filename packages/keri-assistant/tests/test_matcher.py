from keri_assistant.surface import build_micro_app_surface
from keri_assistant.matcher import match
from tests.fixtures.sample_template import SAMPLE_TEMPLATE

SURF = build_micro_app_surface(SAMPLE_TEMPLATE)


def test_confident_match_on_clear_phrasing():
    r = match("please submit the quote now", SURF)
    assert r.confident is True
    assert r.verb is not None and r.verb.id == "submit_quote"


def test_no_match_returns_none():
    r = match("what is the weather", SURF)
    assert r.verb is None
    assert r.confident is False
    assert r.candidates == ()


def test_query_projection_is_matchable():
    r = match("show issued credentials", SURF)
    assert r.confident is True
    assert r.verb.id == "issued_credentials"


def test_tie_is_not_confident_and_lists_candidates():
    # "create the application" and "submit the quote" share no token, so craft a real tie:
    # both "create_application" and "issued_credentials" match zero here; instead force a tie
    # by an utterance overlapping one token of two verbs.
    r = match("credentials application", SURF)
    # 'application' -> create_application (1), 'credentials' -> issued_credentials (1): tie at score 1
    assert r.confident is False
    assert {v.id for v in r.candidates} == {"create_application", "issued_credentials"}
