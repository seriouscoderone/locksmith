# -*- encoding: utf-8 -*-
"""Tests for OnboardingHomePage — the roles-overview home surface (Task 10)
built on the REAL bundled-shape fixture EGF (``fixture_egf()``, one
onboardable "carrier" role, form-mode).

Task 8's ``derive_role_states`` precedence matrix (ACTIVE > REVOKED >
PENDING > AVAILABLE) already has its own FakeEgf-based coverage in
``test_role_states.py``; the tests below are the REAL-EgfDocument
integration proof (``EgfDocument.from_sad``'s actual shape plugged into the
same logic), plus every widget-level test (persona-card/RoleCard rendering,
the FORM submit path including the "one control serves both" jurisdiction
binding, error banners) TRANSLATED from the old single-selected-role state
machine (``derive_state``/``OnboardingState``/``PersonaCard``/
``select_persona`` — all now TRANSITIONAL-shimmed or deleted, see
``home_page.py``'s module docstring) onto the new contract:
``select_persona(role_id)`` -> ``page._on_card_request(role_id)`` (a form-
mode role still routes into the FORM view exactly the same way); a
page-level ``OnboardingState`` -> ``page.role_states[role_id]`` (a
``RoleStatus``) plus ``page._role_id``/``page._stack.currentWidget()`` for
which view is showing.

The old dedicated PENDING/REVOKED message views (``_build_pending_view``/
``_update_pending_view``/``_build_revoked_view``/``_update_revoked_view``)
were deleted per the Task 10 brief — their EGF-derived WHO/next-steps
prose has no home-page-level replacement; the equivalent information is now
just the role's status badge on its overview ``RoleCard`` (see
``test_pending_status_renders_on_overview_card`` /
``test_revoked_status_renders_on_overview_card`` below). This is a known,
brief-directed reduction in per-application detail, not an oversight.
"""
import copy
import dataclasses

import pytest
from keri.core import coring
from keri_serviceaid.egf.documents import EgfDocument
from keri_serviceaid.tests.egf.fixtures.make_fixture_egf import fixture_egf

from locksmith.ui.onboarding.home_page import OnboardingHomePage
from locksmith.ui.onboarding.role_states import RoleStatus, derive_role_states


@dataclasses.dataclass
class Held:
    schema_said: str
    issuer_aid: str
    state: str
    chain_verified: bool
    revoked_at: str = ""


def _doc():
    _, sad = fixture_egf()
    return EgfDocument.from_sad(sad)


_PAYLOAD_SCHEMA = {
    # No `enum` — mirrors the REAL carrier application schema's shape
    # (docs/insurance/egf/.../submit_application's `jurisdiction`: a plain
    # free-text string), so this fixture actually exercises the
    # LineEdit-replaced-by-combo path (item 3) rather than the
    # already-a-combo enum-field path.
    "type": "object",
    "properties": {"jurisdiction": {"type": "string"}},
    "required": ["jurisdiction"],
}


def _resolver(said):
    return {"d": said, "commands": [{"id": "submit_application", "payload_schema": _PAYLOAD_SCHEMA}]}


# ---------------------------------------------------------------------------
# derive_role_states precedence against the REAL fixture EGF (translated
# from the old derive_state precedence matrix — role-scoped now: ACTIVE >
# REVOKED > PENDING > AVAILABLE, in place of LICENSED > REVOKED > PENDING >
# FORM > PICKER).
# ---------------------------------------------------------------------------

def test_role_states_precedence_against_real_fixture():
    """Was test_state_matrix: derive_state(...) is {PICKER, FORM, PENDING,
    LICENSED, REVOKED} -> derive_role_states(...)["carrier"] is
    {AVAILABLE (nothing held/chosen), PENDING, ACTIVE, REVOKED}. FORM/PICKER
    themselves have no per-role status (they were page-level, not
    role-level); the page's own routing is covered separately below."""
    d = _doc()
    lic, app = "E" + "L" * 43, "E" + "P" * 43
    assert derive_role_states([], [], d)["carrier"] is RoleStatus.AVAILABLE
    assert derive_role_states(
        [Held(app, "E" + "S" * 43, "issued", True)], [], d,
    )["carrier"] is RoleStatus.PENDING
    assert derive_role_states(
        [Held(lic, "E" + "U" * 43, "active", True)], [], d,
    )["carrier"] is RoleStatus.ACTIVE
    assert derive_role_states(
        [Held(lic, "E" + "U" * 43, "revoked", True)], [], d,
    )["carrier"] is RoleStatus.REVOKED


