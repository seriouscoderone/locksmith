# -*- encoding: utf-8 -*-
"""HoaShellPlugin: the generic (domain-neutral) HOA onboarding shell as a
bundled plugin — loading matrix + wiring surface (HOA #4).

The tests below the static/gating section (module-level held_provider,
source-inspection gate ordering, on_vault_opened deferred-refresh/
idempotency, and the _bring_up_direct_transport retry chain) are MOVED and
ADAPTED, one-for-one with their assertions preserved, from
``tests/ui/onboarding/test_request_flow.py``'s former "Window wiring" section
-- that logic now lives in this plugin (Task 7, HOA #4 behavior-preserving
move), so the tests that exercised it move with it.
"""
import inspect
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QWidget

from locksmith.plugins.hoa_shell.plugin import HoaShellPlugin


class _FakeHoaVaultPage(QWidget):
    """Real (not mocked) QWidget stand-in for ``HoaVaultPage``, monkeypatched
    in for ``on_vault_ui_ready``'s ``isinstance(vault_page, HoaVaultPage)``
    gate and ``register_page``/``add_menu_entry`` calls. Must be a REAL
    ``QWidget`` -- not a ``MagicMock(spec=HoaVaultPage)`` -- for two
    independent reasons (same finding as
    ``tests/ui/onboarding/test_request_flow.py``'s precedent): (1)
    ``HoaVaultPage``'s metaclass chain (``QABCMeta``, ABC-based) trips
    ``isinstance()`` against a spec'd Mock on this Python/mock combination
    (``AttributeError: type object 'HoaVaultPage' has no attribute
    '_abc_impl'``); (2) the error path constructs a REAL
    ``OnboardingErrorPage`` (a ``QWidget``), and PySide6's ``QWidget.__init__``
    strictly type-checks its ``parent`` argument -- a ``MagicMock`` is not an
    accepted ``QWidget | None``. ``register_page``/``add_menu_entry`` are
    themselves ``MagicMock``s so call-tracking assertions still work.
    """

    def __init__(self):
        super().__init__()
        self.register_page = MagicMock(name="register_page")
        self.add_menu_entry = MagicMock(name="add_menu_entry")


def test_shell_is_ungated_and_contributes_no_static_surfaces():
    p = HoaShellPlugin()
    assert p.plugin_id == "hoa_shell"
    assert p.required_credential is None
    assert p.get_pages() == {}
    assert p.get_menu_entry() is None
    assert p.get_menu_section() == []


def test_on_vault_ui_ready_noop_for_non_onboarding_brand(qapp, monkeypatch):
    from locksmith.plugins.hoa_shell import plugin as shell_mod
    from locksmith.core.branding import Brand
    monkeypatch.setattr(shell_mod, "brand", lambda: Brand())  # onboarding off
    p = HoaShellPlugin()
    p.initialize(MagicMock())
    vault_page = MagicMock()
    p.on_vault_ui_ready(vault_page)
    vault_page.register_page.assert_not_called()


def test_on_vault_ui_ready_registers_home_and_notifications(qapp, monkeypatch):
    """Onboarding brand + resolvable EGF -> the shell registers the same two
    pages + two menu entries the window used to wire (behavior-preserving)."""
    from locksmith.plugins.hoa_shell import plugin as shell_mod
    from locksmith.core.branding import Brand
    onboarding_brand = Brand()  # dataclass is frozen: build via replace
    import dataclasses
    onboarding_brand = dataclasses.replace(
        Brand(), onboarding_enabled=True, peel_core_pages=True)
    monkeypatch.setattr(shell_mod, "brand", lambda: onboarding_brand)

    fake_resolver, fake_egf = MagicMock(), MagicMock()
    fake_egf.personas.return_value = []
    monkeypatch.setattr(shell_mod, "make_hoa_resolver",
                        lambda b: (fake_resolver, fake_egf))
    monkeypatch.setattr(shell_mod, "HoaVaultPage", _FakeHoaVaultPage)
    vault_page = _FakeHoaVaultPage()

    p = HoaShellPlugin()
    p.initialize(MagicMock())
    p.on_vault_ui_ready(vault_page)

    registered = [c.args[0] for c in vault_page.register_page.call_args_list]
    assert registered == ["home", "notifications"]
    assert p._home_page is not None and p._notifications_page is not None


