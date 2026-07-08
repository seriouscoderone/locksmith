"""Static checks on the release CI workflow.

We don't run the workflow here — we assert it reflects the design decisions.
"""
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "release.ci.yml"


def _load():
    return yaml.safe_load(WORKFLOW.read_text())


def test_workflow_loads():
    _load()


def test_id_token_write_permission_for_oidc():
    wf = _load()
    job = wf["jobs"]["build-macos"]
    perms = job.get("permissions", {})
    assert perms.get("id-token") == "write", (
        "OIDC requires id-token: write on the build-macos job"
    )


def test_no_stubbed_build_step():
    src = WORKFLOW.read_text()
    assert "Build command not configured" not in src


def test_invokes_build_macos_script():
    src = WORKFLOW.read_text()
    assert "packaging/build-macos.sh" in src


def test_uses_aws_configure_credentials_action():
    src = WORKFLOW.read_text()
    assert "aws-actions/configure-aws-credentials@v4" in src


def test_role_to_assume_is_release_publisher():
    src = WORKFLOW.read_text()
    assert "gha-locksmith-release-publisher" in src


def test_uploads_to_releases_keri_host_bucket():
    src = WORKFLOW.read_text()
    assert "releases.keri.host" in src
    # Should NOT reference DO Spaces anymore
    assert "digitaloceanspaces" not in src
    assert "SPACES_ACCESS_KEY" not in src


def test_runs_check_version_preflight():
    src = WORKFLOW.read_text()
    assert "scripts/check-version.py" in src


def test_installs_build_macos_extras():
    src = WORKFLOW.read_text()
    assert ".[build-macos]" in src or "[build-macos]" in src


def test_bundle_id_is_brand_derived_and_locksmith_is_host_keri_locksmith():
    # Since the multi-brand matrix, bundle_id is resolved PER BRAND via
    # `brandlib id bundle_id` rather than hardcoded in the workflow. Verify the
    # workflow derives it (no hardcoded/placeholder id) AND that the locksmith
    # brand still resolves to the real value.
    src = WORKFLOW.read_text()
    assert "brandlib id bundle_id" in src
    assert "com.CHANGEME.locksmith" not in src

    import importlib
    import sys
    sys.path.insert(0, str(WORKFLOW.parents[2] / "packaging"))
    brandlib = importlib.import_module("brandlib")
    assert brandlib._identity_value("bundle_id", "locksmith") == "host.keri.locksmith"
