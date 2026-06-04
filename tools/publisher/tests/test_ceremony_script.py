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


def test_ceremony_script_dry_run_emits_files(tmp_path: Path):
    script = _PUBLISHER_ROOT / "ceremony" / "incept.py"
    assert script.exists()

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--dry-run",
            "--output-dir", str(tmp_path),
            "--witness-oobi", "https://staging.keri.host/witness/oobi/BAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            "--witness-oobi", "https://staging.keri.host/witness/oobi/BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB",
            "--witness-oobi", "https://staging.keri.host/witness/oobi/BCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
            "--non-interactive",
        ],
        capture_output=True,
        text=True,
        env=_make_env(),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert (tmp_path / "publisher_anchor.json").exists()
    assert (tmp_path / "publisher-aid.json").exists()
    assert (tmp_path / "kel-events" / "icp-sn-0.cesr").exists()
