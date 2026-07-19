# -*- encoding: utf-8 -*-
"""Tests for ``HoaNotificationsPage`` — the persistent notifications surface
for a peeled HOA build (Task 10, HOA #2 live-demo finding).

The peeled ``HoaVaultPage`` never registers a "notifications" page (see
``tests/ui/vault/test_hoa_page.py``), so the wallet's 5s toast click
dead-ended and an inbound IPEX grant landed nowhere the user could act on.
This page gives it somewhere to land: a simple durable log of notes read
straight from the vault's notifier, an Accept action for `/exn/ipex/grant`
rows (wired through Task 8's ``make_admit_doer`` envelope chokepoint), and
generic rendering for every other route so nothing is ever silently dropped.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _note(rid, route, said, read=False):
    note = MagicMock()
    note.pad = {"a": {"r": route, "d": said}}
    note.datetime = "2026-07-18T12:00:00.000000+00:00"
    note.read = read
    return ((note.datetime, rid), note)


def _app_with_notes(notes):
    app = MagicMock()
    app.vault.notifier.noter.notes.getTopItemIter.return_value = iter(notes)
    hab = MagicMock(); hab.pre = "E" + "C" * 43
    hab.__class__.__name__ = "Hab"; hab.kever.wits = []
    app.vault.hby.habs = {hab.pre: hab}
    return app


def test_grant_note_renders_with_accept(qtbot):
    from locksmith.ui.hoa.notifications_page import HoaNotificationsPage
    app = _app_with_notes([_note("r1", "/exn/ipex/grant", "E" + "G" * 43)])
    page = HoaNotificationsPage(app)
    qtbot.addWidget(page)
    page.refresh()
    (row,) = page.rows()
    assert row["route"] == "/exn/ipex/grant" and row["said"] == "E" + "G" * 43
    assert page.unread_count() == 1


def test_accept_schedules_admit_and_marks_read(qtbot):
    from locksmith.ui.hoa.notifications_page import HoaNotificationsPage
    app = _app_with_notes([_note("r1", "/exn/ipex/grant", "E" + "G" * 43)])
    page = HoaNotificationsPage(app)
    qtbot.addWidget(page)
    page.refresh()
    with patch("locksmith.ui.hoa.notifications_page.make_admit_doer") as mk:
        page._accept(page.rows()[0])
    assert mk.call_args.kwargs["grant_said"] == "E" + "G" * 43
    app.vault.extend.assert_called_once()
    app.vault.notifier.mar.assert_called_once_with("r1")


def test_non_ipex_notes_render_without_accept(qtbot):
    from locksmith.ui.hoa.notifications_page import HoaNotificationsPage
    app = _app_with_notes([_note("r2", "/keystate/update", "")])
    page = HoaNotificationsPage(app)
    qtbot.addWidget(page)
    page.refresh()
    (row,) = page.rows()
    assert row["route"] == "/keystate/update"
    assert not page.has_accept_action(row)
