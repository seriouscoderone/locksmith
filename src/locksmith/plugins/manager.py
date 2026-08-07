# -*- encoding: utf-8 -*-
"""
locksmith.plugins.manager module

Plugin lifecycle dispatch and state tracking.

Discovery itself is delegated to two collaborators (see
``docs/superpowers/specs/2026-07-25-plugin-origin-strategy-design.md``):

- ``origins`` — WHERE a plugin comes from. Each ``PluginOrigin`` yields
  *unimported* ``Candidate`` objects: the installed-clone index
  (``~/.locksmith/plugins/index.json``), the default-on in-tree entry-point
  group, and the brand-composed entry-point group. Registry order is
  precedence, so an installed clone still wins over an in-tree plugin of the
  same id.
- ``activation_policy`` — WHETHER it loads: an ordered veto chain (exclude
  list, HOA peel, brand composition, compatibility, files-present). Policy is
  evaluated on a candidate's identity BEFORE its module is imported.

``discover()`` then calls ``initialize(app)`` on each loaded plugin (any
exception marks it Failed and removes it from the loaded set).

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
from locksmith.plugins import activation_policy, origins, storage
from locksmith.plugins.base import (
    AccountProviderPlugin,
    AppPlugin,
    PluginCore,
    VaultPlugin,
)
from locksmith.plugins.credential_gate import RequiredCredential, gate_satisfied
from locksmith.plugins.origins import Candidate, PluginOrigin
from locksmith.plugins.role_activation import RevealBundledSurface, RoleActivationStrategy

if TYPE_CHECKING:
    from locksmith.ui.vault.menu import VaultNavMenu
    from locksmith.ui.vault.page import VaultPage

logger = help.ogler.getLogger(__name__)

# Re-exported for callers/tests that referenced these here before discovery was
# extracted into `origins` / `activation_policy`.
ENTRY_POINT_GROUP = origins.ENTRY_POINT_GROUP
COMPOSED_ENTRY_POINT_GROUP = origins.COMPOSED_ENTRY_POINT_GROUP
HOA_PEELED_PLUGIN_IDS = activation_policy.HOA_PEELED_PLUGIN_IDS

# NOTE: the former BUNDLED_ONLY_PLUGIN_IDS frozenset is gone. Brand-composed
# plugins are now identified by the entry-point GROUP they are declared in
# (`locksmith.plugins.composed`), which is readable before import and needs no
# framework-level id list — see origins.COMPOSED_ENTRY_POINT_GROUP and the
# design doc's "Retiring BUNDLED_ONLY_PLUGIN_IDS — correctly".


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

    def __init__(self, app: Any, *, keri_base: Path,
                 plugin_origins: tuple[PluginOrigin, ...] | None = None):
        self._app = app
        self._keri_base = Path(keri_base)
        # Injectable so a test (or a future deployment) can add an origin
        # without touching discovery. Order == precedence.
        self._origins: tuple[PluginOrigin, ...] = (
            plugin_origins if plugin_origins is not None
            else origins.DEFAULT_ORIGINS
        )
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
        """Walk each origin in precedence order, apply the activation policy to
        every candidate, and import only the survivors.

        Policy is decided from a candidate's identity BEFORE its module is
        imported (see ``activation_policy`` and defect D1 in
        ``docs/superpowers/specs/2026-07-25-plugin-origin-strategy-design.md``);
        previously an excluded or superseded plugin was imported and constructed
        first and rejected afterwards.
        """
        excluded = set(
            storage.read_enable_list(self._keri_base).get("excluded", [])
        )
        # brand() resolved HERE (not inside the rules) so the policy stays pure
        # and `manager.brand` remains the one patch point tests already use.
        rules = activation_policy.default_rules(excluded, brand())
        for origin in self._origins:
            for candidate in origin.candidates():
                self._consider(candidate, origin, rules)
        self._call_initialize_on_all()

    #: Skip reasons recorded only in the log — the pre-change code returned
    #: before building any PluginState for these, so the Plugins page never
    #: listed a peeled/uncomposed plugin. Preserved deliberately.
    _LOG_ONLY_REASONS = frozenset({"hoa_peel", "not_bundled"})

    def _consider(self, candidate: Candidate, origin: Any,
                  rules: tuple[Any, ...]) -> None:
        pid = candidate.plugin_id
        if pid in self._states or pid in self._plugins:
            # An earlier origin already claimed this id (index wins over
            # in-tree). Skipped before import, unlike the pre-change code.
            return

        reason = activation_policy.first_veto(candidate, rules)
        if reason is not None:
            self._record_skip(candidate, reason)
            return

        state = self._new_state(candidate)
        try:
            plugin = candidate.load()
        except Exception as e:  # noqa: BLE001
            if candidate.in_tree:
                # Matches the pre-change entry-point path: log the failure and
                # leave no PluginState behind.
                logger.exception("plugin.entry_point.load_failed name=%s", pid)
                return
            state.status = "failed"
            state.error = self._format_error(e)
            self._states[pid] = state
            logger.exception("plugin.load_failed plugin_id=%s", pid)
            return

        self._plugins[pid] = plugin
        self._states[pid] = state
        if origin.log_source == "clone":
            logger.info("plugin.loaded plugin_id=%s source=clone path=%s",
                        pid, origins.clone_path(pid))
        else:
            logger.info("plugin.loaded plugin_id=%s source=%s",
                        pid, origin.log_source)

    @staticmethod
    def _new_state(candidate: Candidate) -> PluginState:
        return PluginState(
            plugin_id=candidate.plugin_id,
            source=dict(candidate.source),
            manifest_snapshot=dict(candidate.manifest_snapshot),
            in_tree=candidate.in_tree,
        )

    def _record_skip(self, candidate: Candidate, reason: str) -> None:
        pid = candidate.plugin_id
        if reason == "files_missing":
            state = self._new_state(candidate)
            state.status = reason
            self._states[pid] = state
            logger.warning(
                "plugin.skipped reason=files_missing plugin_id=%s expected_at=%s",
                pid, origins.clone_path(pid),
            )
            return
        if reason not in self._LOG_ONLY_REASONS:
            state = self._new_state(candidate)
            state.status = reason
            self._states[pid] = state
        logger.info("plugin.skipped reason=%s plugin_id=%s", reason, pid)

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
                entry = plugin.get_menu_entry()
                if entry is not None:
                    nav_menu.register_plugin_section(
                        pid, entry, plugin.get_menu_section(),
                    )
            except Exception:
                logger.exception("plugin.vault_ui.register_failed plugin_id=%s", pid)

        for pid, plugin in self._plugins.items():
            if not isinstance(plugin, VaultPlugin):
                continue
            try:
                plugin.on_vault_ui_ready(vault_page)
            except Exception:
                logger.exception("plugin.vault_ui_ready_failed plugin_id=%s", pid)

    def apply_toolbar_entries(self, toolbar, window) -> None:
        """Fan plugin toolbar contributions into the top toolbar (HOA #4).

        Per-plugin failures are isolated: one broken contributor never
        blocks the rest (same posture as entry-point discovery).
        """
        for pid, plugin in self._plugins.items():
            try:
                for action_id, widget, section in plugin.get_toolbar_entries(window):
                    toolbar.add_action(f"{pid}.{action_id}", widget,
                                       section=section)
            except Exception:
                logger.exception("plugin.toolbar_entries_failed plugin_id=%s", pid)

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
            # Resolve the gate against the ECOSYSTEM before evaluating it. A
            # plugin's declared issuer_aids are a fallback, not the authority:
            # the trust root belongs to whoever deployed this framework, and
            # lives in their EGF. Resolving here rather than at plugin
            # construction means a brand swap or an EGF update is picked up
            # without rebuilding the plugin.
            req = self._resolved_gate(plugin.required_credential)
            satisfied = gate_satisfied(held, req)
            active = plugin.plugin_id in self._active_roles
            if satisfied and not active:
                cred = self._matching_credential(held, req)
                try:
                    self._activation_strategy.activate(plugin, cred, host)
                except Exception:                      # a surface defect must not wedge the gate loop
                    logger.exception(
                        "plugin.role_gate.activate_failed id=%s", plugin.plugin_id,
                    )
                else:
                    self._active_roles.add(plugin.plugin_id)
                    self.on_role_credential_activated(plugin, cred)
            elif active and not satisfied:
                try:
                    self._activation_strategy.deactivate(plugin, host)
                except Exception:                      # a surface defect must not wedge the gate loop
                    logger.exception(
                        "plugin.role_gate.deactivate_failed id=%s", plugin.plugin_id,
                    )
                else:
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
        # ACCEPTED LIMITATION (spec 2026-07-19 §8, edge-revocation bound):
        # chain_verified is SAVE-TIME (reger.saved membership, pinned once by
        # Verifier.saveCredential after the whole chain verified). Revoking a
        # chained EDGE TARGET later (e.g. the carrier's own self-issued
        # application that a license's NI2I edge points at) does NOT flip this
        # back to False, so it does not, on its own, deactivate the gate. This
        # is accepted: the edge target is self-issued (self-inflicted/unusual);
        # the realistic revocation (the DOI revokes the license itself) IS
        # observed live via the TEL rev on the license's own registry. Full-
        # chain live re-verification is deferred to the watcher era. Pinned by
        # tests/integration/test_carrier_gate_e2e.py::
        # test_revoking_application_edge_target_leaves_gate_satisfied.
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

    def _resolved_gate(self, req: RequiredCredential) -> RequiredCredential:
        """`req` with schema and trusted issuers taken from the active EGF.

        Falls back to the plugin's own literals whenever the ecosystem cannot
        be read or does not describe the credential -- never widening the gate,
        only re-pointing it at the deployment's real authority.
        """
        from locksmith.plugins.credential_gate import resolve_from_egf

        egf_doc = getattr(self, "_egf_doc", None)
        if egf_doc is None:
            try:
                from locksmith.core.branding import brand
                from locksmith.core.egf_seeding import make_hoa_resolver

                resolved = make_hoa_resolver(brand())
                egf_doc = resolved[1] if resolved else None
            except Exception:                    # noqa: BLE001
                egf_doc = None
            self._egf_doc = egf_doc              # resolve once per manager
        if egf_doc is None:
            return req
        try:
            from locksmith.core.branding import brand
            phases = brand().egf_accept_phases
        except Exception:                        # noqa: BLE001
            phases = ("production",)
        return resolve_from_egf(req, egf_doc, accept_phases=phases)

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

    def recheck_gates(self) -> None:
        """Re-evaluate role gates against the currently-open vault, reading
        live TEL state. The channel-blind live floor: a revocation delivered by
        ANY channel (peer push, mailbox, manual) is caught on the next call,
        since _held_credentials re-reads vcState each time. No-op if no vault."""
        if getattr(self, "_current_vault", None) is not None:
            self.reevaluate_role_gates(self._current_vault)

    def _repoll_after_admit(self, credential_said: str,
                            attempts: int = 10, interval_ms: int = 500) -> None:
        """Bounded re-poll for the full-chain-lands-late window (spec
        Sec 9.1): AdmitDoer awaits only the TOP-LEVEL ACDC in
        reger.saved, but the gate's chain_verified needs the whole
        chain. Re-evaluate on a timer until the matching gate flips or
        the budget is spent; a final miss logs loudly (vault reopen
        remains the recovery).

        Vault-pinned: the vault is captured at scheduling time; a tick aborts
        if ``self._current_vault`` is no longer that vault, so a user
        switching vaults mid-window never triggers cross-vault gate
        bookkeeping."""
        if not credential_said or self._current_vault is None:
            return
        vault = self._current_vault
        creder = vault.rgy.reger.creds.get(keys=(credential_said,))
        if creder is None:
            return
        pending = [p for p in self._gated_plugins()
                   if p.required_credential.schema_said == creder.schema
                   and p.plugin_id not in self._active_roles]
        if not pending:
            return

        remaining = {"n": attempts}

        def _tick() -> None:
            if self._current_vault is not vault:
                return  # vault switched/closed mid-window — abandon this chain
            self.reevaluate_role_gates(vault)
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

        # Symmetric teardown of what on_vault_opened set up: disconnect the
        # MANAGER's own doer_event slot (_on_doer_event) and forget the
        # current vault, so a re-open-same-vault pattern can't accumulate
        # connections on THIS slot or leave the manager evaluating gates
        # against a stale vault. Scope note: this says nothing about the
        # shell plugin's own per-vault-open connections (refresh/
        # on_doer_event/notifications refresh wired in HoaShellPlugin.
        # on_vault_opened, locksmith.plugins.hoa_shell.plugin) — those are
        # a separate teardown concern, not handled here. Idempotent
        # — a never-connected slot or a vault that was never current must not
        # raise.
        signals = getattr(vault, "signals", None)
        if signals is not None:
            try:
                signals.doer_event.disconnect(self._on_doer_event)
            except (TypeError, RuntimeError):
                pass  # slot was never connected (or already gone)
        if getattr(self, "_current_vault", None) is vault:
            self._current_vault = None

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
