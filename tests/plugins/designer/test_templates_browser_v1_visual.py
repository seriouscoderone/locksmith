import pytest

from locksmith.plugins.designer.editors.templates_browser import (
    TemplatesBrowserPage,
)
from locksmith.plugins.designer.store import TemplateStore


@pytest.fixture
def seeded_store(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCKSMITH_DESIGNER_SEED_FIXTURES", "1")
    from locksmith.plugins.designer import seed_fixtures
    store = TemplateStore(root=tmp_path)
    seed_fixtures.maybe_seed(store)
    return store


def test_count_summary(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    # Phase A summary is a plain count — invalid count is shown via
    # the notification pill, not folded into the subtitle.
    assert page.summary_label.text() == "2 micro-apps"


def test_default_state_no_chips_no_filters(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    # Empty filter state: chip rail hidden, both cards visible.
    assert page.filter_chips_text() == ""
    assert page._chip_rail_container.isVisible() is False
    assert page.card_count() == 2


def test_completer_suggests_kind_and_eco_tokens(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    model = page._completer.model()
    suggestions = [model.data(model.index(i, 0))
                   for i in range(model.rowCount())]
    # Full tokens, so the dropdown doubles as token discovery.
    assert "kind:government" in suggestions
    assert "kind:organization" in suggestions
    assert "eco:insurance" in suggestions
    assert "eco:compliance" in suggestions


def test_typing_token_with_space_adds_chip(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    page._search_input.setText("kind:government ")
    assert ("kind", "government") in page._chips
    # Search input cleared, ready for next entry.
    assert page._search_input.text() == ""
    # Filter applied: only the Regulator (kind=government) card remains.
    assert page.card_count() == 1
    assert "Regulator" in page.card_titles()[0]


def test_chip_removed_via_x_restores_full_set(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    page._add_chip("eco", "insurance")
    assert page.card_count() == 2  # both cards have the insurance tag
    page._remove_chip("eco", "insurance")
    assert page._chips == []
    assert page.card_count() == 2
    assert page._chip_rail_container.isVisible() is False


def test_free_text_matches_name_description_role(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    # Free-text search by name fragment.
    page._search_input.setText("carrier license app")
    assert page.card_count() == 1
    assert "Carrier" in page.card_titles()[0]


def test_invalid_pill_hidden_when_no_invalid(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    # All seeded templates pass validation → pill stays hidden.
    assert page._invalid_pill.isVisible() is False
    assert page._showing_invalid_only is False


# --- Phase B: aid: token, paste auto-detect, SAID badge click ------

def test_completer_suggests_aid_tokens_for_known_saids(
    qapp, seeded_store,
):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    model = page._completer.model()
    suggestions = [model.data(model.index(i, 0))
                   for i in range(model.rowCount())]
    # Every template SAID should surface in the dropdown as
    # `aid:<said>` so the user can pick a known AID directly.
    regulator = next(c for c in page._cards
                     if "Regulator" in c.title)
    assert f"aid:{regulator.ref.said}" in suggestions


def test_aid_filter_matches_full_said(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    regulator = next(c for c in page._cards
                     if "Regulator" in c.title)
    page._add_chip("aid", regulator.ref.said)
    assert page.card_count() == 1
    assert "Regulator" in page.card_titles()[0]


def test_aid_filter_matches_partial_said(qapp, seeded_store):
    # The card displays the truncated `ECAR…id00` form; users will
    # often copy the first few chars and expect a partial match.
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    regulator = next(c for c in page._cards
                     if "Regulator" in c.title)
    page._add_chip("aid", regulator.ref.said[:6])
    assert page.card_count() == 1
    assert "Regulator" in page.card_titles()[0]


def test_paste_44char_cesr_auto_promotes_to_aid_chip(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    regulator = next(c for c in page._cards
                     if "Regulator" in c.title)
    full_said = regulator.ref.said
    # Sanity: this is a CESR-shaped 44-char base64url-ish identifier.
    assert len(full_said) == 44 and full_said[0] in "EABDOF"
    # Simulating a paste — textChanged fires once with the full
    # buffer; the auto-detect promotes it to an aid: chip without
    # needing the user to type the prefix.
    page._search_input.setText(full_said)
    assert ("aid", full_said) in page._chips
    assert page._search_input.text() == ""
    assert page.card_count() == 1


def test_paste_random_44char_text_is_not_promoted(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    # A 44-char string that doesn't start with a CESR prefix code
    # should fall through to free-text search instead of being
    # auto-promoted to an aid: chip.
    text = "z" + "a" * 43  # length 44 but prefix 'z' is not CESR
    page._search_input.setText(text)
    assert ("aid", text) not in page._chips
    assert page._free_text == text


def test_card_said_badge_click_adds_aid_filter(qapp, seeded_store):
    from locksmith.plugins.designer.editors.templates_browser import (
        _AIDBadgeLabel,
    )
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    regulator = next(c for c in page._cards
                     if "Regulator" in c.title)
    assert isinstance(regulator.aid_badge, _AIDBadgeLabel)
    # The badge emits the FULL SAID, not the `ECAR…id00` display form.
    regulator.aid_badge.clicked_aid.emit(regulator.ref.said)
    assert ("aid", regulator.ref.said) in page._chips


def test_aid_chip_color_is_purple(qapp, seeded_store):
    from locksmith.plugins.designer.editors.templates_browser import (
        _CHIP_COLORS, _FilterChip,
    )
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    page._add_chip("aid", "ECAR_some_test_said_000000000000000000000000")
    chips = [page._chip_rail.itemAt(i).widget()
             for i in range(page._chip_rail.count())]
    chip = next(c for c in chips
                if isinstance(c, _FilterChip) and c._token == "aid")
    assert chip._color == _CHIP_COLORS["aid"]
    assert _CHIP_COLORS["aid"] == "#A36AE6"


# --- Phase C: rel: compound chip + popover + token-help -----------

def test_rel_token_parses_to_chip(qapp, seeded_store):
    from locksmith.plugins.designer.editors.templates_browser import (
        _RelChip,
    )
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    # Typing `rel:1:issued:EXyz… ` (trailing space) promotes to chip.
    page._search_input.setText("rel:1:issued:EXyzExampleAid ")
    assert ("rel", "1:issued:EXyzExampleAid") in page._chips
    chips = [page._chip_rail.itemAt(i).widget()
             for i in range(page._chip_rail.count())]
    rel_chip = next(c for c in chips if isinstance(c, _RelChip))
    assert rel_chip.hop == 1
    assert rel_chip.kind == "issued"
    assert rel_chip.aid == "EXyzExampleAid"


def test_rel_chip_value_round_trip():
    from locksmith.plugins.designer.editors.templates_browser import (
        _RelChip,
    )
    # Shorthand <hop>:<aid> defaults kind to "any".
    chip = _RelChip("2:EXyzExampleAid")
    assert chip.hop == 2
    assert chip.kind == "any"
    assert chip.aid == "EXyzExampleAid"
    # Full <hop>:<kind>:<aid>.
    chip2 = _RelChip("3:imported:EAbcd")
    assert chip2.hop == 3
    assert chip2.kind == "imported"
    assert chip2.aid == "EAbcd"


def test_rel_chip_set_relationship_emits_changed(qapp):
    from locksmith.plugins.designer.editors.templates_browser import (
        _RelChip,
    )
    chip = _RelChip("1:any:EXyz")
    captured = []
    chip.changed.connect(
        lambda old, new: captured.append((old, new))
    )
    chip.set_relationship(2, "issued")
    assert chip.hop == 2
    assert chip.kind == "issued"
    assert chip.value == "2:issued:EXyz"
    assert captured == [("1:any:EXyz", "2:issued:EXyz")]
    # No-op when nothing changes.
    chip.set_relationship(2, "issued")
    assert len(captured) == 1


def test_rel_chip_changed_updates_page_state(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    page._add_chip("rel", "1:any:EXyz")
    page._on_rel_chip_changed("1:any:EXyz", "2:issued:EXyz")
    assert ("rel", "2:issued:EXyz") in page._chips
    assert ("rel", "1:any:EXyz") not in page._chips


def test_rel_chip_does_not_filter_cards_yet(qapp, seeded_store):
    # The relationship index isn't online, so a rel chip must not
    # silently hide every card — it has to remain a no-op until the
    # backend ships.
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    baseline = page.card_count()
    page._add_chip("rel", "1:any:EXyzExampleAid")
    assert page.card_count() == baseline


def test_rel_chip_label_renders_natural_language(qapp):
    from locksmith.plugins.designer.editors.templates_browser import (
        _RelChip,
    )
    chip = _RelChip("1:any:EXyzExampleAidWith0123456789Padding00")
    assert "rel:" in chip._label.text()
    assert "1-hop" in chip._label.text()
    # Truncated AID rendering for readability.
    assert "…" in chip._label.text()
    # kind=any is hidden from the label.
    assert "any" not in chip._label.text()
    chip2 = _RelChip("2:issued:EShort")
    assert "issued" in chip2._label.text()


def test_token_prefix_dropdown_defaults_to_auto(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    assert page._token_prefix_btn is not None
    assert page._token_prefix_btn.text().startswith("Auto")
    assert page._selected_token == ""


def test_selecting_token_prefix_updates_button_and_placeholder(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    page._select_token_prefix("kind")
    assert page._selected_token == "kind"
    assert page._token_prefix_btn.text().startswith("Kind")
    # Placeholder updates so the user sees what to type next.
    assert "role kind" in page._search_input.placeholderText().lower()


def test_bare_value_with_selected_prefix_creates_chip(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    page._select_token_prefix("kind")
    # Bare "government" with Kind selected → kind:government chip.
    page._search_input.setText("government")
    page._on_search_submitted()
    assert ("kind", "government") in page._chips
    assert page._search_input.text() == ""


def test_typed_full_token_overrides_selected_prefix(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    page._select_token_prefix("kind")
    # Typing a full token wins over the selected prefix.
    page._search_input.setText("eco:insurance")
    page._on_search_submitted()
    assert ("eco", "insurance") in page._chips
    assert ("kind", "eco:insurance") not in page._chips


def test_bare_value_with_auto_selected_stays_freetext(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    # Default _selected_token == "" (Auto) → free-text behavior
    # for values that don't match any auto-detected pattern.
    page._search_input.setText("carrier license app")
    page._on_search_submitted()
    # No chip was created; the input is the free-text filter.
    assert page._chips == []
    assert page._free_text == "carrier license app"


def test_grid_renders_two_cards_in_two_up(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    assert page.card_count() == 2


def test_card_renders_role_icon_badge_with_glyph(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    regulator = next(c for c in page._cards
                     if "Regulator" in c.title)
    assert regulator.role_badge.glyph_label.text() == "🏛️"


def test_card_renders_validation_pill(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    regulator = next(c for c in page._cards
                     if "Regulator" in c.title)
    assert regulator.validation_pill.text() == "Valid"


def test_card_renders_ecosystem_chips(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    regulator = next(c for c in page._cards
                     if "Regulator" in c.title)
    chip_texts = [c.text() for c in regulator.ecosystem_chips]
    assert chip_texts == ["insurance", "compliance"]


def test_card_renders_modified_timestamp(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    regulator = next(c for c in page._cards
                     if "Regulator" in c.title)
    assert regulator.modified_label.text().startswith("Modified")