def test_revoked_beats_pending_against_real_fixture():
    """Was test_revoked_license_derives_revoked_over_pending: REVOKED wins
    even though the (now superseded) held application credential is ALSO
    still present (chain-verified) for the role."""
    d = _doc()
    lic, app = "E" + "L" * 43, "E" + "P" * 43
    held = [
        Held(lic, "E" + "U" * 43, "revoked", True),
        Held(app, "E" + "S" * 43, "issued", True),
    ]
    assert derive_role_states(held, [], d)["carrier"] is RoleStatus.REVOKED


def test_active_beats_revoked_against_real_fixture():
    """Was test_active_grant_beats_revoked: a different, ACTIVE instance of
    the same gating credential must still win even when a revoked instance
    also lingers in the held set."""
    d = _doc()
    lic = "E" + "L" * 43
    held = [
        Held(lic, "E" + "U" * 43, "revoked", True),
        Held(lic, "E" + "U" * 43, "active", True),
    ]
    assert derive_role_states(held, [], d)["carrier"] is RoleStatus.ACTIVE


def test_revoked_requires_chain_verified_against_real_fixture():
    """Was test_revoked_requires_chain_verified: a never-verified (escrowed)
    credential in a revoked state is not a real revocation."""
    d = _doc()
    lic = "E" + "L" * 43
    held = [Held(lic, "E" + "U" * 43, "revoked", False)]
    assert derive_role_states(held, [], d)["carrier"] is RoleStatus.AVAILABLE


def test_suppress_revoked_against_real_fixture():
    """Was test_derive_state_suppress_revoked_escapes_to_picker /
    test_derive_state_suppress_revoked_still_yields_licensed_when_active
    (the second half — suppression only matters when the role IS revoked;
    the "still ACTIVE when held active" half is already
    test_active_beats_revoked_against_real_fixture above, precedence-wise
    unaffected by suppression). Per-role variant already has FakeEgf
    coverage in test_role_states.py's test_suppress_revoked_enables_
    per_role_reapply; this is the real-EgfDocument integration proof."""
    d = _doc()
    lic = "E" + "L" * 43
    held = [Held(lic, "E" + "U" * 43, "revoked", True)]
    assert derive_role_states(held, [], d)["carrier"] is RoleStatus.REVOKED
    assert derive_role_states(
        held, [], d, suppress_revoked_roles=frozenset({"carrier"}),
    )["carrier"] is RoleStatus.AVAILABLE


# ---------------------------------------------------------------------------
# Overview rendering + routing
# ---------------------------------------------------------------------------

def test_overview_renders_only_onboardable_roles(qtbot):
    """Was test_picker_renders_only_onboardable_roles."""
    page = OnboardingHomePage(_doc(), held_provider=list, on_submit=lambda *a: None)
    qtbot.addWidget(page)
    assert [c.role_id for c in page.role_cards()] == ["carrier"]


def test_role_card_request_button_click_routes_form_mode_role_to_form(qtbot):
    """Was test_persona_card_click_selects_role -- home_page.py's real Qt
    event path. Every other test drives routing programmatically via
    ``_on_card_request``; this is the only one that exercises an actual
    left-button press on the rendered card's Request button, which is what
    the ``request_clicked`` signal (wired to ``_on_card_request`` in
    ``_rebuild_overview``) depends on in production."""
    from PySide6.QtCore import Qt

    page = OnboardingHomePage(
        _doc(), held_provider=list, on_submit=lambda *a: None,
        micro_app_resolver=_resolver, accept_phases=("bootstrap", "production"),
    )
    qtbot.addWidget(page)
    card = page.role_cards()[0]
    assert card.role_id == "carrier"
    assert card.request_button is not None

    qtbot.mouseClick(card.request_button, Qt.MouseButton.LeftButton)

    assert page._role_id == "carrier"
    assert page._stack.currentWidget() is page._form_container


