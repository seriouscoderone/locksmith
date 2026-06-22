from locksmith_publisher import kli


def test_kli_init_argv(monkeypatch):
    seen = {}
    monkeypatch.setattr(kli, "_run", lambda argv, **k: seen.setdefault("argv", argv) or "")
    kli.kli_init(name="pub", base="/ks", bran="BRANBRANBRANBRANBRAN0")
    assert seen["argv"] == [
        kli.KLI, "init", "--name", "pub", "--base", "/ks",
        "--passcode", "BRANBRANBRANBRANBRAN0",
    ]


def test_kli_init_with_salt_appends_salt_arg(monkeypatch):
    seen = {}
    monkeypatch.setattr(kli, "_run", lambda argv, **k: seen.setdefault("argv", argv) or "")
    kli.kli_init(name="pub", base="/ks", bran="BRANBRANBRANBRANBRAN0", salt="0ABsomeDeterministicSalt")
    argv = seen["argv"]
    assert "--salt" in argv
    idx = argv.index("--salt")
    assert argv[idx + 1] == "0ABsomeDeterministicSalt"


def test_kli_init_without_salt_omits_salt_arg(monkeypatch):
    seen = {}
    monkeypatch.setattr(kli, "_run", lambda argv, **k: seen.setdefault("argv", argv) or "")
    kli.kli_init(name="pub", base="/ks", bran="BRANBRANBRANBRANBRAN0")
    assert "--salt" not in seen["argv"]


def test_kli_init_none_salt_omits_salt_arg(monkeypatch):
    seen = {}
    monkeypatch.setattr(kli, "_run", lambda argv, **k: seen.setdefault("argv", argv) or "")
    kli.kli_init(name="pub", base="/ks", bran="BRANBRANBRANBRANBRAN0", salt=None)
    assert "--salt" not in seen["argv"]


def test_run_redacts_secrets_in_error_message(monkeypatch):
    """_run must not leak --passcode or --salt values in the RuntimeError message."""
    import subprocess

    class FakeProc:
        returncode = 1
        stderr = "boom"
        stdout = ""

    monkeypatch.setattr(kli.subprocess, "run", lambda *a, **k: FakeProc())
    import pytest
    with pytest.raises(RuntimeError) as exc_info:
        kli._run(
            [kli.KLI, "init", "--passcode", "SECRETBRANVALUE", "--salt", "SECRETSALTVALUE"]
        )
    msg = str(exc_info.value)
    assert "SECRETBRANVALUE" not in msg
    assert "SECRETSALTVALUE" not in msg
    assert "***" in msg
    assert "init" in msg  # non-secret tokens still present


def test_kli_resolve_oobi_argv(monkeypatch):
    seen = {}
    monkeypatch.setattr(kli, "_run", lambda argv, **k: seen.setdefault("argv", argv) or "")
    kli.kli_resolve_oobi(name="pub", base="/ks", bran="BRAN",
                         oobi="https://witness.example.com/oobi/BAID/witness")
    assert seen["argv"] == [
        kli.KLI, "oobi", "resolve", "--name", "pub", "--base", "/ks",
        "--passcode", "BRAN",
        "--oobi", "https://witness.example.com/oobi/BAID/witness",
    ]
