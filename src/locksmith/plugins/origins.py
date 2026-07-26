# -*- encoding: utf-8 -*-
"""
locksmith.plugins.origins module

**Where a plugin is discovered and imported from** — the strategy seam behind
``PluginManager.discover()``. Design:
``docs/superpowers/specs/2026-07-25-plugin-origin-strategy-design.md``.

"Origin" is deliberately NOT "source": ``PluginState.source`` and
``installer.py`` already use *source* for the installer's provenance descriptor
(``{type: "github", user_repo: ...}`` / ``{type: "local", path: ...}``) — where a
plugin's code was **fetched from**. An origin is the discovery-and-import
**channel**. One installed clone has both: origin ``index-clone``, source
``{github, user/repo}``.

Two properties make this more than tidiness:

1. ``candidates()`` yields **unimported** ``Candidate`` objects carrying a
   deferred ``load``. Activation policy runs on identity first, so an excluded
   or superseded plugin's module is never imported (defect D1 in the spec —
   previously ``ep.load()`` ran *before* the exclude check).
2. ``requires_build_collection`` / ``collected_packages`` declare that an
   origin's code is reachable only by dynamic import and therefore MUST be
   collected into frozen builds. PyInstaller cannot see ``ep.load()``, and that
   invisible coupling shipped three times (KF missing in 0.2.21; the whole HOA
   surface missing in 0.3.1). ``tests/unit/test_specs_bundle_plugin_origins.py``
   derives what the specs must contain from these fields, so the requirement is
   checked rather than remembered.
"""
from __future__ import annotations

import importlib
import importlib.metadata
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from keri import help

from locksmith.plugins import storage
from locksmith.plugins.base import PluginCore

logger = help.ogler.getLogger(__name__)

#: Default-on in-tree plugins: loaded for every brand (subject to the peel).
ENTRY_POINT_GROUP = "locksmith.plugins"

#: Brand-composed in-tree plugins: loaded ONLY when the active brand lists the
#: plugin under ``[plugins] bundled``. The *group* carries that policy because it
#: must be decidable before import — a class attribute would require importing
#: the very module we may need to skip. This replaces the framework-level
#: ``BUNDLED_ONLY_PLUGIN_IDS`` id list, so adding a composed plugin no longer
#: means editing the framework.
COMPOSED_ENTRY_POINT_GROUP = "locksmith.plugins.composed"


@dataclass(frozen=True)
class Candidate:
    """A plugin that has been *discovered* but NOT imported.

    Activation policy is evaluated against this; ``load()`` is called only for
    survivors. ``record`` carries the raw index entry for origins whose policy
    needs it (compatibility, clone-files-present).
    """

    plugin_id: str
    origin_id: str
    load: Callable[[], PluginCore]
    source: dict[str, Any] = field(default_factory=dict)
    manifest_snapshot: dict[str, Any] = field(default_factory=dict)
    in_tree: bool = False
    record: dict[str, Any] | None = None


@runtime_checkable
class PluginOrigin(Protocol):
    """A discovery-and-import channel."""

    origin_id: str
    requires_build_collection: bool
    collected_packages: tuple[str, ...]
    log_source: str

    def candidates(self) -> Iterable[Candidate]:
        ...


class EntryPointOrigin:
    """In-tree plugins declared as Python entry points.

    Reached only via ``ep.load()``, so PyInstaller's static analysis cannot see
    them: ``requires_build_collection`` is True and the specs must
    ``collect_submodules`` the package root (plus ``copy_metadata`` so the
    entry-point table itself survives).
    """

    requires_build_collection = True
    collected_packages = ("locksmith.plugins",)
    #: Value used in the ``plugin.loaded ... source=<x>`` log line. Kept as the
    #: pre-change literal so the observability contract is unchanged.
    log_source = "entry_point"

    def __init__(self, group: str = ENTRY_POINT_GROUP,
                 origin_id: str = "entry-point"):
        self.group = group
        self.origin_id = origin_id

    def candidates(self) -> Iterable[Candidate]:
        try:
            eps = importlib.metadata.entry_points(group=self.group)
        except Exception:  # noqa: BLE001 — metadata backend errors must not abort discovery
            logger.exception("plugin.entry_points.discovery_failed group=%s",
                             self.group)
            return
        for ep in eps:
            yield Candidate(
                plugin_id=ep.name,
                origin_id=self.origin_id,
                in_tree=True,
                load=_entry_point_loader(ep),
            )


