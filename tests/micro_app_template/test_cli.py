"""Tests for micro-app-template CLI wrappers."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent.parent
SAIDIFY = REPO_ROOT / "scripts/micro_app_saidify.py"
VALIDATE = REPO_ROOT / "scripts/micro_app_validate.py"


def _run(script: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
    )


def test_saidify_stamps_d_field(tmp_path, minimal_valid_template):
    doc = dict(minimal_valid_template)
    doc["d"] = "#" * 44
    src = tmp_path / "t.json"
    src.write_text(json.dumps(doc))
    result = _run(SAIDIFY, "--input", str(src), "--in-place")
    assert result.returncode == 0, result.stderr
    out = json.loads(src.read_text())
    assert out["d"] != "#" * 44
    assert len(out["d"]) == 44


def test_saidify_verify_passes_on_stamped(tmp_path, minimal_valid_template):
    doc = dict(minimal_valid_template)
    doc["d"] = "#" * 44
    src = tmp_path / "t.json"
    src.write_text(json.dumps(doc))
    _run(SAIDIFY, "--input", str(src), "--in-place")
    result = _run(SAIDIFY, "--input", str(src), "--verify")
    assert result.returncode == 0, result.stderr


def test_saidify_verify_fails_on_tampered(tmp_path, minimal_valid_template):
    doc = dict(minimal_valid_template)
    doc["d"] = "#" * 44
    src = tmp_path / "t.json"
    src.write_text(json.dumps(doc))
    _run(SAIDIFY, "--input", str(src), "--in-place")
    out = json.loads(src.read_text())
    out["header"]["display_name"] = "TAMPERED"
    src.write_text(json.dumps(out))
    result = _run(SAIDIFY, "--input", str(src), "--verify")
    assert result.returncode != 0


def test_validate_passes_on_valid(tmp_path, minimal_valid_template):
    doc = dict(minimal_valid_template)
    src = tmp_path / "t.json"
    src.write_text(json.dumps(doc))
    result = _run(VALIDATE, "--input", str(src))
    assert result.returncode == 0, result.stderr + result.stdout


def test_validate_fails_on_invalid(tmp_path, minimal_valid_template):
    doc = dict(minimal_valid_template)
    del doc["role"]
    src = tmp_path / "t.json"
    src.write_text(json.dumps(doc))
    result = _run(VALIDATE, "--input", str(src))
    assert result.returncode != 0
    assert "role" in (result.stdout + result.stderr).lower()
