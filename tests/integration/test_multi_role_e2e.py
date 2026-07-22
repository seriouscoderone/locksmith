# -*- encoding: utf-8 -*-
"""HOA #4 core proof, in-process: one user identity applies for BOTH
Usurance roles via IPEX apply; admin grants each; both role surfaces
coexist (two entries in ``_active_roles``, two pages registered, no
re-auth); revoking actuary removes ONLY the actuary surface.

WHAT THIS PROVES (the spec's "done when")
-----------------------------------------
Two independently-gated role surfaces coexist on ONE self-incepted user
identity, and revoking one role credential deactivates exactly that one
surface:

  1. the user frames a REAL ``/ipex/apply`` exn for the actuary role
     (``frame_apply_for``) and persists it in its own exchanger — the
     per-role model derives PENDING for actuary while product_designer
     stays AVAILABLE;
  2. usurance-admin issues the edgeless (root) ``actuary_role`` ACDC into
     its ``usurance-admin`` registry; the user admits the disclosure set
     through the REAL keripy ``Kevery``/``Tevery``/``Verifier`` — the
     credential lands non-escrowed in ``reger.saved`` (never stubbed) and
     ``reevaluate_role_gates`` reveals EXACTLY the actuary surface;
  3. the SAME identity (same hab, same vault — no re-auth) applies for the
     product_designer role; admin grants; after the second admit BOTH roles
     are active, BOTH pages are registered on the surface host, and
     ``derive_role_states`` reads ACTIVE for both;
  4. admin revokes the actuary credential (real TEL ``rev``); the rev TEL
     event + its KEL anchor are delivered into the user's Tevery (the #3
     roundtrip e2e's rev-delivery idiom); the gate re-evaluation deactivates
     ONLY actuary — ``_active_roles == {"product_designer"}``, states read
     REVOKED/ACTIVE.

Real keripy verification throughout (Kevery/Tevery/Verifier, escrows
pumped); transport is in-process disclosure (the live two-app demo is the
transport acceptance, per the spec's testing posture).

TEST ADMIN vs PRODUCTION ADMIN
------------------------------
Both role plugins hardcode the production usurance-admin AID
(``EGjm-X1JMz-yKFeumEZ9meSVNvnV8VTXmjJMlyBVMMTO``). Our in-process admin is
freshly incepted, so — exactly like ``_build_carrier_manager``'s TEST DOI —
the discovered plugin instances' ``required_credential`` is OVERRIDDEN to
trust the test admin AID (mechanism test; the literal pins are asserted in
``tests/plugins/roles/test_pin_regression.py``). ``derive_role_states``
does not pin issuers (the gate owns issuer pinning), so the REAL bundled
EGF document is used verbatim.

V1 PROTOCOL PIN (CRITICAL fixture rule)
---------------------------------------
Every hab/registry here is v1-pinned (``_make_party`` pins ``Vrsn_1_0``);
every cross-party parser is ``version=Vrsn_1_0``. See the carrier-gate
e2e's "V1 PROTOCOL PIN" docstring for why.
"""
from __future__ import annotations

import json
from pathlib import Path

from keri.core import eventing, parsing, routing, scheming
from keri.kering import Kinds, Vrsn_1_0
from keri.peer import exchanging
from keri.vdr import eventing as teventing

from keri_serviceaid.egf.documents import EgfDocument
from keri_serviceaid.providers import frame_apply_for, list_sent_applies

from locksmith.core.credentialing import outputKEL, outputTEL
from locksmith.plugins.actuary.plugin import (
    ACTUARY_ROLE_SCHEMA_SAID,
    USURANCE_ADMIN_AID,
    ActuaryPlugin,
)
from locksmith.plugins.credential_gate import RequiredCredential
from locksmith.plugins.product_designer.plugin import (
    PD_ROLE_SCHEMA_SAID,
    ProductDesignerPlugin,
)
from locksmith.ui.onboarding.role_states import RoleStatus, derive_role_states

