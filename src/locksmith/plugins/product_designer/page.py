# -*- encoding: utf-8 -*-
"""
locksmith.plugins.product_designer.page module — the designer's receive-and-assemble
surface.

Design §5's third pane over C1's headless library: a table of received rate programs,
and an assemble action that gathers a mandate's programs into a `product_bundle`.

**Received programs — populated by READING, not by watching.** Unlike the CUO's
mandate (untargeted, discovered only by scanning a KEL — `plugins/cuo/page.py`) or the
actuary's watch of that same mandate (`plugins/actuary/page.py`'s `AnchorWatcher`
chain), a `rate_program_attestation` this page shows has already LANDED locally —
admitted through this wallet's own real Kevery/Tevery/Verifier, by whatever transport
delivered it (an IPEX grant admitted through the stock Received Credentials flow, or a
bare ACDC over a peer connection; both leave the SAME trace: a schema-matching,
chain-verified entry in `vault.rgy.reger.saved`/`reger.creds`). This page does not care
which — it polls the registry for anything of the right schema that is genuinely
`saved` (never escrowed, never assumed) and reads it.

**The mandate column is an EDGE, not an attribute.** `rate_program_attestation`'s own
schema carries no `mandate_said` field — the mandate is the far node of the
attestation's own NI2I edge (`e.mandate.n`). `keri_serviceaid.envelope.envelope_for`
is C1's shared producer for exactly this: `{credential_said, credential_issuer,
credential_edges}`, the SAME function `keri_serviceaid.providers.admit.admit_grant`
(a real IPEX admit) and `providers.sealed_retrieval` (a real KEL watch) both call —
using it here, rather than re-parsing the `e` block by hand, is what keeps this page's
notion of "the mandate a program chains to" identical to every other reader's,
independent of transport. If the envelope's `credential_edges` never reached the fold
(register finding B22's shape), this column is the first place that would show up
empty rather than populated — which is why the UI test asserts it is not.

**Assemble — gathers, does not publish.** `add_rate_program_to_bundle`'s payload is
the COMPLETE set of programs for one assembly (immutability, not a UI choice — see the
template's own note: a bundle's SAID covers its content, so "adding" a program cannot
mutate an existing bundle). This page assembles every received, still-valid program
that shares the SELECTED row's mandate, mints `product_bundle` with a single NI2I edge
to that mandate, and shows the bundle's own SAID as the evidence: **the SAID is the
product's identity** — no `product_id` exists anywhere in this slice, upstream or
here.

**Publishing and completeness are OUT OF SCOPE** (parent design §10, and the
`assembly_is_not_publication` rule in the micro-app template): no "publishable"
column, no completeness indicator, no publish action. Assembling a bundle makes no
claim that the product is complete, filed, approved, or fit to sell.

Widget idiom modeled on `plugins/actuary/page.py` (form layout, banners, doer_event
subscription, the `_ensure_schema_pinned` pattern) — this page pins the two schemas it
READS (`product_mandate`, needed only to resolve edge far-node text; `rate_program_
attestation`, what it scans for) and the one it WRITES (`product_bundle`), exactly the
way `ActuaryPage` pins both its watched and its minted schema.
"""
from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QAbstractItemView, QFormLayout, QHeaderView, QLabel, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from keri import help

from locksmith.core.branding import brand, egf_local_dir
from locksmith.core.serviceaid_bridge import ServiceaidIssueDoer
from locksmith.ui import colors
from locksmith.ui.toolkit.widgets import LocksmithButton

logger = help.ogler.getLogger(__name__)

# Registry-name convention: registry_name == schema_said (Amendment C §14.1),
# mirroring cuo/page.py and actuary/page.py. Pins verified against the bundled
# schemas by tests/plugins/roles/test_pin_regression.py.
PRODUCT_MANDATE_SCHEMA_SAID = "EFYdgrOvpXpxTkVSVl6dRs1lueELnH9cqxpctqwqpVr5"
RATE_PROGRAM_ATTESTATION_SCHEMA_SAID = "EPaMxGLoFc6u1if3s367j5J547kLXKJbsztT-OE1gcHP"
PRODUCT_BUNDLE_SCHEMA_SAID = "EK4y4AX2Uo1d_Y20fyIeg3cZj09RjlvDUzkqXCf2xTL-"

#: How often the received-programs pane re-scans the registry for newly-landed
#: attestations. A poll, not a reaction to any single delivery event — matching
#: ActuaryPage's own watch tock and GateRecheckDoer's idiom (core/inbound_watch.py)
#: elsewhere in this app: whatever transport landed the credential, this notices it
#: on the next pass rather than needing to be told.
_SCAN_POLL_MS = 1000

