import subprocess
import sys
from pathlib import Path


def test_ceremony_script_dry_run_emits_files(tmp_path: Path):
    script = Path(__file__).resolve().parent.parent / "ceremony" / "incept.py"
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
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert (tmp_path / "publisher_anchor.json").exists()
    assert (tmp_path / "publisher-aid.json").exists()
    assert (tmp_path / "kel-events" / "icp-sn-0.cesr").exists()