def test_broken_egf_registers_error_page(qapp, monkeypatch):
    from locksmith.plugins.hoa_shell import plugin as shell_mod
    import dataclasses
    from locksmith.core.branding import Brand
    from keri_serviceaid.egf.errors import EgfDocumentError
    monkeypatch.setattr(shell_mod, "brand", lambda: dataclasses.replace(
        Brand(), onboarding_enabled=True, peel_core_pages=True))

    def _boom(b):
        raise EgfDocumentError("broken bundle")
    monkeypatch.setattr(shell_mod, "make_hoa_resolver", _boom)
    monkeypatch.setattr(shell_mod, "HoaVaultPage", _FakeHoaVaultPage)
    vault_page = _FakeHoaVaultPage()

    p = HoaShellPlugin()
    p.initialize(MagicMock())
    p.on_vault_ui_ready(vault_page)

    assert vault_page.register_page.call_args.args[0] == "home"
    assert p._home_page is None


# ---------------------------------------------------------------------------
# _held_credentials — module-level held_provider None-guard (moved from
# test_request_flow.py's test_onboarding_held_provider_guards_vault_none)
# ---------------------------------------------------------------------------

def test_held_credentials_guards_vault_none():
    """OnboardingHomePage.__init__ calls refresh() -> held_provider at
    on_vault_ui_ready time, BEFORE any vault is open (app.vault is None).
    The provider must return [] then -- not crash on
    PluginManager._held_credentials(None) -- and delegate to the real
    projection once a vault IS open."""
    from locksmith.plugins.hoa_shell.plugin import _held_credentials

    app = MagicMock()
    app.vault = None
    assert _held_credentials(app) == []
    app.plugin_manager._held_credentials.assert_not_called()

    vault = MagicMock(name="vault")
    app.vault = vault
    held = [object()]
    app.plugin_manager._held_credentials.return_value = held
    assert _held_credentials(app) is held
    app.plugin_manager._held_credentials.assert_called_once_with(vault)


# ---------------------------------------------------------------------------
# on_vault_ui_ready gate ordering — source-inspection (B4 pattern), moved
# from test_window_registers_onboarding_home_gated_on_enabled_and_resolver
# ---------------------------------------------------------------------------

def test_on_vault_ui_ready_registration_gated_on_enabled_and_resolver():
    """``HoaShellPlugin.on_vault_ui_ready`` must only construct/register the
    onboarding "home" page when BOTH ``brand().onboarding_enabled`` is true
    AND ``make_hoa_resolver(brand())`` resolved a non-None (resolver,
    egf_doc) pair -- a non-onboarding or non-HOA brand must never construct
    a RequestFlow/OnboardingHomePage at all. Source-inspection, not a live
    construction (mirrors the moved-from precedent)."""
    source = inspect.getsource(HoaShellPlugin.on_vault_ui_ready)

    onboarding_idx = source.index("onboarding_enabled")
    register_idx = source.index('register_page("home"')
    resolver_idx = source.index("make_hoa_resolver(")

    assert onboarding_idx < register_idx, (
        "register_page(\"home\", ...) must be gated behind an "
        "onboarding_enabled check"
    )
    assert resolver_idx < register_idx, (
        "register_page(\"home\", ...) must be gated behind a "
        "make_hoa_resolver(...) is not None check"
    )

    # Both gates must actually guard the SAME registration -- i.e. there is
    # no unconditional "if True" / early-return escape hatch between them
    # and the registration call. A cheap proxy: the registration call must
    # be the nearest "register_page" occurrence AFTER both gate keywords,
    # with no intervening top-level (unindented) statement resetting the
    # if-block. We settle for ordering + a bounded-distance check so this
    # test doesn't have to parse the AST.
    between = source[onboarding_idx:register_idx]
    assert "make_hoa_resolver(" in between


# ---------------------------------------------------------------------------
# on_vault_ui_ready — error path / success path detail, moved from
# test_wire_onboarding_registers_error_page_when_egf_broken /
# test_wire_onboarding_still_registers_home_page_on_success
# ---------------------------------------------------------------------------

