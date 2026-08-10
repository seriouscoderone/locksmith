# -*- encoding: utf-8 -*-
"""The irreversible act: what `attest()` actually commits, and how it lets go.

Everything here is about a credential that is PERMANENT and PUBLIC once minted.
Three families of defect are pinned:

*What gets signed.* The attribute block, the NI2I edge, the untargeted
recipient and the registry name are all wire content of a claim the actuary can
never edit. The read-back on screen is only worth having if it cannot drift from
the payload handed to the mint, so the strongest test here reads the drawer's
own labels and compares them to what the doer was constructed with.

*When the button latches.* `_attesting` is armed AFTER every refusal path on
purpose (page.py:1124). Latching earlier turns a typo'd parse path into a
permanently dead Attest button, with no way back except restarting the app.

*How the listener lets go.* The doer class is `ServiceaidIssueDoer` but it EMITS
the legacy source name `"IssueCredentialDoer"` (serviceaid_bridge.py:245-250), so
a test that emits the class name asserts nothing at all -- it passes against an
implementation that never releases anything. Every emission below uses the name
that actually travels.

The vault is a double, but everything the assertions touch is real: a real
`Habery` and `Regery` (temp dirs, never `~/.keri`), a real `Signal(str, str,
dict)` because connect/disconnect semantics are the thing under test, the real
drawer with its real labels, and the real bundled schema read off disk to say
what the edge and the attribute block are allowed to contain.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from PySide6.QtCore import (
    QCoreApplication, QEvent, QObject, Qt, SIGNAL, Signal,
)
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from keri.app import habbing
from keri.vdr import credentialing

from locksmith.core.branding import egf_local_dir
from locksmith.plugins.actuary import page as page_module
from locksmith.plugins.actuary.page import (
    PRODUCT_MANDATE_SCHEMA_SAID, RATE_PROGRAM_ATTESTATION_SCHEMA_SAID,
    ActuaryPage,
)

#: The name the bridge doer EMITS, which is NOT its class name. See the module
#: docstring -- getting this wrong makes every listener test vacuous.
EMITTED_DOER_NAME = "IssueCredentialDoer"

_MANDATE_SAID = "EGoGTCEKbaG42R_igvrt2O2YCtZOX8FT6pJTvGO5mr4X"
_ISSUER = "EKTRx0wK8UL-hQ2vJmDpLnYcRtWqZbXsAeFgHiJkLmNo"
_MANIFEST = "EMf3fJk9LmQ2xR7vB4nT8cY1pZaWeRtYuIoPaSdFgHjK"
_DIGEST = "EWb9kLmQ2xR7vB4nT8cY1pZaWeRtYuIoPaSdFgHjKlZx"
_CRED_SAID = "EDwFbT9pQnKhVxCr2mLsY8jXuZ4aWeRtYuIoPaSdFgHj"
_MANDATE = {
    "line_of_business": "auto", "jurisdiction": "US-UT",
    "coverages": ["BI", "PD"], "window_opens": "2027-01-01",
    "window_closes": "2027-12-31", "thesis": "Grow teen-driver share in Utah.",
    "issuer": _ISSUER,
}

_DOER_EVENT = SIGNAL("doer_event(QString,QString,QVariantMap)")


# --- harness ---------------------------------------------------------------------


class _Signals(QObject):
    """A REAL Qt signal, not a callable double.

    `attest()` connects a closure and `_retire_listener` disconnects it; a
    double that merely records callbacks cannot show a listener surviving its
    own issuance, which is the failure this file exists to catch.
    """

    doer_event = Signal(str, str, dict)


class _Vault:
    def __init__(self, hby, rgy):
        self.hby = hby
        self.rgy = rgy
        self.signals = _Signals()
        self.extended = []

    def extend(self, doers):
        self.extended.extend(doers)


def _listener_count(vault) -> int:
    """How many slots are connected to `doer_event` right now."""
    return vault.signals.receivers(_DOER_EVENT)


@pytest.fixture
def vault():
    """A real Habery + Regery in temp dirs (never `~/.keri`), behind a fake vault.

    Real because `_actuary_hab` walks `hby.habs` and `rgy.reger.subjs`, and
    because `_ensure_schema_pinned` writes into `hby.db.schema` -- a pin this
    file asserts on as an artefact rather than as a call.
    """
    with habbing.openHby(name="actuary-attest", temp=True) as hby:
        # The brand's `default_aid_alias`, which is `_actuary_hab`'s fallback.
        hby.makeHab(name="default", transferable=True)
        rgy = credentialing.Regery(hby=hby, name="actuary-attest", temp=True)
        yield _Vault(hby, rgy)


@pytest.fixture
def mint(monkeypatch):
    """Intercept the two boundaries that would really issue.

    A real `ServiceaidIssueDoer` mints an ACDC and a real `ensure_registry`
    incepts a TEL; both are recorded here instead, so the arguments -- which ARE
    the wire content of a permanent public claim -- can be read back.
    """
    doers = []
    registries = []

    class _RecordingIssueDoer:
        def __init__(self, app, **kwargs):
            self.app = app
            self.kwargs = kwargs
            doers.append(self)

    monkeypatch.setattr(page_module, "ServiceaidIssueDoer", _RecordingIssueDoer)

    import keri_serviceaid.providers.issue as issue_module

    def _ensure_registry(hby, hab, rgy, *, name):
        registries.append(SimpleNamespace(hby=hby, hab=hab, rgy=rgy, name=name))

    monkeypatch.setattr(issue_module, "ensure_registry", _ensure_registry)
    return SimpleNamespace(doers=doers, registries=registries)


def _page(qtbot, app=None):
    shell = QWidget()
    qtbot.addWidget(shell)
    shell.resize(1180, 940)
    layout = QVBoxLayout(shell)
    layout.setContentsMargins(0, 0, 0, 0)
    page = ActuaryPage(app=app, parent=shell)
    layout.addWidget(page)
    shell.show()
    qtbot.waitExposed(shell)
    # Nothing in this file tests the poll, and leaving it running is a trap for
    # whoever mutates this file next: the `vault` fixture closes its Habery at
    # teardown, so a surviving page ticks `_scan_for_mandates` over a closed
    # LMDB and pytest-qt bills the resulting `AttributeError: 'NoneType' object
    # has no attribute 'begin'` to whichever test is at SETUP next. Measured:
    # 14-17 spurious ERRORs per run, attributed to innocent tests. Production is
    # safe -- `apping.py` sets `vault = None` on close and `_scan_for_mandates`
    # guards on that -- so this is a harness leak, not a shipped defect.
    page._watch_timer.stop()
    return shell, page


def _loaded(page):
    """The state after a successful Load Parse, without needing a real parse dir."""
    page._observed = {_MANDATE_SAID: dict(_MANDATE)}
    page._refresh_observed_list()
    page._parse_manifest = {"workbook_digest": _DIGEST}
    page._parse_manifest_said = _MANIFEST
    page._manifest_said_label.setText(_MANIFEST)
    page._workbook_digest_label.setText(_DIGEST)
    page._selected_mandate_said = _MANDATE_SAID
    page._version.setText("2027.1")
    page._update_attest_enabled()


def _armed(qtbot, vault):
    """A page over a real-ish vault, loaded and one click from minting."""
    shell, page = _page(qtbot, app=SimpleNamespace(vault=vault))
    _loaded(page)
    return shell, page


def _confirm_through_the_drawer(qtbot, page):
    """The actuary's real route to `attest()`: review, acknowledge, confirm."""
    page.review_attestation()
    drawer = page.attest_drawer
    qtbot.keyClick(drawer._ack, Qt.Key.Key_Space)
    confirm = drawer.findChild(QPushButton, "attestDrawer.confirm")
    assert confirm.isEnabled() is True
    confirm.click()
    return drawer


