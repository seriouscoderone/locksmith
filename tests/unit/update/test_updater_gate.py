"""Tests for the native-updater verify gates (``apping._make_update_verifier_macos``
/ ``_make_update_verifier_windows``).

Each gate is the closure handed to Sparkle/WinSparkle as ``verifier=``. It must:

* ENFORCE when a real publisher anchor is resolvable — self-download the
  artifact and call ``verify_artifact`` with the anchor-mapped params.
* Stay DARK when no real anchor is injected (``_load_publisher_anchor`` raises
  ``FileNotFoundError``) — allow without verifying, so pre-cutover builds never
  block updates.

macOS returns ``bool`` (Sparkle's pre-download veto); Windows returns
``(ok, version)`` (WinSparkle's can_shutdown gate). See ``sparkle_bridge`` /
``winsparkle_bridge``.
"""
from __future__ import annotations

import types

import pytest

from locksmith.core import apping
from locksmith.update import errors as update_errors


def _valid_anchor() -> dict:
    return {
        "publisher_aid": "EAbcdefPublisherAID0000000000000000000000000",
        "embedded_kel_sn": 2,
        # NOTE: anchor file uses ``embedded_kel_hash``; verify_artifact's
        # param is ``embedded_kel_said``. The mapping lives in
        # cli._load_anchor_and_appcast and must be honored by the gate.
        "embedded_kel_hash": "EHashSaidOfEmbeddedKelEvent00000000000000000",
        "toad": 4,
    }


# The dark + enforce + anchor-param-mapping paths are covered by the macOS and
# Windows gate tests below (which exercise the shared _anchor_and_appcast_or_dark
# + _run_verify_artifact helpers). The old platform-neutral _make_update_verifier
# was retired once each platform got its own factory.


# --- macOS gate (Sparkle pre-download veto): downloads the artifact itself ---
#
# Sparkle never exposes the staged artifact, so the macOS gate fetches the
# enclosure URL itself, then runs the same verify_artifact pipeline on the
# bytes it fetched. Signature is ``(enclosure_url: str, info: dict) -> bool``.


def _loaded_anchor_tuple(anchor):
    return (
        "<appcast-raw>",
        anchor["publisher_aid"],
        anchor["embedded_kel_sn"],
        anchor["embedded_kel_hash"],
        anchor["toad"],
        "macos",
    )


def test_macos_gate_downloads_then_verifies(monkeypatch, tmp_path):
    anchor = _valid_anchor()
    monkeypatch.setattr(
        apping,
        "_load_anchor_and_appcast",
        lambda platform: _loaded_anchor_tuple(anchor),
        raising=True,
    )

    # _download_to_temp returns a real temp file we can assert gets cleaned up.
    downloaded = tmp_path / "Locksmith.dmg.download"
    downloaded.write_bytes(b"fake-dmg-bytes")
    dl_calls = []

    def fake_download(url):
        dl_calls.append(url)
        return downloaded

    monkeypatch.setattr(apping, "_download_to_temp", fake_download, raising=True)

    spy_calls = []

    def spy_verify_artifact(**kwargs):
        spy_calls.append(kwargs)
        # The artifact must still exist while verify_artifact runs.
        assert kwargs["artifact_path"].exists()
        return types.SimpleNamespace(ok=True)

    monkeypatch.setattr(apping, "verify_artifact", spy_verify_artifact, raising=True)

    gate = apping._make_update_verifier_macos()
    info = {"version": "1.2.3", "anchor_said": "EReleaseSeal"}
    result = gate("https://cdn.example.com/Locksmith.dmg", info)

    assert result is True
    assert dl_calls == ["https://cdn.example.com/Locksmith.dmg"]
    assert len(spy_calls) == 1
    assert spy_calls[0]["artifact_path"] == downloaded
    assert spy_calls[0]["embedded_kel_said"] == anchor["embedded_kel_hash"]
    # The temp file the gate downloaded is cleaned up afterwards.
    assert not downloaded.exists()


def test_macos_gate_dark_skips_download(monkeypatch):
    def raise_missing(platform):
        raise FileNotFoundError("no publisher_anchor.json found")

    monkeypatch.setattr(
        apping, "_load_anchor_and_appcast", raise_missing, raising=True
    )

    def must_not_download(url):
        raise AssertionError("downloaded in dark mode")

    monkeypatch.setattr(apping, "_download_to_temp", must_not_download, raising=True)
    monkeypatch.setattr(
        apping,
        "verify_artifact",
        lambda **k: (_ for _ in ()).throw(AssertionError("verify in dark mode")),
        raising=True,
    )

    gate = apping._make_update_verifier_macos()
    assert gate("https://cdn.example.com/x.dmg", {"version": "9.9.9"}) is True


