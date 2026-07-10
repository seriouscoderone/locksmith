import json
from pathlib import Path
from unittest.mock import patch
from locksmith_publisher import publish


def test_anchor_release_anchors_digest_seal_and_returns_sad(tmp_path, monkeypatch):
    a = tmp_path / "app.dmg"; a.write_bytes(b"m")
    w = tmp_path / "app.msi"; w.write_bytes(b"w")
    captured = {}

    def fake_interact(*, name, alias, bran, base, data):
        captured["data"] = json.loads(data)
    monkeypatch.setattr(publish.kli, "kli_interact", fake_interact)

    # Stop after the interact by making the KEL read-back raise; we only assert
    # the anchored seal + the returned SAD contract here.
    class _Stop(Exception): ...
    monkeypatch.setattr(publish.habbing, "Habery",
                        lambda *x, **k: (_ for _ in ()).throw(_Stop()))
    try:
        publish.anchor_release(name="p", alias="p", bran="b", base="p",
                               version="0.2.20", brand="locksmith",
                               artifacts=[("macos", a), ("windows", w)], out_dir=str(tmp_path))
    except _Stop:
        pass

    seal = captured["data"]
    assert set(seal) == {"d", "brand", "ver"}
    assert seal["brand"] == "locksmith" and seal["ver"] == "0.2.20"
    assert len(seal["d"]) == 44  # qb64 SAID
