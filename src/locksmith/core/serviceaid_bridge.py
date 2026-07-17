# -*- encoding: utf-8 -*-
"""
locksmith.core.serviceaid_bridge module

Bridges keri_serviceaid's host-agnostic, serverless-friendly credential
providers (`issue_credential`/`frame_grant_for`) into Locksmith's existing Qt
doer/signal machinery, WITHOUT touching Locksmith's peer-aware delivery
(`locksmith.peer.posting.PeerAwarePoster`), which stays host-owned per the
framework spec (Sec 5.1/8).

Four pieces:

- `QtProgressSink` adapts `keri_serviceaid.progress.ProgressSink` onto
  Locksmith's `DoerSignalBridge`, so serviceaid's progress emissions surface
  as the SAME Qt events (`doer_event(doer_name, event_type, data)`) the
  gate/UI already filter on. `keri_serviceaid`'s emissions deliberately reuse
  Locksmith's existing vocabulary (`"IssueCredentialDoer"`,
  `"SendGrantDoer"`) for this exact reason.
- `serviceaid_eligible(hab)` is the envelope guard: today's serverless
  providers only support single-sig, unwitnessed identifiers. `GroupHab`
  (multisig) and witnessed habs fall back to the legacy doers.
- `ServiceaidIssueDoer`/`ServiceaidGrantDoer` are thin `hio` doers wrapping
  `issue_credential`/`frame_grant_for`. The grant doer's delivery tail
  mirrors `locksmith.core.ipexing.SendGrantDoer`'s (ipexing.py ~435-506)
  verbatim in shape, at full protocol-delivery parity: build a
  `PeerAwarePoster`, stream the credential artifacts (issuer/issuee KELs
  via `credentialing.sendArtifacts`) and chain sources, send the framed
  grant exn, extend self with a `DoDoer` wrapping `.deliver()`'s doers,
  wait for it to finish, then read `.last_outcome` for the transport
  channel. Only the exn FRAMING differs -- that comes from
  `frame_grant_for(return_raw=True)` instead of
  `keri.vc.protocoling.ipexGrantExn`.
- `make_issue_doer`/`make_grant_doer` are the routing chokepoint: eligible
  habs get a bridge doer, everyone else gets the legacy doer with equivalent
  kwargs. No behavior change for ineligible habs.
"""
from hio.base import doing
from keri import help
from keri.core import serdering
from keri.vdr import credentialing

from keri_serviceaid.providers import frame_grant_for, issue_credential

from locksmith.peer.posting import PeerAwarePoster

logger = help.ogler.getLogger(__name__)


class QtProgressSink:
    """Adapts `keri_serviceaid.progress.ProgressSink` onto Locksmith's
    `DoerSignalBridge`.

    `on_event(source, event_type, data)` delegates straight through to
    `signal_bridge.emit_doer_event(source, event_type, data)` in the same
    tuple order, so serviceaid's own emissions (e.g.
    `("IssueCredentialDoer", "credential_issued", {...})`) surface as
    ordinary Qt doer events -- no new UI wiring needed.
    """

    def __init__(self, signal_bridge):
        self.signal_bridge = signal_bridge

    def on_event(self, source: str, event_type: str, data: dict) -> None:
        self.signal_bridge.emit_doer_event(source, event_type, data)


def serviceaid_eligible(hab) -> bool:
    """True iff `hab` is single-sig and unwitnessed -- the subset of
    identifiers today's serverless serviceaid providers can issue/grant for.

    Pure function. Checks `hab.__class__.__name__` rather than
    `isinstance(hab, habbing.GroupHab)` so it stays testable against a bare
    `MagicMock` with `__class__.__name__` set directly, without needing a
    real `GroupHab` instance or import.
    """
    return hab.__class__.__name__ != "GroupHab" and not hab.kever.wits


