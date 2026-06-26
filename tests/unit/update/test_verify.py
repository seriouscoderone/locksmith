"""Tests for ``locksmith.update.verify.verify_artifact()``."""
import json
import ssl
from pathlib import Path
from unittest.mock import patch

import pytest

from locksmith.update import verify as verify_mod
from locksmith.update.errors import (
    DowngradeError,
    HashMismatchError,
    NetworkError,
    SignatureError,
    StaleAppcastError,
    WitnessThresholdError,
)
from locksmith.update.verify import VerificationResult, verify_artifact

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "update"


def _macos_appcast() -> str:
    return (FIXTURES / "appcast" / "macos.json").read_text()


def _kel_stream() -> bytes:
    return (FIXTURES / "kel" / "publisher.cesr").read_bytes()


def _manifest() -> dict:
    return json.loads((FIXTURES / "publisher_aid.json").read_text())


@pytest.fixture
def patched_fetch(monkeypatch):
    """Patch ``verify._fetch_url`` to return canned bytes by URL substring."""
    def _setup(*, kel: bytes | None = None, anchor: bytes | None = None):
        def fake_fetch(url: str) -> bytes:
            if "publisher" in url or "kel" in url:
                return kel if kel is not None else b""
            return anchor if anchor is not None else b""
        monkeypatch.setattr(verify_mod, "_fetch_url", fake_fetch)
    return _setup


def test_verify_happy_path_macos_110(patched_fetch):
    manifest = _manifest()
    rel_110 = next(r for r in manifest["_releases"] if r["version"] == "1.1.0")
    anchor_event = (FIXTURES / "anchor" / "1.1.0.cesr").read_bytes()
    patched_fetch(kel=_kel_stream(), anchor=anchor_event)
    artifact = FIXTURES / "artifacts" / "Locksmith-1.1.0.dmg.stub"

    result = verify_artifact(
        artifact_path=artifact,
        appcast_raw=_macos_appcast(),
        platform="macos",
        embedded_publisher_aid=manifest["publisher_aid"],
        embedded_kel_sn=0,
        embedded_kel_said=None,
        toad=manifest["toad"],
    )
    assert isinstance(result, VerificationResult)
    assert result.ok is True
    assert result.version == "1.1.0"
    assert result.publisher_aid == manifest["publisher_aid"]
    assert result.anchor_said == rel_110["said"]
    assert result.witness_receipts >= manifest["toad"]


def test_verify_tampered_binary_raises_hash_mismatch(patched_fetch):
    """When attacker swaps the binary but leaves the appcast pointing at the
    current (1.1.0) release, the hash check on the artifact catches it."""
    manifest = _manifest()
    rel_110 = next(r for r in manifest["_releases"] if r["version"] == "1.1.0")
    anchor_event = (FIXTURES / "anchor" / "1.1.0.cesr").read_bytes()
    patched_fetch(kel=_kel_stream(), anchor=anchor_event)

    # Tampered binary masqueraded as 1.1.0 (the current version).
    tampered = FIXTURES / "tampered" / "tampered_binary_1.0.1.dmg.stub"

    with pytest.raises(HashMismatchError) as e:
        verify_artifact(
            artifact_path=tampered,
            appcast_raw=_macos_appcast(),
            platform="macos",
            embedded_publisher_aid=manifest["publisher_aid"],
            embedded_kel_sn=0,
            embedded_kel_said=None,
            toad=manifest["toad"],
        )
    assert "expected_sha256" in e.value.log_fields
    assert "actual_sha256" in e.value.log_fields


def test_verify_wrong_publisher_aid_raises_signature(patched_fetch):
    manifest = _manifest()
    anchor = (FIXTURES / "anchor" / "1.1.0.cesr").read_bytes()
    patched_fetch(kel=_kel_stream(), anchor=anchor)
    with pytest.raises(SignatureError):
        verify_artifact(
            artifact_path=FIXTURES / "artifacts" / "Locksmith-1.1.0.dmg.stub",
            appcast_raw=_macos_appcast(),
            platform="macos",
            embedded_publisher_aid="EWRONG_AID_PREFIX____________________________",
            embedded_kel_sn=0,
            embedded_kel_said=None,
            toad=manifest["toad"],
        )


def test_verify_stale_appcast_raises(patched_fetch):
    """Appcast lists only 1.0.0 with stale current_version, but KEL is at 1.1.0."""
    manifest = _manifest()
    stale = (FIXTURES / "tampered" / "stale_appcast_macos.json").read_text()
    anchor_100 = (FIXTURES / "anchor" / "1.0.0.cesr").read_bytes()
    patched_fetch(kel=_kel_stream(), anchor=anchor_100)
    with pytest.raises(StaleAppcastError):
        verify_artifact(
            artifact_path=FIXTURES / "artifacts" / "Locksmith-1.0.0.dmg.stub",
            appcast_raw=stale,
            platform="macos",
            embedded_publisher_aid=manifest["publisher_aid"],
            embedded_kel_sn=0,
            embedded_kel_said=None,
            toad=manifest["toad"],
        )