_TABLE_HEADERS = ["Attestation", "Issuer", "Mandate", "Manifest SAID", "Version", "Action"]


class ProductDesignerPage(QWidget):
    """The designer's surface: receive attested rate programs, assemble a bundle.

    Args:
        app: the `LocksmithApplication` (needed for `app.vault`); `None` is
            accepted so the class stays constructible in isolation, mirroring
            `ActuaryPage`/`CuoMandatePage`.
    """

    def __init__(self, app: Any = None, parent=None):
        super().__init__(parent)
        self._app = app
        self._pending_listener = None  # the still-connected _on_issue_event, or None

        # received-programs state: attestation SAID -> row data
        self._received: dict[str, dict] = {}
        self._row_saids: list[str] = []          # table row index -> attestation SAID
        self._selected_said: str | None = None

        self.setObjectName("designerPage")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(48, 48, 48, 48)
        outer.setSpacing(16)

        heading = QLabel("Receive Rate Programs, Assemble a Product Bundle")
        heading.setStyleSheet(
            f"font-size: 24px; font-weight: 600; color: {colors.TEXT_PRIMARY};")
        outer.addWidget(heading)

        description = QLabel(
            "Each row below is a rate program an actuary attested, with the mandate "
            "it chains to — an edge, not a copied field. Select a program and "
            "assemble: every received program under that same mandate becomes one "
            "bundle, and the bundle's own SAID is the product's identity. "
            "Publishing and completeness are handled elsewhere."
        )
        description.setWordWrap(True)
        description.setStyleSheet(
            f"color: {colors.TEXT_SECONDARY}; font-size: 13px;")
        outer.addWidget(description)

        self._error_banner = QLabel("")
        self._error_banner.setObjectName("designerPage.errorBanner")
        self._error_banner.setWordWrap(True)
        self._error_banner.setStyleSheet(
            f"color: {colors.DANGER}; background-color: {colors.BACKGROUND_ERROR}; "
            "border-radius: 6px; padding: 8px 12px;")
        self._error_banner.setVisible(False)
        outer.addWidget(self._error_banner)

        # -- Pane 1: received programs ----------------------------------------------
        received_heading = QLabel("Received rate programs")
        received_heading.setStyleSheet(
            f"font-weight: 600; color: {colors.TEXT_PRIMARY};")
        outer.addWidget(received_heading)

        self._received_table = QTableWidget(0, len(_TABLE_HEADERS))
        self._received_table.setObjectName("designerPage.receivedPrograms")
        self._received_table.setHorizontalHeaderLabels(_TABLE_HEADERS)
        self._received_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self._received_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self._received_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        # devctl's click_table_row emits BOTH cellPressed and cellClicked; connect to
        # cellClicked (a real click fires it too) rather than the row_clicked signal
        # PaginatedTableWidget wraps -- this is a plain QTableWidget, matching
        # ActuaryPage's own plain-QListWidget idiom for its watch pane.
        self._received_table.cellClicked.connect(self._on_row_clicked)
        outer.addWidget(self._received_table)

        self._selected_label = QLabel("No program selected.")
        self._selected_label.setObjectName("designerPage.selectedProgram")
        self._selected_label.setWordWrap(True)
        self._selected_label.setStyleSheet(f"color: {colors.TEXT_SECONDARY};")
        outer.addWidget(self._selected_label)

        # -- Pane 2: assemble ---------------------------------------------------------
        assemble_heading = QLabel("Assemble")
        assemble_heading.setStyleSheet(
            f"font-weight: 600; color: {colors.TEXT_PRIMARY};")
        outer.addWidget(assemble_heading)

        form = QFormLayout()
        outer.addLayout(form)

        self._assemble = LocksmithButton("Assemble Bundle")
        self._assemble.setObjectName("designerPage.assemble")
        self._assemble.setEnabled(False)
        self._assemble.clicked.connect(self.assemble)
        form.addRow(self._assemble)

        # Why the button is disabled, when a row IS selected. Without this the
        # only feedback for "the mandate has not arrived from the CUO yet" was a
        # raw keripy failure after the click ("Failure to verify credential ...
        # chain mandate(...)"), which names nothing the user can act on.
        self._assemble_blocker = QLabel("")
        self._assemble_blocker.setObjectName("designerPage.assembleBlocker")
        self._assemble_blocker.setWordWrap(True)
        self._assemble_blocker.setStyleSheet(f"color: {colors.TEXT_SECONDARY};")
        self._assemble_blocker.setVisible(False)
        form.addRow(self._assemble_blocker)

        self._bundle_said = QLabel("")
        self._bundle_said.setObjectName("designerPage.bundleSaid")
        self._bundle_said.setWordWrap(True)
        # Hidden until a bundle is actually assembled (mirrors ActuaryPage's
        # attestedBanner / CuoMandatePage's declaredBanner) -- NOT visible-but-
        # empty like ActuaryPage's manifestSaid/workbookDigest labels, because
        # this widget's own visibility is what a caller synchronizes on
        # (`wait_for ... condition=visible`), and an always-visible label would
        # make that wait a no-op that returns before assembly ever completes.
        self._bundle_said.setVisible(False)
        form.addRow("Bundle SAID", self._bundle_said)

        outer.addStretch(1)

        # -- scan loop ----------------------------------------------------------------
        self._scan_timer = QTimer(self)
        self._scan_timer.setInterval(_SCAN_POLL_MS)
        self._scan_timer.timeout.connect(self._scan_for_programs)
        if self._app is not None and getattr(self._app, "vault", None) is not None:
            self._prepare_schemas()
            self._scan_for_programs()  # an immediate first pass -- don't make a
                                        # freshly-revealed page wait a full tock
            self._scan_timer.start()

    # -- schema plumbing ------------------------------------------------------------

    def _ensure_schema_pinned(self, hby, schema_said: str) -> None:
        """Pin `schema_said`'s schema into `hby.db.schema` if absent, reading it from
        the bundled EGF — mirrors `ActuaryPage._ensure_schema_pinned`. Needed for
        BOTH schemas this page reads (`Verifier.processCredential` must resolve a
        landing credential's schema, whatever transport delivered it) and the one
        it mints (`Credentialer.validate` resolves the schema on the issuing side
        too)."""
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

    def _prepare_schemas(self) -> None:
        for schema_said in (PRODUCT_MANDATE_SCHEMA_SAID,
                            RATE_PROGRAM_ATTESTATION_SCHEMA_SAID,
                            PRODUCT_BUNDLE_SCHEMA_SAID):
            try:
                self._ensure_schema_pinned(self._app.vault.hby, schema_said)
            except Exception:  # noqa: BLE001 -- a missing schema must not crash the
                # page; _scan_for_programs degrades to "nothing received yet",
                # which is diagnosable, rather than an unrevealed surface.
                logger.exception(
                    "designer.schema_prepare_failed schema_said=%s", schema_said)

    # -- identifier resolution --------------------------------------------------

    def _designer_hab(self, vault):
        """The identifier that assembles: whichever local hab holds this vault's
        `product_designer_role` credential -- mirrors `ActuaryPage._actuary_hab`."""
        from locksmith.plugins.product_designer.plugin import PD_ROLE_SCHEMA_SAID

        hby = vault.hby
        reger = vault.rgy.reger
        for pre, hab in hby.habs.items():
            for saider in reger.subjs.get(keys=(pre,)):
                creder = reger.creds.get(keys=(saider.qb64,))
                if creder is not None and creder.schema == PD_ROLE_SCHEMA_SAID:
                    return hab
        alias = brand().default_aid_alias or "default"
        return hby.habByName(alias)

    # -- scanning for received programs ------------------------------------------

    def _scan_for_programs(self) -> None:
        if self._app is None or getattr(self._app, "vault", None) is None:
            return
        vault = self._app.vault
        reger = vault.rgy.reger

        changed = False
        for saider in reger.schms.get(keys=(RATE_PROGRAM_ATTESTATION_SCHEMA_SAID,)):
            said = saider.qb64
            if said in self._received:
                continue
            if reger.saved.get(keys=said) is None:
                continue  # landed but not yet fully chain-verified -- not shown
            creder = reger.creds.get(keys=(said,))
            if creder is None or creder.schema != RATE_PROGRAM_ATTESTATION_SCHEMA_SAID:
                continue
            row = self._envelope_row(creder)
            if row is None:
                continue
            self._received[said] = row
            changed = True

        if changed:
            self._refresh_received_table()

        # Re-evaluate every tick, not only on `changed`: the thing the gate waits
        # for is the MANDATE's arrival, which adds no row to this table (a mandate
        # is not a rate program), so `changed` stays False for the exact event that
        # should enable the button.
        self._refresh_assemble_gate()

    def _envelope_row(self, creder) -> dict | None:
        """Read `creder`'s envelope via C1's shared producer -- the same function
        `admit_grant` and `sealed_retrieval` call -- rather than re-parsing the `e`
        block here. `verified=True` is honest: this is only ever called for a
        `said` this method's own caller just confirmed is in `reger.saved`, which
        `Verifier.saveCredential` only pins after schema + registry + (edgeless)
        chain all verify."""
        from keri_serviceaid.envelope import EnvelopeError, envelope_for

        try:
            env = envelope_for(creder.sad, verified=True)
        except EnvelopeError:
            logger.exception("designer.envelope_failed said=%s", creder.said)
            return None
        attrs = creder.sad.get("a", {}) or {}
        if not isinstance(attrs, dict):
            attrs = {}
        return {
            "attestation_said": env["credential_said"],
            "issuer": env["credential_issuer"],
            "mandate_said": env["credential_edges"].get("mandate", ""),
            "manifest_said": attrs.get("manifest_said", ""),
            "version": attrs.get("version", ""),
            "action": attrs.get("action", ""),
        }

    def _refresh_received_table(self) -> None:
        rows = list(self._received.values())
        self._row_saids = [r["attestation_said"] for r in rows]
        table = self._received_table
        table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for col, key in enumerate(
                ("attestation_said", "issuer", "mandate_said",
                 "manifest_said", "version", "action")):
                table.setItem(i, col, QTableWidgetItem(str(row.get(key, ""))))

    def _on_row_clicked(self, row: int, _col: int) -> None:
        if row < 0 or row >= len(self._row_saids):
            return
        said = self._row_saids[row]
        self._selected_said = said
        record = self._received.get(said, {})
        self._selected_label.setText(
            f"Selected: {said} — mandate {record.get('mandate_said', '')}")
        self._refresh_assemble_gate()

    # -- the assemble gate ----------------------------------------------------------

    def _mandate_blocker(self, mandate_said: str) -> str | None:
        """None when the mandate can serve as this bundle's NI2I edge node;
        otherwise a plain-language reason, naming the SAID being waited on.

        The authority is `Verifier.verifyChain` itself — the very call the issuance
        makes — so the gate cannot drift from what actually succeeds. The granular
        checks in front of it exist only to turn its single `return None` into a
        specific message, mapped to the point it would have bailed at
        (`keripy vdr/verifying.py:336-380`):

          - no body            -> the mandate has not been disclosed to us yet
          - body but not saved -> held but not indexed as a chain node, the state
                                  `_index_disclosed` exists to fix
          - no TEL / no state  -> the registry state is still out-of-band; the
                                  spec allows the state proof attached OR
                                  out-of-band, and this ecosystem chose
                                  out-of-band, so peer_sync must fetch it

        Fails toward BLOCKED: anything unreadable disables the button rather than
        letting a click produce a raw keripy traceback in the banner.
        """
        if not mandate_said:
            return ("This program's mandate edge did not resolve, so there is "
                    "nothing to assemble against.")

        vault = getattr(self._app, "vault", None)
        hab = self._designer_hab(vault) if vault is not None else None
        if vault is None or hab is None:
            return "No open vault or identifier to assemble from."

        short = f"{mandate_said[:12]}…"
        try:
            reger = vault.rgy.reger
            if reger.creds.get(keys=(mandate_said,)) is None:
                return (f"Waiting for mandate {short} to arrive from the CUO — "
                        f"it has not been disclosed to this application yet.")
            if reger.saved.get(keys=mandate_said) is None:
                return (f"Mandate {short} is held but not yet usable as a chain "
                        f"node — still being indexed.")
            if reger.tels.get(keys=mandate_said, on=0) is None:
                return (f"Waiting for mandate {short}'s registry state (its TEL) "
                        f"from the CUO — without it, issued-vs-revoked is unknown.")

            from keri.vdr import verifying
            verifier = verifying.Verifier(hby=vault.hby, reger=reger)
            if verifier.verifyChain(mandate_said, "NI2I", hab.pre) is None:
                return (f"Mandate {short} is not yet verifiable as a chain node.")
        except Exception:                   # noqa: BLE001
            logger.debug("designer.gate.unreadable said=%s", short, exc_info=True)
            return f"Cannot yet verify mandate {short}."
        return None

    def _refresh_assemble_gate(self) -> None:
        """Set the button's enabled state and the blocker text from the currently
        selected row. Called on selection AND on every scan tick, so a mandate that
        lands while a row is already selected enables the button on its own instead
        of making the user re-click."""
        said = self._selected_said
        if not said or said not in self._received:
            self._assemble.setEnabled(False)
            self._assemble_blocker.setVisible(False)
            return
        blocker = self._mandate_blocker(
            self._received[said].get("mandate_said", ""))
        self._assemble.setEnabled(blocker is None)
        self._assemble_blocker.setText(blocker or "")
        self._assemble_blocker.setVisible(blocker is not None)

    # -- assemble / issuance --------------------------------------------------------

    def assemble(self, *_qt_args) -> None:
        """Issue the `product_bundle` ACDC over every received program that shares
        the selected row's mandate, NI2I-edged to that mandate. Mirrors
        `ActuaryPage.attest`'s issuance mechanic (retire-listener / vault.extend,
        subscribing to the doer's EMITTED source name `"IssueCredentialDoer"`, the
        legacy one)."""
        self._error_banner.setVisible(False)
        if self._app is None or getattr(self._app, "vault", None) is None:
            self._show_error("No open vault — cannot assemble.")
            return
        if not self._selected_said or self._selected_said not in self._received:
            self._show_error("Select a received program first.")
            return

        vault = self._app.vault
        hab = self._designer_hab(vault)
        if hab is None:
            self._show_error("No identifier available to assemble from.")
            return

        mandate_said = self._received[self._selected_said]["mandate_said"]
        # The same gate the button is disabled by, re-checked here so a programmatic
        # call (or a click that races the scan tick) reports the plain-language
        # reason rather than a raw keripy MissingChainError from deep in issuance.
        blocker = self._mandate_blocker(mandate_said)
        if blocker is not None:
            self._show_error(blocker)
            return

        # The COMPLETE set of received programs under this mandate — not just the
        # one clicked. Assembling is not editing (the template's own note): a
        # different set of programs is a different bundle with a different SAID,
        # so this always gathers everything currently on the desk for the scope,
        # rather than growing an existing one.
        rate_program_saids = sorted(
            said for said, record in self._received.items()
            if record.get("mandate_said") == mandate_said)

        try:
            self._ensure_schema_pinned(vault.hby, PRODUCT_BUNDLE_SCHEMA_SAID)
            from keri_serviceaid.providers.issue import ensure_registry
            ensure_registry(vault.hby, hab, vault.rgy,
                            name=PRODUCT_BUNDLE_SCHEMA_SAID)
        except Exception as exc:  # noqa: BLE001
            logger.exception("designer.assemble.prepare_failed")
            self._show_error(f"Could not prepare to assemble: {exc}")
            return

        # `bundle_name` is a required, non-empty attribute (schema
        # additionalProperties:false) but this pass has no dedicated form field for
        # it (not part of the objectName contract) -- a deterministic, informative
        # default rather than an empty/placeholder string, matching the schema's
        # own framing of the name as "prose, deliberately unpatterned" rather than
        # an identifier (the bundle's SAID is that).
        bundle_name = (
            f"Bundle over {len(rate_program_saids)} program(s) — "
            f"mandate {mandate_said[:12]}…")

        payload = {
            "bundle_name": bundle_name,
            "rate_program_saids": rate_program_saids,
        }
        # NI2I: the mandate is untargeted, so I2I/DI2I are not legal here (same
        # reasoning as ActuaryPage.attest's own edge -- see that module's comment
        # and the corpus's `assembly_authority_is_admin_rooted` rule: the edge is
        # provenance, never authority).
        edges = {
            "mandate": {
                "cred_said": mandate_said,
                "schema_said": PRODUCT_MANDATE_SCHEMA_SAID,
                "operator": "NI2I",
            },
        }

        signals = vault.signals
        schema_said = PRODUCT_BUNDLE_SCHEMA_SAID

        stale = self._pending_listener
        if stale is not None:
            signals.doer_event.disconnect(stale)
            self._pending_listener = None

        def _on_issue_event(doer_name: str, event_type: str, data: dict) -> None:
            if doer_name != "IssueCredentialDoer" or data.get("schema_said") != schema_said:
                return
            if event_type == "credential_issuance_failed":
                self._retire_listener(_on_issue_event)
                self._show_error(data.get("error", "Assembly failed."))
                return
            if event_type != "credential_issued":
                return
            self._retire_listener(_on_issue_event)
            self._show_assembled(data.get("said", ""))

        self._pending_listener = _on_issue_event
        signals.doer_event.connect(_on_issue_event)

        issue_doer = ServiceaidIssueDoer(
            self._app,
            schema_said=schema_said,
            recipient=None,             # untargeted -- a bundle asserts, confers nothing
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

    def _show_assembled(self, said: str) -> None:
        # The FULL SAID, unpaired with any prefix text -- it is the product's
        # identity, not a truncated banner (see the module docstring).
        self._bundle_said.setText(said)
        self._bundle_said.setVisible(True)
