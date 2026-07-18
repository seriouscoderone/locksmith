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
import copy
import dataclasses

from keri.core import coring
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
    page.select_persona("carrier")
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
    page.select_persona("carrier")
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
    page.select_persona("carrier")

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
    page.select_persona("carrier")

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
    page.select_persona("carrier")

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
    page.select_persona("carrier")

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
    page.select_persona("carrier")

    assert page.applying_to_summary() == ""


def test_missing_command_id_raises_descriptive_error(qtbot):
    """A resolved template lacking the role's request_command_id must fail
    with a clear, named error (not a bare StopIteration from next())."""
    import pytest

    page = OnboardingHomePage(
        _doc(),
        held_provider=list,
        on_submit=lambda *a: None,
        micro_app_resolver=lambda said: {"d": said, "commands": [{"id": "other", "payload_schema": {}}]},
        accept_phases=("bootstrap", "production"),
    )
    qtbot.addWidget(page)
    with pytest.raises(ValueError, match="submit_application"):
        page.select_persona("carrier")


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


def test_persona_card_click_selects_role(qtbot):
    """home_page.py:190-192 -- ``PersonaCard.mousePressEvent``'s real Qt
    event path. Every other test drives selection programmatically via
    ``select_persona``; this is the only one that exercises an actual
    left-button press on the rendered card, which is what the ``selected``
    signal (wired to ``select_persona`` in ``_build_picker_view``) depends
    on in production."""
    from PySide6.QtCore import Qt

    page = OnboardingHomePage(
        _doc(), held_provider=list, on_submit=lambda *a: None,
        micro_app_resolver=_resolver, accept_phases=("bootstrap", "production"),
    )
    qtbot.addWidget(page)
    card = page.persona_cards()[0]
    assert card.role_id == "carrier"

    qtbot.mouseClick(card, Qt.MouseButton.LeftButton)

    assert page.state is OnboardingState.FORM
    assert page._role_id == "carrier"


def test_pending_state_renders_pending_widget(qtbot):
    """home_page.py:361 -- the PENDING branch of ``_render``'s state ->
    widget dispatch. ``test_state_matrix`` already proves ``derive_state``
    computes PENDING correctly, but no prior test drove a REAL
    ``OnboardingHomePage`` into PENDING and checked the stacked widget
    actually switches (PICKER/FORM/LICENSED were all covered this way;
    PENDING was not)."""
    app_said = "E" + "P" * 43
    held = [Held(app_said, "E" + "S" * 43, "issued", True)]
    page = OnboardingHomePage(_doc(), held_provider=lambda: held, on_submit=lambda *a: None)
    qtbot.addWidget(page)

    page.select_persona("carrier")

    assert page.state is OnboardingState.PENDING
    assert page._stack.currentWidget() is page._pending_widget


def test_select_non_onboarding_role_raises_descriptive_error(qtbot):
    """home_page.py:375 -- ``_build_form_view``'s guard against a role
    that has no ``onboarding`` block. ``derive_state`` accepts ANY
    ``role_id`` (it doesn't gate on whether the role is actually a
    persona) -- the fixture's "regulator" role exists but is never
    rendered as a persona card, so selecting it programmatically must
    fail loudly rather than crash on ``role.onboarding.grant_credential_id``
    with an ``AttributeError``."""
    import pytest

    page = OnboardingHomePage(_doc(), held_provider=list, on_submit=lambda *a: None)
    qtbot.addWidget(page)

    with pytest.raises(ValueError, match="regulator.*no onboarding block"):
        page.select_persona("regulator")