def test_verify_downgrade_appcast_raises(patched_fetch):
    """Downgrade appcast claims 1.0.0 has 1.1.0's sha256."""
    manifest = _manifest()
    downgrade = (FIXTURES / "tampered" / "downgrade_appcast_macos.json").read_text()
    # Need to also bump current_version so we pick the 1.0.0 (downgrade) release.
    dg = json.loads(downgrade)
    dg["current_version"] = "1.0.0"
    dg["releases"] = [r for r in dg["releases"] if r["version"] == "1.0.0"]
    anchor_100 = (FIXTURES / "anchor" / "1.0.0.cesr").read_bytes()
    patched_fetch(kel=_kel_stream(), anchor=anchor_100)
    with pytest.raises((DowngradeError, StaleAppcastError, HashMismatchError)):
        verify_artifact(
            artifact_path=FIXTURES / "artifacts" / "Locksmith-1.0.0.dmg.stub",
            appcast_raw=json.dumps(dg),
            platform="macos",
            embedded_publisher_aid=manifest["publisher_aid"],
            embedded_kel_sn=0,
            embedded_kel_said=None,
            toad=manifest["toad"],
        )


def test_verify_insufficient_receipts_raises(patched_fetch):
    """Force toad above what fixtures provide; replay raises WitnessThresholdError."""
    manifest = _manifest()
    anchor = (FIXTURES / "anchor" / "1.1.0.cesr").read_bytes()
    patched_fetch(kel=_kel_stream(), anchor=anchor)
    with pytest.raises(WitnessThresholdError):
        verify_artifact(
            artifact_path=FIXTURES / "artifacts" / "Locksmith-1.1.0.dmg.stub",
            appcast_raw=_macos_appcast(),
            platform="macos",
            embedded_publisher_aid=manifest["publisher_aid"],
            embedded_kel_sn=0,
            embedded_kel_said=None,
            toad=manifest["toad"] + 1,  # one more than we have
        )


def test_verify_network_failure_raises():
    manifest = _manifest()
    with patch.object(
        verify_mod,
        "_fetch_url",
        side_effect=NetworkError("connection refused", log_fields={"url": "x"}),
    ):
        with pytest.raises(NetworkError):
            verify_artifact(
                artifact_path=FIXTURES / "artifacts" / "Locksmith-1.1.0.dmg.stub",
                appcast_raw=_macos_appcast(),
                platform="macos",
                embedded_publisher_aid=manifest["publisher_aid"],
                embedded_kel_sn=0,
                embedded_kel_said=None,
                toad=manifest["toad"],
            )


def test_ssl_context_returns_context_backed_by_certifi():
    """A frozen app's OpenSSL default CA path points at the build machine, so
    the verify path must trust certifi's bundled CA explicitly."""
    ctx = verify_mod.ssl_context()
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode == ssl.CERT_REQUIRED  # TLS verification stays ON


def test_fetch_url_passes_certifi_ssl_context():
    """``_fetch_url`` must hand urlopen the certifi-backed context — otherwise a
    Finder-launched signed build raises CERTIFICATE_VERIFY_FAILED on every fetch."""
    captured = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"ok"

    def fake_urlopen(url, timeout=None, context=None):
        captured["context"] = context
        return _Resp()

    with patch.object(verify_mod.urllib.request, "urlopen", fake_urlopen):
        assert verify_mod._fetch_url("https://example.com/x") == b"ok"
    assert isinstance(captured["context"], ssl.SSLContext)


def test_verification_result_carries_diagnostic_fields(patched_fetch):
    manifest = _manifest()
    rel = next(r for r in manifest["_releases"] if r["version"] == "1.1.0")
    anchor = (FIXTURES / "anchor" / "1.1.0.cesr").read_bytes()
    patched_fetch(kel=_kel_stream(), anchor=anchor)
    result = verify_artifact(
        artifact_path=FIXTURES / "artifacts" / "Locksmith-1.1.0.dmg.stub",
        appcast_raw=_macos_appcast(),
        platform="macos",
        embedded_publisher_aid=manifest["publisher_aid"],
        embedded_kel_sn=0,
        embedded_kel_said=None,
        toad=manifest["toad"],
    )
    assert result.anchor_said == rel["said"]
    assert result.artifact_sha256
    assert result.artifact_size > 0
    assert result.witness_receipts >= manifest["toad"]
    assert result.kel_tip_sn == manifest["kel_tip_sn"]


def test_verify_anchor_url_mismatched_said_raises(patched_fetch):
    """Anchor URL serves a different event than appcast claims."""
    manifest = _manifest()
    wrong_anchor = (FIXTURES / "anchor" / "1.0.0.cesr").read_bytes()
    # KEL is happy-path; appcast says current=1.1.0; serve 1.0.0's anchor instead.
    patched_fetch(kel=_kel_stream(), anchor=wrong_anchor)
    with pytest.raises(SignatureError):
        verify_artifact(
            artifact_path=FIXTURES / "artifacts" / "Locksmith-1.1.0.dmg.stub",
            appcast_raw=_macos_appcast(),
            platform="macos",
            embedded_publisher_aid=manifest["publisher_aid"],
            embedded_kel_sn=0,
            embedded_kel_said=None,
            toad=manifest["toad"],
        )
