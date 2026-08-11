# -*- encoding: utf-8 -*-
"""The module that decides whether the actuary surface exists at all.

`ActuaryPage` is covered from several angles; the 67 lines that DECIDE the page
is built, keyed, gated and named were reached by nothing in this package. Every
defect this file pins is silent: a drifted page key unroutes the surface without
raising, a stale `_page` crashes the second reveal, a null icon resource is
swapped for a generic glyph by `MenuButton.__init__` rather than reported, and a
gate whose `credential_id` is dropped quietly falls back to a compiled-in AID no
other deployment can satisfy.

The revoke -> re-grant arc is driven through the REAL `RevealBundledSurface` and
the REAL `DestroyingSurfaceHost`, not a hand-rolled register/unregister pair:
`deactivate` calls `get_pages()` itself (role_activation.py:56), so the strategy
is part of the mechanism under test, not scaffolding around it.
"""
from __future__ import annotations

import copy
import json

import pytest
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget

from locksmith.plugins.actuary.plugin import (ACTUARY_ROLE_SCHEMA_SAID,
                                              ActuaryPlugin, USURANCE_ADMIN_AID)
from locksmith.plugins.actuary.page import ActuaryPage
from locksmith.plugins.base import VaultPlugin
from locksmith.plugins.credential_gate import RequiredCredential, gate_satisfied
from locksmith.plugins.manager import HeldCredential, PluginManager
from locksmith.plugins.role_activation import RevealBundledSurface
from locksmith.ui.vault.menu import MenuButton
from tests.plugins.conftest import DestroyingSurfaceHost, widget_is_live

# A 44-char AID that is emphatically not Usurance's. Used to RE-POINT the real
# bundled EGF at a different operator, which is the only way to tell "the gate
# read the ecosystem" apart from "the gate read its own literal" -- against the
# shipped EGF the two answers are the same string.
OTHER_ADMIN_AID = "E" + "M" * 43


def _plugin(app=None) -> ActuaryPlugin:
    plugin = ActuaryPlugin()
    plugin.initialize(app=app)
    return plugin


def _bundled_egf_sad() -> dict:
    """The egf-doc/0.1 SAD the ACTIVE brand ships, not the one in the source tree.

    `egf_local_dir()` is what `make_hoa_resolver` passes to the resolver, so this
    is the document the running app would gate against. It only answers at all
    because the package's autouse `usurance_brand` fixture has activated the
    brand -- an inactive brand returns None here, which is why that is asserted
    rather than skipped past.
    """
    from locksmith.core.branding import egf_local_dir

    egf_dir = egf_local_dir()
    assert egf_dir is not None, (
        "egf_local_dir() is None -- the usurance brand is not active, so this "
        "file would be asserting the plugin's literals against themselves")
    for path in sorted(egf_dir.glob("E*.json")):
        sad = json.loads(path.read_text())
        if sad.get("spec_version") == "egf-doc/0.1":
            return sad
    raise AssertionError(f"no egf-doc/0.1 document bundled in {egf_dir}")


def _egf_document(sad: dict):
    """A real `EgfDocument` through its only construction path (meta-schema
    validated), so a re-pointed SAD that no longer conforms fails loudly here
    instead of producing a document shape the gate never sees in production."""
    from keri_serviceaid.egf.documents import EgfDocument

    return EgfDocument.from_sad(sad)


@pytest.fixture
def brand_resources(usurance_brand):
    """Register the ACTIVE (usurance) brand's assets.rcc for one test.

    Deliberately not tests/conftest.py's `default_brand_resources`: that one
    `monkeypatch.delenv`s LOCKSMITH_BRAND_CONFIG and registers the *reference*
    bundle, which would deactivate the brand this package's autouse fixture just
    set up. Qt resource overlap is first-registered-wins, so the two cannot both
    be registered in one test.
    """
    from locksmith.core import branding

    rcc = branding.register_brand_resources()
    yield rcc
    branding.unregister_brand_resources()


# --- identity: one string, three places ------------------------------------------


