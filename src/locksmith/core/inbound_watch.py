# -*- encoding: utf-8 -*-
"""
locksmith.core.inbound_watch module

``InboundGrantWatchDoer`` -- HOA #2's owner-approved auto-admit policy
(design spec, Task 11): when the user explicitly applied for role R (its
per-role onboarding status is ``RoleStatus.PENDING`` -- see
``locksmith.ui.onboarding.role_states.derive_role_states``, Task 8) and the
EXACT grant they're waiting on arrives -- the embedded ACDC's schema
matches R's grant credential AND the exn's sender is one of the EGF's
accepted authorities for that credential's ``issuer_role`` -- it is
admitted WITHOUT prompting. The user already consented by submitting the
application; this only short-circuits the confirmation click for the one
grant that could not possibly be anything else. Multiple simultaneously
PENDING roles (HOA #4 multi-role) are each honored independently -- Task
11 generalizes this from a single-role check onto the full per-role
``RoleStatus`` map, fed by a new ``applies_provider`` (the holder's own
sent ``/ipex/apply`` exns, Task 2's row shape) alongside ``held_provider``.

Anything that doesn't match all three conditions (role not PENDING, wrong
schema, or an unexpected sender) is left unread: `/exn/ipex/grant` notes
land in ``HoaNotificationsPage`` (Task 10), whose **Accept** button routes
through the exact same ``make_admit_doer`` chokepoint on demand.

Polls rather than reacts to a signal because the vault's notifier has no
push-on-arrival hook of its own (`NotificationToastDoer`, this module's
nearest precedent in ``locksmith.core.vaulting``, polls the same notifier
for the identical reason). Malformed/unparseable exns are logged and
skipped -- one bad note must never take the watcher down, since every
other note (including a REAL expected grant sitting right behind it in
the iterator) still needs to be checked on this same pass.
"""
from hio.base import doing
from keri import help
from keri.peer import exchanging

from locksmith.core.serviceaid_bridge import make_admit_doer

logger = help.ogler.getLogger(__name__)

_GRANT_ROUTE = "/exn/ipex/grant"


