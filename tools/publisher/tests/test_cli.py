import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from locksmith_publisher import cli as cli_mod
from locksmith_publisher.witnesses import WitnessInfo


@pytest.fixture
def fake_pool(monkeypatch):
    pool = [WitnessInfo(aid=f"Bwit{i}", oobi=f"https://w{i}.example.com/oobi/Bwit{i}/witness")
            for i in range(5)]
    monkeypatch.setattr(cli_mod, "default_witness_pool", lambda: pool)
    return pool


def test_incept_sequences_kli(monkeypatch, fake_pool):
    calls = []
    monkeypatch.setattr(cli_mod.kli, "kli_init", lambda **k: calls.append(("init", k)) or "")
    monkeypatch.setattr(cli_mod.kli, "kli_resolve_oobi", lambda **k: calls.append(("oobi", k["oobi"])) or "")
    monkeypatch.setattr(cli_mod.kli, "kli_incept",
                        lambda **k: calls.append(("incept", k)) or "Prefix  EpubAID\n")
    monkeypatch.setenv("LOCKSMITH_PUBLISHER_BRAN", "BRAN0000000000000000")
    r = CliRunner().invoke(cli_mod.cli, ["incept", "--name", "pub", "--base", "/ks"])
    assert r.exit_code == 0, r.output
    assert calls[0][0] == "init"
    assert [c[1] for c in calls if c[0] == "oobi"] == [w.oobi for w in fake_pool]
    incept_call = next(c for c in calls if c[0] == "incept")
    assert incept_call[1]["wits"] == [w.aid for w in fake_pool]
    assert incept_call[1]["toad"] == 3
    # Env bran must propagate all the way into the kli_incept kwargs.
    assert incept_call[1]["bran"] == "BRAN0000000000000000"
    # Also confirm kli_init received the same bran.
    init_call = next(c for c in calls if c[0] == "init")
    assert init_call[1]["bran"] == "BRAN0000000000000000"


def test_incept_passes_salt_from_env(monkeypatch, fake_pool):
    """When LOCKSMITH_PUBLISHER_SALT is set, incept passes salt= to kli_init."""
    calls = []
    monkeypatch.setattr(cli_mod.kli, "kli_init", lambda **k: calls.append(("init", k)) or "")
    monkeypatch.setattr(cli_mod.kli, "kli_resolve_oobi", lambda **k: None)
    monkeypatch.setattr(cli_mod.kli, "kli_incept", lambda **k: "Prefix  EpubAID\n")
    monkeypatch.setenv("LOCKSMITH_PUBLISHER_BRAN", "BRAN0000000000000000")
    monkeypatch.setenv("LOCKSMITH_PUBLISHER_SALT", "0ABdeterministicSalt000000000000")
    r = CliRunner().invoke(cli_mod.cli, ["incept", "--name", "pub", "--base", "/ks"])
    assert r.exit_code == 0, r.output
    init_call = next(c for c in calls if c[0] == "init")
    assert init_call[1]["salt"] == "0ABdeterministicSalt000000000000"


def test_incept_no_salt_env_passes_none(monkeypatch, fake_pool):
    """When salt env var is not set, incept passes salt=None to kli_init."""
    calls = []
    monkeypatch.setattr(cli_mod.kli, "kli_init", lambda **k: calls.append(("init", k)) or "")
    monkeypatch.setattr(cli_mod.kli, "kli_resolve_oobi", lambda **k: None)
    monkeypatch.setattr(cli_mod.kli, "kli_incept", lambda **k: "Prefix  EpubAID\n")
    monkeypatch.setenv("LOCKSMITH_PUBLISHER_BRAN", "BRAN0000000000000000")
    monkeypatch.delenv("LOCKSMITH_PUBLISHER_SALT", raising=False)
    r = CliRunner().invoke(cli_mod.cli, ["incept", "--name", "pub", "--base", "/ks"])
    assert r.exit_code == 0, r.output
    init_call = next(c for c in calls if c[0] == "init")
    assert init_call[1]["salt"] is None


def test_incept_empty_salt_env_passes_none(monkeypatch, fake_pool):
    """When salt env var is set but empty, incept passes salt=None to kli_init."""
    calls = []
    monkeypatch.setattr(cli_mod.kli, "kli_init", lambda **k: calls.append(("init", k)) or "")
    monkeypatch.setattr(cli_mod.kli, "kli_resolve_oobi", lambda **k: None)
    monkeypatch.setattr(cli_mod.kli, "kli_incept", lambda **k: "Prefix  EpubAID\n")
    monkeypatch.setenv("LOCKSMITH_PUBLISHER_BRAN", "BRAN0000000000000000")
    monkeypatch.setenv("LOCKSMITH_PUBLISHER_SALT", "")
    r = CliRunner().invoke(cli_mod.cli, ["incept", "--name", "pub", "--base", "/ks"])
    assert r.exit_code == 0, r.output
    init_call = next(c for c in calls if c[0] == "init")
    assert init_call[1]["salt"] is None


def test_incept_custom_salt_env_var(monkeypatch, fake_pool):
    """--salt-env lets the operator use a custom env var name."""
    calls = []
    monkeypatch.setattr(cli_mod.kli, "kli_init", lambda **k: calls.append(("init", k)) or "")
    monkeypatch.setattr(cli_mod.kli, "kli_resolve_oobi", lambda **k: None)
    monkeypatch.setattr(cli_mod.kli, "kli_incept", lambda **k: "Prefix  EpubAID\n")
    monkeypatch.setenv("LOCKSMITH_PUBLISHER_BRAN", "BRAN0000000000000000")
    monkeypatch.setenv("MY_CUSTOM_SALT_VAR", "0ABcustomSalt0000000000000000000")
    monkeypatch.delenv("LOCKSMITH_PUBLISHER_SALT", raising=False)
    r = CliRunner().invoke(cli_mod.cli, [
        "incept", "--name", "pub", "--base", "/ks", "--salt-env", "MY_CUSTOM_SALT_VAR"])
    assert r.exit_code == 0, r.output
    init_call = next(c for c in calls if c[0] == "init")
    assert init_call[1]["salt"] == "0ABcustomSalt0000000000000000000"