def _rows(drawer) -> dict[str, str]:
    """What the read-back is DISPLAYING, keyed by its own data labels.

    `attest_drawer._row` builds a two-QLabel widget per value; this reads the
    rendered text back out of the widget tree rather than re-deriving it, so a
    drawer that shows something other than what it was handed is visible here.
    """
    shown = {}
    for widget in drawer.findChildren(QWidget):
        layout = widget.layout()
        if layout is None or layout.count() != 2:
            continue
        labels = widget.findChildren(QLabel)
        if len(labels) == 2:
            shown[labels[0].text()] = labels[1].text()
    return shown


def _bundled_attestation_schema() -> dict:
    """The schema the mint must satisfy, read off disk -- not restated here."""
    egf_dir = egf_local_dir()
    assert egf_dir is not None, "the usurance brand is not active"
    path = egf_dir / f"{RATE_PROGRAM_ATTESTATION_SCHEMA_SAID}.json"
    return json.loads(path.read_text())


#: A parse directory the way `ipd/pipeline.py` writes one: `index.json`, shards
#: at the top level and under the three table directories, one legitimately
#: EMPTY shard, and a non-ASCII table name. Not decoration -- a flat ASCII
#: stand-in cannot tell a correct manifest from one built with `ensure_ascii=True`
#: or a top-level-only walk, which is precisely what the end-to-end test below
#: has to be able to see.
_REAL_SHARDS: tuple[tuple[str, bytes], ...] = (
    ("index.json", b'{"product":{"lineOfBusiness":"auto"},"files":[]}'),
    ("coverages.jsonl", b'{"record":"coverage","coverage":"BI"}\n'),
    ("parse-report.jsonl", b""),
    ("mappings/Terr_Map.jsonl", b'{"record":"mapping","name":"Terr_Map"}\n'),
    ("risk-value-tables/Prämie_Zöne.jsonl",
     b'{"record":"risk_value_table","name":"Pr\\u00e4mie_Z\\u00f6ne"}\n'),
)


