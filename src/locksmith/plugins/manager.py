# -*- encoding: utf-8 -*-
"""
locksmith.plugins.manager module

Plugin discovery, lifecycle dispatch, and state tracking.

Discovery order:
1. Walk ``~/.locksmith/plugins/index.json``. For each entry:
   - skip if in this wallet's exclude list
   - skip if requires_locksmith is not satisfied (mark Incompatible)
   - skip if clone dir is missing (mark Files-Missing)
   - else add the clone to sys.path, import the entry_point, instantiate
2. Walk Python entry-points registered under ``locksmith.plugins`` for
   in-tree plugins (kerifoundation today). Same exclude check applies.
3. Call ``initialize(app)`` on each loaded plugin (any exception marks
   it Failed and removes it from the loaded set).

Dispatch:
- App lifecycle hooks (on_app_started, on_app_stopping, app shortcuts,
  app services) only run on plugins that are instances of AppPlugin.
- Vault hooks only run on plugins that are instances of VaultPlugin.
- A plugin that inherits both gets both code paths.
"""
from __future__ import annotations

import importlib
import importlib.metadata
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, TYPE_CHECKING

from keri import help

from locksmith.plugins import storage
from locksmith.plugins.base import (
    AccountProviderPlugin,
    AppPlugin,
    PluginCore,
    VaultPlugin,
)

if TYPE_CHECKING:
    from locksmith.ui.vault.menu import VaultNavMenu
    from locksmith.ui.vault.page import VaultPage

logger = help.ogler.getLogger(__name__)

ENTRY_POINT_GROUP = "locksmith.plugins"


@dataclass
class PluginState:
    plugin_id: str
    status: str = "loaded"   # loaded | excluded | incompatible | files_missing | failed
    error: str = ""
    source: dict[str, Any] = field(default_factory=dict)
    manifest_snapshot: dict[str, Any] = field(default_factory=dict)
    in_tree: bool = False


