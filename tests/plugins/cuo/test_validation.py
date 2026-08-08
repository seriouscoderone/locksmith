"""Validation is pure and Qt-free, so every rule is testable without a widget.

Rules come from two places, and the tests say which: the payload schema (enum,
pattern, minItems, uniqueItems, minLength, format) and the micro-app template's two
PRE-MINT gates (window ordering, scope overlap). The ordering gate matters most --
per its own description nothing re-checks it after issuance, so this module is the
last line of defence.
"""
from datetime import date

import pytest

from locksmith.core.branding import egf_local_dir
from locksmith.plugins.cuo import mandate_copy as copy
from locksmith.plugins.cuo.schema_source import (
    FieldConstraints,
    MandateSchema,
    load_mandate_schema,
)
from locksmith.plugins.cuo.validation import (
    FieldError,
    validate_payload,
    windows_overlap,
)


@pytest.fixture
def schema():
    return load_mandate_schema(egf_local_dir())


def _good() -> dict:
    return {
        "line_of_business": "auto",
        "jurisdiction": "US-UT",
        "coverages": ["BI", "PD"],
        "window_opens": "2027-01-01",
        "window_closes": "2027-12-31",
        "thesis": "Grow teen-driver share in Utah.",
    }


def _fields(errors: list[FieldError]) -> set[str]:
    return {e.field for e in errors}


def test_a_good_payload_has_no_errors(schema):
    assert validate_payload(_good(), schema) == []


def test_every_missing_required_field_is_reported_at_once(schema):
    errors = validate_payload({}, schema)
    assert _fields(errors) == {
        "line_of_business", "jurisdiction", "coverages",
        "window_opens", "window_closes", "thesis",
    }, "the summary banner counts these, so all six must report together"


def test_missing_required_fields_are_reported_in_copy_field_order_not_schema_order(schema):
    """`_fields()` above returns a SET, which is blind to sequence. Asserting a
    list against the REAL bundled schema is not enough either: measured,
    `schema.order` already happens to equal `copy.FIELD_ORDER` on this bundle
    (`schema_source.py`'s own docstring calls this out as a coincidence, not a
    guarantee), so mutating `copy.FIELD_ORDER` to `schema.order` in
    `validate_payload` would survive a test that only used the `schema`
    fixture. Build a schema whose `.order` deliberately disagrees, and assert
    the reported sequence still follows `copy.FIELD_ORDER` -- the form focuses
    the first invalid field, so the sequence itself is user-visible."""
    scrambled_order = tuple(reversed(copy.FIELD_ORDER))
    assert scrambled_order != copy.FIELD_ORDER, "the reversal must actually differ"
    scrambled_schema = MandateSchema(fields=dict(schema.fields), order=scrambled_order)
    errors = validate_payload({}, scrambled_schema)
    assert [e.field for e in errors] == list(copy.FIELD_ORDER)


def test_a_value_outside_the_enum_is_rejected(schema):
    payload = _good() | {"line_of_business": "automobile"}
    errors = validate_payload(payload, schema)
    assert _fields(errors) == {"line_of_business"}


def test_a_jurisdiction_that_fails_the_pattern_is_rejected(schema):
    for bad in ("UTAH", "US-U", "us-ut", "UT"):
        errors = validate_payload(_good() | {"jurisdiction": bad}, schema)
        assert _fields(errors) == {"jurisdiction"}, bad


def test_a_structurally_valid_but_fictional_jurisdiction_passes(schema):
    """US-TU matches ^US-[A-Z]{2}$ and the EGF enumerates no subdivisions, so this
    MUST pass here. It is caught by the human read-back, not by validation -- see
    the design spec's jurisdiction decision. A test asserting otherwise would be
    asserting a check the app cannot perform."""
    assert validate_payload(_good() | {"jurisdiction": "US-TU"}, schema) == []


def test_a_lowercase_coverage_is_rejected(schema):
    errors = validate_payload(_good() | {"coverages": ["bi"]}, schema)
    assert _fields(errors) == {"coverages"}


