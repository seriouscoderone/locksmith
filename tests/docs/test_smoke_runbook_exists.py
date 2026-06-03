"""Smoke-test runbook must exist and cover the required checks."""
from pathlib import Path

RUNBOOK = (
    Path(__file__).resolve().parents[2]
    / "docs" / "development" / "macos-build-smoke-test.md"
)

EXPECTED_PHRASES = [
    "clean macOS",
    "Gatekeeper",
    "spctl --assess",
    "stapler validate",
    "Locksmith.app",
    "drag",
    "/Applications",
    "open -a Locksmith",
    "host.keri.locksmith",
    "Activity Monitor",
]


def test_runbook_exists():
    assert RUNBOOK.is_file(), f"missing: {RUNBOOK}"


def test_runbook_covers_key_checks():
    text = RUNBOOK.read_text()
    missing = [p for p in EXPECTED_PHRASES if p not in text]
    assert not missing, f"runbook missing: {missing}"