def _write_workbook(path, marker: bytes = b"rev-a"):
    """A real zip, because a .xlsm is one."""
    import zipfile

    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
        zf.writestr("docProps/custom.xml", marker.decode())
    return path


def _real_parse_fixture(tmp_path):
    """A parse directory, its source workbook, and the sidecar that ties them."""
    parse_dir = tmp_path / "parse"
    for rel, body in _REAL_SHARDS:
        target = parse_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
    workbook = _write_workbook(tmp_path / "ut-auto.xlsm")
    (parse_dir / page_module._WORKBOOK_SIDECAR_NAME).write_text(
        json.dumps({"workbook_path": str(workbook)}))
    return parse_dir, workbook


def _emit(vault, event_type, data, doer_name=EMITTED_DOER_NAME):
    vault.signals.doer_event.emit(doer_name, event_type, data)


def _issued(said=_CRED_SAID):
    return {"schema_said": RATE_PROGRAM_ATTESTATION_SCHEMA_SAID, "said": said}


# --- what gets signed --------------------------------------------------------------


def test_the_edge_operator_is_the_wire_value_the_bundled_schema_demands(
        qtbot, vault, mint):
    """`NI2I`, and by a spec MUST rather than a preference: the mandate is an
    UNTARGETED ACDC, and an edge to a far node with no Issuee cannot be I2I or
    DI2I. The bundled schema pins `o` to `"const": "NI2I"`, so a friendlier
    word here -- `"references"` is the micro-app template's own authoring
    vocabulary for the same operator -- fails validation at issuance, after the
    actuary has already acknowledged the read-back.

    Asserted against the schema file itself, not a literal: a literal would go
    on agreeing with a re-SAIDed schema that had changed underneath it.
    """
    shell, page = _armed(qtbot, vault)
    page.attest()

    edge = mint.doers[0].kwargs["edges"]["mandate"]
    schema_edge = _bundled_attestation_schema()[
        "properties"]["e"]["oneOf"][1]["properties"]["mandate"]["properties"]
    assert schema_edge["o"]["const"] == "NI2I", "the schema moved; this test is stale"
    assert edge["operator"] == schema_edge["o"]["const"]
    shell.hide()


def test_the_edge_names_the_mandate_the_actuary_selected(qtbot, vault, mint):
    """The edge is the whole point of the attestation: it says WHICH mandate
    this rate program answers, permanently. An edge to the wrong mandate is not
    a display bug -- it is a public statement about a CUO's programme that
    cannot be withdrawn, only superseded.

    `schema_said` is likewise pinned by the bundled schema (`"const"` on the
    edge's `s`), because a verifier resolving an edge holds SAIDs and nothing else.
    """
    shell, page = _armed(qtbot, vault)
    other = "EOtherMandate" + "B" * 31
    page._observed[other] = dict(_MANDATE)
    page._refresh_observed_list()
    page._selected_mandate_said = _MANDATE_SAID

    page.attest()

    edge = mint.doers[0].kwargs["edges"]["mandate"]
    assert edge["cred_said"] == _MANDATE_SAID
    assert edge["cred_said"] != other
    schema_edge = _bundled_attestation_schema()[
        "properties"]["e"]["oneOf"][1]["properties"]["mandate"]["properties"]
    assert edge["schema_said"] == schema_edge["s"]["const"]
    assert edge["schema_said"] == PRODUCT_MANDATE_SCHEMA_SAID
    shell.hide()


def test_the_attribute_block_is_exactly_the_schemas_and_nothing_helpful_extra(
        qtbot, vault, mint):
    """`additionalProperties: false`, so a helpfully-added attribute is not
    merely redundant -- it makes the credential unissuable. `mandate_said` is
    the one that looks most like it belongs, and page.py:1098 records that the
    schema rejected it here, measured: it names the edge's far node, not an
    attribute. `carried_coverages` is the same shape of not-an-attribute -- the
    micro-app template says it is INPUT to a consistency check, and the
    `manifest_said` this ACDC does carry is what a consumer re-derives to learn
    the real coverage set.

    Compared against the schema's own `required` list minus the two fields the
    ACDC envelope supplies (`d`, `dt`), so adding a property to the schema
    without minting it -- or minting one the schema never declared -- both fail
    here rather than at the actuary's irreversible click.
    """
    shell, page = _armed(qtbot, vault)
    page.attest()

    payload = mint.doers[0].kwargs["attributes"]
    attributes = _bundled_attestation_schema()["properties"]["a"]["oneOf"][1]
    assert attributes["additionalProperties"] is False, (
        "the schema stopped rejecting extras; this test's premise is gone")

    envelope_supplied = {"d", "dt"}
    assert set(payload) == set(attributes["required"]) - envelope_supplied
    assert "mandate_said" not in payload
    assert "carried_coverages" not in payload
    assert payload == page._attestation_attributes(), (
        "the mint built its own block, so the read-back can now drift from it")
    shell.hide()


