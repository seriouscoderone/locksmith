# -*- encoding: utf-8 -*-
"""Exchange round-trip end-to-end (Plan B Task 12): the sub-project's
automated acceptance for spec §11-12 minus live TCP.

WHAT THIS PROVES
----------------
Two halves of the HOA #2 exchange plumbing, in-process, no sockets, no
subprocesses, transport mocked at the ``PeerAwarePoster`` seam:

PART 1 — first-contact registration (``test_first_contact_...``):
  The carrier's REAL outbound byte stream — assembled exactly as
  ``ServiceaidGrantDoer`` queues it (KEL artifacts via
  ``credentialing.sendArtifacts`` → in-band OOBI rpys via
  ``_inband_oobi_msgs`` → the application grant exn) — is captured off a
  stubbed poster and fed through a DOI-side Reactant-shaped parser
  (``turret/directing.py:536-560`` wiring) whose exchanger is a REAL
  ``PeerExchangerShim(open_inbound=True, on_first_contact=recorder)``. We
  assert the unknown carrier lands in ``doi_hby.kevers``, its tcp loc lands
  in ``doi_hby.db.locs``, ``on_first_contact`` fired with the carrier's url,
  and the grant exn reached the DOI exchanger (recoverable via
  ``cloneMessage``). This is the first test to exercise
  ``_inband_oobi_msgs``'s real serder/attachment split against a real hab
  (see ``tests/core/test_inband_oobi.py``'s deferral note).

PART 2 — return-grant → auto-admit → LICENSED (``test_return_grant_...``):
  The DOI issues the ``carrier_license`` carrying the required NI2I
  ``application`` edge (per acdc-design), frames the return grant, and its
  bytes are delivered into the carrier vault's parser (grant note lands via
  the vault notifier + IPEX handlers). ``InboundGrantWatchDoer.scan_once``
  matches the expected grant and auto-admits through ``make_admit_doer`` →
  ``ServiceaidAdmitDoer`` → ``admit_grant``; ``("AdmitDoer",
  "admit_complete")`` fires; the gate re-poll
  (``PluginManager._repoll_after_admit``, QTimer driven synchronously) is
  genuinely exercised (``_held_credentials`` reports the license
  ``chain_verified=False`` for the first two evaluations post-admit before
  delegating to the real projection), and only then reveals the carrier
  surface; ``derive_role_states`` reads ACTIVE (Task 11 — the old
  page-global ``derive_state`` shim is gone) and the
  ``HoaNotificationsPage`` shows the arrival entry.

LAX CONTINGENCY OUTCOME (brief Step 2)
--------------------------------------
The contingency did NOT trigger. Under ``Kevery(lax=False, local=False)``
— the exact strict wiring the production ``turret.directing.Reactant``
ships — the unknown carrier's inception event is accepted directly
(keripy ``eventing.py`` processes a first-seen ``icp``/``dip`` for an
unknown prefix by constructing its ``Kever`` with no ``lax`` gate; the
``lax`` gates guard only receipts, own-witness/receiptor short-circuits,
and ``/ksn`` key-state-notice trust — none of which apply to a plain
first-contact KEL), and the ``/loc/scheme`` reply is accepted by BADA
signature verification against that now-known key state (also no ``lax``
gate). So no open-inbound lax flag needed threading through
``PeerDoer`` → ``Directant`` → ``Reactant``; the strict parser lands the
first-contact KEL + loc as-is. This is asserted below with the production
``lax=False`` value (``_STRICT_KEVERY_LAX``), so a future keripy change
that started escrowing unknown first-contact KELs would fail here loudly.

PRODUCTION FIX MADE (brief: in-scope round-trip fix)
----------------------------------------------------
``keri_serviceaid.providers.admit.admit_grant`` was a no-op on the credential
save: its docstring says it was lifted from ``locksmith.core.ipexing.
Admitter`` (whose ``__init__`` defaulted ``kvy``/``tvy``/``vry`` to fresh
store-bound processors when the caller passed none), but the lift dropped
that defaulting. ``ServiceaidAdmitDoer`` calls ``admit_grant`` WITHOUT those
processors (and ``tests/core/test_serviceaid_admit.py`` pins that contract),
so the grant's ``anc``/``iss``/``acdc`` embeds — the ONLY place the ACDC body
travels in an IPEX grant — were parsed with ``kvy=tvy=vry=None`` (a no-op),
the credential never reached ``reger.saved``, and the immediate
``reger.saved`` check raised ``"Credential ... did not parse"`` on every real
admit. Restored the lift-source defaulting in ``admit_grant`` (reproduced
first — see the task report). With the deps present (KEL + TEL streamed
ahead of the grant, NI2I edge target self-held) the embed parse now saves the
license synchronously; this test is the end-to-end regression for that fix.

V1 PROTOCOL PIN (CRITICAL fixture rule)
---------------------------------------
Every hab/registry here is v1-pinned (``_make_party`` /
``credentialing`` fixtures pin ``Vrsn_1_0``); every cross-party parser is
``version=Vrsn_1_0``. A v2 hab silently breaks the v1-pinned parsers.
"""
from __future__ import annotations