def test_the_plugin_id_the_page_key_and_the_egf_role_id_are_one_string(qapp):
    """plugin.py:59 states the equality in a COMMENT and nothing enforced it.

    `hoa_shell` opens a role by guessing `_show_vault_page(role_id)` and
    `landing_page_key()` (base.py:162) returns `plugin_id` only when `get_pages()`
    happens to use it as a key. Drift any one of the three and the surface is
    built, registered and never reachable -- no exception anywhere, because each
    half is individually consistent. The EGF leg is what makes this more than two
    literals in one file agreeing with each other.
    """
    plugin = _plugin()
    pages = plugin.get_pages()

    assert plugin.plugin_id == "actuary"
    assert set(pages) == {plugin.plugin_id}, (
        f"get_pages() keys {sorted(pages)} -- the reveal registers under a key "
        "the shell will never ask for")
    assert isinstance(pages[plugin.plugin_id], ActuaryPage)
    assert plugin.landing_page_key() == plugin.plugin_id

    doc = _egf_document(_bundled_egf_sad())
    role = doc.role(plugin.plugin_id)          # EgfDocumentError if the id drifted
    assert role.id == plugin.plugin_id
    assert doc.micro_app_for_role(plugin.plugin_id).role_id == plugin.plugin_id
    assert role.onboarding is not None
    assert role.onboarding.grant_credential_id == \
        plugin.required_credential.credential_id, (
            "the EGF grants a different credential than the gate demands -- the "
            "role can be onboarded and the surface still never opens")


def test_the_plugin_is_dispatched_as_a_vault_plugin(qapp):
    """`PluginManager` reaches this plugin through `isinstance(plugin, VaultPlugin)`
    at eleven separate sites (manager.py:323, 342, 569, 663, 673, 708, 721, 740,
    745, 759) -- including `on_vault_opened`, which is what triggers the first
    role-gate evaluation. A plugin that stops being a `VaultPlugin` keeps its
    `plugin_id`, keeps its `required_credential`, still imports, still
    instantiates, and is simply never asked anything.
    """
    assert isinstance(ActuaryPlugin(), VaultPlugin)


# --- the gate ---------------------------------------------------------------------


def test_the_gate_demands_an_active_chain_verified_actuary_role(qapp):
    """Pinned as a DECISION, not as four attribute reads.

    Every field of `RequiredCredential` is consumed by one conjunct of the same
    predicate (`gate_satisfied`, credential_gate.py:96-99), so the honest test is
    to run the predicate: an actuary_role credential from the admin, active and
    chain-verified, opens the surface, and each single-field deviation closes it.
    Escrowed-but-not-verified is the one that matters most -- it is the state a
    credential is in while it is still arriving.

    The three declaration fields are asserted against the BUNDLED EGF, not
    against the constants the declaration is built from. `req.schema_said ==
    ACTUARY_ROLE_SCHEMA_SAID` and `USURANCE_ADMIN_AID in req.issuer_aids` were
    `X == X` -- both sides are the same imported literal, so drifting the pin
    moved both sides together and nothing went red. `required_state` is NOT
    asserted here at all: "active" is the dataclass default
    (credential_gate.py:37), so the assertion held with the kwarg deleted --
    measured. What the field DECIDES is pinned by the `state="revoked"` row
    below, which is the only honest form the claim has.
    """
    req = ActuaryPlugin.required_credential
    assert isinstance(req, RequiredCredential)

    egf = _bundled_egf_sad()
    catalog = {c["id"]: c for c in egf["credentials"]}
    entry = catalog[req.credential_id]      # KeyError if the gate names no entry
    assert req.credential_id == "actuary_role"
    assert req.schema_said == entry["schema_said"], (
        "the gate demands a schema the ecosystem's own catalog does not give "
        "actuary_role -- no issued role credential can ever match it")
    issuer_aids = {a["aid"] for a in egf["authorities"]
                   if a["role_id"] == entry["issuer_role"]}
    assert issuer_aids, "the premise is empty: the EGF names no issuer for this role"
    assert issuer_aids & set(req.issuer_aids), (
        f"the compiled-in fallback issuers {req.issuer_aids} include none of the "
        f"AIDs the bundled EGF trusts to issue actuary_role ({sorted(issuer_aids)})")

    def held(**over):
        base = dict(schema_said=ACTUARY_ROLE_SCHEMA_SAID,
                    issuer_aid=USURANCE_ADMIN_AID, state="active",
                    chain_verified=True, said="EHeldActuaryRoleCredentialSaid")
        base.update(over)
        return [HeldCredential(**base)]

    assert gate_satisfied(held(), req) is True
    assert gate_satisfied(held(state="revoked"), req) is False
    assert gate_satisfied(held(chain_verified=False), req) is False
    assert gate_satisfied(held(issuer_aid=OTHER_ADMIN_AID), req) is False
    assert gate_satisfied(held(schema_said="E" + "Z" * 43), req) is False
    assert gate_satisfied([], req) is False


