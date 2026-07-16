# -*- encoding: utf-8 -*-
"""End-to-end demo (Task 10): admitting a chain-verified ``carrier_license``
activates the dormant ``carrier`` role-plugin — all KERI transport mocked,
fully in-process, no subprocesses.

WHAT THIS PROVES
----------------
The whole HOA "credential = app access" handshake, with two in-process KERI
parties (a DOI Habery and a carrier Habery) and every witness/mailbox/OOBI
transport replaced by direct in-memory byte hand-off:

  1. the carrier **self-issues** a ``carrier_license_application`` ACDC
     (issuer == issuee == carrier), landing genuinely saved in its own reger;
  2. that application is **presented** to the DOI (mocked transport: its real
     KEL + registry TEL + ACDC are disclosed and re-verified into the DOI's
     stores by the REAL keripy ``Verifier`` — the in-process stand-in for the
     DOI admitting the carrier's IPEX presentation), so the license's edge
     target is resolvable DOI-side at issuance time;
  3. the DOI **issues** a ``carrier_license`` to the carrier carrying the
     required NI2I edge ``application`` -> the presented application SAID;
  4. the carrier **admits** the license (mocked transport: the DOI's disclosure
     set is re-verified into the carrier's stores by the REAL keripy
     ``Verifier``). Because the carrier already holds the self-issued
     application node, chain verification passes and the license lands
     **non-escrowed** in the reger ``saved`` (fully-verified) index;
  5. ``PluginManager.reevaluate_role_gates`` flips the carrier plugin's gate
     unsatisfied -> satisfied and the ``RevealBundledSurface`` strategy
     registers the carrier surface on the host — with no re-auth.

The credential's verified state is NEVER stubbed: ``chain_verified`` is read
from ``reger.saved``, which keripy only pins in ``Verifier.saveCredential``
after the full chain (the NI2I ``application`` edge), schema, and registry all
verify against the real KEL/TEL. This is the "seeded-but-real equivalent" the
task brief permits (real issuance with the edge + application node made
resolvable + real verifier-driven admit) — a faithful literal IPEX
apply/present/grant/admit exn round-trip is impractical to mock purely
in-process (and locksmith's ``ipexing.Admitter.admit`` indexes ``embeds['reg']``,
which ``protocoling.ipexGrantExn`` no longer emits — it would KeyError), so we
drive the *same* real ``kvy``/``tvy``/``vry`` verification that admit performs.

TEST DOI vs PRODUCTION DOI
--------------------------
``CarrierPlugin.required_credential`` hardcodes the real production DOI AID
(``EOtKW1M3PReijqHMu92uX5FG0fCPwIfH7plPQSifb34``). Our in-process DOI has a
different, freshly-incepted AID, so we OVERRIDE the discovered plugin instance's
``required_credential`` to trust the TEST DOI's AID. We are proving the gate
MECHANISM, not the literal production issuer AID (the literal-AID declaration is
asserted separately in ``tests/plugins/carrier/test_carrier_plugin.py``).

V1 PROTOCOL PIN
---------------
keri 2.0.0.dev6's ACDC issuance is v1-only (``vc/proving.py`` hardcodes the v1
``ri`` label; the v2 ``SerderACDC`` rejects it), and ``Hab.interact`` does NOT
inherit the hab's protocol version — it defaults to v2. A KEL mixing a v1 icp
with v2 anchoring ixns cannot be re-parsed cross-party. So every ``makeHab`` and
every ``hab.interact`` here is explicitly pinned to ``Vrsn_1_0``, yielding a
uniformly-v1 KEL+TEL+ACDC stack that the receiving party parses with
``version=Vrsn_1_0``.

EDGE-REVOCATION BOUND (Task 7 acceptance item)
----------------------------------------------
``test_revoking_application_edge_target_leaves_gate_satisfied`` documents the
observed, by-design behavior: revoking the application (the NI2I edge target)
while the license's OWN TEL stays ``iss`` does NOT re-close the gate, because
``chain_verified`` derives from ``reger.saved`` which is **save-time** — keripy
does not proactively re-run chain verification when an edge target's TEL later
changes. Transitive live edge-revocation propagation is therefore out of scope
of the current gate; this is asserted (not silently skipped) below.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from hio.base import doing
from keri.app import habbing, grouping, signing as app_signing
from keri.core import coring, eventing, parsing, scheming, serdering
from keri.core import signing as coresigning
from keri.help import helping
from keri.kering import Kinds, Vrsn_1_0
from keri.vdr import credentialing, verifying, eventing as teventing

from locksmith.core.configing import Environments
from locksmith.core.credentialing import outputKEL, outputTEL
from locksmith.plugins import manager as manager_module
from locksmith.plugins import storage
from locksmith.plugins.carrier.plugin import (
    CARRIER_LICENSE_SCHEMA_SAID,
    DOI_ISSUER_AID,
)
from locksmith.plugins.credential_gate import RequiredCredential
from locksmith.plugins.manager import PluginManager

# ---------------------------------------------------------------------------
# Canonical ugard schemas (embedded verbatim so the test is self-contained;
# the $id of each is its SAID and must round-trip through Schemer unchanged).
# ---------------------------------------------------------------------------
APP_SCHEMA_SAID = "ENbhxLlFINUDp1EU4mV5RVVL-CS6Ub72zXY89EcM7Ccb"
LICENSE_SCHEMA_SAID = CARRIER_LICENSE_SCHEMA_SAID  # "ENIhMZ...R9cX42x"

APPLICATION_SCHEMA = json.loads(r'''
{
  "$id": "ENbhxLlFINUDp1EU4mV5RVVL-CS6Ub72zXY89EcM7Ccb",
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Carrier License Application",
  "description": "A carrier's self-attested application to underwrite named lines of business in a US jurisdiction. Self-issued (issuer = issuee = the carrier) and presented to a state Department of Insurance via IPEX. The granted carrier_license edges back to the exact (immutable, SAID-addressed) version adjudicated.",
  "type": "object",
  "credentialType": "CarrierLicenseApplication",
  "properties": {
    "v": {"description": "ACDC version string.", "type": "string"},
    "d": {"description": "Credential SAID.", "type": "string"},
    "i": {"description": "Issuer AID (the applicant carrier; equals the issuee since self-issued).", "type": "string"},
    "ri": {"description": "Issuance/revocation TEL registry identifier (the carrier's own registry; enables re-issuance/supersession).", "type": "string"},
    "s": {"description": "Schema SAID.", "type": "string"},
    "a": {
      "oneOf": [
        {"description": "Attributes block SAID, compact form.", "type": "string"},
        {
          "$id": "EInnH9PTNvDqEUA3L4CBPcNV_maoVpyXq3OhWPNrJDXz",
          "description": "Carrier license application attributes.",
          "type": "object",
          "properties": {
            "d": {"description": "Attributes block SAID.", "type": "string"},
            "i": {"description": "Issuee AID (the applicant carrier).", "type": "string"},
            "dt": {"description": "Issuance date-time.", "type": "string", "format": "date-time"},
            "applicant_legal_name": {"type": "string", "minLength": 1, "description": "Full legal name of the applying carrier entity."},
            "jurisdiction": {"type": "string", "pattern": "^US-[A-Z]{2}$", "description": "ISO 3166-2 subdivision code the application targets (e.g., 'US-CA')."},
            "lines_of_business": {"type": "array", "description": "Lines of business the carrier seeks authority to underwrite.", "items": {"type": "string", "enum": ["property", "casualty", "life", "health", "auto", "workers_compensation", "marine", "aviation"]}, "minItems": 1, "uniqueItems": true},
            "primary_contact": {"type": "object", "description": "Primary contact for the application.", "properties": {"name": {"type": "string", "minLength": 1}, "email": {"type": "string", "format": "email"}}, "additionalProperties": false, "required": ["name", "email"]},
            "representations": {"type": "object", "description": "Financial representations attested by the applicant.", "properties": {"solvency_reserves_usd": {"type": "number", "minimum": 0, "description": "Attested solvency reserves in USD."}, "solvency_attestation": {"type": "boolean", "description": "Applicant attests reserves are at or above the regulatory minimum."}, "naic_number": {"type": "string", "description": "NAIC company code, if assigned."}, "years_in_operation": {"type": "integer", "minimum": 0, "description": "Years the carrier entity has operated."}}, "additionalProperties": false, "required": ["solvency_reserves_usd", "solvency_attestation"]},
            "submitted_at": {"type": "string", "format": "date-time", "description": "Carrier-stated submission time. Client-supplied (the command binding has no runtime clock)."}
          },
          "additionalProperties": false,
          "required": ["d", "i", "dt", "applicant_legal_name", "jurisdiction", "lines_of_business", "primary_contact", "representations", "submitted_at"]
        }
      ]
    }
  },
  "additionalProperties": false,
  "required": ["v", "d", "i", "ri", "s", "a"]
}
''')

LICENSE_SCHEMA = json.loads(r'''
{
  "$id": "ENIhMZdlSsMGOw7qMkE8VHcSS9RdEC1-aBom-R9cX42x",
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Carrier License",
  "description": "License authorizing an entity to bear insurance risk in a jurisdiction. Issued by a state Department of Insurance to a regulated insurance carrier following review and adjudication of a carrier_license_application.",
  "type": "object",
  "credentialType": "CarrierLicense",
  "properties": {
    "v": {"description": "ACDC version string.", "type": "string"},
    "d": {"description": "Credential SAID.", "type": "string"},
    "i": {"description": "Issuer AID (the granting state Department of Insurance).", "type": "string"},
    "ri": {"description": "Issuance/revocation TEL registry identifier.", "type": "string"},
    "s": {"description": "Schema SAID.", "type": "string"},
    "a": {
      "oneOf": [
        {"description": "Attributes block SAID, compact form.", "type": "string"},
        {
          "$id": "EAZG2BvdAEZ3iKoHR3XlWDT_vnnUcgELHjjDVP7LsJnB",
          "description": "Carrier license attributes.",
          "type": "object",
          "properties": {
            "d": {"description": "Attributes block SAID.", "type": "string"},
            "i": {"description": "Issuee AID (the licensed carrier).", "type": "string"},
            "dt": {"description": "Issuance date-time.", "type": "string", "format": "date-time"},
            "license_number": {"type": "string", "description": "Jurisdiction-assigned license identifier. Upper-case alphanumeric with hyphens.", "pattern": "^[A-Z0-9-]+$", "minLength": 3, "maxLength": 32},
            "jurisdiction": {"type": "string", "description": "ISO 3166-2 subdivision code for the granting jurisdiction (e.g., 'US-CA').", "pattern": "^US-[A-Z]{2}$"},
            "lines_of_business": {"type": "array", "description": "Authorized lines of business under this license.", "items": {"type": "string", "enum": ["property", "casualty", "life", "health", "auto", "workers_compensation", "marine", "aviation"]}, "minItems": 1, "uniqueItems": true},
            "effective_date": {"type": "string", "format": "date", "description": "Date the license takes effect."},
            "expiration_date": {"type": "string", "format": "date", "description": "Date the license expires absent renewal."},
            "regulatory_body": {"type": "string", "description": "Display name of the issuing regulator (e.g., 'California Department of Insurance')."},
            "market_conduct_status": {"type": "string", "description": "Current market-conduct standing as assessed by the regulator.", "enum": ["good_standing", "under_review", "restricted"]}
          },
          "additionalProperties": false,
          "required": ["d", "i", "dt", "license_number", "jurisdiction", "lines_of_business", "effective_date", "expiration_date"]
        }
      ]
    },
    "e": {
      "oneOf": [
        {"description": "Edge block SAID, compact form.", "type": "string"},
        {
          "$id": "EC3cGWy20BUPxr-owG3LTzE09XM4qD1tJUL9Yy9cTgmF",
          "description": "Edges chaining this license to the application it adjudicates.",
          "type": "object",
          "properties": {
            "d": {"description": "Edge block SAID.", "type": "string"},
            "application": {
              "description": "NI2I reference to the immutable carrier_license_application ACDC adjudicated by this grant. No authority transfer — the regulator's authority is statutory/KEL-anchored; this edge is a signed snapshot pointer.",
              "type": "object",
              "properties": {
                "n": {"description": "SAID of the carrier_license_application node.", "type": "string"},
                "s": {"description": "Schema SAID of carrier_license_application.", "type": "string", "const": "ENbhxLlFINUDp1EU4mV5RVVL-CS6Ub72zXY89EcM7Ccb"},
                "o": {"description": "Edge operator: NI2I (not-issuer-to-issuee).", "type": "string", "const": "NI2I"}
              },
              "additionalProperties": false,
              "required": ["n", "s", "o"]
            }
          },
          "additionalProperties": false,
          "required": ["d", "application"]
        }
      ]
    }
  },
  "additionalProperties": false,
  "required": ["v", "d", "i", "ri", "s", "a", "e"]
}
''')

# Schema-valid attribute blocks (mirror concierge-api's fixtures).
APPLICATION_ATTRS = {
    "applicant_legal_name": "Acme Mutual Insurance Co.",
    "jurisdiction": "US-UT",
    "lines_of_business": ["property"],
    "primary_contact": {"name": "Jane Roe", "email": "jane@acme.example"},
    "representations": {"solvency_reserves_usd": 1_000_000, "solvency_attestation": True},
    "submitted_at": "2026-01-01T00:00:00+00:00",
}
LICENSE_ATTRS = {
    "license_number": "P-12345",
    "jurisdiction": "US-UT",
    "lines_of_business": ["property"],
    "effective_date": "2026-01-01",
    "expiration_date": "2027-01-01",
}


# ---------------------------------------------------------------------------
# In-process KERI mechanics (all transport mocked; real Verifier throughout).
# The issuance recipe re-derives keri_serviceaid's proven no-backer flow using
# only keripy primitives (nothing test-only is imported cross-repo).
# ---------------------------------------------------------------------------

def _register_schemas(hby):
    for sed in (APPLICATION_SCHEMA, LICENSE_SCHEMA):
        schemer = scheming.Schemer(sed=sed, kind=Kinds.json)
        hby.db.schema.pin(keys=(schemer.said,), val=schemer)


def _make_party(name, salt):
    """A real in-process party: v1-pinned Habery + single AID + Regery, with
    both ugard schemas registered. Witnessless (wits=[], toad=0)."""
    hby = habbing.Habery(name=name, temp=True, salt=coresigning.Salter(raw=salt).qb64)
    hab = hby.makeHab(name=name, transferable=True, wits=[], toad=0, version=Vrsn_1_0)
    _register_schemas(hby)
    rgy = credentialing.Regery(hby=hby, name=name, temp=True)
    return hby, hab, rgy


def _complete(rgy, registrar, pre, sn, *, verifier=None, credentialer=None,
              cred_said=None, rounds=64):
    """Pump the no-backer TEL/credential escrows on a virtual-time Doist until
    the event (and, when given, the credential) is committed."""
    def _done():
        if not registrar.complete(pre=pre, sn=sn):
            return False
        if credentialer is not None and cred_said is not None:
            return credentialer.complete(said=cred_said)
        return True

    doers = [registrar] if credentialer is None else [registrar, credentialer]
    doist = doing.Doist(real=False, tock=1.0)
    deeds = doist.enter(doers=doers)
    try:
        for _ in range(rounds):
            if _done():
                return
            rgy.processEscrows()
            if verifier is not None:
                verifier.processEscrows()
            doist.recur(deeds=deeds)
        raise AssertionError(f"TEL event did not complete: pre={pre} sn={sn}")
    finally:
        doist.exit(deeds=deeds)


def _ensure_registry(hby, hab, rgy, name):
    existing = rgy.registryByName(name)
    if existing is not None:
        return existing
    counselor = grouping.Counselor(hby=hby)
    registrar = credentialing.Registrar(hby=hby, rgy=rgy, counselor=counselor)
    registry = rgy.makeRegistry(name=name, prefix=hab.pre, noBackers=True,
                                nonce=coresigning.Salter().qb64)
    rseal = eventing.SealEvent(registry.regk, "0", registry.regd)
    rseal = dict(i=rseal.i, s=rseal.s, d=rseal.d)
    anc = hab.interact(data=[rseal], version=Vrsn_1_0)
    registrar.incept(iserder=registry.vcp, anc=serdering.SerderKERI(raw=bytes(anc)))
    _complete(rgy, registrar, registry.regk, 0)
    return registry


def _issue(hby, hab, rgy, *, schema_said, recipient, attributes, registry_name,
           edges=None):
    """Real ACDC issuance (v1) into a no-backer registry, with an optional NI2I
    edge block. Returns the issued credential SAID."""
    _ensure_registry(hby, hab, rgy, registry_name)
    counselor = grouping.Counselor(hby=hby)
    registrar = credentialing.Registrar(hby=hby, rgy=rgy, counselor=counselor)
    verifier = verifying.Verifier(hby=hby, reger=rgy.reger)
    credentialer = credentialing.Credentialer(
        hby=hby, rgy=rgy, registrar=registrar, verifier=verifier)

    source = None
    if edges:
        source = dict(d="")
        for ename, edef in edges.items():
            entry = {"n": edef["cred_said"], "s": edef["schema_said"]}
            if "op" in edef:
                entry["o"] = edef["op"]
            source[ename] = entry
        _, source = coring.Saider.saidify(sad=source, kind=Kinds.json,
                                          label=coring.Saids.d)

    creder = credentialer.create(
        regname=registry_name, recp=recipient, schema=schema_said, source=source,
        rules=None, data=dict(attributes), private=False, version=Vrsn_1_0)
    registry = rgy.registryByName(registry_name)
    iserder = registry.issue(said=creder.said,
                             dt=creder.attrib.get("dt", helping.nowIso8601()))
    rseal = eventing.SealEvent(iserder.pre, iserder.snh, iserder.said)
    rseal = dict(i=rseal.i, s=rseal.s, d=rseal.d)
    anc = hab.interact(data=[rseal], version=Vrsn_1_0)
    credentialer.issue(creder, iserder)
    registrar.issue(creder, iserder, serdering.SerderKERI(raw=bytes(anc)))
    _complete(rgy, registrar, iserder.pre, iserder.sn, verifier=verifier,
              credentialer=credentialer, cred_said=creder.said)
    return creder.said


def _disclose(hby, rgy, said):
    """The credential disclosure set a holder would transmit (issuer KEL +
    registry TEL + credential TEL + signed ACDC). Uses locksmith.core's own
    ``outputKEL``/``outputTEL`` + ``signing.serialize`` — the same artifacts
    ``credentialing.sendArtifacts`` streams over the wire, assembled here for
    direct in-memory hand-off (the mocked transport seam)."""
    creder = rgy.reger.cloneCred(said=said)[0]
    out = bytearray()
    out.extend(outputKEL(hby, creder.issuer))
    out.extend(outputTEL(rgy, creder.regid))
    out.extend(outputTEL(rgy, said))
    prefixer, seqner, saider = rgy.reger.cancs.get(keys=(said,))
    out.extend(app_signing.serialize(creder, prefixer, seqner, saider))
    return bytes(out)


def _admit(hby, rgy, bundle):
    """The real verifying half of an IPEX admit: parse a disclosure set through
    the REAL keripy ``Kevery``/``Tevery``/``Verifier`` and pump escrows. A
    credential whose full chain (NI2I edge target), schema, and registry verify
    lands non-escrowed in ``reger.saved``; anything unresolved stays unsaved."""
    tvy = teventing.Tevery(db=hby.db, reger=rgy.reger, local=False)
    vry = verifying.Verifier(hby=hby, reger=rgy.reger)
    parsing.Parser(kvy=hby.kvy, tvy=tvy, vry=vry, version=Vrsn_1_0).parse(
        ims=bytearray(bundle))
    for _ in range(40):
        hby.kvy.processEscrows()
        tvy.processEscrows()
        vry.processEscrows()


def _introduce_kel(dst_hby, src_hab):
    """Mocked OOBI resolution: make ``src_hab``'s AID resolvable in ``dst_hby``
    (its key state) so ``dst`` can issue a credential TO it."""
    parsing.Parser(kvy=dst_hby.kvy, version=Vrsn_1_0).parse(
        ims=bytearray(src_hab.replay()))
    for _ in range(10):
        dst_hby.kvy.processEscrows()


def _revoke(hby, hab, rgy, registry_name, said):
    """Real TEL ``rev`` for ``said`` on the issuer's own registry."""
    registry = rgy.registryByName(registry_name)
    counselor = grouping.Counselor(hby=hby)
    registrar = credentialing.Registrar(hby=hby, rgy=rgy, counselor=counselor)
    creder = rgy.reger.cloneCred(said=said)[0]
    rserder = registry.revoke(said=said, dt=helping.nowIso8601())
    rseal = eventing.SealEvent(rserder.pre, rserder.snh, rserder.said)
    rseal = dict(i=rseal.i, s=rseal.s, d=rseal.d)
    anc = hab.interact(data=[rseal], version=Vrsn_1_0)
    registrar.revoke(creder=creder, rserder=rserder,
                     anc=serdering.SerderKERI(raw=bytes(anc)))
    _complete(rgy, registrar, rserder.pre, rserder.sn)


