# -*- encoding: utf-8 -*-
"""The watch machinery: what the actuary is allowed to believe she observed.

A mandate is never sent to this desk. It is found by reading somebody else's
KEL, and every step between "there is an anchor" and "this row is a mandate"
is a place where the page can fail two ways that look identical on screen:
observe nothing when a mandate exists, or observe something the KEL never
committed to. Neither failure is visible; both are permanent inputs to a
credential the actuary then mints.

So the fixtures here are REAL. `party` is a real `Habery`, a real `Regery`, a
real no-backer registry and genuinely issued, registry-backed
`product_mandate` ACDCs, whose issuance anchored real `SealEvent`s into a real
KEL — the same `{i: credential SAID, s: TEL sn, d: TEL event SAID}` shape
`providers/issue.py` writes. The seals the tests feed `_consider_seal` are read
back out of that KEL by a real `AnchorWatcher`, not hand-built. A MagicMock
`reger` would make every one of these tests pass against a `_consider_seal`
that skipped the chain walk entirely, which is precisely the check the seal
chain exists to be.

Two deliberate departures from "everything real", both named where they are
used:

* The CUO's hab is dropped from `hby.habs` once it has finished issuing. That
  leaves exactly the state a WATCHING wallet is in — the peer's KEL present in
  `kevers`, no entry in `habs` — which is what `_known_peer_pres` reads, and it
  avoids a two-Habery credential+TEL transfer that would test keripy's replay
  rather than this page.
* The pages under test are built with `app=None` and handed their vault
  afterwards, so the 1s poll timer never starts and a scan happens exactly when
  a test asks for one. `test_a_page_opened_over_a_real_vault_observes_before_the
  _first_tock` is the one exception, because the constructor's immediate first
  pass is itself a claim worth pinning.
"""
import dataclasses
import importlib
import json
import logging
import sys
import types
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem, QVBoxLayout, QWidget

from keri.app import habbing
from keri.app.anchoring import AnchorWatcher
from keri.core import eventing as core_eventing
from keri.core import parsing, scheming
from keri.core.serdering import SerderKERI
from keri.kering import Kinds, Vrsn_1_0
from keri.vdr import credentialing

from keri_serviceaid.providers.issue import issue_credential, revoke_credential
from keri_serviceaid.providers.sealed_retrieval import (
    SealChainError, credential_said_from_seal,
)

from locksmith.plugins.actuary import page as page_mod
from locksmith.plugins.actuary.page import (
    PRODUCT_MANDATE_SCHEMA_SAID, RATE_PROGRAM_ATTESTATION_SCHEMA_SAID, ActuaryPage,
)
from locksmith.plugins.actuary.plugin import ACTUARY_ROLE_SCHEMA_SAID

_REPO = Path(__file__).resolve().parents[3]

#: A seal in a real KEL that names no credential at all. `hab.interact` accepts
#: whatever a controller puts in an `a` block, and `AnchorWatcher.since` returns
#: anything carrying a `d` -- so this is legal KEL content the watch must step
#: over without holding on to it.
_SEAL_WITHOUT_I = {"d": "E" + "A" * 43, "s": 0}
#: A digest seal naming a credential this wallet has never heard of. Legal, and
#: the one shape that SHOULD be held pending: the body may yet arrive.
_SEAL_UNKNOWN_I = {"i": "E" + "Z" * 43, "s": "0", "d": "E" + "Y" * 43}


# --- harness -----------------------------------------------------------------


def _page(qtbot):
    """Copied from test_attest_safety.py rather than shared, so the two files
    stay independent while other agents edit them in parallel."""
    shell = QWidget()
    qtbot.addWidget(shell)
    shell.resize(1180, 940)
    layout = QVBoxLayout(shell)
    layout.setContentsMargins(0, 0, 0, 0)
    page = ActuaryPage(app=None, parent=shell)
    layout.addWidget(page)
    shell.show()
    qtbot.waitExposed(shell)
    return shell, page


class _Vault:
    """The two attributes the watch path reads off a vault: `hby` and `rgy`."""

    def __init__(self, hby, rgy):
        self.hby = hby
        self.rgy = rgy


class _App:
    def __init__(self, vault):
        self.vault = vault


def _watched_page(qtbot, vault):
    shell, page = _page(qtbot)
    page._app = _App(vault)
    return shell, page


def _egf_dir() -> Path:
    """The bundled usurance EGF directory, building the release bundle if a
    fresh clone has none (mirrors this package's conftest, which cannot be
    reused here: it is function-scoped and the parties below are not)."""
    for extra in (_REPO / "scripts", _REPO / "packaging"):
        if str(extra) not in sys.path:
            sys.path.insert(0, str(extra))
    brandlib = importlib.import_module("brandlib")
    out = brandlib.brand_release_dir("usurance", _REPO)
    if not (out / "brand.json").is_file():
        importlib.import_module("brand_apply").apply(
            "usurance", _REPO, out=out, check=False)
    return out / "egf"


def _pin_schema(hby, said):
    sad = json.loads((_egf_dir() / f"{said}.json").read_text())
    schemer = scheming.Schemer(sed=sad, kind=Kinds.json)
    hby.db.schema.pin(keys=(schemer.said,), val=schemer)
    return schemer


def _mandate_attrs(coverages, thesis="Utah auto is underpriced at the low-mileage end."):
    return {
        "line_of_business": "auto",
        "jurisdiction": "US-UT",
        "coverages": list(coverages),
        "window_opens": "2027-01-01",
        "window_closes": "2027-12-31",
        "thesis": thesis,
    }


def _seals_of(hab, pre):
    """Every digest seal in `pre`'s KEL, read by the real watcher, keyed by the
    credential SAID it names."""
    return {seal.get("i"): seal for _sn, seal in AnchorWatcher(hab=hab, pre=pre).since(-1)}


def _iss_sad(reger, said):
    return SerderKERI(raw=bytes(reger.cloneTvtAt(said, sn=0))).sad


class _Captured:
    """Attach pytest's caplog handler to a keripy `ogler` logger.

    `help.ogler.getLogger` returns a logger with `propagate = False` and its own
    stderr handler, so plain `caplog` sees NOTHING from this module -- a
    `chain_broken` assertion written against bare caplog would pass whether or
    not the line was ever emitted.
    """

    def __init__(self, caplog, name):
        self._logger = logging.getLogger(name)
        self._handler = caplog.handler
        self._caplog = caplog
        self._level = None

    def __enter__(self):
        self._level = self._logger.level
        self._logger.setLevel(logging.DEBUG)
        self._logger.addHandler(self._handler)
        return self._caplog

    def __exit__(self, *_exc):
        self._logger.removeHandler(self._handler)
        self._logger.setLevel(self._level)
        return False


