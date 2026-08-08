"""The form's controls and rules come from the EGF, so this is where that starts.

Uses the REAL bundled EGF, not a fixture. A hand-built schema fixture would let the
loader and the shipped bundle drift apart silently, which is the exact defect class
this whole plan exists to close.

One exception: `test_a_field_missing_from_required_is_optional_and_appended_last`
below uses a synthetic EGF on purpose. Every field in the real bundled template
happens to be required, so the `required=False` path and `order`'s append-fallback
path are both permanently unreachable against the shipped bundle alone -- the real
bundle cannot express the case a mutation test needs (confirmed: hardcoding
`required=True` unconditionally in `_constraints` still left the suite green before
that test was added). Everywhere else in this module, testing only against the real
bundle stays correct.
"""
import json

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


def test_a_field_missing_from_required_is_optional_and_appended_last(tmp_path):
    """Synthetic EGF, deliberately -- see the module docstring for why.

    `beta` is declared in `properties` but left out of `required`. That must
    produce a `FieldConstraints(required=False)` for `beta`, AND `beta` must
    land at the end of `order` (the append-fallback branch for anything the
    author didn't position via `required`). Both assertions are needed: either
    one alone would pass under a mutant that gets the other wrong.
    """
    said = "ETESTCUOTEMPLATE0000000000000000000000000A"
    egf_doc = {
        "spec_version": "egf-doc/0.1",
        "micro_apps": [{"said": said, "id": "test-cuo", "role_id": "cuo"}],
    }
    template = {
        "commands": [{
            "id": "declare_product_mandate",
            "payload_schema": {
                "type": "object",
                "properties": {
                    "alpha": {"type": "string"},
                    "beta": {"type": "string"},
                    "gamma": {"type": "string"},
                },
                "required": ["gamma", "alpha"],
            },
        }],
    }
    (tmp_path / "Etest-egf-doc.json").write_text(json.dumps(egf_doc), encoding="utf-8")
    (tmp_path / f"{said}.json").write_text(json.dumps(template), encoding="utf-8")

    schema = load_mandate_schema(tmp_path)

    assert schema.fields["beta"].required is False
    assert schema.fields["alpha"].required is True
    assert schema.fields["gamma"].required is True
    assert schema.order[-1] == "beta"
    assert schema.order[:2] == ("gamma", "alpha")