import dataclasses
from types import SimpleNamespace
from unittest.mock import patch

from hio.base import doing
from keri import kering
from keri.app import grouping, notifying, signaling
from keri.core import eventing, parsing, routing, serdering
from keri.help import helping
from keri.kering import Vrsn_1_0
from keri.peer import exchanging
from keri.vc import protocoling
from keri.vdr import eventing as teventing

import locksmith.core.serviceaid_bridge as serviceaid_bridge
from locksmith.core.credentialing import Registrar, outputKEL, outputTEL
from locksmith.core.egf_seeding import make_hoa_resolver
from locksmith.core.inbound_watch import InboundGrantWatchDoer
from locksmith.core.serviceaid_bridge import ServiceaidGrantDoer
from locksmith.core.signals import DoerSignalBridge
from locksmith.core import branding
from locksmith.db.basing import LocksmithBaser
from locksmith.peer.allowlist import PeerAllowlist
from locksmith.peer.publishing import PublishPeerRoleDoer
from locksmith.peer.records import PeerModeSettings
from locksmith.peer.shim import PeerExchangerShim
from locksmith.ui.hoa.notifications_page import HoaNotificationsPage
from locksmith.ui.onboarding.role_states import RoleStatus, derive_role_states

# Reuse the scaffold e2e's proven in-process fixture family (same test
# package): schemas + attribute blocks, the real no-backer issuance recipe,
# the mocked-transport disclose/admit halves, the carrier PluginManager
# builder, and the haberies teardown fixture (imported so pytest registers
# it here too).
from tests.integration.test_carrier_gate_e2e import (  # noqa: F401 (haberies)
    APP_SCHEMA_SAID,
    APPLICATION_ATTRS,
    LICENSE_ATTRS,
    LICENSE_SCHEMA_SAID,
    _admit,
    _build_carrier_manager,
    _disclose,
    _issue,
    _make_party,
    _vault,
    haberies,
)
# Reuse the onboarding e2e's REAL-bundled-EGF test-variant injector (authority
# AID = the in-process DOI's real AID). Same module/package import.
from tests.integration.test_onboarding_e2e import _inject_test_brand

# The production Reactant ships this Kevery lax value (turret/directing.py:
# 538). Pinned as a constant so the lax-contingency finding (that the strict
# parser lands the first-contact KEL as-is — see module docstring) is asserted
# against the exact production value, not an incidental True.
_STRICT_KEVERY_LAX = False

# The carrier's advertised peer endpoint (no socket is bound — the loc only
# travels in the in-band /loc/scheme rpy the first-contact recipient reads).
_CARRIER_PEER_PORT = 5622
_CARRIER_PEER_URL = f"tcp://127.0.0.1:{_CARRIER_PEER_PORT}"


# ---------------------------------------------------------------------------
# Mocked-transport posters (the ONLY stub on either party's side).
# ---------------------------------------------------------------------------

