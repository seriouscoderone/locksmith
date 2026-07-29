import pytest
from keri_assistant.neververbs import is_never_verb, NEVER_VERB_TOKENS


@pytest.mark.parametrize("route", [
    "/keri/cmd/rotate_key",
    "/x/revoke_credential",
    "/ipex/admit",
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
])
def test_allowed_verbs_not_flagged(route):
    assert is_never_verb(route) is False


def test_token_set_includes_admit_per_reconciliation_note():
    assert "admit" in NEVER_VERB_TOKENS  # spec §9.5: human-only until reconciled
