# -*- encoding: utf-8 -*-
"""
locksmith.plugins.installer module

Install / uninstall plugins. Pure logic + filesystem + ``git`` CLI.
No UI dependency; called by the Plugins page dialogs but also usable
from tests and scripts.
"""
from __future__ import annotations

import datetime
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from keri import help

from locksmith.plugins import storage
from locksmith.plugins.manifest import Manifest, ManifestError, parse_manifest

logger = help.ogler.getLogger(__name__)


class InstallError(RuntimeError):
    """Raised when an install or uninstall cannot complete."""


@dataclass(frozen=True)
class SourceDescriptor:
    """How to fetch a plugin."""

    type: Literal["github", "local"]
    user_repo: str | None = None  # for github
    ref: str | None = None        # for github (branch or tag)
    path: str | None = None       # for local

    def to_dict(self) -> dict[str, Any]:
        if self.type == "github":
            return {"type": "github", "user_repo": self.user_repo, "ref": self.ref}
        return {"type": "local", "path": self.path}


class PluginInstaller:
    """Install + uninstall plugins. Operates on storage paths only."""

    def install(self, source: SourceDescriptor) -> dict[str, Any]:
        """Install a plugin from the given source. Returns the index record."""
        logger.info("plugin.install.requested source=%s", source.to_dict())

        # Stage into a temp dir alongside the final location so the final rename is atomic.
        storage.plugin_root().mkdir(parents=True, exist_ok=True)
        staging_dir = Path(tempfile.mkdtemp(
            prefix=".tmp-install-", dir=storage.plugin_root(),
        ))

        try:
            commit = self._fetch_into(source, staging_dir)

            manifest = self._parse_manifest_in(staging_dir)
            self._check_not_already_installed(manifest.plugin_id)

            final_dir = storage.plugin_clone_dir(manifest.plugin_id)
            if final_dir.exists():
                raise InstallError(
                    f"plugin clone directory already exists at {final_dir}"
                )

            staging_dir.rename(final_dir)
            staging_dir = None  # rename succeeded; don't clean up on finally

            try:
                record = self._record_for(manifest, source, commit)
                self._append_to_index(record)
            except Exception:
                # Roll back the rename so we don't leave an orphaned clone
                # with no index entry. The plugin would otherwise be stuck
                # in a half-installed state: next install attempt finds the
                # clone dir present but `_check_not_already_installed` finds
                # no index entry, leading to "plugin clone directory already
                # exists".
                logger.exception(
                    "plugin.install.rollback plugin_id=%s",
                    manifest.plugin_id,
                )
                shutil.rmtree(final_dir, ignore_errors=True)
                raise

            logger.info(
                "plugin.install.completed plugin_id=%s commit=%s",
                manifest.plugin_id, commit,
            )
            return record
        except InstallError:
            raise
        except Exception as e:
            logger.exception("plugin.install.unexpected_failure")
            raise InstallError(f"unexpected install failure: {e}") from e
        finally:
            if staging_dir is not None and staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)

    def uninstall(self, plugin_id: str) -> None:
        """Remove a plugin from disk and from the index."""
        logger.info("plugin.uninstall.requested plugin_id=%s", plugin_id)
        idx = storage.read_index()
        kept = [p for p in idx.get("plugins", []) if p["plugin_id"] != plugin_id]
        if len(kept) == len(idx.get("plugins", [])):
            raise InstallError(f"plugin not installed: {plugin_id}")

        clone = storage.plugin_clone_dir(plugin_id)
        if clone.exists():
            shutil.rmtree(clone)

        idx["plugins"] = kept
        storage.write_index(idx)
        logger.info("plugin.uninstall.completed plugin_id=%s", plugin_id)

    def upgrade(self, plugin_id: str) -> dict[str, Any]:
        """Re-fetch latest commit for a github-source plugin via sidecar
        clone + atomic swap. Returns the new index record.

        Raises InstallError on failure; the existing clone is left intact.
        See docs/superpowers/specs/2026-05-25-plugin-upgrade-design.md.
        """
        logger.info("plugin.upgrade.requested plugin_id=%s", plugin_id)
        idx = storage.read_index()
        record = next(
            (p for p in idx.get("plugins", []) if p["plugin_id"] == plugin_id),
            None,
        )
        if record is None:
            raise InstallError(f"plugin not installed: {plugin_id}")

        source_dict = record.get("source", {})
        if source_dict.get("type") != "github":
            raise InstallError(
                f"plugin '{plugin_id}' has source type "
                f"'{source_dict.get('type')}' — upgrade only supports github sources; "
                f"uninstall and reinstall to pick up changes."
            )

        source = SourceDescriptor(
            type="github",
            user_repo=source_dict.get("user_repo"),
            ref=source_dict.get("ref"),
        )

        staging = storage.plugin_staging_dir(plugin_id)
        previous = storage.plugin_previous_dir(plugin_id)
        final = storage.plugin_clone_dir(plugin_id)
        old_sha = record["commit"]

        # Stage fresh clone
        if staging.exists():
            shutil.rmtree(staging)
        try:
            storage.plugin_root().mkdir(parents=True, exist_ok=True)
            staging.mkdir()
            new_sha = self._fetch_into(source, staging)
            manifest = self._parse_manifest_in(staging)
            if manifest.plugin_id != plugin_id:
                raise InstallError(
                    f"new manifest declares plugin_id={manifest.plugin_id!r}, "
                    f"expected {plugin_id!r}"
                )
        except InstallError:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            raise
        except Exception as e:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            logger.exception("plugin.upgrade.staging_failure plugin_id=%s", plugin_id)
            raise InstallError(f"upgrade staging failed: {e}") from e

        # Atomic swap
        if previous.exists():
            shutil.rmtree(previous)
        try:
            final.rename(previous)
        except OSError as e:
            shutil.rmtree(staging, ignore_errors=True)
            raise InstallError(f"could not move old clone aside: {e}") from e

        try:
            staging.rename(final)
        except OSError as e:
            try:
                previous.rename(final)
            except OSError:
                logger.exception(
                    "plugin.upgrade.swap_unrecoverable plugin_id=%s "
                    "previous=%s staging=%s final=%s",
                    plugin_id, previous, staging, final,
                )
            shutil.rmtree(staging, ignore_errors=True)
            raise InstallError(f"could not swap new clone into place: {e}") from e

        # Update index
        with storage.index_write_lock():
            idx = storage.read_index()
            for p in idx.get("plugins", []):
                if p["plugin_id"] == plugin_id:
                    p["commit"] = new_sha
                    p["installed_at"] = (
                        datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
                    )
                    p["manifest_snapshot"] = manifest.to_dict()
                    p["previous_commit"] = old_sha
                    break
            storage.write_index(idx)
            new_record = next(p for p in idx["plugins"] if p["plugin_id"] == plugin_id)

        # Update cache: reflect new installed_commit, clear update_available
        cache = storage.read_update_cache()
        if plugin_id in cache.get("plugins", {}):
            entry = cache["plugins"][plugin_id]
            entry["installed_commit"] = new_sha
            entry["latest_commit"] = new_sha
            entry["update_available"] = False
            entry["last_error"] = None
        storage.write_update_cache(cache)

        logger.info(
            "plugin.upgrade.completed plugin_id=%s old=%s new=%s",
            plugin_id, old_sha[:7], new_sha[:7],
        )
        return new_record

    # ------------------- internals ----------------------------------

    def _fetch_into(self, source: SourceDescriptor, dest: Path) -> str:
        """Populate ``dest`` with the plugin content. Returns the commit SHA (or stub for local)."""
        if source.type == "local":
            assert source.path is not None
            src_path = Path(source.path)
            if not src_path.exists():
                raise InstallError(f"local source path does not exist: {src_path}")
            # `dest` was just created by mkdtemp — empty it before copytree.
            shutil.rmtree(dest)
            shutil.copytree(src_path, dest)
            return "local:" + datetime.datetime.utcnow().isoformat(timespec="seconds")

        # github
        assert source.user_repo is not None
        shutil.rmtree(dest)
        url = f"https://github.com/{source.user_repo}.git"
        cmd = ["git", "clone", "--depth", "1"]
        if source.ref:
            cmd += ["--branch", source.ref]
        cmd += [url, str(dest)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise InstallError(
                f"git clone failed (exit {result.returncode}): "
                f"{result.stderr.strip() or 'no stderr'}"
            )
        sha = subprocess.check_output(
            ["git", "-C", str(dest), "rev-parse", "HEAD"],
        ).decode("utf-8").strip()
        return sha

    def _parse_manifest_in(self, clone_dir: Path) -> Manifest:
        manifest_file = clone_dir / "locksmith-plugin.toml"
        if not manifest_file.exists():
            raise InstallError(
                f"no locksmith-plugin.toml at {clone_dir} — not a Locksmith plugin"
            )
        try:
            return parse_manifest(manifest_file)
        except ManifestError as e:
            raise InstallError(str(e)) from e

    def _check_not_already_installed(self, plugin_id: str) -> None:
        idx = storage.read_index()
        for p in idx.get("plugins", []):
            if p["plugin_id"] == plugin_id:
                src = p.get("source", {})
                raise InstallError(
                    f"plugin '{plugin_id}' is already installed "
                    f"(from {src.get('type', '?')}:{src.get('user_repo') or src.get('path')}). "
                    f"Uninstall it first."
                )

    def _record_for(
        self, manifest: Manifest, source: SourceDescriptor, commit: str,
    ) -> dict[str, Any]:
        return {
            "plugin_id": manifest.plugin_id,
            "source": source.to_dict(),
            "commit": commit,
            "installed_at": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "manifest_snapshot": manifest.to_dict(),
        }

    def _append_to_index(self, record: dict[str, Any]) -> None:
        with storage.index_write_lock():
            idx = storage.read_index()
            idx.setdefault("format", 1)
            idx.setdefault("plugins", []).append(record)
            storage.write_index(idx)