# --- parties -----------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def _isolated_home(tmp_path_factory):
    """Belt and braces around the real `~/.keri`.

    Every store below is `temp=True`, which keeps keripy in its own tmpdir, but
    a single missed flag would have a test writing into the owner's live
    keystore, so HOME is pointed somewhere disposable for the whole module.
    """
    import os

    prior = os.environ.get("HOME")
    os.environ["HOME"] = str(tmp_path_factory.mktemp("actuary-watch-home"))
    yield
    if prior is None:
        os.environ.pop("HOME", None)
    else:
        os.environ["HOME"] = prior


@dataclasses.dataclass
class _Party:
    hby: object
    rgy: object
    side_rgy: object
    cuo_pre: str
    default_hab: object
    actuary_hab: object
    m1: str
    m2: str
    orphan: str
    role: str
    seals: dict
    role_seal: dict


@pytest.fixture(scope="module")
def party(_isolated_home):
    """A real CUO who has declared two mandates, plus the debris a real KEL
    carries alongside them.

    Built once because issuance is the expensive part (~0.2s each) and every
    test here reads it rather than writing it; the two tests that DO mutate the
    reger restore what they touched.
    """
    with habbing.openHby(name="actuary-watch", temp=True, version=Vrsn_1_0) as hby:
        for said in (PRODUCT_MANDATE_SCHEMA_SAID, ACTUARY_ROLE_SCHEMA_SAID):
            _pin_schema(hby, said)

        cuo = hby.makeHab(name="cuo", transferable=True, wits=[], toad=0,
                          version=Vrsn_1_0)
        default_hab = hby.makeHab(name="default", transferable=True, wits=[],
                                  toad=0, version=Vrsn_1_0)
        actuary_hab = hby.makeHab(name="actuary", transferable=True, wits=[],
                                  toad=0, version=Vrsn_1_0)

        rgy = credentialing.Regery(hby=hby, name="actuary-watch", temp=True)
        # A SECOND registry, in a store this wallet does not read. Its issuance
        # anchors a real seal into the same KEL while the TEL lands somewhere
        # else -- which is the measured shape of "the seal arrived before the
        # body", not a contrived one.
        side_rgy = credentialing.Regery(hby=hby, name="actuary-watch-side",
                                        temp=True)

        m1 = issue_credential(hby, cuo, rgy, schema_said=PRODUCT_MANDATE_SCHEMA_SAID,
                              recipient=None, attributes=_mandate_attrs(["BI", "PD"]),
                              registry_name=PRODUCT_MANDATE_SCHEMA_SAID)
        orphan = issue_credential(hby, cuo, side_rgy,
                                  schema_said=PRODUCT_MANDATE_SCHEMA_SAID,
                                  recipient=None,
                                  attributes=_mandate_attrs(["UM"]),
                                  registry_name=PRODUCT_MANDATE_SCHEMA_SAID)
        m2 = issue_credential(hby, cuo, rgy, schema_said=PRODUCT_MANDATE_SCHEMA_SAID,
                              recipient=None, attributes=_mandate_attrs(["COMP"]),
                              registry_name=PRODUCT_MANDATE_SCHEMA_SAID)

        # The body of the orphan, present locally with NO local TEL behind it.
        rgy.reger.creds.pin(keys=(orphan,),
                            val=side_rgy.reger.creds.get(keys=(orphan,)))

        # Legal KEL content that is not a credential anchor.
        cuo.interact(data=[dict(_SEAL_WITHOUT_I), dict(_SEAL_UNKNOWN_I)],
                     version=cuo.kever.serder.pvrsn)

        role = issue_credential(hby, actuary_hab, rgy,
                                schema_said=ACTUARY_ROLE_SCHEMA_SAID,
                                recipient=actuary_hab.pre, attributes={},
                                registry_name=ACTUARY_ROLE_SCHEMA_SAID)

        seals = _seals_of(cuo, cuo.pre)
        role_seal = _seals_of(actuary_hab, actuary_hab.pre)[role]
        cuo_pre = cuo.pre
        # The CUO is a PEER, not this wallet's identifier. Dropping the hab
        # leaves the exact state `_known_peer_pres` reads -- KEL in `kevers`,
        # nothing in `habs` -- without a second Habery and a credential+TEL
        # transfer that would be testing keripy's replay, not this page.
        del hby.habs[cuo_pre]

        yield _Party(hby=hby, rgy=rgy, side_rgy=side_rgy, cuo_pre=cuo_pre,
                     default_hab=default_hab, actuary_hab=actuary_hab,
                     m1=m1, m2=m2, orphan=orphan, role=role,
                     seals=seals, role_seal=role_seal)
        rgy.close()
        side_rgy.close()


@pytest.fixture
def vault(party):
    return _Vault(party.hby, party.rgy)


@pytest.fixture(scope="module")
def plain_party(_isolated_home):
    """A wallet with two identifiers and no credentials at all."""
    with habbing.openHby(name="actuary-watch-plain", temp=True,
                         version=Vrsn_1_0) as hby:
        hby.makeHab(name="default", transferable=True, wits=[], toad=0,
                    version=Vrsn_1_0)
        hby.makeHab(name="other", transferable=True, wits=[], toad=0,
                    version=Vrsn_1_0)
        rgy = credentialing.Regery(hby=hby, name="actuary-watch-plain", temp=True)
        yield _Vault(hby, rgy)
        rgy.close()


@pytest.fixture
def revoked_party(_isolated_home):
    """One mandate, declared and then withdrawn. Function-scoped: revocation is
    a one-way door, and sharing it would make every later test order-dependent."""
    with habbing.openHby(name="actuary-watch-rev", temp=True,
                         version=Vrsn_1_0) as hby:
        _pin_schema(hby, PRODUCT_MANDATE_SCHEMA_SAID)
        cuo = hby.makeHab(name="cuo", transferable=True, wits=[], toad=0,
                          version=Vrsn_1_0)
        rgy = credentialing.Regery(hby=hby, name="actuary-watch-rev", temp=True)
        said = issue_credential(hby, cuo, rgy,
                                schema_said=PRODUCT_MANDATE_SCHEMA_SAID,
                                recipient=None, attributes=_mandate_attrs(["BI"]),
                                registry_name=PRODUCT_MANDATE_SCHEMA_SAID)
        seal = _seals_of(cuo, cuo.pre)[said]
        revoke_credential(hby, cuo, rgy, credential_said=said,
                          registry_name=PRODUCT_MANDATE_SCHEMA_SAID)
        yield _Vault(hby, rgy), said, seal
        rgy.close()


