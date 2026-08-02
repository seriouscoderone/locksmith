# -*- encoding: utf-8 -*-
"""Tests for SchemaFormBuilder — the pure JSON-Schema -> Qt form factory
(Task 5). Purely presentation-layer: no doers, no I/O, no resolver. The
fixture schema below mirrors the shape of a real carrier application
``payload_schema`` (see design spec §7.4): scalar fields, an enum select,
an enum-array checkbox group, nested objects with their own ``required``
lists, and a ``string``+``format: date-time`` field that must be
auto-filled at submit time rather than rendered.
"""
import json
from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QGroupBox, QLineEdit, QSpinBox

from locksmith.ui.onboarding.form_builder import SchemaFormBuilder

_REPO_ROOT = Path(__file__).resolve().parents[3]
_EGF_DOC = _REPO_ROOT / "tests/fixtures/carrier_egf_bundle/ED1ePv4Wdv4vXSpN2FgoYj64J9MpRigea3IcDnc5K1dh.json"

SCHEMA = {"type": "object", "additionalProperties": False,
          "properties": {
              "applicant_legal_name": {"type": "string", "minLength": 1},
              "jurisdiction": {"type": "string", "enum": ["US-UT", "US-CA"]},
              "lines_of_business": {"type": "array", "uniqueItems": True, "minItems": 1,
                                    "items": {"type": "string", "enum": ["property", "casualty"]}},
              "primary_contact": {"type": "object", "required": ["email"],
                                  "properties": {"email": {"type": "string", "format": "email"}}},
              "representations": {"type": "object", "required": ["solvency_reserves_usd", "solvency_attestation"],
                                  "properties": {"solvency_reserves_usd": {"type": "number", "minimum": 0},
                                                 "solvency_attestation": {"type": "boolean"},
                                                 "years_in_operation": {"type": "integer", "minimum": 0}}},
              "submitted_at": {"type": "string", "format": "date-time"}},
          "required": ["applicant_legal_name", "jurisdiction", "lines_of_business", "submitted_at"]}


def _built(qtbot):
    b = SchemaFormBuilder(SCHEMA); w = b.build(); qtbot.addWidget(w); return b, w


def test_widget_mapping(qtbot):
    b, w = _built(qtbot)
    assert isinstance(b.widget_for("applicant_legal_name"), QLineEdit)
    assert isinstance(b.widget_for("jurisdiction"), QComboBox)
    assert isinstance(b.widget_for("representations"), QGroupBox)
    assert isinstance(b.widget_for("representations.solvency_reserves_usd"), QDoubleSpinBox)
    assert isinstance(b.widget_for("representations.solvency_attestation"), QCheckBox)
    assert isinstance(b.widget_for("representations.years_in_operation"), QSpinBox)
    assert b.hidden_autofill_fields() == ["submitted_at"]


def test_values_roundtrip_and_checkbox_group(qtbot):
    b, _ = _built(qtbot)
    b.set_field("applicant_legal_name", "Acme Mutual")
    b.set_field("jurisdiction", "US-UT")
    b.set_field("lines_of_business", ["property"])
    v = b.values()
    assert v["lines_of_business"] == ["property"] and v["jurisdiction"] == "US-UT"


def test_validate_reports_missing_required(qtbot):
    b, _ = _built(qtbot)
    msgs = b.validate()
    assert any("applicant_legal_name" in m for m in msgs)
    assert any("lines_of_business" in m for m in msgs)


def test_unsupported_construct_fails_visible(qtbot):
    b = SchemaFormBuilder({"type": "object", "properties": {"weird": {"type": "array",
                           "items": {"type": "object"}}}})
    w = b.build(); qtbot.addWidget(w)
    from PySide6.QtWidgets import QLabel
    errors = w.findChildren(QLabel, "form-error")
    assert errors, "unsupported construct must render a visible error row"


