"""The form's controls and rules come from the EGF, so this is where that starts.

Uses the REAL bundled EGF, not a fixture. A hand-built schema fixture would let the
loader and the shipped bundle drift apart silently, which is the exact defect class
this whole plan exists to close.
"""
import pytest

from locksmith.core.branding import egf_local_dir
from locksmith.plugins.cuo.schema_source import (
    SchemaSourceError,
    load_mandate_schema,
)


@pytest.fixture
def schema():
    egf = egf_local_dir()
    assert egf is not None, "no bundled EGF for the active brand"
    return load_mandate_schema(egf)


def test_the_six_submitted_fields_are_all_found(schema):
    assert set(schema.fields) == {
        "line_of_business", "jurisdiction", "coverages",
        "window_opens", "window_closes", "thesis",
    }
    assert all(f.required for f in schema.fields.values())


def test_line_of_business_carries_the_enum_from_the_bundle(schema):
    lob = schema.fields["line_of_business"]
    assert lob.enum is not None
    assert len(lob.enum) == 8
    assert "workers_compensation" in lob.enum
    assert lob.pattern is None


def test_jurisdiction_carries_a_pattern_and_no_enum(schema):
    j = schema.fields["jurisdiction"]
    assert j.pattern is not None and j.pattern.startswith("^US-")
    assert j.enum is None, (
        "if the EGF ever gains a jurisdiction enum, the form should offer a "
        "dropdown -- see the design spec's jurisdiction decision")


def test_coverages_carries_array_constraints(schema):
    c = schema.fields["coverages"]
    assert c.type == "array"
    assert c.min_items == 1
    assert c.unique_items is True
    assert c.item_pattern is not None


def test_both_window_fields_are_dates(schema):
    assert schema.fields["window_opens"].fmt == "date"
    assert schema.fields["window_closes"].fmt == "date"


def test_thesis_has_a_min_length(schema):
    assert schema.fields["thesis"].min_length == 1


def test_order_is_the_declared_field_order_not_alphabetical(schema):
    assert schema.order[0] == "line_of_business"
    assert schema.order != tuple(sorted(schema.order))


def test_a_directory_with_no_egf_doc_fails_loudly(tmp_path):
    with pytest.raises(SchemaSourceError, match="no egf-doc"):
        load_mandate_schema(tmp_path)


def test_the_brand_fixture_actually_activated_an_egf_dir():
    """Guards the conftest. Without brand activation `egf_local_dir()` is None and
    every test above would fail on its fixture rather than on its subject -- so
    assert the precondition directly, once."""
    egf = egf_local_dir()
    assert egf is not None and egf.is_dir()
    assert egf.name == "egf" and egf.parent.name == "usurance"