def test_the_attestation_is_untargeted(qtbot, vault, mint):
    """`recipient=None` is a protocol claim, not a default. The schema's own
    attribute block has no `i`, and its description says the ACDC asserts
    authorship rather than conferring anything -- the designer READS it. A
    recipient would make it targeted, which changes what an edge to it is
    allowed to be and what a verifier may infer from holding it.
    """
    shell, page = _armed(qtbot, vault)
    page.attest()

    assert mint.doers[0].kwargs["recipient"] is None
    attributes = _bundled_attestation_schema()["properties"]["a"]["oneOf"][1]
    assert "i" not in attributes["properties"], (
        "the schema grew an issuee; untargeted is no longer the contract")
    shell.hide()


def test_the_registry_is_named_after_the_schema_and_the_schema_is_really_pinned(
        qtbot, vault, mint):
    """Two things the mint cannot do without.

    `registry_name == schema_said` is the shipped convention (Amendment C
    §14.1): one management TEL per credential type, keyed by schema SAID. The
    doer resolves its issuing hab BY that name (serviceaid_bridge.py:230), so a
    wrong name is not a naming quibble -- it resolves no registry, hands
    `hab=None` to `issue_credential`, and the attestation never mints.

    And the schema must be pinned into `hby.db.schema` before `Credentialer
    .create` can validate what it is about to sign. Asserted as a database
    artefact, not as a call: the pin either landed or it did not.
    """
    shell, page = _armed(qtbot, vault)
    assert vault.hby.db.schema.get(
        keys=(RATE_PROGRAM_ATTESTATION_SCHEMA_SAID,)) is None, (
        "already pinned before attest() ran; the assertion below proves nothing")

    page.attest()

    kwargs = mint.doers[0].kwargs
    assert kwargs["schema_said"] == RATE_PROGRAM_ATTESTATION_SCHEMA_SAID
    assert kwargs["registry_name"] == kwargs["schema_said"]
    assert mint.registries[0].name == RATE_PROGRAM_ATTESTATION_SCHEMA_SAID
    assert mint.registries[0].hab is vault.hby.habByName("default")

    schemer = vault.hby.db.schema.get(
        keys=(RATE_PROGRAM_ATTESTATION_SCHEMA_SAID,))
    assert schemer is not None, "nothing pinned the attestation schema"
    assert schemer.said == RATE_PROGRAM_ATTESTATION_SCHEMA_SAID
    shell.hide()


def test_the_doer_is_actually_scheduled_on_the_vault(qtbot, vault, mint):
    """Constructing the doer issues nothing; `vault.extend` is what runs it.
    A page that built the doer and never scheduled it would satisfy every
    payload assertion above while minting nothing at all."""
    shell, page = _armed(qtbot, vault)
    page.attest()

    assert len(vault.extended) == 1
    assert vault.extended[0] is mint.doers[0]
    assert vault.extended[0].app is page._app
    shell.hide()


def test_the_read_back_shows_the_values_that_are_actually_minted(
        qtbot, vault, mint):
    """THE test this file exists for. A read-back is only worth the ceremony if
    what it displays is what gets signed; one that shows something else is worse
    than none, because it manufactures consent for values nobody saw.

    Both sides come from `_attestation_attributes()` today. This reads the
    drawer's RENDERED labels -- not the dict it was constructed from -- then
    lets the actuary confirm for real (space on the acknowledgement, click on
    the confirm button) and compares against the payload the doer was actually
    handed. Any future refactor that gives the mint its own copy of the block
    breaks here.
    """
    shell, page = _armed(qtbot, vault)
    page._version.setText("2027.2")

    page.review_attestation()
    drawer = page.attest_drawer
    shown = _rows(drawer)
    qtbot.keyClick(drawer._ack, Qt.Key.Key_Space)
    drawer.findChild(QPushButton, "attestDrawer.confirm").click()

    kwargs = mint.doers[0].kwargs
    payload = kwargs["attributes"]
    assert shown["Manifest SAID"] == payload["manifest_said"] == _MANIFEST
    assert shown["Version"] == payload["version"] == "2027.2"
    assert shown["Filing date"] == payload["filing_date"]
    assert shown["Action"] == payload["action"]
    assert shown["Mandate"] == kwargs["edges"]["mandate"]["cred_said"]
    assert shown["Workbook digest"] == _DIGEST
    # ...and nothing committed is invisible: every value in the block is on
    # screen somewhere, whatever row it was given.
    assert set(payload.values()) <= set(shown.values())
    shell.hide()


