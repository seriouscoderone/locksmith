import json
import subprocess
import sys
from pathlib import Path

SCRIPT = "scripts/check-anchor-present.py"


def _run(path):
    return subprocess.run([sys.executable, SCRIPT, "--anchor", str(path)],
                          capture_output=True, text=True)


def test_rejects_placeholder(tmp_path):
    p = tmp_path / "a.json"
    p.write_text(json.dumps({"publisher_aid": "ELocksmithPublisherAidPlaceholderExample00000"}))
    assert _run(p).returncode != 0


def test_accepts_real(tmp_path):
    p = tmp_path / "a.json"
    p.write_text(json.dumps({"publisher_aid": "ErealAID000000000000000000000000000000000000",
                             "embedded_kel_sn": 0, "toad": 3,
                             "witness_oobis": ["https://w/oobi/B/witness"]}))
    assert _run(p).returncode == 0


def test_rejects_missing(tmp_path):
    assert _run(tmp_path / "nope.json").returncode != 0


def test_rejects_no_witness_oobis(tmp_path):
    p = tmp_path / "a.json"
    p.write_text(json.dumps({"publisher_aid": "ErealAID000000000000000000000000000000000000",
                             "embedded_kel_sn": 0, "toad": 3,
                             "witness_oobis": []}))
    assert _run(p).returncode != 0
