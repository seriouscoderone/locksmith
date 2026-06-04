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
    """Single-sig software-key ceremony in dry-run mode produces all expected outputs."""
    script = _PUBLISHER_ROOT / "ceremony" / "incept.py"
    output_dir = tmp_path / "ceremony-output"
    keys_dir = tmp_path / "keys"

    env = _make_env(
        LOCKSMITH_PW_1="test-passphrase-one-12345",
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

    # Software key files were created under new current/ and next/ subdirs
    assert (keys_dir / "current" / "key-1.enc.pem").exists(), "current key-1 missing"
    assert (keys_dir / "next" / "key-1.enc.pem").exists(), "next key-1 missing"
    for subdir in ("current", "next"):
        mode = (keys_dir / subdir / "key-1.enc.pem").stat().st_mode & 0o777
        assert mode == 0o600, f"{subdir}/key-1.enc.pem should be 0600, got {oct(mode)}"

    # AID prefix is real (starts with E, not PLACEHOLDER)
    anchor = json.loads((output_dir / "publisher_anchor.json").read_text())
    assert anchor["publisher_aid"].startswith("E")
    assert "PLACEHOLDER" not in anchor["publisher_aid"]


def test_software_ceremony_next_key_digest_verifiable(tmp_path: Path):
    """Rotation feasibility: the persisted next key produces the digest committed in n:.

    This is the critical correctness check: load next/key-1.enc.pem with the
    same passphrase, derive its Verfer, compute Diger(ser=verfer.qb64b), and
    compare against n:[0] in the inception event.  A mismatch means the AID
    can never be rotated.
    """
    script = _PUBLISHER_ROOT / "ceremony" / "incept.py"
    output_dir = tmp_path / "ceremony-output"
    keys_dir = tmp_path / "keys"
    passphrase_str = "test-passphrase-one-12345"

    env = _make_env(LOCKSMITH_PW_1=passphrase_str)

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

    # Read the committed digest from the inception event.
    icp_bytes = (output_dir / "kel-events" / "icp-sn-0.cesr").read_bytes()
    icp_body = json.loads(icp_bytes)
    committed_qb64 = icp_body["n"][0]

    # Load the next key and re-derive its digest.
    # We do this in a subprocess to keep test isolation, but also do it inline
    # so the assertion message is clear.
    sys.path.insert(0, _SRC_DIR)
    from keri.core import coring
    from locksmith_publisher.software_key import SoftwareKeyDevice

    next_device = SoftwareKeyDevice(
        serial="sw-1",
        slot="sw",
        key_path=keys_dir / "next" / "key-1.enc.pem",
        passphrase=passphrase_str.encode("utf-8"),
    )
    next_pubkey_raw = next_device.generate_signing_key()
    next_verfer = coring.Verfer(raw=next_pubkey_raw, code=coring.MtrDex.Ed25519)
    expected_qb64 = coring.Diger(ser=next_verfer.qb64b).qb64

    assert expected_qb64 == committed_qb64, (
        f"ROTATION FEASIBILITY FAILED.\n"
        f"  Committed digest in n:[0]: {committed_qb64!r}\n"
        f"  Blake2b-256(loaded next_verfer.qb64b): {expected_qb64!r}\n"
        "The inception event cannot be rotated with the stored next-key file."
    )


def test_software_ceremony_reuses_existing_key_files(tmp_path: Path):
    """Re-running the ceremony with existing key files loads them rather than regenerating.

    Both current/ and next/ key files must be stable across ceremony re-runs.
    The AID prefix will differ between runs (KERI self-addressing identifier
    binds the prefix to the full inception event), but the key material is
    preserved.
    """
    script = _PUBLISHER_ROOT / "ceremony" / "incept.py"
    keys_dir = tmp_path / "keys"

    env = _make_env(LOCKSMITH_PW_1="test-passphrase-one-12345")

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

    # First run — creates the key files under current/ and next/.
    run("run-1")
    mtimes_after_first = {
        f"{subdir}/key-1": (keys_dir / subdir / "key-1.enc.pem").stat().st_mtime
        for subdir in ("current", "next")
    }

    # Second run — should succeed loading existing files without modifying them.
    run("run-2")
    mtimes_after_second = {
        f"{subdir}/key-1": (keys_dir / subdir / "key-1.enc.pem").stat().st_mtime
        for subdir in ("current", "next")
    }

    assert mtimes_after_first == mtimes_after_second, (
        "Key files should not be modified on the second ceremony run — "
        "SoftwareKeyDevice.generate_signing_key() must load existing files, not regenerate."
    )
