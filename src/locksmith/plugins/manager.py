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
from PySide6.QtCore import QTimer

from locksmith.core.branding import brand
from locksmith.plugins import storage
from locksmith.plugins.base import (
    AccountProviderPlugin,
    AppPlugin,
    PluginCore,
    VaultPlugin,
)
from locksmith.plugins.credential_gate import RequiredCredential, gate_satisfied
from locksmith.plugins.role_activation import RevealBundledSurface, RoleActivationStrategy

if TYPE_CHECKING:
    from locksmith.ui.vault.menu import VaultNavMenu
    from locksmith.ui.vault.page import VaultPage

logger = help.ogler.getLogger(__name__)

ENTRY_POINT_GROUP = "locksmith.plugins"

# In-tree entry-point plugin excluded from HOA (peel_core_pages) brands at
# runtime. pyproject.toml's entry-point declaration is shared across brands
# and is NOT brand-gated — deleting it there broke the default Locksmith
# build (see backlog/2026-07-09-kerifoundation-plugin-brand-leak-and-onboarding-crash.md).
# The exclusion instead happens here, filtered by plugin_id before the
# plugin class is even loaded/instantiated.
HOA_PEELED_PLUGIN_IDS = frozenset({"kerifoundation"})

# In-tree entry-point plugin that is the mirror-image case: an
# insurance-specific (HOA) demo role-plugin that must NOT load for the
# default Locksmith build. pyproject.toml's entry-point declaration is
# shared across brands (same constraint as HOA_PEELED_PLUGIN_IDS above), so
# the gating happens here too, filtered by plugin_id before the plugin
# class is loaded/instantiated — skipped when the active brand does NOT
# peel core pages (i.e. it loads only under peel/HOA brands).
HOA_ONLY_PLUGIN_IDS = frozenset({"carrier"})


@dataclass
class PluginState:
    plugin_id: str
    status: str = "loaded"   # loaded | excluded | incompatible | files_missing | failed
    error: str = ""
    source: dict[str, Any] = field(default_factory=dict)
    manifest_snapshot: dict[str, Any] = field(default_factory=dict)
    in_tree: bool = False


@dataclass(frozen=True)
class HeldCredential:
    """Gate-shaped view of one held ACDC, projected from the vault's real
    credential store (``core/credentialing`` / keripy ``reger``) into exactly
    the attributes ``credential_gate.gate_satisfied`` reads. See
    ``PluginManager._held_credentials`` for the precise derivation."""

    schema_said: str
    issuer_aid: str
    state: str            # active | revoked | unknown (from the TEL Tever vcState)
    chain_verified: bool  # True iff present in the reger `saved` (fully-verified) index
    said: str             # the ACDC's own SAID — per-instance identity for UI detail views; the gate predicate does not read it
    revoked_at: str = ""  # iso8601 of the latest TEL event when state=="revoked" (from vcState.dt); "" otherwise