def test_pending_status_renders_on_overview_card(qtbot):
    """Was test_pending_state_renders_pending_widget -- there is no more
    dedicated PENDING widget (deleted per the brief); the equivalent is the
    role's card carrying RoleStatus.PENDING, with neither a Request nor an
    Open button (see RoleCard's own button-gating)."""
    app_said = "E" + "P" * 43
    held = [Held(app_said, "E" + "S" * 43, "issued", True)]
    page = OnboardingHomePage(_doc(), held_provider=lambda: held, on_submit=lambda *a: None)
    qtbot.addWidget(page)

    assert page.role_states["carrier"] is RoleStatus.PENDING
    card = page.role_cards()[0]
    assert card.status is RoleStatus.PENDING
    assert card.request_button is None
    assert card.open_button is None


def test_revoked_status_renders_on_overview_card(qtbot):
    """Was test_revoked_state_renders_revoked_view -- there is no more
    dedicated REVOKED widget (deleted per the brief; the revocation-time/
    issuer prose it rendered has no home-page-level replacement anymore).
    The equivalent is the role's card carrying RoleStatus.REVOKED with a
    "Request again" button."""
    lic = "E" + "L" * 43
    held = [Held(lic, "E" + "U" * 43, "revoked", True,
                 revoked_at="2026-07-19T12:00:00.000000+00:00")]
    page = OnboardingHomePage(
        _doc(), held_provider=lambda: held, on_submit=lambda *a: None,
        micro_app_resolver=_resolver, accept_phases=("bootstrap", "production"),
    )
    qtbot.addWidget(page)
    page.refresh()

    assert page.role_states["carrier"] is RoleStatus.REVOKED
    card = page.role_cards()[0]
    assert card.status is RoleStatus.REVOKED
    assert card.request_button is not None
    assert card.request_button.text() == "Request again"


def test_revoked_reapply_reenters_form(qtbot):
    """Was test_revoked_reapply_resets_to_picker. Form-mode's "Request
    again" affordance still gets the holder back into the application form
    despite the still-held revoked license (a TEL rev never removes the
    credential from the holder's store) -- ``_on_card_request``'s form-mode
    branch routes on onboarding mode BEFORE consulting REVOKED status at
    all (see its docstring), so this is unconditional. Unlike the apply-mode
    reapply path (test_roles_overview.py's
    test_request_again_suppresses_revoked_and_reapplies), form-mode's
    ``_on_card_request`` does not add the role to ``_reapplying_roles`` --
    flagged as a concern in the task report -- so the overview card may
    still read REVOKED (not AVAILABLE/PENDING) if the holder navigates back
    to it before a fresh grant arrives; the form flow itself is what this
    test asserts, matching the old behavior's core guarantee (re-apply is
    not a dead end)."""
    lic = "E" + "L" * 43
    revoked = Held(lic, "E" + "U" * 43, "revoked", True)
    held = [revoked]
    page = OnboardingHomePage(
        _doc(), held_provider=lambda: list(held), on_submit=lambda *a: None,
        micro_app_resolver=_resolver, accept_phases=("bootstrap", "production"),
    )
    qtbot.addWidget(page)
    assert page.role_states["carrier"] is RoleStatus.REVOKED

    page._on_card_request("carrier")

    assert page._role_id == "carrier"
    assert page._stack.currentWidget() is page._form_container