class ServiceaidIssueDoer(doing.Doer):
    """Issues a credential through `keri_serviceaid.providers.issue_credential`,
    forwarding its progress events to the Qt signal bridge via
    `QtProgressSink`.

    Eligibility (single-sig, unwitnessed hab) is the caller's job --
    see `serviceaid_eligible` / `make_issue_doer`. The issuing hab is
    resolved from the (already-seeded, per `EgfSeeder`) registry named
    `registry_name`, mirroring how the legacy `IssueCredentialDoer` resolves
    its hab from the registry rather than taking one directly.
    """

    def __init__(self, app, *, schema_said, recipient, attributes,
                 registry_name, edges=None, rules=None, **kwa):
        self.app = app
        self.hby = app.vault.hby
        self.rgy = app.vault.rgy
        self.schema_said = schema_said
        self.recipient = recipient
        self.attributes = attributes
        self.registry_name = registry_name
        self.edges = edges
        self.rules = rules
        self.credential_said = None
        super(ServiceaidIssueDoer, self).__init__(**kwa)

    def do(self, tymth, tock=0.0, **opts):
        """Generator method for serviceaid-backed credential issuance.

        Overrides `doing.Doer.do` directly (rather than delegating to a
        `doify`-wrapped helper) so it can be driven the same way a Doist
        would: `list(doer.do(tymth, tock))`.
        """
        self.wind(tymth)
        self.tock = tock
        _ = (yield self.tock)

        sink = QtProgressSink(self.app.vault.signals)

        try:
            registry = self.rgy.registryByName(self.registry_name)
            hab = registry.hab if registry is not None else None

            self.credential_said = issue_credential(
                self.hby, hab, self.rgy,
                schema_said=self.schema_said,
                recipient=self.recipient,
                attributes=self.attributes,
                registry_name=self.registry_name,
                edges=self.edges,
                rules=self.rules,
                sink=sink,
            )
        except Exception as e:
            logger.exception(f"ServiceaidIssueDoer failed: {e}")
            # Legacy event name/shape (see credentialing.py's
            # IssueCredentialDoer.issue_credential_do except-block) so the
            # existing IssueCredentialDialog._on_doer_event handler keeps
            # working unmodified against this bridge doer.
            sink.on_event(
                "IssueCredentialDoer",
                "credential_issuance_failed",
                {
                    'error': str(e),
                    'schema_said': self.schema_said,
                    'recipient_pre': self.recipient,
                    'success': False,
                },
            )

        return


class ServiceaidGrantDoer(doing.DoDoer):
    """Frames an IPEX grant for an already-issued credential via
    `keri_serviceaid.providers.frame_grant_for(return_raw=True)`, then
    delivers it through Locksmith's existing peer-aware transport
    (`PeerAwarePoster`). Only the exn FRAMING comes from the library --
    ALL delivery (artifact streaming + the grant exn itself) stays
    host-owned per spec Sec 5.1/8.

    Mirrors `SendGrantDoer`'s delivery tail (ipexing.py ~435-506) verbatim
    in shape, at FULL protocol-delivery parity:

    - stream credential artifacts (issuer KEL, issuee KEL, delegation
      chains) via `credentialing.sendArtifacts` on the same postman;
    - stream each credential chain source (edge credentials) --
      `sendArtifacts` for the source plus the source serder + attachment;
    - send the framed grant exn last;
    - extend self with a `DoDoer` wrapping `.deliver()`'s doers, wait for
      it to finish, then emit success/failure under the SAME
      `"SendGrantDoer"` vocabulary (incl. `channel` from
      `postman.last_outcome`) the existing grant dialog
      (`ui/vault/credentials/issued/grant.py`) already filters on.
    """

    def __init__(self, app, *, credential_said, recipient, hab_pre, **kwa):
        self.app = app
        self.hby = app.vault.hby
        self.rgy = app.vault.rgy
        self.signal_bridge = app.vault.signals
        self.credential_said = credential_said
        self.recipient = recipient
        self.hab_pre = hab_pre

        doers = [doing.doify(self.grantDo)]
        super(ServiceaidGrantDoer, self).__init__(doers=doers, **kwa)

    def grantDo(self, tymth, tock=0.0, **opts):
        """Generator method for framing + delivering the serviceaid grant."""
        self.wind(tymth)
        self.tock = tock
        _ = (yield self.tock)

        sink = QtProgressSink(self.signal_bridge)

        try:
            hab = self.hby.habs.get(self.hab_pre)
            if not hab:
                logger.error(f"Hab not found for prefix: {self.hab_pre}")
                sink.on_event(
                    "SendGrantDoer",
                    "send_failed",
                    {
                        'error': 'Issuer identifier not found',
                        'success': False,
                        'credential_said': self.credential_said,
                    },
                )
                return

            # Validate the credential exists -- mirrors SendGrantDoer's
            # check, and supplies the creder the artifact streaming below
            # feeds to sendArtifacts.
            creder, prefixer, seqner, saider = self.rgy.reger.cloneCred(
                said=self.credential_said
            )
            if creder is None:
                logger.error(f"Credential not found: {self.credential_said}")
                sink.on_event(
                    "SendGrantDoer",
                    "send_failed",
                    {
                        'error': f'Credential {self.credential_said} '
                                 f'not found in registry',
                        'success': False,
                        'credential_said': self.credential_said,
                    },
                )
                return

            grant_said, raw = frame_grant_for(
                self.hby, hab, self.rgy,
                credential_said=self.credential_said,
                recipient=self.recipient,
                sink=sink,
                return_raw=True,
            )

            # Split the framed message the same way keri_serviceaid's own
            # PostmanDeliverer does: serder + trailing attachment bytes.
            ims = bytearray(raw)
            serder = serdering.SerderKERI(raw=bytes(ims))
            del ims[:serder.size]
            attachment = bytes(ims) if ims else None

            postman = PeerAwarePoster(
                hby=self.hby,
                hab=hab,
                recp=self.recipient,
                baser=self.app.vault.db,
                topic="credential",
            )

            # Send credential artifacts (issuer KEL, issuee KEL, etc.) --
            # verbatim shape of SendGrantDoer's block (ipexing.py ~443-450),
            # on the SAME postman the grant travels on, so the recipient can
            # verify the grant without pre-resolved key state.
            credentialing.sendArtifacts(
                self.hby, self.rgy.reger, postman, creder, self.recipient
            )

            # Send credential chain sources (edge credentials)
            sources = self.rgy.reger.sources(self.hby.db, creder)
            for source, satc in sources:
                credentialing.sendArtifacts(
                    self.hby, self.rgy.reger, postman, source, self.recipient
                )
                postman.send(serder=source, attachment=satc)

            # Send the framed grant exn last, after everything needed to
            # verify it.
            postman.send(serder=serder, attachment=attachment)

            # Deliver all messages -- verbatim shape of SendGrantDoer's tail.
            doer = doing.DoDoer(doers=postman.deliver())
            self.extend([doer])

            while not doer.done:
                yield self.tock

            channel = (
                postman.last_outcome.value if postman.last_outcome else "mailbox"
            )
            logger.info(
                f"Grant message {grant_said} sent successfully to "
                f"{self.recipient} channel={channel}"
            )

            sink.on_event(
                "SendGrantDoer",
                "send_complete",
                {
                    'success': True,
                    'credential_said': self.credential_said,
                    'recipient': self.recipient,
                    'grant_said': grant_said,
                    'channel': channel,
                },
            )
            return

        except Exception as e:
            logger.exception(f"ServiceaidGrantDoer failed: {e}")
            sink.on_event(
                "SendGrantDoer",
                "send_failed",
                {
                    'error': str(e),
                    'success': False,
                    'credential_said': self.credential_said,
                },
            )
            return