class CapturePoster:
    """``PeerAwarePoster`` stand-in that MATERIALIZES the outbound stream.

    ``ServiceaidGrantDoer`` builds one poster per grant and calls ``send``
    for every artifact in wire order (KEL events, in-band OOBI rpys, chain
    sources, then the grant exn last). Concatenating ``serder.raw +
    attachment`` per send — exactly what ``keri_serviceaid``'s own
    ``PostmanDeliverer`` puts on the wire — reconstructs the byte stream a
    real TCP peer would receive. ``deliver()`` returns no doers and
    ``last_outcome=None`` drives the grant doer's documented mailbox-channel
    fallback."""

    instances: list = []

    def __init__(self, **kwa):
        self.kwa = kwa
        self.sent: list = []
        self.stream = bytearray()
        self.last_outcome = None
        CapturePoster.instances.append(self)

    def send(self, serder=None, attachment=None, **kwa):
        self.sent.append((serder, attachment))
        self.stream.extend(bytes(serder.raw))
        if attachment:
            self.stream.extend(bytes(attachment))

    def deliver(self):
        return []


class SilentPoster:
    """Records nothing, delivers nothing — the admit-back courtesy seam
    (``ServiceaidAdmitDoer._deliver_admit_back``) is best-effort and out of
    this test's scope; the LOCAL admit landing is what gates."""

    def __init__(self, **kwa):
        self.last_outcome = None

    def send(self, serder=None, attachment=None, **kwa):
        pass

    def deliver(self):
        return []


# ---------------------------------------------------------------------------
# In-process vault harnesses — REAL hio DoDoers exposing exactly the surface
# the flow objects consume, pumped by a real virtual-time Doist.
# ---------------------------------------------------------------------------

class GrantingVault(doing.DoDoer):
    """The carrier's vault while it GRANTS (part 1): the real scheduling
    seam (``extend``), a real Qt signal bridge, a real Exchanger (so the
    framed grant lands in ``hby.db.exns``), and a real ``LocksmithBaser``
    (``db``) holding the peer-mode settings ``ServiceaidGrantDoer`` reads to
    decide whether to queue the in-band OOBI."""

    def __init__(self, hby, rgy, lockdb):
        self.hby = hby
        self.rgy = rgy
        self.db = lockdb
        self.signals = DoerSignalBridge()
        self.exc = exchanging.Exchanger(hby=hby, handlers=[])
        super().__init__(doers=[], always=True)


class AdmittingVault(doing.DoDoer):
    """The carrier's vault while it ADMITS an inbound grant (part 2): adds a
    real ``Notifier`` + IPEX handler set (so the delivered grant exn produces
    the unread ``/exn/ipex/grant`` note ``InboundGrantWatchDoer`` polls) on
    top of the granting surface. ``db`` is a real ``LocksmithBaser`` for the
    admit-back poster seam."""

    def __init__(self, hby, rgy, lockdb):
        self.hby = hby
        self.rgy = rgy
        self.db = lockdb
        self.signals = DoerSignalBridge()
        self.signaler = signaling.Signaler()
        self.notifier = notifying.Notifier(hby=hby, signaler=self.signaler)
        self.exc = exchanging.Exchanger(hby=hby, handlers=[])
        protocoling.loadHandlers(hby=hby, exc=self.exc, notifier=self.notifier)
        super().__init__(doers=[], always=True)


# ---------------------------------------------------------------------------
# Shared helpers.
# ---------------------------------------------------------------------------

def _open_lockdb(tmp_path, request, name):
    db = LocksmithBaser(name=name, headDirPath=str(tmp_path / name),
                        reopen=True, temp=True)
    request.addfinalizer(lambda: db.close(clear=True))
    return db


def _event_collector(vault):
    events: list = []
    vault.signals.doer_event.connect(
        lambda name, etype, data: events.append((name, etype, data)))

    def first(doer_name, event_type):
        return next((d for n, t, d in events
                     if n == doer_name and t == event_type), None)

    return events, first


def _run(vault, request):
    doist = doing.Doist(real=False, tock=0.03125)
    deeds = doist.enter(doers=[vault])
    request.addfinalizer(lambda: doist.exit(deeds=deeds))

    def pump(until, what, rounds=300):
        for _ in range(rounds):
            if until():
                return
            doist.recur(deeds=deeds)
        raise AssertionError(f"doist did not reach: {what}")

    return pump


