# -*- encoding: utf-8 -*-
"""
locksmith.plugins.actuary.page module — the actuary's observe-and-attest surface.

Design §5's two panes over C1's headless library:

**Observed mandates** — populated by WATCHING, never by being handed anything. A
`product_mandate` is untargeted (design's Amendment C §14.6 -- "addressed to nobody
and requesting nothing"), so a reader finds it by watching the declaring identifier's
own KEL for an anchored seal (`keri.app.anchoring.AnchorWatcher`, Plan A), then walking
the seal -> TEL -> credential chain (`keri_serviceaid.providers.sealed_retrieval`,
Plan C1) to prove the body that landed locally really is the one the KEL committed to
-- never trusting a seal's own `i` field on its own. The final verdict (schema
accepted by the ecosystem, TEL state current) is C1's `keri_serviceaid.egf.attestation
.verify_attestation`, the same shared entry point the concierge CLI uses. **The
message is a hint, the log is the authority**: this polls the locally-known KELs on a
timer rather than reacting to any single delivery event, matching the credential-gate
recheck idiom `core/inbound_watch.py::GateRecheckDoer` already uses elsewhere in this
app.

**Attest** — takes a REAL `ipd-parse` output directory (the workbench artifact; see
`insurance-product/parser` in the sibling `ugard` repo), computes the manifest SAID
that commits to the parse shards AND the source workbook's own bytes
(`the_manifest_commits_to_the_workbook_itself` in the corpus's `rules[]`), and issues
`rate_program_attestation` with an NI2I edge to the selected mandate.
The manifest algorithm is REIMPLEMENTED here rather than imported from `ipd.manifest`
across repos: that package is workbench tooling in a sibling repo with its own
dependency surface (`openpyxl`) keripy's venv does not carry, and per CLAUDE.md's
workbench/HOA boundary ("does this need to be provable later, to someone who wasn't
there?") the HOA's runtime must not reach across repos for it. The algorithm below
must stay byte-identical to `ipd.manifest.build_manifest`/`manifest_said` (JSON
canonicalization matching `keri.core.sealing.verifySealedBody`'s opaque-blob path) or
a designer re-deriving with the parser's own tool would get a different answer than
this page computed.

**Render no rate table** — Excel is the rate UI (owner ruling). The manifest SAID and
the workbook digest are shown as EVIDENCE that a specific set of bytes was attested,
never the rates themselves.

Widget idiom modeled on `plugins/cuo/page.py` (form layout, banners, doer_event
subscription) and `ui/vault/peers/list.py` (the plain `QListWidget` idiom).
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import QDate, Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QFormLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QSizePolicy, QVBoxLayout, QWidget,
)

from keri import help
from keri.core.serdering import SerderKERI
from keri.kering import Ilks

from locksmith.core.branding import brand, egf_local_dir
from locksmith.core.serviceaid_bridge import ServiceaidIssueDoer
from locksmith.plugins.actuary.attest_drawer import AttestReviewDrawer
from locksmith.ui import colors
from locksmith.ui.styles import get_monospace_font_family
from locksmith.ui.toolkit.widgets import LocksmithButton
from locksmith.ui.toolkit.widgets.buttons import LocksmithInvertedButton
from locksmith.ui.toolkit.widgets.fields import LocksmithLineEdit

logger = help.ogler.getLogger(__name__)

# Registry-name convention: registry_name == schema_said (Amendment C §14.1),
# mirroring cuo/page.py. Pins verified against the bundled schemas by
# tests/plugins/roles/test_pin_regression.py.
PRODUCT_MANDATE_SCHEMA_SAID = "EFYdgrOvpXpxTkVSVl6dRs1lueELnH9cqxpctqwqpVr5"
RATE_PROGRAM_ATTESTATION_SCHEMA_SAID = "EPaMxGLoFc6u1if3s367j5J547kLXKJbsztT-OE1gcHP"

#: How often the observed-mandates pane re-scans locally-known KELs for new
#: anchors. The message is a hint, the log is the authority -- this is a poll,
#: not a reaction to any single delivery event, matching GateRecheckDoer's idiom
#: (core/inbound_watch.py) elsewhere in this app.
_WATCH_POLL_MS = 1000

#: The sidecar `ipd-parse` itself does not write: no invocation of `ipd-parse`
#: records the source workbook's own location in its output (measured -- no field
#: in index.json names it, no copy of the .xlsm is written), so a caller has
#: always supplied the workbook out-of-band alongside `--out`. Until that lands
#: upstream, this page's convention is a sidecar dropped BESIDE the parse shards
#: by whoever produced them, naming the workbook this manifest must also commit
#: to. Excluded by name from the manifest's own shard walk (below) so it is never
#: mistaken for parser output.
_WORKBOOK_SIDECAR_NAME = ".workbook_source.json"

#: The attestation schema's own enum for `action` -- the IPD retention contract.
#: Read from the schema at load time would be better; pinned here because this
#: page already pins the schema SAID and a drifted enum fails loudly at issuance.
_ACTION_VALUES = ("Publish", "Sandbox")

_TEL_STATE_LABELS = {
    Ilks.iss: "issued", Ilks.bis: "issued",
    Ilks.rev: "revoked", Ilks.brv: "revoked",
}


def _mono_css() -> str:
    """A monospace `font-family` value that survives the font not being loaded.

    QUOTED and with a real fallback, matching `styles.py`'s own global rule. The
    bare form has two silent failure modes: the loaded family is "Source Code
    Pro", whose space breaks an unquoted CSS family name, and the module default
    is the literal string "monospace", which is NOT a registered family on macOS
    -- measured, it resolves to .AppleSystemUIFont with fixedPitch False and `I`
    at 3px against `W` at 12px. Proportional, on the two 44-character digests
    this page exists to make proof-readable.
    """
    return f'"{get_monospace_font_family()}", Menlo, monospace'


def _digest(raw: bytes) -> str:
    """qb64 digest of raw bytes -- byte-identical to `ipd.manifest._digest`
    and to keripy's own `Diger(ser=raw)` default, including on an empty
    `ser` (`Diger.__init__`'s ser-fallback re-raises on falsy `ser`; the real
    parser emits at least one legitimately empty shard, so this must not)."""
    from keri.core.coring import Diger, DigDex
    return Diger(raw=Diger._digest(raw, code=DigDex.Blake3_256), code=DigDex.Blake3_256).qb64


def _build_manifest(parse_dir: Path, workbook: Path) -> dict:
    """Byte-identical to `ipd.manifest.build_manifest` -- see the module
    docstring for why this is reimplemented rather than imported."""
    shards = sorted(
        (
            {"name": p.relative_to(parse_dir).as_posix(), "digest": _digest(p.read_bytes())}
            for p in parse_dir.rglob("*")
            if p.is_file() and p.name != _WORKBOOK_SIDECAR_NAME
        ),
        key=lambda shard: shard["name"],
    )
    return {
        "kind": "rate_program_manifest",
        "workbook_digest": _digest(workbook.read_bytes()),
        "shards": shards,
    }


def _manifest_said(manifest: dict) -> str:
    """Byte-identical to `ipd.manifest.manifest_said` -- see the module docstring."""
    raw = json.dumps(manifest, separators=(",", ":"), ensure_ascii=False).encode()
    return _digest(raw)


class ActuaryPage(QWidget):
    """The actuary's surface: observe a watched mandate, attest a rate program.

    Args:
        app: the `LocksmithApplication` (needed for `app.vault`); `None` is
            accepted so the class stays constructible in isolation, mirroring
            `CuoMandatePage`.
    """

    def __init__(self, app: Any = None, parent=None):
        super().__init__(parent)
        self._app = app
        self._pending_listener = None  # the still-connected _on_issue_event, or None

        # watch state
        self._watchers: dict[str, Any] = {}       # peer AID -> AnchorWatcher
        self._observed: dict[str, dict] = {}       # mandate SAID -> {line_of_business, jurisdiction, coverages}
        # Seals seen but NOT yet resolvable, re-considered on every tick.
        #
        # `AnchorWatcher.since()` advances `.checkpoint` to the highest sn
        # EXAMINED — its own docstring calls it a scan cursor — so a seal this
        # page looks at and cannot act on is stepped over PERMANENTLY. And that
        # is the normal case, not an edge one: the seal is what tells us a body
        # exists, so the body necessarily arrives afterwards. Measured, one run:
        #
        #   17:36:11  CUO anchors the mandate; the actuary syncs the KEL, sees
        #             the seal, finds no local body, returns False — cursor moves
        #   17:36:22  peer_sync.stored said=EOaM4IbWLJGA   (11s too late)
        #
        # The retrieval worked perfectly and the mandate still never appeared.
        # Holding unresolved seals here is the consumer saying "I am not done
        # with this one", which the watcher's cursor cannot express.
        self._pending_seals: dict[str, dict] = {}  # candidate SAID -> seal
        self._egf_doc_cache = "unresolved"          # sentinel: distinct from a real None

        # attest state
        self._selected_mandate_said: str | None = None
        self.attest_drawer: AttestReviewDrawer | None = None
        # One-shot guard: an attestation is under way. `attest()` reaches
        # `vault.extend` with no natural barrier, so without this a double-click
        # schedules TWO `ServiceaidIssueDoer`s and mints two permanent, public
        # credentials for one rate program -- and the second listener replaces
        # the first, so a single banner covers both and the actuary never learns
        # there are two. `CuoMandatePage` carries the same guard (`_anchoring`)
        # for the same reason; this page was the one irreversible mint without it.
        self._attesting = False
        self._parse_manifest: dict | None = None
        self._parse_manifest_said: str | None = None

        self.setObjectName("actuaryPage")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(48, 48, 48, 48)
        # 24px between blocks, and 32px before each section heading (added at the
        # heading itself). The two jobs on this page ARE its meaning, and at a
        # uniform 16px the boundary between them was drawn at the same strength
        # as a paragraph gap. Both values are on the suite's 4px scale.
        outer.setSpacing(24)

        heading = QLabel("Observe a Mandate, Attest a Rate Program")
        heading.setStyleSheet(
            f"font-size: 24px; font-weight: 600; color: {colors.TEXT_PRIMARY};")
        outer.addWidget(heading)

        description = QLabel(
            "The mandate below was never sent to you — this watches the CUO's own "
            "log and verifies what it finds there. Once you have parsed a rate "
            "program in Excel and ipd-parse, attest it against the mandate you "
            "observed. No rates are shown here; Excel is the rate UI."
        )
        description.setWordWrap(True)
        # 14px, not 13: 13 is not a step on the suite's scale
        # (11·12·14·16·18·20·24·30). TEXT_SUBTLE, not TEXT_SECONDARY: measured
        # 4.483:1 for #6E7074 on this page's #F2F3FA, just under the 4.5:1 floor
        # ui-conventions.md:74 sets. Fixed page-locally rather than by darkening
        # the shared token, whose blast radius is the whole app and whose value
        # is not brandable (colors.py) -- that is an owner call, not mine.
        description.setStyleSheet(
            f"color: {colors.TEXT_SUBTLE}; font-size: 14px;")
        outer.addWidget(description)

        self._error_banner = QLabel("")
        self._error_banner.setObjectName("actuaryPage.errorBanner")
        self._error_banner.setWordWrap(True)
        self._error_banner.setStyleSheet(
            f"color: {colors.DANGER}; background-color: {colors.BACKGROUND_ERROR}; "
            "border-radius: 6px; padding: 8px 12px;")
        self._error_banner.setVisible(False)
        outer.addWidget(self._error_banner)

        # -- Pane 1: observed mandates -------------------------------------------
        outer.addSpacing(8)
        observed_heading = QLabel("Observed mandates")
        # design-system.md:260 "Section header | text-lg font-semibold | 16px
        # semibold". These set weight and NO size, so they inherited 12px and
        # differed from body text by weight alone.
        observed_heading.setStyleSheet(
            f"font-size: 16px; font-weight: 600; color: {colors.TEXT_PRIMARY};")
        outer.addWidget(observed_heading)

        self._observed_list = QListWidget()
        self._observed_list.setObjectName("actuaryPage.observedMandates")
        # devctl's click_list_item emits QAbstractItemView.clicked(QModelIndex),
        # not QListWidget.itemClicked(QListWidgetItem) -- connect to the signal
        # devctl (and every real mouse click, which clicked() also fires for)
        # actually emits, not the item-based convenience signal.
        self._observed_list.clicked.connect(self._on_mandate_clicked)
        # KEYBOARD. `clicked` fires for mouse and for devctl, and for nothing
        # else -- so arrow keys moved the highlight while `_selected_mandate_said`
        # stayed put, and Attest went on refusing with no explanation. The whole
        # attest flow was mouse-only. Both connections are kept: `clicked` is
        # devctl's contract, `currentItemChanged` is the keyboard's.
        self._observed_list.currentItemChanged.connect(self._on_mandate_current)
        self._observed_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {colors.BACKGROUND_CONTENT};
                border: 1px solid {colors.BORDER_DARK};
                border-radius: 4px;
                padding: 4px;
                font-size: 14px;
            }}
            QListWidget::item {{
                padding: 8px 12px;
                border-radius: 4px;
                color: {colors.TEXT_PRIMARY};
            }}
            QListWidget::item:hover {{
                background-color: {colors.BACKGROUND_TABLE_ROW_HOVER};
            }}
            QListWidget::item:selected {{
                background-color: {colors.BACKGROUND_TABLE_ROW_SELECTED};
                color: {colors.TEXT_PRIMARY};
                border-left: 3px solid {colors.PRIMARY_PRESSED};
            }}
        """)
        outer.addWidget(self._observed_list)

        # THE EMPTY STATE. Measured before this: the list interior was 1080x188
        # with ZERO non-background pixels and one distinct colour -- so "watching,
        # nothing declared yet" and "the watch is broken" were pixel-identical,
        # and this is the state the actuary sits in front of most.
        #
        # No CTA, deliberately departing from ux-patterns.md:161 ("illustration +
        # message + primary action"): there is no action to offer. A mandate
        # arrives because a CUO declares one somewhere else; the only honest
        # thing this page can do is say what it is doing and prove it is still
        # doing it.
        self._empty_state = QLabel("")
        self._empty_state.setObjectName("actuaryPage.observedEmpty")
        self._empty_state.setWordWrap(True)
        self._empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_state.setStyleSheet(
            f"color: {colors.TEXT_SUBTLE}; font-size: 14px;"
            f" background-color: {colors.BACKGROUND_CONTENT};"
            f" border: 1px dashed {colors.BORDER_DARK};"
            f" border-radius: 4px; padding: 28px 24px;")
        outer.addWidget(self._empty_state)

        self._selected_label = QLabel("No mandate selected.")
        self._selected_label.setObjectName("actuaryPage.selectedMandate")
        self._selected_label.setWordWrap(True)
        self._selected_label.setStyleSheet(f"color: {colors.TEXT_SECONDARY};")
        outer.addWidget(self._selected_label)

        # -- Pane 2: attest -------------------------------------------------------
        outer.addSpacing(8)
        attest_heading = QLabel("Attest a rate program")
        # design-system.md:260 "Section header | text-lg font-semibold | 16px
        # semibold". These set weight and NO size, so they inherited 12px and
        # differed from body text by weight alone.
        attest_heading.setStyleSheet(
            f"font-size: 16px; font-weight: 600; color: {colors.TEXT_PRIMARY};")
        outer.addWidget(attest_heading)

        form = QFormLayout()
        # ux-patterns.md:300 "Label position: Always above the field. Never to the
        # left." A side-label column breaks the single scan line the rest of the
        # page reads down, and it is what squeezed the parse-directory field to
        # ~145px in the built page -- narrower than the paths it accepts.
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        # EXPLICIT, because the default is style-dependent and the two styles
        # disagree: Fusion (what offscreen tests and every screenshot I take run
        # under) defaults to AllNonFixedFieldsGrow, while the macOS style defaults
        # to FieldsStayAtSizeHint. So the parse-directory field rendered full
        # width in every render I checked and ~150px on the owner's actual Mac --
        # narrower than the absolute paths it exists to accept.
        form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setHorizontalSpacing(0)
        form.setVerticalSpacing(8)
        outer.addLayout(form)

        self._parse_dir = LocksmithLineEdit(
            placeholder_text="path to a real ipd-parse output directory")
        self._parse_dir.setObjectName("actuaryPage.parseDir")
        # A loaded parse belongs to the path it was loaded FROM. Without this the
        # actuary could load directory A, edit the field to directory B, and
        # attest -- minting a permanent, public credential that binds directory
        # A's manifest SAID and workbook digest while the screen displayed B.
        # Nothing else caught it: `attest()` reads `_parse_manifest_said`, never
        # the field, so the UI behaved exactly as designed and the ARTEFACT was
        # wrong. The one defect on this page where the credential itself is
        # incorrect rather than merely hard to read.
        self._parse_dir.textChanged.connect(self._invalidate_parse)
        form.addRow("Parse directory", self._parse_dir)

        # SECONDARY. Loading a parse is a local, re-runnable directory read; it
        # carried the exact same filled-teal authority as a permanent public mint
        # sitting 120px below it, so the page had two primaries and therefore
        # none. design-system.md:236 allows one.
        self._load_parse = LocksmithInvertedButton("Load Parse")
        self._load_parse.setObjectName("actuaryPage.loadParse")
        self._load_parse.clicked.connect(self.load_parse)
        self._load_parse.setSizePolicy(QSizePolicy.Policy.Maximum,
                                       QSizePolicy.Policy.Fixed)
        load_row = QHBoxLayout()
        load_row.setContentsMargins(0, 0, 0, 0)
        load_row.addWidget(self._load_parse)
        load_row.addStretch(1)
        form.addRow(load_row)

        # THE EVIDENCE. These two 44-character digests are the entire content of
        # the credential this page mints, and they were bare QLabels with no
        # stylesheet at all -- proportional, palette black, unselectable. In a
        # proportional face `l`/`I`/`1` and `O`/`0` are the same shape, and an
        # actuary cannot proof-read what they cannot distinguish. Mono, plain
        # text, selectable so they can be copied and compared against the
        # parser's own output. The em dash placeholder says "nothing loaded yet"
        # instead of leaving an unexplained blank.
        self._manifest_said_label = self._evidence_label("actuaryPage.manifestSaid")
        form.addRow("Manifest SAID", self._manifest_said_label)

        self._workbook_digest_label = self._evidence_label(
            "actuaryPage.workbookDigest")
        form.addRow("Workbook digest", self._workbook_digest_label)

        # "Review…", not "Attest": the page primary opens the read-back, and the
        # commit verb lives on the drawer's own confirm. Two-stage vocabulary,
        # matching the sibling flow -- the button that mints must be the one that
        # says so, and it must not be reachable from the page.
        # THE THREE THE ACTUARY ASSERTS. All three are `required` by the
        # attestation schema and all three were hardcoded -- `version="1.0"`,
        # `filing_date=today`, `action="Sandbox"` -- so the app was making
        # permanent, public assertions on the actuary's behalf that they never
        # saw. The schema is explicit that they are theirs: version is "a
        # human-chosen label", filing_date is "the filing date the actuary
        # recorded at parse time ... an attribute the actuary asserts", and
        # action is "the IPD retention contract the parse was run under".
        #
        # `Sandbox` in particular is a retention CONTRACT, not a test mode -- the
        # schema says so in capitals -- so defaulting every attestation to it
        # silently claimed exploratory retention for filed work.
        self._version = LocksmithLineEdit(placeholder_text="e.g. 2027.1")
        self._version.setObjectName("actuaryPage.version")
        self._version.textChanged.connect(lambda _t: self._update_attest_enabled())
        form.addRow("Rate program version", self._version)

        self._filing_date = QDateEdit()
        self._filing_date.setObjectName("actuaryPage.filingDate")
        self._filing_date.setDisplayFormat("MM/dd/yyyy")
        self._filing_date.setCalendarPopup(True)
        # Today is a DEFAULT, not an assertion the app makes: the field is
        # editable, and the read-back shows whatever it holds.
        self._filing_date.setDate(QDate.currentDate())
        self._filing_date.setStyleSheet(
            f"QDateEdit {{ border: 1px solid {colors.BORDER_DARK};"
            f" border-radius: 6px; padding: 12px; font-size: 14px;"
            f" color: {colors.TEXT_PRIMARY}; }}")
        form.addRow("Filing date", self._filing_date)

        self._action = QComboBox()
        self._action.setObjectName("actuaryPage.action")
        # From the schema's own enum, not a hand-kept list.
        self._action.addItems(_ACTION_VALUES)
        self._action.setStyleSheet(
            f"QComboBox {{ border: 1px solid {colors.BORDER_DARK};"
            f" border-radius: 6px; padding: 12px; font-size: 14px;"
            f" color: {colors.TEXT_PRIMARY}; }}")
        form.addRow("Retention", self._action)

        self._attest = LocksmithButton("Review attestation…")
        self._attest.setObjectName("actuaryPage.attest")
        self._attest.setEnabled(False)
        self._attest.clicked.connect(self.review_attestation)
        self._attest.setSizePolicy(QSizePolicy.Policy.Maximum,
                                   QSizePolicy.Policy.Fixed)

        # ALWAYS VISIBLE, not a tooltip. "Silently disabled" is the state the
        # actuary meets most on this page, and a Qt tooltip is unreachable by
        # keyboard -- so the reason the mint is blocked has to be on the screen,
        # not one hover away. The tooltip is set too, for the mouse.
        self._attest_blocker = QLabel("")
        self._attest_blocker.setObjectName("actuaryPage.attestBlocker")
        self._attest_blocker.setWordWrap(True)
        self._attest_blocker.setStyleSheet(
            f"color: {colors.TEXT_SUBTLE}; font-size: 12px;")

        attest_row = QHBoxLayout()
        attest_row.setContentsMargins(0, 0, 0, 0)
        attest_row.addWidget(self._attest_blocker)
        # An explicit stretch, NOT the blocker's own stretch factor: a hidden
        # widget is ignored by the layout and surrenders its stretch, so once the
        # gate cleared and the blocker line disappeared the primary drifted to
        # the CENTRE of the page. The button's position must not depend on
        # whether something else is currently visible.
        attest_row.addStretch(1)
        attest_row.addWidget(self._attest)
        outer.addLayout(attest_row)

        self._attested_banner = QLabel("")
        self._attested_banner.setObjectName("actuaryPage.attestedBanner")
        self._attested_banner.setWordWrap(True)
        self._attested_banner.setStyleSheet(
            f"color: {colors.SUCCESS_TEXT}; background-color: {colors.BACKGROUND_SUCCESS}; "
            "border-radius: 6px; padding: 8px 12px;")
        self._attested_banner.setVisible(False)
        outer.addWidget(self._attested_banner)

        outer.addStretch(1)

        # -- watch loop -------------------------------------------------------------
        self._last_checked: str = ""
        # Paint the initial gate state: both the placard and the blocker line are
        # rendered from state, and neither had been asked to render yet, so the
        # page opened with an empty box and a silently-disabled primary -- the
        # exact two things this work exists to remove.
        self._render_empty_state()
        self._update_attest_enabled()

        # design-system.md:311 "Tab order: Follows visual layout order". Measured
        # before: parseDir -> loadParse -> attest -> list, so the keyboard reached
        # step ONE last, after the irreversible step.
        self.setTabOrder(self._observed_list, self._parse_dir)
        self.setTabOrder(self._parse_dir, self._load_parse)
        self.setTabOrder(self._load_parse, self._attest)

        self._watch_timer = QTimer(self)
        self._watch_timer.setInterval(_WATCH_POLL_MS)
        self._watch_timer.timeout.connect(self._scan_for_mandates)
        if self._app is not None and getattr(self._app, "vault", None) is not None:
            self._prepare_import_schema()
            self._scan_for_mandates()  # an immediate first pass -- don't make a
                                        # freshly-revealed page wait a full tock
            self._watch_timer.start()

    # -- schema plumbing ----------------------------------------------------------

    def _ensure_schema_pinned(self, hby, schema_said: str) -> None:
        """Pin `schema_said`'s schema into `hby.db.schema` if absent, reading it
        from the bundled EGF -- mirrors `CuoMandatePage._ensure_mandate_schema_pinned`.
        Both the mandate this desk WATCHES and the attestation it MINTS need their
        own schema resolvable: the mandate's for `Verifier.processCredential` to
        validate what lands locally, the attestation's for `Credentialer.create` on
        the issuing side."""
        from keri.core import scheming
        from keri.kering import Kinds

        if hby.db.schema.get(keys=(schema_said,)) is not None:
            return
        egf_dir = egf_local_dir()
        if egf_dir is None:
            raise RuntimeError(
                "no bundled EGF directory for this brand -- cannot resolve "
                f"schema {schema_said}")
        schema_path = egf_dir / f"{schema_said}.json"
        if not schema_path.is_file():
            raise RuntimeError(f"schema not bundled at {schema_path}")
        sad = json.loads(schema_path.read_text())
        schemer = scheming.Schemer(sed=sad, kind=Kinds.json)
        if schemer.said != schema_said:
            raise RuntimeError(f"bundled schema at {schema_path} does not verify")
        hby.db.schema.pin(keys=(schemer.said,), val=schemer)

    def _prepare_import_schema(self) -> None:
        try:
            self._ensure_schema_pinned(self._app.vault.hby, PRODUCT_MANDATE_SCHEMA_SAID)
        except Exception:  # noqa: BLE001 -- a missing schema must not crash the page;
            # _scan_for_mandates degrades to "nothing observed yet", which is
            # diagnosable, rather than an unrevealed surface.
            logger.exception("actuary.watch.schema_prepare_failed")

    # -- identifier resolution --------------------------------------------------

    def _actuary_hab(self, vault):
        """The identifier that attests: whichever local hab holds this vault's
        `actuary_role` credential -- mirrors `CuoMandatePage._cuo_hab`."""
        from locksmith.plugins.actuary.plugin import ACTUARY_ROLE_SCHEMA_SAID

        hby = vault.hby
        reger = vault.rgy.reger
        for pre, hab in hby.habs.items():
            for saider in reger.subjs.get(keys=(pre,)):
                creder = reger.creds.get(keys=(saider.qb64,))
                if creder is not None and creder.schema == ACTUARY_ROLE_SCHEMA_SAID:
                    return hab
        alias = brand().default_aid_alias or "default"
        return hby.habByName(alias)

    # -- watching -----------------------------------------------------------------

    def _egf_doc(self):
        """The active brand's `EgfDocument`, cached -- `verify_attestation`'s
        `accepted_schema_saids` check reads it. `None` is a legitimate steady
        state (a brand with no EGF pinned), and `verify_attestation` fails that
        check closed rather than raising when `egf` is `None`."""
        if self._egf_doc_cache == "unresolved":
            doc = None
            try:
                from locksmith.core.egf_seeding import make_hoa_resolver
                result = make_hoa_resolver(brand())
                if result is not None:
                    doc = result[1]
            except Exception:  # noqa: BLE001 -- see _prepare_import_schema
                logger.exception("actuary.watch.egf_resolve_failed")
            self._egf_doc_cache = doc
        return self._egf_doc_cache

    def _known_peer_pres(self, vault) -> list[str]:
        """Every AID this wallet knows about that is NOT one of its own local
        identifiers -- candidates to watch. Paired peers (imported via peer-OOBI
        blob) land here because their KEL replay populates `hby.kevers` the same
        way a local hab's own KEL does."""
        own = set(vault.hby.habs.keys())
        return [pre for pre in list(vault.hby.kevers.keys()) if pre not in own]

    def _watcher_for(self, hab, pre: str):
        from keri.app.anchoring import AnchorWatcher

        watcher = self._watchers.get(pre)
        if watcher is None:
            watcher = AnchorWatcher(hab=hab, pre=pre)
            self._watchers[pre] = watcher
        return watcher

    def _scan_for_mandates(self) -> None:
        # Stamped on every tick, before the early returns: a scan that cannot run
        # because there is no vault is still a scan that happened, and an actuary
        # watching a frozen timestamp learns something true. Format per
        # ux-patterns.md:390 "Date + time | MM/DD/YYYY h:mm A".
        self._last_checked = _dt.datetime.now().strftime("%m/%d/%Y %-I:%M %p")
        if not self._observed:
            self._render_empty_state()
        if self._app is None or getattr(self._app, "vault", None) is None:
            return
        vault = self._app.vault
        hab = next(iter(vault.hby.habs.values()), None)
        if hab is None:
            return

        changed = False

        # Retry everything we could not resolve last time, FIRST — the body may
        # have landed since, and the watcher will never offer these again.
        for candidate, seal in list(self._pending_seals.items()):
            if self._consider_one(vault, seal):
                self._pending_seals.pop(candidate, None)
                changed = True

        for pre in self._known_peer_pres(vault):
            watcher = self._watcher_for(hab, pre)
            for _sn, seal in watcher.since(watcher.checkpoint):
                if self._consider_one(vault, seal):
                    self._pending_seals.pop(seal.get("i") or "", None)
                    changed = True
                else:
                    candidate = seal.get("i")
                    # Only hold seals that could still become a mandate. A KEL's
                    # `a` block carries all sorts of anchors; one already
                    # observed, or with no `i` to resolve, is not pending on
                    # anything.
                    if candidate and candidate not in self._observed:
                        if candidate not in self._pending_seals:
                            logger.info("actuary.watch.pending said=%s",
                                        str(candidate)[:12])
                        self._pending_seals[candidate] = seal
        if changed:
            self._refresh_observed_list()

    def _consider_one(self, vault, seal: dict) -> bool:
        """`_consider_seal` with a blast radius of one seal.

        A KEL's `a` block carries anchors this page knows nothing about, and
        resolving one walks into keripy's TEL accessors — where an entry that
        has not arrived yet used to surface as a TypeError out of `dgKey`
        (upstream `cloneTvtAt` passed a None digest straight through; see
        keripy docs/FORK_DIVERGENCE.md). That exception propagated out of
        `_scan_for_mandates` and killed the ENTIRE scan mid-loop — including
        the `_refresh_observed_list()` at the end.

        Measured, one run: the mandate was retrieved, verified, and recorded in
        `self._observed`, and the list still rendered empty forever, because a
        LATER unrelated seal in the same pass raised before the repaint. A
        watch must degrade on the anchor it cannot read, never stop.
        """
        try:
            return self._consider_seal(vault, seal)
        except Exception:               # noqa: BLE001 — one bad anchor, not the watch
            logger.exception("actuary.watch.seal_failed said=%s",
                             str(seal.get("i"))[:12])
            return False

    def _consider_seal(self, vault, seal: dict) -> bool:
        """Try to resolve `seal` to a genuinely-anchored, schema-matching,
        TEL-current `product_mandate` -- the C1 seal->TEL->credential chain
        (`keri_serviceaid.providers.sealed_retrieval`), never trusting
        `seal["i"]` on its own. Returns True if a NEW mandate was recorded."""
        candidate_said = seal.get("i")
        if not candidate_said or candidate_said in self._observed:
            return False

        reger = vault.rgy.reger
        creder = reger.creds.get(keys=(candidate_said,))
        if creder is None:
            # Not landed locally yet — a real watch is asynchronous with
            # delivery, so this is the NORMAL first answer for a fresh seal.
            logger.debug("actuary.watch.skip reason=no_body said=%s",
                         str(candidate_said)[:12])
            return False
        if creder.schema != PRODUCT_MANDATE_SCHEMA_SAID:
            # An anchor for something else entirely — a KEL's `a` block is not
            # reserved for credential seals.
            logger.debug("actuary.watch.skip reason=other_schema said=%s "
                         "schema=%s", str(candidate_said)[:12],
                         str(creder.schema)[:12])
            return False

        from keri_serviceaid.providers.sealed_retrieval import (
            SealChainError, credential_said_from_seal,
        )

        iss_raw = reger.cloneTvtAt(candidate_said, sn=0)
        if not iss_raw:
            logger.debug("actuary.watch.skip reason=no_tel_iss said=%s",
                         str(candidate_said)[:12])
            return False
        iss_event = SerderKERI(raw=bytes(iss_raw)).sad
        try:
            proven_said = credential_said_from_seal(seal, iss_event)
        except SealChainError:
            logger.warning("actuary.watch.chain_broken said=%s", candidate_said)
            return False
        if proven_said != creder.said:
            logger.debug("actuary.watch.skip reason=said_mismatch said=%s "
                         "proven=%s", str(candidate_said)[:12],
                         str(proven_said)[:12])
            return False

        tel_state = None
        tever = reger.tevers.get(creder.regid)
        if tever is not None:
            state = tever.vcState(creder.said)
            if state is not None:
                tel_state = _TEL_STATE_LABELS.get(state.et, state.et)

        from keri_serviceaid.egf.attestation import verify_attestation

        verdict = verify_attestation(acdc=creder.sad, egf=self._egf_doc(),
                                     tel_state=tel_state)
        if not verdict.ok:
            logger.warning("actuary.watch.verify_failed said=%s failures=%s",
                           candidate_said, verdict.failures)
            return False

        attrs = creder.sad.get("a", {}) or {}
        # The whole mandate, not three fields of it. The attestation's edge
        # asserts "my rate program answers THAT mandate", and until the read-back
        # existed there was nowhere to show what "that" is: the window and thesis
        # were never even read, the coverages were stored and rendered nowhere,
        # and the issuer was dropped entirely -- so two different AIDs declaring
        # `auto / US-UT` produced indistinguishable rows.
        self._observed[creder.said] = {
            "line_of_business": attrs.get("line_of_business", ""),
            "jurisdiction": attrs.get("jurisdiction", ""),
            "coverages": list(attrs.get("coverages", []) or []),
            "window_opens": attrs.get("window_opens", ""),
            "window_closes": attrs.get("window_closes", ""),
            "thesis": attrs.get("thesis", ""),
            "issuer": getattr(creder, "issuer", "") or "",
        }
        return True

    def _on_mandate_current(self, current, _previous=None) -> None:
        """Keyboard selection. Mirrors `_on_mandate_clicked`, which is index-based
        because that is what devctl emits; this is item-based because that is what
        arrow keys emit."""
        if current is None:
            return
        self._select_mandate(current.data(Qt.UserRole))

    def _refresh_observed_list(self) -> None:
        self._render_empty_state()
        self._observed_list.clear()
        for said, mandate in self._observed.items():
            # Two lines, and the SAID in FULL. `said[:12]…` in a proportional
            # face is not an identifier an actuary can tell apart from another --
            # and two AIDs can declare the same line and jurisdiction, so the
            # SAID is the only thing that distinguishes the rows. The edge this
            # page mints points at exactly one of them.
            item = QListWidgetItem(
                f"{mandate['line_of_business']} / {mandate['jurisdiction']}\n{said}")
            item.setData(Qt.UserRole, said)
            item.setFont(self._row_font())
            self._observed_list.addItem(item)

    def _row_font(self):
        """The list row's font. Qt gives a QListWidgetItem no per-line styling, so
        the whole row goes monospace -- the SAID is the half that needs it, and a
        mixed row would need a delegate for a gain nobody asked for."""
        from PySide6.QtGui import QFont

        font = QFont(get_monospace_font_family())
        # A QFont given a family Qt does not know falls back SILENTLY to the
        # default proportional face. The style hint is what makes the fallback
        # itself monospaced.
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPixelSize(13)
        return font

    def _render_empty_state(self) -> None:
        """Show the placard instead of an empty box, and hide it once anything
        has been observed. The heartbeat is the part that distinguishes a healthy
        quiet watch from a dead one -- a timestamp that advances is the only
        evidence a poll is still running that this page can honestly give."""
        empty = not self._observed
        self._observed_list.setVisible(not empty)
        self._empty_state.setVisible(empty)
        if not empty:
            return
        checked = self._last_checked
        heartbeat = (f"Last checked {checked}." if checked
                     else "Waiting for the first check…")
        self._empty_state.setText(
            "No mandates observed yet.\n\n"
            "A mandate is never sent here — this watches the CUO's own log and "
            "picks one up once it has been declared and anchored.\n"
            f"{heartbeat}")

    def _on_mandate_clicked(self, index) -> None:
        item = self._observed_list.item(index.row())
        if item is None:
            return
        self._select_mandate(item.data(Qt.UserRole))

    def _select_mandate(self, said: str | None) -> None:
        """The one place selection happens, whichever input caused it.

        Extracted so the mouse path and the keyboard path cannot drift: they were
        one handler and one signal, and the signal only fired for the mouse.
        """
        if not said:
            return
        self._selected_mandate_said = said
        mandate = self._observed.get(said, {})
        self._selected_label.setText(
            f"Selected: {said} — {mandate.get('line_of_business', '')} / "
            f"{mandate.get('jurisdiction', '')}")
        self._update_attest_enabled()

    # -- parse loading --------------------------------------------------------------

    def _resolve_workbook(self, parse_dir: Path) -> Path | None:
        sidecar = parse_dir / _WORKBOOK_SIDECAR_NAME
        if not sidecar.is_file():
            return None
        try:
            data = json.loads(sidecar.read_text())
            path = Path(data["workbook_path"])
        except (OSError, ValueError, KeyError, TypeError):
            return None
        return path if path.is_file() else None

    def load_parse(self, *_qt_args) -> None:
        self._error_banner.setVisible(False)
        self._attested_banner.setVisible(False)

        parse_dir = Path(self._parse_dir.text().strip())
        if not parse_dir.is_dir():
            self._show_error(f"Not a directory: {parse_dir}")
            return

        workbook_path = self._resolve_workbook(parse_dir)
        if workbook_path is None:
            self._show_error(
                "No source workbook recorded for this parse directory — expected "
                f"a {_WORKBOOK_SIDECAR_NAME} sidecar naming it (ipd-parse itself "
                "does not preserve the workbook's location in its own output).")
            return

        try:
            manifest = _build_manifest(parse_dir, workbook_path)
        except OSError as exc:
            self._show_error(f"Could not read the parse directory or workbook: {exc}")
            return

        said = _manifest_said(manifest)
        self._parse_manifest = manifest
        self._parse_manifest_said = said
        self._manifest_said_label.setText(said)
        self._workbook_digest_label.setText(manifest["workbook_digest"])
        self._update_attest_enabled()

    def _release_attest(self) -> None:
        """Drop the in-flight guard once issuance has resolved, either way.

        BOTH outcomes, not just success: a guard that only lifts on
        `credential_issued` turns one failed attestation into a permanently dead
        button, which is the trap the sibling read-back shipped with for a commit
        (its "Signing..." modal survived its own success). The re-enable still
        goes through `_update_attest_enabled`, so a parse invalidated mid-flight
        does not come back armed.
        """
        self._attesting = False
        self._update_attest_enabled()

    def _invalidate_parse(self, *_qt_args) -> None:
        """Forget the loaded parse the moment the path it came from changes.

        Clears the displayed evidence too, not just the internal state: leaving a
        manifest SAID and workbook digest on screen under a path that no longer
        produced them is the same lie in a quieter font.
        """
        if self._parse_manifest_said is None and self._parse_manifest is None:
            return
        self._parse_manifest = None
        self._parse_manifest_said = None
        self._manifest_said_label.setText("—")
        self._workbook_digest_label.setText("—")
        self._attested_banner.setVisible(False)
        self._update_attest_enabled()

    def _evidence_label(self, object_name: str) -> QLabel:
        """A monospaced, selectable, plain-text value with an em-dash placeholder."""
        label = QLabel("—")
        label.setObjectName(object_name)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setStyleSheet(
            f"color: {colors.TEXT_PRIMARY}; font-size: 14px;"
            f" font-family: {_mono_css()};")
        return label

    def _attest_blocker_text(self) -> str:
        """Why the mint is unavailable, in the actuary's own sequence.

        Returns "" when nothing blocks. Names ONE reason at a time, the first one
        in the order the page asks for them, so the line reads as the next step
        rather than as a list of complaints.
        """
        if self._attesting:
            return "Attesting…"
        if not self._selected_mandate_said:
            return "Select an observed mandate to attest against."
        if self._parse_manifest_said is None:
            return "Load a parse directory to attest."
        if not self._version.text().strip():
            # Schema-required, and the one field with no defensible default: it
            # is the actuary's own label for this rate program.
            return "Give the rate program a version to attest."
        return ""

    def _update_attest_enabled(self) -> None:
        blocked = self._attest_blocker_text()
        self._attest.setEnabled(not blocked)
        self._attest.setToolTip(blocked)
        self._attest_blocker.setText(blocked)
        self._attest_blocker.setVisible(bool(blocked))

    # -- attest / issuance --------------------------------------------------------

    def _attestation_attributes(self) -> dict:
        """The ACDC attribute block. Built HERE rather than inline in `attest()`
        so the read-back can show exactly what will be committed -- three of
        these are asserted on the actuary's behalf and were previously invisible.
        One source, so the drawer cannot drift from the mint."""
        return {
            "manifest_said": self._parse_manifest_said,
            "version": self._version.text().strip(),
            "filing_date": self._filing_date.date().toString("yyyy-MM-dd"),
            "action": self._action.currentText(),
        }

    def review_attestation(self, *_qt_args) -> None:
        """Open the read-back. Nothing is minted until its own confirm."""
        if self._attesting or self.attest_drawer is not None:
            return
        if not self._selected_mandate_said or self._parse_manifest_said is None:
            self._show_error("Select an observed mandate and load a parse first.")
            return

        drawer = AttestReviewDrawer(
            mandate_said=self._selected_mandate_said,
            mandate=self._observed.get(self._selected_mandate_said, {}),
            manifest_said=self._parse_manifest_said,
            workbook_digest=(self._parse_manifest or {}).get("workbook_digest", ""),
            attributes=self._attestation_attributes(),
            parent=self)
        self.attest_drawer = drawer
        drawer.confirm.connect(self.attest)
        drawer.cancelled.connect(self._forget_drawer)
        drawer.open_drawer()

    def _forget_drawer(self) -> None:
        self.attest_drawer = None

    def _close_drawer(self) -> None:
        drawer, self.attest_drawer = self.attest_drawer, None
        if drawer is None:
            return
        try:
            # `finish()`, NOT `close_drawer()`: the drawer refuses to close while
            # an attestation is in flight, so a plain close is ignored and the
            # read-back survives its own success.
            drawer.finish()
        except RuntimeError:                # already destroyed by Qt
            pass

    def attest(self, *_qt_args) -> None:
        """Issue the `rate_program_attestation` ACDC, NI2I-edged to the selected
        mandate. See the module docstring for the issuance mechanic; mirrors
        `CuoMandatePage.submit` (retire-listener / vault.extend, subscribing to
        the doer's EMITTED source name `"IssueCredentialDoer"`, the legacy one)."""
        if self._attesting:
            return
        self._error_banner.setVisible(False)
        if self._app is None or getattr(self._app, "vault", None) is None:
            self._show_error("No open vault — cannot attest.")
            return
        if not self._selected_mandate_said or self._parse_manifest_said is None:
            self._show_error("Select an observed mandate and load a parse first.")
            return

        vault = self._app.vault
        hab = self._actuary_hab(vault)
        if hab is None:
            self._show_error("No identifier available to attest from.")
            return

        try:
            self._ensure_schema_pinned(vault.hby, RATE_PROGRAM_ATTESTATION_SCHEMA_SAID)
            from keri_serviceaid.providers.issue import ensure_registry
            ensure_registry(vault.hby, hab, vault.rgy,
                            name=RATE_PROGRAM_ATTESTATION_SCHEMA_SAID)
        except Exception as exc:  # noqa: BLE001
            logger.exception("actuary.attest.prepare_failed")
            self._show_error(f"Could not prepare to attest: {exc}")
            return

        # `mandate_said` is NOT an ACDC attribute -- it names the edge's far
        # node (`edges["mandate"]["cred_said"]` below), and the schema's own
        # `a` block has no property for it (`additionalProperties: false`
        # rejected it here, measured). `carried_coverages` is the same shape
        # of not-an-attribute: the micro-app template's own description says
        # so explicitly ("INPUT to the consistency check... deliberately NOT
        # an attestation attribute" -- the manifest_said the ACDC DOES carry
        # is what a consumer re-derives to learn the real coverage set).
        payload = self._attestation_attributes()
        # NI2I: the mandate is untargeted, and per the ACDC spec an edge to an
        # untargeted far node MUST NOT be I2I/DI2I. "NI2I" (not "references",
        # the micro-app-template's own authoring-layer vocabulary for this
        # same operator) is the literal wire value the bundled schema's `o`
        # field requires (`"const": "NI2I"`, schemas/rate_program_attestation
        # .json) -- keripy's `_build_edge_source` passes this straight
        # through into the ACDC's `e` block. See the corpus's own
        # `attestation_authority_is_admin_rooted` rule -- the edge is
        # provenance, never authority.
        edges = {
            "mandate": {
                "cred_said": self._selected_mandate_said,
                "schema_said": PRODUCT_MANDATE_SCHEMA_SAID,
                "operator": "NI2I",
            },
        }

        # Armed HERE, not at the top: every `return` above is a refusal that
        # leaves the actuary free to try again, and latching the guard before
        # them would disable the button permanently on a typo'd path.
        self._attesting = True
        self._update_attest_enabled()

        signals = vault.signals
        schema_said = RATE_PROGRAM_ATTESTATION_SCHEMA_SAID

        stale = self._pending_listener
        if stale is not None:
            signals.doer_event.disconnect(stale)
            self._pending_listener = None

        def _on_issue_event(doer_name: str, event_type: str, data: dict) -> None:
            if doer_name != "IssueCredentialDoer" or data.get("schema_said") != schema_said:
                return
            if event_type == "credential_issuance_failed":
                self._retire_listener(_on_issue_event)
                self._release_attest()
                self._close_drawer()
                self._show_error(data.get("error", "Attestation failed."))
                return
            if event_type != "credential_issued":
                return
            self._retire_listener(_on_issue_event)
            self._release_attest()
            self._close_drawer()
            self._show_attested(data.get("said", ""))

        self._pending_listener = _on_issue_event
        signals.doer_event.connect(_on_issue_event)

        issue_doer = ServiceaidIssueDoer(
            self._app,
            schema_said=schema_said,
            recipient=None,             # untargeted — the designer READS it
            attributes=payload,
            registry_name=schema_said,
            edges=edges,
        )
        vault.extend([issue_doer])

    def _retire_listener(self, listener) -> None:
        signals = self._app.vault.signals
        signals.doer_event.disconnect(listener)
        if self._pending_listener is listener:
            self._pending_listener = None

    def _show_error(self, message: str) -> None:
        self._error_banner.setText(message)
        self._error_banner.setVisible(True)

    def _show_attested(self, said: str) -> None:
        # IN FULL. `said[:12]…` is not a handle: an actuary cannot go and find
        # what they just published from a twelfth of its identifier, and this
        # credential is the artefact the whole page exists to produce. Monospaced
        # and selectable for the same reason the evidence values are.
        self._attested_banner.setTextFormat(Qt.TextFormat.PlainText)
        self._attested_banner.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self._attested_banner.setStyleSheet(
            f"color: {colors.SUCCESS_TEXT};"
            f" background-color: {colors.BACKGROUND_SUCCESS};"
            f" border-radius: 6px; padding: 8px 12px; font-size: 14px;"
            f" font-family: {_mono_css()};")
        self._attested_banner.setText(
            f"Rate program attested. {said}" if said else "Rate program attested.")
        self._attested_banner.setVisible(True)