def test_the_compiled_in_admin_aid_is_only_reached_when_the_egf_is_silent(qapp):
    """plugin.py:35 annotates `issuer_aids` "FALLBACK only". Measured here.

    Precedence lives in `PluginManager._resolved_gate` (manager.py:524-551), which
    hands the declaration to `resolve_from_egf` -- and that only re-points the gate
    when the plugin names a catalog entry. Drop `credential_id` and the annotation
    silently becomes a lie: the compiled-in Usurance AID is then the permanent
    trust root and an HOA deployed against any other ecosystem can never open the
    surface, with nothing raising to say so.

    Driven through the real `_resolved_gate` and `_matching_credential` (the
    production decision path) against the real bundled EGF, re-pointed at a
    different operator -- against the shipped EGF the resolved and compiled-in
    answers are the same string and prove nothing.
    """
    sad = copy.deepcopy(_bundled_egf_sad())
    doc = _egf_document(sad)
    issuer_role = doc.credential("actuary_role").issuer_role
    repointed = copy.deepcopy(sad)
    swapped = 0
    for authority in repointed["authorities"]:
        if authority["role_id"] == issuer_role:
            authority["aid"] = OTHER_ADMIN_AID
            swapped += 1
    assert swapped >= 1, f"no {issuer_role!r} authority to re-point in the EGF"

    manager = PluginManager.__new__(PluginManager)   # no app/vault on this path
    manager._egf_doc = _egf_document(repointed)
    effective = manager._resolved_gate(ActuaryPlugin.required_credential)

    assert effective.issuer_aids == [OTHER_ADMIN_AID]
    assert USURANCE_ADMIN_AID not in effective.issuer_aids, (
        "the ecosystem named its own authority and the gate still trusts the "
        "AID compiled into the plugin")
    assert effective.schema_said == ACTUARY_ROLE_SCHEMA_SAID, (
        "the catalog and the pin disagree on the actuary_role schema")

    def held(issuer):
        return [HeldCredential(schema_said=ACTUARY_ROLE_SCHEMA_SAID,
                               issuer_aid=issuer, state="active",
                               chain_verified=True, said="EHeldActuaryRole")]

    assert PluginManager._matching_credential(held(OTHER_ADMIN_AID),
                                              effective) is not None
    assert PluginManager._matching_credential(held(USURANCE_ADMIN_AID),
                                              effective) is None, (
        "a credential from the ORIGINAL admin still opens a gate the ecosystem "
        "re-pointed -- the fallback is acting as the trust root")


# --- revoke -> re-grant -----------------------------------------------------------


def test_a_withdrawn_actuary_surface_is_rebuilt_live_on_re_grant(qapp):
    """THE defect plugin.py:53-56 exists to prevent, reproduced on this plugin.

    Revocation runs `RevealBundledSurface.deactivate` -> `VaultPage.unregister_page`,
    which DESTROYS the widget (`setParent(None)` + `deleteLater`). The Python
    wrapper survives, so `self._page is not None` still answers True; handing that
    object to the next `register_page` reparents a dead C++ object and raises
    `RuntimeError: Internal C++ object (...) already deleted` straight out of the
    gate loop. Revoke -> re-grant is a real arc (a role credential is re-issued
    after a lapse), so this is a crash on a normal day, not a torture test.

    Measured with the real host before writing: the second register_page DOES
    raise once the DeferredDelete is forced -- the assertion below is not a
    formality. Liveness is read with `widget_is_live`, deliberately not
    `plugins.base._is_alive`, which is the function under test.
    """
    plugin = _plugin()
    host = DestroyingSurfaceHost()
    reveal = RevealBundledSurface()

    reveal.activate(plugin, credential=None, surface_host=host)
    first = host.pages["actuary"]
    assert widget_is_live(first)
    assert host.entries["actuary"] is not None

    reveal.deactivate(plugin, surface_host=host)
    assert widget_is_live(first) is False, (
        "the host did not really destroy the page, so this test cannot reach "
        "the defect it exists for")
    assert "actuary" not in host.pages
    assert "actuary" not in host.entries

    reveal.activate(plugin, credential=None, surface_host=host)   # must not raise

    second = host.pages["actuary"]
    assert widget_is_live(second), "the re-revealed surface is a dead widget"
    assert second is not first, "get_pages() handed back the destroyed page"
    assert isinstance(second, ActuaryPage)
    assert plugin._page is second


def test_a_living_page_is_handed_back_rather_than_rebuilt(qapp):
    """The negative half, and the reason the test above can fail at all.

    A `get_pages()` that built a fresh widget on every call would make the
    destroyed-widget branch unreachable -- and would also silently orphan the
    page the user is looking at on every gate re-poll (`GateRecheckDoer` runs
    every 2s), because the host would be handed a different widget under the same
    key while the old one keeps its listeners and its half-typed parse directory.
    """
    plugin = _plugin()

    first = plugin.get_pages()["actuary"]
    second = plugin.get_pages()["actuary"]

    assert second is first, "a fresh page per call throws away live page state"
    assert plugin._page is first
    assert widget_is_live(first)

    # ...and the identity survives the call `deactivate` itself makes.
    assert plugin.get_pages()["actuary"] is first