def test_the_minted_manifest_said_is_derived_from_the_bytes_on_disk(
        qtbot, vault, mint, tmp_path):
    """The one join nothing else in this package makes.

    `test_manifest.py` proves the SAID is computed correctly over a real parse
    directory. This file proves the payload carries `_parse_manifest_said`. But
    every `_loaded()` in here installs a HAND-TYPED 44-character string, so the
    `manifest_said` in a minted payload had never once come from actual bytes --
    and it is the only substantive attribute the credential has. A consumer
    re-derives that one string from the parse they were given; nothing else in
    the ACDC describes the rate program at all.

    So this runs the whole route on real artefacts: a real parse directory laid
    out the way `ipd/pipeline.py` lays one out (subdirectories, an empty shard,
    a non-ASCII table name), a real .xlsm (a zip, because that is what one is),
    the sidecar naming it, `load_parse()`, then `attest()`. The minted value is
    then checked twice: re-derived from the same bytes, and verified through
    `keri.core.sealing.verifySealedBody` -- the CONSUMER's own verifier, which
    re-serializes independently of this page's `_manifest_said`.
    """
    from keri.core.sealing import verifySealedBody

    parse_dir, workbook = _real_parse_fixture(tmp_path)
    shell, page = _page(qtbot, app=SimpleNamespace(vault=vault))
    page._observed = {_MANDATE_SAID: dict(_MANDATE)}
    page._refresh_observed_list()
    page._selected_mandate_said = _MANDATE_SAID
    page._version.setText("2027.1")
    page._parse_dir.setText(str(parse_dir))

    page.load_parse()

    assert page._error_banner.isVisible() is False, page._error_banner.text()
    computed = page._parse_manifest_said
    assert computed and computed != _MANIFEST, (
        "the page is still holding the hand-typed stand-in, not a derived SAID")

    page.attest()

    minted = mint.doers[0].kwargs["attributes"]["manifest_said"]
    assert minted == computed
    assert minted == page_module._manifest_said(
        page_module._build_manifest(parse_dir, workbook)), (
            "the minted SAID does not re-derive from the directory it was "
            "loaded from")
    assert verifySealedBody({"d": minted}, page._parse_manifest) is True, (
        "the consumer's own verifier refuses the manifest this credential "
        "commits to")

    # ... and it is genuinely about THESE bytes: one changed byte in the
    # workbook is a different rate program, and the seal must stop verifying.
    moved = _write_workbook(tmp_path / "moved.xlsm", marker=b"rev-b")
    other = page_module._build_manifest(parse_dir, moved)
    assert page_module._manifest_said(other) != minted
    assert verifySealedBody({"d": minted}, other) is False
    shell.hide()


# --- the guard: armed only after every refusal ------------------------------------


def test_a_re_entered_attest_schedules_no_second_doer(qtbot, vault, mint):
    """The observable half of this guard is already pinned; the artefact half is
    here. A double-click that gets past the button mints a SECOND permanent
    public credential for one rate program, and the second listener replaces the
    first, so one banner covers both and the actuary never learns there are two.
    """
    shell, page = _armed(qtbot, vault)
    page._attesting = True

    page.attest()

    assert mint.doers == [], "a re-entered attest built a second issue doer"
    assert vault.extended == [], "a re-entered attest scheduled a second issuance"
    assert _listener_count(vault) == 0
    shell.hide()


def test_no_vault_refuses_and_leaves_the_button_usable(qtbot, mint):
    """Refusals must not latch the guard. `_attesting` is armed at page.py:1127,
    after every return above it, because a guard set at the top of the method
    would disable Attest permanently the first time the vault was not open --
    with no path back short of restarting the app."""
    for app in (None, SimpleNamespace(vault=None)):
        shell, page = _page(qtbot, app=app)
        _loaded(page)
        assert page._attest.isEnabled() is True

        page.attest()

        assert "No open vault" in page._error_banner.text()
        assert page._error_banner.isVisible() is True
        assert page._attesting is False, "a refusal latched the guard"
        assert page._attest.isEnabled() is True, "the actuary cannot try again"
        assert mint.doers == []
        shell.hide()


def test_nothing_selected_refuses_and_leaves_the_button_usable(qtbot, vault, mint):
    """Same latch, reached the way it actually happens: the parse path was
    edited (which forgets the parse) or the mandate list was rebuilt under the
    selection."""
    shell, page = _armed(qtbot, vault)
    page._selected_mandate_said = None
    page._update_attest_enabled()

    page.attest()

    assert "Select an observed mandate" in page._error_banner.text()
    assert page._attesting is False, "a refusal latched the guard"
    assert mint.doers == []
    assert _listener_count(vault) == 0

    # ...and the recovery really works: re-select, and the button comes back.
    page._selected_mandate_said = _MANDATE_SAID
    page._update_attest_enabled()
    assert page._attest.isEnabled() is True
    shell.hide()


