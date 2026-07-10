from pathlib import Path
from keri.core.coring import Saider
from locksmith_publisher.seal import build_release_sad, build_release_seal


def _tmpfile(tmp_path, name, content):
    p = tmp_path / name
    p.write_bytes(content)
    return p


def test_build_release_sad_is_saidified_with_ver_and_artifacts(tmp_path):
    a = _tmpfile(tmp_path, "app.dmg", b"macos-bytes")
    sad = build_release_sad(version="0.2.20", brand="locksmith",
                            artifacts=[("macos", a)])
    # self-addressing: re-saidify reproduces d, and there is NO reserved 'v'
    assert "v" not in sad
    assert sad["brand"] == "locksmith" and sad["ver"] == "0.2.20"
    assert sad["artifacts"][0]["platform"] == "macos"
    assert len(sad["artifacts"][0]["sha256"]) == 64
    _, recomputed = Saider.saidify(sad=dict(sad))
    assert recomputed["d"] == sad["d"]


def test_build_release_seal_is_digest_seal_with_brand_ver(tmp_path):
    a = _tmpfile(tmp_path, "app.dmg", b"macos-bytes")
    seal = build_release_seal(version="0.2.20", brand="locksmith",
                              artifacts=[("macos", a)])
    sad = build_release_sad(version="0.2.20", brand="locksmith",
                            artifacts=[("macos", a)])
    assert seal == {"d": sad["d"], "brand": "locksmith", "ver": "0.2.20"}