@pytest.fixture
def aliased_party(_isolated_home):
    """A wallet holding no role credential whose habs are named "default" and
    something else, so "the brand's configured alias" and "the literal
    "default"" are two DIFFERENT identifiers.

    Function-scoped and its own Habery: the brand is monkeypatched over these
    tests, and a module-scoped fixture would carry the extra hab into every
    `party`-based test's `_known_peer_pres` and hab-iteration order.
    """
    with habbing.openHby(name="actuary-watch-alias", temp=True,
                         version=Vrsn_1_0) as hby:
        default_hab = hby.makeHab(name="default", transferable=True, wits=[],
                                  toad=0, version=Vrsn_1_0)
        aliased_hab = hby.makeHab(name="attesting", transferable=True, wits=[],
                                  toad=0, version=Vrsn_1_0)
        rgy = credentialing.Regery(hby=hby, name="actuary-watch-alias", temp=True)
        yield _Vault(hby, rgy), default_hab, aliased_hab
        rgy.close()


@pytest.fixture
def watching_only_vault(_isolated_home):
    """A wallet that has been paired with a peer and has NOT yet incepted an
    identifier of its own: a real peer KEL in `kevers`, `habs` empty.

    Not contrived -- it is the state between "the OOBI resolved" and "the user
    made their first AID", and the page's 1s poll runs throughout it.
    """
    with habbing.openHby(name="actuary-watch-hably", temp=True,
                         version=Vrsn_1_0) as hby:
        with habbing.openHby(name="actuary-watch-hably-far", temp=True,
                             version=Vrsn_1_0) as far_hby:
            far = far_hby.makeHab(name="far", transferable=True, wits=[], toad=0,
                                  version=Vrsn_1_0)
            kvy = core_eventing.Kevery(db=hby.db, lax=True, local=False)
            parsing.Parser(kvy=kvy, version=Vrsn_1_0).parse(
                ims=bytearray(far.replay()), kvy=kvy)
        rgy = credentialing.Regery(hby=hby, name="actuary-watch-hably", temp=True)
        assert hby.habs == {}, "the premise is gone: this wallet owns an identifier"
        assert far.pre in hby.kevers, "the peer KEL never landed"
        yield _Vault(hby, rgy), far.pre
        rgy.close()


@pytest.fixture
def bare_hby(_isolated_home):
    """A Habery with nothing pinned in `db.schema`."""
    with habbing.openHby(name="actuary-watch-bare", temp=True,
                         version=Vrsn_1_0) as hby:
        yield hby


# --- schema plumbing ---------------------------------------------------------


def test_a_tampered_bundled_schema_is_never_pinned(qtbot, bare_hby, tmp_path,
                                                   monkeypatch):
    """The check that stops a swapped schema file becoming authoritative.

    `hby.db.schema` is what `Verifier.processCredential` validates an arriving
    mandate against, so whatever is pinned under a SAID silently becomes the
    rules for that credential type. The bundle is a file on disk; if the pin
    trusted the filename instead of re-deriving the SAID from the bytes,
    dropping an altered schema next to the brand would redefine what counts as
    a valid mandate, with nothing on screen or in the ACDC to show for it.
    """
    sad = json.loads(
        (_egf_dir() / f"{PRODUCT_MANDATE_SCHEMA_SAID}.json").read_text())
    # One field, and a permissive one: `jurisdiction`'s pattern is what confines
    # a mandate to a US subdivision.
    sad["properties"]["a"]["oneOf"][1]["properties"]["jurisdiction"]["pattern"] = ".*"
    (tmp_path / f"{PRODUCT_MANDATE_SCHEMA_SAID}.json").write_text(json.dumps(sad))
    monkeypatch.setattr(page_mod, "egf_local_dir", lambda: tmp_path)

    _shell, page = _page(qtbot)
    with pytest.raises(RuntimeError, match="does not verify"):
        page._ensure_schema_pinned(bare_hby, PRODUCT_MANDATE_SCHEMA_SAID)

    assert bare_hby.db.schema.get(keys=(PRODUCT_MANDATE_SCHEMA_SAID,)) is None, (
        "a schema whose bytes do not re-derive to its SAID was pinned as the "
        "rules for every mandate this vault will ever validate")


def test_pinning_the_mandate_schema_makes_the_vault_able_to_recognise_one(
        qtbot, bare_hby):
    """The success path, asserted on the artefact rather than on the call.

    What matters is not that a function ran but that `hby.db.schema` now holds a
    `Schemer` under the mandate SAID -- without it `_scan_for_mandates` degrades
    to "nothing observed yet" forever, which is the failure mode this whole page
    was rebuilt to stop being invisible.
    """
    _shell, page = _page(qtbot)
    page._ensure_schema_pinned(bare_hby, PRODUCT_MANDATE_SCHEMA_SAID)

    pinned = bare_hby.db.schema.get(keys=(PRODUCT_MANDATE_SCHEMA_SAID,))
    assert pinned is not None
    assert pinned.said == PRODUCT_MANDATE_SCHEMA_SAID
    # The bundle carries the attestation schema too -- the mint side needs its
    # own pin, and one call must not have quietly pinned everything.
    assert bare_hby.db.schema.get(
        keys=(RATE_PROGRAM_ATTESTATION_SCHEMA_SAID,)) is None


def test_an_already_pinned_schema_never_touches_the_egf_directory_again(
        qtbot, bare_hby, monkeypatch):
    """`_prepare_import_schema` runs on construction and `attest()` calls this
    again for the attestation schema; a re-read of the bundle per call is a file
    read and a SAID re-derivation on the GUI thread for a question already
    answered. The short-circuit is asserted by making the directory lookup fatal:
    if it is reached at all, the test raises."""
    _shell, page = _page(qtbot)
    page._ensure_schema_pinned(bare_hby, PRODUCT_MANDATE_SCHEMA_SAID)

    def _explode():
        raise AssertionError("the EGF directory was read for an already-pinned schema")

    monkeypatch.setattr(page_mod, "egf_local_dir", _explode)
    page._ensure_schema_pinned(bare_hby, PRODUCT_MANDATE_SCHEMA_SAID)


