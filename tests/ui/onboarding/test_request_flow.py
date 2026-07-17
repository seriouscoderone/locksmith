# -*- encoding: utf-8 -*-
"""Tests for `locksmith.ui.onboarding.request_flow.RequestFlow` (Plan B
Task 8): the persona-pick-to-presented-application controller behind
`OnboardingHomePage.on_submit`.

`EgfSeeder`/`ServiceaidIssueDoer`/`ServiceaidGrantDoer` are all monkeypatched
to capturing fakes (mirroring `tests/core/test_egf_seeding.py`'s pattern for
`LoadSchemaDoer`) -- these tests pin RequestFlow's OWN orchestration
(argument shapes, ordering, error handling), not the already-tested
behavior of the modules it calls. `app.vault.signals` is a REAL
`DoerSignalBridge` (not a MagicMock) in every test that exercises the
credential_issued -> grant-doer hand-off, since a mocked Signal never
actually invokes connected slots on `.emit()` -- only a real Qt signal does.

Also covers the window-wiring gate (Task 8's other half): a source-inspection
test (B4 pattern -- see `tests/core/test_bootstrapping_overrides.py`) that
the onboarding "home" page registration in `LocksmithWindow.__init__` is
gated on BOTH `brand().onboarding_enabled` and a non-None
`make_hoa_resolver(...)` result.
"""
import inspect
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from keri_serviceaid.egf.documents import EgfDocument
from keri_serviceaid.tests.egf.fixtures.make_fixture_egf import fixture_egf

import locksmith.ui.onboarding.request_flow as request_flow
from locksmith.core.signals import DoerSignalBridge
from locksmith.ui.onboarding.request_flow import RequestFlow

GRANT_SAID = "E" + "L" * 43        # "lic" credential's schema_said in fixture_egf()
APPLICATION_SAID = "E" + "P" * 43  # "app" credential's schema_said == plan.registry_name
MICRO_APP_SAID = "E" + "M" * 43
UT_AID = "E" + "U" * 43            # bootstrap-phase "UT DOI" authority's aid
CA_AID = "E" + "C" * 43            # production-phase "CA DOI" authority's aid
DEFAULT_HAB_PRE = "E" + "D" * 43

PAYLOAD_SCHEMA = {
    "type": "object",
    "properties": {"applicant_legal_name": {"type": "string", "minLength": 1}},
    "required": ["applicant_legal_name"],
}

MICRO_APP = {
    "d": MICRO_APP_SAID,
    "commands": [{"id": "submit_application", "payload_schema": PAYLOAD_SCHEMA}],
}

VALID_PAYLOAD = {"applicant_legal_name": "Acme Mutual"}
VALID_CONTEXT = {"jurisdiction": "US-UT"}


class FakeResolver:
    """Stands in for `EgfResolver`: only `resolve_micro_app` is used by
    `derive_request` (schema resolution is EgfSeeder's job, and EgfSeeder
    itself is monkeypatched below)."""

    def resolve_micro_app(self, said):
        assert said == MICRO_APP_SAID
        return MICRO_APP


def _egf_doc() -> EgfDocument:
    _, sad = fixture_egf()
    return EgfDocument.from_sad(sad)


