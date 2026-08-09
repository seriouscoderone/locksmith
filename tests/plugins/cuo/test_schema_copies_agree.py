# -*- encoding: utf-8 -*-
"""The mandate's constraints exist TWICE -- in the command's payload_schema and in
the ACDC schema. Two copies with no reconciler is how they drift; this is the
reconciler.

The form validates against payload_schema; the issuer validates against the ACDC
schema. If they disagree, the form passes input the mint rejects, and the user sees
a failure they cannot act on.

Matches the ACDC schema by `credentialType == "UsuranceProductMandate"`, never by
filename or SAID: the SAID changes whenever the schema is re-SAIDed, and a guard
pinned to today's filename would stop finding the schema the next time it is
re-derived, silently passing on nothing.
"""
import glob
import json

from locksmith.core.branding import egf_local_dir
from locksmith.plugins.cuo.schema_source import load_mandate_schema

_COMPARED = ("type", "enum", "pattern", "format", "minLength", "minItems",
             "uniqueItems", "items")


def _acdc_attribute_block() -> dict:
    egf = egf_local_dir()
    for path in glob.glob(f"{egf}/E*.json"):
        doc = json.loads(open(path).read())
        if doc.get("credentialType") != "UsuranceProductMandate":
            continue
        for option in doc["properties"]["a"].get("oneOf", []):
            if option.get("type") == "object":
                return option
    raise AssertionError("no product-mandate ACDC schema in the bundle")


def test_every_payload_field_matches_the_acdc_schema():
    payload = load_mandate_schema(egf_local_dir())
    acdc = _acdc_attribute_block()["properties"]
    for name in payload.order:
        assert name in acdc, f"{name} is in payload_schema but not the ACDC schema"
    field = payload.fields
    for name in payload.order:
        a = acdc[name]
        f = field[name]
        assert (tuple(a["enum"]) if a.get("enum") else None) == f.enum, name
        assert a.get("pattern") == f.pattern, name
        assert a.get("format") == f.fmt, name
        assert a.get("minLength") == f.min_length, name
        assert a.get("minItems") == f.min_items, name
        assert bool(a.get("uniqueItems")) == f.unique_items, name


def test_required_sets_agree():
    payload = load_mandate_schema(egf_local_dir())
    acdc_required = set(_acdc_attribute_block().get("required") or ())
    payload_required = {n for n, f in payload.fields.items() if f.required}
    assert payload_required <= acdc_required, (
        payload_required - acdc_required)
