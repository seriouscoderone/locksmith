# -*- encoding: utf-8 -*-
"""
locksmith.plugins.storage module

Path resolution + atomic JSON read/write for plugin install state.

Two files are managed:
- ``~/.locksmith/plugins/index.json``: user-scoped, shared across all
  Locksmith wallet instances. Records what's installed.
- ``<keri-base>/locksmith/plugin-enable.json``: per-wallet exclude list.

Both writes use temp-file + os.replace() for atomicity, so concurrent
wallet instances installing simultaneously can never see a half-written
file. Last writer wins; convergence on next restart.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from keri import help

logger = help.ogler.getLogger(__name__)


def _user_home() -> Path:
    """Indirection point so tests can monkeypatch the home dir."""
    return Path.home()


def plugin_root() -> Path:
    """Directory holding all user-scoped plugin clones + the registry."""
    return _user_home() / ".locksmith" / "plugins"


def index_path() -> Path:
    """Path to the shared installed-plugin registry."""
    return plugin_root() / "index.json"


def plugin_clone_dir(plugin_id: str) -> Path:
    """Where a plugin's repo clone lives on disk."""
    return plugin_root() / plugin_id


def enable_list_path(keri_base: Path) -> Path:
    """Per-wallet plugin-enable.json under the given KERI base path."""
    return Path(keri_base) / "locksmith" / "plugin-enable.json"


def index_lock_path() -> Path:
    """Lockfile used to serialise concurrent read-modify-write operations on the index."""
    return plugin_root() / "index.lock"


@contextlib.contextmanager
def index_write_lock():
    """Acquire an exclusive file lock around index read-modify-write operations.

    Uses ``fcntl.flock`` (POSIX, inherited by forked processes).  Safe for
    concurrent threads **and** concurrent processes.  The lock is held only
    for the duration of the read-modify-write cycle, not for the atomic
    ``os.replace`` write itself (which is already atomic at the OS level).
    """
    plugin_root().mkdir(parents=True, exist_ok=True)
    lock_path = index_lock_path()
    # Open (or create) the lockfile.  Never hold a reference to its data.
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _default_index() -> dict[str, Any]:
    return {"format": 1, "plugins": []}


def _default_enable_list() -> dict[str, Any]:
    return {"format": 1, "excluded": []}


def read_index() -> dict[str, Any]:
    """Read the shared install registry. Returns default if missing or malformed."""
    path = index_path()
    if not path.exists():
        return _default_index()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("plugin.index.read_failed path=%s error=%s", path, e)
        return _default_index()


def write_index(payload: dict[str, Any]) -> None:
    """Atomically replace the shared install registry."""
    _atomic_write_json(index_path(), payload)
    logger.info(
        "plugin.index.written path=%s plugins=%d",
        index_path(), len(payload.get("plugins", [])),
    )


def read_enable_list(keri_base: Path) -> dict[str, Any]:
    """Read this wallet's exclude list. Returns default if missing or malformed."""
    path = enable_list_path(keri_base)
    if not path.exists():
        return _default_enable_list()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("plugin.enable.read_failed path=%s error=%s", path, e)
        return _default_enable_list()


def write_enable_list(keri_base: Path, payload: dict[str, Any]) -> None:
    """Atomically replace this wallet's exclude list."""
    path = enable_list_path(keri_base)
    _atomic_write_json(path, payload)
    logger.info(
        "plugin.enable.written path=%s excluded=%s",
        path, payload.get("excluded", []),
    )


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # NamedTemporaryFile in the same directory ensures os.replace stays atomic.
    fd, tmp = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
