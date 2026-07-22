# -*- encoding: utf-8 -*-
"""Top-toolbar contribution seam (HOA #4): plugins add/remove widgets by id."""
from types import SimpleNamespace

from PySide6.QtWidgets import QPushButton

from locksmith.ui.toolbar import LocksmithToolbar


def _toolbar(qapp) -> LocksmithToolbar:
    app = SimpleNamespace(vault=None, name=None)
    return LocksmithToolbar(app)


def test_add_action_inserts_widget_and_tracks_id(qapp):
    tb = _toolbar(qapp)
    try:
        btn = QPushButton("Roles")
        tb.add_action("hoa_shell.roles", btn, section="right")
        assert "hoa_shell.roles" in tb._contributed
        assert btn.parent() is tb
    finally:
        tb.deleteLater()


def test_add_action_same_id_replaces_previous_widget(qapp):
    tb = _toolbar(qapp)
    try:
        first, second = QPushButton("a"), QPushButton("b")
        tb.add_action("x.a", first, section="right")
        tb.add_action("x.a", second, section="right")
        assert len(tb._contributed) == 1
        assert second.parent() is tb
    finally:
        tb.deleteLater()


def test_remove_action_symmetric_and_idempotent(qapp):
    tb = _toolbar(qapp)
    try:
        tb.add_action("x.a", QPushButton("a"), section="left")
        tb.remove_action("x.a")
        assert "x.a" not in tb._contributed
        tb.remove_action("x.a")          # unknown id: silent no-op
        tb.remove_action("never-added")  # never-known id: silent no-op
    finally:
        tb.deleteLater()


def test_left_and_right_sections_both_insert(qapp):
    tb = _toolbar(qapp)
    try:
        tb.add_action("x.l", QPushButton("l"), section="left")
        tb.add_action("x.r", QPushButton("r"), section="right")
        assert set(tb._contributed) == {"x.l", "x.r"}
    finally:
        tb.deleteLater()
