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


def test_read_grant_row_has_no_accept_action(qtbot):
    """Finding 5 (final-review wave): has_accept_action was route-only, so
    an auto-admitted (marked-read) grant row still offered Accept -- a
    second admit could be scheduled for a grant that already landed.
    Requiring `not row["read"]` closes that window."""
    from locksmith.ui.hoa.notifications_page import HoaNotificationsPage
    app = _app_with_notes([_note("r1", "/exn/ipex/grant", "E" + "G" * 43, read=True)])
    page = HoaNotificationsPage(app)
    qtbot.addWidget(page)
    page.refresh()
    (row,) = page.rows()
    assert row["read"] is True
    assert not page.has_accept_action(row)


def test_unread_grant_row_has_accept_action(qtbot):
    """Companion to the above: an unread grant row still offers Accept."""
    from locksmith.ui.hoa.notifications_page import HoaNotificationsPage
    app = _app_with_notes([_note("r1", "/exn/ipex/grant", "E" + "G" * 43, read=False)])
    page = HoaNotificationsPage(app)
    qtbot.addWidget(page)
    page.refresh()
    (row,) = page.rows()
    assert row["read"] is False
    assert page.has_accept_action(row)


def test_accept_admits_with_grants_recipient_hab_not_first_hab(qtbot):
    """Finding 6 (final-review wave): _accept must resolve the admitting
    hab from the grant's own recipient (its exn's `a.i` attribute), not
    unconditionally the first hab in `hby.habs` -- a multi-hab wallet
    could otherwise schedule the admit under the wrong identifier."""
    from locksmith.ui.hoa.notifications_page import HoaNotificationsPage

    said = "E" + "G" * 43
    app = _app_with_notes([_note("r1", "/exn/ipex/grant", said)])

    first_hab = next(iter(app.vault.hby.habs.values()))
    second_hab = MagicMock()
    second_hab.pre = "E" + "D" * 43
    app.vault.hby.habs[second_hab.pre] = second_hab

    exn = SimpleNamespace(ked={"a": {"i": second_hab.pre}})

    page = HoaNotificationsPage(app)
    qtbot.addWidget(page)
    page.refresh()

    with patch("locksmith.ui.hoa.notifications_page.exchanging.cloneMessage") as clone_mock, \
            patch("locksmith.ui.hoa.notifications_page.make_admit_doer") as mk:
        clone_mock.return_value = (exn, {})
        page._accept(page.rows()[0])

    assert mk.call_args.args[1] is second_hab
    assert mk.call_args.args[1] is not first_hab


def test_inbound_grant_to_local_hab_shows_accept(qtbot):
    """A genuine INBOUND grant -- its exn recipient (`a.i`) is a LOCAL hab
    and its sender (`i`) is remote -- still offers Accept."""
    from locksmith.ui.hoa.notifications_page import HoaNotificationsPage

    said = "E" + "G" * 43
    local_pre = "E" + "C" * 43   # matches the hab _app_with_notes installs
    remote_pre = "E" + "R" * 43
    app = _app_with_notes([_note("r1", "/exn/ipex/grant", said)])
    exn = SimpleNamespace(ked={"i": remote_pre, "a": {"i": local_pre}})

    page = HoaNotificationsPage(app)
    qtbot.addWidget(page)
    with patch("locksmith.ui.hoa.notifications_page.exchanging.cloneMessage") as clone:
        clone.return_value = (exn, {})
        page.refresh()

    (row,) = page.rows()
    assert page.has_accept_action(row)


def test_self_sent_grant_suppresses_accept(qtbot):
    """The wallet's OWN outbound self-issued grant (exn sender `i` is a
    LOCAL hab) is parsed into the local exchanger just like an inbound one,
    but accepting your own grant is meaningless -- Accept must be suppressed.
    (HOA #3 two-app demo, 2026-07-20: the carrier's 'Carrier License
    Application' row wrongly showed an Accept button.)"""
    from locksmith.ui.hoa.notifications_page import HoaNotificationsPage

    said = "E" + "G" * 43
    local_pre = "E" + "C" * 43   # matches the hab _app_with_notes installs
    remote_pre = "E" + "R" * 43
    app = _app_with_notes([_note("r1", "/exn/ipex/grant", said)])
    # Carrier (local) sent the grant to a remote applicant.
    exn = SimpleNamespace(ked={"i": local_pre, "a": {"i": remote_pre}})

    page = HoaNotificationsPage(app)
    qtbot.addWidget(page)
    with patch("locksmith.ui.hoa.notifications_page.exchanging.cloneMessage") as clone:
        clone.return_value = (exn, {})
        page.refresh()

    (row,) = page.rows()
    assert not page.has_accept_action(row)


