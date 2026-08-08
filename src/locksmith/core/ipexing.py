# -*- encoding: utf-8 -*-
"""
locksmith.core.ipexing module

Dialog for granting (sending or saving) issued credentials.
"""
import time

from hio.base import doing
from keri import help
from keri.app import organizing, signing, grouping, forwarding, habbing, agenting
from keri.kering import Vrsn_1_0

from locksmith.peer.posting import (
    PeerAwarePoster,
    recipient_label,
    undeliverable,
    undeliverable_reason,
    unreachable_advertisement,
)
from keri.app.notifying import Notifier
from keri.core import serdering, coring, parsing, eventing
from keri.help import helping
from keri.peer import exchanging
from keri.vc import protocoling
from keri.vdr import eventing as teventing, verifying, credentialing

from locksmith.core.remoting import message_version

logger = help.ogler.getLogger(__name__)


def _embed_serder(label, ked):
    """Version-agnostic re-serialization of a grant embed.

    ``coring.Sadder`` serializes only the library's current protocol version
    (v2 in keri 2.0.0-dev6, via ``sizeify``), so it raises
    ``Unsupported version`` on the v1 events the wallet still emits during the
    KERI v2 v1-hold. Selecting the concrete Serder by embed label instead keeps
    this version-agnostic: each Serder reads the protocol version from the ked's
    own version string, so it handles v1 today and v2 later unchanged.

    Parameters:
        label (str): grant embed label ("acdc", "anc", or "iss").
        ked (dict): the embedded key/credential event dict.

    Returns:
        Serder: SerderACDC for the ``acdc`` embed, SerderKERI otherwise.
    """
    if label == "acdc":
        return serdering.SerderACDC(sad=ked)
    return serdering.SerderKERI(sad=ked)


def _wait_for(predicate, *, timeout, tock=0.0, clock=None):
    """Cooperatively wait for ``predicate()`` to become truthy, bounded by a
    wall-clock ``timeout``.

    Yields ``tock`` back to the doist between checks (so the doer stays
    cooperative) and returns ``True`` once ``predicate()`` is truthy, or
    ``False`` if ``timeout`` seconds elapse first.

    The timeout is measured against ``clock`` (wall-clock ``time.monotonic`` by
    default) rather than by accumulating ``tock``. These waits run inside doers
    entered via ``doing.doify``, which forwards the doify default ``tock == 0.0``
    (see ``DoDoer.enter`` -> ``doer(tock=doer.tock)``); a ``timer += tock``
    accumulator therefore never advances and the guard is unreachable, so a real
    save/coordination failure hangs forever instead of failing cleanly. ``clock``
    is injectable so the timeout is deterministically testable.

    Callers that must fail on timeout branch on the return value; callers that
    merely wait "up to" the timeout (then proceed either way) ignore it.
    """
    if clock is None:  # resolved at call time so it stays monkeypatchable
        clock = time.monotonic
    start = clock()
    while not predicate():
        if clock() - start > timeout:
            return False
        yield tock
    return True