def _tel_state(rgy, said):
    creder = rgy.reger.cloneCred(said=said)[0]
    return rgy.reger.tevers[creder.regid].vcState(said).et


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def haberies():
    """Track Haberies opened by a test and close them on teardown so temp LMDB
    environments do not leak between tests."""
    opened: list = []
    yield opened
    for hby in reversed(opened):
        try:
            hby.close()
        except Exception:  # noqa: BLE001 — teardown best-effort
            pass


@pytest.fixture
def party(haberies):
    def _factory(name, salt):
        hby, hab, rgy = _make_party(name, salt)
        haberies.append(hby)
        return hby, hab, rgy
    return _factory


def _build_carrier_manager(monkeypatch, tmp_path, qapp, *, trusted_issuer):
    """Discover the real bundled ``carrier`` plugin via its entry point (Task 9)
    under a peel/HOA brand, override its trusted issuer to the TEST DOI AID, and
    wire a mock surface host. Returns (manager, carrier_plugin)."""
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    monkeypatch.setattr(
        manager_module, "brand",
        lambda: SimpleNamespace(peel_core_pages=True),
    )
    app = MagicMock()
    app.config = SimpleNamespace(base="", environment=Environments.DEVELOPMENT)
    mgr = PluginManager(app, keri_base=tmp_path / "keri")
    mgr.discover()  # loads + initializes CarrierPlugin (builds its real QWidget)

    carrier = mgr.get_plugin("carrier")
    assert carrier is not None, "carrier entry point must be discoverable"
    # Prove the plugin ships trusting the PRODUCTION DOI AID out of the box...
    assert carrier.required_credential.issuer_aids == [DOI_ISSUER_AID]
    # ...then override to the TEST DOI for this in-process world (mechanism test).
    carrier.required_credential = RequiredCredential(
        schema_said=LICENSE_SCHEMA_SAID,
        issuer_aids=[trusted_issuer],
        required_state="active",
    )
    mgr._surface_host = MagicMock()
    return mgr, carrier