def test_real_bundled_schema_roundtrip(qtbot):
    """Regression: the REAL carrier application payload_schema lists its
    nested objects (``primary_contact``, ``representations``) in the
    top-level ``required`` — object CONTAINER paths must never enter the
    value/validation iteration (fix round 1: ``values()`` used to raise
    ``AssertionError: unhandled kind 'group'`` on exactly this schema)."""
    doc = json.loads(_EGF_DOC.read_text())
    schema = next(c for c in doc["commands"] if c["id"] == "submit_application")["payload_schema"]
    b = SchemaFormBuilder(schema)
    w = b.build(); qtbot.addWidget(w)

    # submitted_at is hidden-autofill: not rendered, excluded from validate().
    assert b.hidden_autofill_fields() == ["submitted_at"]
    assert b.widget_for("submitted_at") is None

    b.set_field("applicant_legal_name", "Acme Mutual")
    b.set_field("jurisdiction", "US-UT")
    b.set_field("lines_of_business", ["property"])
    b.set_field("primary_contact.name", "Jo Carrier")
    b.set_field("primary_contact.email", "jo@acme.example")
    b.set_field("representations.solvency_reserves_usd", 5000000.0)
    b.set_field("representations.solvency_attestation", True)

    assert b.validate() == []
    v = b.values()
    assert v["primary_contact"]["email"] == "jo@acme.example"
    assert v["primary_contact"]["name"] == "Jo Carrier"
    assert v["representations"]["solvency_attestation"] is True
    assert v["representations"]["solvency_reserves_usd"] == 5000000.0
    assert v["lines_of_business"] == ["property"]


def test_optional_minitems_group_untouched_validates_clean(qtbot):
    """An OPTIONAL enum-array with minItems must validate clean while
    untouched (required-or-touched gating), but still enforce minItems
    once the user has interacted with the group."""
    b = SchemaFormBuilder({"type": "object", "properties": {
        "tags": {"type": "array", "uniqueItems": True, "minItems": 2,
                 "items": {"type": "string", "enum": ["a", "b", "c"]}}}})
    w = b.build(); qtbot.addWidget(w)
    assert b.validate() == []  # optional + untouched -> no minItems complaint
    b.set_field("tags", ["a"])  # touched, under minItems
    assert any("tags" in m for m in b.validate())


def test_unsupported_top_level_field_type_renders_error_row(qtbot):
    """form_builder.py:160 -- `_populate`'s catch-all for a field whose
    schema `type` isn't one of the six recognized kinds. Distinct from
    ``test_unsupported_construct_fails_visible`` above, which exercises
    the ARRAY-specific unsupported-construct branch (line 226) -- this
    hits the outer per-field dispatch's own else clause."""
    b = SchemaFormBuilder({"type": "object", "properties": {
        "mystery": {"type": "null"}}})
    w = b.build(); qtbot.addWidget(w)
    from PySide6.QtWidgets import QLabel
    errors = w.findChildren(QLabel, "form-error")
    assert errors, "unsupported top-level field type must render a visible error row"
    assert "unsupported schema type" in errors[0].text()


def test_string_enum_field_sets_tooltip_from_description(qtbot):
    """form_builder.py:169 -- the enum (QComboBox) branch of
    ``_build_string_field`` sets a tooltip from the schema's
    ``description`` only when one is present."""
    b = SchemaFormBuilder({"type": "object", "properties": {
        "status": {"type": "string", "enum": ["a", "b"], "description": "pick one"}}})
    w = b.build(); qtbot.addWidget(w)
    combo = b.widget_for("status")
    assert combo.toolTip() == "pick one"


def test_array_checkbox_group_sets_tooltip_from_description(qtbot):
    """form_builder.py:214 -- the checkbox-group (QGroupBox) branch of
    ``_build_array_field`` sets a tooltip from the schema's
    ``description`` only when one is present."""
    b = SchemaFormBuilder({"type": "object", "properties": {
        "tags": {"type": "array", "items": {"type": "string", "enum": ["x", "y"]},
                 "description": "pick tags"}}})
    w = b.build(); qtbot.addWidget(w)
    group = b.widget_for("tags")
    assert group.toolTip() == "pick tags"


def test_set_field_unknown_path_raises_key_error(qtbot):
    """form_builder.py:295 -- ``set_field`` on a path that was never
    registered (not rendered — e.g. a typo, or a hidden autofill field)
    must fail loudly rather than silently no-op."""
    import pytest
    b, _ = _built(qtbot)
    with pytest.raises(KeyError, match="no rendered field"):
        b.set_field("does_not_exist", "x")


