"""Tests for locksmith-plugin.toml parsing + validation."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from locksmith.plugins.manifest import (
    Manifest,
    ManifestError,
    parse_manifest,
    parse_manifest_text,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "plugins"


def test_parse_echo_app_fixture():
    m = parse_manifest(FIXTURE_ROOT / "echo-app" / "locksmith-plugin.toml")
    assert m.plugin_id == "echo_app"
    assert m.entry_point == "echo_app.plugin:EchoAppPlugin"
    assert m.manifest_version == 1
    assert m.name == "Echo App"
    assert m.version == "0.1.0"
    assert m.requires_locksmith == ">=0.0.1"
    assert m.capabilities == ["app.service"]
    assert m.capabilities_detail == {
        "app.service": "Logs lifecycle events for test assertions.",
    }


def test_parse_malformed_toml_raises():
    with pytest.raises(ManifestError) as exc:
        parse_manifest(FIXTURE_ROOT / "malformed-toml" / "locksmith-plugin.toml")
    assert "invalid toml" in str(exc.value).lower() or "parse" in str(exc.value).lower()


def test_parse_missing_required_fields_raises():
    with pytest.raises(ManifestError) as exc:
        parse_manifest(FIXTURE_ROOT / "missing-required-fields" / "locksmith-plugin.toml")
    msg = str(exc.value)
    assert "plugin_id" in msg
    assert "entry_point" in msg


def test_entry_point_format_validated():
    text = textwrap.dedent("""
        plugin_id = "x"
        entry_point = "no_colon_here"
        manifest_version = 1
        name = "x"
        version = "0.1.0"
        description = "x"
    """).strip()
    with pytest.raises(ManifestError) as exc:
        parse_manifest_text(text, source="<test>")
    assert "entry_point" in str(exc.value)
    assert "module:Class" in str(exc.value)


def test_plugin_id_format_validated():
    text = textwrap.dedent("""
        plugin_id = "has spaces"
        entry_point = "mod:Cls"
        manifest_version = 1
        name = "x"
        version = "0.1.0"
        description = "x"
    """).strip()
    with pytest.raises(ManifestError) as exc:
        parse_manifest_text(text, source="<test>")
    assert "plugin_id" in str(exc.value)


def test_manifest_to_dict_roundtrip():
    m = parse_manifest(FIXTURE_ROOT / "echo-app" / "locksmith-plugin.toml")
    d = m.to_dict()
    assert d["plugin_id"] == "echo_app"
    assert d["capabilities"] == ["app.service"]
    # to_dict is the snapshot stored in index.json — must be json-serializable.
    import json
    json.dumps(d)


def test_unknown_capabilities_preserved_verbatim():
    text = textwrap.dedent("""
        plugin_id = "x"
        entry_point = "mod:Cls"
        manifest_version = 1
        name = "x"
        version = "0.1.0"
        description = "x"
        capabilities = ["app.shortcut", "made.up.capability"]
    """).strip()
    m = parse_manifest_text(text, source="<test>")
    assert "made.up.capability" in m.capabilities