def _vault(hby, rgy):
    """The minimal vault view ``reevaluate_role_gates`` reads."""
    return SimpleNamespace(hby=hby, rgy=rgy)


# ---------------------------------------------------------------------------
# The end-to-end demo + gate negatives
# ---------------------------------------------------------------------------

def test_admitting_carrier_license_activates_carrier_plugin(
        monkeypatch, tmp_path, qapp, party):
    """Positive path + negative (a): the gate is shut BEFORE admit and opens
    only once the chain-verified license lands."""
    hby_c, hab_c, rgy_c = party("t10_carrier", b"t10_carrier_01234567")
    hby_d, hab_d, rgy_d = party("t10_doi", b"t10_doi_012345678901")

    # 1. carrier self-issues the application (issuer == issuee).
    app_said = _issue(
        hby_c, hab_c, rgy_c, schema_said=APP_SCHEMA_SAID, recipient=hab_c.pre,
        attributes=APPLICATION_ATTRS, registry_name="carrier-apps")
    assert rgy_c.reger.saved.get(keys=(app_said,)) is not None

    mgr, carrier = _build_carrier_manager(
        monkeypatch, tmp_path, qapp, trusted_issuer=hab_d.pre)

    # Negative (a): holding only the self-issued application, the gate is shut.
    mgr.reevaluate_role_gates(_vault(hby_c, rgy_c))
    assert "carrier" not in mgr._active_roles
    mgr._surface_host.register_page.assert_not_called()

    # 2. present the application to the DOI (mocked transport, real verifier).
    _admit(hby_d, rgy_d, _disclose(hby_c, rgy_c, app_said))
    assert rgy_d.reger.saved.get(keys=(app_said,)) is not None, \
        "DOI must hold the application so the license's NI2I edge resolves"

    # 3. DOI issues the carrier_license carrying the required NI2I edge.
    license_said = _issue(
        hby_d, hab_d, rgy_d, schema_said=LICENSE_SCHEMA_SAID,
        recipient=hab_c.pre, attributes=LICENSE_ATTRS,
        registry_name="doi-licenses",
        edges={"application": {"cred_said": app_said,
                               "schema_said": APP_SCHEMA_SAID, "op": "NI2I"}})
    edge = rgy_d.reger.cloneCred(said=license_said)[0].sad["e"]["application"]
    assert edge["n"] == app_said and edge["s"] == APP_SCHEMA_SAID \
        and edge["o"] == "NI2I"

    # 4. carrier admits the license (mocked transport, real verifier).
    _admit(hby_c, rgy_c, _disclose(hby_d, rgy_d, license_said))
    # Genuinely chain-verified by the REAL keripy verifier — not stubbed.
    assert rgy_c.reger.saved.get(keys=(license_said,)) is not None
    assert _tel_state(rgy_c, license_said) == "iss"
    assert rgy_c.reger.cloneCred(said=license_said)[0].issuer == hab_d.pre

    # 5. re-evaluating the gate activates the carrier plugin — no re-auth.
    mgr.reevaluate_role_gates(_vault(hby_c, rgy_c))
    assert "carrier" in mgr._active_roles
    mgr._surface_host.register_page.assert_any_call(
        "carrier", carrier.get_pages()["carrier"])