def test_a_brand_with_no_bundled_egf_names_the_schema_it_could_not_resolve(
        qtbot, bare_hby, monkeypatch):
    """Failing closed is half of it; the other half is that the message has to
    carry the SAID, because the same RuntimeError is raised for the mandate this
    desk watches and for the attestation it mints, and those two failures have
    completely different consequences for the actuary."""
    monkeypatch.setattr(page_mod, "egf_local_dir", lambda: None)
    _shell, page = _page(qtbot)

    with pytest.raises(RuntimeError, match=PRODUCT_MANDATE_SCHEMA_SAID):
        page._ensure_schema_pinned(bare_hby, PRODUCT_MANDATE_SCHEMA_SAID)
    assert bare_hby.db.schema.get(keys=(PRODUCT_MANDATE_SCHEMA_SAID,)) is None


def test_a_schema_missing_from_the_bundle_names_the_path_it_looked_at(
        qtbot, bare_hby, tmp_path, monkeypatch):
    """An EGF directory that exists but is missing this schema is a build
    packaging fault, and the only thing that makes it diagnosable is the path
    that was searched. Without the `is_file` guard this surfaces as a bare
    FileNotFoundError out of `read_text` -- a stack trace instead of a sentence."""
    monkeypatch.setattr(page_mod, "egf_local_dir", lambda: tmp_path)
    _shell, page = _page(qtbot)

    with pytest.raises(RuntimeError, match="not bundled"):
        page._ensure_schema_pinned(bare_hby, PRODUCT_MANDATE_SCHEMA_SAID)


def test_a_failed_schema_prepare_becomes_on_screen_text_not_a_dead_page(
        qtbot, bare_hby, monkeypatch):
    """The wiring behind the placard the existing suite renders.

    `_prepare_import_schema` runs in the constructor. If it propagated, the
    whole surface would fail to build for a packaging fault; if it only logged,
    the page would sit there looking like a healthy quiet watch. It has to do
    the third thing -- swallow, and say so where the actuary is looking.

    The vault is deliberately one with NOTHING pinned: a vault that already has
    the schema short-circuits before the bundle is ever consulted, so this
    failure is only reachable on a cold one.
    """
    monkeypatch.setattr(page_mod, "egf_local_dir", lambda: None)
    _shell, page = _watched_page(qtbot, _Vault(bare_hby, None))
    page._watch_error = ""

    page._prepare_import_schema()          # must not raise

    assert "schema" in page._watch_error.lower()
    assert "cannot recognise a mandate" in page._watch_error
    page._render_empty_state()
    assert page._watch_retry.isVisible() is True


# --- identifier resolution ---------------------------------------------------


def test_the_attesting_hab_is_the_one_holding_the_actuary_role(qtbot, party, vault):
    """Not "the first hab", and not "the default" -- the one the role credential
    was actually issued to. This vault has two identifiers and the role belongs
    to the SECOND, so a scan that stops at the first, or a fallback that never
    looks, both mint the attestation from the wrong AID: a permanent, public
    credential whose issuer does not hold the role it claims to act under."""
    _shell, page = _page(qtbot)

    hab = page._actuary_hab(vault)

    assert hab is not None
    assert hab.pre == party.actuary_hab.pre
    assert hab.pre != party.default_hab.pre, "returned the first hab, not the holder"
    assert next(iter(party.hby.habs)) == party.default_hab.pre, (
        "the two-hab premise of this test has drifted; the role holder is now "
        "first in iteration order, so 'the first hab' would pass vacuously")


def test_the_attesting_hab_falls_back_to_the_alias_the_brand_configures(
        qtbot, aliased_party, monkeypatch):
    """A vault holding no role credential at all still has to name SOMETHING to
    attest from, or the button refuses with "No identifier available" and the
    actuary has no way to act. The fallback is the brand's own configured alias
    (`default_aid_alias`) -- which is the whole point, because a brand that
    calls its primary identifier anything else would otherwise attest from
    nothing.

    This test used to be unable to fail. It ran against the usurance brand,
    whose `default_aid_alias` IS the literal "default", so both halves of
    `brand().default_aid_alias or "default"` gave the same string: replacing the
    line with `alias = "default"` -- deleting the brand read the docstring says
    is the point -- left the file at 28 passed. Measured. So the brand here
    names something the fallback literal cannot reach.
    """
    from locksmith.core.branding import brand

    vault, default_hab, aliased_hab = aliased_party
    assert brand().default_aid_alias != "attesting", (
        "the active brand already configures this alias, so the monkeypatch "
        "below changes nothing and the test is vacuous again")

    # Patched AFTER construction: the page reads the real brand while it builds.
    _shell, page = _page(qtbot)
    monkeypatch.setattr(page_mod, "brand",
                        lambda: types.SimpleNamespace(default_aid_alias="attesting"))

    hab = page._actuary_hab(vault)

    assert hab is not None, "no identifier to attest from"
    assert hab.pre == aliased_hab.pre
    assert hab.pre != default_hab.pre, (
        "the hardcoded literal was used, not the alias the brand configures")


def test_a_brand_that_configures_no_alias_still_names_an_identifier(
        qtbot, aliased_party, monkeypatch):
    """`default_aid_alias` is optional, and `or "default"` is what stops an
    unset one becoming `habByName(None)`. Without the fallback the Attest button
    refuses with "No identifier available to attest from" on a wallet that has a
    perfectly good identifier -- and nothing raises to say why."""
    vault, default_hab, aliased_hab = aliased_party
    _shell, page = _page(qtbot)
    monkeypatch.setattr(page_mod, "brand",
                        lambda: types.SimpleNamespace(default_aid_alias=None))

    hab = page._actuary_hab(vault)

    assert hab is not None, "an unset brand alias left the actuary unable to attest"
    assert hab.pre == default_hab.pre
    assert hab.pre != aliased_hab.pre


# --- the EGF document --------------------------------------------------------


def test_the_egf_document_is_the_real_one_and_admits_the_mandate_schema(qtbot):
    """`verify_attestation` fails CLOSED on `accepted_schema_saids`, so resolving
    the wrong object here -- the resolver instead of the document, say -- does not
    raise, it just silently refuses every mandate forever. Asserted against the
    bundled ecosystem's real accepted list, not against a stub."""
    _shell, page = _page(qtbot)

    doc = page._egf_doc()

    assert doc is not None, "the usurance brand pins an EGF; None means it was lost"
    assert PRODUCT_MANDATE_SCHEMA_SAID in doc.accepted_schema_saids
    assert RATE_PROGRAM_ATTESTATION_SCHEMA_SAID in doc.accepted_schema_saids