def test_select_persona_without_micro_app_resolver_raises_descriptive_error(qtbot):
    """home_page.py:377 -- `_build_form_view`'s SECOND guard. Distinct from
    ``test_select_non_onboarding_role_raises_descriptive_error`` above
    (which hits the first guard, line 375, for a role with no onboarding
    block): here the role DOES have an onboarding block ("carrier"), but
    no ``micro_app_resolver`` was supplied at construction -- the resolver
    is only optional while the page never leaves PICKER/LICENSED (as in
    ``test_picker_renders_only_onboardable_roles``, which never selects a
    persona at all)."""
    import pytest

    page = OnboardingHomePage(_doc(), held_provider=list, on_submit=lambda *a: None)
    qtbot.addWidget(page)

    with pytest.raises(ValueError, match="micro_app_resolver is required"):
        page.select_persona("carrier")


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
    """home_page.py:416 -- `_build_context_controls`'s early return when
    the grant's issuer_role has NO context dimensions defined at all (as
    opposed to having dimensions that are all shared with payload fields,
    which every other test's fixture EGF exercises via at least the one
    "jurisdiction" dimension)."""
    from PySide6.QtWidgets import QComboBox

    doc = _doc_without_context_dimensions()
    page = OnboardingHomePage(
        doc, held_provider=list, on_submit=lambda *a: None,
        micro_app_resolver=_resolver_no_dim, accept_phases=("bootstrap", "production"),
    )
    qtbot.addWidget(page)

    page.select_persona("carrier")

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
    """home_page.py:465 -- `_dedup_context_options`'s skip-continue for an
    authority whose context value for this dimension was already seen
    from an earlier authority. Three authorities exist (two US-UT +
    one US-CA) but the combo must offer only two options."""
    from PySide6.QtWidgets import QComboBox

    doc = _doc_with_duplicate_authority_context()
    page = OnboardingHomePage(
        doc, held_provider=list, on_submit=lambda *a: None,
        micro_app_resolver=_resolver_no_dim, accept_phases=("bootstrap", "production"),
    )
    qtbot.addWidget(page)

    page.select_persona("carrier")

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
    """home_page.py:507 -- `_dotted_get`'s guard when a shared context
    dimension's payload key is simply absent from ``form.values()`` (an
    OPTIONAL, untouched field is omitted by ``SchemaFormBuilder``, not
    reported as an empty string). Submission must still succeed, with the
    dimension's context value surfacing as ``None`` rather than crashing
    on a missing dict key."""
    got = {}
    page = OnboardingHomePage(
        _doc(),
        held_provider=list,
        on_submit=lambda r, p, c: got.update(role=r, payload=p, ctx=c),
        micro_app_resolver=_resolver_optional_dim,
        accept_phases=("bootstrap", "production"),
    )
    qtbot.addWidget(page)
    page.select_persona("carrier")

    page.submit()  # jurisdiction never touched -- optional, so validate() is clean

    assert got["ctx"] == {"jurisdiction": None}
    assert "jurisdiction" not in got["payload"]


def test_second_submit_clears_previous_error_labels(qtbot):
    """home_page.py:513-514 -- `_clear_form_errors`'s loop body only runs
    when there are EXISTING error labels to remove. Every other test's
    first ``submit()`` call starts from an empty ``_error_labels`` list
    (a no-op loop); this drives a SECOND failing ``submit()`` so the loop
    that actually detaches/deletes the stale labels executes, rather than
    silently accumulating duplicate error rows on every retry."""
    from PySide6.QtWidgets import QLabel

    page = OnboardingHomePage(
        _doc(), held_provider=list, on_submit=lambda *a: None,
        micro_app_resolver=_resolver, accept_phases=("bootstrap", "production"),
    )
    qtbot.addWidget(page)
    page.select_persona("carrier")

    page.submit()  # jurisdiction untouched -- required -- fails
    first_errors = page.findChildren(QLabel, "form-error")
    assert first_errors

    page.submit()  # second failing submit must clear the FIRST batch first
    second_errors = page.findChildren(QLabel, "form-error")
    assert len(second_errors) == len(first_errors)
    assert not (set(first_errors) & set(second_errors)), \
        "stale error labels from the first submit must be removed, not accumulated"


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
    """home_page.py:529-533 -- `_clear_layout`'s loop body only runs when
    ``_form_layout`` already has content, i.e. a SECOND real
    ``_build_form_view`` call for a DIFFERENT persona after the first one
    already populated the layout. Without this, switching personas would
    stack the new form's widgets on top of the old one's instead of
    replacing them."""
    doc = _doc_with_second_persona()
    page = OnboardingHomePage(
        doc, held_provider=list, on_submit=lambda *a: None,
        micro_app_resolver=_resolver, accept_phases=("bootstrap", "production"),
    )
    qtbot.addWidget(page)

    page.select_persona("carrier")
    assert page._form_layout.count() == 1

    page.select_persona("broker")

    assert page._built_form_role_id == "broker"
    assert page._form_layout.count() == 1, \
        "the previous persona's form widget must be cleared, not stacked"


def test_get_toolbar_config_hides_vault_and_lock_controls(qtbot):
    """home_page.py:540 -- ``get_toolbar_config`` itself (the ``BasePage``
    override) was never called by any prior test; the window/plugin layer
    that consumes it is out of this module's own test scope, but the
    method's own return value still belongs to this module's coverage."""
    page = OnboardingHomePage(_doc(), held_provider=list, on_submit=lambda *a: None)
    qtbot.addWidget(page)

    assert page.get_toolbar_config() == {
        "show_vaults_button": False,
        "show_lock_button": False,
        "show_settings_button": True,
    }