# ---------------------------------------------------------------------------
# FORM submit path (unchanged machinery -- select_persona -> _on_card_request)
# ---------------------------------------------------------------------------

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
    page._on_card_request("carrier")
    # The shared "jurisdiction" field is a narrowed combo (item 3), not a
    # free-text LineEdit -- set_field still works (matches raw itemData).
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
    pattern from B5) rather than silently failing. Also asserts the
    one-control-serves-both invariant (item 3): because the "jurisdiction"
    dimension matches a payload property, the form's OWN field for it is a
    combo (never a free-text LineEdit a user could type an arbitrary,
    unmatchable value into) -- exactly one QComboBox on the page total,
    never a second, duplicate context-only widget alongside it."""
    from PySide6.QtWidgets import QComboBox, QLabel

    called = []
    page = OnboardingHomePage(
        _doc(),
        held_provider=list,
        on_submit=lambda *a: called.append(a),
        micro_app_resolver=_resolver,
        accept_phases=("bootstrap", "production"),
    )
    qtbot.addWidget(page)
    page._on_card_request("carrier")
    page.submit()
    assert not called
    assert page.findChildren(QLabel, "form-error")

    combos = page.findChildren(QComboBox)
    assert len(combos) == 1, "shared dimension must render exactly one combo, never a duplicate"
    combo = combos[0]
    assert combo.objectName() == "onboarding.context.jurisdiction"
    assert page.form.widget_for("jurisdiction") is combo, \
        "the form's own field IS the context control, not a separate one"
    assert not combo.isEditable(), "typing arbitrary junk into the jurisdiction control must be impossible"


# Payload schema WITHOUT the jurisdiction property — forces the DEDICATED
# context-combo path (the dimension has no matching form field to share).
_PAYLOAD_SCHEMA_NO_DIM = {
    "type": "object",
    "properties": {"applicant_legal_name": {"type": "string", "minLength": 1}},
    "required": ["applicant_legal_name"],
}


def _resolver_no_dim(said):
    return {"d": said, "commands": [{"id": "submit_application", "payload_schema": _PAYLOAD_SCHEMA_NO_DIM}]}


def test_untouched_dedicated_context_combo_blocks_submit(qtbot):
    """A dedicated (non-shared) context combo starts unselected; submit()
    must treat it as required — inline form-error with the dimension's
    prompt, on_submit NOT called (never a context of {"jurisdiction": None})."""
    from PySide6.QtWidgets import QLabel

    called = []
    page = OnboardingHomePage(
        _doc(),
        held_provider=list,
        on_submit=lambda *a: called.append(a),
        micro_app_resolver=_resolver_no_dim,
        accept_phases=("bootstrap", "production"),
    )
    qtbot.addWidget(page)
    page._on_card_request("carrier")
    page.form.set_field("applicant_legal_name", "Acme Mutual")  # form itself is clean
    page.submit()
    assert not called
    errors = page.findChildren(QLabel, "form-error")
    assert any("Which state?" in e.text() for e in errors)


def test_dedicated_context_combo_selection_passes_context_not_payload(qtbot):
    """Selecting an option in the dedicated combo supplies the context
    value only — the payload has no such key. Bootstrap-phase authorities'
    entries carry the " (pilot)" suffix in display text, but the raw
    context value is unsuffixed."""
    from PySide6.QtWidgets import QComboBox

    got = {}
    page = OnboardingHomePage(
        _doc(),
        held_provider=list,
        on_submit=lambda r, p, c: got.update(role=r, payload=p, ctx=c),
        micro_app_resolver=_resolver_no_dim,
        accept_phases=("bootstrap", "production"),
    )
    qtbot.addWidget(page)
    page._on_card_request("carrier")

    combo = next(
        c
        for c in page.findChildren(QComboBox)
        if c.objectName() == "onboarding.context.jurisdiction"
    )
    texts = [combo.itemText(i) for i in range(combo.count())]
    assert "US-UT (pilot)" in texts  # bootstrap-phase authority badged
    assert "US-CA" in texts  # production-phase authority unbadged

    page.form.set_field("applicant_legal_name", "Acme Mutual")
    combo.setCurrentIndex(texts.index("US-UT (pilot)"))
    page.submit()
    assert got["role"] == "carrier"
    assert got["ctx"] == {"jurisdiction": "US-UT"}  # raw value, no suffix
    assert "jurisdiction" not in got["payload"]


# fixture_egf()'s "UT DOI" authority: bootstrap phase, US-UT.
UT_AID = "E" + "U" * 44


def test_applying_to_header_hidden_before_any_selection(qtbot):
    """Item 5: the header stays hidden until a context selection resolves
    to exactly one authority — no premature/blank "Applying to" text."""
    page = OnboardingHomePage(
        _doc(), held_provider=list, on_submit=lambda *a: None,
        micro_app_resolver=_resolver, accept_phases=("bootstrap", "production"),
    )
    qtbot.addWidget(page)
    page._on_card_request("carrier")

    assert page.applying_to_summary() == ""


def test_applying_to_header_updates_on_shared_dim_combo_selection(qtbot):
    """Item 5: selecting the shared "jurisdiction" combo (item 3) reveals
    the "applying to" header with the matching authority's display_name,
    a truncated AID, and the bootstrap-phase "PILOT" badge — sourced from
    the SAME `egf.authorities(...)` call the combo's own options use."""
    page = OnboardingHomePage(
        _doc(), held_provider=list, on_submit=lambda *a: None,
        micro_app_resolver=_resolver, accept_phases=("bootstrap", "production"),
    )
    qtbot.addWidget(page)
    page._on_card_request("carrier")

    combo = page.form.widget_for("jurisdiction")
    combo.setCurrentIndex(combo.findData("US-UT"))

    summary = page.applying_to_summary()
    assert "UT DOI" in summary
    assert UT_AID[:12] in summary
    assert "PILOT" in summary