def test_a_brand_with_no_egf_caches_the_none_instead_of_re_resolving(
        qtbot, monkeypatch):
    """`None` is a legitimate steady state (a brand with no EGF pinned), which is
    why the cache sentinel is the string "unresolved" and not None. A cache that
    only remembers truthy answers re-runs resolution on every 1s tick forever --
    reading and re-validating the EGF bundle off disk, on the GUI thread, to
    reach the same answer."""
    calls = []

    def _resolver(brand):
        calls.append(brand)
        return None

    monkeypatch.setattr("locksmith.core.egf_seeding.make_hoa_resolver", _resolver)
    _shell, page = _page(qtbot)
    page._egf_doc_cache = "unresolved"

    assert page._egf_doc() is None
    assert page._egf_doc() is None

    assert len(calls) == 1, f"resolved {len(calls)} times; None was not cached"
    assert page._egf_doc_cache is None
    assert page._watch_error == "", "a legitimate no-EGF brand is not a failure"


def test_a_raising_egf_resolver_is_reported_on_screen_and_not_retried(
        qtbot, monkeypatch):
    """A corrupt or unresolvable EGF bundle means no mandate can ever be
    verified. Swallowed into the log, that is pixel-identical to a healthy watch
    with nothing to observe; and re-raised every tick it would be an exception
    per second out of a QTimer slot."""
    calls = []

    def _resolver(brand):
        calls.append(brand)
        raise RuntimeError("the EGF bundle is unreadable")

    monkeypatch.setattr("locksmith.core.egf_seeding.make_hoa_resolver", _resolver)
    _shell, page = _page(qtbot)
    page._egf_doc_cache = "unresolved"
    page._watch_error = ""

    assert page._egf_doc() is None
    assert page._egf_doc() is None

    assert len(calls) == 1, "a failure that is not cached is retried every tick"
    assert "governance framework could not be resolved" in page._watch_error
    page._render_empty_state()
    assert "not working" in page._empty_state.text().lower()


# --- watch candidates --------------------------------------------------------


def test_the_wallets_own_identifiers_are_not_watch_candidates(
        qtbot, plain_party):
    """Watching your own KEL is not watching. Every anchor this wallet writes --
    every registry inception, every credential it issues itself -- would come
    back through the watcher as a candidate mandate, and the attestation the
    actuary mints here anchors into her own KEL too.

    The peer is REAL: a separate Habery's inception event replayed in, which is
    how a paired peer's KEL actually lands (`kevers` populated by replay, no
    entry in `habs`).
    """
    with habbing.openHby(name="actuary-watch-far", temp=True,
                         version=Vrsn_1_0) as far_hby:
        far = far_hby.makeHab(name="far", transferable=True, wits=[], toad=0,
                              version=Vrsn_1_0)
        kvy = core_eventing.Kevery(db=plain_party.hby.db, lax=True, local=False)
        parsing.Parser(kvy=kvy, version=Vrsn_1_0).parse(
            ims=bytearray(far.replay()), kvy=kvy)

        _shell, page = _page(qtbot)
        candidates = page._known_peer_pres(plain_party)

        assert far.pre in candidates, "a replayed peer KEL is not being watched"
        own = set(plain_party.hby.habs.keys())
        assert own, "the premise is empty: this wallet owns no identifiers"
        assert own.isdisjoint(candidates), (
            f"the wallet is watching its own identifiers: "
            f"{sorted(own & set(candidates))}")


def test_the_same_watcher_is_reused_so_its_cursor_survives_the_poll(qtbot, party):
    """`AnchorWatcher.checkpoint` starts at -1 and is a SCAN CURSOR. A fresh
    watcher per poll resets it, so every anchor in the peer's whole KEL is
    re-reported once a second, forever -- every one of them re-walked through the
    TEL and the chain, and every unresolvable one re-logged as pending."""
    _shell, page = _page(qtbot)

    first = page._watcher_for(party.default_hab, party.cuo_pre)
    assert page._watcher_for(party.default_hab, party.cuo_pre) is first

    first.since(first.checkpoint)
    advanced = first.checkpoint
    assert advanced > -1, "the premise is empty: this KEL has no events"
    assert page._watcher_for(party.default_hab, party.cuo_pre).checkpoint == advanced

    other = page._watcher_for(party.default_hab, party.actuary_hab.pre)
    assert other is not first
    assert set(page._watchers) == {party.cuo_pre, party.actuary_hab.pre}


# --- _consider_seal: every refusal, and the one acceptance -------------------


def test_a_seal_with_no_credential_and_one_already_observed_are_both_refused(
        qtbot, party, vault):
    """Two guards in one line, and the second is the one with teeth: re-walking a
    mandate already on screen would overwrite the recorded row every second. The
    sentinel below is what makes that visible -- a re-walk succeeds, so the return
    value alone cannot tell you whether the guard fired."""
    _shell, page = _watched_page(qtbot, vault)
    page._observed[party.m1] = {"line_of_business": "SENTINEL"}

    assert page._consider_seal(vault, _SEAL_WITHOUT_I) is False
    assert page._consider_seal(vault, {}) is False
    assert page._consider_seal(vault, party.seals[party.m1]) is False

    assert page._observed[party.m1] == {"line_of_business": "SENTINEL"}, (
        "an already-observed mandate was re-walked and its row rewritten")
    assert set(page._observed) == {party.m1}


def test_a_credential_that_has_not_landed_yet_is_a_normal_refusal_not_an_error(
        qtbot, party, vault):
    """THE most common answer this function gives, and it must be boring.

    A seal is what tells you a body exists, so the body necessarily arrives
    afterwards -- measured on one run, 11 seconds afterwards. If "not here yet"
    painted the watch as broken, the page would show a red placard for every
    mandate in the seconds before it arrived; if it raised, the scan would die.
    The registry-inception anchor below is real KEL content of exactly this
    shape: an `i` that names no credential this reger has.
    """
    _shell, page = _watched_page(qtbot, vault)
    page._watch_error = ""
    unknown = _SEAL_UNKNOWN_I

    assert page._consider_seal(vault, unknown) is False

    assert page._observed == {}
    assert page._watch_error == "", (
        "a body that has simply not arrived yet painted the watch as broken")


def test_an_anchor_for_a_different_schema_is_refused(qtbot, party, vault):
    """A KEL's `a` block is not reserved for mandates. The role credential this
    desk is gated on is itself registry-backed, so its issuance anchored a seal
    of the identical shape -- and its schema IS in the ecosystem's accepted list,
    so `verify_attestation` says yes to it. Without the schema check the actuary
    would find her own role credential rendered as a mandate she could attest a
    rate program against."""
    _shell, page = _watched_page(qtbot, vault)

    creder = vault.rgy.reger.creds.get(keys=(party.role,))
    assert creder is not None and creder.schema == ACTUARY_ROLE_SCHEMA_SAID
    assert creder.schema in page._egf_doc().accepted_schema_saids, (
        "the premise is gone: this schema is no longer EGF-accepted, so the "
        "verdict check would refuse it anyway and this test proves nothing")

    assert page._consider_seal(vault, party.role_seal) is False
    assert page._observed == {}


