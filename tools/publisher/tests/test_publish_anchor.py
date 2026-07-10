import json
from pathlib import Path
from locksmith_publisher import publish
from locksmith_publisher.seal import build_release_sad


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


def test_anchor_release_returns_release_sad(tmp_path, monkeypatch):
    """anchor_release must return a dict containing release_sad equal to
    build_release_sad() for the same inputs, with per-platform sha256s."""
    version = "0.2.20"
    brand = "locksmith"
    a = tmp_path / "app.dmg"; a.write_bytes(b"mac-payload")
    w = tmp_path / "app.msi"; w.write_bytes(b"win-payload")
    artifacts = [("macos", a), ("windows", w)]

    monkeypatch.setattr(publish.kli, "kli_interact",
                        lambda *, name, alias, bran, base, data: None)

    # Build the expected SAD from the real function so the test is tied to the
    # same contract the production code uses.
    expected_sad = build_release_sad(version=version, artifacts=artifacts, brand=brand)

    # --- Fake hab ----------------------------------------------------------------
    fake_pre = "B" + "A" * 43  # 44-char qb64 prefix
    fake_said = "E" + "A" * 43

    class _FakeKever:
        class toader:
            num = 0  # toad=0 → receipt wait satisfied immediately
        sn = 1
        class serder:
            said = fake_said

    class _FakeHab:
        pre = fake_pre
        kever = _FakeKever()

    # --- Fake anchor from export_kel ------------------------------------------
    # Patch export_kel (the genusified CESR exporter) to return a minimal but
    # structurally correct (kel_bytes, anchor) pair.  The real CESR encoding is
    # tested by test_publish_export.py; here we only assert anchor_release's
    # SAD-return contract.
    fake_kel = b"fake-kel-bytes"
    fake_anchor = dict(said=fake_said, sn=1, bytes=b"fake-anchor-event")

    monkeypatch.setattr(publish, "export_kel",
                        lambda hby, hab, *, version, brand: (fake_kel, fake_anchor))

    # --- Fake hby ----------------------------------------------------------------
    class _FakeKever2:
        class toader:
            num = 0  # toad=0 → receipt wait satisfied immediately
        sn = 1
        class serder:
            said = fake_said

    class _FakeHby:
        class db:
            class wigs:
                @staticmethod
                def get(*, keys):
                    return []  # toad=0, empty wigs is fine

        def habByName(self, alias):
            class _Hab:
                pre = fake_pre
                kever = _FakeKever2()
            return _Hab()

        def close(self):
            pass

    monkeypatch.setattr(publish.habbing, "Habery", lambda **kw: _FakeHby())

    result = publish.anchor_release(
        name="p", alias="p", bran="b", base="p",
        version=version, brand=brand,
        artifacts=artifacts, out_dir=str(tmp_path),
    )

    # Core contract: release_sad is present and matches build_release_sad output.
    assert "release_sad" in result, "anchor_release must return release_sad"
    assert result["release_sad"] == expected_sad
    assert result["release_sad"]["brand"] == brand
    assert result["release_sad"]["ver"] == version

    # Per-platform sha256s are present and non-empty in the SAD.
    art = result["release_sad"]["artifacts"]
    platforms = {e["platform"] for e in art}
    assert platforms == {"macos", "windows"}
    for entry in art:
        assert len(entry["sha256"]) == 64, "sha256 must be a 64-char hex digest"

    # Other keys expected in the return dict.
    assert "anchor_said" in result
    assert "anchor_sn" in result
    assert "kel_path" in result
    assert "anchor_event_path" in result
