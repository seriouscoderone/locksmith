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
