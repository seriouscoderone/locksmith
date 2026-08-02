# -*- encoding: utf-8 -*-
"""Onboarding end-to-end (Plan B Task 10): persona pick to licensed surface,
transport mocked — the sub-project's automated acceptance (design spec §11
acceptance #2).

WHAT THIS PROVES
----------------
The full HOA onboarding pipeline against the REAL bundled insurance EGF
(re-saidified so its one bootstrap authority's AID is the in-process DOI
Habery's real AID), driven through the REAL flow objects — no orchestration
fakes anywhere on the carrier side:

  1. ``make_hoa_resolver(brand())`` resolves the test EGF variant through the
     actual ``LOCKSMITH_BRAND_CONFIG`` env injection + ``egf_local_dir()`` +
     ``make_resolver()`` chain (same as ``tests/core/test_egf_seeding.py``'s
     runtime test, but with the REAL usurance bundle artifacts).
  2. ``RequestFlow.seed_all_personas`` seeds the carrier role's onboarding
     schemas into the vault via real ``LoadSchemaDoer`` runs scheduled through
     the real ``app.vault.extend`` path, pumped on a real hio Doist.
  3. ``RequestFlow.submit(role_id="carrier", ...)`` derives the request plan
     from the EGF, validates the payload (with the ``submitted_at`` date-time
     autofill), selects the Utah bootstrap authority, and schedules a REAL
     ``ServiceaidIssueDoer`` — the application ACDC is self-issued
     (issuer == issuee == the vault's default identifier) into the carrier's
     own registry by ``keri_serviceaid.providers.issue_credential``.
  4. The flow's one-shot ``credential_issued`` listener schedules a REAL
     ``ServiceaidGrantDoer``: the IPEX grant exn is framed by
     ``frame_grant_for`` and parsed into the vault's exchanger
     (``hby.db.exns``); only the *delivery* transport (``PeerAwarePoster``)
     is stubbed — delivery is the transport project's (#2) scope.
  5. DOI side mirrors the scaffold e2e (``test_carrier_gate_e2e``): the
     application is presented (mocked transport: disclosure set re-verified
     by the REAL keripy Verifier), and the DOI issues the ``carrier_license``
     with the required NI2I ``application`` edge.
  6. The carrier admits the license through the scaffold's parse-streams
     admit path (real Kevery/Tevery/Verifier — HOA-native inbound admit is
     the transport project's scope), landing it chain-verified in
     ``reger.saved``.
  7. ``PluginManager.reevaluate_role_gates`` reveals the carrier surface
     (``"carrier" in mgr._active_roles``) and the per-role model derives
     ACTIVE (``derive_role_states(held, [], egf)["carrier"]``).

ACDC-DESIGN RECONCILIATION (Task 10 Step 1)
-------------------------------------------
The DOI-grant fixture issues a ``carrier_license`` ACDC; the ``acdc-design``
skill was invoked and reconciled against this fixture's construction:

- **Edge operator** (edges-and-provenance.md "Chaining vs linking"): the
  license *references* (NI2I) the application — the application's holder
  (the carrier) is NOT the license's issuer (the DOI is), so ``authorizes``
  (I2I) would be wrong; the edge is a provenance pointer to the exact
  immutable application adjudicated, with no authority transfer. The fixture
  passes ``op="NI2I"`` explicitly, matching the bundled license schema's
  ``e.application.o const "NI2I"``. Confirmed, unchanged from the blueprint.
- **Edges are authz/provenance-only** (ugard decision): the edge carries only
  ``n``/``s``/``o`` — no attribute values ride the edge. Confirmed.
- **Authority bootstrapping** (governance-and-bootstrapping.md "open now,
  closed later"): the bundled EGF's Utah authority is ``phase="bootstrap"``
  (operator-controlled stand-in until the real Utah DOI incepts). This test
  exercises exactly that seam: ``accept_phases=("bootstrap", "production")``
  is what lets ``select_authority`` match the bootstrap-phase authority, and
  the test EGF variant fills the authority *role* with the in-process DOI
  Habery's real AID — the pattern's "placeholder AID" step, instantiated
  in-process. The schema itself stays issuer-open (no issuer const), so no
  schema SAID changes; only the EGF document (which pins the authority AID)
  is re-saidified. Confirmed — and this is WHY only the EGF doc's SAID
  differs between the bundle and the test variant.
- **Registry pattern** (lifecycle-and-registries.md): registry-name ==
  application schema SAID follows the established Locksmith convention
  (one registry per credential type); the plan's ``registry_name`` is derived
  by ``keri_serviceaid.egf.onboarding.derive_request``. Confirmed.

V1 PROTOCOL PIN (CRITICAL fixture rule)
---------------------------------------
Every fixture hab/registry here is v1-pinned, per the blueprint's finding:
keri 2.0.0.dev's ACDC issuance is v1-only, and ``hab.interact`` does NOT
inherit the hab's protocol version (defaults to the module-level v2
constant). The carrier/DOI habs are ``makeHab(..., version=Vrsn_1_0)``; the
carrier's application registry is pre-created v1-pinned via
``keri_serviceaid.providers.issue.ensure_registry`` (which anchors with
``version=hab.kever.serder.pvrsn``) BEFORE seeding runs, because the legacy
``LoadSchemaDoer._create_registry`` anchors with an UNPINNED
``hab.interact(data=[rseal])`` — a v2 ixn on the carrier's v1 KEL, which the
DOI-side cross-party re-parse (``_admit``'s v1 Parser) rejects, breaking the
application presentation. (That unpinned interact is a latent product-code
hazard of the same class as the Task 7 finding fixed in
``keri_serviceaid/providers/issue.py`` — flagged in the task report; fixing
it is out of this test task's scope.) With the registry pre-created, the
real ``EgfSeeder`` two-gate logic still runs and schedules real schema-only
``LoadSchemaDoer`` passes (no interact), exercising the seeding path.

TASK 10/11 ADDITION (roles-overview home surface)
--------------------------------------------------
``OnboardingHomePage``'s old single-selected-role state machine
(``derive_state``/``OnboardingState``) was TRANSITIONAL through Task 10 —
kept only as a thin shim because ``locksmith.core.inbound_watch`` still
imported it. Task 11 rewrote that watcher onto ``derive_role_states`` and
removed the shim; every checkpoint below now asserts directly against the
per-role model (``locksmith.ui.onboarding.role_states.derive_role_states``/
``RoleStatus``) at each point in the pipeline — this is the one
REAL-credential integration proof for ``derive_role_states`` (Task 8's own
test suite only exercises it against a FakeEgf/synthetic ``Held``
dataclass, never an actually-admitted ACDC): nothing held -> AVAILABLE,
application held -> PENDING, license admitted -> ACTIVE.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from hio.base import doing
from keri.app import habbing
from keri.core import coring
from keri.core import signing as coresigning
from keri.kering import Vrsn_1_0
from keri.peer import exchanging
from keri.vdr import credentialing

from keri_serviceaid.providers.issue import ensure_registry

from locksmith.core import branding
import locksmith.core.serviceaid_bridge as serviceaid_bridge
from locksmith.core.egf_seeding import make_hoa_resolver
from locksmith.core.signals import DoerSignalBridge
from locksmith.peer.sending import SendOutcome
from locksmith.ui.onboarding.request_flow import RequestFlow
from locksmith.ui.onboarding.role_states import RoleStatus, derive_role_states

# Reuse the scaffold e2e's proven in-process fixture family (same test
# package): parties, disclosure/admit (mocked transport, real Verifier),
# issuance, the carrier PluginManager builder, and the haberies teardown
# fixture (imported so pytest registers it here too).
from tests.integration.test_carrier_gate_e2e import (  # noqa: F401 (haberies)
    APP_SCHEMA_SAID,
    LICENSE_SCHEMA_SAID,
    LICENSE_ATTRS,
    _admit,
    _build_carrier_manager,
    _disclose,
    _issue,
    _make_party,
    _vault,
    haberies,
)

# The vault's default identifier alias — RequestFlow._default_hab resolves it
# via brand().default_aid_alias, so the injected brand.json below must agree
# (the shipping brand.toml no longer uses this alias; the retired carrier
# example lives on as the tests/fixtures/carrier_egf_bundle/ fixture).
CARRIER_ALIAS = "carrier"

# A valid submit_application payload per the REAL bundled micro-app's
# payload_schema (tests/fixtures/carrier_egf_bundle/ED1ePv....json). ``submitted_at`` is
# deliberately omitted: it is required + format date-time, and the REAL flow
# autofills it (RequestFlow._autofill_date_time_fields) exactly as the page
# would — asserting the autofill path end to end.
SUBMIT_PAYLOAD = {
    "applicant_legal_name": "Acme Mutual Insurance Co.",
    "jurisdiction": "US-UT",
    "lines_of_business": ["property"],
    "primary_contact": {"name": "Jane Roe", "email": "jane@acme.example"},
    "representations": {
        "solvency_reserves_usd": 1_000_000,
        "solvency_attestation": True,
    },
}

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BUNDLE_DIR = _REPO_ROOT / "tests" / "fixtures" / "carrier_egf_bundle"


# ---------------------------------------------------------------------------
# Test-EGF-variant + brand injection plumbing
# ---------------------------------------------------------------------------

def _write_test_egf_bundle(egf_dir: Path, doi_aid: str) -> str:
    """Copy the REAL usurance EGF bundle into ``egf_dir``, replacing the one
    authority's AID with ``doi_aid`` and re-saidifying the EGF document (the
    B3/bundle-consistency re-said pattern). Schemas and micro-apps are copied
    verbatim — their SAIDs (which the EGF pins) are unchanged; only the EGF
    document's own SAID differs. Returns the variant EGF document's SAID."""
    egf_dir.mkdir(parents=True, exist_ok=True)
    egf_said = None
    for path in sorted(_BUNDLE_DIR.glob("E*.json")):
        doc = json.loads(path.read_text())
        if doc.get("spec_version") == "egf-doc/0.1":
            assert len(doc["authorities"]) == 1, "bundle grew a second authority"
            doc["authorities"][0]["aid"] = doi_aid
            doc["d"] = ""
            _, doc = coring.Saider.saidify(sad=doc, label="d")
            egf_said = doc["d"]
            # as-parsed rule: dump in insertion order (no key sorting) so the
            # resolver's verify_sad re-derivation matches.
            (egf_dir / f"{egf_said}.json").write_text(json.dumps(doc))
        else:
            (egf_dir / path.name).write_bytes(path.read_bytes())
    assert egf_said is not None, "no egf-doc/0.1 document in the bundle"
    return egf_said


def _inject_test_brand(tmp_path: Path, monkeypatch, request, doi_aid: str) -> str:
    """Write a test HOA brand (brand.json + sibling egf/ variant bundle) and
    inject it via the real ``LOCKSMITH_BRAND_CONFIG`` env path. Returns the
    variant EGF document SAID. Brand cache is reset now and again at teardown
    (before monkeypatch restores the env, so the next test recomputes from
    the restored environment)."""
    brand_dir = tmp_path / "brand"
    brand_dir.mkdir()
    egf_said = _write_test_egf_bundle(brand_dir / "egf", doi_aid)
    (brand_dir / "brand.json").write_text(json.dumps({
        "id": "e2e-hoa",
        "bootstrap": {
            "peel_core_pages": True,
            "default_aid_alias": CARRIER_ALIAS,
        },
        "plugins": {"bundled": ["carrier", "hoa_shell"]},
        "egf": {
            "source": "local",
            "document_said": egf_said,
            "accept_phases": ["bootstrap", "production"],
        },
        "onboarding": {"enabled": True},
    }))
    monkeypatch.setenv(branding.BRAND_CONFIG_ENV_VAR, str(brand_dir / "brand.json"))
    branding._reset_cache_for_tests()
    request.addfinalizer(branding._reset_cache_for_tests)
    return egf_said


# ---------------------------------------------------------------------------
# The carrier's vault: a REAL hio DoDoer with exactly the surface the flow
# consumes (hby/rgy/signals/exc/extend), pumped by a real virtual-time Doist.
# ---------------------------------------------------------------------------

class VaultHarness(doing.DoDoer):
    """Minimal REAL vault: ``extend`` is the real DoDoer scheduling seam the
    flow uses; ``signals`` is a real Qt ``DoerSignalBridge`` (the
    credential_issued -> grant-doer hand-off only fires on a real signal);
    ``exc`` is a real keripy Exchanger (``Exchanger.processEvent`` persists
    exns via ``logEvent`` regardless of registered behaviors, so the framed
    grant genuinely lands in ``hby.db.exns``). ``db`` is never touched: the
    only consumer (``PeerAwarePoster``) is the stubbed transport seam."""

    def __init__(self, hby, rgy):
        self.hby = hby
        self.rgy = rgy
        self.signals = DoerSignalBridge()
        self.exc = exchanging.Exchanger(hby=hby, handlers=[])
        self.db = None
        super().__init__(doers=[], always=True)


class TransportStubPoster:
    """The mocked-transport seam (delivery is project #2's scope): records
    sends, moves no bytes.

    ``last_outcome`` reports ``PEER`` because this seam stands in for a
    transport hop that SUCCEEDED — the point of mocking it here is that this
    test is about persona-pick-to-licensed-surface orchestration, not about
    how bytes travel. It used to report ``None``, which the grant doer renders
    as ``channel="mailbox"``; that was inert while the channel only picked a
    cosmetic badge, but the deliverability policy
    (``peer.posting.undeliverable``) now reads it to decide whether a send
    reached anybody, and this test's recipient has no mailbox ends — so an
    unset outcome made the modeled-successful grant emit ``send_failed``
    ("couldn't reach …'s wallet") and the framing assertion below failed.
    Same correction, same reason, as ``CapturePoster`` in
    ``test_exchange_roundtrip_e2e`` (commit d942bddb); this seam was missed
    because that branch verified five suites rather than the full run.

    Production is unaffected: ``PeerAwarePoster.deliver()`` sets
    ``last_outcome`` on every path that transmits, and the sole ``None`` path
    sends nothing. The ``None`` -> "mailbox" default stays as-is on purpose —
    "unknown is not a confirmed peer delivery" is the safe direction
    (backlog/2026-07-29-grant-send-reports-success-while-undeliverable.md)."""

    instances: list = []

    def __init__(self, **kwa):
        self.kwa = kwa
        self.sent = []
        self.last_outcome = SendOutcome.PEER
        TransportStubPoster.instances.append(self)

    def send(self, serder=None, attachment=None, **kwa):
        self.sent.append((serder, attachment))

    def deliver(self):
        return []


# ---------------------------------------------------------------------------
# The end-to-end acceptance test
# ---------------------------------------------------------------------------

def test_onboarding_e2e_persona_pick_to_licensed_surface(
        monkeypatch, tmp_path, request, qapp, haberies):
    # ---- parties (v1-pinned per the CRITICAL fixture rule) ----------------
    # DOI: blueprint party (v1 hab + both ugard schemas registered — it must
    # verify the presented application and issue the license).
    hby_d, hab_d, rgy_d = _make_party("e2e_doi", b"e2e_doi_012345678901")
    haberies.append(hby_d)
    # Carrier: v1 hab, NO pre-registered schemas — the real EGF seeding path
    # (EgfSeeder -> LoadSchemaDoer <- resolver.resolve_schema) pins them.
    hby_c = habbing.Habery(name="e2e_onb_carrier", temp=True,
                           salt=coresigning.Salter(raw=b"e2e_onb_carrier_0123").qb64)
    haberies.append(hby_c)
    hab_c = hby_c.makeHab(name=CARRIER_ALIAS, transferable=True, wits=[],
                          toad=0, version=Vrsn_1_0)
    rgy_c = credentialing.Regery(hby=hby_c, name="e2e_onb_carrier", temp=True)

    # ---- REAL bundled EGF, test variant (authority AID = in-process DOI) --
    egf_said = _inject_test_brand(tmp_path, monkeypatch, request, hab_d.pre)
    resolved = make_hoa_resolver(branding.brand())
    assert resolved is not None, "test brand must resolve its bundled EGF"
    resolver, egf_doc = resolved
    assert egf_doc.said == egf_said
    utah = egf_doc.authorities("regulator", accept_phases=("bootstrap",))[0]
    assert utah.aid == hab_d.pre, "variant must pin the in-process DOI's AID"

    # ---- the flow under test, on a REAL vault DoDoer + REAL doist ---------
    vault = VaultHarness(hby_c, rgy_c)
    app = SimpleNamespace(vault=vault)
    flow = RequestFlow(app, resolver, egf_doc,
                       accept_phases=branding.brand().egf_accept_phases)

    # Transport seam (the ONLY stub on the carrier side): delivery is #2's
    # scope; framing + local exchanger parse stay real.
    monkeypatch.setattr(serviceaid_bridge, "PeerAwarePoster", TransportStubPoster)

    events: list = []
    vault.signals.doer_event.connect(
        lambda name, etype, data: events.append((name, etype, data)))

    def first_event(doer_name, event_type):
        return next((d for n, t, d in events
                     if n == doer_name and t == event_type), None)

    doist = doing.Doist(real=False, tock=0.03125)
    deeds = doist.enter(doers=[vault])
    request.addfinalizer(lambda: doist.exit(deeds=deeds))

    def pump(until, what, rounds=200):
        for _ in range(rounds):
            if until():
                return
            doist.recur(deeds=deeds)
        raise AssertionError(
            f"vault doist did not reach: {what}; events={events}")

    # ---- registry pre-created v1-pinned (see module docstring's V1 pin
    # section: LoadSchemaDoer's registry path anchors with an unpinned v2
    # interact, which would poison the carrier's v1 KEL for the DOI-side
    # cross-party re-parse). ensure_registry anchors at the hab's own
    # established version — the same product function issuance uses. --------
    ensure_registry(hby_c, hab_c, rgy_c, name=APP_SCHEMA_SAID)

    # ---- seeding (real EgfSeeder + real LoadSchemaDoer schema passes) -----
    assert hby_c.db.schema.get(keys=(APP_SCHEMA_SAID,)) is None  # honest start
    flow.seed_all_personas()
    pump(lambda: (hby_c.db.schema.get(keys=(APP_SCHEMA_SAID,)) is not None
                  and hby_c.db.schema.get(keys=(LICENSE_SCHEMA_SAID,)) is not None),
         "role schemas seeded into the vault")
    assert rgy_c.registryByName(APP_SCHEMA_SAID) is not None

    # ---- onboarding state: nothing held yet -> AVAILABLE -------------------
    mgr, carrier = _build_carrier_manager(
        monkeypatch, tmp_path, qapp, trusted_issuer=hab_d.pre)
    held = mgr._held_credentials(_vault(hby_c, rgy_c))
    # Task 11: nothing held, nothing applied -> the carrier role is simply
    # AVAILABLE (per-role model; the old page-global PICKER no longer exists).
    assert derive_role_states(held, [], egf_doc)["carrier"] is RoleStatus.AVAILABLE

    # ---- submit: the REAL pipeline (derive/validate/autofill/select/issue)
    flow.submit("carrier", dict(SUBMIT_PAYLOAD), {"jurisdiction": "US-UT"})
    pump(lambda: (first_event("IssueCredentialDoer", "credential_issued")
                  or first_event("IssueCredentialDoer", "credential_issuance_failed")
                  or first_event("RequestFlow", "request_failed")),
         "application credential issuance")
    assert first_event("RequestFlow", "request_failed") is None, \
        f"submit failed: {first_event('RequestFlow', 'request_failed')}"
    issued = first_event("IssueCredentialDoer", "credential_issued")
    assert issued is not None, (
        f"issuance failed: "
        f"{first_event('IssueCredentialDoer', 'credential_issuance_failed')}")
    assert issued["schema_said"] == APP_SCHEMA_SAID
    app_said = issued["said"]

    # Self-issued application, genuinely saved (chain-verified) in the
    # carrier's own reger; issuer == issuee == the default identifier.
    assert rgy_c.reger.saved.get(keys=(app_said,)) is not None
    creder = rgy_c.reger.cloneCred(said=app_said)[0]
    assert creder.issuer == hab_c.pre and creder.attrib["i"] == hab_c.pre
    assert creder.attrib["submitted_at"], "date-time autofill must have run"

    # ---- the flow's listener chains the grant doer: framed + parsed -------
    pump(lambda: (first_event("SendGrantDoer", "send_complete")
                  or first_event("SendGrantDoer", "send_failed")),
         "grant exn framed")
    sent = first_event("SendGrantDoer", "send_complete")
    assert sent is not None, \
        f"grant framing failed: {first_event('SendGrantDoer', 'send_failed')}"
    assert sent["credential_said"] == app_said
    assert sent["recipient"] == hab_d.pre  # the selected Utah authority
    grant_said = sent["grant_said"]

    # Framed grant genuinely parsed into the vault's exchanger: recoverable
    # from hby.db.exns via cloneMessage (what the recipient's later
    # /ipex/admit verification looks up on the granter).
    exn, _pathed = exchanging.cloneMessage(hby_c, grant_said)
    assert exn is not None and exn.ked["r"] == "/ipex/grant"
    assert exn.ked["a"]["i"] == hab_d.pre
    # ...and the stubbed transport saw artifacts + the grant exn last.
    assert TransportStubPoster.instances, "grant delivery must use the poster seam"
    poster = TransportStubPoster.instances[-1]
    assert poster.sent and poster.sent[-1][0].said == grant_said

    # ---- onboarding state: application held -> PENDING; gate still shut ---
    held = mgr._held_credentials(_vault(hby_c, rgy_c))
    # Task 11: the self-issued application credential is held+chain-verified,
    # so the role reads PENDING (form-mode's chained_from derivation — see
    # derive_role_states).
    assert derive_role_states(held, [], egf_doc)["carrier"] is RoleStatus.PENDING
    mgr.reevaluate_role_gates(_vault(hby_c, rgy_c))
    assert "carrier" not in mgr._active_roles
    mgr._surface_host.register_page.assert_not_called()

    # ---- DOI side (blueprint's mocked-transport presentation + grant) -----
    _admit(hby_d, rgy_d, _disclose(hby_c, rgy_c, app_said))
    assert rgy_d.reger.saved.get(keys=(app_said,)) is not None, \
        "DOI must hold the application so the license's NI2I edge resolves"

    # DOI issues the carrier_license carrying the required NI2I edge to the
    # EXACT application adjudicated (acdc-design: references/NI2I provenance
    # pointer — no authority transfer, no data on the edge).
    license_said = _issue(
        hby_d, hab_d, rgy_d, schema_said=LICENSE_SCHEMA_SAID,
        recipient=hab_c.pre, attributes=LICENSE_ATTRS,
        registry_name="doi-licenses",
        edges={"application": {"cred_said": app_said,
                               "schema_said": APP_SCHEMA_SAID, "op": "NI2I"}})
    edge = rgy_d.reger.cloneCred(said=license_said)[0].sad["e"]["application"]
    assert edge["n"] == app_said and edge["o"] == "NI2I"

    # ---- carrier admits (blueprint's parse-streams path, real Verifier) ---
    _admit(hby_c, rgy_c, _disclose(hby_d, rgy_d, license_said))
    assert rgy_c.reger.saved.get(keys=(license_said,)) is not None, \
        "license must chain-verify (NI2I edge target already held)"

    # ---- acceptance: gate reveals the carrier surface ----------------------
    mgr.reevaluate_role_gates(_vault(hby_c, rgy_c))
    assert "carrier" in mgr._active_roles
    mgr._surface_host.register_page.assert_any_call(
        "carrier", carrier.get_pages()["carrier"])

    # ---- acceptance: onboarding shows ACTIVE -------------------------------
    held = mgr._held_credentials(_vault(hby_c, rgy_c))
    # Task 11: carrier goes licensed -> its role shows ACTIVE (the
    # real-credential integration proof for derive_role_states; Task 8's own
    # suite only exercises it against a FakeEgf/synthetic Held dataclass,
    # never a REAL admitted ACDC).
    assert derive_role_states(held, [], egf_doc)["carrier"] is RoleStatus.ACTIVE
