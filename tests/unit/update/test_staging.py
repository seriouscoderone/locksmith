"""Tests for ``locksmith.update.staging`` — TOCTOU defenses per spec §7.8."""
import hashlib
import platform as _platform
import stat
import sys
from pathlib import Path

import pytest

from locksmith.update.errors import HashMismatchError, StagingError
from locksmith.update.staging import (
    StagedArtifact,
    StagingArea,
    default_staging_root,
    stage_and_lock,
)


@pytest.fixture
def tmp_root(tmp_path) -> Path:
    return tmp_path / "staging"


def test_default_staging_root_per_platform():
    p = default_staging_root()
    assert p.name == "staging"
    if _platform.system() == "Darwin":
        assert "Locksmith" in str(p)
        assert "Application Support" in str(p)
    elif _platform.system() == "Windows":  # pragma: no cover
        assert "Locksmith" in str(p)


def test_staging_directory_is_created_with_0700(tmp_root):
    area = StagingArea(root=tmp_root)
    area.ensure()
    assert tmp_root.is_dir()
    if sys.platform != "win32":
        mode = stat.S_IMODE(tmp_root.stat().st_mode)
        assert mode == 0o700


def test_stage_and_lock_writes_artifact_under_root(tmp_root, tmp_path):
    src = tmp_path / "candidate.bin"
    src.write_bytes(b"hello locksmith")
    expected = hashlib.sha256(src.read_bytes()).hexdigest()

    with stage_and_lock(src, sha256=expected, root=tmp_root) as staged:
        assert isinstance(staged, StagedArtifact)
        assert staged.path.parent == tmp_root
        assert staged.path.read_bytes() == b"hello locksmith"
        assert staged.locked is True


def test_lock_is_released_after_context_exit(tmp_root, tmp_path):
    src = tmp_path / "x.bin"
    src.write_bytes(b"abc")
    sha = hashlib.sha256(b"abc").hexdigest()
    with stage_and_lock(src, sha256=sha, root=tmp_root) as staged:
        first_path = staged.path
    # Re-acquiring the lock immediately afterward must succeed.
    src2 = tmp_path / "y.bin"
    src2.write_bytes(b"abc")
    with stage_and_lock(src2, sha256=sha, root=tmp_root) as staged2:
        assert staged2.locked is True


def test_initial_hash_mismatch_raises(tmp_root, tmp_path):
    src = tmp_path / "z.bin"
    src.write_bytes(b"correct")
    bad_sha = "0" * 64
    with pytest.raises(HashMismatchError):
        with stage_and_lock(src, sha256=bad_sha, root=tmp_root):
            pass


def test_recheck_before_handoff_detects_swap(tmp_root, tmp_path):
    src = tmp_path / "z.bin"
    src.write_bytes(b"correct")
    sha = hashlib.sha256(b"correct").hexdigest()
    with stage_and_lock(src, sha256=sha, root=tmp_root) as staged:
        # Simulate hostile swap of the staged file.
        staged.path.write_bytes(b"swapped")
        with pytest.raises(HashMismatchError):
            staged.recheck_or_raise()


def test_recheck_returns_true_for_unchanged_file(tmp_root, tmp_path):
    src = tmp_path / "z.bin"
    src.write_bytes(b"correct")
    sha = hashlib.sha256(b"correct").hexdigest()
    with stage_and_lock(src, sha256=sha, root=tmp_root) as staged:
        assert staged.recheck_or_raise() is True


def test_missing_source_raises_staging_error(tmp_root, tmp_path):
    with pytest.raises(StagingError):
        with stage_and_lock(tmp_path / "nope.bin", sha256="0" * 64, root=tmp_root):
            pass


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX flock semantics")
def test_concurrent_lock_attempt_fails(tmp_root, tmp_path):
    """A second stage_and_lock on the same destination raises StagingError."""
    src = tmp_path / "a.bin"
    src.write_bytes(b"x")
    sha = hashlib.sha256(b"x").hexdigest()
    with stage_and_lock(src, sha256=sha, root=tmp_root):
        # Second invocation copies a new source over the same dst; the
        # exclusive lock on dst should block.
        src2 = tmp_path / "a.bin"  # same name → same dst
        # Re-create with same bytes to satisfy hash.
        src2.write_bytes(b"x")
        with pytest.raises(StagingError):
            with stage_and_lock(src2, sha256=sha, root=tmp_root):
                pass