def test_on_vault_ui_ready_registers_error_page_when_egf_broken(qapp, monkeypatch):
    """Hardening wave item 1 (design spec §4.5): "A persona picker over a
    broken EGF shows an error state, not an empty list." When
    ``make_hoa_resolver`` raises an ``EgfError`` subclass (a pinned EGF whose
    bundle is missing/tampered/incomplete -- e.g. ``EgfIntegrityError`` on a
    SAID mismatch), ``on_vault_ui_ready`` must NOT propagate the exception
    (which would crash vault-UI construction). Instead: neither
    ``RequestFlow`` nor ``OnboardingHomePage`` is constructed, and a minimal
    ``OnboardingErrorPage`` is registered as "home" instead."""
    from keri_serviceaid.egf.errors import EgfIntegrityError
    from locksmith.plugins.hoa_shell import plugin as shell_mod
    from locksmith.ui.onboarding.home_page import OnboardingErrorPage

    fake_brand = MagicMock()
    fake_brand.onboarding_enabled = True

    def _raise_integrity_error(_brand):
        raise EgfIntegrityError("E" + "X" * 43, "E" + "Y" * 43)

    request_flow_cls = MagicMock(name="RequestFlow")
    onboarding_home_page_cls = MagicMock(name="OnboardingHomePage")
    monkeypatch.setattr(shell_mod, "brand", lambda: fake_brand)
    monkeypatch.setattr(shell_mod, "make_hoa_resolver", _raise_integrity_error)
    monkeypatch.setattr(shell_mod, "RequestFlow", request_flow_cls)
    monkeypatch.setattr(shell_mod, "OnboardingHomePage", onboarding_home_page_cls)
    monkeypatch.setattr(shell_mod, "HoaVaultPage", _FakeHoaVaultPage)

    plugin = HoaShellPlugin()
    plugin.initialize(MagicMock())
    vault_page = _FakeHoaVaultPage()

    # Must not raise -- this is the crash vault-UI construction would
    # otherwise hit before the fix.
    plugin.on_vault_ui_ready(vault_page)

    assert plugin._request_flow is None
    assert plugin._home_page is None
    assert plugin._notifications_page is None
    request_flow_cls.assert_not_called()
    onboarding_home_page_cls.assert_not_called()

    assert len(vault_page.register_page.call_args_list) == 1
    call = vault_page.register_page.call_args_list[0]
    assert call.args[0] == "home"
    assert isinstance(call.args[1], OnboardingErrorPage)

    # No nav menu entry for a controller that was never built.
    vault_page.add_menu_entry.assert_not_called()


def test_on_vault_ui_ready_registers_home_and_notifications_success(qapp, monkeypatch):
    """Control case for the above: when ``make_hoa_resolver`` resolves
    cleanly, ``on_vault_ui_ready`` must take the normal path -- RequestFlow +
    OnboardingHomePage constructed, registered as "home", nav entry added --
    unaffected by the try/except. Task 10: the same success path also
    constructs a REAL ``HoaNotificationsPage`` (not mocked -- its ``__init__``
    does no I/O; see its own module docstring) and registers it as
    "notifications" + a second nav-menu entry, mirroring "home" exactly."""
    from locksmith.ui.hoa.notifications_page import HoaNotificationsPage
    from locksmith.plugins.hoa_shell import plugin as shell_mod

    fake_brand = MagicMock()
    fake_brand.onboarding_enabled = True

    resolver = MagicMock(name="resolver")
    egf_doc = MagicMock(name="egf_doc")
    request_flow_instance = MagicMock(name="request_flow_instance")
    onboarding_home_page_instance = MagicMock(name="onboarding_home_page_instance")
    request_flow_cls = MagicMock(name="RequestFlow", return_value=request_flow_instance)
    onboarding_home_page_cls = MagicMock(
        name="OnboardingHomePage", return_value=onboarding_home_page_instance,
    )

    monkeypatch.setattr(shell_mod, "brand", lambda: fake_brand)
    monkeypatch.setattr(
        shell_mod, "make_hoa_resolver", lambda _brand: (resolver, egf_doc),
    )
    monkeypatch.setattr(shell_mod, "RequestFlow", request_flow_cls)
    monkeypatch.setattr(shell_mod, "OnboardingHomePage", onboarding_home_page_cls)
    monkeypatch.setattr(shell_mod, "HoaVaultPage", _FakeHoaVaultPage)

    plugin = HoaShellPlugin()
    plugin.initialize(MagicMock())
    vault_page = _FakeHoaVaultPage()

    plugin.on_vault_ui_ready(vault_page)

    request_flow_cls.assert_called_once()
    onboarding_home_page_cls.assert_called_once()
    assert plugin._request_flow is request_flow_instance
    assert plugin._home_page is onboarding_home_page_instance
    assert isinstance(plugin._notifications_page, HoaNotificationsPage)
    registered = {c.args[0]: c.args[1] for c in vault_page.register_page.call_args_list}
    assert registered == {
        "home": onboarding_home_page_instance,
        "notifications": plugin._notifications_page,
    }
    assert vault_page.add_menu_entry.call_count == 2
    assert plugin._vault_page is vault_page


