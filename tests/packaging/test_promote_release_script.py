"""The off-CI promote path must refuse to anchor the wrong thing.

`scripts/promote-release.sh` replaced a per-version `/tmp/promote-<version>/
promote.sh` that was hand-`sed`-ed from the previous cut. That shape put the
version inside a COPY of the script, which is how the v0.3.1 cut ran
`promote-0.3.0/promote.sh` and added two junk events to the publisher KEL
(backlog/2026-07-25-committed-promote-release-script.md).

These tests cover the two things the backlog asks be mechanically checked: the
version assertion and the artifact-name derivation. The S3/KEL legs stay manual
by design — the publisher keystore and passphrase never enter a test.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "promote-release.sh"
ANCHOR_CHECK = REPO_ROOT / "scripts" / "check-baked-anchor.py"

BRANDS = ("locksmith", "usurance")


def _run(*args: str, bran: str | None = "dummy-not-a-real-bran"):
    env = dict(os.environ)
    if bran is not None:
        env["LOCKSMITH_PUBLISHER_BRAN"] = bran
    else:
        env.pop("LOCKSMITH_PUBLISHER_BRAN", None)
    return subprocess.run([str(SCRIPT), *args], cwd=REPO_ROOT, env=env,
                          capture_output=True, text=True, timeout=120)


def _pyproject_version() -> str:
    with open(REPO_ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["version"]


# --- it exists and is runnable -----------------------------------------------

def test_the_script_is_committed_and_executable():
    """The whole point is that it is versioned alongside the publisher, not /tmp."""
    assert SCRIPT.is_file(), (
        "scripts/promote-release.sh is missing — do not go back to hand-copying "
        "a per-version script into /tmp")
    assert os.access(SCRIPT, os.X_OK), f"{SCRIPT} is not executable"


def test_the_script_is_valid_bash():
    r = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# --- the version assertion (the v0.3.1 defect) -------------------------------

def test_a_version_that_was_never_cut_is_refused():
    """The failure the /tmp copies allowed: anchoring a version nobody built."""
    r = _run("9.9.9")
    assert r.returncode != 0, "promoting 9.9.9 must fail"
    combined = r.stdout + r.stderr
    assert "9.9.9" in combined and _pyproject_version() in combined, (
        f"the refusal must name both versions so the operator sees the mismatch; "
        f"got:\n{combined}")


def test_the_version_is_required():
    r = _run()
    assert r.returncode != 0
    assert "usage" in (r.stdout + r.stderr).lower()


def test_refusal_happens_before_anything_touches_the_keystore():
    """A bad version must not reach `anchor` — a partial anchor grows the KEL."""
    r = _run("9.9.9")
    combined = r.stdout + r.stderr
    for forbidden in ("anchor", "publish"):
        assert f"locksmith-publisher {forbidden}" not in combined, (
            f"the script reached `{forbidden}` despite a version mismatch")


def test_the_current_version_passes_the_version_assertion():
    """Guards against an assertion so strict it rejects the real version.

    Runs the REAL version, which gets past the version check and then stops at
    whatever comes next (tag/publisher/network). The only thing asserted is that
    the version mismatch message is absent.
    """
    r = _run(_pyproject_version())
    assert "but you asked to promote" not in (r.stdout + r.stderr), (
        "the real pyproject version was rejected by the version assertion")


# --- artifact-name derivation (no hardcoded brand names) ---------------------

def test_artifact_names_are_derived_not_hardcoded():
    """A new brand must need no script edit."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "brandlib id artifact_prefix" in text
    assert "brandlib id release_prefix" in text
    for hardcoded in ('"Locksmith-', "'Locksmith-", '"Usurance-', "'Usurance-"):
        assert hardcoded not in text, (
            f"{hardcoded} is hardcoded in promote-release.sh — read it from the "
            "brand manifest so a new brand needs no script edit")


@pytest.mark.parametrize("brand,prefix,release_prefix", [
    ("locksmith", "Locksmith", "releases"),
    ("usurance", "Usurance", "usurance/releases"),
])
def test_brandlib_yields_the_paths_the_script_relies_on(brand, prefix, release_prefix):
    """Pins the two brandlib answers the script builds every URL from."""
    env = dict(os.environ, LOCKSMITH_BRAND=brand)
    packaging = REPO_ROOT / "packaging"
    got_prefix = subprocess.run(
        [sys.executable, "-m", "brandlib", "id", "artifact_prefix"],
        cwd=packaging, env=env, capture_output=True, text=True, check=True).stdout.strip()
    got_release = subprocess.run(
        [sys.executable, "-m", "brandlib", "id", "release_prefix"],
        cwd=packaging, env=env, capture_output=True, text=True, check=True).stdout.strip()
    assert (got_prefix, got_release) == (prefix, release_prefix)