def test_escrowed_license_with_unresolvable_edge_does_not_activate(
        monkeypatch, tmp_path, qapp, party):
    """Negative (b): a license whose NI2I ``application`` edge target the holder
    does NOT possess never chain-verifies (absent from ``reger.saved``), so the
    gate — which requires ``chain_verified`` — stays shut."""
    hby_c, hab_c, rgy_c = party("t10b_carrier", b"t10b_carrier_012345")
    hby_d, hab_d, rgy_d = party("t10b_doi", b"t10b_doi_0123456789")

    # DOI mints a license edged to an application it holds...
    _introduce_kel(hby_d, hab_c)  # DOI learns the carrier AID (mocked OOBI)
    app_said = _issue(
        hby_d, hab_d, rgy_d, schema_said=APP_SCHEMA_SAID, recipient=hab_d.pre,
        attributes=APPLICATION_ATTRS, registry_name="doi-apps")
    license_said = _issue(
        hby_d, hab_d, rgy_d, schema_said=LICENSE_SCHEMA_SAID,
        recipient=hab_c.pre, attributes=LICENSE_ATTRS,
        registry_name="doi-licenses",
        edges={"application": {"cred_said": app_said,
                               "schema_said": APP_SCHEMA_SAID, "op": "NI2I"}})

    # ...but the carrier admits ONLY the license, never the edge target.
    _admit(hby_c, rgy_c, _disclose(hby_d, rgy_d, license_said))
    assert rgy_c.reger.saved.get(keys=(license_said,)) is None, \
        "license must NOT be chain-verified without its resolvable edge target"

    mgr, _carrier = _build_carrier_manager(
        monkeypatch, tmp_path, qapp, trusted_issuer=hab_d.pre)
    mgr.reevaluate_role_gates(_vault(hby_c, rgy_c))
    assert "carrier" not in mgr._active_roles
    mgr._surface_host.register_page.assert_not_called()