def test_a_duplicate_coverage_is_rejected(schema):
    errors = validate_payload(_good() | {"coverages": ["BI", "BI"]}, schema)
    assert _fields(errors) == {"coverages"}
    assert "BI" in errors[0].message, "the error must name the offending value"


def test_an_empty_coverage_list_is_rejected(schema):
    errors = validate_payload(_good() | {"coverages": []}, schema)
    assert _fields(errors) == {"coverages"}


def test_an_unhashable_coverage_item_does_not_crash_the_duplicate_check(schema):
    """MINOR regression: a nested list is unhashable, so `item in seen` used
    to raise `TypeError` straight out of the uniqueness check -- a crash at
    the submit button. Membership must use `str(item)`, matching the pattern
    loop just below it."""
    errors = validate_payload(_good() | {"coverages": [["BI"], ["BI"]]}, schema)
    assert _fields(errors) == {"coverages"}


def test_a_non_list_coverages_reports_a_shape_problem_not_add_a_code(schema):
    """MINOR regression: a bare string for `coverages` used to report "Add at
    least one coverage code," which misdiagnoses a value the user DID supply
    -- it is the wrong shape, not empty."""
    errors = validate_payload(_good() | {"coverages": "BI"}, schema)
    assert _fields(errors) == {"coverages"}
    assert "at least one" not in errors[0].message.lower()


def test_a_non_date_is_rejected(schema):
    errors = validate_payload(_good() | {"window_opens": "01/01/2027"}, schema)
    assert _fields(errors) == {"window_opens"}


def test_a_window_that_closes_before_it_opens_is_rejected(schema):
    payload = _good() | {"window_opens": "2027-12-31", "window_closes": "2027-01-01"}
    errors = validate_payload(payload, schema)
    assert _fields(errors) == {"window_closes"}


def test_a_single_day_window_is_rejected_because_the_gate_is_strict(schema):
    """`command.window_opens < command.window_closes` is strict, so equal dates
    fail. The field help promises a two-day floor for exactly this reason."""
    payload = _good() | {"window_opens": "2027-06-01", "window_closes": "2027-06-01"}
    assert _fields(validate_payload(payload, schema)) == {"window_closes"}


def test_a_non_dash_iso_form_that_inverts_the_window_is_still_rejected(schema):
    """CRITICAL regression: `date.fromisoformat` has accepted every ISO 8601
    date form since Python 3.11 (`20270101` as well as `2027-01-01`), and the
    schema puts no `pattern` on these fields -- only `format: date`. A string
    compare between two different forms inverts, because `'-'` is 0x2D and
    `'0'` is 0x30: `"2027-12-31" < "20270101"` is True even though
    2027-12-31 is chronologically LATER. An earlier revision that compared raw
    strings let this validate clean; the gate must compare parsed dates."""
    payload = _good() | {"window_opens": "2027-12-31", "window_closes": "20270101"}
    errors = validate_payload(payload, schema)
    assert _fields(errors) == {"window_closes"}


def test_an_iso_week_form_that_inverts_the_window_is_still_rejected(schema):
    """Same defect, the other ISO 8601 form Python accepts: `YYYY-Www-D`."""
    payload = _good() | {"window_opens": "2027-12-31", "window_closes": "2027-W01-1"}
    errors = validate_payload(payload, schema)
    assert _fields(errors) == {"window_closes"}


def test_a_python_date_object_is_rejected_by_the_field_check_not_silently_accepted(schema):
    """CRITICAL regression: `str(date(2027, 1, 1)) == "2027-01-01"`, so an
    earlier revision's `str()` coercion made a `date` object pass the
    field-level format check silently -- and then made the ordering gate's own
    `isinstance(value, str)` guard False, skipping the ordering/overlap check
    entirely. That let a -364-day window (`window_opens=date(2027,12,31)`,
    `window_closes=date(2027,1,1)`) validate clean. Non-strings must be
    rejected at the field check, not coerced."""
    payload = _good() | {
        "window_opens": date(2027, 12, 31), "window_closes": date(2027, 1, 1),
    }
    errors = validate_payload(payload, schema)
    assert _fields(errors) == {"window_opens", "window_closes"}


