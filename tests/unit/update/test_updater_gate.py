"""Tests for the native-updater verify gate (``apping._make_update_verifier``).

The gate is the closure handed to Sparkle/WinSparkle as ``verifier=``. It must:

* ENFORCE when a real publisher anchor is resolvable — call ``verify_artifact``
  with the anchor-mapped params and return its ``.ok``.
* Stay DARK when no real anchor is injected (``_load_publisher_anchor`` raises
  ``FileNotFoundError``) — return ``True`` without calling ``verify_artifact``,
  so pre-cutover builds never block updates.

The closure signature matches the Sparkle/WinSparkle bridge contract:
``(staged: str, info: dict) -> bool`` (see ``sparkle_bridge``/``winsparkle_bridge``).
"""
from __future__ import annotations

import json
import types

import pytest

from locksmith.core import apping
from locksmith.update import cli as update_cli
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


def test_gate_enforces_when_anchor_present(monkeypatch, tmp_path):
    # Arrange a resolvable publisher anchor via the env-var path.
    anchor = _valid_anchor()
    anchor_file = tmp_path / "publisher_anchor.json"
    anchor_file.write_text(json.dumps(anchor))
    monkeypatch.setenv(update_cli.ANCHOR_ENV_VAR, str(anchor_file))

    # Avoid a live appcast fetch: stub the network read inside cli.
    monkeypatch.setattr(
        update_cli.urllib.request,
        "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no network")),
        raising=True,
    )
    # Make _load_anchor_and_appcast deterministic (anchor + canned appcast).
    captured = {}

    def fake_load_anchor_and_appcast(platform):
        captured["platform"] = platform
        return (
            "<appcast-raw>",
            anchor["publisher_aid"],
            anchor["embedded_kel_sn"],
            anchor["embedded_kel_hash"],
            anchor["toad"],
            platform,
        )

    monkeypatch.setattr(
        apping, "_load_anchor_and_appcast", fake_load_anchor_and_appcast, raising=True
    )

    # Spy verify_artifact: capture params, return an object with .ok.
    spy_calls = []

    def spy_verify_artifact(**kwargs):
        spy_calls.append(kwargs)
        return types.SimpleNamespace(ok=True)

    monkeypatch.setattr(apping, "verify_artifact", spy_verify_artifact, raising=True)

    gate = apping._make_update_verifier()

    info = {"version": "1.2.3", "anchor_said": "EReleaseSeal", "artifact_sha256": "ab"}
    result = gate("/tmp/staged/Locksmith.dmg", info)

    assert result is True
    assert len(spy_calls) == 1
    call = spy_calls[0]
    # Anchor-mapped params reach verify_artifact (embedded_kel_hash -> said).
    assert str(call["artifact_path"]) == "/tmp/staged/Locksmith.dmg"
    assert call["appcast_raw"] == "<appcast-raw>"
    assert call["embedded_publisher_aid"] == anchor["publisher_aid"]
    assert call["embedded_kel_sn"] == anchor["embedded_kel_sn"]
    assert call["embedded_kel_said"] == anchor["embedded_kel_hash"]
    assert call["toad"] == anchor["toad"]
    assert call["platform"] in ("macos", "windows")

    # And the closure returns verify_artifact(...).ok — flip it to prove.
    spy_calls.clear()

    def spy_verify_artifact_false(**kwargs):
        spy_calls.append(kwargs)
        return types.SimpleNamespace(ok=False)

    monkeypatch.setattr(
        apping, "verify_artifact", spy_verify_artifact_false, raising=True
    )
    gate2 = apping._make_update_verifier()
    assert gate2("/tmp/staged/Locksmith.dmg", info) is False
    assert len(spy_calls) == 1


def test_gate_dark_when_no_real_anchor(monkeypatch):
    # No injected anchor: _load_publisher_anchor raises FileNotFoundError, which
    # propagates out of _load_anchor_and_appcast.
    def raise_missing(platform):
        raise FileNotFoundError("no publisher_anchor.json found")

    monkeypatch.setattr(
        apping, "_load_anchor_and_appcast", raise_missing, raising=True
    )

    # verify_artifact must NOT be called in dark mode.
    def must_not_call(**kwargs):
        raise AssertionError("verify_artifact called in dark mode")

    monkeypatch.setattr(apping, "verify_artifact", must_not_call, raising=True)

    gate = apping._make_update_verifier()
    result = gate("/tmp/staged/Locksmith.dmg", {"version": "9.9.9"})

    # Dark: does NOT block updates.
    assert result is True


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
