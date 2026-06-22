from locksmith_publisher import kli


def test_kli_init_argv(monkeypatch):
    seen = {}
    monkeypatch.setattr(kli, "_run", lambda argv, **k: seen.setdefault("argv", argv) or "")
    kli.kli_init(name="pub", base="/ks", bran="BRANBRANBRANBRANBRAN0")
    assert seen["argv"] == [
        kli.KLI, "init", "--name", "pub", "--base", "/ks",
        "--passcode", "BRANBRANBRANBRANBRAN0",
    ]


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
