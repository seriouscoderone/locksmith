"""Sparkle bridge tests — pure-Python parts only (no PyObjC required).

The PyObjC ``NSObject`` adapter is exercised by the macOS integration
test in a later task; this unit test pins the platform-neutral
``SparkleVerifierDelegate`` decision logic.
"""
import sys

import pytest


def test_bridge_module_imports_on_all_platforms():
    # The module guards PyObjC behind sys.platform; should import everywhere.
    from locksmith.update import sparkle_bridge  # noqa: F401


def test_should_proceed_calls_verifier_and_returns_true_on_pass(tmp_path):
    from locksmith.update.sparkle_bridge import SparkleVerifierDelegate

    staged = tmp_path / "Locksmith-1.3.0.dmg"
    staged.write_bytes(b"fake")

    calls = {}

    def fake_verify(artifact_path, release_info):
        calls["artifact_path"] = artifact_path
        calls["release_info"] = release_info
        return True

    log_entries = []
    delegate = SparkleVerifierDelegate(
        verifier=fake_verify,
        log_recorder=lambda **kw: log_entries.append(kw),
        on_failure=lambda v: None,
    )
    delegate.willDownloadUpdate(
        {"version": "1.3.0", "anchor_said": "ESAID"},
    )

    result = delegate.shouldProceedWithInstall(str(staged))
    assert result is True
    assert calls["artifact_path"] == str(staged)
    assert calls["release_info"]["version"] == "1.3.0"
    assert log_entries and log_entries[0]["status"] == "verified"
    assert staged.exists()  # success path leaves the artifact alone


def test_should_proceed_deletes_artifact_and_returns_false_on_fail(tmp_path):
    from locksmith.update.sparkle_bridge import SparkleVerifierDelegate

    staged = tmp_path / "Locksmith-1.3.0.dmg"
    staged.write_bytes(b"tampered")

    failures = []
    log_entries = []

    delegate = SparkleVerifierDelegate(
        verifier=lambda path, info: False,
        log_recorder=lambda **kw: log_entries.append(kw),
        on_failure=lambda version: failures.append(version),
    )
    delegate.willDownloadUpdate(
        {"version": "1.3.0", "anchor_said": "ESAID"},
    )

    result = delegate.shouldProceedWithInstall(str(staged))
    assert result is False
    assert not staged.exists()
    assert failures == ["1.3.0"]
    assert log_entries and log_entries[0]["status"] == "failed"


def test_verifier_exception_treated_as_failure(tmp_path):
    from locksmith.update.sparkle_bridge import SparkleVerifierDelegate

    staged = tmp_path / "Locksmith-1.3.0.dmg"
    staged.write_bytes(b"x")

    def _boom(path, info):
        raise RuntimeError("kel fetch timed out")

    failures = []
    delegate = SparkleVerifierDelegate(
        verifier=_boom,
        log_recorder=lambda **kw: None,
        on_failure=lambda v: failures.append(v),
    )
    delegate.willDownloadUpdate({"version": "1.3.0"})
    assert delegate.shouldProceedWithInstall(str(staged)) is False
    assert failures == ["1.3.0"]


def test_missing_release_info_uses_unknown_version(tmp_path):
    """If Sparkle skipped willDownloadUpdate (shouldn't happen, but guard)."""
    from locksmith.update.sparkle_bridge import SparkleVerifierDelegate

    staged = tmp_path / "x.dmg"
    staged.write_bytes(b"x")
    failures = []
    delegate = SparkleVerifierDelegate(
        verifier=lambda *a, **k: False,
        log_recorder=lambda **kw: None,
        on_failure=lambda v: failures.append(v),
    )
    delegate.shouldProceedWithInstall(str(staged))
    assert failures == ["unknown"]


@pytest.mark.skipif(sys.platform == "darwin", reason="macOS has PyObjC")
def test_make_objc_delegate_returns_none_without_pyobjc():
    from locksmith.update.sparkle_bridge import (
        SparkleVerifierDelegate, make_objc_delegate,
    )
    delegate = SparkleVerifierDelegate(
        verifier=lambda *a, **k: True,
        log_recorder=lambda **k: None,
        on_failure=lambda v: None,
    )
    assert make_objc_delegate(delegate) is None


def test_sparkle_init_returns_none_off_darwin():
    """init_sparkle is a no-op on non-macOS platforms."""
    if sys.platform == "darwin":
        pytest.skip("darwin has its own init test")
    from locksmith.update.sparkle_init import init_sparkle
    ctrl, py_del = init_sparkle(
        verifier=lambda *a, **k: True,
        log_recorder=lambda **k: None,
        on_failure=lambda v: None,
    )
    assert ctrl is None
    assert py_del is None