def test_no_identifier_refuses_and_leaves_the_button_usable(qtbot, vault, mint):
    """A vault with no `actuary_role` holder and no default alias has nobody to
    attest AS. That is a recoverable state -- the credential can be granted
    while the app is running -- so it must not kill the button."""
    shell, page = _armed(qtbot, vault)
    page._actuary_hab = lambda _vault: None

    page.attest()

    assert "No identifier available" in page._error_banner.text()
    assert page._attesting is False, "a refusal latched the guard"
    assert mint.doers == []
    assert _listener_count(vault) == 0

    page._update_attest_enabled()
    assert page._attest.isEnabled() is True
    shell.hide()


def test_a_failed_preparation_says_so_and_leaves_the_button_usable(
        qtbot, vault, mint, monkeypatch):
    """Registry seeding and schema pinning happen BEFORE anything is signed, and
    both can fail on a vault that is otherwise fine. The actuary needs the
    reason on screen -- the log is not where they are looking -- and the button
    back, because the fix (seed the registry, re-import the EGF) happens while
    the app is running."""
    import keri_serviceaid.providers.issue as issue_module

    def _boom(hby, hab, rgy, *, name):
        raise RuntimeError("registry vcp was never anchored")

    monkeypatch.setattr(issue_module, "ensure_registry", _boom)
    shell, page = _armed(qtbot, vault)

    page.attest()

    assert page._error_banner.isVisible() is True
    assert page._error_banner.text() == (
        "Could not prepare to attest: registry vcp was never anchored")
    assert page._attesting is False, "a failed preparation latched the guard"
    assert page._attest.isEnabled() is True
    assert mint.doers == [], "an unprepared registry still scheduled an issuance"
    assert _listener_count(vault) == 0, "a listener outlived a failed preparation"
    shell.hide()


def test_a_successful_attest_arms_the_guard_and_says_it_is_working(
        qtbot, vault, mint):
    """The other half of the same decision: once the mint IS scheduled, the
    guard must latch, or a second click schedules a second irreversible
    issuance."""
    shell, page = _armed(qtbot, vault)

    page.attest()

    assert page._attesting is True
    assert page._attest.isEnabled() is False
    assert page._attest_blocker.text() == "Attesting…"
    assert _listener_count(vault) == 1
    shell.hide()


# --- the listener: what it answers to, and what it must ignore --------------------


def test_another_doers_issuance_does_not_end_this_attestation(qtbot, vault, mint):
    """The bridge emits a SOURCE name, and every issuance in the app emits the
    same one, so the schema is what distinguishes them -- but the doer name is
    the first filter and it has to hold on its own.

    Note the skew this test is built around: the class is `ServiceaidIssueDoer`
    and it emits `"IssueCredentialDoer"` (the legacy name, deliberately reused
    so existing UI handlers keep working). Emitting the CLASS name is the
    natural mistake, and a listener test written that way passes against an
    implementation that never releases anything at all -- so the class name is
    used here as a foreign name, which is exactly what it is on the wire.
    """
    shell, page = _armed(qtbot, vault)
    drawer = _confirm_through_the_drawer(qtbot, page)

    for foreign in ("SendGrantDoer", "AdmitDoer", "ServiceaidIssueDoer"):
        _emit(vault, "credential_issued", _issued(), doer_name=foreign)

    assert page._attesting is True, "another doer's issuance released the guard"
    assert page.attest_drawer is drawer
    assert drawer.isVisible() is True, "another doer's issuance closed the read-back"
    assert page._attested_banner.isVisible() is False
    assert page._error_banner.isVisible() is False
    assert _listener_count(vault) == 1, "the listener retired on a foreign event"
    shell.hide()


def test_another_schemas_issuance_does_not_end_this_attestation(qtbot, vault, mint):
    """One vault issues several credential types through the same bridge and the
    same signal. A role credential landing while an attestation is in flight
    would otherwise close the read-back and print "Rate program attested" over
    somebody else's SAID."""
    shell, page = _armed(qtbot, vault)
    drawer = _confirm_through_the_drawer(qtbot, page)

    _emit(vault, "credential_issued",
          {"schema_said": PRODUCT_MANDATE_SCHEMA_SAID, "said": _CRED_SAID})
    _emit(vault, "credential_issuance_failed",
          {"schema_said": PRODUCT_MANDATE_SCHEMA_SAID, "error": "not ours"})

    assert page._attesting is True, "another schema's event released the guard"
    assert page.attest_drawer is drawer
    assert page._attested_banner.isVisible() is False
    assert page._error_banner.isVisible() is False
    assert _listener_count(vault) == 1
    shell.hide()


