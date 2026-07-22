# -*- encoding: utf-8 -*-
"""Roles-overview home surface: one card per persona, per-role status,
Request/Open/Request-again affordances (HOA #4)."""
from unittest.mock import MagicMock

from locksmith.ui.onboarding.home_page import OnboardingHomePage, RoleCard
from locksmith.ui.onboarding.role_states import RoleStatus

# Reuse the FakeEgf + Held helpers from test_role_states (import them).
from tests.ui.onboarding.test_role_states import (FakeEgf, Held, SCHEMA_A,
                                                  SCHEMA_P, _apply)


def _page(qapp, held=(), applies=(), on_apply=None, open_role=None,
          available_pages=()):
    return OnboardingHomePage(
        FakeEgf(),
        held_provider=lambda: list(held),
        on_submit=MagicMock(),
        applies_provider=lambda: list(applies),
        on_apply=on_apply or MagicMock(),
        open_role=open_role or MagicMock(),
        accept_phases=("production",),
    )


def test_overview_renders_one_card_per_persona(qapp):
    page = _page(qapp)
    assert set(page.role_states) == {"actuary", "product_designer",
                                     "carrier_like"}
    assert all(s is RoleStatus.AVAILABLE for s in page.role_states.values())


def test_request_click_fires_on_apply_for_apply_mode_role(qapp):
    on_apply = MagicMock()
    page = _page(qapp, on_apply=on_apply)
    page._on_card_request("actuary")
    on_apply.assert_called_once_with("actuary")


def test_request_click_routes_form_mode_role_to_form(qapp):
    on_apply = MagicMock()
    page = _page(qapp, on_apply=on_apply)
    page._on_card_request("carrier_like")
    on_apply.assert_not_called()
    assert page._role_id == "carrier_like"      # form flow engaged


def test_active_and_pending_statuses_render(qapp):
    page = _page(qapp, held=[Held(SCHEMA_A)], applies=[_apply(SCHEMA_P)])
    assert page.role_states["actuary"] is RoleStatus.ACTIVE
    assert page.role_states["product_designer"] is RoleStatus.PENDING


def test_request_again_suppresses_revoked_and_reapplies(qapp):
    on_apply = MagicMock()
    page = _page(qapp, held=[Held(SCHEMA_A, state="revoked")],
                 on_apply=on_apply)
    assert page.role_states["actuary"] is RoleStatus.REVOKED
    page._on_card_request("actuary")
    on_apply.assert_called_once_with("actuary")
    page.refresh()
    assert page.role_states["actuary"] is RoleStatus.AVAILABLE  # suppressed


def test_reapply_suppression_clears_on_active(qapp):
    held = [Held(SCHEMA_A, state="revoked")]
    page = _page(qapp, held=held)
    page._reapplying_roles.add("actuary")
    held.append(Held(SCHEMA_A, state="active"))
    page.refresh()
    assert page.role_states["actuary"] is RoleStatus.ACTIVE
    assert "actuary" not in page._reapplying_roles


def test_apply_failed_event_shows_banner_and_apply_sent_refreshes(qapp):
    applies = []
    page = _page(qapp, applies=applies)
    page.on_doer_event("ApplyFlow", "apply_failed",
                       {"error": "unreachable", "schema_said": SCHEMA_A})
    # The failure happened while the OVERVIEW was showing (_role_id is
    # None) -- the visible proof is the overview's OWN banner, NOT the
    # form's `_error_labels`/`_error_layout` (that view is never on screen
    # here; asserting only `_error_labels` non-empty is exactly the
    # masking-the-invisibility bug this test used to have -- review fix).
    # See test_apply_failed_while_overview_visible_shows_visible_banner for
    # the dedicated ancestor-of-currentWidget() visibility proof.
    assert page._error_labels == []
    assert page._overview_error_label.text() == "unreachable"
    assert not page._overview_error_label.isHidden()

    applies.append(_apply(SCHEMA_A))
    page.on_doer_event("ApplyFlow", "apply_sent",
                       {"said": "E" + "S" * 43, "schema_said": SCHEMA_A})
    # apply_sent clears the overview banner...
    assert page._overview_error_label.text() == ""
    assert page._overview_error_label.isHidden()
    # ...and refresh() actually ran: the newly-appended sent apply is
    # picked up as PENDING (state re-derived, not just "no crash").
    assert page.role_states["actuary"] is RoleStatus.PENDING


def test_apply_failed_while_overview_visible_shows_visible_banner(qapp):
    """Review fix, item 1/2/5: an apply-mode failure must be visible to the
    user, not just recorded in some off-screen label list. The banner has
    to actually live under the widget the stack currently shows."""
    page = _page(qapp)
    assert page._role_id is None                     # overview is showing
    assert page._stack.currentWidget() is page._overview_widget

    page.on_doer_event("ApplyFlow", "apply_failed",
                       {"error": "issuer unreachable", "schema_said": SCHEMA_A})

    assert page._overview_error_label.text() == "issuer unreachable"
    assert not page._overview_error_label.isHidden()
    # Visibility proof: the banner is a descendant of the widget the stack
    # is CURRENTLY showing (the overview), not merely constructed somewhere
    # off-screen (e.g. inside the never-shown form container).
    current = page._stack.currentWidget()
    assert current is page._overview_widget
    assert current.isAncestorOf(page._overview_error_label)
    assert not page._form_container.isAncestorOf(page._overview_error_label)


def test_apply_failed_rolls_back_reapply_suppression_for_revoked_role(qapp):
    """Review fix, item 3: a REVOKED role's Request-again click
    speculatively suppresses REVOKED (see ``_on_card_request``) so its
    outstanding PENDING isn't immediately re-masked. If that apply then
    FAILS, the suppression must be rolled back -- otherwise the card lies
    AVAILABLE forever with no visible error instead of reverting to
    REVOKED."""
    on_apply = MagicMock()
    page = _page(qapp, held=[Held(SCHEMA_A, state="revoked")], on_apply=on_apply)
    assert page.role_states["actuary"] is RoleStatus.REVOKED

    page._on_card_request("actuary")
    on_apply.assert_called_once_with("actuary")
    assert "actuary" in page._reapplying_roles
    page.refresh()
    assert page.role_states["actuary"] is RoleStatus.AVAILABLE  # suppressed

    page.on_doer_event("ApplyFlow", "apply_failed",
                       {"error": "unreachable", "schema_said": SCHEMA_A})

    assert "actuary" not in page._reapplying_roles     # rolled back
    assert page.role_states["actuary"] is RoleStatus.REVOKED   # card is honest again
    assert page._overview_error_label.text() == "unreachable"
    assert not page._overview_error_label.isHidden()


def test_new_request_click_clears_a_stale_overview_banner(qapp):
    page = _page(qapp)
    page.on_doer_event("ApplyFlow", "apply_failed",
                       {"error": "unreachable", "schema_said": SCHEMA_A})
    assert not page._overview_error_label.isHidden()

    page._on_card_request("actuary")
    assert page._overview_error_label.text() == ""
    assert page._overview_error_label.isHidden()


def test_role_card_open_only_when_page_available(qapp):
    from keri_serviceaid.egf.documents import Onboarding, Role
    role = Role(id="actuary", display_name="Actuarial", kind="person",
                description="", onboarding=Onboarding("actuary_role"))
    with_page = RoleCard(role, RoleStatus.ACTIVE, page_available=True)
    without = RoleCard(role, RoleStatus.ACTIVE, page_available=False)
    assert with_page.open_button is not None
    assert without.open_button is None
