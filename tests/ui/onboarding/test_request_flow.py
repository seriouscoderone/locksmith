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

The former "window-wiring gate" section (held_provider None-guard,
source-inspection gate ordering, per-vault-open wiring, direct-transport
retry) moved to `tests/plugins/hoa_shell/test_shell_plugin.py` when that
logic moved from `LocksmithWindow` into the bundled `hoa_shell` plugin
(Task 7, HOA #4 behavior-preserving move).
"""
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
        # `kever.wits = []` (unwitnessed) + the default `SimpleNamespace`
        # class name (never "GroupHab") makes this hab pass
        # `serviceaid_eligible` -- see hardening wave item 2's own tests
        # below for the witnessed/multisig-rejection cases.
        self.hab = SimpleNamespace(pre=DEFAULT_HAB_PRE, kever=SimpleNamespace(wits=[]))

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


def test_matching_doer_and_schema_but_unknown_event_type_is_ignored(env):
    """request_flow.py:283 -- the listener's FINAL early return. Distinct
    from the two guards already covered: `doer_name` matches
    "IssueCredentialDoer" AND `schema_said` matches THIS submission's
    application schema, but `event_type` is neither
    "credential_issuance_failed" nor "credential_issued" (any other event
    type the doer might one day emit under the same vocabulary). Must be
    ignored with the listener left pending, so the real credential_issued
    event still fires it afterward."""
    flow = env.flow()
    flow.submit("carrier", dict(VALID_PAYLOAD), dict(VALID_CONTEXT))

    env.signals.doer_event.emit(
        "IssueCredentialDoer", "some_other_event", {"schema_said": APPLICATION_SAID},
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


def test_submit_witnessed_hab_emits_request_failed_and_schedules_nothing(env):
    """Hardening wave item 2 (RequestFlow envelope self-enforcement):
    today's serverless serviceaid providers only support single-sig,
    unwitnessed identifiers (`serviceaid_eligible`). A witnessed default
    hab must fail closed BEFORE any seeding or issuance is scheduled --
    never reach `EgfSeeder`/`ServiceaidIssueDoer`."""
    env.hab.kever.wits = ["B" + "W" * 43]  # witnessed
    flow = env.flow()
    flow.submit("carrier", dict(VALID_PAYLOAD), dict(VALID_CONTEXT))

    assert env.issued == []
    assert env.seeder_calls == []
    assert env.extended == []
    assert len(env.failures) == 1
    assert env.failures[0][0] == "RequestFlow"
    assert env.failures[0][1] == "request_failed"
    assert (
        env.failures[0][2]["message"]
        == "this secure workspace's identifier is outside the serviceaid envelope (witnessed or multisig)"
    )


def test_submit_failure_logs_a_warning_with_the_message(env, caplog):
    """Acceptance-demo item 2: every request_failed path must ALSO log a
    warning (live-log visibility for a failure that would otherwise only
    ever surface as a Qt signal) -- pins both the invalid-payload path
    (a plain ValueError) and the envelope-guard path (its own early
    if/return, not the shared except block) since `_fail` is the single
    chokepoint for both."""
    import logging

    # The module logger comes from keri's ogler, which may attach direct
    # handlers with propagate=False depending on ogler's global state — in
    # that mode pytest's caplog (which relies on propagation) sees nothing.
    # Force propagation for the duration of the test so capture is
    # deterministic across environments.
    module_logger = logging.getLogger("locksmith.ui.onboarding.request_flow")
    old_propagate = module_logger.propagate
    module_logger.propagate = True
    try:
        caplog.set_level(logging.WARNING, logger="locksmith.ui.onboarding.request_flow")
        flow = env.flow()
        flow.submit("carrier", {}, dict(VALID_CONTEXT))  # missing applicant_legal_name

        assert any(
            "onboarding.request_failed" in record.message and "applicant_legal_name" in record.message
            for record in caplog.records
        )
    finally:
        module_logger.propagate = old_propagate


def test_submit_multisig_hab_emits_request_failed_and_schedules_nothing(env):
    """Same guard, the multisig (`GroupHab`) branch of `serviceaid_eligible`."""
    group_hab = MagicMock(name="group_hab")
    group_hab.__class__.__name__ = "GroupHab"
    group_hab.pre = DEFAULT_HAB_PRE
    group_hab.kever.wits = []
    env.app.vault.hby.habByName.return_value = group_hab

    flow = env.flow()
    flow.submit("carrier", dict(VALID_PAYLOAD), dict(VALID_CONTEXT))

    assert env.issued == []
    assert env.seeder_calls == []
    assert env.extended == []
    assert len(env.failures) == 1
    assert "serviceaid envelope" in env.failures[0][2]["message"]


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


def test_direct_authority_mailbox_outcome_fails(env):
    """authority has a direct endpoint; simulate send_complete with
    channel='mailbox' -> a ('RequestFlow','request_failed') event whose
    message mentions 'reachable'."""
    flow = env.flow()
    # VALID_CONTEXT (jurisdiction=US-UT) selects the UT DOI authority, whose
    # fixture_egf() entry carries a direct endpoint.
    flow.submit("carrier", dict(VALID_PAYLOAD), dict(VALID_CONTEXT))
    env.emit_issued("Ecred1")
    assert len(env.granted) == 1

    env.signals.doer_event.emit(
        "SendGrantDoer", "send_complete",
        {"credential_said": "Ecred1", "channel": "mailbox", "success": True},
    )

    assert len(env.failures) == 1
    assert env.failures[0][0] == "RequestFlow"
    assert env.failures[0][1] == "request_failed"
    assert "reachable" in env.failures[0][2]["message"]


def test_direct_authority_peer_outcome_is_clean(env):
    """channel='peer' -> no request_failed emitted."""
    flow = env.flow()
    flow.submit("carrier", dict(VALID_PAYLOAD), dict(VALID_CONTEXT))  # UT DOI, direct endpoint
    env.emit_issued("Ecred1")
    assert len(env.granted) == 1

    env.signals.doer_event.emit(
        "SendGrantDoer", "send_complete",
        {"credential_said": "Ecred1", "channel": "peer", "success": True},
    )

    assert env.failures == []


def test_nondirect_authority_keeps_fallback_semantics(env):
    """authority with no direct endpoint: channel='mailbox' -> no failure."""
    flow = env.flow()
    # jurisdiction=US-CA selects the CA DOI authority, whose fixture_egf()
    # entry carries NO endpoints -- no outcome listener should be wired.
    flow.submit("carrier", dict(VALID_PAYLOAD), {"jurisdiction": "US-CA"})
    env.emit_issued("Ecred1")
    assert len(env.granted) == 1

    env.signals.doer_event.emit(
        "SendGrantDoer", "send_complete",
        {"credential_said": "Ecred1", "channel": "mailbox", "success": True},
    )

    assert env.failures == []


def test_direct_authority_send_failed_outcome_fails(env):
    """send_failed for the direct authority's credential -> request_failed,
    same as a non-peer channel -- the other half of the listener's outcome
    guard ('send_failed' or channel != 'peer')."""
    flow = env.flow()
    flow.submit("carrier", dict(VALID_PAYLOAD), dict(VALID_CONTEXT))  # UT DOI, direct endpoint
    env.emit_issued("Ecred1")
    assert len(env.granted) == 1

    env.signals.doer_event.emit(
        "SendGrantDoer", "send_failed",
        {"credential_said": "Ecred1", "error": "boom", "success": False},
    )

    assert len(env.failures) == 1
    assert "reachable" in env.failures[0][2]["message"]


def test_direct_authority_outcome_listener_is_one_shot(env):
    """The outcome listener must disconnect itself after firing once -- a
    second send_complete/send_failed for the same credential must not
    surface a second request_failed (mirrors the credential_issued listener's
    one-shot discipline elsewhere in this file)."""
    flow = env.flow()
    flow.submit("carrier", dict(VALID_PAYLOAD), dict(VALID_CONTEXT))  # UT DOI, direct endpoint
    env.emit_issued("Ecred1")
    assert len(env.granted) == 1

    env.signals.doer_event.emit(
        "SendGrantDoer", "send_complete",
        {"credential_said": "Ecred1", "channel": "mailbox", "success": True},
    )
    env.signals.doer_event.emit(
        "SendGrantDoer", "send_complete",
        {"credential_said": "Ecred1", "channel": "mailbox", "success": True},
    )

    assert len(env.failures) == 1


def test_resubmission_evicts_stale_outcome_listener(env):
    """Finding 1 fix (listener-leak regression, review round 2): the
    direct-mode `_on_send_outcome` listener wired per submission must be
    evicted by a same-role resubmission before the previous grant's outcome
    arrives -- mirroring `_pending_listeners`' latest-submission-wins
    discipline via the parallel `_pending_outcome_listeners` registry.
    Without the fix, the FIRST submission's outcome listener stays connected
    and fires a stale `request_failed` for a credential the user already
    abandoned by resubmitting."""
    flow = env.flow()
    flow.submit("carrier", dict(VALID_PAYLOAD), dict(VALID_CONTEXT))  # UT DOI, direct endpoint
    env.emit_issued("Ecred-first")  # wires outcome listener #1
    assert len(env.granted) == 1

    flow.submit("carrier", dict(VALID_PAYLOAD), dict(VALID_CONTEXT))  # evicts #1
    env.emit_issued("Ecred-second")  # wires outcome listener #2
    assert len(env.granted) == 2

    # The FIRST credential's outcome must be a no-op now -- listener #1 was
    # evicted by the resubmission, before its grant's outcome ever arrived.
    env.signals.doer_event.emit(
        "SendGrantDoer", "send_complete",
        {"credential_said": "Ecred-first", "channel": "mailbox", "success": True},
    )
    assert env.failures == [], (
        "a stale outcome listener from an evicted submission must not fire "
        "request_failed for the abandoned attempt's credential"
    )

    # The SECOND (current) submission's outcome must still be live.
    env.signals.doer_event.emit(
        "SendGrantDoer", "send_complete",
        {"credential_said": "Ecred-second", "channel": "mailbox", "success": True},
    )
    assert len(env.failures) == 1
    assert "reachable" in env.failures[0][2]["message"]


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

