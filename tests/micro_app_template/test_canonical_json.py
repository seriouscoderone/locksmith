"""Tests for micro-app-template canonical JSON serialization."""
from __future__ import annotations

import json

from locksmith.micro_app_template.canonical_json import canonicalize


def test_sorts_top_level_keys():
    obj = {"z": 1, "a": 2, "m": 3}
    out = canonicalize(obj)
    assert out.index('"a"') < out.index('"m"') < out.index('"z"')


def test_sorts_nested_keys_recursively():
    """Keys at every level must be sorted lexicographically."""
    obj = {"outer": {"z": 1, "a": 2}, "inner": {"y": 3, "b": 4}}
    expected = (
        '{\n'
        '  "inner": {\n'
        '    "b": 4,\n'
        '    "y": 3\n'
        '  },\n'
        '  "outer": {\n'
        '    "a": 2,\n'
        '    "z": 1\n'
        '  }\n'
        '}\n'
    )
    assert canonicalize(obj) == expected


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
    obj = {"z": 1, "a": {"y": 2, "b": [3, 1, 2]}, "m": "text"}
    once = canonicalize(obj)
    twice = canonicalize(json.loads(once))
    assert once == twice


def test_exact_output_for_known_input():
    """Pin the byte-exact contract — SAID computation depends on this."""
    expected = (
        '{\n'
        '  "a": [\n'
        '    2,\n'
        '    1\n'
        '  ],\n'
        '  "b": 1\n'
        '}\n'
    )
    assert canonicalize({"b": 1, "a": [2, 1]}) == expected


def test_empty_dict_and_list():
    assert canonicalize({}) == "{}\n"
    assert canonicalize([]) == "[]\n"


def test_sorts_special_character_keys():
    """Punctuation in keys must sort deterministically — matters for SAID stability."""
    obj = {"a/b": 1, "a-b": 2, "ab": 3, "a_b": 4}
    out = canonicalize(obj)
    # Lexicographic ASCII order: '-' (45) < '/' (47) < '_' (95) < no-suffix
    # So expected key order is: a-b, a/b, a_b, ab
    expected = '{\n  "a-b": 2,\n  "a/b": 1,\n  "a_b": 4,\n  "ab": 3\n}\n'
    assert out == expected
