# -*- encoding: utf-8 -*-
"""HOA #4 core proof, in-process: one user identity applies for BOTH
Usurance roles via IPEX apply; admin grants each; both role surfaces
coexist (two entries in ``_active_roles``, two pages registered, no
re-auth); revoking actuary removes ONLY the actuary surface.

C2c (Task 7) extends this file for the third bundled role, ``cuo``, added by
the actuarial-HOA C2c EGF (Task 3): ``test_two_roles_coexist_and_revoke_
removes_exactly_one`` was left red by that change (the bundled EGF's persona
catalog grew from two roles to three, so ``derive_role_states`` now returns
a three-entry map) purely because it went stale, not because the coexistence
mechanism regressed — repaired below by extending every expected state map
to include ``cuo: AVAILABLE`` (this test never applies for or is granted
``cuo`` — it stays available throughout, an untouched third role bundled
alongside the two this test actually exercises). A NEW test,
``test_revoking_the_cuo_credential_removes_exactly_the_cuo_surface``, is the
one that actually exercises ``cuo``'s own grant/revoke/re-grant arc.

ACCEPTED BOUND: chain_verified is save-time only
-------------------------------------------------
``PluginManager._held_credential_view`` (``manager.py``) derives
``chain_verified`` from ``reger.saved`` membership, which keripy's
``Verifier.saveCredential`` pins ONCE, after the credential's full chain
(schema, registry, and any NI2I/I2I edge targets) verifies — and never
unwrites. Revoking a chained EDGE TARGET later (e.g. an application ACDC an
NI2I edge points at) does NOT flip a dependent credential's
``chain_verified`` back to False, so it does not, on its own, re-close a
gate. This is an accepted bound, already pinned by ``tests/integration/
test_carrier_gate_e2e.py::test_revoking_application_edge_target_leaves_
gate_satisfied`` — not a defect to fix here. What done-when #5 requires, and
what every test in this file exercises, is the ordinary case: the gate
closes on revocation of the ROLE credential itself (a real TEL ``rev`` on
that credential's own registry entry), which the ``chain_verified`` save-time
snapshot does not shield — a revoked credential's own ``state`` still reads
``"revoked"`` off the live TEL, and the gate predicate checks both.

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
from locksmith.plugins.cuo.plugin import CUO_ROLE_SCHEMA_SAID, CuoPlugin
from locksmith.plugins.product_designer.plugin import (
    PD_ROLE_SCHEMA_SAID,
    ProductDesignerPlugin,
)
from locksmith.ui.onboarding.role_states import RoleStatus, derive_role_states

# tests/plugins/conftest.py's DestroyingSurfaceHost, NOT a MagicMock: the
# revoke -> re-grant proof (test_revoking_the_cuo_credential_removes_exactly_
# the_cuo_surface, below) needs a host whose unregister_page ACTUALLY destroys
# the widget (setParent(None) + deleteLater, forced through via
# sendPostedEvents) for CuoPlugin.get_pages()'s `_is_alive` rebuild check to be
# exercised for real -- a MagicMock's unregister_page is a no-op call record,
# so get_pages() would just hand back the same (never-destroyed) widget and
# the re-grant leg would prove nothing about Task 2's rebuild-on-destroy fix.
from tests.plugins.conftest import DestroyingSurfaceHost, widget_is_live

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
ROLE_SCHEMAS = (ACTUARY_ROLE_SCHEMA_SAID, PD_ROLE_SCHEMA_SAID, CUO_ROLE_SCHEMA_SAID)

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


def _build_role_manager(monkeypatch, tmp_path, qapp, *, trusted_admin,
                        surface_host=None):
    """Discover the real bundled ``actuary`` + ``product_designer`` + ``cuo``
    plugins via their entry points under a usurance-shaped HOA brand, override
    their trusted issuer to the TEST admin AID, and wire a surface host.
    Mirrors ``_build_carrier_manager`` (carrier-gate e2e) with three gated
    plugins. ``surface_host`` defaults to a ``MagicMock`` (the sibling
    coexistence test only checks call records); pass a
    ``DestroyingSurfaceHost`` (``tests.plugins.conftest``) when a test needs
    ``.pages`` to genuinely reflect registered/destroyed widgets (the
    cuo-revoke-then-re-grant test does). Returns (manager, actuary_plugin,
    product_designer_plugin, cuo_plugin)."""
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
        # (brands/usurance/brand.toml's [plugins] bundled). C2c adds "cuo".
        lambda: SimpleNamespace(
            peel_core_pages=True,
            bundled_plugins=("actuary", "product_designer", "cuo")),
    )
    app = MagicMock()
    app.config = SimpleNamespace(base="", environment=Environments.DEVELOPMENT)
    mgr = PluginManager(app, keri_base=tmp_path / "keri")
    mgr.discover()  # loads + initializes all three role plugins (real QWidgets)

    plugins = []
    for pid, cls, schema_said in (
            ("actuary", ActuaryPlugin, ACTUARY_ROLE_SCHEMA_SAID),
            ("product_designer", ProductDesignerPlugin, PD_ROLE_SCHEMA_SAID),
            ("cuo", CuoPlugin, CUO_ROLE_SCHEMA_SAID)):
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
    mgr._surface_host = surface_host if surface_host is not None else MagicMock()
    return mgr, plugins[0], plugins[1], plugins[2]


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

    # (this test never touches "cuo" itself; _build_role_manager's now-three-
    # plugin bundle still hands it back for symmetry with the other two)
    mgr, actuary, product_designer, _cuo = _build_role_manager(
        monkeypatch, tmp_path, qapp, trusted_admin=admin_hab.pre)
    vault = _vault(user_hby, user_rgy)
    # A real exchanger so the framed applies genuinely persist in
    # hby.db.exns (frame_apply_for does NOT persist — same contract the
    # ServiceaidApplyDoer honors in serviceaid_bridge.py).
    vault.exc = exchanging.Exchanger(hby=user_hby, handlers=[])

    # Honest start: nothing held, nothing applied — all three roles
    # AVAILABLE, all gates shut. This test never touches "cuo" beyond this
    # point (it stays AVAILABLE throughout) — see
    # test_revoking_the_cuo_credential_removes_exactly_the_cuo_surface for
    # cuo's own grant/revoke/re-grant arc.
    states0 = derive_role_states(
        mgr._held_credentials(vault), list_sent_applies(user_hby, user_hab.pre),
        egf)
    assert states0 == {"actuary": RoleStatus.AVAILABLE,
                       "product_designer": RoleStatus.AVAILABLE,
                       "cuo": RoleStatus.AVAILABLE}
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
                       "product_designer": RoleStatus.AVAILABLE,
                       "cuo": RoleStatus.AVAILABLE}
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
    # This test only ever applies for actuary + product_designer — "cuo" is
    # deliberately never touched here (see test_revoking_the_cuo_credential_
    # removes_exactly_the_cuo_surface below), so the applied set is a PROPER
    # SUBSET of the now-three-member ROLE_SCHEMAS, not equal to it.
    assert {a["schema_said"] for a in applies} == {
        ACTUARY_ROLE_SCHEMA_SAID, PD_ROLE_SCHEMA_SAID}

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
                       "product_designer": RoleStatus.ACTIVE,
                       "cuo": RoleStatus.AVAILABLE}

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
    assert states3["cuo"] is RoleStatus.AVAILABLE


def test_revoking_the_cuo_credential_removes_exactly_the_cuo_surface(
        monkeypatch, tmp_path, qapp, haberies):
    """Done-when #5, for the role added in C2c. Follows the same issuer-side
    (registry.revoke -> SealEvent -> version-pinned interact -> Registrar.revoke)
    and holder-side (stream KEL+TEL into a fresh Tevery) recipes as the sibling
    test (test_two_roles_coexist_and_revoke_removes_exactly_one) — skipping the
    interact leaves the TEL unanchored and the revocation invisible.

    Uses a REAL ``DestroyingSurfaceHost`` (not the sibling test's MagicMock) so
    the re-grant leg genuinely exercises Task 2's rebuild-on-destroy fix
    (``CuoPlugin.get_pages()``'s ``_is_alive`` check) through the full
    activate/deactivate stack, not just bookkeeping: ``unregister_page`` here
    ACTUALLY destroys the widget, so handing back the same (dead) instance on
    re-grant would raise when the strategy re-registers it."""
    # -- parties (v1-pinned) ----------------------------------------------
    admin_hby, admin_hab, admin_rgy = _make_party(
        "t7_admin", b"t7_admin_0123456789")
    haberies.append(admin_hby)
    user_hby, user_hab, user_rgy = _make_party(
        "t7_user", b"t7_user_01234567890")
    haberies.append(user_hby)
    _seed_role_schemas(admin_hby)
    _seed_role_schemas(user_hby)
    egf = _bundle_egf()

    _introduce_kel(admin_hby, user_hab)

    host = DestroyingSurfaceHost()
    # Plugin refs unused here (unlike the sibling test): this test asserts
    # through the manager's own bookkeeping + the real surface host's
    # `.pages`, not per-plugin `register_page.assert_any_call` expectations.
    mgr, _actuary, _product_designer, _cuo = _build_role_manager(
        monkeypatch, tmp_path, qapp, trusted_admin=admin_hab.pre,
        surface_host=host)
    vault = _vault(user_hby, user_rgy)

    # -- arrange: all three roles active, as the sibling test does --------
    # (root credentials, same shape the sibling test issues — no apply
    # ceremony needed here since this test only cares about the granted/
    # revoked/re-granted arc, not the PENDING state the sibling already
    # covers.)
    cred_a = _issue(admin_hby, admin_hab, admin_rgy,
                    schema_said=ACTUARY_ROLE_SCHEMA_SAID,
                    recipient=user_hab.pre, attributes={},
                    registry_name=ADMIN_REGISTRY)
    _admit(user_hby, user_rgy, _disclose(admin_hby, admin_rgy, cred_a))
    cred_p = _issue(admin_hby, admin_hab, admin_rgy,
                    schema_said=PD_ROLE_SCHEMA_SAID,
                    recipient=user_hab.pre, attributes={},
                    registry_name=ADMIN_REGISTRY)
    _admit(user_hby, user_rgy, _disclose(admin_hby, admin_rgy, cred_p))
    cred_c = _issue(admin_hby, admin_hab, admin_rgy,
                    schema_said=CUO_ROLE_SCHEMA_SAID,
                    recipient=user_hab.pre, attributes={},
                    registry_name=ADMIN_REGISTRY)
    _admit(user_hby, user_rgy, _disclose(admin_hby, admin_rgy, cred_c))
    for said in (cred_a, cred_p, cred_c):
        assert user_rgy.reger.saved.get(keys=(said,)) is not None
        assert _tel_state(user_rgy, said) == "iss"

    mgr.reevaluate_role_gates(vault)
    assert mgr._active_roles == {"actuary", "product_designer", "cuo"}
    assert set(host.pages) == {"actuary", "product_designer", "cuo"}
    cuo_page_before = host.pages["cuo"]
    assert widget_is_live(cuo_page_before)

    states = derive_role_states(
        mgr._held_credentials(vault), list_sent_applies(user_hby, user_hab.pre),
        egf)
    assert states == {"actuary": RoleStatus.ACTIVE,
                      "product_designer": RoleStatus.ACTIVE,
                      "cuo": RoleStatus.ACTIVE}

    # -- revoke ONLY cuo: exactly the cuo surface unloads ------------------
    _revoke(admin_hby, admin_hab, admin_rgy, ADMIN_REGISTRY, cred_c)
    assert _tel_state(admin_rgy, cred_c) == "rev"
    _deliver_rev(user_hby, user_rgy, admin_hby, admin_rgy,
                 issuer_pre=admin_hab.pre, cred_said=cred_c)
    assert _tel_state(user_rgy, cred_c) == "rev"
    # the sibling credentials' own TELs are untouched by cuo's revocation
    assert _tel_state(user_rgy, cred_a) == "iss"
    assert _tel_state(user_rgy, cred_p) == "iss"

    mgr.reevaluate_role_gates(vault)
    assert "cuo" not in mgr._active_roles
    assert {"actuary", "product_designer"} <= mgr._active_roles
    assert "cuo" not in host.pages
    assert widget_is_live(cuo_page_before) is False, (
        "unregister_page must have actually destroyed the withdrawn cuo page"
    )
    # the sibling surfaces' own widgets were never touched
    assert set(host.pages) == {"actuary", "product_designer"}

    states = derive_role_states(
        mgr._held_credentials(vault), list_sent_applies(user_hby, user_hab.pre),
        egf)
    assert states["cuo"] is RoleStatus.REVOKED
    assert states["actuary"] is RoleStatus.ACTIVE
    assert states["product_designer"] is RoleStatus.ACTIVE

    # -- re-grant: prove the surface comes BACK (the arc the demo performs) --
    # A fresh cuo_role credential, issued and delivered exactly like the
    # first — this exercises Task 2's rebuild-on-destroy fix
    # (CuoPlugin.get_pages()'s _is_alive check) through the FULL
    # PluginManager -> RevealBundledSurface -> DestroyingSurfaceHost stack,
    # not a unit host.
    cred_c2 = _issue(admin_hby, admin_hab, admin_rgy,
                     schema_said=CUO_ROLE_SCHEMA_SAID,
                     recipient=user_hab.pre, attributes={},
                     registry_name=ADMIN_REGISTRY)
    _admit(user_hby, user_rgy, _disclose(admin_hby, admin_rgy, cred_c2))
    assert user_rgy.reger.saved.get(keys=(cred_c2,)) is not None
    assert _tel_state(user_rgy, cred_c2) == "iss"

    mgr.reevaluate_role_gates(vault)
    assert mgr._active_roles == {"actuary", "product_designer", "cuo"}
    assert "cuo" in host.pages
    cuo_page_after = host.pages["cuo"]
    assert widget_is_live(cuo_page_after)
    assert cuo_page_after is not cuo_page_before, (
        "get_pages() must not hand back the destroyed widget on re-grant"
    )

    states = derive_role_states(
        mgr._held_credentials(vault), list_sent_applies(user_hby, user_hab.pre),
        egf)
    assert states == {"actuary": RoleStatus.ACTIVE,
                      "product_designer": RoleStatus.ACTIVE,
                      "cuo": RoleStatus.ACTIVE}