def test_macos_gate_fail_closed_on_download_error(monkeypatch):
    anchor = _valid_anchor()
    monkeypatch.setattr(
        apping,
        "_load_anchor_and_appcast",
        lambda platform: _loaded_anchor_tuple(anchor),
        raising=True,
    )

    def boom_download(url):
        raise update_errors.NetworkError("connection refused", log_fields={"url": url})

    monkeypatch.setattr(apping, "_download_to_temp", boom_download, raising=True)
    monkeypatch.setattr(
        apping,
        "verify_artifact",
        lambda **k: (_ for _ in ()).throw(AssertionError("verify after failed dl")),
        raising=True,
    )

    gate = apping._make_update_verifier_macos()
    # Trust is active but we couldn't fetch the bytes to verify -> fail closed.
    assert gate("https://cdn.example.com/x.dmg", {"version": "1.2.3"}) is False


def test_macos_gate_returns_false_when_verify_fails(monkeypatch, tmp_path):
    anchor = _valid_anchor()
    monkeypatch.setattr(
        apping,
        "_load_anchor_and_appcast",
        lambda platform: _loaded_anchor_tuple(anchor),
        raising=True,
    )
    downloaded = tmp_path / "tampered.dmg.download"
    downloaded.write_bytes(b"tampered")
    monkeypatch.setattr(
        apping, "_download_to_temp", lambda url: downloaded, raising=True
    )
    monkeypatch.setattr(
        apping,
        "verify_artifact",
        lambda **k: types.SimpleNamespace(ok=False),
        raising=True,
    )

    gate = apping._make_update_verifier_macos()
    assert gate("https://cdn.example.com/x.dmg", {"version": "1.2.3"}) is False
    assert not downloaded.exists()  # temp cleaned even on verification failure


def test_macos_gate_calls_on_verified_with_result_on_success(monkeypatch, tmp_path):
    """On an enforced PASS the gate hands the VerificationResult to on_verified
    (the app persists it so the Release Verification dialog can show the proof)."""
    anchor = _valid_anchor()
    monkeypatch.setattr(
        apping, "_load_anchor_and_appcast",
        lambda platform: _loaded_anchor_tuple(anchor), raising=True,
    )
    downloaded = tmp_path / "ok.dmg.download"
    downloaded.write_bytes(b"bytes")
    monkeypatch.setattr(apping, "_download_to_temp", lambda url: downloaded, raising=True)
    result = types.SimpleNamespace(ok=True, version="0.2.10", kel_tip_sn=7)
    monkeypatch.setattr(apping, "verify_artifact", lambda **k: result, raising=True)

    seen = []
    gate = apping._make_update_verifier_macos(on_verified=seen.append)
    assert gate("https://cdn.example.com/x.dmg", {"version": "0.2.10"}) is True
    assert seen == [result]  # exactly the VerificationResult, once


def test_macos_gate_does_not_call_on_verified_in_dark(monkeypatch):
    monkeypatch.setattr(
        apping, "_load_anchor_and_appcast",
        lambda platform: (_ for _ in ()).throw(FileNotFoundError("no anchor")),
        raising=True,
    )
    seen = []
    gate = apping._make_update_verifier_macos(on_verified=seen.append)
    assert gate("https://cdn.example.com/x.dmg", {"version": "9.9.9"}) is True
    assert seen == []  # dark allows but records no cryptographic proof


# --- Windows gate (WinSparkle): no-arg self-fetch (() -> (ok, version)) -----
#
# WinSparkle 0.8.3 hands its callbacks nothing, so the gate derives the MSI URL
# from the appcast itself, self-downloads, and verifies. It returns
# ``(ok, version)`` and must NEVER raise (it runs in a C callback).


def _fake_release(url="https://cdn.example.com/Locksmith-0.2.10.msi", version="0.2.10"):
    return types.SimpleNamespace(
        version=version, artifact_url=url, artifact_sha256="deadbeef",
    )


