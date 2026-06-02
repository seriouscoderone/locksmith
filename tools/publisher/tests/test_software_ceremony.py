"""Test the ceremony script with software-key backend end-to-end."""
import json
import os
import subprocess
import sys
from pathlib import Path

# The ceremony script is a standalone entry-point that imports locksmith_publisher.
# When run as a subprocess via sys.executable (not via the installed entry-point),
# the package's src/ directory must be on PYTHONPATH.
_PUBLISHER_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = str(_PUBLISHER_ROOT / "src")


def _make_env(**extra: str) -> dict[str, str]:
    """Build env dict with PYTHONPATH set so locksmith_publisher is importable."""
    base = os.environ.copy()
    existing = base.get("PYTHONPATH", "")
    base["PYTHONPATH"] = f"{_SRC_DIR}:{existing}" if existing else _SRC_DIR
    base.update(extra)
    return base


def test_ceremony_with_software_keys_emits_anchor(tmp_path: Path):
    """Software-key ceremony in dry-run mode produces all expected outputs."""
    script = _PUBLISHER_ROOT / "ceremony" / "incept.py"
    output_dir = tmp_path / "ceremony-output"
    keys_dir = tmp_path / "keys"

    env = _make_env(
        LOCKSMITH_PW_1="test-passphrase-one-12345",
        LOCKSMITH_PW_2="test-passphrase-two-12345",
        LOCKSMITH_PW_3="test-passphrase-three-12345",
    )

    result = subprocess.run(
        [
            sys.executable, str(script),
            "--dry-run",
            "--output-dir", str(output_dir),
            "--software-keys", str(keys_dir),
            "--passphrase-env-prefix", "LOCKSMITH_PW",
            "--non-interactive",
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"

    # Outputs exist
    assert (output_dir / "publisher_anchor.json").exists()
    assert (output_dir / "publisher-aid.json").exists()
    assert (output_dir / "kel-events" / "icp-sn-0.cesr").exists()

    # Software key files were created
    for i in (1, 2, 3):
        assert (keys_dir / f"key-{i}.enc.pem").exists()
        mode = (keys_dir / f"key-{i}.enc.pem").stat().st_mode & 0o777
        assert mode == 0o600

    # AID prefix is real (starts with E, not PLACEHOLDER)
    anchor = json.loads((output_dir / "publisher_anchor.json").read_text())
    assert anchor["publisher_aid"].startswith("E")
    assert "PLACEHOLDER" not in anchor["publisher_aid"]


def test_software_ceremony_reuses_existing_key_files(tmp_path: Path):
    """Re-running the ceremony with existing key files loads them rather than regenerating.

    Note: The AID prefix changes each run because the ceremony generates fresh
    pre-rotation next-key digests (random by design — KERI self-addressing
    identifiers bind the prefix to the full inception event content). The
    meaningful idempotency guarantee is at the key-file level: the encrypted PEM
    files are not replaced when they already exist.
    """
    script = _PUBLISHER_ROOT / "ceremony" / "incept.py"
    keys_dir = tmp_path / "keys"

    env = _make_env(
        LOCKSMITH_PW_1="test-passphrase-one-12345",
        LOCKSMITH_PW_2="test-passphrase-two-12345",
        LOCKSMITH_PW_3="test-passphrase-three-12345",
    )

    def run(output_subdir: str) -> None:
        output_dir = tmp_path / output_subdir
        result = subprocess.run(
            [
                sys.executable, str(script),
                "--dry-run",
                "--output-dir", str(output_dir),
                "--software-keys", str(keys_dir),
                "--passphrase-env-prefix", "LOCKSMITH_PW",
                "--non-interactive",
            ],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"

    # First run — creates the 3 key files.
    run("run-1")
    mtimes_after_first = {
        i: (keys_dir / f"key-{i}.enc.pem").stat().st_mtime
        for i in (1, 2, 3)
    }

    # Second run — should succeed using the existing key files without modifying them.
    run("run-2")
    mtimes_after_second = {
        i: (keys_dir / f"key-{i}.enc.pem").stat().st_mtime
        for i in (1, 2, 3)
    }

    assert mtimes_after_first == mtimes_after_second, (
        "Key files should not be modified on the second ceremony run — "
        "SoftwareKeyDevice.generate_signing_key() must load existing files, not regenerate."
    )