class ComposedEntryPointOrigin(EntryPointOrigin):
    """Brand-composed in-tree plugins (``[plugins] bundled`` opt-in)."""

    def __init__(self):
        super().__init__(group=COMPOSED_ENTRY_POINT_GROUP,
                         origin_id="entry-point-composed")


class IndexCloneOrigin:
    """Plugins installed into ``~/.locksmith/plugins/`` and recorded in
    ``index.json`` (the GitHub / local-path installs).

    Their code lives OUTSIDE the app bundle by design, which is precisely why
    they kept working when the bundled plugins were missing from frozen builds —
    hence ``requires_build_collection = False``.
    """

    origin_id = "index-clone"
    requires_build_collection = False
    collected_packages: tuple[str, ...] = ()
    log_source = "clone"

    def candidates(self) -> Iterable[Candidate]:
        idx = storage.read_index()
        for record in idx.get("plugins", []):
            pid = record.get("plugin_id")
            if not pid:
                continue
            yield Candidate(
                plugin_id=pid,
                origin_id=self.origin_id,
                source=record.get("source", {}),
                manifest_snapshot=record.get("manifest_snapshot", {}),
                record=record,
                load=_clone_loader(pid, record),
            )


def _entry_point_loader(ep: Any) -> Callable[[], PluginCore]:
    def _load() -> PluginCore:
        plugin = ep.load()()
        # Mirror the clone loader's identity check: policy was decided from
        # ep.name, so a class disagreeing about its own id would silently
        # bypass the exclude/peel/composition decisions made above.
        if plugin.plugin_id != ep.name:
            raise RuntimeError(
                f"plugin_id mismatch: entry point is {ep.name!r}, "
                f"class returns {plugin.plugin_id!r}"
            )
        return plugin

    return _load


def _clone_loader(pid: str, record: dict[str, Any]) -> Callable[[], PluginCore]:
    def _load() -> PluginCore:
        clone = storage.plugin_clone_dir(pid)
        snap = record.get("manifest_snapshot", {})
        entry_point = snap.get("entry_point")
        if not entry_point or ":" not in entry_point:
            raise RuntimeError(
                f"missing or malformed entry_point in record: {entry_point!r}"
            )
        module_name, _, class_name = entry_point.partition(":")

        # Support both flat-layout (<clone>/<pkg>/) and src-layout
        # (<clone>/src/<pkg>/) plugins. Add src/ first if present so it takes
        # priority; clone-root stays as a fallback for flat-layout.
        src_dir = clone / "src"
        for candidate in (src_dir, clone) if src_dir.is_dir() else (clone,):
            cand_str = str(candidate)
            if cand_str not in sys.path:
                sys.path.insert(0, cand_str)

        module = importlib.import_module(module_name)
        plugin = getattr(module, class_name)()
        if plugin.plugin_id != pid:
            raise RuntimeError(
                f"plugin_id mismatch: manifest says {pid!r}, "
                f"class returns {plugin.plugin_id!r}"
            )
        return plugin

    return _load


def clone_path(pid: str) -> Path:
    """Where an index-clone plugin's files live (for logging / policy)."""
    return storage.plugin_clone_dir(pid)


#: Discovery order == precedence. An installed clone claiming a plugin_id wins
#: over the in-tree entry point of the same id (pre-existing behavior); with
#: deferred loading the loser is now skipped *before* its module is imported.
DEFAULT_ORIGINS: tuple[PluginOrigin, ...] = (
    IndexCloneOrigin(),
    EntryPointOrigin(),
    ComposedEntryPointOrigin(),
)
