"""Tests for micro-app-template canonical JSON serialization."""
from __future__ import annotations

from locksmith.micro_app_template.canonical_json import canonicalize


def test_sorts_top_level_keys():
    obj = {"z": 1, "a": 2, "m": 3}
    out = canonicalize(obj)
    assert out.index('"a"') < out.index('"m"') < out.index('"z"')


def test_sorts_nested_keys_recursively():
    obj = {"outer": {"z": 1, "a": 2}, "inner": {"y": 3, "b": 4}}
    out = canonicalize(obj)
    a_pos = out.index('"a"')
    z_pos = out.index('"z"')
    b_pos = out.index('"b"')
    y_pos = out.index('"y"')
    assert a_pos < z_pos
    assert b_pos < y_pos


def test_preserves_array_order():
    obj = {"items": ["c", "a", "b"]}
    out = canonicalize(obj)
    assert out.index('"c"') < out.index('"a"') < out.index('"b"')


def test_two_space_indent():
    obj = {"a": {"b": 1}}
    out = canonicalize(obj)
    assert '\n  "a"' in out
    assert '\n    "b"' in out


def test_ends_with_single_newline():
    obj = {"a": 1}
    out = canonicalize(obj)
    assert out.endswith("\n")
    assert not out.endswith("\n\n")


def test_utf8_unicode_preserved():
    obj = {"description": "Crédit licencié"}
    out = canonicalize(obj)
    assert "Crédit licencié" in out


def test_round_trip_stable():
    """canonicalize(parse(canonicalize(x))) == canonicalize(x)"""
    import json
    obj = {"z": 1, "a": {"y": 2, "b": [3, 1, 2]}, "m": "text"}
    once = canonicalize(obj)
    twice = canonicalize(json.loads(once))
    assert once == twice