class PluginManager:
    """Discovers, initializes, and manages Locksmith plugins."""

    def __init__(self, app: Any, *, keri_base: Path):
        self._app = app
        self._keri_base = Path(keri_base)
        self._plugins: dict[str, PluginCore] = {}
        self._states: dict[str, PluginState] = {}
        self._started_services: dict[str, list[Any]] = {}

    # ------------------- discovery ---------------------------------

    def discover(self) -> None:
        excluded = set(
            storage.read_enable_list(self._keri_base).get("excluded", [])
        )
        self._discover_from_index(excluded)
        self._discover_from_entry_points(excluded)
        self._call_initialize_on_all()

    def _discover_from_index(self, excluded: set[str]) -> None:
        idx = storage.read_index()
        for record in idx.get("plugins", []):
            pid = record.get("plugin_id")
            if not pid:
                continue
            self._states[pid] = PluginState(
                plugin_id=pid,
                source=record.get("source", {}),
                manifest_snapshot=record.get("manifest_snapshot", {}),
            )
            if pid in excluded:
                self._states[pid].status = "excluded"
                logger.info("plugin.skipped reason=excluded plugin_id=%s", pid)
                continue
            if not self._compat_ok(record):
                self._states[pid].status = "incompatible"
                logger.info("plugin.skipped reason=incompatible plugin_id=%s", pid)
                continue
            clone = storage.plugin_clone_dir(pid)
            if not clone.exists():
                self._states[pid].status = "files_missing"
                logger.warning(
                    "plugin.skipped reason=files_missing plugin_id=%s expected_at=%s",
                    pid, clone,
                )
                continue
            try:
                self._load_from_clone(record, clone)
            except Exception as e:  # noqa: BLE001
                self._states[pid].status = "failed"
                self._states[pid].error = self._format_error(e)
                logger.exception("plugin.load_failed plugin_id=%s", pid)

    def _discover_from_entry_points(self, excluded: set[str]) -> None:
        try:
            eps = importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)
        except Exception:
            logger.exception("plugin.entry_points.discovery_failed")
            return
        for ep in eps:
            try:
                plugin_cls = ep.load()
                plugin = plugin_cls()
                pid = plugin.plugin_id
                if pid in self._states:
                    # Already loaded via index — index wins.
                    continue
                state = PluginState(plugin_id=pid, in_tree=True)
                if pid in excluded:
                    state.status = "excluded"
                    self._states[pid] = state
                    logger.info("plugin.skipped reason=excluded plugin_id=%s", pid)
                    continue
                self._plugins[pid] = plugin
                self._states[pid] = state
                logger.info("plugin.loaded plugin_id=%s source=entry_point", pid)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "plugin.entry_point.load_failed name=%s", ep.name,
                )

    def _load_from_clone(self, record: dict[str, Any], clone: Path) -> None:
        pid = record["plugin_id"]
        snap = record.get("manifest_snapshot", {})
        entry_point = snap.get("entry_point")
        if not entry_point or ":" not in entry_point:
            raise RuntimeError(f"missing or malformed entry_point in record: {entry_point!r}")

        module_name, _, class_name = entry_point.partition(":")

        clone_str = str(clone)
        if clone_str not in sys.path:
            sys.path.insert(0, clone_str)

        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)
        plugin = cls()
        if plugin.plugin_id != pid:
            raise RuntimeError(
                f"plugin_id mismatch: manifest says {pid!r}, "
                f"class returns {plugin.plugin_id!r}"
            )
        self._plugins[pid] = plugin
        logger.info("plugin.loaded plugin_id=%s source=clone path=%s", pid, clone)

    def _call_initialize_on_all(self) -> None:
        for pid in list(self._plugins.keys()):
            plugin = self._plugins[pid]
            try:
                plugin.initialize(self._app)
            except Exception as e:  # noqa: BLE001
                self._states[pid].status = "failed"
                self._states[pid].error = self._format_error(e)
                del self._plugins[pid]
                logger.exception("plugin.initialize_failed plugin_id=%s", pid)

    @staticmethod
    def _format_error(e: Exception) -> str:
        return "".join(traceback.format_exception_only(type(e), e)).strip()

    def _compat_ok(self, record: dict[str, Any]) -> bool:
        """Apply the requires_locksmith gate. Stage 1 always passes; later tightens."""
        return True

    # ------------------- public read API ---------------------------

    def loaded_ids(self) -> list[str]:
        return list(self._plugins.keys())

    def excluded_ids(self) -> list[str]:
        return [s.plugin_id for s in self._states.values() if s.status == "excluded"]

    def get_plugin(self, plugin_id: str) -> PluginCore | None:
        return self._plugins.get(plugin_id)

    def get_state(self, plugin_id: str) -> PluginState | None:
        return self._states.get(plugin_id)

    def all_states(self) -> list[PluginState]:
        return list(self._states.values())

    # ------------------- App-lifecycle dispatch --------------------

    def on_app_started(self, window: Any) -> None:
        for pid, plugin in self._plugins.items():
            if not isinstance(plugin, AppPlugin):
                continue
            try:
                plugin.on_app_started(self._app, window)
            except Exception:
                self._states[pid].status = "failed"
                self._states[pid].error = self._format_error_from_current()
                logger.exception("plugin.on_app_started_failed plugin_id=%s", pid)
                continue
            services = []
            for service in plugin.get_app_services():
                try:
                    service.start()
                    services.append(service)
                except Exception:
                    logger.exception(
                        "plugin.service.start_failed plugin_id=%s service=%s",
                        pid, type(service).__name__,
                    )
            self._started_services[pid] = services

    def on_app_stopping(self) -> None:
        for pid in reversed(list(self._started_services.keys())):
            for service in reversed(self._started_services.get(pid, [])):
                try:
                    service.stop()
                except Exception:
                    logger.exception(
                        "plugin.service.stop_failed plugin_id=%s service=%s",
                        pid, type(service).__name__,
                    )
        for pid, plugin in self._plugins.items():
            if not isinstance(plugin, AppPlugin):
                continue
            try:
                plugin.on_app_stopping(self._app)
            except Exception:
                logger.exception("plugin.on_app_stopping_failed plugin_id=%s", pid)

    # ------------------- Vault-lifecycle dispatch ------------------

    def discover_and_initialize_vault_ui(
        self, vault_page: "VaultPage", nav_menu: "VaultNavMenu",
    ) -> None:
        """Register vault-plugin pages and menus into the VaultPage."""
        for pid, plugin in self._plugins.items():
            if not isinstance(plugin, VaultPlugin):
                continue
            try:
                for key, widget in plugin.get_pages().items():
                    vault_page.register_page(key, widget)
                nav_menu.register_plugin_section(
                    pid, plugin.get_menu_entry(), plugin.get_menu_section(),
                )
            except Exception:
                logger.exception("plugin.vault_ui.register_failed plugin_id=%s", pid)

    def on_vault_opened(self, vault: Any) -> None:
        for pid, plugin in self._plugins.items():
            if not isinstance(plugin, VaultPlugin):
                continue
            try:
                plugin.on_vault_opened(vault)
                vault.doers.extend(plugin.get_doers())
            except Exception:
                logger.exception("plugin.on_vault_opened_failed plugin_id=%s", pid)

    def prepare_vault_deletion(self, vault: Any) -> None:
        for pid, plugin in self._plugins.items():
            if not isinstance(plugin, VaultPlugin):
                continue
            try:
                plugin.prepare_vault_deletion(vault)
            except Exception:
                logger.exception("plugin.prepare_vault_deletion_failed plugin_id=%s", pid)
                raise

    def on_vault_closed(self, vault: Any, *, clear: bool = False) -> None:
        for pid, plugin in self._plugins.items():
            if not isinstance(plugin, VaultPlugin):
                continue
            try:
                plugin.on_vault_closed(vault, clear=clear)
            except Exception:
                logger.exception("plugin.on_vault_closed_failed plugin_id=%s", pid)

    def is_setup_complete(self, plugin_id: str, vault: Any) -> bool:
        plugin = self._plugins.get(plugin_id)
        if plugin and isinstance(plugin, AccountProviderPlugin):
            return plugin.is_setup_complete(vault)
        return True

    async def after_identifier_authenticated(self, vault: Any, hab: Any) -> None:
        for pid, plugin in self._plugins.items():
            if not isinstance(plugin, VaultPlugin):
                continue
            try:
                await plugin.after_identifier_authenticated(vault, hab)
            except Exception:
                logger.exception(
                    "plugin.after_identifier_authenticated_failed plugin_id=%s", pid,
                )

    def get_witness_batches(self, vault: Any, hab_pre: str) -> Any | None:
        merged = []
        seen = set()
        for plugin in self._plugins.values():
            if not isinstance(plugin, VaultPlugin):
                continue
            result = plugin.get_witness_batches(vault, hab_pre)
            if result is None:
                continue
            for batch in getattr(result, "batches", []) or []:
                if not isinstance(batch, (list, tuple)) or not batch:
                    continue
                key = tuple(sorted(str(eid) for eid in batch))
                if key in seen:
                    continue
                seen.add(key)
                merged.append(list(batch))
        if not merged:
            return None
        return SimpleNamespace(batches=merged)

    def update_witness_state_after_rotation(self, vault: Any, wit_eid: str) -> None:
        for plugin in self._plugins.values():
            if isinstance(plugin, VaultPlugin):
                plugin.update_witness_state(vault, wit_eid)

    def update_witness_state_after_auth(self, vault: Any, wit_eid: str) -> None:
        for plugin in self._plugins.values():
            if isinstance(plugin, VaultPlugin):
                plugin.update_witness_state_after_auth(vault, wit_eid)

    # ------------------- legacy shim (removed in Task 13) ----------

    def discover_and_initialize(
        self, vault_page: "VaultPage", nav_menu: "VaultNavMenu",
    ) -> None:
        """Legacy entrypoint kept for ui/window.py compatibility until Task 13."""
        self.discover()
        self.discover_and_initialize_vault_ui(vault_page, nav_menu)

    # ------------------- internal helpers --------------------------

    def _format_error_from_current(self) -> str:
        import sys as _sys
        exc = _sys.exc_info()[1]
        return self._format_error(exc) if exc else ""
