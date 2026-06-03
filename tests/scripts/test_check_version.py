"""Tests for scripts/check-version.py preflight."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "check-version.py"


def run(args, env=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def test_valid_tag_matches_pyproject(tmp_path, monkeypatch):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\nversion = "1.2.3"\n')
    result = run(["--tag", "v1.2.3", "--pyproject", str(pyproject), "--skip-tag-signature"])
    assert result.returncode == 0, result.stderr


def test_tag_mismatch_fails(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\nversion = "1.2.3"\n')
    result = run(["--tag", "v9.9.9", "--pyproject", str(pyproject), "--skip-tag-signature"])
    assert result.returncode == 1
    assert "tag v9.9.9 does not match pyproject version 1.2.3" in result.stderr


def test_invalid_semver_fails(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\nversion = "not-semver"\n')
    result = run(["--tag", "vnot-semver", "--pyproject", str(pyproject), "--skip-tag-signature"])
    assert result.returncode == 1
    assert "not valid semver" in result.stderr


def test_missing_v_prefix_fails(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\nversion = "1.2.3"\n')
    result = run(["--tag", "1.2.3", "--pyproject", str(pyproject), "--skip-tag-signature"])
    assert result.returncode == 1
    assert "must start with 'v'" in result.stderr


def test_unsigned_tag_fails(tmp_path, monkeypatch):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\nversion = "1.2.3"\n')
    # Without --skip-tag-signature, git verify-tag will be called on a tag that
    # doesn't exist in the test repo. Expect the script to fail with a clear error.
    result = run(["--tag", "v1.2.3", "--pyproject", str(pyproject)])
    assert result.returncode == 1
    assert "tag signature" in result.stderr.lower() or "verify-tag" in result.stderr.lower()
