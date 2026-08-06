# -*- encoding: utf-8 -*-
"""The two Usurance role-plugins: independent gates, one page each, page
key == plugin_id == EGF role id (HOA #4 convention)."""
import pytest

from locksmith.plugins.actuary.plugin import (ACTUARY_ROLE_SCHEMA_SAID,
                                              USURANCE_ADMIN_AID,
                                              ActuaryPlugin)
from locksmith.plugins.cuo.plugin import CUO_ROLE_SCHEMA_SAID, CuoPlugin
from locksmith.plugins.product_designer.plugin import (
    PD_ROLE_SCHEMA_SAID, ProductDesignerPlugin)


@pytest.mark.parametrize("cls,pid,schema", [
    (ActuaryPlugin, "actuary", ACTUARY_ROLE_SCHEMA_SAID),
    (ProductDesignerPlugin, "product_designer", PD_ROLE_SCHEMA_SAID),
    (CuoPlugin, "cuo", CUO_ROLE_SCHEMA_SAID),
])
def test_role_plugin_declares_its_own_gate(cls, pid, schema):
    p = cls()
    assert p.plugin_id == pid
    rc = p.required_credential
    assert rc.schema_said == schema
    assert rc.issuer_aids == [USURANCE_ADMIN_AID]
    assert rc.required_state == "active"


def test_gates_are_distinct():
    assert ACTUARY_ROLE_SCHEMA_SAID != PD_ROLE_SCHEMA_SAID
    assert ACTUARY_ROLE_SCHEMA_SAID != CUO_ROLE_SCHEMA_SAID
    assert PD_ROLE_SCHEMA_SAID != CUO_ROLE_SCHEMA_SAID


def test_admin_aid_shape():
    assert len(USURANCE_ADMIN_AID) == 44
    assert USURANCE_ADMIN_AID.startswith("E")
    assert not USURANCE_ADMIN_AID.endswith("-")   # unlike the DOI AID


@pytest.mark.parametrize("cls,pid,label", [
    (ActuaryPlugin, "actuary", "Actuarial"),
    (ProductDesignerPlugin, "product_designer", "Insurance Product Design"),
    (CuoPlugin, "cuo", "Underwriting"),
])
def test_page_key_equals_plugin_id_and_menu_label(qapp, cls, pid, label):
    p = cls()
    p.initialize(object())
    assert list(p.get_pages().keys()) == [pid]
    assert p.get_menu_entry().text_label.text() == label
    assert p.get_menu_section() == []


def test_entry_points_registered():
    """Role plugins are brand-COMPOSED, so they live in the composed group.

    The group is what makes "brand must opt in" decidable before import; see
    docs/superpowers/specs/2026-07-25-plugin-origin-strategy-design.md. They are
    deliberately NOT in the default-on ``locksmith.plugins`` group — that would
    load them for every brand.
    """
    import importlib.metadata as md

    from locksmith.plugins.origins import (
        COMPOSED_ENTRY_POINT_GROUP,
        ENTRY_POINT_GROUP,
    )

    composed = {ep.name for ep in md.entry_points(group=COMPOSED_ENTRY_POINT_GROUP)}
    assert {"actuary", "product_designer", "cuo"} <= composed

    default_on = {ep.name for ep in md.entry_points(group=ENTRY_POINT_GROUP)}
    assert not ({"actuary", "product_designer", "cuo"} & default_on)


def test_two_gates_coexist_and_revoke_deactivates_exactly_one(monkeypatch):
    """Spec §12 unit: two simultaneously-satisfied gates -> two active roles;
    one gate dropping -> exactly one deactivates. Pure manager-level (mocked
    strategy/host, per tests/plugins/test_role_activation.py's idiom); the
    real-verifier version is the Task 14 e2e."""
    from unittest.mock import MagicMock
    from locksmith.plugins import manager as m
    from locksmith.plugins.manager import PluginManager

    mgr = PluginManager.__new__(PluginManager)
    mgr._active_roles = set()
    mgr._activation_strategy = MagicMock()
    mgr._surface_host = MagicMock()
    a, p = ActuaryPlugin(), ProductDesignerPlugin()
    mgr._gated_plugins = lambda: [a, p]
    mgr._held_credentials = lambda vault: []
    cred = MagicMock()
    mgr._matching_credential = lambda held, req: cred

    # both gates satisfied -> both activate
    monkeypatch.setattr(m, "gate_satisfied", lambda creds, req: True)
    mgr.reevaluate_role_gates(MagicMock())
    assert mgr._active_roles == {"actuary", "product_designer"}

    # actuary's gate drops (revoked); product_designer's stays satisfied
    monkeypatch.setattr(
        m, "gate_satisfied",
        lambda creds, req: req.schema_said != ACTUARY_ROLE_SCHEMA_SAID)
    mgr.reevaluate_role_gates(MagicMock())
    assert mgr._active_roles == {"product_designer"}
    mgr._activation_strategy.deactivate.assert_called_once_with(
        a, mgr._surface_host)