def test_an_int_window_value_is_rejected_by_the_field_check_not_silently_accepted(schema):
    """Same defect, the other non-string shape: an int, which also survives
    `str()` coercion (`str(20270101) == "20270101"`, itself a valid ISO form)."""
    payload = _good() | {"window_opens": 20271231, "window_closes": 20270101}
    errors = validate_payload(payload, schema)
    assert _fields(errors) == {"window_opens", "window_closes"}


def test_an_overlapping_mandate_for_the_same_scope_is_rejected(schema):
    existing = [{
        "line_of_business": "auto", "jurisdiction": "US-UT",
        "window_opens": "2027-06-01", "window_closes": "2028-06-01",
    }]
    errors = validate_payload(_good(), schema, existing=existing)
    assert _fields(errors) == {"window_opens"}
    assert "US-UT" in errors[0].message


def test_a_different_line_or_jurisdiction_is_not_an_overlap(schema):
    """'A further jurisdiction or a further line is NOT an overlap and is
    accepted, which is how scope is added.'"""
    for differing in ({"line_of_business": "property"}, {"jurisdiction": "US-NV"}):
        existing = [{
            "line_of_business": "auto", "jurisdiction": "US-UT",
            "window_opens": "2027-06-01", "window_closes": "2028-06-01",
        } | differing]
        assert validate_payload(_good(), schema, existing=existing) == []


def test_a_non_overlapping_window_for_the_same_scope_is_accepted(schema):
    existing = [{
        "line_of_business": "auto", "jurisdiction": "US-UT",
        "window_opens": "2028-01-01", "window_closes": "2028-12-31",
    }]
    assert validate_payload(_good(), schema, existing=existing) == []


@pytest.mark.parametrize("a,b,expected", [
    (("2027-01-01", "2027-06-01"), ("2027-05-01", "2027-12-01"), True),
    (("2027-01-01", "2027-06-01"), ("2027-06-01", "2027-12-01"), True),
    (("2027-01-01", "2027-06-01"), ("2027-06-02", "2027-12-01"), False),
    # The mirror of the touching-endpoint case above: the EXISTING mandate
    # ends exactly the day the new one opens. The first three cases only
    # exercise the `a_opens <= b_closes` half of the test -- mutating it to
    # `<` would still pass all three. This one only passes if that half is
    # also `<=`.
    (("2027-06-01", "2027-06-30"), ("2027-05-01", "2027-06-01"), True),
])
def test_overlap_is_the_standard_inclusive_interval_test(a, b, expected):
    """'Overlap is the standard interval test -- each range starts on or before
    the other ends.' Touching endpoints DO overlap; both dates are in force."""
    assert windows_overlap(a[0], a[1], b[0], b[1]) is expected


def test_min_length_is_enforced_above_the_floor_the_real_schema_uses(schema):
    """The real schema's `minLength` on `thesis` is 1, which `_empty()`
    already catches before this branch ever runs -- the only value that could
    violate `minLength: 1` is empty. Synthesize a tighter floor to actually
    exercise the branch: mutating it to `if False:` would otherwise survive
    every test in this module."""
    c = FieldConstraints(
        name="thesis", type="string", required=True, enum=None, pattern=None,
        fmt=None, min_length=5, item_pattern=None, min_items=None,
        unique_items=False, description="",
    )
    tight_schema = MandateSchema(fields={"thesis": c}, order=("thesis",))
    errors = validate_payload({"thesis": "hi"}, tight_schema)
    assert _fields(errors) == {"thesis"}


def test_min_items_is_enforced_above_the_floor_the_real_schema_uses(schema):
    """Same reasoning as the `min_length` test above, for `coverages`' real
    `minItems: 1` -- synthesize `minItems: 2` so a non-empty but too-short
    list actually reaches the branch."""
    c = FieldConstraints(
        name="coverages", type="array", required=True, enum=None, pattern=None,
        fmt=None, min_length=None, item_pattern=None, min_items=2,
        unique_items=False, description="",
    )
    tight_schema = MandateSchema(fields={"coverages": c}, order=("coverages",))
    errors = validate_payload({"coverages": ["BI"]}, tight_schema)
    assert _fields(errors) == {"coverages"}