def test_a_seal_whose_d_does_not_re_derive_to_the_tel_event_is_refused(
        qtbot, party, vault, caplog):
    """The security-relevant refusal: the difference between believing a KEL
    commitment and believing an unverified field.

    A seal is `a`-block content and `hab.interact` accepts whatever a controller
    puts there, so `seal["i"]` on its own is a claim, not evidence. The chain
    reads the credential SAID out of the TEL event the seal's `d` COMMITS to.
    Here `d` is swapped for another real TEL event's digest, leaving a
    well-formed seal naming a real mandate that this KEL never committed to.
    """
    tampered = dict(party.seals[party.m1])
    tampered["d"] = _iss_sad(vault.rgy.reger, party.m2)["d"]
    assert tampered["i"] == party.m1, "the swap must leave the claimed `i` intact"

    _shell, page = _watched_page(qtbot, vault)
    with _Captured(caplog, "locksmith.plugins.actuary.page"):
        assert page._consider_seal(vault, tampered) is False

    assert page._observed == {}, (
        "a seal was believed on the strength of its own `i` field")
    assert "chain_broken" in caplog.text


def test_a_seal_naming_a_credential_the_committed_event_does_not_name(
        qtbot, party, vault):
    """The chain's third failure mode, pinned at the library that owns it.

    `credential_said_from_seal` returns the SAID the KEL committed to, and it
    refuses when the seal's own `i` contradicts it. Both artefacts here are real:
    a real `iss` event, and a seal that genuinely re-derives to it (so
    `verifySealedBody` passes) while naming a different mandate.

    The page cannot be driven into this branch, because it fetches the TEL event
    BY `seal["i"]` -- see this file's report. The page-level half below asserts
    the refusal it does reach for the same malformed seal.
    """
    iss2 = _iss_sad(vault.rgy.reger, party.m2)
    liar = {"i": party.m1, "s": "0", "d": iss2["d"]}
    assert iss2["i"] == party.m2

    with pytest.raises(SealChainError, match="disagree"):
        credential_said_from_seal(liar, iss2)

    _shell, page = _watched_page(qtbot, vault)
    assert page._consider_seal(vault, liar) is False
    assert page._observed == {}


def test_a_substituted_body_under_a_committed_said_is_refused(qtbot, party, vault):
    """Step (c) of the chain: the body that landed must BE the credential the
    KEL committed to.

    The reger is corrupted the only way that reaches this branch -- the `creds`
    table maps m1's SAID to m2's body, which is exactly the substitution
    `sealed_retrieval` describes as "a well-formed credential that the KEL never
    committed to". Without the comparison the page records m2's attributes under
    m2's SAID from an anchor that committed to m1.
    """
    reger = vault.rgy.reger
    original = reger.creds.get(keys=(party.m1,))
    substitute = reger.creds.get(keys=(party.m2,))
    assert substitute.said != party.m1

    _shell, page = _watched_page(qtbot, vault)
    reger.creds.pin(keys=(party.m1,), val=substitute)
    try:
        assert page._consider_seal(vault, party.seals[party.m1]) is False
        assert page._observed == {}
    finally:
        reger.creds.pin(keys=(party.m1,), val=original)

    assert reger.creds.get(keys=(party.m1,)).said == party.m1, "reger not restored"


def test_a_revoked_mandate_is_not_observable(qtbot, revoked_party):
    """A mandate can be withdrawn -- the schema says so, and the whole reason it
    is registry-backed is that a consumer must learn of the withdrawal from
    registry state without asking the CUO. The anchor stays in the KEL forever,
    so the ONLY thing standing between a cancelled initiative and an actuary
    attesting a rate program against it is this TEL read."""
    vault, said, seal = revoked_party
    _shell, page = _watched_page(qtbot, vault)

    reger = vault.rgy.reger
    creder = reger.creds.get(keys=(said,))
    state = reger.tevers.get(creder.regid).vcState(creder.said)
    assert page_mod._TEL_STATE_LABELS.get(state.et) == "revoked", (
        f"keripy reports the withdrawn state as {state.et!r}, which this page's "
        "label map does not translate to 'revoked'")

    assert page._consider_seal(vault, seal) is False
    assert page._observed == {}


def test_a_schema_the_ecosystem_has_not_admitted_is_refused(qtbot, party, vault,
                                                            monkeypatch):
    """`accepted_schema_saids` is the EGF's list of credential types this
    ecosystem has admitted, and it is the ONLY thing tying a well-formed,
    correctly-chained mandate to this ecosystem rather than any other. The
    document below is a real `EgfDocument` with that one tuple narrowed, not a
    stand-in with an attribute of the right name."""
    _shell, page = _watched_page(qtbot, vault)
    narrowed = dataclasses.replace(page._egf_doc(), accepted_schema_saids=())
    page._egf_doc_cache = narrowed

    assert page._consider_seal(vault, party.seals[party.m1]) is False
    assert page._observed == {}

    # ... and it is genuinely the EGF check doing the refusing.
    page._egf_doc_cache = "unresolved"
    assert page._consider_seal(vault, party.seals[party.m1]) is True


def test_an_observed_mandate_carries_all_seven_fields_including_its_issuer(
        qtbot, party, vault):
    """The happy path, and the shape of the row it records.

    Four of these were previously never read: the window, the thesis, and the
    issuer. The issuer is the one that changes an answer rather than an
    appearance -- two different AIDs declaring `auto / US-UT` produced
    indistinguishable rows, and the attestation's edge asserts "my rate program
    answers THAT mandate" about exactly one of them.
    """
    _shell, page = _watched_page(qtbot, vault)

    assert page._consider_seal(vault, party.seals[party.m1]) is True

    assert page._observed[party.m1] == {
        "line_of_business": "auto",
        "jurisdiction": "US-UT",
        "coverages": ["BI", "PD"],
        "window_opens": "2027-01-01",
        "window_closes": "2027-12-31",
        "thesis": "Utah auto is underpriced at the low-mileage end.",
        "issuer": party.cuo_pre,
    }


# --- _consider_one: the blast radius -----------------------------------------


