"""Validation is pure and Qt-free, so every rule is testable without a widget.

Rules come from two places, and the tests say which: the payload schema (enum,
pattern, minItems, uniqueItems, minLength, format) and the micro-app template's two
PRE-MINT gates (window ordering, scope overlap). The ordering gate matters most --
per its own description nothing re-checks it after issuance, so this module is the
last line of defence.
"""
import pytest

from locksmith.core.branding import egf_local_dir
from locksmith.plugins.cuo.schema_source import load_mandate_schema
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
])
def test_overlap_is_the_standard_inclusive_interval_test(a, b, expected):
    """'Overlap is the standard interval test -- each range starts on or before
    the other ends.' Touching endpoints DO overlap; both dates are in force."""
    assert windows_overlap(a[0], a[1], b[0], b[1]) is expected