def test_windows_gate_downloads_then_verifies(monkeypatch, tmp_path):
    anchor = _valid_anchor()
    monkeypatch.setattr(
        apping, "_load_anchor_and_appcast",
        lambda platform: _loaded_anchor_tuple(anchor), raising=True,
    )
    monkeypatch.setattr(apping, "parse_appcast", lambda raw: object(), raising=True)
    rel = _fake_release()
    monkeypatch.setattr(
        apping, "select_latest_for_platform", lambda ac, plat: rel, raising=True
    )
    downloaded = tmp_path / "Locksmith-0.2.10.msi.download"
    downloaded.write_bytes(b"msi-bytes")
    dl = []
    monkeypatch.setattr(
        apping, "_download_to_temp", lambda url: dl.append(url) or downloaded,
        raising=True,
    )
    result = types.SimpleNamespace(ok=True, version="0.2.10")
    monkeypatch.setattr(apping, "verify_artifact", lambda **k: result, raising=True)

    seen = []
    gate = apping._make_update_verifier_windows(on_verified=seen.append)
    ok, version = gate()
    assert ok is True and version == "0.2.10"
    assert dl == [rel.artifact_url]          # self-downloaded the MSI URL from the appcast
    assert seen == [result]                  # proof handed to on_verified
    assert not downloaded.exists()           # temp cleaned


def test_windows_gate_dark_allows_without_download(monkeypatch):
    monkeypatch.setattr(
        apping, "_load_anchor_and_appcast",
        lambda platform: (_ for _ in ()).throw(FileNotFoundError("no anchor")),
        raising=True,
    )
    monkeypatch.setattr(
        apping, "_download_to_temp",
        lambda url: (_ for _ in ()).throw(AssertionError("downloaded in dark")),
        raising=True,
    )
    assert apping._make_update_verifier_windows()() == (True, "")


def test_windows_gate_blocks_on_download_failure(monkeypatch):
    anchor = _valid_anchor()
    monkeypatch.setattr(
        apping, "_load_anchor_and_appcast",
        lambda platform: _loaded_anchor_tuple(anchor), raising=True,
    )
    monkeypatch.setattr(apping, "parse_appcast", lambda raw: object(), raising=True)
    monkeypatch.setattr(
        apping, "select_latest_for_platform", lambda ac, plat: _fake_release(),
        raising=True,
    )
    monkeypatch.setattr(
        apping, "_download_to_temp",
        lambda url: (_ for _ in ()).throw(
            update_errors.NetworkError("refused", log_fields={})),
        raising=True,
    )
    monkeypatch.setattr(
        apping, "verify_artifact",
        lambda **k: (_ for _ in ()).throw(AssertionError("verify after dl fail")),
        raising=True,
    )
    ok, version = apping._make_update_verifier_windows()()
    assert ok is False and version == "0.2.10"


def test_windows_gate_blocks_and_cleans_on_verify_failure(monkeypatch, tmp_path):
    anchor = _valid_anchor()
    monkeypatch.setattr(
        apping, "_load_anchor_and_appcast",
        lambda platform: _loaded_anchor_tuple(anchor), raising=True,
    )
    monkeypatch.setattr(apping, "parse_appcast", lambda raw: object(), raising=True)
    monkeypatch.setattr(
        apping, "select_latest_for_platform", lambda ac, plat: _fake_release(),
        raising=True,
    )
    downloaded = tmp_path / "tampered.msi.download"
    downloaded.write_bytes(b"tampered")
    monkeypatch.setattr(
        apping, "_download_to_temp", lambda url: downloaded, raising=True
    )

    def _raise_mismatch(**k):
        raise update_errors.HashMismatchError("sha mismatch", log_fields={})

    monkeypatch.setattr(apping, "verify_artifact", _raise_mismatch, raising=True)

    seen = []
    # The closure must SWALLOW the verify exception (C-callback safety) and
    # return a clean block — NOT propagate.
    ok, version = apping._make_update_verifier_windows(on_verified=seen.append)()
    assert ok is False and version == "0.2.10"
    assert seen == []                        # no proof recorded on failure
    assert not downloaded.exists()           # temp cleaned even on failure


def test_macos_gate_cleans_temp_and_propagates_verify_exception(monkeypatch, tmp_path):
    """verify_artifact raises on a real mismatch; the gate must not swallow it
    (the bridge turns it into verify_fail) but MUST clean the temp file."""
    anchor = _valid_anchor()
    monkeypatch.setattr(
        apping,
        "_load_anchor_and_appcast",
        lambda platform: _loaded_anchor_tuple(anchor),
        raising=True,
    )
    downloaded = tmp_path / "mismatch.dmg.download"
    downloaded.write_bytes(b"bytes")
    monkeypatch.setattr(
        apping, "_download_to_temp", lambda url: downloaded, raising=True
    )

    def raising_verify(**kwargs):
        raise update_errors.HashMismatchError("sha mismatch", log_fields={})

    monkeypatch.setattr(apping, "verify_artifact", raising_verify, raising=True)

    gate = apping._make_update_verifier_macos()
    with pytest.raises(update_errors.HashMismatchError):
        gate("https://cdn.example.com/x.dmg", {"version": "1.2.3"})
    assert not downloaded.exists()