def test_applying_to_header_updates_on_dedicated_combo_selection(qtbot):
    """Same header, driven by a DEDICATED (non-shared) context combo."""
    page = OnboardingHomePage(
        _doc(), held_provider=list, on_submit=lambda *a: None,
        micro_app_resolver=_resolver_no_dim, accept_phases=("bootstrap", "production"),
    )
    qtbot.addWidget(page)
    page._on_card_request("carrier")

    from PySide6.QtWidgets import QComboBox
    combo = next(
        c for c in page.findChildren(QComboBox)
        if c.objectName() == "onboarding.context.jurisdiction"
    )
    combo.setCurrentIndex(combo.findData("US-CA"))

    summary = page.applying_to_summary()
    assert "CA DOI" in summary
    assert "PRODUCTION" in summary


def test_applying_to_header_hidden_when_no_context_dimensions(qtbot):
    """The early-return path in `_build_context_controls` (no context
    dimensions at all for the issuer role) must still leave the header
    correctly hidden, not stale from a previous persona's selection."""
    doc = _doc_without_context_dimensions()
    page = OnboardingHomePage(
        doc, held_provider=list, on_submit=lambda *a: None,
        micro_app_resolver=_resolver_no_dim, accept_phases=("bootstrap", "production"),
    )
    qtbot.addWidget(page)
    page._on_card_request("carrier")

    assert page.applying_to_summary() == ""


def test_build_form_view_raises_for_non_onboarding_role(qtbot):
    """Was test_select_non_onboarding_role_raises_descriptive_error --
    ``_build_form_view``'s guard against a role that has no ``onboarding``
    block. Called directly (rather than through ``_on_card_request``, whose
    routing branch is only ever reached for actual persona cards in
    production): this is ``_build_form_view``'s OWN input-validation
    contract, unchanged by this task ("keep the FORM machinery
    untouched")."""
    page = OnboardingHomePage(_doc(), held_provider=list, on_submit=lambda *a: None)
    qtbot.addWidget(page)

    with pytest.raises(ValueError, match="regulator.*no onboarding block"):
        page._build_form_view("regulator")


def test_build_form_view_without_micro_app_resolver_raises_descriptive_error(qtbot):
    """Was test_select_persona_without_micro_app_resolver_raises_
    descriptive_error -- `_build_form_view`'s SECOND guard: the role DOES
    have an onboarding block ("carrier"), but no `micro_app_resolver` was
    supplied at construction."""
    page = OnboardingHomePage(_doc(), held_provider=list, on_submit=lambda *a: None)
    qtbot.addWidget(page)

    with pytest.raises(ValueError, match="micro_app_resolver is required"):
        page._build_form_view("carrier")