class PluginManager:
    """Discovers, initializes, and manages Locksmith plugins."""

    def __init__(self, app: Any, *, keri_base: Path):
        self._app = app
        self._keri_base = Path(keri_base)
        self._plugins: dict[str, PluginCore] = {}
        self._states: dict[str, PluginState] = {}
        self._started_services: dict[str, list[Any]] = {}
        # Role-activation (credential-gated) state. The strategy turns a
        # satisfied gate into a revealed surface; _active_roles tracks which
        # gated plugin_ids are currently revealed so reevaluate_role_gates can
        # fire activate/deactivate only on transitions. _surface_host is the
        # VaultPage/HoaVaultPage, captured at vault-UI init.
        self._activation_strategy: RoleActivationStrategy = RevealBundledSurface()
        self._active_roles: set[str] = set()
        self._surface_host: Any | None = None
        # The vault most recently opened, so a live credential-changed
        # signal (see _on_credential_changed) knows what to re-evaluate
        # gates against without needing the caller to pass it through.
        self._current_vault: Any | None = None

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
        peel_core_pages = brand().peel_core_pages
        for ep in eps:
            if peel_core_pages and ep.name in HOA_PEELED_PLUGIN_IDS:
                logger.info(
                    "plugin.skipped reason=hoa_peel plugin_id=%s", ep.name,
                )
                continue
            if not peel_core_pages and ep.name in HOA_ONLY_PLUGIN_IDS:
                logger.info(
                    "plugin.skipped reason=hoa_only plugin_id=%s", ep.name,
                )
                continue
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

        # Support both flat-layout (<clone>/<pkg>/) and src-layout
        # (<clone>/src/<pkg>/) plugins. Add src/ first if present so it
        # takes priority; clone-root stays as a fallback for flat-layout.
        src_dir = clone / "src"
        for candidate in (src_dir, clone) if src_dir.is_dir() else (clone,):
            cand_str = str(candidate)
            if cand_str not in sys.path:
                sys.path.insert(0, cand_str)

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
        """Register vault-plugin pages and menus into the VaultPage.

        Ungated plugins register exactly as before. Credential-gated plugins
        (``required_credential is not None``) are NOT auto-registered here —
        their surface is withheld until their gate is satisfied and
        ``reevaluate_role_gates`` reveals it via the activation strategy. The
        surface host is captured here so gate re-evaluation can target it.
        """
        self._surface_host = vault_page
        for pid, plugin in self._plugins.items():
            if not isinstance(plugin, VaultPlugin):
                continue
            if getattr(plugin, "required_credential", None) is not None:
                logger.info(
                    "plugin.vault_ui.gated_deferred plugin_id=%s", pid,
                )
                continue
            try:
                for key, widget in plugin.get_pages().items():
                    vault_page.register_page(key, widget)
                nav_menu.register_plugin_section(
                    pid, plugin.get_menu_entry(), plugin.get_menu_section(),
                )
            except Exception:
                logger.exception("plugin.vault_ui.register_failed plugin_id=%s", pid)

    # ------------------- Role-activation (credential gate) ---------

    def reevaluate_role_gates(self, vault: Any) -> None:
        """Recompute every gated plugin's gate against the vault's held
        credentials and drive the activation strategy on state transitions.

        On unsatisfied->satisfied: activate the plugin's surface and fire the
        ``on_role_credential_activated`` seam. On satisfied->unsatisfied:
        deactivate. Steady states are no-ops. This is the ONLY path that
        registers a gated plugin's surface; the live triggers that call it are
        wired in a later task.
        """
        host = self._surface_host
        held = self._held_credentials(vault)
        for plugin in self._gated_plugins():
            req = plugin.required_credential
            satisfied = gate_satisfied(held, req)
            active = plugin.plugin_id in self._active_roles
            if satisfied and not active:
                cred = self._matching_credential(held, req)
                self._activation_strategy.activate(plugin, cred, host)
                self._active_roles.add(plugin.plugin_id)
                self.on_role_credential_activated(plugin, cred)
            elif active and not satisfied:
                self._activation_strategy.deactivate(plugin, host)
                self._active_roles.discard(plugin.plugin_id)
                signals = getattr(vault, "signals", None)
                if signals is not None:
                    signals.emit_doer_event(
                        "RoleGate", "role_revoked",
                        {"plugin_id": plugin.plugin_id, "schema_said": req.schema_said},
                    )

    def on_role_credential_activated(self, plugin: Any, credential: Any) -> None:
        """Named seam fired once when a role credential activates a plugin.

        POC no-op beyond the surface activation already performed by the
        strategy; future strategies/consumers hook here (analytics, agent
        provisioning, notifications, etc.)."""

    def _gated_plugins(self) -> list[PluginCore]:
        """Loaded plugins that declare a credential gate."""
        return [
            p for p in self._plugins.values()
            if getattr(p, "required_credential", None) is not None
        ]

    def _held_credentials(self, vault: Any) -> list[HeldCredential]:
        """Project the vault's real held ACDCs into gate-shaped views.

        Enumeration mirrors the received-credentials list page: for each local
        hab, the reger subject index (``reger.subjs``) yields the SAIDs of
        credentials held (issued *to*) that identifier. For each SAID we read:

        - ``schema_said`` / ``issuer_aid`` from the stored ACDC
          (``reger.creds`` -> ``creder.schema`` / ``creder.issuer``);
        - ``state`` from the registry Tever TEL status
          (``reger.tevers[regid].vcState(said).et``): iss/bis -> "active",
          rev/brv -> "revoked", otherwise "unknown" (e.g. the registry Tever is
          not present locally);
        - ``chain_verified`` from the reger ``saved`` index. keripy only pins
          ``saved`` in ``Verifier.saveCredential``, which runs *after* the full
          chain (all required edges, e.g. a carrier_license's NI2I edge to its
          application ACDC), schema, and registry all verify. A credential
          still sitting in a missing-chain/registry/schema escrow (mce/mre/mse)
          is never in ``saved`` (and, in fact, never indexed in ``subjs``), so
          it maps to ``chain_verified=False`` — we never treat mere storage as
          verification.
        """
        reger = vault.rgy.reger
        habs = vault.hby.habs
        views: list[HeldCredential] = []
        seen: set[str] = set()
        for pre in habs.keys():
            for saider in reger.subjs.get(keys=(pre,)):
                said = saider.qb64
                if said in seen:
                    continue
                seen.add(said)
                views.append(self._held_credential_view(reger, said))
        return views

    @staticmethod
    def _held_credential_view(reger: Any, said: str) -> HeldCredential:
        creder = reger.creds.get(keys=(said,))
        chain_verified = reger.saved.get(keys=(said,)) is not None
        state = "unknown"
        revoked_at = ""
        try:
            status = reger.tevers[creder.regid].vcState(said)
            et = getattr(status, "et", None)
            if et in ("iss", "bis"):
                state = "active"
            elif et in ("rev", "brv"):
                state = "revoked"
                revoked_at = getattr(status, "dt", "") or ""
        except Exception:  # noqa: BLE001 — missing/partial TEL => state unknown
            logger.warning(
                "role_gate.vcstate_unavailable said=%s (state=unknown)", said,
            )
        return HeldCredential(
            schema_said=creder.schema,
            issuer_aid=creder.issuer,
            state=state,
            chain_verified=chain_verified,
            said=said,
            revoked_at=revoked_at,
        )

    @staticmethod
    def _matching_credential(
        held: list[HeldCredential], req: RequiredCredential,
    ) -> HeldCredential | None:
        """The first held credential that satisfies ``req`` (schema, trusted
        issuer, required TEL state, fully chain-verified), or None."""
        for c in held:
            if (c.schema_said == req.schema_said
                    and c.issuer_aid in req.issuer_aids
                    and c.state == req.required_state
                    and c.chain_verified):
                return c
        return None

    def on_vault_opened(self, vault: Any) -> None:
        for pid, plugin in self._plugins.items():
            if not isinstance(plugin, VaultPlugin):
                continue
            try:
                plugin.on_vault_opened(vault)
                vault.doers.extend(plugin.get_doers())
            except Exception:
                logger.exception("plugin.on_vault_opened_failed plugin_id=%s", pid)

        # Trigger (a): evaluate role gates against whatever credentials this
        # vault already holds. Catches credentials admitted in a prior
        # session (no re-auth needed on relaunch). Cheap no-op when there are
        # no gated plugins, so the default (ungated) build is unaffected.
        self._current_vault = vault
        signals = getattr(vault, "signals", None)
        if signals is not None:
            # Trigger (b): live re-evaluation on IPEX admit, with no restart.
            # ``vault.signals`` is the same DoerSignalBridge instance AdmitDoer
            # is handed (see ui/vault/credentials/received/accept_grant.py),
            # and "AdmitDoer"/"admit_complete" is the same event the
            # received-credentials list page already refreshes on (see
            # ui/vault/credentials/received/list.py:_on_doer_event). Piggy-
            # backing on it means no new signal/emit site is needed.
            signals.doer_event.connect(self._on_doer_event)
        self.reevaluate_role_gates(vault)

    def _on_doer_event(self, doer_name: str, event_type: str, data: dict) -> None:
        """Filter the vault's general doer-event bus down to a successful
        IPEX admit landing in the credential store, and re-evaluate role
        gates live (no restart)."""
        if doer_name == "AdmitDoer" and event_type == "admit_complete" and data.get("success"):
            self._on_credential_changed()
            self._repoll_after_admit(data.get("credential_said", ""))

    def _on_credential_changed(self) -> None:
        """Re-evaluate role gates against the currently-open vault.

        A no-op if no vault is current (e.g. called before any vault has
        been opened)."""
        if getattr(self, "_current_vault", None) is not None:
            self.reevaluate_role_gates(self._current_vault)

    def _repoll_after_admit(self, credential_said: str,
                            attempts: int = 10, interval_ms: int = 500) -> None:
        """Bounded re-poll for the full-chain-lands-late window (spec
        Sec 9.1): AdmitDoer awaits only the TOP-LEVEL ACDC in
        reger.saved, but the gate's chain_verified needs the whole
        chain. Re-evaluate on a timer until the matching gate flips or
        the budget is spent; a final miss logs loudly (vault reopen
        remains the recovery)."""
        if not credential_said or self._current_vault is None:
            return
        creder = self._current_vault.rgy.reger.creds.get(keys=(credential_said,))
        if creder is None:
            return
        pending = [p for p in self._gated_plugins()
                   if p.required_credential.schema_said == creder.schema
                   and p.plugin_id not in self._active_roles]
        if not pending:
            return

        remaining = {"n": attempts}

        def _tick() -> None:
            self.reevaluate_role_gates(self._current_vault)
            still = [p for p in pending if p.plugin_id not in self._active_roles]
            remaining["n"] -= 1
            if not still:
                return
            if remaining["n"] <= 0:
                logger.warning(
                    f"gate.repoll_exhausted credential={credential_said}")
                return
            QTimer.singleShot(interval_ms, _tick)

        _tick()

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

    def has_witness_auth_for_any(
        self, vault: Any, hab_pre: str, wit_eids: list[str],
    ) -> bool:
        """Return True if any installed plugin reports holding auth
        material (e.g. a TOTP seed) for at least one of ``wit_eids``
        under controller ``hab_pre``. Used by the rotation flow to
        decide whether a witness-auth fallback modal would help —
        purely-KERI witnesses produce ``False`` here and the wallet
        skips the modal entirely.
        """
        for plugin in self._plugins.values():
            if not isinstance(plugin, VaultPlugin):
                continue
            for wit in wit_eids:
                try:
                    if plugin.has_witness_auth_material(vault, hab_pre, wit):
                        return True
                except Exception as exc:  # noqa: BLE001
                    # A misbehaving plugin must never break the core
                    # rotation flow. Treat raise as "no material here".
                    logger.warning(
                        f"plugin {plugin.__class__.__name__}.has_witness_auth_material "
                        f"raised, treating as False: {exc}"
                    )
        return False

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
