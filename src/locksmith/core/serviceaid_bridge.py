# -*- encoding: utf-8 -*-
"""
locksmith.core.serviceaid_bridge module

Bridges keri_serviceaid's host-agnostic, serverless-friendly credential
providers (`issue_credential`/`frame_grant_for`) into Locksmith's existing Qt
doer/signal machinery, WITHOUT touching Locksmith's peer-aware delivery
(`locksmith.peer.posting.PeerAwarePoster`), which stays host-owned per the
framework spec (Sec 5.1/8).

Five pieces:

- `QtProgressSink` adapts `keri_serviceaid.progress.ProgressSink` onto
  Locksmith's `DoerSignalBridge`, so serviceaid's progress emissions surface
  as the SAME Qt events (`doer_event(doer_name, event_type, data)`) the
  gate/UI already filter on. `keri_serviceaid`'s emissions deliberately reuse
  Locksmith's existing vocabulary (`"IssueCredentialDoer"`,
  `"SendGrantDoer"`, `"AdmitDoer"`) for this exact reason.
- `serviceaid_eligible(hab)` is the envelope guard: today's serverless
  providers only support single-sig, unwitnessed identifiers. `GroupHab`
  (multisig) and witnessed habs fall back to the legacy doers.
- `ServiceaidIssueDoer`/`ServiceaidGrantDoer` are thin `hio` doers wrapping
  `issue_credential`/`frame_grant_for`. The grant doer mirrors
  `locksmith.core.ipexing.SendGrantDoer`'s framing + delivery tail
  (ipexing.py ~372-506) verbatim in shape, at full protocol parity: parse
  the framed grant into the wallet's exchanger (`app.vault.exc`, so the
  recipient's later /ipex/admit verifies), build a `PeerAwarePoster`,
  stream the credential artifacts (issuer/issuee KELs via
  `credentialing.sendArtifacts`) and chain sources, send the framed grant
  exn, extend self with a `DoDoer` wrapping `.deliver()`'s doers, wait for
  it to finish, then read `.last_outcome` for the transport channel. Only
  the exn FRAMING differs -- that comes from
  `frame_grant_for(return_raw=True)` instead of
  `keri.vc.protocoling.ipexGrantExn`.
- `ServiceaidAdmitDoer` wraps `keri_serviceaid.providers.admit_grant`, which
  already does the local admit (parse the grant's embeds, save the
  credential, frame + locally land the admit exn) and emits the legacy
  `("AdmitDoer", "admit_complete")` vocabulary via the sink -- zero new UI
  wiring. The doer then best-effort delivers the admit exn back to the
  granter over `PeerAwarePoster`: it reconstructs the admit's raw message +
  attachment from storage via `exchanging.serializeMessage(said,
  framed=True)` (NOT `exchanging.cloneMessage`, whose `pathed` return only
  carries nested embed-signature paths -- empty for a no-embeds admit exn,
  never the exn's own top-level signature attachment) and resolves the
  granter AID from the original grant's `.ked["i"]` (`cloneMessage` returns
  a plain `(serder, pathed)` 2-tuple). Delivery failure is logged, never
  fatal -- the LOCAL landing (`admit_grant` succeeding) is what gates.
- `make_issue_doer`/`make_grant_doer`/`make_admit_doer` are the routing
  chokepoint: eligible habs get a bridge doer, everyone else gets the legacy
  doer with equivalent kwargs. No behavior change for ineligible habs.
"""
from types import SimpleNamespace

from hio.base import doing
from keri import help, kering
from keri.core import parsing, serdering
from keri.peer import exchanging
from keri.vdr import credentialing

from keri_serviceaid.providers import admit_grant, frame_grant_for, issue_credential

from locksmith.core.remoting import message_version
from locksmith.peer.exposure import is_aid_peer_exposed as _is_aid_peer_exposed_by_pre
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


def is_aid_peer_exposed(hab) -> bool:
    """One-hab adapter over `locksmith.peer.exposure.is_aid_peer_exposed`'s
    real `(hby, pre)` signature (peer/exposure.py:32-48): that function
    takes the Habery to guard db-open state and re-resolve the hab from a
    prefix, but a `Hab` keeps no back-reference to its owning `Habery`
    (keripy's `habbing.BaseHab.__init__` only injects
    `db`/`ks`/`cf`/`mgr`/`rtr`/`rvy`/`kvy`/`psr` -- never the Habery
    itself), and `_inband_oobi_msgs` only ever has the hab in hand.
    `hab.db` IS the exact same `Baser` instance the Habery injects into
    every `Hab` it makes (`Habery.makeHab` passes `self.db` straight
    through unchanged), so a minimal hby-shaped stand-in exposing just
    `.db` and `.habs` -- the only two attributes the real function reads
    -- lets this delegate to the SAME check using only the hab already in
    hand, rather than reimplementing its db-open/end-record logic here.
    """
    hby_view = SimpleNamespace(db=hab.db, habs={hab.pre: hab})
    return _is_aid_peer_exposed_by_pre(hby_view, hab.pre)