# ---------------------------------------------------------------------------
# on_vault_opened — deferred refresh + idempotency, moved from
# test_maybe_wire_onboarding_schedules_deferred_refresh /
# test_maybe_wire_onboarding_is_idempotent_per_vault_no_double_schedule
# ---------------------------------------------------------------------------

def test_on_vault_opened_schedules_deferred_refresh(monkeypatch):
    """Live-observation fix: reopening a workspace holding a pending
    application showed the persona PICKER until the user interacted with
    it, because ``OnboardingHomePage.__init__`` derives state from
    ``held_provider()`` at CONSTRUCTION time -- potentially before this
    (possibly freshly-opened) vault is warm -- and, until now, only the
    ``doer_event`` connections wired below re-derived state afterward.
    ``on_vault_opened`` must ALSO schedule one deferred ``refresh()`` via
    ``QTimer.singleShot(0, ...)`` so the next event-loop turn re-derives
    against the now-open vault's real held credentials, landing directly on
    PENDING/LICENSED instead of requiring an unrelated event to happen
    first."""
    from locksmith.plugins.hoa_shell import plugin as shell_mod

    scheduled = []
    monkeypatch.setattr(
        shell_mod.QTimer, "singleShot",
        lambda delay, slot: scheduled.append((delay, slot)),
    )
    # Transport branch is orthogonal to this test's refresh-scheduling
    # assertions; neutralize it so a prior test's cached usurance
    # brand() (make_hoa_oobi_source non-None) can't invoke
    # _bring_up_direct_transport on this bare plugin.
    monkeypatch.setattr(shell_mod, "make_hoa_oobi_source", lambda: None)

    request_flow = MagicMock(name="request_flow")
    home_page = MagicMock(name="home_page")
    notifications_page = MagicMock(name="notifications_page")
    vault = MagicMock(name="vault")

    plugin = HoaShellPlugin()
    plugin.initialize(SimpleNamespace(vault=vault))
    plugin._request_flow = request_flow
    plugin._home_page = home_page
    plugin._notifications_page = notifications_page

    plugin.on_vault_opened(vault)

    request_flow.seed_all_personas.assert_called_once()
    vault.signals.doer_event.connect.assert_any_call(home_page.refresh)
    vault.signals.doer_event.connect.assert_any_call(home_page.on_doer_event)
    # Task 10: the notifications page's own refresh() is wired the same way.
    vault.signals.doer_event.connect.assert_any_call(notifications_page.refresh)

    assert scheduled == [(0, home_page.refresh)], (
        "must schedule exactly one deferred refresh() via QTimer.singleShot(0, ...)"
    )
    assert plugin._wired_vault is vault


def test_on_vault_opened_is_idempotent_per_vault_no_double_schedule(monkeypatch):
    """A plugin manager that re-invoked on_vault_opened for the SAME vault
    instance must not accumulate doer_event connections or refresh
    schedules -- the vault-identity guard must keep both from
    double-firing."""
    from locksmith.plugins.hoa_shell import plugin as shell_mod

    scheduled = []
    monkeypatch.setattr(
        shell_mod.QTimer, "singleShot",
        lambda delay, slot: scheduled.append((delay, slot)),
    )
    monkeypatch.setattr(shell_mod, "make_hoa_oobi_source", lambda: None)

    request_flow = MagicMock(name="request_flow")
    home_page = MagicMock(name="home_page")
    notifications_page = MagicMock(name="notifications_page")
    vault = MagicMock(name="vault")

    plugin = HoaShellPlugin()
    plugin.initialize(SimpleNamespace(vault=vault))
    plugin._request_flow = request_flow
    plugin._home_page = home_page
    plugin._notifications_page = notifications_page

    plugin.on_vault_opened(vault)
    plugin.on_vault_opened(vault)  # revisit, same vault

    assert len(scheduled) == 1, (
        "revisiting an already-wired vault must not re-schedule refresh()"
    )
    request_flow.seed_all_personas.assert_called_once()


