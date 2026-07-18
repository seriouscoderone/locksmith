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
from PySide6.QtWidgets import QWidget

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

    caplog.set_level(logging.WARNING, logger="locksmith.ui.onboarding.request_flow")
    flow = env.flow()
    flow.submit("carrier", {}, dict(VALID_CONTEXT))  # missing applicant_legal_name

    assert any(
        "onboarding.request_failed" in record.message and "applicant_legal_name" in record.message
        for record in caplog.records
    )


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
    """`LocksmithWindow._wire_onboarding` must only construct/register the
    onboarding "home" page when BOTH `brand().onboarding_enabled` is true
    AND `make_hoa_resolver(brand())` resolved a non-None (resolver,
    egf_doc) pair -- a non-onboarding or non-HOA brand must never
    construct a RequestFlow/OnboardingHomePage at all. Source-inspection,
    not a live construction, mirrors `tests/core/test_bootstrapping_
    overrides.py`'s precedent (a full `LocksmithWindow` needs a live
    QApplication + full plugin discovery to construct). `_wire_onboarding`
    is called unconditionally from `__init__` (see
    `test_wire_onboarding_registers_error_page_when_egf_broken` below for
    its behavioral, hardening-wave-item-1 error path)."""
    from locksmith.ui.window import LocksmithWindow

    source = inspect.getsource(LocksmithWindow._wire_onboarding)

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


class _FakeHoaVaultPage(QWidget):
    """Real (not mocked) QWidget stand-in for `HoaVaultPage`, monkeypatched
    in for `_wire_onboarding`'s `isinstance(vault_page, HoaVaultPage)` gate
    and `register_page`/`add_menu_entry` calls. Must be a REAL `QWidget` --
    not a `MagicMock(spec=HoaVaultPage)` -- for two independent reasons:
    (1) `HoaVaultPage`'s metaclass chain (`QABCMeta`, ABC-based) trips
    `isinstance()` against a spec'd Mock on this Python/mock combination
    (`AttributeError: type object 'HoaVaultPage' has no attribute
    '_abc_impl'`); (2) the error path constructs a REAL `OnboardingErrorPage`
    (a `QWidget`), and PySide6's `QWidget.__init__` strictly type-checks its
    `parent` argument -- a `MagicMock` is not an accepted `QWidget | None`.
    """

    def __init__(self):
        super().__init__()
        self.registered_pages: dict = {}
        self.menu_entries: list = []

    def register_page(self, key, widget) -> None:
        self.registered_pages[key] = widget

    def add_menu_entry(self, plugin_id, entry_button, submenu_items=None) -> None:
        self.menu_entries.append((plugin_id, entry_button, submenu_items))


def test_wire_onboarding_registers_error_page_when_egf_broken(monkeypatch):
    """Hardening wave item 1 (design spec §4.5): "A persona picker over a
    broken EGF shows an error state, not an empty list." When
    `make_hoa_resolver` raises an `EgfError` subclass (a pinned EGF whose
    bundle is missing/tampered/incomplete -- e.g. `EgfIntegrityError` on a
    SAID mismatch), `_wire_onboarding` must NOT propagate the exception
    (which would crash `LocksmithWindow.__init__` and the whole app launch).
    Instead: neither `RequestFlow` nor `OnboardingHomePage` is constructed,
    and a minimal `OnboardingErrorPage` is registered as "home" instead."""
    from keri_serviceaid.egf.errors import EgfIntegrityError
    from locksmith.ui.onboarding.home_page import OnboardingErrorPage
    from locksmith.ui.window import LocksmithWindow

    fake_brand = MagicMock()
    fake_brand.onboarding_enabled = True

    def _raise_integrity_error(_brand):
        raise EgfIntegrityError("E" + "X" * 43, "E" + "Y" * 43)

    request_flow_cls = MagicMock(name="RequestFlow")
    onboarding_home_page_cls = MagicMock(name="OnboardingHomePage")
    monkeypatch.setattr("locksmith.ui.window.brand", lambda: fake_brand)
    monkeypatch.setattr("locksmith.ui.window.make_hoa_resolver", _raise_integrity_error)
    monkeypatch.setattr("locksmith.ui.window.RequestFlow", request_flow_cls)
    monkeypatch.setattr("locksmith.ui.window.OnboardingHomePage", onboarding_home_page_cls)
    monkeypatch.setattr("locksmith.ui.window.HoaVaultPage", _FakeHoaVaultPage)

    win = SimpleNamespace(app=MagicMock(), _request_flow=None, _onboarding_home_page=None)
    vault_page = _FakeHoaVaultPage()

    # Must not raise -- this is the crash `LocksmithWindow.__init__` would
    # otherwise hit before the fix.
    LocksmithWindow._wire_onboarding(win, vault_page)

    assert win._request_flow is None
    assert win._onboarding_home_page is None
    request_flow_cls.assert_not_called()
    onboarding_home_page_cls.assert_not_called()

    assert list(vault_page.registered_pages.keys()) == ["home"]
    page = vault_page.registered_pages["home"]
    assert isinstance(page, OnboardingErrorPage)

    # No nav menu entry for a controller that was never built.
    assert vault_page.menu_entries == []