def test_set_field_non_leaf_group_path_raises_key_error(qtbot):
    """form_builder.py:311 -- ``set_field`` on a registered but non-leaf
    (``kind == "group"``) path — a nested object container carries no
    value of its own, only its own leaves do."""
    import pytest
    b, _ = _built(qtbot)
    with pytest.raises(KeyError, match="cannot set value for non-leaf path"):
        b.set_field("representations", {"solvency_reserves_usd": 1})


def test_extract_value_unhandled_kind_raises_assertion_error(qtbot):
    """form_builder.py:348 -- `_extract_value`'s internal-invariant guard
    against a ``_kind`` entry that doesn't match any of the five widget
    kinds the builder itself ever assigns. Not reachable through the
    public API (only ``_register``/``_build_object_field`` ever populate
    ``_kind``, and both only use recognized values), so this simulates the
    defensive scenario directly: corrupt ``_kind`` after a normal build,
    the same technique used elsewhere to prove an internal guard actually
    fires rather than silently passing."""
    import pytest
    b, _ = _built(qtbot)
    b._kind["applicant_legal_name"] = "bogus_kind"
    with pytest.raises(AssertionError, match="unhandled kind"):
        b.values()


def test_replace_field_with_combo_swaps_line_edit_for_narrowed_combo(qtbot):
    """Design spec §7.4's "one control serves both": a free-text field
    (jurisdiction, no schema enum) is replaced IN PLACE by a combo offering
    only the caller-supplied (authority-sourced) options — never a
    duplicate widget, and the user can no longer type an arbitrary value."""
    b = SchemaFormBuilder({"type": "object", "properties": {
        "jurisdiction": {"type": "string"}}, "required": ["jurisdiction"]})
    w = b.build(); qtbot.addWidget(w)
    assert isinstance(b.widget_for("jurisdiction"), QLineEdit)

    combo = b.replace_field_with_combo(
        "jurisdiction", [("US-UT", "US-UT (pilot)"), ("US-CA", "US-CA")],
    )
    assert isinstance(combo, QComboBox)
    assert b.widget_for("jurisdiction") is combo
    assert not combo.isEditable()
    assert [combo.itemText(i) for i in range(combo.count())] == ["US-UT (pilot)", "US-CA"]
    assert combo.currentIndex() == -1  # untouched — no default selection

    # set_field matches by raw itemData, not display text.
    b.set_field("jurisdiction", "US-UT")
    assert combo.currentIndex() == 0
    assert b.values()["jurisdiction"] == "US-UT"

    # validate() never flags this field itself (the caller owns that).
    combo.setCurrentIndex(-1)
    assert b.validate() == []


def test_replace_field_with_combo_on_unknown_path_raises_key_error(qtbot):
    import pytest
    b, _ = _built(qtbot)
    with pytest.raises(KeyError, match="cannot replace non-field path"):
        b.replace_field_with_combo("does_not_exist", [])


def test_replace_field_with_combo_on_group_path_raises_key_error(qtbot):
    """A container (`kind == "group"`) path carries no single row widget of
    its own to replace."""
    import pytest
    b, _ = _built(qtbot)
    with pytest.raises(KeyError, match="cannot replace non-field path"):
        b.replace_field_with_combo("representations", [])


def test_validate_reports_min_length_pattern_and_email_violations(qtbot):
    """form_builder.py:378,381,383 -- the three ``line_edit`` validation
    messages (minLength, pattern, email format) are independent ``if``s,
    not ``elif``s, so a single too-short, pattern-violating value trips
    both of the first two, and a separately malformed email trips the
    third."""
    schema = {"type": "object", "properties": {
        "code": {"type": "string", "minLength": 5, "pattern": r"^[A-Z]+$"},
        "email": {"type": "string", "format": "email"}}}
    b = SchemaFormBuilder(schema)
    w = b.build(); qtbot.addWidget(w)
    b.set_field("code", "ab")
    b.set_field("email", "not-an-email")
    msgs = b.validate()
    assert any("at least 5 characters" in m for m in msgs)
    assert any("does not match the required pattern" in m for m in msgs)
    assert any("must be a valid email address" in m for m in msgs)