class Granter:
    """
    Granter class for handling credential granting process.
    """

    def __init__(self, hby, hab, rgy, exc=None):
        """
        Initialize Granter with the given parameters.

        Parameters:
            hby (Habery): The hby object.
            hab (Hab): The hab object.
            rgy (Regery): The rgy object.
            exc (Exchanger, optional): Existing exchanger to use. If None, creates new one.
        """
        self.hby = hby
        self.hab = hab
        self.rgy = rgy

        # Use provided exchanger or create new one
        if exc is not None:
            self.exc = exc
        else:
            # Fallback: create new resources if not provided
            notifier = Notifier(self.hby)
            mux = grouping.Multiplexor(self.hby, notifier=notifier)

            self.exc = exchanging.Exchanger(hby=self.hby, handlers=[])
            grouping.loadHandlers(self.exc, mux)
            protocoling.loadHandlers(self.hby, exc=self.exc, notifier=notifier)


    def grant(self, said, recp=None, message="", timestamp=None):
        """
        Grant a credential to the specified recipient.

        Parameters:
            said (str): The SAID of the credential to grant.
            recp (str, optional): The recipient's identifier. Defaults to None.
            message (str, optional): The message to include in the grant. Defaults to "".
            timestamp (str, optional): The timestamp for the grant. Defaults to current ISO 8601 timestamp.
        """
        timestamp = timestamp or helping.nowIso8601()

        org = organizing.Organizer(hby=self.hby)
        creder, prefixer, seqner, saider = self.rgy.reger.cloneCred(said=said)
        if creder is None:
            raise ValueError(f"invalid credential SAID to grant={said}")
    
        acdc = signing.serialize(creder, prefixer, seqner, saider)
    
        if recp is None:
            recp = creder.attrib['i'] if 'i' in creder.attrib else None
        elif recp in self.hby.kevers:
            recp = recp
        else:
            recp = org.find("alias", recp)
            if len(recp) != 1:
                raise ValueError(f"invalid recipient {recp}")
            recp = recp[0]['id']
    
        if recp is None:
            raise ValueError("unable to find recipient")
    
        iss = self.rgy.reger.cloneTvtAt(creder.said)

        iserder = serdering.SerderKERI(raw=bytes(iss))
        seqner = coring.Seqner(sn=iserder.sn)

        serder = self.hby.db.fetchLastSealingEventByEventSeal(creder.sad['i'],
                                                              seal=dict(i=iserder.pre, s=seqner.snh, d=iserder.said))
        anc = self.hby.db.cloneEvtMsg(pre=serder.pre, fn=0, dig=serder.said)

        # keripy's ipexGrantExn dropped the `reg` kwarg — receiver
        # reconstructs TEL state from iss + anc.
        exn, atc = protocoling.ipexGrantExn(hab=self.hab, recp=recp, message=message, acdc=acdc,
                                            iss=iss, anc=anc, dt=timestamp)
        msg = bytearray(exn.raw)
        msg.extend(atc)
    
        parsing.Parser().parseOne(ims=bytes(msg), exc=self.exc, version=message_version(msg))

        return msg


class Admitter:
    """
       Admitter class for handling IPEX admission process.
    """

    def __init__(self, hby, hab, rgy, exc=None, kvy=None, tvy=None, vry=None):
        """
        Initialize Admitter with the given parameters.

        Parameters:
            hby (Habery): The hby object.
            hab (Hab): The hab object.
            rgy (Regery): The rgy object.
            exc (Exchanger, optional): Existing exchanger to use. If None, creates new one.
            kvy (Kevery, optional): Existing kevery to use. If None, creates new one.
            tvy (Tevery, optional): Existing tevery to use. If None, creates new one.
            vry (Verifier, optional): Existing verifier to use. If None, creates new one.
        """
        self.hby = hby
        self.hab = hab
        self.rgy = rgy

        # Use provided resources or create new ones
        self.kvy = kvy if kvy is not None else eventing.Kevery(db=self.hby.db)
        self.tvy = tvy if tvy is not None else teventing.Tevery(db=self.hby.db, reger=self.rgy.reger)
        self.vry = vry if vry is not None else verifying.Verifier(hby=self.hby, reger=self.rgy.reger)

        # Use provided exchanger or create new one
        if exc is not None:
            self.exc = exc
        else:
            # Fallback: create new resources if not provided
            notifier = Notifier(self.hby)
            mux = grouping.Multiplexor(self.hby, notifier=notifier)

            self.exc = exchanging.Exchanger(hby=self.hby, handlers=[])
            grouping.loadHandlers(self.exc, mux)
            protocoling.loadHandlers(self.hby, exc=self.exc, notifier=notifier)


    def parse(self, ims):
        parsing.Parser().parseOne(ims=bytes(ims), exc=self.exc, version=message_version(ims))

    def admit(self, said, message="", timestamp=None):
        """
        Admit a credential based on the provided SAID.

        Parameters:
            said (str): The SAID of the credential to admit.
            message (str, optional): The message to include in the admission. Defaults to "".
            timestamp (str, optional): The timestamp for the admission. Defaults to None.
        """
        timestamp = timestamp or helping.nowIso8601()
        grant, pathed = exchanging.cloneMessage(self.hby, said)
        if grant is None:
            raise ValueError(f"exn message said={said} not found")

        route = grant.ked['r']
        if route != "/ipex/grant":
            raise ValueError(f"exn said={said} is not a grant message, route={route}")

        embeds = grant.ked['e']
        acdc = embeds["acdc"]

        # keripy's ipexGrantExn no longer emits a `reg` embed; the receiver
        # reconstructs TEL/registry state from `anc` + `iss`. Parse only the
        # labels the grant actually carries, version-agnostically (see
        # _embed_serder — coring.Sadder is v2-only and breaks the v1-hold).
        for label in ("anc", "iss", "acdc"):
            ked = embeds.get(label)
            if not ked:
                continue
            sadder = _embed_serder(label, ked)
            ims = bytearray(sadder.raw) + pathed.get(label, b'')
            parsing.Parser(
                kvy=self.kvy,
                tvy=self.tvy,
                vry=self.vry,
                version=message_version(ims),
            ).parseOne(ims=ims)

        credential_said = acdc["d"]
        if not self.rgy.reger.saved.get(keys=credential_said):
            raise ValueError(f"Credential said={credential_said} did not parse from message said={said}")

        exn, atc = protocoling.ipexAdmitExn(hab=self.hab, message=message, grant=grant, dt=timestamp)
        admin_said = exn.said
        msg = bytearray(exn.raw)
        msg.extend(atc)

        parsing.Parser().parseOne(ims=bytes(msg), exc=self.exc, version=message_version(msg))

        return admin_said, msg