def _inband_oobi_msgs(hab, settings):
    """Reply-as-OOBI for the sender itself (spec Sec 6): the two signed
    rpys (/loc/scheme by the EID, /end/role/add by the CID) that let a
    first-contact recipient verify AND reach back. The sender's KEL is
    already streamed by sendArtifacts -- only the OKEA rpys are needed.
    Empty unless the peer listener is on and this AID opted into peer
    exposure (stock wallets without peer mode are unchanged)."""
    if settings is None or not settings.enabled:
        return []
    if not is_aid_peer_exposed(hab):
        return []
    url = f"tcp://{settings.advertised_host or '127.0.0.1'}:{settings.port}"
    out = []
    for msg in (
        hab.reply(route="/loc/scheme",
                  data=dict(eid=hab.pre, scheme=kering.Schemes.tcp, url=url)),
        hab.reply(route="/end/role/add",
                  data=dict(cid=hab.pre, role=kering.Roles.peer, eid=hab.pre)),
    ):
        ims = bytearray(msg)
        serder = serdering.SerderKERI(raw=bytes(ims))
        del ims[:serder.size]
        out.append((serder, bytes(ims) if ims else None))
    return out


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

    Mirrors `SendGrantDoer`'s framing tail + delivery tail (ipexing.py
    ~372-506) verbatim in shape, at FULL protocol parity:

    - parse the freshly-framed grant into the wallet's own exchanger
      (`app.vault.exc`, ipexing.py:376) so it lands in `hby.db.exns` --
      required for the recipient's later /ipex/admit to pass
      `IpexHandler.verify`'s cloneMessage lookup (the granter-side
      round-trip);
    - stream credential artifacts (issuer KEL, issuee KEL, delegation
      chains) via `credentialing.sendArtifacts` on the same postman;
    - queue the in-band OOBI (`_inband_oobi_msgs`, Task 7, spec Sec 6):
      two signed rpys (`/loc/scheme` by the EID, `/end/role/add` by the
      CID) that let a first-contact recipient reach back, gated on the
      vault's peer-mode settings and this AID's peer exposure -- empty
      (no-op) for stock wallets without peer mode enabled;
    - stream each credential chain source (edge credentials) --
      `sendArtifacts` for the source plus the source serder + attachment;
    - send the framed grant exn last;
    - extend self with a `DoDoer` wrapping `.deliver()`'s doers, wait for
      it to finish, then emit success/failure under the SAME
      `"SendGrantDoer"` vocabulary (incl. `channel` from
      `postman.last_outcome`) the existing grant dialog
      (`ui/vault/credentials/issued/grant.py`) already filters on.

    Deliberately NOT mirrored: `SendGrantDoer`'s alias-resolution block
    (ipexing.py:317-338, `Organizer.find("alias", ...)` fallback) --
    recipients here are resolved AID prefixes by contract (the onboarding
    flow selects authorities from the EGF document, which pins AIDs).
    """

    def __init__(self, app, *, credential_said, recipient, hab_pre,
                 message: str = "", **kwa):
        self.app = app
        self.hby = app.vault.hby
        self.rgy = app.vault.rgy
        self.signal_bridge = app.vault.signals
        self.credential_said = credential_said
        self.recipient = recipient
        self.hab_pre = hab_pre
        self.message = message

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
                message=self.message,
                return_raw=True,
            )

            # Parse the freshly-framed grant into the WALLET's exchanger --
            # mirrors SendGrantDoer (ipexing.py:376). frame_grant_for does
            # NOT persist into the vault's exc; without this the grant never
            # lands in hby.db.exns, so when the recipient later sends
            # /ipex/admit, keripy's IpexHandler.verify fails its
            # cloneMessage lookup on the grant SAID and the Exchanger
            # silently drops the admit. parseOne gets a bytes() copy so
            # `raw` stays intact for the serder/attachment split below.
            parsing.Parser().parseOne(ims=bytes(raw), exc=self.app.vault.exc,
                                      version=message_version(raw))

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

            # In-band OOBI (spec Sec 6): after the KEL artifacts, before
            # the grant -- so a first-contact recipient's parser lands
            # key state, then reachability, then the exn.
            db = getattr(self.app.vault, "db", None)
            settings = db.peerSettings.get(keys=("default",)) if db is not None else None
            for oserder, oatc in _inband_oobi_msgs(hab, settings):
                postman.send(serder=oserder, attachment=oatc)

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
            message=kwargs.get("message", ""),
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


class ServiceaidAdmitDoer(doing.Doer):
    """Admits an inbound IPEX grant through keri_serviceaid's single-sig
    admit_grant (which emits the legacy ("AdmitDoer","admit_complete")
    vocabulary via the sink -- the gate and onboarding refresh react with
    zero new wiring), then best-effort delivers the admit exn back to
    the granter over the peer-aware transport. Delivery failure is
    logged, never fatal: the LOCAL landing is what gates."""

    def __init__(self, app, *, grant_said: str, hab_pre: str,
                 message: str = "", **kwa):
        self.app = app
        self.grant_said = grant_said
        self.hab_pre = hab_pre
        self.message = message
        super(ServiceaidAdmitDoer, self).__init__(**kwa)

    def do(self, tymth, tock=0.0, **opts):
        self.wind(tymth)
        self.tock = tock
        _ = (yield self.tock)
        vault = self.app.vault
        sink = QtProgressSink(vault.signals)
        hab = vault.hby.habs.get(self.hab_pre)
        try:
            admit_said = admit_grant(
                vault.hby, hab, vault.rgy,
                grant_said=self.grant_said,
                exc=vault.exc,
                message=self.message,
                sink=sink,
            )
        except Exception as e:  # noqa: BLE001
            logger.exception(f"ServiceaidAdmitDoer failed: {e}")
            sink.on_event("AdmitDoer", "admit_failed", {
                "error": str(e), "success": False,
                "grant_said": self.grant_said})
            return
        try:
            self._deliver_admit_back(hab, admit_said)
        except Exception:  # noqa: BLE001 -- courtesy ack only
            logger.exception("admit-back delivery failed (non-fatal)")
        return

    def _deliver_admit_back(self, hab, admit_said: str) -> None:
        """Best-effort courtesy delivery of the just-landed admit exn back
        to the granter.

        `exchanging.cloneMessage` returns a plain `(serder, pathed)`
        2-tuple (never an object with `.serder`/`.pathed` attributes), and
        its `pathed` only carries nested "e"-embed signature paths -- empty
        here, since an admit exn (`protocoling.ipexAdmitExn`) has no `e`
        embeds at all. It is NOT where the exn's own top-level signature
        attachment lives, so it cannot supply what `PeerAwarePoster.send`
        needs to send. `exchanging.serializeMessage(hby, said,
        framed=True)` is the primitive that reconstructs a sendable raw
        message (event body + its own signature attachment) from storage
        by SAID -- `framed=True` skips the extra attachment-group wrapper
        `serializeMessage` otherwise adds for re-embedding, since this
        message is sent individually (mirrors `ServiceaidGrantDoer`'s
        raw-splitting of `frame_grant_for(return_raw=True)`'s output).
        """
        vault = self.app.vault
        grant, _pathed = exchanging.cloneMessage(vault.hby, self.grant_said)
        if grant is None:
            raise ValueError(f"grant message {self.grant_said} not found")
        granter = grant.ked["i"]

        raw = exchanging.serializeMessage(vault.hby, admit_said, framed=True)
        if not raw:
            raise ValueError(f"admit message {admit_said} not found")
        ims = bytearray(raw)
        admit_serder = serdering.SerderKERI(raw=bytes(ims))
        del ims[:admit_serder.size]
        attachment = bytes(ims) if ims else None

        postman = PeerAwarePoster(
            hby=vault.hby, hab=hab, recp=granter,
            baser=vault.db, topic="credential")
        postman.send(serder=admit_serder, attachment=attachment)
        doer = doing.DoDoer(doers=postman.deliver())
        self.app.vault.extend([doer])


def make_admit_doer(app, hab, **kwargs):
    """Routing chokepoint for IPEX admit: eligible habs (single-sig,
    unwitnessed) get the serviceaid bridge doer; everyone else gets the
    legacy AdmitDoer with equivalent kwargs. The stock wallet's admit
    UI stays on the legacy path (spec Sec 8.2).

    Accepts the bridge doer's kwarg vocabulary: `grant_said`, `hab_pre`,
    `message`. `hab_pre` defaults to `hab.pre`, matching `make_grant_doer`.

    The legacy fallback intentionally leaves `AdmitDoer`'s `save_only` at
    its default (`False`, i.e. full send + multisig-coordination mode) --
    NOT the `save_only=True` used by accept_grant.py's offline "save for
    later" button (ipexing.py's other AdmitDoer call site). GroupHab is
    routed here specifically BECAUSE only the legacy doer can run its
    multisig coordination + send dance (`admit_grant` raises
    NotImplementedError for GroupHab); constructing it with
    `save_only=True` would silently skip exactly that behavior, making the
    fallback route pointless for the GroupHab case it exists to cover.
    """
    if serviceaid_eligible(hab):
        return ServiceaidAdmitDoer(
            app,
            grant_said=kwargs["grant_said"],
            hab_pre=kwargs.get("hab_pre") or hab.pre,
            message=kwargs.get("message", ""),
        )

    from locksmith.core.ipexing import AdmitDoer

    return AdmitDoer(
        app,
        hab_pre=kwargs.get("hab_pre") or hab.pre,
        grant_said=kwargs["grant_said"],
        message=kwargs.get("message", ""),
        signal_bridge=app.vault.signals,
    )
