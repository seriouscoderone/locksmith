# -*- encoding: utf-8 -*-
"""Revoke -> re-grant must not crash the reveal, for EVERY gated role plugin.

Parametrized over the live `locksmith.plugins.composed` entry-point group instead of a
hardcoded list: a future role plugin is covered the day it is registered. (Contrast
tests/plugins/test_brand_plugin_parity.py, whose hardcoded EXPECTED set is deliberate
— its job is to CATCH drift, so deriving it from the thing it guards would make it
assert nothing. Derive a check that applies to every member; hand-write a tripwire.)
"""
from __future__ import annotations

from importlib.metadata import entry_points

import pytest
from PySide6.QtWidgets import QWidget

from locksmith.plugins.role_activation import RevealBundledSurface
from tests.plugins.conftest import DestroyingSurfaceHost, widget_is_live


def _gated_role_plugins():
    """Every composed plugin that declares a credential gate — i.e. every role
    surface that can be revealed and withdrawn."""
    found = []
    for ep in entry_points(group="locksmith.plugins.composed"):
        cls = ep.load()
        if getattr(cls, "required_credential", None) is not None:
            found.append(pytest.param(cls, id=ep.name))
    return found


def test_the_registry_actually_yields_gated_plugins():
    """Guards the guard: an empty parametrize list would make every test below vanish
    silently, reporting green while asserting nothing."""
    assert len(_gated_role_plugins()) >= 2


@pytest.mark.parametrize("plugin_cls", _gated_role_plugins())
def test_a_withdrawn_surface_can_be_revealed_again(qapp, plugin_cls):
    plugin = plugin_cls()
    plugin.initialize(app=None)
    host = DestroyingSurfaceHost()
    reveal = RevealBundledSurface()

    reveal.activate(plugin, credential=None, surface_host=host)
    key = next(iter(host.pages))
    first = host.pages[key]
    assert widget_is_live(first)

    reveal.deactivate(plugin, surface_host=host)   # the revocation edge destroys the widget
    reveal.activate(plugin, credential=None, surface_host=host)   # the re-grant edge must produce a LIVE one

    second = host.pages[key]
    assert widget_is_live(second), "re-revealed surface must be a live widget"
    assert second is not first, "get_pages() must not hand back the destroyed widget"
    assert isinstance(second, QWidget)


def test_a_failing_activation_does_not_leave_the_role_wedged(qapp, monkeypatch):
    """reevaluate_role_gates calls `self._activation_strategy.activate(plugin, cred,
    host)` and only THEN does `self._active_roles.add(plugin.plugin_id)` -- both calls
    unguarded. An activate() that raises therefore propagates straight out of
    reevaluate_role_gates (crashing whatever caller/doer invoked it -- on_vault_opened,
    the live IPEX-admit signal handler, or GateRecheckDoer's 2s poll) AND leaves
    _active_roles without the role, so the next recheck retries the same doomed
    activation forever with no record it ever ran.

    This drives the real internal seam (`PluginManager.reevaluate_role_gates`) rather
    than a `_activate_role` method (no such method exists) -- see manager.py:365-385.
    """
    from locksmith.plugins.credential_gate import RequiredCredential
    from locksmith.plugins.manager import HeldCredential, PluginManager

    mgr = PluginManager.__new__(PluginManager)   # no app/vault needed for this path
    mgr._active_roles = set()
    mgr._surface_host = object()

    class _Boom:
        def activate(self, plugin, credential, surface_host):
            raise RuntimeError("surface build failed")

        def deactivate(self, plugin, surface_host):
            pass

    mgr._activation_strategy = _Boom()

    req = RequiredCredential(
        schema_said="ETESTSCHEMA", issuer_aids=["EISSUERAID"], required_state="active",
    )

    class _Plugin:
        plugin_id = "actuary"
        required_credential = req

    mgr._plugins = {"actuary": _Plugin()}
    held = [HeldCredential(
        schema_said="ETESTSCHEMA", issuer_aid="EISSUERAID", state="active",
        chain_verified=True, said="ESAID",
    )]
    monkeypatch.setattr(mgr, "_held_credentials", lambda vault: held)

    # must not propagate -- a bad surface cannot be allowed to wedge the gate loop
    mgr.reevaluate_role_gates(vault=object())

    assert "actuary" not in mgr._active_roles, (
        "activation raised -- the role must not be recorded active when nothing is "
        "actually on screen"
    )