class SendGrantDoer(doing.DoDoer):
    """
    Doer for sending credential grant messages via IPEX protocol.

    Handles the complete workflow:
    - Validates credential and recipient
    - Creates grant message
    - Handles multisig coordination if needed
    - Sends credential artifacts and grant to recipient
    - Signals completion to UI
    """

    def __init__(self, app, hab_pre: str, credential_said: str, recipient_pre: str,
                 message: str = "", signal_bridge=None):
        """
        Initialize the SendGrantDoer.

        Args:
            app: Application instance with vault
            hab_pre: The prefix of the local identifier (issuer/sender)
            credential_said: SAID of the credential to grant
            recipient_pre: The prefix of the recipient identifier (who the grant is for)
            message: Optional human-readable message to include
            signal_bridge: DoerSignalBridge for UI communication
        """
        self.app = app
        self.hab_pre = hab_pre
        self.credential_said = credential_said
        self.recipient_pre = recipient_pre
        self.message = message
        self.signal_bridge = signal_bridge

        self.hby = app.vault.hby
        self.rgy = app.rgy

        # Use existing vault resources instead of creating new ones
        self.exc = app.vault.exc

        doers = [doing.doify(self.sendGrantDo)]

        super(SendGrantDoer, self).__init__(doers=doers)

    def sendGrantDo(self, tymth, tock=0.0, **opts):
        """
        Generator method for sending credential grant.

        Args:
            tymth: Tymist function for time management
            tock: Initial tock value

        Yields:
            tock: Current tock value for doer scheduling
        """
        self.wind(tymth)
        self.tock = tock
        _ = (yield self.tock)

        try:
            # Get the hab
            hab = self.hby.habs.get(self.hab_pre)
            if not hab:
                logger.error(f"Hab not found for prefix: {self.hab_pre}")
                if self.signal_bridge:
                    self.signal_bridge.emit_doer_event(
                        doer_name="SendGrantDoer",
                        event_type="send_failed",
                        data={
                            'error': 'Issuer identifier not found',
                            'success': False,
                            'credential_said': self.credential_said
                        }
                    )
                return

            # Validate credential exists
            creder, prefixer, seqner, saider = self.rgy.reger.cloneCred(said=self.credential_said)
            if creder is None:
                logger.error(f"Credential not found: {self.credential_said}")
                if self.signal_bridge:
                    self.signal_bridge.emit_doer_event(
                        doer_name="SendGrantDoer",
                        event_type="send_failed",
                        data={
                            'error': f'Credential {self.credential_said} not found in registry',
                            'success': False,
                            'credential_said': self.credential_said
                        }
                    )
                return

            # Validate recipient exists
            org = organizing.Organizer(hby=self.hby)
            recp = self.recipient_pre

            if recp not in self.hby.kevers:
                # Try to find by alias
                found = org.find("alias", recp)
                if len(found) == 1:
                    recp = found[0]['id']
                else:
                    logger.error(f"Recipient not found or ambiguous: {self.recipient_pre}")
                    if self.signal_bridge:
                        self.signal_bridge.emit_doer_event(
                            doer_name="SendGrantDoer",
                            event_type="send_failed",
                            data={
                                'error': f'Recipient identifier {self.recipient_pre} not found',
                                'success': False,
                                'credential_said': self.credential_said
                            }
                        )
                    return

            logger.info(f"Sending credential {self.credential_said} to {recp}")

            # Serialize ACDC
            acdc = signing.serialize(creder, prefixer, seqner, saider)

            # Get issuance info
            iss = self.rgy.reger.cloneTvtAt(creder.said)
            iserder = serdering.SerderKERI(raw=bytes(iss))
            iseqner = coring.Seqner(sn=iserder.sn)

            # Get anchoring event
            serder = self.hby.db.fetchLastSealingEventByEventSeal(
                creder.sad['i'],
                seal=dict(i=iserder.pre, s=iseqner.snh, d=iserder.said)
            )
            anc = self.hby.db.cloneEvtMsg(pre=serder.pre, fn=0, dig=serder.said)

            # Create grant exchange message. keripy's ipexGrantExn no
            # longer accepts a `reg` kwarg — the receiver reconstructs
            # TEL state from the issuer's iss event + the anchoring KEL
            # event included here.
            timestamp = helping.nowIso8601()
            exn, atc = protocoling.ipexGrantExn(
                hab=hab,
                recp=recp,
                message=self.message,
                acdc=acdc,
                iss=iss,
                anc=anc,
                dt=timestamp
            )

            msg = bytearray(exn.raw)
            msg.extend(atc)

            # Parse locally using vault's existing exchanger (already has handlers loaded)
            parsing.Parser().parseOne(ims=bytes(msg), exc=self.exc, version=message_version(msg))

            sender = hab

            # Handle multisig coordination if this is a group hab
            if isinstance(hab, habbing.GroupHab):
                logger.info(f"Handling multisig coordination for group {hab.pre}")
                sender = hab.mhab

                # Create multisig exn wrapper
                # TRANSITIONAL (KERI v2 v1-hold): pin v1 so the outer stream
                # framing (gvrsn) uses v1 attachment count codes; the embedded
                # exn body is already v1. Without this gvrsn defaults to v2.
                # Lift with serviceaid (grep TRANSITIONAL).
                wexn, watc = grouping.multisigExn(hab, exn=msg, version=Vrsn_1_0)

                # Get signing members (excluding self)
                smids = hab.db.signingMembers(pre=hab.pre)
                smids.remove(hab.mhab.pre)

                logger.info(f"Sending to {len(smids)} multisig participants")

                # Send to each participant
                for part in smids:
                    postman = forwarding.StreamPoster(
                        hby=self.hby,
                        hab=hab.mhab,
                        recp=part,
                        topic="multisig"
                    )
                    postman.send(serder=wexn, attachment=watc)
                    doer = doing.DoDoer(doers=postman.deliver())
                    self.extend([doer])

                # Wait for multisig completion. Wall-clock timeout via _wait_for:
                # this doer runs under doify with tock == 0.0, so the old
                # `timer += self.tock` guard never advanced and was unreachable.
                completed = yield from _wait_for(
                    lambda: self.exc.complete(said=exn.said),
                    timeout=30.0, tock=self.tock)
                if not completed:
                    logger.error("Multisig coordination timeout")
                    if self.signal_bridge:
                        self.signal_bridge.emit_doer_event(
                            doer_name="SendGrantDoer",
                            event_type="send_failed",
                            data={
                                'error': 'Multisig coordination timeout',
                                'success': False,
                                'credential_said': self.credential_said
                            }
                        )
                    return

                logger.info("Multisig coordination complete")

            # Check if we are lead (always true for single-sig, determined by multisig for groups)
            if self.exc.lead(hab, said=exn.said):

                postman = PeerAwarePoster(
                    hby=self.hby,
                    hab=sender,
                    recp=recp,
                    baser=self.app.vault.db,
                    topic="credential",
                )

                # Send credential artifacts (issuer KEL, issuee KEL, etc.)
                credentialing.sendArtifacts(self.hby, self.rgy.reger, postman, creder, recp)

                # Send credential chain sources
                sources = self.rgy.reger.sources(self.hby.db, creder)
                for source, satc in sources:
                    credentialing.sendArtifacts(self.hby, self.rgy.reger, postman, source, recp)
                    postman.send(serder=source, attachment=satc)

                # Send grant message with the attachments returned by
                # ipexGrantExn (signatures). Deliberately does NOT round-trip
                # through exchanging.serializeMessage: the builder's atc is
                # already in hand and already quadlet-aligned, so re-fetching
                # would be work for nothing.
                #
                # It also used to be a CESR alignment raise — that helper seeded
                # its attachment accumulator with exn.raw (JSON, not 4-aligned)
                # before quadlet-checking. FIXED in the fork 2026-08-08
                # (keripy docs/FORK_DIVERGENCE.md, src/keri/peer/exchanging.py),
                # so the helper is safe now; this path stays as it is on the
                # simpler "already have it" ground above.
                postman.send(serder=exn, attachment=atc)

                # Deliver all messages
                doer = doing.DoDoer(doers=postman.deliver())
                self.extend([doer])

                while not doer.done:
                    yield self.tock

                channel = (
                    postman.last_outcome.value if postman.last_outcome else "mailbox"
                )

                # Loud-failure policy (never lie about delivery): a non-peer
                # outcome is only a success if the mailbox fallback actually
                # had somewhere to route — mirrors ServiceaidGrantDoer
                # (backlog/2026-07-29-grant-send-reports-success-while-undeliverable.md).
                if undeliverable(channel, sender, recp):
                    label = recipient_label(
                        self.app.vault.db, recp,
                        org=getattr(self.app.vault, "org", None))
                    advertised = unreachable_advertisement(sender.db, recp)
                    logger.warning(
                        f"peer.send.undeliverable recipient={recp} "
                        f"channel={channel} grant={exn.said} "
                        f"advertised={advertised or '-'}"
                    )
                    if self.signal_bridge:
                        data = {
                            'error': undeliverable_reason(label, advertised),
                            'success': False,
                            'credential_said': self.credential_said,
                            'recipient': recp,
                            'grant_said': exn.said,
                            'channel': channel,
                            'undeliverable': True,
                        }
                        if advertised:
                            data['advertised_host'] = advertised
                        self.signal_bridge.emit_doer_event(
                            doer_name="SendGrantDoer",
                            event_type="send_failed",
                            data=data,
                        )
                    return

                logger.info(
                    f"Grant message {exn.said} sent successfully to {recp} "
                    f"channel={channel}"
                )

                # Signal success
                if self.signal_bridge:
                    self.signal_bridge.emit_doer_event(
                        doer_name="SendGrantDoer",
                        event_type="send_complete",
                        data={
                            'success': True,
                            'credential_said': self.credential_said,
                            'recipient': recp,
                            'grant_said': exn.said,
                            'channel': channel,
                        }
                    )
            else:
                logger.info("Not lead in multisig group, grant will be sent by lead")
                # Still signal success since our part is done
                if self.signal_bridge:
                    self.signal_bridge.emit_doer_event(
                        doer_name="SendGrantDoer",
                        event_type="send_complete",
                        data={
                            'success': True,
                            'credential_said': self.credential_said,
                            'recipient': recp,
                            'grant_said': exn.said,
                            'note': 'Multisig coordination complete, lead will send'
                        }
                    )

            return

        except Exception as e:
            logger.exception(f"SendGrantDoer failed: {e}")

            if self.signal_bridge:
                self.signal_bridge.emit_doer_event(
                    doer_name="SendGrantDoer",
                    event_type="send_failed",
                    data={
                        'error': str(e),
                        'success': False,
                        'credential_said': self.credential_said
                    }
                )
            return