class InboundGrantWatchDoer(doing.Doer):
    """Polls unread `/exn/ipex/grant` notes and auto-admits the one the
    holder is expecting.

    Args:
        app: The ``LocksmithApplication`` -- reads ``app.vault.notifier``
            (unread notes), ``app.vault.hby`` (habs + ``cloneMessage``),
            and ``app.vault.extend``/``app.vault.signals`` (scheduling the
            admit + emitting the auto-admit event).
        egf_doc: The typed ``EgfDocument`` (Task 6) this HOA onboards
            against -- source of the personas/credentials/authorities the
            expected-grant test is checked against.
        accept_phases: Iterable of authority phases to trust when matching
            the exn's sender (mirrors ``brand().egf_accept_phases`` --
            same vocabulary as ``RequestFlow``/``OnboardingHomePage``).
        held_provider: Zero-arg callable returning the vault's current
            held-credential views (``OnboardingHomePage``'s own
            ``held_provider`` shape, e.g. the shell's ``_held_credentials``
            in ``locksmith.plugins.hoa_shell.plugin``)
            -- re-read on every scan so a just-issued application
            credential is visible without reconstructing the doer.
        applies_provider: Zero-arg callable returning the holder's own sent
            ``/ipex/apply`` exn rows (Task 2's shape, e.g.
            ``keri_serviceaid.providers.list_sent_applies``'s return) --
            re-read on every scan for the same reason as ``held_provider``.
            Feeds ``derive_role_states``'s apply-mode PENDING derivation
            (Task 11); defaults to no outstanding applies so callers that
            only onboard form-mode roles need not pass it.
        tock: Poll interval in seconds (default 1.0).
    """

    def __init__(self, app, egf_doc, accept_phases, held_provider,
                 applies_provider=lambda: [], tock: float = 1.0, **kwa):
        self.app = app
        self.egf_doc = egf_doc
        self.accept_phases = tuple(accept_phases)
        self.held_provider = held_provider
        self.applies_provider = applies_provider
        super(InboundGrantWatchDoer, self).__init__(tock=tock, **kwa)

    def do(self, tymth, tock=0.0, **opts):
        """Generator method -- overrides ``doing.Doer.do`` directly (same
        convention as ``locksmith.core.serviceaid_bridge``'s bridge doers)
        so it can be driven the same way a Doist would."""
        self.wind(tymth)
        self.tock = tock
        while True:
            yield self.tock
            self.scan_once()

    def scan_once(self) -> None:
        """One pass over the notifier's notes. Never raises -- a failure
        reading the notifier, or processing any single note, is logged and
        the pass continues (or ends) without taking the doer down."""
        notifier = getattr(getattr(self.app, "vault", None), "notifier", None)
        if notifier is None:
            return

        try:
            items = list(notifier.noter.notes.getTopItemIter())
        except Exception:
            logger.exception("InboundGrantWatchDoer: failed reading notifier notes")
            return

        for (_dt, rid), note in items:
            try:
                self._process_note(rid, note)
            except Exception:
                logger.exception(
                    "InboundGrantWatchDoer: error processing note rid=%s", rid)

    def _process_note(self, rid, note) -> None:
        if getattr(note, "read", False):
            return  # already handled (admitted, spurned, or read elsewhere)

        pad = getattr(note, "pad", None) or {}
        attrs = pad.get("a", {}) or {}
        route = attrs.get("r", "") or ""
        if _GRANT_ROUTE not in route:
            return  # not a grant -- notifications page's prompt handles it

        said = attrs.get("d", "") or ""
        if not said:
            return

        serder, _pathed = exchanging.cloneMessage(self.app.vault.hby, said)
        if serder is None:
            return

        ked = serder.ked
        sender = ked.get("i")
        schema_said = ked.get("e", {}).get("acdc", {}).get("s")
        if not sender or not schema_said:
            return

        match = self._match_expected_role(sender, schema_said)
        if match is None:
            return

        recipient = ked.get("a", {}).get("i", "") or ""
        self._admit(rid, said, schema_said, recipient)

    def _match_expected_role(self, sender: str, schema_said: str):
        """A grant auto-admits iff it satisfies an OUTSTANDING request:
        the role derived PENDING (apply-mode sent-apply or form-mode held
        application) AND the sender is an accepted authority for the role's
        issuer_role. Multiple simultaneously-PENDING roles each match
        independently (HOA #4 multi-role). Held credentials and sent
        applies are read fresh (``held_provider()``/``applies_provider()``)
        once per note, not cached across notes, since a match on an
        earlier note in this same pass (already admitted) can change
        subsequent state derivations."""
        from locksmith.ui.onboarding.role_states import (RoleStatus,
                                                         derive_role_states)
        held = self.held_provider()
        applies = self.applies_provider()
        states = derive_role_states(held, applies, self.egf_doc)
        for role in self.egf_doc.personas():
            grant = self.egf_doc.credential(role.onboarding.grant_credential_id)
            if grant.schema_said != schema_said:
                continue
            if states.get(role.id) is not RoleStatus.PENDING:
                continue
            authorities = self.egf_doc.authorities(
                grant.issuer_role, accept_phases=self.accept_phases)
            if not any(a.aid == sender for a in authorities):
                continue
            return role
        return None

    def _admit(self, rid: str, said: str, schema_said: str, recipient: str = "") -> None:
        vault = self.app.vault
        # Prefer the grant's own recipient hab (the exn's `a.i` attribute --
        # the same field `PeerExchangerShim.processEvent` reads as the
        # message's destination) when it resolves in this Habery; a
        # multi-hab wallet could otherwise admit under the wrong
        # identifier. Falls back to the previous first-hab behavior when
        # the recipient doesn't resolve.
        hab = vault.hby.habs.get(recipient) if recipient else None
        if hab is None:
            hab = next(iter(vault.hby.habs.values()), None)
        if hab is None:
            logger.error(
                "InboundGrantWatchDoer: no hab available to admit grant_said=%s", said)
            return

        doer = make_admit_doer(self.app, hab, grant_said=said)
        vault.extend([doer])
        vault.notifier.mar(rid)
        vault.signals.emit_doer_event(
            "InboundWatch", "auto_admitted",
            {"grant_said": said, "schema_said": schema_said})


class GateRecheckDoer(doing.Doer):
    """Periodically re-evaluates the credential gates against live TEL state --
    the live floor for revocation. A raw TEL `rev` over peer fires no
    doer_event (unlike an inbound grant exn, which lands a note
    InboundGrantWatchDoer polls), so nothing else would deactivate the surface
    until the next vault open. Polls PluginManager.recheck_gates on the same
    cadence and for the same reason InboundGrantWatchDoer polls the notifier
    ('no push-on-arrival hook'). Cheap: an in-memory vcState read per gated
    plugin. Never raises -- a bad pass is logged and the next tick proceeds."""

    def __init__(self, app, tock: float = 2.0, **kwa):
        self.app = app
        super(GateRecheckDoer, self).__init__(tock=tock, **kwa)

    def recheck_once(self) -> None:
        try:
            pm = getattr(self.app, "plugin_manager", None)
            if pm is not None:
                pm.recheck_gates()
        except Exception:
            logger.exception("GateRecheckDoer: recheck pass failed")

    def do(self, tymth, tock=0.0, **opts):
        self.wind(tymth)
        self.tock = tock
        while True:
            yield self.tock
            self.recheck_once()