def test_wrong_issuer_license_does_not_activate(
        monkeypatch, tmp_path, qapp, party):
    """Negative (c): a fully chain-verified, active license issued by an
    UNTRUSTED issuer (not the trusted DOI) does not open the gate."""
    hby_c, hab_c, rgy_c = party("t10c_carrier", b"t10c_carrier_012345")
    hby_d, hab_d, rgy_d = party("t10c_doi", b"t10c_doi_0123456789")
    hby_r, hab_r, rgy_r = party("t10c_rogue", b"t10c_rogue_01234567")

    # carrier self-issues the application; the ROGUE issuer resolves it (NI2I
    # makes the edge target's issuer irrelevant to chain verification).
    app_said = _issue(
        hby_c, hab_c, rgy_c, schema_said=APP_SCHEMA_SAID, recipient=hab_c.pre,
        attributes=APPLICATION_ATTRS, registry_name="carrier-apps")
    _admit(hby_r, rgy_r, _disclose(hby_c, rgy_c, app_said))

    # Rogue mints a genuinely chain-verifiable carrier_license to the carrier.
    rogue_license = _issue(
        hby_r, hab_r, rgy_r, schema_said=LICENSE_SCHEMA_SAID,
        recipient=hab_c.pre, attributes=LICENSE_ATTRS,
        registry_name="rogue-licenses",
        edges={"application": {"cred_said": app_said,
                               "schema_said": APP_SCHEMA_SAID, "op": "NI2I"}})
    _admit(hby_c, rgy_c, _disclose(hby_r, rgy_r, rogue_license))

    # It IS chain-verified and active — but issued by the wrong AID.
    assert rgy_c.reger.saved.get(keys=(rogue_license,)) is not None
    assert _tel_state(rgy_c, rogue_license) == "iss"
    rogue_issuer = rgy_c.reger.cloneCred(said=rogue_license)[0].issuer
    assert rogue_issuer == hab_r.pre and rogue_issuer != hab_d.pre

    # The gate trusts only the legit DOI, so the rogue license does not open it.
    mgr, _carrier = _build_carrier_manager(
        monkeypatch, tmp_path, qapp, trusted_issuer=hab_d.pre)
    mgr.reevaluate_role_gates(_vault(hby_c, rgy_c))
    assert "carrier" not in mgr._active_roles