def _send_attachment(hab, exn, atc, hby):
    """Attachment bytes for the outbound admit exn.

    Single-sig: the builder's ``atc`` (from ``protocoling.ipexAdmitExn``) is already
    complete and CESR quadlet-aligned, so use it directly — mirrors the grant-send
    path. Group (multisig): the fully-aggregated signatures are written to the db
    during coordination, so re-fetch the messagized exn and strip the serder to get
    just the aggregated attachment.

    The old code always re-fetched (``serializeMessage(...)`` then ``del
    gatc[:exn.size]``), which crashed on a ``(None, None)`` not-found tuple and could
    emit a non-quadlet-aligned attachment ("nonintegral quadlets"). BOTH of those
    were keripy defects and both are FIXED in the fork as of 2026-08-08 (see
    ``keripy docs/FORK_DIVERGENCE.md`` → ``src/keri/peer/exchanging.py``): the
    helper now returns a bare ``None`` when the exn is absent, and its ``framed=False``
    layout is ``[body][counter][attachments]`` — which is what makes the
    ``del gatc[:exn.size]`` below land exactly on the counter instead of mid-body.
    The single-sig branch still short-circuits, on the "already have it" ground
    above rather than on distrust of the helper.
    """
    if isinstance(hab, habbing.GroupHab):
        gatc = exchanging.serializeMessage(hby, exn.said)
        del gatc[:exn.size]
        return gatc
    return atc


