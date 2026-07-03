import hashlib
from pathlib import Path
from locksmith_publisher.seal import build_release_seal


def test_build_release_seal_shape(tmp_path):
    mac = tmp_path / "Locksmith-macos.dmg"; mac.write_bytes(b"mac-bytes")
    win = tmp_path / "Locksmith-win.msi"; win.write_bytes(b"win-bytes")
    seal = build_release_seal(version="0.2.0", brand="usurance",
                              artifacts=[("macos", mac), ("windows", win)])
    assert seal == {"release": {"brand": "usurance", "v": "0.2.0", "artifacts": [
        {"platform": "macos", "sha256": hashlib.sha256(b"mac-bytes").hexdigest()},
        {"platform": "windows", "sha256": hashlib.sha256(b"win-bytes").hexdigest()},
    ]}}
