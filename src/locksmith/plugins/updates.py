# -*- encoding: utf-8 -*-
"""
locksmith.plugins.updates module

Background poll for plugin updates. PluginUpdateChecker reads
~/.locksmith/plugins/index.json, runs `git ls-remote` per github-source
plugin, and writes the result to ~/.locksmith/plugins/update-cache.json.
The Qt main window owns a QTimer that calls check_now() periodically.

See docs/superpowers/specs/2026-05-25-plugin-upgrade-design.md.
"""
from __future__ import annotations

import datetime
import subprocess
from typing import Any, Callable

from keri import help

from locksmith.plugins import storage

logger = help.ogler.getLogger(__name__)


def _ls_remote(url: str, ref: str) -> str:
    """Return the SHA at the given ref on the given remote URL.

    Raises subprocess.CalledProcessError on non-zero exit.
    """
    result = subprocess.run(
        ["git", "ls-remote", url, ref],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, ["git", "ls-remote", url, ref],
            output=result.stdout, stderr=result.stderr,
        )
    first_line = result.stdout.splitlines()[0] if result.stdout else ""
    sha = first_line.split("\t")[0].strip() if first_line else ""
    if not sha:
        raise subprocess.CalledProcessError(
            -1, ["git", "ls-remote", url, ref],
            output=result.stdout, stderr="empty ls-remote output",
        )
    return sha


def _now_iso() -> str:
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"


class PluginUpdateChecker:
    """Compares installed plugin SHAs to remote HEAD and maintains a cache.

    Plain Python — the Qt main window drives a QTimer that calls check_now()
    periodically. Subscribers are notified on whichever thread invokes
    check_all_plugins() (in production that's always the Qt main thread).
    """

    def __init__(self, manager: Any, *, interval_hours: int = 6):
        self._manager = manager
        self._interval_seconds = interval_hours * 3600
        self._subscribers: list[Callable[[], None]] = []

    @property
    def interval_seconds(self) -> int:
        return self._interval_seconds

    def cache(self) -> dict[str, Any]:
        """Return the current update cache (read fresh from disk each call)."""
        return storage.read_update_cache()

    def subscribe(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Register a callback fired after each check_all_plugins() pass.
        Returns an unsubscribe function."""
        self._subscribers.append(callback)

        def _unsubscribe() -> None:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

        return _unsubscribe

    def check_now(self) -> None:
        """Run check_all_plugins() unconditionally. Called by the UI button
        and by the QTimer in LocksmithWindow."""
        self.check_all_plugins()

    def should_check_now(self) -> bool:
        """True if the cache is missing or older than interval_seconds.
        Used at startup to decide whether to fire an immediate check."""
        cache = storage.read_update_cache()
        elapsed = self._elapsed_since(cache.get("checked_at"))
        return elapsed is None or elapsed >= self._interval_seconds

    def check_all_plugins(self) -> None:
        """One full pass: for every github-source plugin in the index,
        run ls-remote and update the cache. Notify subscribers at the end."""
        idx = storage.read_index()
        cache = storage.read_update_cache()
        cache.setdefault("plugins", {})

        installed_ids = set()
        for record in idx.get("plugins", []):
            pid = record["plugin_id"]
            source = record.get("source", {})
            if source.get("type") != "github":
                continue
            installed_ids.add(pid)
            self._check_one(record, source, cache)

        # Drop cache entries for plugins no longer in the index.
        cache["plugins"] = {
            pid: entry for pid, entry in cache["plugins"].items() if pid in installed_ids
        }

        cache["checked_at"] = _now_iso()
        storage.write_update_cache(cache)
        self._notify_subscribers()

    # ----- internals ------------------------------------------------------

    def _check_one(
        self, record: dict[str, Any], source: dict[str, Any], cache: dict[str, Any],
    ) -> None:
        """Update cache["plugins"][pid] in-place for one github-source plugin."""
        pid = record["plugin_id"]
        user_repo = source.get("user_repo")
        ref = source.get("ref") or "HEAD"
        url = f"https://github.com/{user_repo}.git"
        installed = record["commit"]
        existing = cache["plugins"].get(pid, {})
        try:
            latest = _ls_remote(url, ref)
        except subprocess.CalledProcessError as e:
            err = (e.stderr or "").strip() or f"ls-remote exit {e.returncode}"
            cache["plugins"][pid] = {
                "ref": ref,
                "installed_commit": installed,
                "latest_commit": existing.get("latest_commit"),
                "latest_checked_at": _now_iso(),
                "update_available": existing.get("update_available", False),
                "last_error": f"ls-remote: {err}",
            }
            logger.info(
                "plugin.update.check_failed plugin_id=%s error=%s", pid, err,
            )
            return
        except Exception as e:  # noqa: BLE001
            logger.exception("plugin.update.unexpected_check_failure plugin_id=%s", pid)
            cache["plugins"][pid] = {
                "ref": ref,
                "installed_commit": installed,
                "latest_commit": existing.get("latest_commit"),
                "latest_checked_at": _now_iso(),
                "update_available": existing.get("update_available", False),
                "last_error": f"unexpected: {type(e).__name__}: {e}",
            }
            return

        cache["plugins"][pid] = {
            "ref": ref,
            "installed_commit": installed,
            "latest_commit": latest,
            "latest_checked_at": _now_iso(),
            "update_available": latest != installed,
            "last_error": None,
        }
        logger.info(
            "plugin.update.checked plugin_id=%s installed=%s latest=%s update_available=%s",
            pid, installed[:7], latest[:7], latest != installed,
        )

    def _elapsed_since(self, iso: str | None) -> float | None:
        if not iso:
            return None
        try:
            ts = datetime.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return None
        return (datetime.datetime.utcnow() - ts).total_seconds()

    def _notify_subscribers(self) -> None:
        for cb in list(self._subscribers):
            try:
                cb()
            except Exception:  # noqa: BLE001
                logger.exception("plugin.update.subscriber_failure")
