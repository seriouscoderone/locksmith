"""Release seal — the publisher↔verifier contract anchored in the ixn ``a`` field.

SAID-native: the ixn anchors a digest seal ``{"d": <said>, "brand": <b>, "ver": <v>}``.
``d`` is the SAID of the release SAD ``{"d","brand","ver","artifacts":[{platform,sha256}]}``,
which the publisher also publishes in the JSON appcast. Verifier (locksmith/update)
reads brand/ver from the KEL seal (freeze-defense) and resolves+verifies the SAD.
Never use the reserved ``v`` field — it collides with the KERI version string.
"""
import hashlib
from pathlib import Path

from keri.core.coring import Saider


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_release_sad(*, version: str, artifacts: list[tuple[str, Path]], brand: str) -> dict:
    """The saidified release SAD. artifacts = [(platform, path), ...] in publish order."""
    sad = {
        "d": "",
        "brand": brand,
        "ver": version,
        "artifacts": [{"platform": plat, "sha256": _sha256(path)} for plat, path in artifacts],
    }
    _, sad = Saider.saidify(sad=sad)
    return sad


def build_release_seal(*, version: str, artifacts: list[tuple[str, Path]], brand: str) -> dict:
    """The KEL digest seal anchored in the ixn ``a`` field."""
    sad = build_release_sad(version=version, artifacts=artifacts, brand=brand)
    return {"d": sad["d"], "brand": brand, "ver": version}