class Env:
    """Shared harness: a MagicMock app with a REAL `DoerSignalBridge` for
    `vault.signals` (needed for the credential_issued round trip), a fake
    default hab, and monkeypatched `EgfSeeder`/`ServiceaidIssueDoer`/
    `ServiceaidGrantDoer` that capture constructor kwargs instead of doing
    real work."""

    def __init__(self, monkeypatch):
        self.egf_doc = _egf_doc()
        self.resolver = FakeResolver()
        self.hab = SimpleNamespace(pre=DEFAULT_HAB_PRE)

        self.app = MagicMock(name="app")
        self.signals = DoerSignalBridge()
        self.app.vault.signals = self.signals
        self.app.vault.hby.habByName.return_value = self.hab

        self.seeder_calls: list = []
        env = self

        class FakeSeeder:
            def __init__(_self, app, resolver, egf_doc):
                _self.app, _self.resolver, _self.egf_doc = app, resolver, egf_doc

            def seed_for_role(_self, role_id, issuer_aid=None):
                env.seeder_calls.append((role_id, issuer_aid))

        monkeypatch.setattr(request_flow, "EgfSeeder", FakeSeeder)

        self.issued: list = []
        self.granted: list = []

        class FakeIssueDoer:
            def __init__(_self, app, **kwargs):
                _self.kwargs = kwargs
                env.issued.append(_self)

        class FakeGrantDoer:
            def __init__(_self, app, **kwargs):
                _self.kwargs = kwargs
                env.granted.append(_self)

        monkeypatch.setattr(request_flow, "ServiceaidIssueDoer", FakeIssueDoer)
        monkeypatch.setattr(request_flow, "ServiceaidGrantDoer", FakeGrantDoer)

        self.extended: list = []
        self.app.vault.extend.side_effect = lambda doers: self.extended.extend(doers)

        self.failures: list = []
        self.signals.doer_event.connect(self._capture_failure)

    def _capture_failure(self, doer_name, event_type, data):
        if event_type == "request_failed":
            self.failures.append((doer_name, event_type, data))

    def flow(self, accept_phases=("bootstrap", "production")) -> RequestFlow:
        return RequestFlow(self.app, self.resolver, self.egf_doc, accept_phases)

    def emit_issued(self, said: str, schema_said: str = APPLICATION_SAID) -> None:
        self.signals.doer_event.emit(
            "IssueCredentialDoer", "credential_issued", {"said": said, "schema_said": schema_said},
        )

    def emit_issuance_failed(self, schema_said: str = APPLICATION_SAID) -> None:
        # Mirrors ServiceaidIssueDoer's real except-path event shape
        # (serviceaid_bridge.py) -- notably it carries the SAME
        # "schema_said" key the success event does.
        self.signals.doer_event.emit(
            "IssueCredentialDoer", "credential_issuance_failed",
            {"error": "boom", "schema_said": schema_said,
             "recipient_pre": DEFAULT_HAB_PRE, "success": False},
        )


@pytest.fixture
def env(monkeypatch):
    return Env(monkeypatch)


def test_submit_happy_path_schedules_issue_doer_with_application_schema_and_registry(env):
    flow = env.flow()
    flow.submit("carrier", dict(VALID_PAYLOAD), dict(VALID_CONTEXT))

    assert env.seeder_calls == [("carrier", DEFAULT_HAB_PRE)]
    assert len(env.issued) == 1
    kwargs = env.issued[0].kwargs
    assert kwargs["schema_said"] == APPLICATION_SAID
    assert kwargs["registry_name"] == APPLICATION_SAID
    assert kwargs["recipient"] == DEFAULT_HAB_PRE  # self-issued: recipient == issuer
    assert kwargs["attributes"] == VALID_PAYLOAD
    assert env.extended == [env.issued[0]]
    assert env.granted == []  # not yet -- no credential_issued event fired
    assert env.failures == []


def test_credential_issued_event_schedules_grant_doer_for_utah_authority(env):
    flow = env.flow()
    flow.submit("carrier", dict(VALID_PAYLOAD), dict(VALID_CONTEXT))

    env.emit_issued("Ecred1")

    assert len(env.granted) == 1
    kwargs = env.granted[0].kwargs
    assert kwargs["credential_said"] == "Ecred1"
    assert kwargs["recipient"] == UT_AID
    assert kwargs["hab_pre"] == DEFAULT_HAB_PRE
    assert env.granted[0] in env.extended


def test_credential_issued_listener_is_one_shot_no_double_grant(env):
    """A SECOND credential_issued event for the SAME schema (e.g. a later
    application after a rejected first one) must NOT schedule a second
    grant doer -- the listener disconnects itself after firing once."""
    flow = env.flow()
    flow.submit("carrier", dict(VALID_PAYLOAD), dict(VALID_CONTEXT))

    env.emit_issued("Ecred1")
    env.emit_issued("Ecred2")

    assert len(env.granted) == 1
    assert env.granted[0].kwargs["credential_said"] == "Ecred1"


def test_failure_then_retry_grants_exactly_once_with_retry_authority(env):
    """The listener-leak regression (review fix round 1): a FAILED issuance
    must retire its listener. Otherwise a retry submit()'s single success
    event fires BOTH listeners -- two grant doers, one carrying the STALE
    first attempt's authority. The two submits use two different authority
    contexts (US-UT bootstrap vs US-CA production) to discriminate which
    attempt's authority the grant carries."""
    flow = env.flow()
    flow.submit("carrier", dict(VALID_PAYLOAD), {"jurisdiction": "US-UT"})
    env.emit_issuance_failed()  # first attempt's issuance fails

    flow.submit("carrier", dict(VALID_PAYLOAD), {"jurisdiction": "US-CA"})  # retry
    env.emit_issued("Ecred-retry")

    assert len(env.granted) == 1, "retry's success must schedule exactly ONE grant doer"
    assert env.granted[0].kwargs["recipient"] == CA_AID  # the RETRY's authority, not UT
    assert env.granted[0].kwargs["credential_said"] == "Ecred-retry"


