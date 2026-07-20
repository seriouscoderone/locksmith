# -*- encoding: utf-8 -*-
"""Tests for `InboundGrantWatchDoer`: the owner-approved auto-admit policy
for HOA #2 -- when the user explicitly applied for role R (PENDING state)
and the EXPECTED grant arrives (schema == R's grant credential schema AND
sender is one of the EGF's accepted authorities for that credential's
issuer_role), admit WITHOUT prompting. Anything else is left unread for
the notifications page's Accept prompt (Task 10).

Adaptation from the task-11 brief: the brief's mock shape patches
`exchanging.cloneMessage` to return an object with `.serder.ked`, but the
REAL `keri.peer.exchanging.cloneMessage` returns a plain `(serder, pathed)`
2-tuple (see `locksmith.core.serviceaid_bridge.ServiceaidAdmitDoer.
_deliver_admit_back`'s docstring, and `HoaNotificationsPage.
_grant_credential_name`, which both unpack it this same way). `_grant_msg`
below builds the SERDER half only; call sites wrap it in `(serder, {})`.
"""
from unittest.mock import MagicMock, patch

import dataclasses

from keri_serviceaid.egf.documents import EgfDocument
from keri_serviceaid.tests.egf.fixtures.make_fixture_egf import fixture_egf


@dataclasses.dataclass
class Held:
    schema_said: str; issuer_aid: str; state: str; chain_verified: bool
    said: str = "E" + "I" * 43


def _doc():
    _, sad = fixture_egf()
    return EgfDocument.from_sad(sad)


def _grant_msg(sender, schema):
    """The SERDER half of `exchanging.cloneMessage`'s real `(serder,
    pathed)` return -- callers wrap this as `(serder, {})`."""
    serder = MagicMock()
    serder.ked = {"i": sender, "r": "/ipex/grant",
                  "e": {"acdc": {"s": schema, "i": sender}}}
    return serder


def _env(doc, held, notes):
    app = MagicMock()
    app.vault.notifier.noter.notes.getTopItemIter.return_value = iter(notes)
    hab = MagicMock(); hab.pre = "E" + "C" * 43
    hab.__class__.__name__ = "Hab"; hab.kever.wits = []
    app.vault.hby.habs = {hab.pre: hab}
    from locksmith.core.inbound_watch import InboundGrantWatchDoer
    return app, InboundGrantWatchDoer(
        app, doc, ("bootstrap", "production"), held_provider=lambda: held)


def _note(rid, said):
    note = MagicMock()
    note.pad = {"a": {"r": "/exn/ipex/grant", "d": said}}
    note.read = False
    return (("2026-07-18T12:00:00+00:00", rid), note)


def test_expected_grant_auto_admits():
    doc = _doc()
    role = doc.personas()[0]
    grant_cred = doc.credential(role.onboarding.grant_credential_id)
    app_cred = doc.credential(grant_cred.chained_from)
    # Adaptation: the fixture EGF has TWO regulator authorities across the
    # combined ("bootstrap", "production") phases accepted here (UT DOI +
    # CA DOI -- see make_fixture_egf.py), so the brief's single-tuple
    # unpack (`(authority,) = ...`) raises ValueError. Take the first
    # accepted authority instead -- still a legitimate authority for this
    # credential's issuer_role, which is all the test needs.
    authority = doc.authorities(grant_cred.issuer_role,
                                accept_phases=("bootstrap", "production"))[0]
    held = [Held(app_cred.schema_said, "E" + "C" * 43, "issued", True)]  # PENDING
    app, watcher = _env(doc, held, [_note("r1", "E" + "G" * 43)])
    with patch("locksmith.core.inbound_watch.make_admit_doer") as mk, \
         patch("locksmith.core.inbound_watch.exchanging") as exc:
        exc.cloneMessage.return_value = (
            _grant_msg(authority.aid, grant_cred.schema_said), {})
        watcher.scan_once()
    assert mk.call_args.kwargs["grant_said"] == "E" + "G" * 43
    app.vault.notifier.mar.assert_called_once_with("r1")


def test_wrong_issuer_is_left_for_prompt():
    doc = _doc()
    role = doc.personas()[0]
    grant_cred = doc.credential(role.onboarding.grant_credential_id)
    app_cred = doc.credential(grant_cred.chained_from)
    held = [Held(app_cred.schema_said, "E" + "C" * 43, "issued", True)]
    app, watcher = _env(doc, held, [_note("r1", "E" + "G" * 43)])
    with patch("locksmith.core.inbound_watch.make_admit_doer") as mk, \
         patch("locksmith.core.inbound_watch.exchanging") as exc:
        exc.cloneMessage.return_value = (
            _grant_msg("E" + "V" * 43, grant_cred.schema_said), {})
        watcher.scan_once()
    mk.assert_not_called()
    app.vault.notifier.mar.assert_not_called()


def test_not_pending_never_auto_admits():
    doc = _doc()
    app, watcher = _env(doc, [], [_note("r1", "E" + "G" * 43)])  # PICKER state
    with patch("locksmith.core.inbound_watch.make_admit_doer") as mk, \
         patch("locksmith.core.inbound_watch.exchanging") as exc:
        exc.cloneMessage.return_value = (
            _grant_msg("E" + "U" * 43, "E" + "L" * 43), {})
        watcher.scan_once()
    mk.assert_not_called()


def test_admits_with_grants_recipient_hab_when_multiple_habs_present():
    """Finding 6 (final-review wave): `_admit` must resolve the admitting
    hab from the grant's own recipient (the exn's `a.i` attribute), not
    unconditionally the first hab in `hby.habs` -- a multi-hab wallet could
    otherwise schedule the admit under the wrong identifier."""
    doc = _doc()
    role = doc.personas()[0]
    grant_cred = doc.credential(role.onboarding.grant_credential_id)
    app_cred = doc.credential(grant_cred.chained_from)
    authority = doc.authorities(grant_cred.issuer_role,
                                accept_phases=("bootstrap", "production"))[0]
    held = [Held(app_cred.schema_said, "E" + "C" * 43, "issued", True)]  # PENDING
    app, watcher = _env(doc, held, [_note("r1", "E" + "G" * 43)])

    # A second hab, distinct from the first -- the grant's `a.i` recipient.
    second_hab = MagicMock()
    second_hab.pre = "E" + "D" * 43
    second_hab.__class__.__name__ = "Hab"
    second_hab.kever.wits = []
    app.vault.hby.habs[second_hab.pre] = second_hab

    grant_serder = MagicMock()
    grant_serder.ked = {
        "i": authority.aid, "r": "/ipex/grant",
        "e": {"acdc": {"s": grant_cred.schema_said, "i": authority.aid}},
        "a": {"i": second_hab.pre},
    }

    with patch("locksmith.core.inbound_watch.make_admit_doer") as mk, \
         patch("locksmith.core.inbound_watch.exchanging") as exc:
        exc.cloneMessage.return_value = (grant_serder, {})
        watcher.scan_once()

    assert mk.call_args.args[1] is second_hab


def test_malformed_exn_skipped_not_fatal():
    doc = _doc()
    app, watcher = _env(doc, [], [_note("r1", "E" + "G" * 43)])
    with patch("locksmith.core.inbound_watch.exchanging") as exc:
        exc.cloneMessage.side_effect = ValueError("bad stream")
        watcher.scan_once()   # must not raise
