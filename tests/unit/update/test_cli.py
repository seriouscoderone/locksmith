"""Tests for the ``--verify-update`` standalone CLI flag."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from locksmith.update import cli
from locksmith.update.errors import (
    HashMismatchError,
    NetworkError,
    SignatureError,
    StaleAppcastError,
    WitnessThresholdError,
)
from locksmith.update.verify import VerificationResult


def _ok_result() -> VerificationResult:
    return VerificationResult(
        ok=True,
        version="1.1.0",
        platform="macos",
        publisher_aid="EAaa",
        anchor_said="EHsh",
        artifact_sha256="abc" * 21 + "a",
        artifact_size=42,
        witness_receipts=3,
        kel_tip_sn=4,
    )


@pytest.fixture
def fake_anchor(monkeypatch):
    """Patch the embedded-anchor loader to a deterministic tuple."""
    def _load(platform):
        return ("appcast-bytes", "EAaa", 0, None, 3, platform)
    monkeypatch.setattr(cli, "_load_anchor_and_appcast", _load)


def test_verified_returns_exit_0(tmp_path, capsys, fake_anchor):
    artifact = tmp_path / "a.dmg"
    artifact.write_bytes(b"x")
    with patch("locksmith.update.cli.verify_artifact", return_value=_ok_result()):
        rc = cli.run(["--verify-update", str(artifact), "--platform", "macos"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "verified" in out.lower()
    assert "1.1.0" in out


@pytest.mark.parametrize(
    "exc_class,exit_code",
    [
        (SignatureError, 10),
        (HashMismatchError, 11),
        (WitnessThresholdError, 12),
        (StaleAppcastError, 13),
        (NetworkError, 14),
    ],
)
def test_each_failure_returns_correct_exit_code(
    tmp_path, exc_class, exit_code, fake_anchor
):
    artifact = tmp_path / "a.dmg"
    artifact.write_bytes(b"x")
    err = exc_class("synthetic", log_fields={"k": "v"})
    with patch("locksmith.update.cli.verify_artifact", side_effect=err):
        rc = cli.run(["--verify-update", str(artifact), "--platform", "macos"])
    assert rc == exit_code


def test_json_output_mode_on_success(tmp_path, capsys, fake_anchor):
    artifact = tmp_path / "a.dmg"
    artifact.write_bytes(b"x")
    with patch("locksmith.update.cli.verify_artifact", return_value=_ok_result()):
        rc = cli.run(
            ["--verify-update", str(artifact), "--platform", "macos", "--json"]
        )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["version"] == "1.1.0"
    assert payload["exit_code"] == 0
    assert payload["anchor_said"] == "EHsh"


def test_json_output_mode_on_failure(tmp_path, capsys, fake_anchor):
    artifact = tmp_path / "a.dmg"
    artifact.write_bytes(b"x")
    err = HashMismatchError(
        "bad", log_fields={"expected_sha256": "a", "actual_sha256": "b"}
    )
    with patch("locksmith.update.cli.verify_artifact", side_effect=err):
        rc = cli.run(
            ["--verify-update", str(artifact), "--platform", "macos", "--json"]
        )
    assert rc == 11
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["exit_code"] == 11
    assert payload["error"] == "HashMismatchError"
    assert payload["log_fields"]["expected_sha256"] == "a"


def test_never_offers_install_anyway(tmp_path, capsys, fake_anchor):
    """Spec §9.2: verification failure must NEVER suggest 'install anyway'."""
    artifact = tmp_path / "a.dmg"
    artifact.write_bytes(b"x")
    with patch(
        "locksmith.update.cli.verify_artifact",
        side_effect=HashMismatchError("bad"),
    ):
        cli.run(["--verify-update", str(artifact), "--platform", "macos"])
    captured = capsys.readouterr()
    combined = (captured.out + captured.err).lower()
    assert "install anyway" not in combined
    assert "override" not in combined
    assert "force" not in combined


def test_platform_autodetect_on_macos(tmp_path, fake_anchor):
    """On macOS test host, omit --platform → defaults to 'macos'."""
    import platform as _platform
    if _platform.system() != "Darwin":  # pragma: no cover
        pytest.skip("autodetect is platform-dependent")
    artifact = tmp_path / "a.dmg"
    artifact.write_bytes(b"x")
    with patch("locksmith.update.cli.verify_artifact", return_value=_ok_result()):
        rc = cli.run(["--verify-update", str(artifact)])
    assert rc == 0