def test_new_submit_disconnects_stale_pending_listener(env):
    """Latest-submission-wins: a second submit() for the same role (with
    neither a success nor a failure event in between) must evict the first
    submit()'s still-pending listener -- one success event afterward
    schedules exactly ONE grant doer, carrying the SECOND submit's
    authority."""
    flow = env.flow()
    flow.submit("carrier", dict(VALID_PAYLOAD), {"jurisdiction": "US-UT"})
    flow.submit("carrier", dict(VALID_PAYLOAD), {"jurisdiction": "US-CA"})

    env.emit_issued("Ecred1")

    assert len(env.granted) == 1
    assert env.granted[0].kwargs["recipient"] == CA_AID


def test_credential_issued_for_grant_schema_does_not_trigger_grant(env):
    """schema_said discriminator: a correctly-shaped credential_issued event
    whose schema_said is the GRANT credential's (not the application's) must
    NOT trigger the grant doer -- and must leave the listener pending, so
    the real application-schema event still fires it."""
    flow = env.flow()
    flow.submit("carrier", dict(VALID_PAYLOAD), dict(VALID_CONTEXT))

    env.emit_issued("Ex", schema_said=GRANT_SAID)
    assert env.granted == []

    env.emit_issued("Ecred1")  # the application schema -- the real match
    assert len(env.granted) == 1
    assert env.granted[0].kwargs["credential_said"] == "Ecred1"


def test_unrelated_events_before_match_are_ignored(env):
    flow = env.flow()
    flow.submit("carrier", dict(VALID_PAYLOAD), dict(VALID_CONTEXT))

    env.signals.doer_event.emit(
        "SomeOtherDoer", "credential_issued", {"said": "Ex", "schema_said": APPLICATION_SAID},
    )
    env.signals.doer_event.emit(
        "IssueCredentialDoer", "credential_issuance_failed", {"error": "boom"},
    )
    assert env.granted == []

    env.emit_issued("Ecred1")
    assert len(env.granted) == 1


def test_submit_invalid_payload_emits_request_failed_and_schedules_nothing(env):
    flow = env.flow()
    flow.submit("carrier", {}, dict(VALID_CONTEXT))  # missing applicant_legal_name

    assert env.issued == []
    assert env.seeder_calls == []
    assert len(env.failures) == 1
    assert "applicant_legal_name" in env.failures[0][2]["message"]


def test_submit_no_matching_authority_emits_request_failed_mentioning_authority(env):
    flow = env.flow()
    flow.submit("carrier", dict(VALID_PAYLOAD), {"jurisdiction": "US-XX"})

    assert env.issued == []
    assert len(env.failures) == 1
    assert "authority" in env.failures[0][2]["message"]


def test_submit_shared_dim_none_context_emits_request_failed_and_schedules_nothing(env):
    """B6 carry-forward: a shared context dimension resolving to None (e.g.
    a payload-shape mismatch in _dotted_get) must be treated as a
    validation error, never handed to select_authority."""
    flow = env.flow()
    flow.submit("carrier", dict(VALID_PAYLOAD), {"jurisdiction": None})

    assert env.issued == []
    assert env.seeder_calls == []
    assert len(env.failures) == 1
    assert "jurisdiction" in env.failures[0][2]["message"]


def test_submit_no_default_hab_emits_request_failed(env):
    env.app.vault.hby.habByName.return_value = None
    flow = env.flow()
    flow.submit("carrier", dict(VALID_PAYLOAD), dict(VALID_CONTEXT))

    assert env.issued == []
    assert len(env.failures) == 1
    assert "default identifier" in env.failures[0][2]["message"]


