import pytest
from keri.core.coring import Saider
from locksmith.update.verify import _verify_sad_against_anchor  # new helper (Task 6)
from locksmith.update.errors import SignatureError


def _sad():
    _, sad = Saider.saidify(sad={"d": "", "brand": "locksmith", "ver": "0.2.20",
                                 "artifacts": [{"platform": "macos", "sha256": "a"*64}]})
    return sad


def test_verify_sad_matches_anchor_returns_artifact_sha():
    sad = _sad()
    sha = _verify_sad_against_anchor(sad, anchor_d=sad["d"], platform="macos")
    assert sha == "a"*64


def test_verify_sad_rejects_tampered_sad():
    sad = _sad()
    tampered = dict(sad)
    tampered["artifacts"] = [{"platform": "macos", "sha256": "b"*64}]  # d no longer matches
    with pytest.raises(SignatureError):
        _verify_sad_against_anchor(tampered, anchor_d=sad["d"], platform="macos")


def test_verify_sad_rejects_anchor_mismatch():
    sad = _sad()
    with pytest.raises(SignatureError):
        _verify_sad_against_anchor(sad, anchor_d="E" + "Z"*43, platform="macos")
