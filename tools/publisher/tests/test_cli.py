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