# Reuse the scaffold e2e's proven in-process fixture family (same test
# package): v1-pinned parties, the real no-backer issuance recipe, the
# mocked-transport disclose/admit halves (REAL Verifier), the mocked-OOBI
# KEL introduction, the issuer-side TEL revoke, the TEL-state probe, the
# minimal vault view, and the haberies teardown fixture (imported so pytest
# registers it here too). The manager builder is mirrored below for the two
# role plugins (``_build_role_manager``).
from tests.integration.test_carrier_gate_e2e import (  # noqa: F401 (haberies)
    _admit,
    _disclose,
    _introduce_kel,
    _issue,
    _make_party,
    _revoke,
    _tel_state,
    _vault,
    haberies,
)

# The NEW usurance-internal EGF bundle (Task 13): EGF doc + the two role
# schemas + the production admin OOBI. Anchored at the repo root so the test
# is cwd-independent.
_REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLE = _REPO_ROOT / "brands" / "usurance" / "egf"
ROLE_SCHEMAS = (ACTUARY_ROLE_SCHEMA_SAID, PD_ROLE_SCHEMA_SAID)

# Registry-name convention for the admin party (one registry, both role
# credential types — the brief's naming; ``_issue`` creates it by name on
# first use via ``_ensure_registry``).
ADMIN_REGISTRY = "usurance-admin"


def _seed_role_schemas(hby):
    """Pin both role schemas into ``hby.db.schema``. BOTH parties need them
    before issuance/admit: the issuer's ``Credentialer.validate`` resolves the
    schema at create time, and the holder's ``Verifier`` parks a credential in
    the missing-schema escrow (mse) otherwise. Round-trips each bundle file
    through ``Schemer`` so a SAID mismatch fails loudly here, not as an
    inexplicable escrow later."""
    for said in ROLE_SCHEMAS:
        sad = json.loads((BUNDLE / f"{said}.json").read_text())
        schemer = scheming.Schemer(sed=sad, kind=Kinds.json)
        assert schemer.said == said, f"bundle schema {said} does not verify"
        hby.db.schema.pin(keys=(schemer.said,), val=schemer)


def _bundle_egf():
    """The REAL bundled usurance-internal EGF document, verbatim (no re-said
    variant needed: ``derive_role_states`` keys on schema SAIDs + TEL state +
    chain_verified — issuer pinning is the gate's job, overridden below)."""
    for p in BUNDLE.glob("E*.json"):
        d = json.loads(p.read_text())
        if d.get("spec_version") == "egf-doc/0.1":
            return EgfDocument.from_sad(d)
    raise AssertionError("no EGF in bundle")


