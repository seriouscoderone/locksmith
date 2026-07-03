"""Release seal — the publisher↔verifier contract anchored in the ixn ``a`` field.

Verifier (locksmith/update/verify.py + kel_replay.extract_release_seal) expects:
    {"release": {"v": <version>, "artifacts": [{"platform": <p>, "sha256": <hex>}, ...]}}
"""
import hashlib
from pathlib import Path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_release_seal(*, version: str, artifacts: list[tuple[str, Path]], brand: str) -> dict:
    """artifacts = [(platform, path), ...] in publish order."""
    return {"release": {"brand": brand, "v": version, "artifacts": [
        {"platform": plat, "sha256": _sha256(path)} for plat, path in artifacts
    ]}}