def test_missing_command_id_raises_descriptive_error(qtbot):
    """A resolved template lacking the role's request_command_id must fail
    with a clear, named error (not a bare StopIteration from next())."""
    page = OnboardingHomePage(
        _doc(),
        held_provider=list,
        on_submit=lambda *a: None,
        micro_app_resolver=lambda said: {"d": said, "commands": [{"id": "other", "payload_schema": {}}]},
        accept_phases=("bootstrap", "production"),
    )
    qtbot.addWidget(page)
    with pytest.raises(ValueError, match="submit_application"):
        page._build_form_view("carrier")


def test_refresh_recomputes_state_from_held_provider(qtbot):
    """refresh() re-derives every role's status from held_provider() —
    callers (the shell) connect this to doer_event so a newly-issued/
    revoked credential is reflected without reconstructing the page."""
    state = {"held": []}
    page = OnboardingHomePage(_doc(), held_provider=lambda: state["held"], on_submit=lambda *a: None)
    qtbot.addWidget(page)
    assert page.role_states["carrier"] is RoleStatus.AVAILABLE

    lic = "E" + "L" * 43
    state["held"] = [Held(lic, "E" + "U" * 43, "active", True)]
    page.refresh()
    assert page.role_states["carrier"] is RoleStatus.ACTIVE


def _doc_without_context_dimensions() -> EgfDocument:
    """Variant of the fixture EGF with `context_dimensions` emptied out —
    re-saidified the same way Task 3's ``EgfSeeder`` variant-authoring
    pattern does (copy the sad, mutate, re-saidify the `d` field only)."""
    _, sad = fixture_egf()
    sad = dict(sad)
    sad["context_dimensions"] = []
    _, sad = coring.Saider.saidify(sad=sad, label="d")
    return EgfDocument.from_sad(sad)


def test_no_context_dimensions_for_issuer_role_skips_context_group(qtbot):
    """`_build_context_controls`'s early return when the grant's issuer_role
    has NO context dimensions defined at all (as opposed to having
    dimensions that are all shared with payload fields, which every other
    test's fixture EGF exercises via at least the one "jurisdiction"
    dimension)."""
    from PySide6.QtWidgets import QComboBox

    doc = _doc_without_context_dimensions()
    page = OnboardingHomePage(
        doc, held_provider=list, on_submit=lambda *a: None,
        micro_app_resolver=_resolver_no_dim, accept_phases=("bootstrap", "production"),
    )
    qtbot.addWidget(page)

    page._on_card_request("carrier")

    assert page._context_widgets == {}
    context_combos = [
        c for c in page.findChildren(QComboBox)
        if c.objectName().startswith("onboarding.context.")
    ]
    assert context_combos == []


def _doc_with_duplicate_authority_context() -> EgfDocument:
    """Variant of the fixture EGF with a THIRD "regulator" authority whose
    context value duplicates the existing UT DOI's ("US-UT") -- every
    other fixture-based test only ever has distinct per-authority context
    values, so the dedup guard's skip-continue was never exercised."""
    _, sad = fixture_egf()
    sad = dict(sad)
    authorities = list(sad["authorities"])
    duplicate = copy.deepcopy(authorities[0])  # UT DOI: phase=bootstrap, US-UT
    duplicate["display_name"] = "UT DOI (duplicate)"
    duplicate["aid"] = "E" + "D" * 43
    authorities.append(duplicate)
    sad["authorities"] = authorities
    _, sad = coring.Saider.saidify(sad=sad, label="d")
    return EgfDocument.from_sad(sad)