def _build_role_manager(monkeypatch, tmp_path, qapp, *, trusted_admin):
    """Discover the real bundled ``actuary`` + ``product_designer`` plugins
    via their entry points under a usurance-shaped HOA brand, override their
    trusted issuer to the TEST admin AID, and wire a mock surface host.
    Mirrors ``_build_carrier_manager`` (carrier-gate e2e) with two gated
    plugins. Returns (manager, actuary_plugin, product_designer_plugin)."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from locksmith.core.configing import Environments
    from locksmith.plugins import manager as manager_module
    from locksmith.plugins import storage
    from locksmith.plugins.manager import PluginManager

    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    monkeypatch.setattr(
        manager_module, "brand",
        # HOA #4: which surfaces a brand composes is brand config
        # (brands/usurance/brand.toml's [plugins] bundled).
        lambda: SimpleNamespace(peel_core_pages=True,
                                bundled_plugins=("actuary", "product_designer")),
    )
    app = MagicMock()
    app.config = SimpleNamespace(base="", environment=Environments.DEVELOPMENT)
    mgr = PluginManager(app, keri_base=tmp_path / "keri")
    mgr.discover()  # loads + initializes both role plugins (real QWidgets)

    plugins = []
    for pid, cls, schema_said in (
            ("actuary", ActuaryPlugin, ACTUARY_ROLE_SCHEMA_SAID),
            ("product_designer", ProductDesignerPlugin, PD_ROLE_SCHEMA_SAID)):
        plugin = mgr.get_plugin(pid)
        assert plugin is not None, f"{pid} entry point must be discoverable"
        assert isinstance(plugin, cls)
        # Prove each plugin ships trusting the PRODUCTION admin AID...
        assert plugin.required_credential.issuer_aids == [USURANCE_ADMIN_AID]
        # ...then override to the TEST admin for this in-process world.
        plugin.required_credential = RequiredCredential(
            schema_said=schema_said,
            issuer_aids=[trusted_admin],
            required_state="active",
        )
        plugins.append(plugin)
    mgr._surface_host = MagicMock()
    return mgr, plugins[0], plugins[1]


def _deliver_rev(user_hby, user_rgy, admin_hby, admin_rgy, *, issuer_pre,
                 cred_said):
    """The #3 roundtrip e2e's rev-delivery idiom: stream the issuer's KEL
    (carrying the rev anchor ixn) + the credential's TEL (now ending in
    ``rev``) into the user's stores through a fresh strict-shaped parser
    (Revery/Kevery/Tevery), escrows pumped — the in-process stand-in for the
    revocation TEL event arriving over transport."""
    stream = bytearray()
    stream.extend(outputKEL(admin_hby, issuer_pre))
    stream.extend(outputTEL(admin_rgy, cred_said))
    rvy = routing.Revery(db=user_hby.db)
    kvy = eventing.Kevery(db=user_hby.db, lax=True, local=False, rvy=rvy)
    kvy.registerReplyRoutes(router=rvy.rtr)
    tvy = teventing.Tevery(db=user_hby.db, reger=user_rgy.reger, local=False,
                           rvy=rvy)
    tvy.registerReplyRoutes(router=rvy.rtr)
    parsing.Parser(framed=True, kvy=kvy, tvy=tvy, rvy=rvy,
                   version=Vrsn_1_0).parse(ims=bytearray(stream))
    for _ in range(40):
        kvy.processEscrows()
        tvy.processEscrows()


def test_two_roles_coexist_and_revoke_removes_exactly_one(
        monkeypatch, tmp_path, qapp, haberies):
    # -- parties (v1-pinned) ----------------------------------------------
    admin_hby, admin_hab, admin_rgy = _make_party(
        "t14_admin", b"t14_admin_012345678")
    haberies.append(admin_hby)
    user_hby, user_hab, user_rgy = _make_party(
        "t14_user", b"t14_user_0123456789")
    haberies.append(user_hby)
    _seed_role_schemas(admin_hby)
    _seed_role_schemas(user_hby)
    egf = _bundle_egf()

    # Mocked OOBI: the admin must know the user's key state to issue TO it
    # (Credentialer.create requires recp in hby.kevers).
    _introduce_kel(admin_hby, user_hab)

    mgr, actuary, product_designer = _build_role_manager(
        monkeypatch, tmp_path, qapp, trusted_admin=admin_hab.pre)
    vault = _vault(user_hby, user_rgy)
    # A real exchanger so the framed applies genuinely persist in
    # hby.db.exns (frame_apply_for does NOT persist — same contract the
    # ServiceaidApplyDoer honors in serviceaid_bridge.py).
    vault.exc = exchanging.Exchanger(hby=user_hby, handlers=[])

    # Honest start: nothing held, nothing applied — both roles AVAILABLE,
    # both gates shut.
    states0 = derive_role_states(
        mgr._held_credentials(vault), list_sent_applies(user_hby, user_hab.pre),
        egf)
    assert states0 == {"actuary": RoleStatus.AVAILABLE,
                       "product_designer": RoleStatus.AVAILABLE}
    mgr.reevaluate_role_gates(vault)
    assert mgr._active_roles == set()
    mgr._surface_host.register_page.assert_not_called()

    # -- role 1: apply -> PENDING ------------------------------------------
    said_a, raw_a = frame_apply_for(
        user_hby, user_hab, schema_said=ACTUARY_ROLE_SCHEMA_SAID,
        recipient=admin_hab.pre, return_raw=True)
    # Persist into the sender's own exchanger (serviceaid_bridge idiom).
    parsing.Parser().parseOne(ims=bytes(raw_a), exc=vault.exc,
                              version=Vrsn_1_0)
    applies = list_sent_applies(user_hby, user_hab.pre)
    assert [a["schema_said"] for a in applies] == [ACTUARY_ROLE_SCHEMA_SAID]
    assert applies[0]["said"] == said_a
    assert applies[0]["recipient"] == admin_hab.pre

    states1 = derive_role_states(mgr._held_credentials(vault), applies, egf)
    assert states1 == {"actuary": RoleStatus.PENDING,
                       "product_designer": RoleStatus.AVAILABLE}
    mgr.reevaluate_role_gates(vault)
    assert mgr._active_roles == set()  # applying grants nothing

    # -- role 1: admin grants; user admits; gate opens EXACTLY one surface --
    # Root credential: no edge section; attributes={} — the a-block's d/i/dt
    # are protocol-filled (proving.credential), matching the role schema's
    # exact d,i,dt requirement with additionalProperties:false.
    cred_a = _issue(admin_hby, admin_hab, admin_rgy,
                    schema_said=ACTUARY_ROLE_SCHEMA_SAID,
                    recipient=user_hab.pre, attributes={},
                    registry_name=ADMIN_REGISTRY)
    _admit(user_hby, user_rgy, _disclose(admin_hby, admin_rgy, cred_a))
    # Genuinely chain-verified by the REAL keripy Verifier — never stubbed:
    # ``saved`` is pinned only by Verifier.saveCredential after schema +
    # registry + (edgeless) chain all verify.
    assert user_rgy.reger.saved.get(keys=(cred_a,)) is not None
    assert _tel_state(user_rgy, cred_a) == "iss"

    mgr.reevaluate_role_gates(vault)
    assert mgr._active_roles == {"actuary"}
    mgr._surface_host.register_page.assert_any_call(
        "actuary", actuary.get_pages()["actuary"])

    # -- role 2: second apply from the SAME identity, no re-auth ------------
    said_p, raw_p = frame_apply_for(
        user_hby, user_hab, schema_said=PD_ROLE_SCHEMA_SAID,
        recipient=admin_hab.pre, return_raw=True)
    parsing.Parser().parseOne(ims=bytes(raw_p), exc=vault.exc,
                              version=Vrsn_1_0)
    applies = list_sent_applies(user_hby, user_hab.pre)
    assert {a["schema_said"] for a in applies} == set(ROLE_SCHEMAS)

    cred_p = _issue(admin_hby, admin_hab, admin_rgy,
                    schema_said=PD_ROLE_SCHEMA_SAID,
                    recipient=user_hab.pre, attributes={},
                    registry_name=ADMIN_REGISTRY)
    _admit(user_hby, user_rgy, _disclose(admin_hby, admin_rgy, cred_p))
    assert user_rgy.reger.saved.get(keys=(cred_p,)) is not None
    assert _tel_state(user_rgy, cred_p) == "iss"
    mgr.reevaluate_role_gates(vault)

    # -- THE COEXISTENCE PROOF ----------------------------------------------
    assert mgr._active_roles == {"actuary", "product_designer"}
    mgr._surface_host.register_page.assert_any_call(
        "actuary", actuary.get_pages()["actuary"])
    mgr._surface_host.register_page.assert_any_call(
        "product_designer", product_designer.get_pages()["product_designer"])
    mgr._surface_host.unregister_page.assert_not_called()

    held = mgr._held_credentials(vault)
    states2 = derive_role_states(
        held, list_sent_applies(user_hby, user_hab.pre), egf)
    assert states2 == {"actuary": RoleStatus.ACTIVE,
                       "product_designer": RoleStatus.ACTIVE}

    # -- revoke actuary: exactly one surface unloads --------------------------
    _revoke(admin_hby, admin_hab, admin_rgy, ADMIN_REGISTRY, cred_a)
    assert _tel_state(admin_rgy, cred_a) == "rev"
    _deliver_rev(user_hby, user_rgy, admin_hby, admin_rgy,
                 issuer_pre=admin_hab.pre, cred_said=cred_a)
    # The user's OWN Tevery now reports the actuary credential revoked; the
    # product_designer credential is untouched.
    assert _tel_state(user_rgy, cred_a) == "rev"
    assert _tel_state(user_rgy, cred_p) == "iss"

    mgr.reevaluate_role_gates(vault)
    assert mgr._active_roles == {"product_designer"}
    mgr._surface_host.unregister_page.assert_called_once_with("actuary")

    held = mgr._held_credentials(vault)
    states3 = derive_role_states(
        held, list_sent_applies(user_hby, user_hab.pre), egf)
    assert states3["actuary"] is RoleStatus.REVOKED
    assert states3["product_designer"] is RoleStatus.ACTIVE
