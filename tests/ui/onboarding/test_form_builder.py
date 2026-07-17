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
_EGF_DOC = _REPO_ROOT / "brands/usurance/egf/EBTP1zVbY_KjEBlafARtCwJPyD-cKPFknUL08AazZJDP.json"

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