def test_both_brands_are_promoted_by_default():
    """One run must cover both, or a brand silently stays on the old version."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "LOCKSMITH_BRANDS:-locksmith usurance" in text


# --- the enforced gates ------------------------------------------------------

def test_the_baked_anchor_check_runs_before_publishing_and_is_enforced():
    """The v0.2.21 failure: a stale CI anchor secret, invisible from src/.

    It must gate BEFORE publish — catching it afterwards means the feed is
    already advertising an update every client will refuse.
    """
    text = SCRIPT.read_text(encoding="utf-8")
    assert ANCHOR_CHECK.is_file(), "scripts/check-baked-anchor.py is missing"
    assert "check-baked-anchor.py" in text
    pre = text.index("check-baked-anchor.py")
    pub = text.index("locksmith-publisher\" publish") if '"$PUBLISHER" publish' not in text \
        else text.index('"$PUBLISHER" publish')
    assert pre < pub, "the baked-anchor check must run BEFORE publish"
    assert "|| die" in text[pre:pre + 400], (
        "the baked-anchor check is advisory — it must refuse to publish")


def test_the_full_verifier_is_enforced_after_publishing():
    text = SCRIPT.read_text(encoding="utf-8")
    idx = text.rindex("verify-release-artifact.py")
    assert "|| die" in text[idx:idx + 400], (
        "the post-publish verification must fail the run, not just warn")


def test_the_bran_is_never_passed_on_a_command_line():
    """It goes via --bran-env, so it cannot land in a process listing or history."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "--bran " not in text and "--bran=" not in text
    assert "read -rs" in text, "the prompt fallback must be silent"


def test_no_bare_python_is_invoked():
    """It runs in the OPERATOR's shell, which has no venv active.

    A bare `python` died at "python: command not found" on the first real run —
    macOS ships no `python`, only `python3`, and the operator's shell is the one
    holding the bran, not an activated venv.
    """
    import re
    text = SCRIPT.read_text(encoding="utf-8")
    offenders = [
        line for line in text.splitlines()
        if re.search(r'(^|[|&;(]|\$\()\s*(LOCKSMITH_BRAND="\$BRAND"\s+)?python\b', line)
        and not line.lstrip().startswith("#")
    ]
    assert not offenders, (
        "promote-release.sh invokes a bare `python`; use \"$PY\" so it works in a "
        f"shell with no venv activated:\n" + "\n".join(offenders))


def test_a_signed_tag_is_not_reported_as_unsigned():
    """SSH-signed tags fail `git tag -v` without allowedSignersFile configured.

    Conflating "unsigned" with "unverifiable" printed a false alarm on a
    correctly signed tag during the v0.4.0 promote.
    """
    text = SCRIPT.read_text(encoding="utf-8")
    assert "BEGIN (SSH|PGP) SIGNATURE" in text, (
        "the script must test for signature PRESENCE separately from validity")
    assert "allowedSignersFile" in text, (
        "when a signature is present but unverifiable, say why")


def test_a_dry_run_never_claims_it_published():
    """The closing summary must not say "anchored, published and verified" after
    a dry run — that sentence fired on a run that touched nothing."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "NOTHING WAS PUBLISHED" in text
    claim = text.index("Both brands anchored, published and verified")
    guard = text.index("LOCKSMITH_PROMOTE_DRY_RUN:-0}\" == \"1\" ]]; then\n    cat <<EOF")
    assert guard < claim, "the dry-run summary must be chosen before the real one"


def test_dry_run_stops_before_the_keystore():
    text = SCRIPT.read_text(encoding="utf-8")
    dry = text.index("DRY RUN: stopping before anchor")
    anchor = text.index('"$PUBLISHER" anchor')
    assert dry < anchor, "the dry-run bail must precede the anchor invocation"


def test_aws_credentials_are_checked_before_anchoring():
    """`publish` uploads to S3. If credentials are missing, the run must stop
    BEFORE `anchor` — on the real v0.4.0 promote it died with NoCredentialsError
    after the anchor was already signed, witnessed and committed to the KEL,
    leaving a release anchored with no feed advertising it."""
    text = SCRIPT.read_text(encoding="utf-8")
    aws = text.index("AWS credentials cannot reach")
    anchor = text.index('"$PUBLISHER" anchor')
    assert aws < anchor, "the AWS credential check must precede the anchor"
    assert "AWS_PROFILE=personal" in text, (
        "the failure must name a concrete way to supply credentials")


def test_the_aws_check_uses_the_same_resolution_path_as_the_publisher():
    """boto3, not the `aws` CLI — the CLI can resolve credentials the publisher
    cannot, which would let the preflight pass while publish still fails."""
    text = SCRIPT.read_text(encoding="utf-8")
    idx = text.index("AWS credentials cannot reach")
    preamble = text[:idx]
    assert "import boto3" in preamble
    assert "aws sts get-caller-identity" not in preamble


def test_promote_to_latest_is_not_automated():
    """Deliberate per the backlog: verification passing is not permission to ship."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "not automated" in text.lower() or "conscious decision" in text.lower()