def test_an_event_type_this_listener_does_not_answer_to_is_stepped_over(
        qtbot, vault, mint):
    """The third filter, after the doer name and the schema: `credential_issued`
    or nothing.

    `doer_event` is an application-wide bus -- twenty-odd doers emit on it and
    the page's closure is called for every one of them while an attestation is
    in flight. The name and the schema narrow that to this doer's own
    vocabulary; the event type is what keeps a NON-terminal member of that
    vocabulary from being read as "done". Without it, one such event retires the
    listener, releases the guard, closes the read-back mid-flight and prints
    "Rate program attested." with no SAID after it -- and the real issuance,
    when it lands, is heard by nobody.

    Measured: mutating this guard to a sentinel left the package at 114 passed.
    Note plainly what the corpus does and does not have -- TODAY the two
    emitters under this name (credentialing.py:485/505 and serviceaid's
    providers/issue.py:151 + serviceaid_bridge.py:251) emit exactly the two
    types this listener handles, so no third type is reachable in the shipped
    app. This pins the contract for the next one, which is the whole reason a
    guard is written before it is needed.
    """
    shell, page = _armed(qtbot, vault)
    drawer = _confirm_through_the_drawer(qtbot, page)

    for stray in ("credential_issuance_started", "credential_registered",
                  "progress"):
        _emit(vault, stray, _issued())

    assert page._attesting is True, "a non-terminal event released the guard"
    assert page.attest_drawer is drawer
    assert drawer.isVisible() is True, "the read-back was closed mid-flight"
    assert page._attested_banner.isVisible() is False, (
        "the page announced an attestation that had not happened")
    assert page._error_banner.isVisible() is False
    assert _listener_count(vault) == 1, "the listener retired before its own event"

    # ... and the real one still lands, which is what the retirement would have
    # cost: the credential mints either way, the actuary just never hears of it.
    _emit(vault, "credential_issued", _issued())
    assert page._attesting is False
    assert page._attested_banner.text() == f"Rate program attested. {_CRED_SAID}"
    shell.hide()


def test_a_failed_issuance_retires_its_listener_and_frees_the_button(
        qtbot, vault, mint):
    """A guard that only lifts on success turns one failed attestation into a
    permanently dead button, and a listener that outlives its own issuance
    reports the NEXT one as this one. The banner carries the event's own error,
    because "Attestation failed." alone leaves nothing to act on."""
    shell, page = _armed(qtbot, vault)
    drawer = _confirm_through_the_drawer(qtbot, page)

    _emit(vault, "credential_issuance_failed",
          {"schema_said": RATE_PROGRAM_ATTESTATION_SCHEMA_SAID,
           "error": "registry EJmN… is not seeded"})

    assert page._attesting is False
    assert page._attest.isEnabled() is True, "the actuary cannot retry"
    assert page._error_banner.text() == "registry EJmN… is not seeded"
    assert page._error_banner.isVisible() is True
    assert page._attested_banner.isVisible() is False
    assert page._pending_listener is None
    assert _listener_count(vault) == 0, "the listener survived its own failure"
    assert page.attest_drawer is None
    qtbot.waitUntil(lambda: not drawer.isVisible(), timeout=2000)

    # And it is really gone from the signal, not merely forgotten by the page.
    page._error_banner.setVisible(False)
    _emit(vault, "credential_issuance_failed",
          {"schema_said": RATE_PROGRAM_ATTESTATION_SCHEMA_SAID,
           "error": "a later, unrelated failure"})
    assert page._error_banner.isVisible() is False, (
        "a retired listener still answered the signal")
    shell.hide()


def test_a_successful_issuance_closes_the_read_back_and_names_the_credential_in_full(
        qtbot, vault, mint):
    """Three things at once, because they are one moment for the actuary.

    The read-back must CLOSE -- `close_drawer` refuses while an attestation is
    in flight, so the page has to call `finish()`; the sibling dialog shipped
    the plain-close version for a commit and its modal survived its own success.

    The SAID must be printed IN FULL. `said[:12]…` is not a handle: this
    credential is the artefact the whole page exists to produce, and an actuary
    cannot go and find what they published from a twelfth of its identifier.

    And the listener must retire, or the next issuance of any kind re-announces
    this one.
    """
    shell, page = _armed(qtbot, vault)
    drawer = _confirm_through_the_drawer(qtbot, page)

    _emit(vault, "credential_issued", _issued())

    assert page._attesting is False
    assert page._attest.isEnabled() is True
    assert page._pending_listener is None
    assert _listener_count(vault) == 0, "the listener survived its own success"

    assert page.attest_drawer is None
    qtbot.waitUntil(lambda: not drawer.isVisible(), timeout=2000)

    banner = page._attested_banner
    assert banner.isVisible() is True
    assert _CRED_SAID in banner.text(), (
        f"the SAID is truncated or missing: {banner.text()!r}")
    assert banner.text() == f"Rate program attested. {_CRED_SAID}"
    assert page._error_banner.isVisible() is False
    shell.hide()


