"""Tests for ``locksmith.update.appcast`` — schema validation + parsing."""
import json
from pathlib import Path

import pytest

from locksmith.update.appcast import (
    Appcast,
    Release,
    parse_appcast,
    select_latest_for_platform,
)
from locksmith.update.errors import SchemaError

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "update"


def load_macos_appcast() -> str:
    return (FIXTURES / "appcast" / "macos.json").read_text()


def test_parse_happy_path_macos():
    ac = parse_appcast(load_macos_appcast())
    assert isinstance(ac, Appcast)
    assert ac.schema_version == 1
    assert ac.channel == "stable"
    assert ac.current_version == "1.1.0"
    assert len(ac.releases) == 3
    versions = [r.version for r in ac.releases]
    assert versions == ["1.0.0", "1.0.1", "1.1.0"]


def test_release_dataclass_carries_all_fields():
    ac = parse_appcast(load_macos_appcast())
    r = ac.releases[-1]
    assert isinstance(r, Release)
    assert r.platform == "macos"
    assert r.artifact_sha256
    assert r.artifact_size > 0
    assert r.anchor_url.endswith("release-anchor-1.1.0.cesr")
    assert r.anchor_said
    assert r.is_major is True


def test_schema_version_mismatch_raises():
    raw = json.loads(load_macos_appcast())
    raw["schema_version"] = 2
    with pytest.raises(SchemaError) as e:
        parse_appcast(json.dumps(raw))
    assert "schema_version" in e.value.reason


def test_missing_required_field_raises():
    raw = json.loads(load_macos_appcast())
    del raw["publisher_aid"]
    with pytest.raises(SchemaError):
        parse_appcast(json.dumps(raw))


def test_missing_release_field_raises():
    raw = json.loads(load_macos_appcast())
    del raw["releases"][0]["anchor_said"]
    with pytest.raises(SchemaError) as e:
        parse_appcast(json.dumps(raw))
    assert "anchor_said" in e.value.reason


def test_select_latest_returns_current_version_release():
    ac = parse_appcast(load_macos_appcast())
    latest = select_latest_for_platform(ac, "macos")
    assert latest.version == "1.1.0"


def test_select_latest_wrong_platform_raises():
    ac = parse_appcast(load_macos_appcast())
    with pytest.raises(SchemaError) as e:
        select_latest_for_platform(ac, "linux")
    assert "platform" in e.value.reason.lower()


def test_releases_ordered_oldest_to_newest_by_semver():
    raw = json.loads(load_macos_appcast())
    raw["releases"] = list(reversed(raw["releases"]))
    ac2 = parse_appcast(json.dumps(raw))
    assert [r.version for r in ac2.releases] == ["1.0.0", "1.0.1", "1.1.0"]


def test_invalid_json_raises_schema_error():
    with pytest.raises(SchemaError):
        parse_appcast("not json at all")


def test_top_level_must_be_object():
    with pytest.raises(SchemaError):
        parse_appcast("[]")


def test_empty_releases_raises():
    raw = json.loads(load_macos_appcast())
    raw["releases"] = []
    with pytest.raises(SchemaError):
        parse_appcast(json.dumps(raw))


def test_invalid_semver_in_release_raises():
    raw = json.loads(load_macos_appcast())
    raw["releases"][0]["version"] = "not-semver"
    with pytest.raises(SchemaError) as e:
        parse_appcast(json.dumps(raw))
    assert "semver" in e.value.reason.lower()
