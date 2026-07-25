"""Verify AppIcon.ico is committed and well-formed.

The .ico is produced by packaging/build-appicon.py and committed; CI does
not regenerate it. This test fails if the icon goes missing or the file
header is not a valid Windows ICONDIR.
"""
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
ICO = REPO_ROOT / "brands" / "locksmith" / "AppIcon.ico"


def test_appicon_ico_exists():
    assert ICO.is_file(), f"missing {ICO}"


def test_appicon_ico_header():
    # ICO files start with `00 00 01 00` (reserved + type=1).
    head = ICO.read_bytes()[:4]
    assert head == b"\x00\x00\x01\x00", f"not an ICO file: {head!r}"


def test_appicon_ico_contains_expected_sizes():
    with Image.open(ICO) as img:
        sizes = set(img.info.get("sizes", []))
    expected = {(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)}
    assert expected.issubset(sizes), (
        f"expected sizes {expected} not all present; got {sizes}"
    )


def test_appicon_ico_nontrivial_size():
    # A 6-frame .ico with PNG/BMP nesting should be at least 10KB.
    assert ICO.stat().st_size > 10_000, f"ICO suspiciously small: {ICO.stat().st_size} bytes"