def test_dedup_context_options_skips_duplicate_authority_value(qtbot):
    """`_dedup_context_options`'s skip-continue for an authority whose
    context value for this dimension was already seen from an earlier
    authority. Three authorities exist (two US-UT + one US-CA) but the
    combo must offer only two options."""
    from PySide6.QtWidgets import QComboBox

    doc = _doc_with_duplicate_authority_context()
    page = OnboardingHomePage(
        doc, held_provider=list, on_submit=lambda *a: None,
        micro_app_resolver=_resolver_no_dim, accept_phases=("bootstrap", "production"),
    )
    qtbot.addWidget(page)

    page._on_card_request("carrier")

    combo = next(
        c for c in page.findChildren(QComboBox)
        if c.objectName() == "onboarding.context.jurisdiction"
    )
    texts = [combo.itemText(i) for i in range(combo.count())]
    assert combo.count() == 2
    assert texts.count("US-UT (pilot)") == 1
    assert "US-CA" in texts


# Payload schema with jurisdiction as an OPTIONAL shared dimension (unlike
# the module-level `_PAYLOAD_SCHEMA`, which requires it) -- forces
# `values()` to OMIT the field entirely when untouched, so the shared-dim
# mirror in `submit()` must cope with a payload that simply lacks the key,
# AND submit()'s requiredness gating (`_shared_dims[dim_id]`) must NOT
# block submission just because the combo is unselected.
_PAYLOAD_SCHEMA_OPTIONAL_DIM = {
    "type": "object",
    "properties": {"jurisdiction": {"type": "string"}},
    "required": [],
}


def _resolver_optional_dim(said):
    return {"d": said, "commands": [{"id": "submit_application", "payload_schema": _PAYLOAD_SCHEMA_OPTIONAL_DIM}]}


def test_shared_dim_untouched_optional_field_yields_none_context(qtbot):
    """`_dotted_get`'s guard when a shared context dimension's payload key
    is simply absent from ``form.values()`` (an OPTIONAL, untouched field
    is omitted by ``SchemaFormBuilder``, not reported as an empty string).
    Submission must still succeed, with the dimension's context value
    surfacing as ``None`` rather than crashing on a missing dict key."""
    got = {}
    page = OnboardingHomePage(
        _doc(),
        held_provider=list,
        on_submit=lambda r, p, c: got.update(role=r, payload=p, ctx=c),
        micro_app_resolver=_resolver_optional_dim,
        accept_phases=("bootstrap", "production"),
    )
    qtbot.addWidget(page)
    page._on_card_request("carrier")

    page.submit()  # jurisdiction never touched -- optional, so validate() is clean

    assert got["ctx"] == {"jurisdiction": None}
    assert "jurisdiction" not in got["payload"]


def test_second_submit_clears_previous_error_labels(qtbot):
    """`_clear_form_errors`'s loop body only runs when there are EXISTING
    error labels to remove. Every other test's first ``submit()`` call
    starts from an empty ``_error_labels`` list (a no-op loop); this drives
    a SECOND failing ``submit()`` so the loop that actually detaches/
    deletes the stale labels executes, rather than silently accumulating
    duplicate error rows on every retry."""
    from PySide6.QtWidgets import QLabel

    page = OnboardingHomePage(
        _doc(), held_provider=list, on_submit=lambda *a: None,
        micro_app_resolver=_resolver, accept_phases=("bootstrap", "production"),
    )
    qtbot.addWidget(page)
    page._on_card_request("carrier")

    page.submit()  # jurisdiction untouched -- required -- fails
    first_errors = page.findChildren(QLabel, "form-error")
    assert first_errors

    page.submit()  # second failing submit must clear the FIRST batch first
    second_errors = page.findChildren(QLabel, "form-error")
    assert len(second_errors) == len(first_errors)
    assert not (set(first_errors) & set(second_errors)), \
        "stale error labels from the first submit must be removed, not accumulated"


def test_on_doer_event_shows_banner_for_request_failed(qtbot):
    """Acceptance-demo item 2: the shell wires `RequestFlow`'s
    `request_failed` doer_event to this page's `on_doer_event` -- it must
    render the message as a visible (house "form-error" styling from item
    1) inline banner on the form view."""
    from PySide6.QtWidgets import QLabel

    page = OnboardingHomePage(
        _doc(), held_provider=list, on_submit=lambda *a: None,
        micro_app_resolver=_resolver, accept_phases=("bootstrap", "production"),
    )
    qtbot.addWidget(page)
    page._on_card_request("carrier")

    page.on_doer_event(
        "RequestFlow", "request_failed",
        {"message": "this workspace's identifier is outside the serviceaid envelope"},
    )

    errors = page.findChildren(QLabel, "form-error")
    assert any("outside the serviceaid envelope" in e.text() for e in errors)