# --- Side-panel icons (HOA #4 demo follow-up) --------------------------------

def _composed_role_plugin_classes():
    """Every gated plugin the brand can compose, read from the LIVE entry-point
    group rather than named here.

    A hardcoded tuple is how this check silently stopped covering `cuo`: the
    plugin was added to four other enumerations and missed here, and a
    non-resolving icon degrades SILENTLY to the generic glyph (menu.py:50-51),
    so nothing would have reported it. Deriving the list means the next role
    plugin is covered the day it is registered.
    """
    from importlib.metadata import entry_points

    found = []
    for ep in entry_points(group="locksmith.plugins.composed"):
        cls = ep.load()
        if getattr(cls, "required_credential", None) is not None:
            found.append(pytest.param(cls, id=ep.name))
    return found


def test_the_composed_registry_actually_yields_gated_plugins():
    """Guards the guard: an empty parametrize list collects zero tests and
    reports green while asserting nothing."""
    assert len(_composed_role_plugin_classes()) >= 3


def _declared_icon_paths(cls):
    """The `:/assets/...` resource paths a plugin's get_menu_entry() names.

    Read from the source rather than the QIcon, because by the time the icon
    reaches `MenuButton.icon_obj` a non-resolving path has already been
    silently swapped for the fallback glyph and the original is unrecoverable.
    """
    import inspect
    import re

    return re.findall(r'":(/assets/[^"]+)"',
                      inspect.getsource(cls.get_menu_entry))


@pytest.mark.parametrize("cls", _composed_role_plugin_classes())
def test_role_menu_entry_icons_actually_resolve(qapp, default_brand_resources, cls):
    """Each role plugin's declared icon must actually RESOLVE in the bundle.

    The previous assertion here — `not icon_obj.isNull()` — was VACUOUS:
    MenuButton substitutes the generic plugin glyph for any null icon
    (menu.py:50-51), so `icon_obj` is never null however broken the path is.
    Measured: pointing a plugin at a non-existent `gavel.svg` still passed. A
    wrong icon is therefore invisible at runtime AND in tests, which is why
    this checks the resource path itself.

    `default_brand_resources` is required: resources_rc.py no longer exists —
    compiled assets live in the gitignored release/assets.rcc that brand_apply
    builds, and registration is per-test because Qt resource overlap is
    first-registered-wins (a global default would shadow brand-override tests).
    """
    from PySide6.QtCore import QFile

    paths = _declared_icon_paths(cls)
    if not paths:
        # Legitimate and supported: menu.py:44-47 documents that a plugin may
        # register an entry with a bare QIcon() and take the generic glyph on
        # purpose (the `carrier` plugin does). The contract is only that a
        # DECLARED path must resolve — not that every plugin must declare one.
        pytest.skip(f"{cls.__name__} declares no icon; the fallback is intended")
    for path in paths:
        assert QFile(f":{path}").exists(), (
            f"{cls.__name__} declares ':{path}', which does not resolve — "
            "MenuButton would silently fall back to the generic glyph. The "
            "name must exist in assets/material-icons/ AND be listed in "
            "resources.qrc.")


def test_menubutton_falls_back_to_default_plugin_icon(qapp, default_brand_resources):
    """A MenuButton given an empty icon adopts the generic plugin glyph, so a
    plugin that registers no icon never shows a blank side-panel entry."""
    from PySide6.QtGui import QIcon
    from locksmith.ui.vault.menu import MenuButton, _DEFAULT_PLUGIN_ICON
    assert not QIcon(_DEFAULT_PLUGIN_ICON).isNull(), "default icon resource missing"
    btn = MenuButton(icon=QIcon(), label="No Icon Plugin")
    assert not btn.icon_obj.isNull()
