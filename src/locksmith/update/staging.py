"""Per-user staging directory + exclusive file lock per spec §7.8.

Three nested TOCTOU defenses:

1. Staging dir is 0700-permissioned per-user (POSIX); Windows relies on
   per-user ``%LOCALAPPDATA%`` ACLs.
2. An exclusive lock is held over the staged file from verify -> install.
3. The staged file is re-hashed immediately before exec hand-off.

Reuses the cross-platform lock backend pattern from
``locksmith.plugins.storage`` (fcntl on POSIX, msvcrt on Windows).
"""
from __future__ import annotations

import contextlib
import hashlib
import os
import platform as _platform
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from locksmith.update.errors import HashMismatchError, StagingError


# Platform-specific lock backends. Use non-blocking modes so a second
# verifier instance fails fast instead of stalling.
if sys.platform == "win32":  # pragma: no cover - selected per OS
    import msvcrt

    def _lock(fd: int) -> None:
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError as ex:
            raise StagingError(
                f"could not acquire lock: {ex}",
                log_fields={"errno": getattr(ex, "errno", None)},
            ) from ex

    def _unlock(fd: int) -> None:
        with contextlib.suppress(OSError):
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _lock(fd: int) -> None:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as ex:
            raise StagingError(
                f"could not acquire flock: {ex}",
                log_fields={"errno": getattr(ex, "errno", None)},
            ) from ex

    def _unlock(fd: int) -> None:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)


def default_staging_root() -> Path:
    """Return the platform-appropriate staging directory.

    macOS: ``~/Library/Application Support/Locksmith/staging``
    Windows: ``%LOCALAPPDATA%/Locksmith/staging``
    Other: ``~/.local/share/locksmith/staging``
    """
    sysname = _platform.system()
    if sysname == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Locksmith" / "staging"
    if sysname == "Windows":
        base = os.environ.get("LOCALAPPDATA", str(Path.home()))
        return Path(base) / "Locksmith" / "staging"
    return Path.home() / ".local" / "share" / "locksmith" / "staging"


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class StagedArtifact:
    """A staged file under an exclusive lock.

    Caller invokes ``recheck_or_raise()`` immediately before exec to detect
    last-millisecond swaps.
    """

    path: Path
    sha256: str
    locked: bool = False
    _fd: int | None = field(default=None, repr=False)

    def recheck_or_raise(self) -> bool:
        actual = _hash_file(self.path)
        if actual != self.sha256:
            raise HashMismatchError(
                f"staged file sha256 changed: expected {self.sha256} got {actual}",
                log_fields={
                    "expected_sha256": self.sha256,
                    "actual_sha256": actual,
                    "staged_path": str(self.path),
                },
            )
        return True


@dataclass
class StagingArea:
    """A per-user staging dir, lazily created with 0700 perms (POSIX)."""

    root: Path

    def ensure(self) -> None:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError as ex:
            raise StagingError(
                f"cannot create staging dir: {ex}",
                log_fields={"root": str(self.root)},
            ) from ex
        if sys.platform != "win32":
            try:
                os.chmod(self.root, 0o700)
            except OSError as ex:
                raise StagingError(
                    f"cannot chmod 0700: {ex}",
                    log_fields={"root": str(self.root)},
                ) from ex


@contextlib.contextmanager
def stage_and_lock(
    src: Path,
    *,
    sha256: str,
    root: Path | None = None,
) -> Iterator[StagedArtifact]:
    """Copy ``src`` into the staging root, hold an exclusive lock, yield it.

    The yielded ``StagedArtifact`` is locked for the duration of the
    ``with`` block. Caller is expected to invoke ``recheck_or_raise()``
    just before exec/install.

    Raises:
        ``StagingError`` if the source is missing or the lock can't be acquired.
        ``HashMismatchError`` if ``src`` doesn't match ``sha256`` at stage time.
    """
    if not src.is_file():
        raise StagingError(
            f"source not found: {src}",
            log_fields={"source": str(src)},
        )
    area = StagingArea(root=root or default_staging_root())
    area.ensure()

    # Hash-check the source before copying. Stops obvious cases where the
    # downloader was redirected mid-flight.
    actual = _hash_file(src)
    if actual != sha256:
        raise HashMismatchError(
            f"source sha256 mismatch: expected {sha256} got {actual}",
            log_fields={
                "expected_sha256": sha256,
                "actual_sha256": actual,
                "source": str(src),
            },
        )

    dst = area.root / src.name
    try:
        shutil.copyfile(src, dst)
    except OSError as ex:
        raise StagingError(
            f"copy failed: {ex}",
            log_fields={"source": str(src), "dest": str(dst)},
        ) from ex

    fd = os.open(dst, os.O_RDWR)
    try:
        _lock(fd)
        staged = StagedArtifact(path=dst, sha256=sha256, locked=True, _fd=fd)
        try:
            yield staged
        finally:
            staged.locked = False
    finally:
        _unlock(fd)
        os.close(fd)
