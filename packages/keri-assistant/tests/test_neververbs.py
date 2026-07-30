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


def test_override_is_additive_and_cannot_weaken_the_framework_floor():
    # a caller passing a non-superset must NOT be able to re-enable a floor operation
    assert is_never_verb("/keri/cmd/rotate_key", frozenset({"license"})) is True
    assert is_never_verb("/vault/seed_display", frozenset()) is True
    # and adding still works
    assert is_never_verb("/insurance/cmd/revoke_license", frozenset({"license"})) is True


@pytest.mark.parametrize("route", [
    "/keri/cmd/rot",
    "/x/dip",
    "/y/drt",
])
def test_bare_keri_short_codes_are_individually_blocked(route):
    # "rot"/"dip"/"drt" are the real KERI event-type codes (plain rotation, delegated inception,
    # delegated rotation) -- distinct tokens from the longhand "rotate"/"delegate" above, and each
    # is load-bearing on its own: removing any ONE of them from NEVER_VERB_TOKENS left the whole
    # suite green before this test existed, because nothing else exercised a bare short code.
    assert is_never_verb(route) is True