def _expose_peer_aid(hby, hab, request):
    """Publish the AID's peer role locally (witnessless → lands the
    /end/role/add + /loc/scheme rpys in hab.db so ``is_aid_peer_exposed``
    reads True and ``_inband_oobi_msgs`` proceeds). Driven on its own
    short-lived Doist to completion."""
    doer = PublishPeerRoleDoer(hby, hab, _CARRIER_PEER_URL, allow=True)
    doist = doing.Doist(real=False, tock=0.03125)
    deeds = doist.enter(doers=[doer])
    try:
        for _ in range(64):
            if doer.completed:
                return
            doist.recur(deeds=deeds)
        raise AssertionError("peer-role publish did not complete")
    finally:
        doist.exit(deeds=deeds)


# ---------------------------------------------------------------------------
# PART 1 — first-contact registration through the strict Reactant parser.
# ---------------------------------------------------------------------------

def test_first_contact_registers_unknown_carrier_and_delivers_grant(
        monkeypatch, tmp_path, request, qapp, haberies):
    # ---- parties (v1-pinned) ---------------------------------------------
    # Carrier: self-issues its application, then grants it to the DOI.
    hby_c, hab_c, rgy_c = _make_party("t12p1_carrier", b"t12p1_carrier_01234")
    haberies.append(hby_c)
    # DOI: the first-contact recipient — never seen the carrier before.
    hby_d, hab_d, rgy_d = _make_party("t12p1_doi", b"t12p1_doi_012345678")
    haberies.append(hby_d)

    app_said = _issue(hby_c, hab_c, rgy_c, schema_said=APP_SCHEMA_SAID,
                      recipient=hab_c.pre, attributes=APPLICATION_ATTRS,
                      registry_name="carrier-apps")

    # ---- carrier vault: peer mode ON + this AID exposed -------------------
    carrier_lockdb = _open_lockdb(tmp_path, request, "t12p1_carrier_lock")
    carrier_lockdb.peerSettings.pin(keys=("default",), val=PeerModeSettings(
        enabled=True, port=_CARRIER_PEER_PORT, advertised_host="127.0.0.1"))
    _expose_peer_aid(hby_c, hab_c, request)

    vault = GrantingVault(hby_c, rgy_c, carrier_lockdb)
    app = SimpleNamespace(vault=vault)
    _events, first = _event_collector(vault)
    pump = _run(vault, request)

    # ---- capture the carrier's REAL outbound grant stream -----------------
    CapturePoster.instances.clear()
    monkeypatch.setattr(serviceaid_bridge, "PeerAwarePoster", CapturePoster)

    grant_doer = ServiceaidGrantDoer(
        app, credential_said=app_said, recipient=hab_d.pre, hab_pre=hab_c.pre)
    vault.extend([grant_doer])
    pump(lambda: (first("SendGrantDoer", "send_complete")
                  or first("SendGrantDoer", "send_failed")),
         "carrier grant framed + streamed")
    sent = first("SendGrantDoer", "send_complete")
    assert sent is not None, f"grant failed: {first('SendGrantDoer', 'send_failed')}"
    grant_said = sent["grant_said"]

    assert CapturePoster.instances, "grant must use the poster seam"
    poster = CapturePoster.instances[-1]
    stream = bytes(poster.stream)
    # The grant exn is streamed LAST, after everything needed to verify it.
    assert poster.sent[-1][0].said == grant_said
    # The in-band OOBI rpys were queued (peer mode on + AID exposed): the
    # stream carries a /loc/scheme and an /end/role/add reply.
    routes = [s.ked.get("r") for s, _atc in poster.sent
              if isinstance(getattr(s, "ked", None), dict)]
    assert "/loc/scheme" in routes and "/end/role/add" in routes

    # ---- DOI-side first-contact parser (turret Reactant wiring) -----------
    doi_lockdb = _open_lockdb(tmp_path, request, "t12p1_doi_lock")
    allowlist = PeerAllowlist(doi_lockdb)  # empty — carrier is unknown
    assert not allowlist.contains(hab_c.pre)

    doi_exc = exchanging.Exchanger(hby=hby_d, handlers=[])
    recorder: list = []
    shim = PeerExchangerShim(
        allowlist,
        doi_exc,
        is_destination_exposed=lambda aid: aid == hab_d.pre,
        hby=hby_d,
        open_inbound=True,
        on_first_contact=lambda aid, url: recorder.append((aid, url)),
    )

    rvy = routing.Revery(db=hby_d.db)
    kvy = eventing.Kevery(db=hby_d.db, lax=_STRICT_KEVERY_LAX, local=False, rvy=rvy)
    kvy.registerReplyRoutes(router=rvy.rtr)
    tvy = teventing.Tevery(db=hby_d.db, reger=rgy_d.reger, local=False, rvy=rvy)
    tvy.registerReplyRoutes(router=rvy.rtr)
    parser = parsing.Parser(framed=True, kvy=kvy, tvy=tvy, exc=shim, rvy=rvy,
                            version=Vrsn_1_0)
    parser.parse(ims=bytearray(stream))
    for _ in range(40):
        kvy.processEscrows()
        tvy.processEscrows()

    # ---- assertions: strict parser landed first contact as-is -------------
    # (a) the unknown carrier's KEL verified into the DOI's key state.
    assert hab_c.pre in hby_d.kevers, (
        "strict lax=False parser must land the first-contact carrier KEL "
        "(lax contingency did NOT trigger)")
    # (b) its advertised tcp reach-back loc landed.
    loc = hby_d.db.locs.get(keys=(hab_c.pre, kering.Schemes.tcp))
    assert loc is not None and loc.url == _CARRIER_PEER_URL
    # (c) on_first_contact fired exactly once with the carrier + its url.
    assert recorder == [(hab_c.pre, _CARRIER_PEER_URL)]
    # (d) the grant exn passed both shim gates into the DOI exchanger.
    exn, _pathed = exchanging.cloneMessage(hby_d, grant_said)
    assert exn is not None and exn.ked["r"] == "/ipex/grant"
    assert exn.ked["a"]["i"] == hab_d.pre  # addressed to the DOI


