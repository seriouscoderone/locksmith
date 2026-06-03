"""Verify scripts/upload.py uses AWS S3 (no DigitalOcean endpoint)."""
from pathlib import Path

UPLOAD = Path(__file__).resolve().parents[2] / "scripts" / "upload.py"


def test_no_digitaloceanspaces_endpoint():
    src = UPLOAD.read_text()
    assert "digitaloceanspaces.com" not in src


def test_supports_env_credentials():
    src = UPLOAD.read_text()
    # boto3.client('s3') without explicit access-key args lets it pick up
    # AWS_ACCESS_KEY_ID / AWS_SESSION_TOKEN from the environment (OIDC).
    assert "boto3.client" in src
    assert "--bucket" in src
    assert "--object-key" in src
    assert "--file" in src
