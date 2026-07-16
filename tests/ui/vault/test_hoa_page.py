# -*- encoding: utf-8 -*-
"""Tests for HoaVaultPage — the peel-light VaultPage that suppresses the
built-in wallet pages for an HOA shell while keeping the string-keyed page
registry and the plugin surface intact.

VaultPage.__init__ requires a non-None parent exposing an ``.app`` attribute
(it asserts on this and reads ``parent.app`` unconditionally), so tests build
a minimal fake parent — the same pattern used elsewhere in this repo, e.g.
tests/test_keri_v2_compat.py::test_add_identifier_flow_opens_dialog_with_keri_v2_salt.
"""
from types import SimpleNamespace

from PySide6.QtWidgets import QWidget

from locksmith.ui.vault.hoa_page import HoaVaultPage


def _fake_parent() -> QWidget:
    parent = QWidget()
    parent.app = SimpleNamespace(config=SimpleNamespace(), vault=None)
    return parent


def test_hoa_page_registers_no_core_wallet_pages(qtbot):
    parent = _fake_parent()
    qtbot.addWidget(parent)
    page = HoaVaultPage(parent)
    qtbot.addWidget(page)
    # Core wallet page keys that stock Locksmith registers in _register_core_pages()
    core_keys = {"identifiers", "credentials", "groups", "remotes", "settings", "notifications"}
    assert core_keys.isdisjoint(set(page.registered_page_keys()))


def test_hoa_page_still_accepts_plugin_pages(qtbot):
    parent = _fake_parent()
    qtbot.addWidget(parent)
    page = HoaVaultPage(parent)
    qtbot.addWidget(page)
    page.register_page("carrier", QWidget())
    assert "carrier" in page.registered_page_keys()