def test_self_sent_grant_to_own_hab_suppresses_accept(qtbot):
    """Even when BOTH sender and recipient are local habs, a grant this
    wallet authored is not an inbound offer -- the sender-is-local clause
    suppresses Accept. A recipient-only check would wrongly show it, so this
    pins that clause specifically."""
    from locksmith.ui.hoa.notifications_page import HoaNotificationsPage

    said = "E" + "G" * 43
    local_pre = "E" + "C" * 43   # matches the hab _app_with_notes installs
    second_pre = "E" + "D" * 43
    app = _app_with_notes([_note("r1", "/exn/ipex/grant", said)])
    second = MagicMock(); second.pre = second_pre
    app.vault.hby.habs[second_pre] = second
    exn = SimpleNamespace(ked={"i": local_pre, "a": {"i": second_pre}})

    page = HoaNotificationsPage(app)
    qtbot.addWidget(page)
    with patch("locksmith.ui.hoa.notifications_page.exchanging.cloneMessage") as clone:
        clone.return_value = (exn, {})
        page.refresh()

    (row,) = page.rows()
    assert not page.has_accept_action(row)


def test_grant_title_resolved_from_egf_credential_catalog(qtbot):
    """When egf_doc is provided and grant's embedded ACDC schema matches
    a catalog entry, the title is upgraded from generic to the credential's
    display name (e.g. 'License' instead of 'New credential offer')."""
    from locksmith.ui.hoa.notifications_page import HoaNotificationsPage
    from keri_serviceaid.egf.documents import EgfDocument
    from keri_serviceaid.tests.egf.fixtures.make_fixture_egf import fixture_egf

    # Load real fixture document
    _, sad = fixture_egf()
    egf_doc = EgfDocument.from_sad(sad)

    # Create app with grant note
    grant_said = "E" + "G" * 43
    app = _app_with_notes([_note("r1", "/exn/ipex/grant", grant_said)])

    # Mock exchanging.cloneMessage to return an exn with License schema
    license_schema_said = "E" + "L" * 43  # From fixture: License credential schema
    exn_ked = {
        "e": {
            "acdc": {
                "s": license_schema_said
            }
        }
    }
    exn_mock = SimpleNamespace(ked=exn_ked)

    with patch("locksmith.ui.hoa.notifications_page.exchanging.cloneMessage") as clone_mock:
        clone_mock.return_value = (exn_mock, [])
        page = HoaNotificationsPage(app, egf_doc=egf_doc)
        qtbot.addWidget(page)
        page.refresh()

    # The row title should be resolved to "License" from the EGF catalog
    (row,) = page.rows()
    assert row["title"] == "License"


def test_notifications_synthesizes_revoked_row(qtbot):
    """A held gating credential that has been revoked (chain-verified,
    state == "revoked") synthesizes a durable 'access revoked' row, even
    though a raw TEL `rev` produces no notifier note of its own."""
    from locksmith.ui.hoa.notifications_page import HoaNotificationsPage
    from keri_serviceaid.egf.documents import EgfDocument
    from keri_serviceaid.tests.egf.fixtures.make_fixture_egf import fixture_egf

    _, sad = fixture_egf()
    egf_doc = EgfDocument.from_sad(sad)

    revoked = SimpleNamespace(
        schema_said="E" + "L" * 43,
        issuer_aid="E" + "U" * 43,
        state="revoked",
        chain_verified=True,
        said="ELIC",
        revoked_at="2026-07-19T12:00:00.000000+00:00",
    )

    app = _app_with_notes([])
    page = HoaNotificationsPage(app, egf_doc=egf_doc, held_provider=lambda: [revoked])
    qtbot.addWidget(page)
    page.refresh()

    rev_rows = [r for r in page.rows() if r["route"] == "revoked"]
    assert rev_rows, "a revoked gating credential must synthesize a card"
    assert "revoked" in rev_rows[0]["title"].lower()
    assert rev_rows[0]["said"] == "ELIC"
    assert not HoaNotificationsPage.has_accept_action(rev_rows[0])


def test_notifications_no_revoked_row_when_none_held(qtbot):
    """No held credentials -> no synthesized revoked rows."""
    from locksmith.ui.hoa.notifications_page import HoaNotificationsPage
    from keri_serviceaid.egf.documents import EgfDocument
    from keri_serviceaid.tests.egf.fixtures.make_fixture_egf import fixture_egf

    _, sad = fixture_egf()
    egf_doc = EgfDocument.from_sad(sad)

    app = _app_with_notes([])
    page = HoaNotificationsPage(app, egf_doc=egf_doc, held_provider=lambda: [])
    qtbot.addWidget(page)
    page.refresh()

    assert not [r for r in page.rows() if r["route"] == "revoked"]
