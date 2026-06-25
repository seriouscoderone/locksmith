"""Sparkle bridge tests — pure-Python parts only (no PyObjC required).

The PyObjC ``NSObject`` adapter is exercised on a real macOS build (the
``devbuild-macos.sh`` loop + the signed install e2e); this unit test pins the
platform-neutral ``SparkleVerifierDelegate`` decision logic.

Sparkle 2's only BOOL veto, ``updater:shouldProceedWithUpdate:updateCheck:error:``,
fires BEFORE download (no hook ever exposes the staged artifact). So the gate
runs at that veto: the verifier closure (see ``apping._make_update_verifier_macos``)
fetches the artifact from the enclosure URL itself and runs ``verify_artifact``.
The delegate here just wraps that closure with logging / log-recording / the
failure callback.
"""
import sys

import pytest


def test_bridge_module_imports_on_all_platforms():
    # The module guards PyObjC behind sys.platform; should import everywhere.
    from locksmith.update import sparkle_bridge  # noqa: F401


def test_should_proceed_calls_verifier_with_url_and_returns_true_on_pass():
    from locksmith.update.sparkle_bridge import SparkleVerifierDelegate

    calls = {}

    def fake_verify(enclosure_url, release_info):
        calls["url"] = enclosure_url
        calls["release_info"] = release_info
        return True

    log_entries = []
    delegate = SparkleVerifierDelegate(
        verifier=fake_verify,
        log_recorder=lambda **kw: log_entries.append(kw),
        on_failure=lambda v: None,
    )

    info = {"version": "1.3.0", "anchor_said": "ESAID", "artifact_sha256": "ab"}
    result = delegate.shouldProceedWithUpdate(
        info, "https://cdn.example.com/Locksmith-1.3.0.dmg"
    )

    assert result is True
    assert calls["url"] == "https://cdn.example.com/Locksmith-1.3.0.dmg"
    assert calls["release_info"]["version"] == "1.3.0"
    assert log_entries and log_entries[0]["status"] == "verified"
    assert log_entries[0]["anchor_said"] == "ESAID"


def test_should_proceed_returns_false_and_fires_failure_on_fail():
    from locksmith.update.sparkle_bridge import SparkleVerifierDelegate

    failures = []
    log_entries = []

    delegate = SparkleVerifierDelegate(
        verifier=lambda url, info: False,
        log_recorder=lambda **kw: log_entries.append(kw),
        on_failure=lambda version: failures.append(version),
    )

    result = delegate.shouldProceedWithUpdate(
        {"version": "1.3.0"}, "https://cdn.example.com/x.dmg"
    )
    assert result is False
    assert failures == ["1.3.0"]
    assert log_entries and log_entries[0]["status"] == "failed"


def test_verifier_exception_treated_as_failure():
    from locksmith.update.sparkle_bridge import SparkleVerifierDelegate

    def _boom(url, info):
        raise RuntimeError("kel fetch timed out")

    failures = []
    delegate = SparkleVerifierDelegate(
        verifier=_boom,
        log_recorder=lambda **kw: None,
        on_failure=lambda v: failures.append(v),
    )
    assert (
        delegate.shouldProceedWithUpdate({"version": "1.3.0"}, "https://cdn/x.dmg")
        is False
    )
    assert failures == ["1.3.0"]


def test_missing_release_info_uses_unknown_version():
    """If Sparkle hands us an item with no version, fall back to 'unknown'."""
    from locksmith.update.sparkle_bridge import SparkleVerifierDelegate

    failures = []
    delegate = SparkleVerifierDelegate(
        verifier=lambda *a, **k: False,
        log_recorder=lambda **kw: None,
        on_failure=lambda v: failures.append(v),
    )
    delegate.shouldProceedWithUpdate({}, "https://cdn/x.dmg")
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


def test_sparkle_init_returns_none_triplet_off_darwin():
    """init_sparkle is a no-op on non-macOS platforms (3-tuple of None)."""
    if sys.platform == "darwin":
        pytest.skip("darwin has its own init test")
    from locksmith.update.sparkle_init import init_sparkle
    ctrl, py_del, objc_del = init_sparkle(
        verifier=lambda *a, **k: True,
        log_recorder=lambda **k: None,
        on_failure=lambda v: None,
    )
    assert ctrl is None
    assert py_del is None
    assert objc_del is None
