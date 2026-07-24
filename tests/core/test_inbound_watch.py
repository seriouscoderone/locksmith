# -*- encoding: utf-8 -*-
"""Tests for `InboundGrantWatchDoer`: the owner-approved auto-admit policy
for HOA #2 -- when the user explicitly applied for role R (PENDING state)
and the EXPECTED grant arrives (schema == R's grant credential schema AND
sender is one of the EGF's accepted authorities for that credential's
issuer_role), admit WITHOUT prompting. Anything else is left unread for
the notifications page's Accept prompt (Task 10).

Task 11 (multi-apply auto-admit, HOA #4): the watcher's PENDING check now
goes through `locksmith.ui.onboarding.role_states.derive_role_states`
(Task 8) rather than the single-role `derive_state`/`OnboardingState` app-
global state machine (removed -- see `home_page.py`'s module docstring),
fed by a NEW `applies_provider` constructor arg (the holder's own sent
`/ipex/apply` exns, Task 2 row shape: `{"schema_said": ..., ...}`).
Multiple simultaneously-outstanding applies (across DIFFERENT roles) each
match independently -- `test_two_outstanding_applies_each_auto_admit_
independently` below is the new coverage; the rest of this file's tests
are UNCHANGED behaviorally (single fixture EGF's one form-mode "carrier"
role, PENDING via a held application credential, `applies_provider`
defaulting to empty).

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

from keri.core import coring
from keri_serviceaid.egf.documents import EgfDocument
from keri_serviceaid.tests.egf.fixtures.make_fixture_egf import fixture_egf

SCHEMA_A = "E" + "A" * 43   # actuary_role
SCHEMA_P = "E" + "P" * 43   # product_designer_role


@dataclasses.dataclass
class Held:
    schema_said: str; issuer_aid: str; state: str; chain_verified: bool
    said: str = "E" + "I" * 43


def _doc():
    _, sad = fixture_egf()
    return EgfDocument.from_sad(sad)


def _saidify(doc: dict) -> dict:
    doc = dict(doc)
    doc["d"] = ""
    _, sad = coring.Saider.saidify(sad=doc, label="d")
    return sad


def _two_persona_doc():
    """A SECOND fixture EGF, alongside `_doc()` (`fixture_egf()`'s one
    form-mode "carrier" role): TWO apply-mode personas ("actuary"/SCHEMA_A,
    "product_designer"/SCHEMA_P), both role-credentialed by the SAME
    "admin" authority -- HOA #4 multi-role, mirroring `test_role_states.
    py`'s FakeEgf naming so the two suites read as the same scenario. No
    existing bundled fixture has two apply-mode personas sharing one
    issuer_role, so this is hand-assembled the same way `make_fixture_egf.
    apply_mode_egf` is (a minimal valid egf-doc/0.1 SAD), just with a
    second persona/credential pair."""
    admin_aid = "E" + "B" * 43
    doc = {
        "d": "", "spec_version": "egf-doc/0.1", "version": "0.1.0",
        "ecosystem": {"id": "t-multi", "display_name": "T", "openness": "closed",
                      "description": "test"},
        "governance": {"phase": "production", "transition_plan": "n/a"},
        "roles": [
            {"id": "actuary", "display_name": "Actuarial", "kind": "individual",
             "description": "", "onboarding": {"grant_credential_id": "actuary_role"}},
            {"id": "product_designer", "display_name": "IPD", "kind": "individual",
             "description": "",
             "onboarding": {"grant_credential_id": "product_designer_role"}},
            {"id": "admin", "display_name": "Admin", "kind": "organization",
             "description": ""},
        ],
        "credentials": [
            {"id": "actuary_role", "name": "Actuary Role", "schema_said": SCHEMA_A,
             "issuer_role": "admin", "holder_role": "actuary",
             "disclosure_mode": "full", "chained_from": None, "self_issued": False},
            {"id": "product_designer_role", "name": "IPD Role", "schema_said": SCHEMA_P,
             "issuer_role": "admin", "holder_role": "product_designer",
             "disclosure_mode": "full", "chained_from": None, "self_issued": False},
        ],
        "authorities": [
            {"role_id": "admin", "display_name": "Admin", "context": {},
             "aid": admin_aid, "phase": "production",
             "phase_note": "genuine internal authority",
             "expected_transition": None,
             "credentials": ["actuary_role", "product_designer_role"],
             "endpoints": []},
        ],
        "accepted_schema_saids": [SCHEMA_A, SCHEMA_P],
        "micro_apps": [],
        "context_dimensions": [],
    }
    sad = _saidify(doc)
    return EgfDocument.from_sad(sad)


def _apply(schema_said, dt="2026-07-22T00:00:00+00:00"):
    """A sent-apply row -- Task 2's contract shape; the deriver only reads
    `schema_said` (see `role_states._role_pending`), the rest is carried
    for shape-fidelity with `keri_serviceaid.providers.apply.
    list_sent_applies`'s real row."""
    return {"said": "E" + "S" * 43, "schema_said": schema_said,
            "recipient": "E" + "B" * 43, "message": "", "dt": dt}


def _grant_msg(sender, schema):
    """The SERDER half of `exchanging.cloneMessage`'s real `(serder,
    pathed)` return -- callers wrap this as `(serder, {})`."""
    serder = MagicMock()
    serder.ked = {"i": sender, "r": "/ipex/grant",
                  "e": {"acdc": {"s": schema, "i": sender}}}
    return serder


def _env(doc, held, notes, applies=()):
    app = MagicMock()
    app.vault.notifier.noter.notes.getTopItemIter.return_value = iter(notes)
    hab = MagicMock(); hab.pre = "E" + "C" * 43
    hab.__class__.__name__ = "Hab"; hab.kever.wits = []
    app.vault.hby.habs = {hab.pre: hab}
    from locksmith.core.inbound_watch import InboundGrantWatchDoer
    return app, InboundGrantWatchDoer(
        app, doc, ("bootstrap", "production"), held_provider=lambda: held,
        applies_provider=lambda: list(applies))


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


# ---------------------------------------------------------------------------
# Task 11: multi-apply auto-admit -- the `applies_provider`-fed,
# `derive_role_states`-backed outstanding-request set. Two simultaneously
# PENDING apply-mode roles (sharing one "admin" issuer_role/authority, see
# `_two_persona_doc`) must each match independently; a role with no
# outstanding apply (AVAILABLE) must never auto-admit; a sender that isn't
# an accepted authority must never auto-admit even with a PENDING match.
# ---------------------------------------------------------------------------

def test_two_outstanding_applies_each_auto_admit_independently():
    """HOA #4 multi-role: the holder sent TWO outstanding applies (actuary +
    product_designer) -- an inbound grant for EITHER schema, from the
    shared admin authority, auto-admits independently of the other."""
    doc = _two_persona_doc()
    admin_authority = doc.authorities(
        "admin", accept_phases=("bootstrap", "production"))[0]
    applies = [_apply(SCHEMA_A), _apply(SCHEMA_P)]
    notes = [_note("r1", "E" + "G" * 43), _note("r2", "E" + "H" * 43)]
    app, watcher = _env(doc, [], notes, applies=applies)

    grants = {
        "E" + "G" * 43: (_grant_msg(admin_authority.aid, SCHEMA_A), {}),
        "E" + "H" * 43: (_grant_msg(admin_authority.aid, SCHEMA_P), {}),
    }
    with patch("locksmith.core.inbound_watch.make_admit_doer") as mk, \
         patch("locksmith.core.inbound_watch.exchanging") as exc:
        exc.cloneMessage.side_effect = lambda hby, said: grants[said]
        watcher.scan_once()

    admitted = {call.kwargs["grant_said"] for call in mk.call_args_list}
    assert admitted == {"E" + "G" * 43, "E" + "H" * 43}
    app.vault.notifier.mar.assert_any_call("r1")
    app.vault.notifier.mar.assert_any_call("r2")


def test_grant_without_outstanding_apply_prompts_not_admits():
    """No sent apply for either role -> both AVAILABLE, not PENDING -- the
    grant is left unread for `HoaNotificationsPage`'s Accept prompt."""
    doc = _two_persona_doc()
    admin_authority = doc.authorities(
        "admin", accept_phases=("bootstrap", "production"))[0]
    app, watcher = _env(doc, [], [_note("r1", "E" + "G" * 43)], applies=[])
    with patch("locksmith.core.inbound_watch.make_admit_doer") as mk, \
         patch("locksmith.core.inbound_watch.exchanging") as exc:
        exc.cloneMessage.return_value = (
            _grant_msg(admin_authority.aid, SCHEMA_A), {})
        watcher.scan_once()
    mk.assert_not_called()
    app.vault.notifier.mar.assert_not_called()


def test_grant_from_non_authority_never_auto_admits():
    """An outstanding apply for SCHEMA_A exists (actuary PENDING), but the
    grant's sender is NOT an accepted authority for actuary_role's
    issuer_role -- must never auto-admit, regardless of the PENDING
    match."""
    doc = _two_persona_doc()
    applies = [_apply(SCHEMA_A)]
    app, watcher = _env(doc, [], [_note("r1", "E" + "G" * 43)], applies=applies)
    with patch("locksmith.core.inbound_watch.make_admit_doer") as mk, \
         patch("locksmith.core.inbound_watch.exchanging") as exc:
        exc.cloneMessage.return_value = (
            _grant_msg("E" + "V" * 43, SCHEMA_A), {})  # not the admin authority
        watcher.scan_once()
    mk.assert_not_called()
    app.vault.notifier.mar.assert_not_called()