class AdmitDoer(doing.DoDoer):
    """
    Doer for admitting credentials from IPEX grant messages.

    Handles the complete workflow:
    - Queries witnesses for latest KEL/Registry
    - Parses and validates the grant message
    - Waits for credential to be saved
    - Handles multisig coordination if needed
    - Sends admit message to grantor
    - Signals completion to UI
    """

    def __init__(self, app, hab_pre: str, grant_said: str, message: str = "",
                 save_only: bool = False, signal_bridge=None):
        """
        Initialize the AdmitDoer.

        Args:
            app: Application instance with vault
            hab_pre: The prefix of the local identifier (recipient)
            grant_said: SAID of the grant message to admit
            message: Optional response message to send back
            save_only: If True, only saves admit locally without sending
            signal_bridge: DoerSignalBridge for UI communication
        """
        self.app = app
        self.hab_pre = hab_pre
        self.grant_said = grant_said
        self.message = message
        self.save_only = save_only
        self.signal_bridge = signal_bridge

        self.hby = app.vault.hby
        self.rgy = app.rgy

        # Use existing vault resources
        self.exc = app.vault.exc
        self.kvy = app.vault.kvy if hasattr(app.vault, 'kvy') else eventing.Kevery(db=self.hby.db)
        self.tvy = app.vault.tvy if hasattr(app.vault, 'tvy') else teventing.Tevery(db=self.hby.db, reger=self.rgy.reger)
        self.vry = app.vault.vry if hasattr(app.vault, 'vry') else verifying.Verifier(hby=self.hby, reger=self.rgy.reger)

        # For witness querying
        self.witq = agenting.WitnessInquisitor(hby=self.hby)

        doers = [self.witq, doing.doify(self.admitDo)]

        super(AdmitDoer, self).__init__(doers=doers)

    def admitDo(self, tymth, tock=0.0, **opts):
        """
        Generator method for admitting credential.

        Args:
            tymth: Tymist function for time management
            tock: Initial tock value

        Yields:
            tock: Current tock value for doer scheduling
        """
        self.wind(tymth)
        self.tock = tock
        _ = (yield self.tock)

        try:
            # Get the hab
            hab = self.hby.habs.get(self.hab_pre)
            if not hab:
                logger.error(f"Hab not found for prefix: {self.hab_pre}")
                if self.signal_bridge:
                    self.signal_bridge.emit_doer_event(
                        doer_name="AdmitDoer",
                        event_type="admit_failed",
                        data={
                            'error': 'Recipient identifier not found',
                            'success': False,
                            'grant_said': self.grant_said
                        }
                    )
                return

            # Clone the grant message
            grant, pathed = exchanging.cloneMessage(self.hby, self.grant_said)
            if grant is None:
                logger.error(f"Grant message not found: {self.grant_said}")
                if self.signal_bridge:
                    self.signal_bridge.emit_doer_event(
                        doer_name="AdmitDoer",
                        event_type="admit_failed",
                        data={
                            'error': f'Grant message {self.grant_said} not found',
                            'success': False,
                            'grant_said': self.grant_said
                        }
                    )
                return

            # Validate it's a grant message
            route = grant.ked.get('r')
            if route != "/ipex/grant":
                logger.error(f"Not a grant message, route: {route}")
                if self.signal_bridge:
                    self.signal_bridge.emit_doer_event(
                        doer_name="AdmitDoer",
                        event_type="admit_failed",
                        data={
                            'error': f'Message is not a grant (route: {route})',
                            'success': False,
                            'grant_said': self.grant_said
                        }
                    )
                return

            # Extract embeds
            embeds = grant.ked.get('e', {})
            acdc = embeds.get("acdc", {})
            issr = acdc.get('i', '')

            logger.info(f"Processing grant from issuer: {issr}")
            # TODO implement this or similar logic, as written this may breaks non-witnessed admissions
            # # Signal progress: querying witnesses
            # if self.signal_bridge:
            #     self.signal_bridge.emit_doer_event(
            #         doer_name="AdmitDoer",
            #         event_type="progress",
            #         data={
            #             'message': 'Querying witnesses for latest updates...',
            #             'grant_said': self.grant_said
            #         }
            #     )
            #
            # # Query witnesses for latest KEL
            # self.witq.query(src=hab.pre, pre=issr)
            #
            # # Query for registry if credential has one
            # if "ri" in acdc:
            #     self.witq.telquery(src=hab.pre, wits=hab.kevers[issr].wits,
            #                       ri=acdc["ri"], i=acdc["d"])
            #
            # Wait (up to a wall-clock timeout) for the issuer's KEL to arrive,
            # then proceed either way. Bounded via _wait_for because this doer
            # runs under doify with tock == 0.0: the old `while timer < timeout`
            # with `timer += self.tock` never advanced, so absent the KEL it
            # spun for the whole run instead of giving up after ~5s.
            yield from _wait_for(
                lambda: issr in self.hby.kevers, timeout=5.0, tock=self.tock)

            # Signal progress: parsing credential
            if self.signal_bridge:
                self.signal_bridge.emit_doer_event(
                    doer_name="AdmitDoer",
                    event_type="progress",
                    data={
                        'message': 'Parsing credential data...',
                        'grant_said': self.grant_said
                    }
                )

            # Parse embedded messages (skip "reg" as per KERIpy). Re-serialize
            # version-agnostically (see _embed_serder — coring.Sadder is v2-only
            # and breaks the v1-hold).
            for label in ("anc", "iss", "acdc"):
                ked = embeds.get(label)
                if ked:
                    sadder = _embed_serder(label, ked)
                    ims = bytearray(sadder.raw) + pathed.get(label, b'')
                    parsing.Parser(
                        kvy=self.kvy,
                        tvy=self.tvy,
                        vry=self.vry,
                        version=message_version(ims),
                    ).parseOne(ims=ims)

            # Get credential SAID
            credential_said = acdc.get("d", "")

            # Wait for credential to be saved. Wall-clock timeout via _wait_for:
            # this doer runs under doify with tock == 0.0, so the old
            # `timer += self.tock` guard never fired and a real save failure
            # hung forever instead of emitting admit_failed (2026-07-18 demo).
            logger.info(f"Waiting for credential {credential_said} to be saved...")
            saved = yield from _wait_for(
                lambda: self.rgy.reger.saved.get(keys=credential_said),
                timeout=10.0, tock=self.tock)
            if not saved:
                logger.error("Timeout waiting for credential to be saved")
                if self.signal_bridge:
                    self.signal_bridge.emit_doer_event(
                        doer_name="AdmitDoer",
                        event_type="admit_failed",
                        data={
                            'error': 'Timeout processing credential',
                            'success': False,
                            'grant_said': self.grant_said
                        }
                    )
                return

            logger.info(f"Credential {credential_said} saved successfully")

            # Create admit message
            timestamp = helping.nowIso8601()
            exn, atc = protocoling.ipexAdmitExn(
                hab=hab,
                message=self.message,
                grant=grant,
                dt=timestamp
            )

            admin_said = exn.said
            msg = bytearray(exn.raw)
            msg.extend(atc)

            # Parse locally
            parsing.Parser().parseOne(ims=bytes(msg), exc=self.exc, version=message_version(msg))

            # If save-only mode, we're done
            if self.save_only:
                logger.info(f"Admit message created (save-only): {admin_said}")
                if self.signal_bridge:
                    self.signal_bridge.emit_doer_event(
                        doer_name="AdmitDoer",
                        event_type="admit_complete",
                        data={
                            'success': True,
                            'grant_said': self.grant_said,
                            'admit_said': admin_said,
                            'admit_message': bytes(msg),
                            'save_only': True,
                            'credential_said': credential_said,
                        }
                    )
                return

            # Signal progress: handling multisig if needed
            sender = hab
            recp = grant.ked.get('i', '')  # Grantor is recipient of admit

            # Handle multisig coordination if this is a group hab
            if isinstance(hab, habbing.GroupHab):
                logger.info(f"Handling multisig coordination for group {hab.pre}")

                if self.signal_bridge:
                    self.signal_bridge.emit_doer_event(
                        doer_name="AdmitDoer",
                        event_type="progress",
                        data={
                            'message': 'Coordinating with multisig members...',
                            'grant_said': self.grant_said
                        }
                    )

                sender = hab.mhab

                # Create multisig exn wrapper
                # TRANSITIONAL (KERI v2 v1-hold): pin v1 so the outer stream
                # framing (gvrsn) uses v1 attachment count codes; the embedded
                # exn body is already v1. Without this gvrsn defaults to v2.
                # Lift with serviceaid (grep TRANSITIONAL).
                wexn, watc = grouping.multisigExn(hab, exn=msg, version=Vrsn_1_0)

                # Get signing members (excluding self)
                smids = hab.db.signingMembers(pre=hab.pre)
                smids.remove(hab.mhab.pre)

                logger.info(f"Sending to {len(smids)} multisig participants")

                # Send to each participant
                for part in smids:
                    postman = forwarding.StreamPoster(
                        hby=self.hby,
                        hab=hab.mhab,
                        recp=part,
                        topic="multisig"
                    )
                    postman.send(serder=wexn, attachment=watc)
                    doer = doing.DoDoer(doers=postman.deliver())
                    self.extend([doer])

                # Wait for multisig completion. Wall-clock timeout via _wait_for
                # (doify tock == 0.0 makes a `timer += self.tock` guard unreachable).
                completed = yield from _wait_for(
                    lambda: self.exc.complete(said=exn.said),
                    timeout=30.0, tock=self.tock)
                if not completed:
                    logger.error("Multisig coordination timeout")
                    if self.signal_bridge:
                        self.signal_bridge.emit_doer_event(
                            doer_name="AdmitDoer",
                            event_type="admit_failed",
                            data={
                                'error': 'Multisig coordination timeout',
                                'success': False,
                                'grant_said': self.grant_said
                            }
                        )
                    return

                logger.info("Multisig coordination complete")

            # Check if we are lead (always true for single-sig, determined by multisig for groups)
            if self.exc.lead(hab, said=exn.said):
                logger.info(f"Sending admit message to {recp}")

                if self.signal_bridge:
                    self.signal_bridge.emit_doer_event(
                        doer_name="AdmitDoer",
                        event_type="progress",
                        data={
                            'message': f'Sending admit message to grantor...',
                            'grant_said': self.grant_said
                        }
                    )

                # Send admit message to grantor
                postman = PeerAwarePoster(
                    hby=self.hby,
                    hab=sender,
                    recp=recp,
                    baser=self.app.vault.db,
                    topic="credential",
                )

                # Send admit exn with the builder's own attachment (single-sig) or
                # the aggregated multisig signatures (group hab). See _send_attachment.
                postman.send(serder=exn,
                             attachment=_send_attachment(hab, exn, atc, self.hby))

                # Deliver message
                doer = doing.DoDoer(doers=postman.deliver())
                self.extend([doer])

                while not doer.done:
                    yield self.tock

                logger.info(f"Admit message {exn.said} sent successfully to {recp}")

                # Signal success
                if self.signal_bridge:
                    self.signal_bridge.emit_doer_event(
                        doer_name="AdmitDoer",
                        event_type="admit_complete",
                        data={
                            'success': True,
                            'grant_said': self.grant_said,
                            'admit_said': admin_said,
                            'grantor': recp,
                            'credential_said': credential_said,
                        }
                    )
            else:
                logger.info("Not lead in multisig group, admit will be sent by lead")
                # Still signal success since our part is done
                if self.signal_bridge:
                    self.signal_bridge.emit_doer_event(
                        doer_name="AdmitDoer",
                        event_type="admit_complete",
                        data={
                            'success': True,
                            'grant_said': self.grant_said,
                            'admit_said': admin_said,
                            'note': 'Multisig coordination complete, lead will send',
                            'credential_said': credential_said,
                        }
                    )

            return

        except Exception as e:
            logger.exception(f"AdmitDoer failed: {e}")

            if self.signal_bridge:
                self.signal_bridge.emit_doer_event(
                    doer_name="AdmitDoer",
                    event_type="admit_failed",
                    data={
                        'error': str(e),
                        'success': False,
                        'grant_said': self.grant_said
                    }
                )
            return
