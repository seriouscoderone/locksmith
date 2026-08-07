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

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFormLayout, QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget,
)

from keri import help
from keri.core.serdering import SerderKERI
from keri.kering import Ilks

from locksmith.core.branding import brand, egf_local_dir
from locksmith.core.serviceaid_bridge import ServiceaidIssueDoer
from locksmith.ui import colors
from locksmith.ui.toolkit.widgets import LocksmithButton
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

_TEL_STATE_LABELS = {
    Ilks.iss: "issued", Ilks.bis: "issued",
    Ilks.rev: "revoked", Ilks.brv: "revoked",
}


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
        self._parse_manifest: dict | None = None
        self._parse_manifest_said: str | None = None

        self.setObjectName("actuaryPage")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(48, 48, 48, 48)
        outer.setSpacing(16)

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
        description.setStyleSheet(
            f"color: {colors.TEXT_SECONDARY}; font-size: 13px;")
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
        observed_heading = QLabel("Observed mandates")
        observed_heading.setStyleSheet(
            f"font-weight: 600; color: {colors.TEXT_PRIMARY};")
        outer.addWidget(observed_heading)

        self._observed_list = QListWidget()
        self._observed_list.setObjectName("actuaryPage.observedMandates")
        # devctl's click_list_item emits QAbstractItemView.clicked(QModelIndex),
        # not QListWidget.itemClicked(QListWidgetItem) -- connect to the signal
        # devctl (and every real mouse click, which clicked() also fires for)
        # actually emits, not the item-based convenience signal.
        self._observed_list.clicked.connect(self._on_mandate_clicked)
        outer.addWidget(self._observed_list)

        self._selected_label = QLabel("No mandate selected.")
        self._selected_label.setObjectName("actuaryPage.selectedMandate")
        self._selected_label.setWordWrap(True)
        self._selected_label.setStyleSheet(f"color: {colors.TEXT_SECONDARY};")
        outer.addWidget(self._selected_label)

        # -- Pane 2: attest -------------------------------------------------------
        attest_heading = QLabel("Attest a rate program")
        attest_heading.setStyleSheet(
            f"font-weight: 600; color: {colors.TEXT_PRIMARY};")
        outer.addWidget(attest_heading)

        form = QFormLayout()
        outer.addLayout(form)

        self._parse_dir = LocksmithLineEdit(
            placeholder_text="path to a real ipd-parse output directory")
        self._parse_dir.setObjectName("actuaryPage.parseDir")
        form.addRow("Parse directory", self._parse_dir)

        self._load_parse = LocksmithButton("Load Parse")
        self._load_parse.setObjectName("actuaryPage.loadParse")
        self._load_parse.clicked.connect(self.load_parse)
        form.addRow(self._load_parse)

        self._manifest_said_label = QLabel("")
        self._manifest_said_label.setObjectName("actuaryPage.manifestSaid")
        self._manifest_said_label.setWordWrap(True)
        form.addRow("Manifest SAID", self._manifest_said_label)

        self._workbook_digest_label = QLabel("")
        self._workbook_digest_label.setObjectName("actuaryPage.workbookDigest")
        self._workbook_digest_label.setWordWrap(True)
        form.addRow("Workbook digest", self._workbook_digest_label)

        self._attest = LocksmithButton("Attest Rate Program")
        self._attest.setObjectName("actuaryPage.attest")
        self._attest.setEnabled(False)
        self._attest.clicked.connect(self.attest)
        outer.addWidget(self._attest)

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
        self._observed[creder.said] = {
            "line_of_business": attrs.get("line_of_business", ""),
            "jurisdiction": attrs.get("jurisdiction", ""),
            "coverages": list(attrs.get("coverages", []) or []),
        }
        return True

    def _refresh_observed_list(self) -> None:
        self._observed_list.clear()
        for said, mandate in self._observed.items():
            label = (f"{mandate['line_of_business']} / {mandate['jurisdiction']} "
                     f"— {said[:12]}…")
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, said)
            self._observed_list.addItem(item)

    def _on_mandate_clicked(self, index) -> None:
        item = self._observed_list.item(index.row())
        if item is None:
            return
        said = item.data(Qt.UserRole)
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

    def _update_attest_enabled(self) -> None:
        self._attest.setEnabled(
            bool(self._selected_mandate_said) and self._parse_manifest_said is not None)

    # -- attest / issuance --------------------------------------------------------

    def attest(self, *_qt_args) -> None:
        """Issue the `rate_program_attestation` ACDC, NI2I-edged to the selected
        mandate. See the module docstring for the issuance mechanic; mirrors
        `CuoMandatePage.submit` (retire-listener / vault.extend, subscribing to
        the doer's EMITTED source name `"IssueCredentialDoer"`, the legacy one)."""
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
        payload = {
            "manifest_said": self._parse_manifest_said,
            "version": "1.0",
            "filing_date": _dt.date.today().isoformat(),
            "action": "Sandbox",
        }
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
                self._show_error(data.get("error", "Attestation failed."))
                return
            if event_type != "credential_issued":
                return
            self._retire_listener(_on_issue_event)
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
        self._attested_banner.setText(
            f"Rate program attested ({said[:12]}…)." if said else "Rate program attested.")
        self._attested_banner.setVisible(True)