def make_issue_doer(app, hab, **kwargs):
    """Routing chokepoint for credential issuance: eligible habs (single-sig,
    unwitnessed) get the serviceaid bridge doer; everyone else (GroupHab,
    witnessed) gets the legacy `IssueCredentialDoer` with equivalent kwargs.

    No behavior change for ineligible habs; no UI copy changes. Legacy import
    is lazy (inside the function) to avoid an import cycle between
    `serviceaid_bridge` and `credentialing`.

    Accepts the bridge doer's kwarg vocabulary: `schema_said`, `recipient`,
    `attributes`, `registry_name`, `edges`, `rules`, `codes`.
    """
    if serviceaid_eligible(hab):
        return ServiceaidIssueDoer(
            app,
            schema_said=kwargs["schema_said"],
            recipient=kwargs["recipient"],
            attributes=kwargs["attributes"],
            registry_name=kwargs["registry_name"],
            edges=kwargs.get("edges"),
            rules=kwargs.get("rules"),
        )

    from locksmith.core.credentialing import IssueCredentialDoer

    return IssueCredentialDoer(
        app,
        schema_said=kwargs["schema_said"],
        recipient_pre=kwargs["recipient"],
        attributes=kwargs["attributes"],
        edges=kwargs.get("edges"),
        rules=kwargs.get("rules"),
        codes=kwargs.get("codes"),
        signal_bridge=app.vault.signals,
    )


def make_grant_doer(app, hab, **kwargs):
    """Routing chokepoint for credential granting: eligible habs (single-sig,
    unwitnessed) get the serviceaid bridge doer; everyone else (GroupHab,
    witnessed) gets the legacy `SendGrantDoer` with equivalent kwargs.

    No behavior change for ineligible habs; no UI copy changes. Legacy import
    is lazy (inside the function) to avoid an import cycle between
    `serviceaid_bridge` and `ipexing`.

    Accepts the bridge doer's kwarg vocabulary: `credential_said`,
    `recipient`, `message`. `hab_pre` defaults to `hab.pre` -- callers
    already have `hab` (it's how they resolved eligibility) so they need not
    pass it explicitly.
    """
    if serviceaid_eligible(hab):
        return ServiceaidGrantDoer(
            app,
            credential_said=kwargs["credential_said"],
            recipient=kwargs["recipient"],
            hab_pre=kwargs.get("hab_pre") or hab.pre,
        )

    from locksmith.core.ipexing import SendGrantDoer

    return SendGrantDoer(
        app,
        hab_pre=kwargs.get("hab_pre") or hab.pre,
        credential_said=kwargs["credential_said"],
        recipient_pre=kwargs["recipient"],
        message=kwargs.get("message", ""),
        signal_bridge=app.vault.signals,
    )