def test_submit_autofills_missing_date_time_property_before_validating(env):
    """The real insurance EGF's carrier submit_application schema marks
    `submitted_at` (format: date-time) required AND client-supplied, with
    no form field ever rendered for it (SchemaFormBuilder hides date-time
    fields -- see form_builder.py's hidden_autofill_fields()). RequestFlow
    must autofill it before validate_payload runs, or every real submission
    would fail validation for a field nothing ever populates."""
    schema_with_dt = {
        "type": "object",
        "properties": {
            "applicant_legal_name": {"type": "string", "minLength": 1},
            "submitted_at": {"type": "string", "format": "date-time"},
        },
        "required": ["applicant_legal_name", "submitted_at"],
    }
    micro_app = {
        "d": MICRO_APP_SAID,
        "commands": [{"id": "submit_application", "payload_schema": schema_with_dt}],
    }

    class ResolverWithDt:
        def resolve_micro_app(self, said):
            return micro_app

    flow = RequestFlow(env.app, ResolverWithDt(), env.egf_doc, ("bootstrap", "production"))
    flow.submit("carrier", {"applicant_legal_name": "Acme Mutual"}, dict(VALID_CONTEXT))

    assert env.failures == []
    assert len(env.issued) == 1
    attrs = env.issued[0].kwargs["attributes"]
    assert attrs["applicant_legal_name"] == "Acme Mutual"
    assert attrs.get("submitted_at")  # non-empty ISO string, autofilled


def test_seed_all_personas_seeds_every_onboardable_role_with_default_hab(env):
    flow = env.flow()
    flow.seed_all_personas()
    # "carrier" is the only onboardable role (with an `onboarding` block) in fixture_egf().
    assert env.seeder_calls == [("carrier", DEFAULT_HAB_PRE)]


def test_seed_all_personas_seeds_schema_only_when_no_default_hab_yet(env):
    env.app.vault.hby.habByName.return_value = None
    flow = env.flow()
    flow.seed_all_personas()
    assert env.seeder_calls == [("carrier", None)]


# ---------------------------------------------------------------------------
# Window wiring: held_provider None-guard + source-inspection test (B4 pattern)
# ---------------------------------------------------------------------------

def test_onboarding_held_provider_guards_vault_none():
    """OnboardingHomePage.__init__ calls refresh() -> held_provider at
    window-construction time, BEFORE any vault is open (app.vault is None).
    The provider must return [] then -- not crash on
    PluginManager._held_credentials(None) -- and delegate to the real
    projection once a vault IS open."""
    from locksmith.ui.window import _onboarding_held_credentials

    app = MagicMock()
    app.vault = None
    assert _onboarding_held_credentials(app) == []
    app.plugin_manager._held_credentials.assert_not_called()

    vault = MagicMock(name="vault")
    app.vault = vault
    held = [object()]
    app.plugin_manager._held_credentials.return_value = held
    assert _onboarding_held_credentials(app) is held
    app.plugin_manager._held_credentials.assert_called_once_with(vault)

def test_window_registers_onboarding_home_gated_on_enabled_and_resolver():
    """`LocksmithWindow.__init__` must only construct/register the
    onboarding "home" page when BOTH `brand().onboarding_enabled` is true
    AND `make_hoa_resolver(brand())` resolved a non-None (resolver,
    egf_doc) pair -- a non-onboarding or non-HOA brand must never
    construct a RequestFlow/OnboardingHomePage at all. Source-inspection,
    not a live construction, mirrors `tests/core/test_bootstrapping_
    overrides.py`'s precedent (a full `LocksmithWindow` needs a live
    QApplication + full plugin discovery to construct)."""
    from locksmith.ui.window import LocksmithWindow

    source = inspect.getsource(LocksmithWindow.__init__)

    onboarding_idx = source.index("onboarding_enabled")
    register_idx = source.index('register_page("home"')
    resolver_idx = source.index("make_hoa_resolver(")

    assert onboarding_idx < register_idx, (
        "register_page(\"home\", ...) must be gated behind an "
        "onboarding_enabled check"
    )
    assert resolver_idx < register_idx, (
        "register_page(\"home\", ...) must be gated behind a "
        "make_hoa_resolver(...) is not None check"
    )

    # Both gates must actually guard the SAME registration -- i.e. there is
    # no unconditional "if True" / early-return escape hatch between them
    # and the registration call. A cheap proxy: the registration call must
    # be the nearest "register_page" occurrence AFTER both gate keywords,
    # with no intervening top-level (unindented) statement resetting the
    # if-block. We settle for ordering + a bounded-distance check so this
    # test doesn't have to parse the AST.
    between = source[onboarding_idx:register_idx]
    assert "make_hoa_resolver(" in between