def test_one_unreadable_anchor_does_not_kill_the_rest_of_the_scan(
        qtbot, party, vault, monkeypatch):
    """The measured incident this function's docstring records.

    A credential whose body arrived but whose TEL has not is not exotic -- it is
    the ordinary state while a watch catches up, and `cloneTvtAt` raises
    `MissingEntryError` for it. That exception used to propagate out of
    `_scan_for_mandates` and kill the whole loop, INCLUDING the
    `_refresh_observed_list()` at the end: one run had the mandate retrieved,
    verified and recorded in `_observed`, and the list still rendered empty
    forever, because a later unrelated seal raised before the repaint.

    The KEL here has that shape for real: m1's anchor, then the orphan's (body
    pinned locally, TEL in a store this wallet does not read), then m2's.
    """
    reger = vault.rgy.reger
    assert reger.creds.get(keys=(party.orphan,)) is not None
    with pytest.raises(Exception):
        reger.cloneTvtAt(party.orphan, sn=0)

    _shell, page = _watched_page(qtbot, vault)

    assert page._consider_one(vault, party.seals[party.orphan]) is False

    page._scan_for_mandates()

    assert set(page._observed) == {party.m1, party.m2}, (
        "an unrelated unreadable anchor took the whole scan down with it")
    assert page._observed_list.count() == 2, "the repaint never happened"
    assert page._observed_list.isVisible() is True


# --- _scan_for_mandates ------------------------------------------------------


def test_a_scan_with_no_vault_still_stamps_the_clock(qtbot, monkeypatch):
    """The heartbeat is the only evidence this page can honestly give that the
    poll is alive, and a scan that cannot run because there is no vault is still
    a scan that happened. Stamping after the early return would freeze the
    timestamp at "Waiting for the first check…" on exactly the page that most
    needs to say something."""
    ticks = iter(["11/04/2026 9:15 AM", "11/04/2026 9:16 AM"])

    class _Now:
        def strftime(self, _fmt):
            return next(ticks)

    monkeypatch.setattr(page_mod, "_dt",
                        types.SimpleNamespace(
                            datetime=types.SimpleNamespace(now=lambda: _Now())))
    _shell, page = _page(qtbot)
    assert page._app is None
    assert page._last_checked == ""

    page._scan_for_mandates()
    first = page._last_checked
    page._scan_for_mandates()

    assert first == "11/04/2026 9:15 AM"
    assert page._last_checked == "11/04/2026 9:16 AM", "the heartbeat is frozen"
    # In its OWN label, not the last line of the placard. Inside it, the
    # timestamp read as part of the explanation of what a mandate is -- and it
    # disappeared entirely once a mandate arrived and the placard was hidden,
    # which is when a stalled poll matters most.
    assert "Last checked 11/04/2026 9:16 AM" in page._heartbeat.text()
    assert "Last checked" not in page._empty_state.text()

    # ...and it keeps reporting once there is something to show.
    page._observed = {"E" + "z" * 43: {"line_of_business": "auto",
                                       "jurisdiction": "US-UT", "coverages": []}}
    page._render_empty_state()
    assert page._empty_state.isVisible() is False
    assert "Last checked" in page._heartbeat.text(), (
        "the only liveness signal vanished as soon as the placard did")


def test_a_wallet_with_a_peer_kel_and_no_identifier_of_its_own_scans_cleanly(
        qtbot, watching_only_vault):
    """`_watcher_for` needs a hab to read the peer's KEL through -- it is the
    `hab.db` inside `AnchorWatcher.since` -- and a wallet paired before it
    incepts anything has a peer in `kevers` and nothing in `habs`.

    So the early return is not defensive: without it the very first tick after
    an OOBI resolves builds `AnchorWatcher(hab=None, ...)` and dies on
    `None.db`, out of a QTimer slot, once a second. The artefact is that no
    watcher was built at all.
    """
    vault, peer_pre = watching_only_vault
    _shell, page = _watched_page(qtbot, vault)
    assert peer_pre in page._known_peer_pres(vault), (
        "the premise is gone: this wallet has no peer to be tempted by")

    page._scan_for_mandates()          # must not raise

    assert page._watchers == {}, "a watcher was built with no hab to read through"
    assert page._observed == {}
    assert page._last_checked, "the heartbeat did not stamp"
    assert page._empty_state.isVisible() is True


# --- selection: which mandate the edge will name -----------------------------


def test_a_click_selects_the_row_that_was_clicked_not_the_first_one(
        qtbot, party, vault):
    """The one step in the attest flow that decides WHICH mandate a permanent
    public credential answers, and it was reached by nothing.

    Everything downstream is exhaustively covered -- the NI2I edge, the far
    node's SAID, the read-back -- but all of it takes `_selected_mandate_said`
    as given. Measured: replacing this handler's body with `item = None` left
    the package at 114 passed. So a hardcoded first row, or an off-by-one,
    would mint an edge naming a mandate the actuary never chose, and the label
    on screen would agree with it.

    Driven by EMITTING the signal the page is connected to: devctl's
    `click_list_item` and a real mouse both fire
    `QAbstractItemView.clicked(QModelIndex)`, not `itemClicked` (page.py:250).
    """
    _shell, page = _watched_page(qtbot, vault)
    page._scan_for_mandates()
    rows = [page._observed_list.item(i).data(Qt.UserRole)
            for i in range(page._observed_list.count())]
    assert rows == [party.m1, party.m2], (
        f"the two-row premise has drifted: {rows} -- row 1 must not be row 0")

    page._observed_list.clicked.emit(page._observed_list.model().index(1, 0))

    assert page._selected_mandate_said == party.m2, (
        "the second mandate was clicked and the first was selected")
    label = page._selected_label.text()
    assert party.m2 in label, f"the label does not name the selection: {label}"
    assert party.m1 not in label
    assert "auto / US-UT" in label


def test_a_click_delivered_against_a_row_that_has_gone_leaves_the_choice_alone(
        qtbot, party, vault):
    """`_refresh_observed_list` `clear()`s the widget on every scan that changed
    something, and a `QModelIndex` is not a persistent index -- it goes on
    reporting row 1 after the model has emptied. `item(1)` then answers None,
    and the next line reads `.data()` off it.

    The row that matters is not the crash: it is that a click arriving in that
    window must not silently blank the mandate the edge is about to name.
    """
    _shell, page = _watched_page(qtbot, vault)
    page._scan_for_mandates()
    index = page._observed_list.model().index(1, 0)
    page._observed_list.clicked.emit(index)
    assert page._selected_mandate_said == party.m2

    page._observed_list.clear()
    page._on_mandate_clicked(index)        # the slot Qt would call; must not raise

    assert page._selected_mandate_said == party.m2, (
        "a click on a row that no longer exists changed the selection")
    assert party.m2 in page._selected_label.text()