# ---------------------------------------------------------------------------
# PART 2 — return grant → auto-admit → LICENSED (+ re-poll + notifications).
# ---------------------------------------------------------------------------

def _reach_licensed(monkeypatch, tmp_path, request, qapp, haberies) -> dict:
    """Shared "reach LICENSED" setup + admit flow (part 2's original body).

    Builds both parties, the REAL bundled EGF (test variant), the carrier's
    self-issued application, the DOI's edged ``carrier_license``, the
    carrier's ADMIT vault + manager, and drives the full return-grant ->
    auto-admit -> gate-open -> LICENSED sequence (including the re-poll
    exercise). Extracted so the LICENSED -> REVOKED test (part 3) can start
    from the exact same end-state as part 2's own acceptance without
    duplicating ~140 lines of harness wiring. Returns every handle either
    caller needs."""
    # ---- parties (v1-pinned) ---------------------------------------------
    hby_c, hab_c, rgy_c = _make_party("t12p2_carrier", b"t12p2_carrier_01234")
    haberies.append(hby_c)
    hby_d, hab_d, rgy_d = _make_party("t12p2_doi", b"t12p2_doi_012345678")
    haberies.append(hby_d)

    # ---- REAL bundled EGF, test variant (regulator authority = the DOI) ---
    egf_said = _inject_test_brand(tmp_path, monkeypatch, request, hab_d.pre)
    resolver, egf_doc = make_hoa_resolver(branding.brand())
    assert egf_doc.said == egf_said
    assert egf_doc.authorities("regulator", accept_phases=("bootstrap",))[0].aid \
        == hab_d.pre

    # ---- carrier self-issues its application (onboarding state: PENDING) --
    app_said = _issue(hby_c, hab_c, rgy_c, schema_said=APP_SCHEMA_SAID,
                      recipient=hab_c.pre, attributes=APPLICATION_ATTRS,
                      registry_name="carrier-apps")
    assert rgy_c.reger.saved.get(keys=(app_said,)) is not None

    # ---- DOI holds the application (so the license's NI2I edge resolves) --
    _admit(hby_d, rgy_d, _disclose(hby_c, rgy_c, app_said))
    assert rgy_d.reger.saved.get(keys=(app_said,)) is not None

    # ---- DOI issues the carrier_license with the required NI2I edge -------
    license_said = _issue(
        hby_d, hab_d, rgy_d, schema_said=LICENSE_SCHEMA_SAID,
        recipient=hab_c.pre, attributes=LICENSE_ATTRS, registry_name="doi-licenses",
        edges={"application": {"cred_said": app_said,
                               "schema_said": APP_SCHEMA_SAID, "op": "NI2I"}})
    creder_l = rgy_d.reger.cloneCred(said=license_said)[0]
    assert creder_l.sad["e"]["application"]["n"] == app_said
    assert creder_l.sad["e"]["application"]["o"] == "NI2I"

    # ---- build the carrier's ADMIT vault + manager ------------------------
    carrier_lockdb = _open_lockdb(tmp_path, request, "t12p2_carrier_lock")
    vault = AdmittingVault(hby_c, rgy_c, carrier_lockdb)
    app = SimpleNamespace(vault=vault)
    events, first = _event_collector(vault)
    # Admit-back courtesy delivery is out of scope — silence its poster.
    monkeypatch.setattr(serviceaid_bridge, "PeerAwarePoster", SilentPoster)

    mgr, carrier = _build_carrier_manager(
        monkeypatch, tmp_path, qapp, trusted_issuer=hab_d.pre)
    vault_view = _vault(hby_c, rgy_c)
    mgr._current_vault = vault_view
    vault.signals.doer_event.connect(mgr._on_doer_event)

    # PENDING before the license arrives; gate shut.
    held0 = mgr._held_credentials(vault_view)
    assert derive_role_states(held0, [], egf_doc)["carrier"] is RoleStatus.PENDING
    mgr.reevaluate_role_gates(vault_view)
    assert "carrier" not in mgr._active_roles

    # ---- deliver the DOI's return-grant bytes into the carrier parser -----
    # Stream shape = ServiceaidGrantDoer's: issuer(DOI) KEL + license registry
    # TEL + license credential TEL + the grant exn (embedding anc/iss/acdc).
    # The NI2I edge target (the application) is already carrier-held, so it is
    # not restreamed. The grant exn produces the /exn/ipex/grant note.
    stream = bytearray()
    stream.extend(outputKEL(hby_d, hab_d.pre))
    stream.extend(outputTEL(rgy_d, creder_l.regid))
    stream.extend(outputTEL(rgy_d, license_said))
    grant_said, raw = serviceaid_bridge.frame_grant_for(
        hby_d, hab_d, rgy_d, credential_said=license_said,
        recipient=hab_c.pre, return_raw=True)
    stream.extend(raw)

    r_rvy = routing.Revery(db=hby_c.db)
    r_kvy = eventing.Kevery(db=hby_c.db, lax=True, local=False, rvy=r_rvy)
    r_kvy.registerReplyRoutes(router=r_rvy.rtr)
    r_tvy = teventing.Tevery(db=hby_c.db, reger=rgy_c.reger, local=False, rvy=r_rvy)
    r_tvy.registerReplyRoutes(router=r_rvy.rtr)
    parsing.Parser(framed=True, kvy=r_kvy, tvy=r_tvy, exc=vault.exc, rvy=r_rvy,
                   version=Vrsn_1_0).parse(ims=bytearray(stream))
    for _ in range(40):
        r_kvy.processEscrows()
        r_tvy.processEscrows()

    # The grant note landed unread; the license is NOT yet saved (its ACDC
    # body travels only in the grant embed — admit_grant saves it).
    notes = list(vault.notifier.noter.notes.getTopItemIter())
    assert any(n.pad.get("a", {}).get("r") == "/exn/ipex/grant"
               for _k, n in notes)
    assert rgy_c.reger.saved.get(keys=(license_said,)) is None

    # ---- re-poll exercise: force chain_verified=False for the first two
    # MANAGER evaluations post-admit, then delegate to the real projection.
    # Only the manager's gate re-evaluation is patched; the watcher keeps the
    # real projection (``real_held``) so its PENDING match is accurate AND so
    # the whole forced-False budget is spent post-admit (the watcher's own
    # ``held_provider()`` call during ``scan_once`` must not consume it). ----
    real_held = mgr._held_credentials
    hold = {"n": 0}

    def held_provider(vlt):
        views = real_held(vlt)
        hold["n"] += 1
        if hold["n"] <= 2:
            views = [dataclasses.replace(v, chain_verified=False)
                     if v.schema_said == LICENSE_SCHEMA_SAID else v
                     for v in views]
        return views

    mgr._held_credentials = held_provider

    # ---- auto-admit: the watcher matches the expected grant and admits ----
    watcher = InboundGrantWatchDoer(
        app, egf_doc, accept_phases=("bootstrap", "production"),
        held_provider=lambda: real_held(vault_view))
    pump = _run(vault, request)

    with patch("locksmith.plugins.manager.QTimer") as qt:
        qt.singleShot.side_effect = lambda ms, cb: cb()  # drive re-poll synchronously
        watcher.scan_once()   # extends the ServiceaidAdmitDoer onto the vault
        pump(lambda: first("AdmitDoer", "admit_complete")
             or first("AdmitDoer", "admit_failed"),
             "inbound grant auto-admitted")

    # ---- acceptance assertions -------------------------------------------
    admit_evt = first("AdmitDoer", "admit_complete")
    assert admit_evt is not None, f"admit failed: {first('AdmitDoer', 'admit_failed')}"
    assert admit_evt["credential_said"] == license_said
    assert first("InboundWatch", "auto_admitted") is not None

    # The license genuinely chain-verified into the carrier's reger.
    assert rgy_c.reger.saved.get(keys=(license_said,)) is not None
    # The re-poll ran (>= the two forced-False evaluations + the real one).
    assert hold["n"] >= 3, "bounded re-poll must have been exercised"
    # The gate opened only after the re-poll saw the real chain-verified view.
    assert "carrier" in mgr._active_roles
    mgr._surface_host.register_page.assert_any_call(
        "carrier", carrier.get_pages()["carrier"])

    # Onboarding derives ACTIVE (real projection).
    held_final = real_held(vault_view)
    assert derive_role_states(held_final, [], egf_doc)["carrier"] is RoleStatus.ACTIVE

    return dict(
        mgr=mgr, app=app, vault=vault, vault_view=vault_view, egf_doc=egf_doc,
        hby_c=hby_c, hab_c=hab_c, rgy_c=rgy_c,
        hby_d=hby_d, hab_d=hab_d, rgy_d=rgy_d,
        license_said=license_said, creder_l=creder_l, real_held=real_held,
        carrier=carrier,
    )


