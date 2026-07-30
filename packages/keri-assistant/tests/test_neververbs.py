import pytest
from keri_assistant.neververbs import is_never_verb, NEVER_VERB_TOKENS


@pytest.mark.parametrize("route", [
    "/keri/cmd/rotate_key",
    "/vault/seed_display",
    "/y/delegate_authority",
])
def test_never_verbs_detected(route):
    assert is_never_verb(route) is True


@pytest.mark.parametrize("route", [
    "/ipex/grant",
    "/ipex/apply",
    "/insurance/cmd/submit_quote",
    "/qry/issued_credentials",
    "/x/revoke_credential",
    "/ipex/admit",
])
def test_allowed_verbs_not_flagged(route):
    assert is_never_verb(route) is False


def test_domain_verbs_that_merely_resemble_keri_ops_are_allowed():
    # spec §9.5: revoke/rev/admit are legitimate domain verbs, not never-verbs
    assert "revoke" not in NEVER_VERB_TOKENS
    assert "rev" not in NEVER_VERB_TOKENS
    assert "admit" not in NEVER_VERB_TOKENS


@pytest.mark.parametrize("route", [
    "/x/delegate-authority",
    "/keri/cmd/rotate-key",
])
def test_hyphenated_routes_are_detected(route):
    assert is_never_verb(route) is True


def test_allowed_hyphenated_route_not_flagged():
    assert is_never_verb("/insurance/cmd/submit-quote") is False


def test_the_real_regulator_revoke_license_command_survives():
    # this exact route was silently dropped before the floor was narrowed
    assert is_never_verb("/insurance/cmd/revoke_license") is False
    assert is_never_verb("/ipex/admit") is False


def test_own_key_material_and_secrets_are_still_blocked():
    for route in ("/keri/cmd/rotate_key", "/x/rotate-keys", "/vault/seed_display",
                  "/v/passcode", "/y/delegate_authority", "/z/recover_account"):
        assert is_never_verb(route) is True, route


def test_token_set_is_caller_overridable_for_a_later_application_tier():
    extra = NEVER_VERB_TOKENS | {"license"}
    assert is_never_verb("/insurance/cmd/revoke_license", extra) is True   # app-tier restriction
    assert is_never_verb("/insurance/cmd/revoke_license") is False         # default floor unchanged