def test_re_initializing_forgets_a_page_that_was_destroyed(qapp):
    """`initialize` runs once per process today, but the destroyed page is the
    state it must not inherit: `_page` left pointing at a dead C++ object turns
    the FIRST reveal of the next run into the crash above. Pinning it here means
    the comment on plugin.py:42 is enforced rather than aspirational.
    """
    plugin = _plugin()
    host = DestroyingSurfaceHost()

    page = plugin.get_pages()["actuary"]
    host.register_page("actuary", page)
    host.unregister_page("actuary")
    assert widget_is_live(page) is False

    plugin.initialize(app=None)

    assert plugin._page is None, "a destroyed page survived re-initialization"
    fresh = plugin.get_pages()["actuary"]
    assert fresh is not page
    assert widget_is_live(fresh)


def test_the_page_is_built_with_the_app_initialize_was_handed(qapp):
    """`ActuaryPage` reaches the vault only through `self._app` -- it is what
    `attest()` calls `vault.extend` on and what the watch loop reads habs from.
    An `initialize` that drops it produces a page that builds, renders, gates and
    then cannot do the one thing it exists for, with the failure surfacing much
    later as a swallowed watch error.
    """
    app = object()
    plugin = _plugin(app=app)

    page = plugin.get_pages()["actuary"]

    assert page._app is app


# --- the sidebar entry -------------------------------------------------------------


def test_the_menu_entry_is_labelled_actuarial(qapp):
    """The label is the only thing naming this surface in the sidebar. Asserted
    on the QLabel `MenuButton` actually paints, not on the argument: a button
    built with a label it never renders looks identical in source review."""
    entry = _plugin().get_menu_entry()

    assert isinstance(entry, MenuButton)
    assert entry.label_text == "Actuarial"
    assert entry.text_label is not None, "no text label was created to paint"
    assert entry.text_label.text() == "Actuarial"


def test_the_menu_entry_paints_the_badge_glyph_not_the_generic_fallback(qapp,
                                                                        brand_resources):
    """A missing Qt resource yields a NULL QIcon with no error -- and
    `MenuButton.__init__` (menu.py:50) then quietly substitutes the generic
    puzzle-piece `extension.svg`. So `icon.isNull()` on the button is False even
    when the plugin's own artwork was never found: the actuary role would ship
    wearing the "unbranded plugin" glyph and every screenshot would look fine.

    The assertion is therefore on the PIXELS the sidebar paints, compared against
    both candidates, with a guard that the two candidates actually differ (if the
    bundle were unregistered both would be null images and compare equal, which
    would make the whole test vacuous).
    """
    entry = _plugin().get_menu_entry()

    badge = QIcon(":/assets/material-icons/badge.svg").pixmap(32, 32).toImage()
    fallback = QIcon(":/assets/material-icons/extension.svg").pixmap(32, 32).toImage()
    assert not badge.isNull(), f"badge.svg is not in {brand_resources}"
    assert badge != fallback, "the two glyphs render identically; nothing is measured"

    painted = entry.icon_label.pixmap()
    assert not painted.isNull(), "the sidebar entry paints no glyph at all"
    assert painted.toImage() == badge
    assert painted.toImage() != fallback, (
        "the entry is wearing the generic plugin glyph -- badge.svg did not resolve")


def test_the_role_contributes_no_submenu(qapp):
    """`RevealBundledSurface.activate` passes this straight to
    `add_menu_entry(plugin_id, entry, section)` (role_activation.py:51). A
    non-empty section pushes a second nav level over a plugin that registers
    exactly one page, so the entry would open a submenu whose only job is to
    lead back to the page the entry already is.
    """
    plugin = _plugin()

    assert plugin.get_menu_section() == []
    assert all(isinstance(w, QWidget) for w in plugin.get_menu_section())


# --- the documented no-ops ----------------------------------------------------------


def test_the_vault_hooks_do_not_disturb_the_revealed_surface(qapp):
    """These are declared no-ops, and "no-op" is a claim about the page as much as
    about the plugin. `on_vault_closed` clearing `_page` would leave the host
    still holding the widget it registered while the plugin builds a second one
    on the next `get_pages()` -- two live ActuaryPages, one of them invisible and
    still connected to its issue listener. `clear=True` (vault deletion) is
    included because that is the branch nothing else ever calls.
    """
    plugin = _plugin()
    page = plugin.get_pages()["actuary"]
    vault = object()

    plugin.on_vault_opened(vault)
    plugin.on_vault_closed(vault)
    plugin.on_vault_closed(vault, clear=True)

    assert plugin._page is page
    assert widget_is_live(page)
    assert plugin.get_pages()["actuary"] is page