def test_wire_onboarding_still_registers_home_page_on_success(monkeypatch):
    """Control case for the above: when `make_hoa_resolver` resolves
    cleanly, `_wire_onboarding` must take the normal path -- RequestFlow +
    OnboardingHomePage constructed, registered as "home", nav entry added --
    unaffected by the new try/except."""
    from locksmith.ui.window import LocksmithWindow

    fake_brand = MagicMock()
    fake_brand.onboarding_enabled = True

    resolver = MagicMock(name="resolver")
    egf_doc = MagicMock(name="egf_doc")
    request_flow_instance = MagicMock(name="request_flow_instance")
    onboarding_home_page_instance = MagicMock(name="onboarding_home_page_instance")
    request_flow_cls = MagicMock(name="RequestFlow", return_value=request_flow_instance)
    onboarding_home_page_cls = MagicMock(
        name="OnboardingHomePage", return_value=onboarding_home_page_instance,
    )

    monkeypatch.setattr("locksmith.ui.window.brand", lambda: fake_brand)
    monkeypatch.setattr(
        "locksmith.ui.window.make_hoa_resolver", lambda _brand: (resolver, egf_doc),
    )
    monkeypatch.setattr("locksmith.ui.window.RequestFlow", request_flow_cls)
    monkeypatch.setattr("locksmith.ui.window.OnboardingHomePage", onboarding_home_page_cls)
    monkeypatch.setattr("locksmith.ui.window.HoaVaultPage", _FakeHoaVaultPage)

    win = SimpleNamespace(app=MagicMock(), _request_flow=None, _onboarding_home_page=None)
    vault_page = _FakeHoaVaultPage()

    LocksmithWindow._wire_onboarding(win, vault_page)

    request_flow_cls.assert_called_once()
    onboarding_home_page_cls.assert_called_once()
    assert win._request_flow is request_flow_instance
    assert win._onboarding_home_page is onboarding_home_page_instance
    assert vault_page.registered_pages == {"home": onboarding_home_page_instance}
    assert len(vault_page.menu_entries) == 1


def test_maybe_wire_onboarding_schedules_deferred_refresh(monkeypatch):
    """Live-observation fix: reopening a workspace holding a pending
    application showed the persona PICKER until the user interacted with
    it, because `OnboardingHomePage.__init__` derives state from
    `held_provider()` at CONSTRUCTION time -- potentially before this
    (possibly freshly-opened) vault is warm -- and, until now, only the
    `doer_event` connections wired below re-derived state afterward.
    `_maybe_wire_onboarding_for_vault` must ALSO schedule one deferred
    `refresh()` via `QTimer.singleShot(0, ...)` (the same pattern
    `LocksmithWindow.__init__` already uses for `_show_first_run_setup`/
    `_run_default_bootstrap` -- see `test_onboarding_branch_uses_deferred_
    setup_page_scheduling` in `tests/core/test_bootstrapping_overrides.py`)
    so the next event-loop turn re-derives against the now-open vault's
    real held credentials, landing directly on PENDING/LICENSED instead of
    requiring an unrelated event to happen first."""
    from locksmith.ui.window import LocksmithWindow

    scheduled = []
    monkeypatch.setattr(
        "locksmith.ui.window.QTimer.singleShot",
        lambda delay, slot: scheduled.append((delay, slot)),
    )

    request_flow = MagicMock(name="request_flow")
    onboarding_home_page = MagicMock(name="onboarding_home_page")
    vault = MagicMock(name="vault")

    win = SimpleNamespace(
        app=SimpleNamespace(vault=vault),
        _request_flow=request_flow,
        _onboarding_home_page=onboarding_home_page,
        _onboarding_wired_vault=None,
        pages={},
    )

    LocksmithWindow._maybe_wire_onboarding_for_vault(win)

    request_flow.seed_all_personas.assert_called_once()
    vault.signals.doer_event.connect.assert_any_call(onboarding_home_page.refresh)
    vault.signals.doer_event.connect.assert_any_call(onboarding_home_page.on_doer_event)

    assert scheduled == [(0, onboarding_home_page.refresh)], (
        "must schedule exactly one deferred refresh() via QTimer.singleShot(0, ...)"
    )
    assert win._onboarding_wired_vault is vault


def test_maybe_wire_onboarding_is_idempotent_per_vault_no_double_schedule(monkeypatch):
    """`Pages.VAULT` is shown every time the user navigates back into an
    ALREADY-open vault (e.g. Plugins -> Vault), not just on first open --
    the existing vault-identity guard must keep BOTH the `doer_event`
    connections and the new deferred-refresh scheduling from accumulating
    on every revisit (a later event would otherwise call `refresh()` once
    per accumulated connection/schedule)."""
    from locksmith.ui.window import LocksmithWindow

    scheduled = []
    monkeypatch.setattr(
        "locksmith.ui.window.QTimer.singleShot",
        lambda delay, slot: scheduled.append((delay, slot)),
    )

    request_flow = MagicMock(name="request_flow")
    onboarding_home_page = MagicMock(name="onboarding_home_page")
    vault = MagicMock(name="vault")

    win = SimpleNamespace(
        app=SimpleNamespace(vault=vault),
        _request_flow=request_flow,
        _onboarding_home_page=onboarding_home_page,
        _onboarding_wired_vault=None,
        pages={},
    )

    LocksmithWindow._maybe_wire_onboarding_for_vault(win)
    LocksmithWindow._maybe_wire_onboarding_for_vault(win)  # revisit, same vault

    assert len(scheduled) == 1, (
        "revisiting an already-wired vault must not re-schedule refresh()"
    )
    request_flow.seed_all_personas.assert_called_once()
