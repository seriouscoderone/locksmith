"""Publisher trust-anchor loader: template + build-injection resolution.

Privacy rule (see project notes): no real publisher AID or witness domains are
committed. The repo ships ``publisher_anchor.example.json`` with ``example.com``
placeholders; the real anchor is build-injected via either the
``LOCKSMITH_PUBLISHER_ANCHOR`` env var or a gitignored
``src/locksmith/release/publisher_anchor.json``.

These tests target the real loader API in ``locksmith.update.cli``:
``_load_publisher_anchor()`` (the resolution-order helper) which
``_load_anchor_and_appcast`` delegates to.
"""
import json
from pathlib import Path

import pytest

from locksmith.update import cli

REQUIRED_KEYS = {
    "publisher_aid",
    "embedded_kel_hash",
    "embedded_kel_sn",
    "witness_oobis",
}

# Resolve the committed example relative to the repo, not the package, so the
# test is independent of how the package is installed.
EXAMPLE_PATH = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "locksmith"
    / "release"
    / "publisher_anchor.example.json"
)


def test_example_anchor_exists_and_is_committed():
    assert EXAMPLE_PATH.exists(), f"missing committed template: {EXAMPLE_PATH}"


def test_example_anchor_has_all_required_keys():
    body = json.loads(EXAMPLE_PATH.read_text())
    assert REQUIRED_KEYS.issubset(set(body.keys()))
    assert isinstance(body["publisher_aid"], str) and body["publisher_aid"]
    assert isinstance(body["embedded_kel_hash"], str) and body["embedded_kel_hash"]
    assert isinstance(body["embedded_kel_sn"], int)
    assert isinstance(body["witness_oobis"], list)
    assert len(body["witness_oobis"]) >= 3


def test_example_anchor_uses_only_placeholder_values():
    """No real domains or AIDs in the committed template."""
    body = json.loads(EXAMPLE_PATH.read_text())
    # Every witness OOBI must live under an example.com host. Asserted
    # positively so this test never names the real federation domains (which
    # would itself be a privacy leak in the committed repo).
    for oobi in body["witness_oobis"]:
        assert oobi.startswith("https://"), oobi
        assert "example.com" in oobi, f"non-placeholder host in OOBI: {oobi}"
    # The placeholder AID must be obviously a placeholder.
    assert "Placeholder" in body["publisher_aid"] or "Example" in body["publisher_aid"]


def test_loader_prefers_env_var_anchor(tmp_path, monkeypatch):
    """``$LOCKSMITH_PUBLISHER_ANCHOR`` (file) wins over everything else."""
    injected = tmp_path / "injected_anchor.json"
    injected.write_text(
        json.dumps(
            {
                "publisher_aid": "EEnvVarInjectedAidForTestOnly000000000000000",
                "embedded_kel_hash": "EEnvVarInjectedAidForTestOnly000000000000000",
                "embedded_kel_sn": 0,
                "witness_oobis": [
                    "https://witness.example.com/oobi/Benv1/witness",
                    "https://witness.example.com/oobi/Benv2/witness",
                    "https://witness.example.com/oobi/Benv3/witness",
                ],
            }
        )
    )
    monkeypatch.setenv("LOCKSMITH_PUBLISHER_ANCHOR", str(injected))

    anchor = cli._load_publisher_anchor()
    assert anchor["publisher_aid"] == "EEnvVarInjectedAidForTestOnly000000000000000"


def test_loader_falls_back_to_packaged_anchor(tmp_path, monkeypatch):
    """With no env var, the packaged ``publisher_anchor.json`` is used."""
    monkeypatch.delenv("LOCKSMITH_PUBLISHER_ANCHOR", raising=False)
    # Control the packaged path deterministically so this test does not depend on
    # whether a real (gitignored) publisher_anchor.json happens to be on disk in
    # this checkout. Use placeholder/example.com values (no real domains/AIDs).
    packaged = tmp_path / "publisher_anchor.json"
    packaged.write_text(
        json.dumps(
            {
                "publisher_aid": "EPackagedAnchorForTestOnly0000000000000000000",
                "embedded_kel_hash": "EPackagedAnchorForTestOnly0000000000000000000",
                "embedded_kel_sn": 0,
                "witness_oobis": [
                    "https://witness.example.com/oobi/Bpkg1/witness",
                    "https://witness.example.com/oobi/Bpkg2/witness",
                    "https://witness.example.com/oobi/Bpkg3/witness",
                ],
            }
        )
    )
    monkeypatch.setattr(cli, "_packaged_publisher_anchor_path", lambda: packaged)

    anchor = cli._load_publisher_anchor()
    assert REQUIRED_KEYS.issubset(set(anchor.keys()))
    assert anchor["publisher_aid"] == "EPackagedAnchorForTestOnly0000000000000000000"


def test_loader_raises_clear_error_when_nothing_resolvable(tmp_path, monkeypatch):
    """Env var points at a missing file AND no packaged anchor → clear error."""
    monkeypatch.setenv(
        "LOCKSMITH_PUBLISHER_ANCHOR", str(tmp_path / "does-not-exist.json")
    )

    # Force the packaged-resource fallback to miss too.
    def _missing_packaged() -> Path | None:
        return None

    monkeypatch.setattr(cli, "_packaged_publisher_anchor_path", _missing_packaged)

    with pytest.raises(FileNotFoundError) as exc:
        cli._load_publisher_anchor()
    assert "publisher_anchor" in str(exc.value).lower()


def test_load_anchor_and_appcast_delegates_to_loader(monkeypatch):
    """The appcast loader must read the anchor through ``_load_publisher_anchor``."""
    monkeypatch.setattr(
        cli,
        "_load_publisher_anchor",
        lambda: {
            "publisher_aid": "EDelegatedAidForTest00000000000000000000000",
            "embedded_kel_hash": "EDelegatedHashForTest0000000000000000000000",
            "embedded_kel_sn": 0,
            "witness_oobis": ["https://witness.example.com/oobi/B/witness"],
            "toad": 3,
        },
    )

    captured = {}

    def _fake_urlopen(url, timeout=0, context=None):
        captured["url"] = url
        captured["context"] = context

        class _Resp:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False

            def read(self_inner):
                return b'{"appcast": true}'

        return _Resp()

    monkeypatch.setattr(cli.urllib.request, "urlopen", _fake_urlopen)

    (appcast_raw, aid, sn, said, toad, platform) = cli._load_anchor_and_appcast(
        "macos"
    )
    assert aid == "EDelegatedAidForTest00000000000000000000000"
    assert said == "EDelegatedHashForTest0000000000000000000000"
    assert sn == 0
    assert toad == 3
    assert platform == "macos"
    assert appcast_raw == '{"appcast": true}'