def test_return_grant_auto_admits_carrier_to_licensed_surface(
        monkeypatch, tmp_path, request, qapp, haberies):
    handles = _reach_licensed(monkeypatch, tmp_path, request, qapp, haberies)
    app = handles["app"]
    egf_doc = handles["egf_doc"]

    # ---- the notifications page shows the arrival entry -------------------
    page = HoaNotificationsPage(app, egf_doc)
    page.refresh()
    grant_rows = [r for r in page.rows() if "/ipex/grant" in r["route"]]
    assert grant_rows, "notifications page must show the grant arrival"
    # Title upgraded to the EGF catalog credential name (best-effort resolve).
    assert grant_rows[0]["title"] == "Carrier License"
    # Finding 5 (final-review wave): the grant was auto-admitted, which
    # marks the note read -- an already-admitted row must no longer offer
    # Accept (a second admit for a grant that already landed must not be
    # schedulable).
    assert grant_rows[0]["read"] is True
    assert not HoaNotificationsPage.has_accept_action(grant_rows[0])


# ---------------------------------------------------------------------------
# PART 3 — DOI revokes the license -> gate deactivates -> REVOKED.
# ---------------------------------------------------------------------------

def test_revoked_license_deactivates_surface_and_shows_revoked(
        monkeypatch, tmp_path, request, qapp, haberies):
    # ---- reach LICENSED via the shared part-2 flow -------------------------
    handles = _reach_licensed(monkeypatch, tmp_path, request, qapp, haberies)
    mgr = handles["mgr"]
    app = handles["app"]
    vault = handles["vault"]
    vault_view = handles["vault_view"]
    egf_doc = handles["egf_doc"]
    hby_c = handles["hby_c"]
    hby_d = handles["hby_d"]
    hab_d = handles["hab_d"]
    rgy_c = handles["rgy_c"]
    rgy_d = handles["rgy_d"]
    license_said = handles["license_said"]
    creder_l = handles["creder_l"]
    real_held = handles["real_held"]

    assert "carrier" in mgr._active_roles
    assert derive_role_states(real_held(vault_view), [], egf_doc)["carrier"] \
        is RoleStatus.ACTIVE

    # ---- DOI revokes the license (local TEL rev, pure KERI) -----------------
    # No keri_serviceaid here -- this mirrors RevokeCredentialDoer's own
    # sequence (locksmith/core/credentialing.py): registry.revoke() fires the
    # TEL `rev` event, the resulting seal is anchored into the issuer hab's
    # KEL via interact() (this registry is estOnly=False, noBackers=True --
    # see `_ensure_registry` -- so interact(), not rotate()), then
    # Registrar.revoke() registers the anchor (registry.anchorMsg()) that
    # Tevery's escrow needs to resolve the rev event's MissingAnchorError --
    # without it the TEL event stays escrowed forever, however many times
    # processEscrows() runs (confirmed by running this test: a first attempt
    # that skipped the Registrar left the TEL parked at `iss`).
    registry = rgy_d.regs[creder_l.regid]
    rserder = registry.revoke(said=license_said, dt=helping.nowIso8601())
    rseal = eventing.SealEvent(rserder.pre, rserder.snh, rserder.said)
    rseal = dict(i=rseal.i, s=rseal.s, d=rseal.d)
    anc = hab_d.interact(data=[rseal], version=hab_d.kever.serder.pvrsn)
    aserder = serdering.SerderKERI(raw=anc)

    counselor = grouping.Counselor(hby=hby_d)
    registrar = Registrar(hby=hby_d, rgy=rgy_d, counselor=counselor)
    registrar.revoke(creder=creder_l, rserder=rserder, anc=aserder)

    for _ in range(10):
        rgy_d.processEscrows()
        registrar.processEscrows()
    assert rgy_d.reger.tevers[creder_l.regid].vcState(license_said).et in ("rev", "brv")

    # ---- deliver the raw TEL rev + KEL anchor into the carrier parser -----
    # (same parser seam part-2 uses for the return-grant stream; outputKEL/
    # outputTEL are already imported at the top of this module)
    rev_stream = bytearray()
    rev_stream.extend(outputKEL(hby_d, hab_d.pre))
    rev_stream.extend(outputTEL(rgy_d, license_said))
    rr_rvy = routing.Revery(db=hby_c.db)
    rr_kvy = eventing.Kevery(db=hby_c.db, lax=True, local=False, rvy=rr_rvy)
    rr_kvy.registerReplyRoutes(router=rr_rvy.rtr)
    rr_tvy = teventing.Tevery(db=hby_c.db, reger=rgy_c.reger, local=False, rvy=rr_rvy)
    rr_tvy.registerReplyRoutes(router=rr_rvy.rtr)
    parsing.Parser(framed=True, kvy=rr_kvy, tvy=rr_tvy, exc=vault.exc, rvy=rr_rvy,
                   version=Vrsn_1_0).parse(ims=bytearray(rev_stream))
    for _ in range(40):
        rr_kvy.processEscrows()
        rr_tvy.processEscrows()

    # carrier's TEL now reports the license revoked.
    tever = rgy_c.reger.tevers[creder_l.regid]
    assert tever.vcState(license_said).et in ("rev", "brv")

    # ---- live floor: recheck_gates deactivates the surface -----------------
    mgr._held_credentials = real_held        # undo part-2's re-poll patch
    assert mgr._current_vault is vault_view   # confirm still set (part-2 set it)
    mgr.recheck_gates()
    assert "carrier" not in mgr._active_roles

    # ---- onboarding derives REVOKED; notifications synthesize the card ----
    held_after = real_held(vault_view)
    assert derive_role_states(held_after, [], egf_doc)["carrier"] is RoleStatus.REVOKED
    page = HoaNotificationsPage(app, egf_doc, held_provider=lambda: real_held(vault_view))
    page.refresh()
    assert [r for r in page.rows() if r["route"] == "revoked"], \
        "notifications must show the revocation entry"