def test_incept_requires_bran_env(monkeypatch, fake_pool):
    monkeypatch.delenv("LOCKSMITH_PUBLISHER_BRAN", raising=False)
    r = CliRunner().invoke(cli_mod.cli, ["incept", "--name", "pub", "--base", "/ks"])
    assert r.exit_code != 0
    assert "LOCKSMITH_PUBLISHER_BRAN" in r.output


def test_gen_anchor_writes_doc(monkeypatch, tmp_path, fake_pool):
    out = tmp_path / "publisher_anchor.json"
    monkeypatch.setattr(cli_mod, "_publisher_anchor_path", lambda: out)
    monkeypatch.setattr(cli_mod, "_read_publisher_aid",
                        lambda **k: "EpubAID000000000000000000000000000000000000")
    monkeypatch.setenv("LOCKSMITH_PUBLISHER_BRAN", "BRAN0000000000000000")
    r = CliRunner().invoke(cli_mod.cli, ["gen-anchor", "--name", "pub", "--base", "/ks"])
    assert r.exit_code == 0, r.output
    doc = json.loads(out.read_text())
    assert doc["publisher_aid"] == "EpubAID000000000000000000000000000000000000"
    assert doc["embedded_kel_hash"] == doc["publisher_aid"]
    assert doc["embedded_kel_sn"] == 0 and doc["toad"] == 3
    assert doc["witness_oobis"] == [w.oobi for w in fake_pool]
    # refuses overwrite without --force
    r2 = CliRunner().invoke(cli_mod.cli, ["gen-anchor", "--name", "pub", "--base", "/ks"])
    assert r2.exit_code != 0 and "exists" in r2.output.lower()


def test_cli_help_lists_appcast():
    r = CliRunner().invoke(cli_mod.cli, ["--help"])
    assert r.exit_code == 0
    assert "appcast" in r.output


def test_cli_version_flag():
    r = CliRunner().invoke(cli_mod.cli, ["--version"])
    assert r.exit_code == 0
    assert "0.1.0" in r.output


def test_anchor_invokes_anchor_release(monkeypatch, tmp_path):
    mac = tmp_path / "Locksmith-0.1.7.dmg"; mac.write_bytes(b"dmg")
    win = tmp_path / "Locksmith-0.1.7.msi"; win.write_bytes(b"msi")
    seen = {}
    monkeypatch.setattr(cli_mod.publish, "anchor_release",
                        lambda **k: seen.update(k) or {
                            "anchor_said": "Eanchor", "anchor_sn": 1,
                            "kel_path": str(tmp_path / "kel.cesr"),
                            "anchor_event_path": str(tmp_path / "Eanchor.cesr")})
    monkeypatch.setenv("LOCKSMITH_PUBLISHER_BRAN", "BRAN0000000000000000")
    r = CliRunner().invoke(cli_mod.cli, [
        "anchor", "--name", "pub", "--base", "/ks", "--version", "0.1.7",
        "--macos", str(mac), "--windows", str(win), "--out-dir", str(tmp_path)])
    assert r.exit_code == 0, r.output
    assert seen["version"] == "0.1.7"
    assert [p for p, _ in seen["artifacts"]] == ["macos", "windows"]
    # Env bran must propagate into anchor_release kwargs.
    assert seen["bran"] == "BRAN0000000000000000"


def test_publish_uploads_kel_anchor_and_two_appcasts(monkeypatch, tmp_path):
    (tmp_path / "EpubAID-kel.cesr").write_bytes(b"KEL")
    (tmp_path / "Eanchor.cesr").write_bytes(b"ANCHOR")
    monkeypatch.setattr(cli_mod, "load_deploy_config", lambda: {
        "s3_bucket": "releases.example.com",
        "releases_cdn_base": "https://releases.example.com",
        "publisher_kel_url": "https://releases.example.com/publisher/v1/kel.cesr",
    })
    monkeypatch.setattr(cli_mod, "_read_publisher_aid", lambda **k: "EpubAID")
    uploads = {"release": None, "puts": []}
    class FakeS3:
        def upload_release(self, **k): uploads["release"] = k
        def put_object(self, **k): uploads["puts"].append(k)
    monkeypatch.setattr(cli_mod.S3, "default", classmethod(lambda cls: FakeS3()))
    monkeypatch.setenv("LOCKSMITH_PUBLISHER_BRAN", "BRAN0000000000000000")
    r = CliRunner().invoke(cli_mod.cli, [
        "publish", "--name", "pub", "--base", "/ks", "--version", "0.1.7",
        "--anchor-said", "Eanchor",
        "--macos-sha256", "a"*64, "--windows-sha256", "b"*64,
        "--out-dir", str(tmp_path)])
    assert r.exit_code == 0, r.output
    rel = uploads["release"]
    assert rel["bucket"] == "releases.example.com"
    assert rel["kel"] == b"KEL"
    assert rel["anchors"] == {"Eanchor": b"ANCHOR"}
    assert rel["appcast_key"] == "appcast/v1/macos.json"
    # windows appcast uploaded separately
    assert any(p["key"] == "appcast/v1/windows.json" for p in uploads["puts"])
