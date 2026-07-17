# -*- encoding: utf-8 -*-
"""Tests for OnboardingHomePage — the EGF-sourced persona picker + vault-
derived state machine (Task 6).

``derive_state`` is pure (no Qt): it reads held-credential views (the
gate's ``HeldCredential`` shape — schema_said/issuer_aid/state/
chain_verified) plus the typed ``EgfDocument`` to decide which of
PICKER/FORM/PENDING/LICENSED to show. Precedence is LICENSED > PENDING >
FORM > PICKER — a revoked license does NOT count as LICENSED, but falls
through to whatever the held application credential + chosen role_id
would otherwise derive.

Widget tests exercise persona-card rendering (onboardable roles only,
i.e. roles with an ``onboarding`` block) and the submit path, including
the "one control serves both" jurisdiction binding: the fixture's single
context dimension id ("jurisdiction") matches a payload_schema property
name, so ONE rendered form field supplies both ``payload["jurisdiction"]``
and ``context["jurisdiction"]`` — no duplicate context-picker widget.
"""
import dataclasses

from keri_serviceaid.egf.documents import EgfDocument
from keri_serviceaid.tests.egf.fixtures.make_fixture_egf import fixture_egf

from locksmith.ui.onboarding.home_page import OnboardingHomePage, OnboardingState, derive_state


@dataclasses.dataclass
class Held:
    schema_said: str
    issuer_aid: str
    state: str
    chain_verified: bool


def _doc():
    _, sad = fixture_egf()
    return EgfDocument.from_sad(sad)


_PAYLOAD_SCHEMA = {
    "type": "object",
    "properties": {"jurisdiction": {"type": "string", "enum": ["US-UT"]}},
    "required": ["jurisdiction"],
}


def _resolver(said):
    return {"d": said, "commands": [{"id": "submit_application", "payload_schema": _PAYLOAD_SCHEMA}]}


def test_state_matrix():
    d = _doc()
    lic, app = "E" + "L" * 43, "E" + "P" * 43
    assert derive_state([], d, None) is OnboardingState.PICKER
    assert derive_state([], d, "carrier") is OnboardingState.FORM
    assert derive_state([Held(app, "E" + "S" * 43, "issued", True)], d, "carrier") is OnboardingState.PENDING
    assert derive_state([Held(lic, "E" + "U" * 43, "active", True)], d, None) is OnboardingState.LICENSED
    assert derive_state([Held(lic, "E" + "U" * 43, "revoked", True)], d, None) is OnboardingState.PICKER


def test_revoked_license_falls_through_to_pending_precedence():
    """Precedence is LICENSED > PENDING > FORM > PICKER. A revoked license
    never counts as LICENSED, but if the held application credential is
    ALSO still present (chain-verified) for the chosen role, PENDING wins
    over FORM/PICKER — the revocation doesn't erase the in-flight
    application, it just disqualifies the (now-revoked) grant itself."""
    d = _doc()
    lic, app = "E" + "L" * 43, "E" + "P" * 43
    held = [
        Held(lic, "E" + "U" * 43, "revoked", True),
        Held(app, "E" + "S" * 43, "issued", True),
    ]
    assert derive_state(held, d, "carrier") is OnboardingState.PENDING


def test_picker_renders_only_onboardable_roles(qtbot):
    page = OnboardingHomePage(_doc(), held_provider=list, on_submit=lambda *a: None)
    qtbot.addWidget(page)
    assert [c.role_id for c in page.persona_cards()] == ["carrier"]


def test_form_submit_passes_payload_and_context(qtbot):
    got = {}
    page = OnboardingHomePage(
        _doc(),
        held_provider=list,
        on_submit=lambda r, p, c: got.update(role=r, payload=p, ctx=c),
        micro_app_resolver=_resolver,
        accept_phases=("bootstrap", "production"),
    )
    qtbot.addWidget(page)
    page.select_persona("carrier")
    page.form.set_field("jurisdiction", "US-UT")
    page.submit()
    assert got["role"] == "carrier"
    # One-control-serves-both: the same "US-UT" value must appear in BOTH
    # the command payload and the issuer-selection context, sourced from
    # the single shared form field (no second context-only widget).
    assert got["payload"] == {"jurisdiction": "US-UT"}
    assert got["ctx"] == {"jurisdiction": "US-UT"}


def test_submit_blocked_and_no_duplicate_context_widget_when_invalid(qtbot):
    """The shared field is required; submitting without setting it must
    NOT call on_submit, and must render a visible form-error row (house
    pattern from B5) rather than silently failing."""
    from PySide6.QtWidgets import QLabel

    called = []
    page = OnboardingHomePage(
        _doc(),
        held_provider=list,
        on_submit=lambda *a: called.append(a),
        micro_app_resolver=_resolver,
        accept_phases=("bootstrap", "production"),
    )
    qtbot.addWidget(page)
    page.select_persona("carrier")
    page.submit()
    assert not called
    assert page.findChildren(QLabel, "form-error")


def test_refresh_recomputes_state_from_held_provider(qtbot):
    """refresh() re-derives state from held_provider() — callers (B8)
    connect this to doer_event so a newly-issued/revoked credential is
    reflected without reconstructing the page."""
    state = {"held": []}
    page = OnboardingHomePage(_doc(), held_provider=lambda: state["held"], on_submit=lambda *a: None)
    qtbot.addWidget(page)
    assert page.state is OnboardingState.PICKER

    lic = "E" + "L" * 43
    state["held"] = [Held(lic, "E" + "U" * 43, "active", True)]
    page.refresh()
    assert page.state is OnboardingState.LICENSED