def test_an_issuance_that_reports_no_said_still_says_it_happened(qtbot, vault, mint):
    """`data["said"]` is not guaranteed -- the bridge's failure path emits a
    payload without it, and a future emission could too. The banner must not
    read "Rate program attested. " with an empty space where the credential's
    identity should be: that looks like a truncation bug at exactly the moment
    the actuary is trying to verify what they published."""
    shell, page = _armed(qtbot, vault)

    page._show_attested("")

    assert page._attested_banner.text() == "Rate program attested."
    assert page._attested_banner.isVisible() is True
    shell.hide()


def test_two_attests_leave_exactly_one_listener(qtbot, vault, mint):
    """A stale listener is disconnected before a new one is connected
    (page.py:1133). Without that, one issuance triggers two banners for one
    credential -- and the actuary reading two success lines has no way to tell
    whether two credentials were minted.

    The stale state is reached through real page code: `_release_attest()` drops
    the guard and deliberately does NOT retire the listener (retiring is the
    listener's own job), which is exactly the arrangement the defensive
    disconnect exists for.
    """
    shell, page = _armed(qtbot, vault)
    page.attest()
    first = page._pending_listener
    assert first is not None
    assert _listener_count(vault) == 1

    page._release_attest()
    page.attest()

    assert page._pending_listener is not first, "the second attest reused the closure"
    assert _listener_count(vault) == 1, (
        "two listeners are connected; one issuance will announce itself twice")

    # The harm, measured: one issuance, one banner.
    announced = []
    real_show = page._show_attested
    page._show_attested = lambda said: (announced.append(said), real_show(said))[1]
    _emit(vault, "credential_issued", _issued())
    assert announced == [_CRED_SAID]
    assert len(mint.doers) == 2, "both attests really scheduled an issuance"
    shell.hide()


# --- the read-back's own guards ---------------------------------------------------


def test_a_second_review_does_not_stack_a_read_back_over_the_first(
        qtbot, vault, mint):
    """`review_attestation` is reachable from the button, from Enter, and from
    devctl. A second drawer would take the page's handle, leaving the first
    orphaned on screen with its own backdrop -- and the page would then `finish()`
    the wrong one when the issuance resolved, so the visible read-back would
    survive its own success."""
    shell, page = _armed(qtbot, vault)
    page.review_attestation()
    drawer = page.attest_drawer
    assert drawer is not None

    page.review_attestation()

    assert page.attest_drawer is drawer, "a second read-back replaced the first"

    # ...and once the mint is in flight, no new read-back opens at all.
    page._close_drawer()
    page._attesting = True
    page.review_attestation()
    assert page.attest_drawer is None, "a read-back opened over an in-flight mint"
    shell.hide()


def test_reviewing_without_a_mandate_or_a_parse_says_so_and_opens_nothing(
        qtbot, vault, mint):
    """The drawer's whole content is the mandate and the manifest. Opening it
    with either missing renders a page of em dashes and an armed confirm button
    that would then be refused by `attest()` -- a ceremony around nothing."""
    shell, page = _armed(qtbot, vault)
    page._selected_mandate_said = None

    page.review_attestation()

    assert page.attest_drawer is None
    assert page._error_banner.isVisible() is True
    assert "Select an observed mandate" in page._error_banner.text()

    page._selected_mandate_said = _MANDATE_SAID
    page._parse_manifest_said = None
    page._error_banner.setVisible(False)
    page.review_attestation()
    assert page.attest_drawer is None, "a read-back opened over no parse"
    assert page._error_banner.isVisible() is True
    shell.hide()


def test_closing_a_read_back_qt_already_destroyed_is_not_a_crash(
        qtbot, vault, mint):
    """`_close_drawer` runs from inside a Qt slot, on the outcome of an issuance
    that is still in flight when the surface goes away -- and the surface does go
    away: a revoked role credential destroys this page and its children
    (`unregister_page` -> `setParent(None)` + `deleteLater`) while the doer keeps
    running. An uncaught `RuntimeError: Internal C++ object already deleted`
    there would take out the slot before the guard is released, on the one path
    that has no second chance."""
    shell, page = _armed(qtbot, vault)
    page.review_attestation()
    drawer = page.attest_drawer

    drawer.setParent(None)
    drawer.deleteLater()
    QCoreApplication.sendPostedEvents(drawer, QEvent.Type.DeferredDelete)
    with pytest.raises(RuntimeError):
        drawer.isVisible()          # independent oracle: the C++ side is gone

    page._close_drawer()            # must not raise

    assert page.attest_drawer is None
    shell.hide()


def test_closing_a_read_back_that_was_never_opened_is_not_a_crash(
        qtbot, vault, mint):
    """`attest()` is callable without the drawer (devctl, Enter, a future
    keyboard path), so the failure listener can reach `_close_drawer` with
    nothing to close. This is the ordinary case, not a defensive one."""
    shell, page = _armed(qtbot, vault)
    assert page.attest_drawer is None

    page._close_drawer()

    assert page.attest_drawer is None
    shell.hide()
