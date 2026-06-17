from locksmith_publisher import kli


def test_interact_argv_forces_receipt_endpoint(monkeypatch):
    captured = {}
    monkeypatch.setattr(kli, "_run", lambda argv, **kw: captured.setdefault("argv", argv) or "")
    kli.kli_interact(name="publisher", alias="publisher", bran="x" * 21,
                     base="/tmp/pub", data='{"release":{}}')
    argv = captured["argv"]
    assert argv[:2] == ["kli", "interact"]
    assert "--receipt-endpoint" in argv
    assert "--data" in argv and '{"release":{}}' in argv
    assert "--alias" in argv and "publisher" in argv


def test_incept_argv_has_wits_toad_and_receipt_endpoint(monkeypatch):
    captured = {}
    monkeypatch.setattr(kli, "_run", lambda argv, **kw: captured.setdefault("argv", argv) or "")
    kli.kli_incept(name="publisher", alias="publisher", bran="x" * 21, base="/tmp/pub",
                   wits=["BWit1", "BWit2", "BWit3"], toad=3)
    argv = captured["argv"]
    assert "--receipt-endpoint" in argv
    assert argv.count("--wits") == 3 and "BWit2" in argv
    assert "--toad" in argv and "3" in argv
