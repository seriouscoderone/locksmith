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
    page = _page(qapp)
    page.on_doer_event("ApplyFlow", "apply_failed",
                       {"error": "unreachable", "schema_said": SCHEMA_A})
    assert page._error_labels          # inline banner rendered
    page.on_doer_event("ApplyFlow", "apply_sent",
                       {"said": "E" + "S" * 43, "schema_said": SCHEMA_A})
    # no crash; state re-derived (PENDING only if provider reports the apply)


def test_role_card_open_only_when_page_available(qapp):
    from keri_serviceaid.egf.documents import Onboarding, Role
    role = Role(id="actuary", display_name="Actuarial", kind="person",
                description="", onboarding=Onboarding("actuary_role"))
    with_page = RoleCard(role, RoleStatus.ACTIVE, page_available=True)
    without = RoleCard(role, RoleStatus.ACTIVE, page_available=False)
    assert with_page.open_button is not None
    assert without.open_button is None