def test_on_doer_event_replaces_previous_banner_not_accumulates(qtbot):
    from PySide6.QtWidgets import QLabel

    page = OnboardingHomePage(
        _doc(), held_provider=list, on_submit=lambda *a: None,
        micro_app_resolver=_resolver, accept_phases=("bootstrap", "production"),
    )
    qtbot.addWidget(page)
    page._on_card_request("carrier")

    page.on_doer_event("RequestFlow", "request_failed", {"message": "first failure"})
    page.on_doer_event("RequestFlow", "request_failed", {"message": "second failure"})

    errors = [e.text() for e in page.findChildren(QLabel, "form-error")]
    assert errors == ["second failure"]


def test_on_doer_event_ignores_unrelated_doer_or_event_type(qtbot):
    """Only (`RequestFlow`, `request_failed`) and the two `ApplyFlow` events
    trigger anything here -- every other doer_event on the same bus (e.g.
    `refresh`'s own wiring source) must be a no-op."""
    from PySide6.QtWidgets import QLabel

    page = OnboardingHomePage(
        _doc(), held_provider=list, on_submit=lambda *a: None,
        micro_app_resolver=_resolver, accept_phases=("bootstrap", "production"),
    )
    qtbot.addWidget(page)
    page._on_card_request("carrier")

    page.on_doer_event("SomeOtherDoer", "request_failed", {"message": "irrelevant"})
    page.on_doer_event("RequestFlow", "some_other_event", {"message": "irrelevant"})

    assert page.findChildren(QLabel, "form-error") == []


def _doc_with_second_persona() -> EgfDocument:
    """Variant of the fixture EGF with a SECOND onboardable role ("broker",
    cloned from "carrier"'s onboarding block) -- needed to drive
    ``_build_form_view`` a second time for a DIFFERENT role_id (selecting
    the SAME role twice is a no-op per ``_built_form_role_id`` gating)."""
    _, sad = fixture_egf()
    sad = dict(sad)
    roles = list(sad["roles"])
    broker_role = copy.deepcopy(roles[0])  # "carrier", onboarding block included
    broker_role["id"] = "broker"
    broker_role["display_name"] = "Broker"
    roles.append(broker_role)
    sad["roles"] = roles
    _, sad = coring.Saider.saidify(sad=sad, label="d")
    return EgfDocument.from_sad(sad)


def test_selecting_second_persona_clears_previous_form_widgets(qtbot):
    """`_clear_layout`'s loop body only runs when ``_form_layout`` already
    has content, i.e. a SECOND real ``_build_form_view`` call for a
    DIFFERENT persona after the first one already populated the layout.
    Without this, switching personas would stack the new form's widgets on
    top of the old one's instead of replacing them."""
    doc = _doc_with_second_persona()
    page = OnboardingHomePage(
        doc, held_provider=list, on_submit=lambda *a: None,
        micro_app_resolver=_resolver, accept_phases=("bootstrap", "production"),
    )
    qtbot.addWidget(page)

    page._on_card_request("carrier")
    assert page._form_layout.count() == 1

    page._on_card_request("broker")

    assert page._built_form_role_id == "broker"
    assert page._form_layout.count() == 1, \
        "the previous persona's form widget must be cleared, not stacked"


def test_get_toolbar_config_hides_vault_and_lock_controls(qtbot):
    """``get_toolbar_config`` itself (the ``BasePage`` override) — the
    window/plugin layer that consumes it is out of this module's own test
    scope, but the method's own return value still belongs to this
    module's coverage."""
    page = OnboardingHomePage(_doc(), held_provider=list, on_submit=lambda *a: None)
    qtbot.addWidget(page)

    assert page.get_toolbar_config() == {
        "show_vaults_button": False,
        "show_lock_button": False,
        "show_settings_button": True,
    }