def test_revoking_application_edge_target_leaves_gate_satisfied(
        monkeypatch, tmp_path, qapp, party):
    """Task 7 acceptance item — transitive edge revocation.

    Observed, by-design behavior: revoking the application (the NI2I edge
    target) while the license's OWN TEL stays ``iss`` does NOT re-close the
    gate. ``chain_verified`` derives from ``reger.saved``, which keripy pins at
    save time and does not re-evaluate when an edge target's TEL later changes.
    Transitive live edge-revocation is therefore a documented BOUND of the
    current gate, not a supported feature. Asserted here (not skipped)."""
    hby_c, hab_c, rgy_c = party("t10d_carrier", b"t10d_carrier_012345")
    hby_d, hab_d, rgy_d = party("t10d_doi", b"t10d_doi_0123456789")

    app_said = _issue(
        hby_c, hab_c, rgy_c, schema_said=APP_SCHEMA_SAID, recipient=hab_c.pre,
        attributes=APPLICATION_ATTRS, registry_name="carrier-apps")
    _admit(hby_d, rgy_d, _disclose(hby_c, rgy_c, app_said))
    license_said = _issue(
        hby_d, hab_d, rgy_d, schema_said=LICENSE_SCHEMA_SAID,
        recipient=hab_c.pre, attributes=LICENSE_ATTRS,
        registry_name="doi-licenses",
        edges={"application": {"cred_said": app_said,
                               "schema_said": APP_SCHEMA_SAID, "op": "NI2I"}})
    _admit(hby_c, rgy_c, _disclose(hby_d, rgy_d, license_said))

    mgr, _carrier = _build_carrier_manager(
        monkeypatch, tmp_path, qapp, trusted_issuer=hab_d.pre)
    mgr.reevaluate_role_gates(_vault(hby_c, rgy_c))
    assert "carrier" in mgr._active_roles  # activated first

    # Revoke the application (edge target) — carrier is its self-issuer.
    _revoke(hby_c, hab_c, rgy_c, "carrier-apps", app_said)
    assert _tel_state(rgy_c, app_said) == "rev"          # edge target revoked
    assert _tel_state(rgy_c, license_said) == "iss"       # license itself intact
    # save-time chain_verified: the license stays saved despite the revoked edge.
    assert rgy_c.reger.saved.get(keys=(license_said,)) is not None

    # Documented bound: the gate stays satisfied (no live transitive re-check).
    mgr.reevaluate_role_gates(_vault(hby_c, rgy_c))
    assert "carrier" in mgr._active_roles