# ---------------------------------------------------------------------------
# _bring_up_direct_transport — retry/abort/budget, moved from
# test_bring_up_direct_transport_retries_until_hab_appears /
# test_bring_up_direct_transport_aborts_on_vault_switch /
# test_bring_up_direct_transport_stops_at_budget
# ---------------------------------------------------------------------------

def _transport_plugin(vault):
    """A minimal HoaShellPlugin stand-in for the _bring_up_direct_transport
    retry tests: it only needs _app.vault, _wired_vault, and
    _request_flow.egf_doc -- the method itself is real (bound on a real
    HoaShellPlugin instance), so the retry recursion calls back into it."""
    plugin = HoaShellPlugin()
    plugin.initialize(SimpleNamespace(vault=vault))
    plugin._wired_vault = vault
    plugin._request_flow = SimpleNamespace(egf_doc=MagicMock(name="egf_doc"))
    return plugin


def test_bring_up_direct_transport_retries_until_hab_appears(monkeypatch):
    """First-run inception is async (create_identifier schedules an
    InceptDoer and returns before the hab exists), so the first
    ensure_direct_transport finds no hab and returns False. The plugin must
    retry on a bounded timer -- otherwise the per-vault wiring guard means
    transport never comes up for the first-run flow and the carrier can
    never present (the live-demo bug this fixes)."""
    from locksmith.plugins.hoa_shell import plugin as shell_mod

    scheduled = []
    monkeypatch.setattr(
        shell_mod.QTimer, "singleShot",
        lambda delay, slot: scheduled.append((delay, slot)),
    )
    monkeypatch.setattr(shell_mod, "make_hoa_oobi_source", lambda: None)
    monkeypatch.setattr(shell_mod, "brand",
                        lambda: SimpleNamespace(egf_accept_phases=("bootstrap",)))
    # False (deferred, no hab yet) on the first two calls, True on the third.
    results = iter([False, False, True])
    calls = []
    def fake_ensure(app, egf, src, phases):
        calls.append(1)
        return next(results)
    monkeypatch.setattr(shell_mod, "ensure_direct_transport", fake_ensure)

    vault = MagicMock(name="vault")
    plugin = _transport_plugin(vault)
    src = MagicMock(name="oobi_source")

    plugin._bring_up_direct_transport(src)                    # attempt 0 -> False
    assert scheduled and scheduled[-1][0] == 250              # retry queued at 250ms
    scheduled[-1][1]()                                        # fire attempt 1 -> False
    scheduled[-1][1]()                                        # fire attempt 2 -> True
    assert len(calls) == 3                                    # stopped once done


def test_bring_up_direct_transport_aborts_on_vault_switch(monkeypatch):
    """A queued retry must not run ensure_direct_transport against a vault
    that is no longer the wired/open one (vault switch or close mid-retry)."""
    from locksmith.plugins.hoa_shell import plugin as shell_mod

    monkeypatch.setattr(shell_mod, "brand",
                        lambda: SimpleNamespace(egf_accept_phases=("bootstrap",)))
    called = []
    monkeypatch.setattr(shell_mod, "ensure_direct_transport",
                        lambda *a: called.append(1) or True)

    vault = MagicMock(name="vault")
    plugin = _transport_plugin(vault)
    plugin._app.vault = MagicMock(name="a_different_vault")   # switched underneath
    plugin._bring_up_direct_transport(MagicMock())
    assert called == []                                       # never touched transport


def test_bring_up_direct_transport_stops_at_budget(monkeypatch):
    """If the hab never appears, the retry chain stops at max_attempts with
    a warning rather than scheduling forever."""
    from locksmith.plugins.hoa_shell import plugin as shell_mod

    scheduled = []
    monkeypatch.setattr(
        shell_mod.QTimer, "singleShot",
        lambda delay, slot: scheduled.append(slot),
    )
    monkeypatch.setattr(shell_mod, "make_hoa_oobi_source", lambda: None)
    monkeypatch.setattr(shell_mod, "brand",
                        lambda: SimpleNamespace(egf_accept_phases=("bootstrap",)))
    monkeypatch.setattr(shell_mod, "ensure_direct_transport",
                        lambda *a: False)                     # never done

    plugin = _transport_plugin(MagicMock(name="vault"))
    plugin._bring_up_direct_transport(MagicMock(), attempt=39, max_attempts=40)
    assert scheduled == []                                    # budget spent, no reschedule