def test_the_list_emptying_under_a_selected_row_does_not_take_the_page_down(
        qtbot, party, vault):
    """`currentItemChanged` is connected for the keyboard, and Qt fires it with
    `current=None` when the widget is cleared -- which is exactly what a scan
    that observed a new mandate does, once a second, under whatever row the
    actuary had arrowed onto.

    So `current is None` is the ordinary case, not a defensive one, and without
    the guard it is `None.data(Qt.UserRole)` inside a timer-driven slot.
    """
    _shell, page = _watched_page(qtbot, vault)
    page._scan_for_mandates()
    page._observed_list.setCurrentRow(1)
    assert page._selected_mandate_said == party.m2

    page._observed_list.clear()
    page._on_mandate_current(None, None)    # the slot Qt would call; must not raise

    assert page._selected_mandate_said == party.m2, (
        "clearing the list forgot which mandate the actuary had chosen")


def test_a_row_that_names_no_mandate_cannot_blank_the_actuarys_choice(
        qtbot, party, vault):
    """Both input paths hand `_select_mandate` whatever `Qt.UserRole` holds, and
    that is `None` for any row `_refresh_observed_list` did not build -- the
    placard rows this list has carried before, and anything a later revision
    adds.

    Blanking the selection there is worse than ignoring it: the row stays
    highlighted, so the page looks like a mandate is chosen while `attest()`
    refuses, and the label reads "Selected: None — / ".
    """
    _shell, page = _watched_page(qtbot, vault)
    page._scan_for_mandates()
    page._observed_list.clicked.emit(page._observed_list.model().index(0, 0))
    assert page._selected_mandate_said == party.m1

    page._observed_list.addItem(QListWidgetItem("a row with no mandate behind it"))
    page._observed_list.clicked.emit(page._observed_list.model().index(2, 0))

    assert page._selected_mandate_said == party.m1, (
        "a row carrying no SAID blanked the mandate the edge names")
    assert "None" not in page._selected_label.text()
    assert party.m1 in page._selected_label.text()


def test_a_seal_the_watcher_has_already_stepped_past_is_still_retried_first(
        qtbot, party, vault):
    """`AnchorWatcher.since()` advances its checkpoint to the highest sn
    EXAMINED, so a seal this page looks at and cannot act on is stepped over
    PERMANENTLY -- and that is the normal case, because the seal is what tells
    you the body exists. Measured: the retrieval worked perfectly, 11 seconds
    late, and the mandate never appeared.

    The watcher below is wound forward past every anchor, so it offers nothing;
    the only route to observing m1 is the pending list. The order is recorded
    through the real `_consider_seal`, because "retried first" is the property
    and nothing in the end state distinguishes it.
    """
    _shell, page = _watched_page(qtbot, vault)
    watcher = page._watcher_for(party.default_hab, party.cuo_pre)
    watcher.since(-1)
    assert watcher.since(watcher.checkpoint) == [], "the watcher is not exhausted"

    page._pending_seals = {party.m1: party.seals[party.m1],
                           party.orphan: party.seals[party.orphan]}
    seen = []
    real = page._consider_seal
    page._consider_seal = lambda v, seal: (seen.append(seal.get("i")),
                                           real(v, seal))[1]

    page._scan_for_mandates()

    assert party.m1 in page._observed, (
        "a seal the watcher had already stepped past was never reconsidered")
    assert party.m1 not in page._pending_seals, "a resolved seal stayed pending"
    assert party.orphan in page._pending_seals, "an unresolved seal was dropped"
    assert seen[:2] == [party.m1, party.orphan], (
        f"pending seals were not considered first: {seen}")
    assert page._observed_list.count() == 1


def test_only_seals_that_could_still_become_a_mandate_are_held_pending(
        qtbot, party, vault):
    """`_pending_seals` is retried on every tick forever, so what goes into it
    matters. A KEL's `a` block carries registry inceptions, other credential
    types, and whatever else a controller anchored; one with no `i` to resolve,
    or one already observed, is not pending on anything and would be re-walked
    once a second for the life of the page."""
    _shell, page = _watched_page(qtbot, vault)

    page._scan_for_mandates()

    assert set(page._observed) == {party.m1, party.m2}
    assert "" not in page._pending_seals and None not in page._pending_seals, (
        "the `a`-block entry with no `i` was held pending on nothing")
    assert _SEAL_WITHOUT_I["d"] not in page._pending_seals
    assert party.m1 not in page._pending_seals
    assert party.m2 not in page._pending_seals
    # ... and the two shapes that genuinely might still resolve are held.
    assert party.orphan in page._pending_seals
    assert _SEAL_UNKNOWN_I["i"] in page._pending_seals


def test_an_unchanged_scan_does_not_rebuild_the_list_under_the_actuary(
        qtbot, party, vault):
    """`_refresh_observed_list` clears the QListWidget and rebuilds it, which
    drops the current row. At a 1s poll, rebuilding on every tick would take the
    actuary's selection away roughly as fast as she could make one -- and
    selecting a mandate is step one of the only irreversible action on this page.
    """
    _shell, page = _watched_page(qtbot, vault)
    page._scan_for_mandates()
    assert page._observed_list.count() == 2

    page._observed_list.setCurrentRow(1)
    chosen = page._selected_mandate_said
    assert chosen

    page._scan_for_mandates()          # nothing new: same KEL, same reger

    assert page._observed_list.currentRow() == 1, (
        "the list was rebuilt for a scan that changed nothing")
    assert page._selected_mandate_said == chosen


def test_a_page_opened_over_a_real_vault_observes_before_the_first_tock(
        qtbot, party, vault):
    """End to end, through the constructor: brand -> schema pin -> peer scan ->
    seal -> TEL -> chain -> EGF verdict -> a rendered row.

    A freshly-revealed page that waited a full poll interval would open on the
    "no mandates observed yet" placard for a second even when two are already
    declared and anchored, which reads as "nothing here" at exactly the moment
    the actuary is deciding whether the surface works.
    """
    shell = QWidget()
    qtbot.addWidget(shell)
    layout = QVBoxLayout(shell)
    page = ActuaryPage(app=_App(vault), parent=shell)
    page._watch_timer.stop()               # deterministic: no background scans
    layout.addWidget(page)
    shell.show()
    qtbot.waitExposed(shell)

    assert set(page._observed) == {party.m1, party.m2}
    assert page._observed_list.count() == 2
    assert page._empty_state.isVisible() is False
    assert page._watch_error == ""
    rows = [page._observed_list.item(i).text()
            for i in range(page._observed_list.count())]
    assert any(party.m1 in row for row in rows), (
        f"the mandate SAID is not in the row it identifies: {rows}")
    assert all("auto / US-UT" in row for row in rows)
    shell.hide()
