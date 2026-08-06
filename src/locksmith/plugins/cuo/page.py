# -*- encoding: utf-8 -*-
"""
locksmith.plugins.cuo.page module — the CUO mandate-declaration surface.

Design §6's form: line of business / jurisdiction / coverages / effective window /
thesis -> the `declare_product_mandate` command, minting a `product_mandate` ACDC.

**Untargeted by construction.** Design spec Amendment C §14.6: "CUO HOA declare_mandate
-> iss(vcdig=mandate SAID) + ixn carrying SealEvent(...) -> (no push)". A mandate is
"addressed to nobody and requesting nothing" (the schema's own description, quoting the
ACDC spec's Untargeted Attribute Section) -- consumers find it by watching this
identifier's own KEL, not by being sent it. `issue_credential`'s `recipient=None` is what
makes the ACDC's `a` block carry no `i` (see `keri.vc.proving.credential`: `if recipient
is not None: subject['i'] = recipient`) -- untargeted is the ABSENCE of a recipient
argument, not a separate code path.

**Issuance mechanic.** Follows the SAME retire-listener / `vault.extend` pattern
`RequestFlow._schedule_issue_then_grant` uses (`ui/onboarding/request_flow.py:319`) for
scheduling a `ServiceaidIssueDoer` and picking up its result off the vault's
`doer_event` bus -- BUT WITHOUT the follow-up `ServiceaidGrantDoer` that flow chains:
that doer frames and delivers an IPEX grant to a specific recipient, and a mandate has
none. Do not add one; an untargeted credential has nothing to grant.

Subscribes to the doer's EMITTED source name, which is the LEGACY one --
`"IssueCredentialDoer"`, not `"ServiceaidIssueDoer"`.
`keri_serviceaid.providers.issue_credential` stamps this name onto every
`sink.on_event` call (both the `credential_issued` success path and the
`credential_issuance_failed` except-path -- `keri_serviceaid/providers/issue.py:151`
and `serviceaid_bridge.py:249-258`) so the pre-existing UI vocabulary
(`IssueCredentialDialog._on_doer_event`) keeps working unmodified. A listener
subscribed to the doer CLASS's real name, `ServiceaidIssueDoer`, receives nothing,
silently.

Widget idiom modeled on `ui/vault/credentials/received/list.py` (page layout, palette)
and `ui/onboarding/form_builder.py`/`home_page.py` (QFormLayout rows, the persistent
hidden-until-shown error/success banner styled with `colors.DANGER`/`BACKGROUND_ERROR`
and `colors.SUCCESS_TEXT`/`BACKGROUND_SUCCESS`).

Does not compute or display any premium, and renders no rate table -- out of scope
since the parent design; Excel is the rate UI (owner ruling).
"""
from __future__ import annotations

import json
from typing import Any

from PySide6.QtWidgets import QFormLayout, QLabel, QVBoxLayout, QWidget

from keri import help

from locksmith.core.branding import brand, egf_local_dir
from locksmith.core.serviceaid_bridge import ServiceaidIssueDoer
from locksmith.ui import colors
from locksmith.ui.toolkit.widgets import LocksmithButton
from locksmith.ui.toolkit.widgets.fields import LocksmithLineEdit

logger = help.ogler.getLogger(__name__)

# Registry-name convention: registry_name == schema_said (Amendment C §14.1).
# Pin verified against the bundled schema by
# tests/plugins/roles/test_pin_regression.py; the schema's own $id is the
# source of truth (brands/usurance/egf/EFYdgrOvpXpxTkVSVl6dRs1lueELnH9cqxpctqwqpVr5.json).
PRODUCT_MANDATE_SCHEMA_SAID = "EFYdgrOvpXpxTkVSVl6dRs1lueELnH9cqxpctqwqpVr5"


class CuoMandatePage(QWidget):
    """The CUO's mandate-declaration surface.

    Args:
        app: the `LocksmithApplication` (needed at submit time for
            `app.vault`); `None` is accepted so the class stays constructible
            in isolation (e.g. a stray `CuoMandatePage()`), but `submit()`
            surfaces a clear error rather than crashing when there is none.
    """

    def __init__(self, app: Any = None, parent=None):
        super().__init__(parent)
        self._app = app
        self._pending_listener = None  # the still-connected _on_issue_event, or None

        self.setObjectName("cuoMandatePage")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(48, 48, 48, 48)
        outer.setSpacing(16)

        heading = QLabel("Declare a Product Mandate")
        heading.setStyleSheet(
            f"font-size: 24px; font-weight: 600; color: {colors.TEXT_PRIMARY};")
        outer.addWidget(heading)

        description = QLabel(
            "This line of business, this jurisdiction, these coverages — go. "
            "An untargeted declaration, addressed to nobody: a reader finds it "
            "by watching this identifier's own log, never by being sent it."
        )
        description.setWordWrap(True)
        description.setStyleSheet(
            f"color: {colors.TEXT_SECONDARY}; font-size: 13px;")
        outer.addWidget(description)

        self._error_banner = QLabel("")
        self._error_banner.setObjectName("cuoMandatePage.errorBanner")
        self._error_banner.setWordWrap(True)
        self._error_banner.setStyleSheet(
            f"color: {colors.DANGER}; background-color: {colors.BACKGROUND_ERROR}; "
            "border-radius: 6px; padding: 8px 12px;")
        self._error_banner.setVisible(False)
        outer.addWidget(self._error_banner)

        self._declared_banner = QLabel("")
        self._declared_banner.setObjectName("cuoMandatePage.declaredBanner")
        self._declared_banner.setWordWrap(True)
        self._declared_banner.setStyleSheet(
            f"color: {colors.SUCCESS_TEXT}; background-color: {colors.BACKGROUND_SUCCESS}; "
            "border-radius: 6px; padding: 8px 12px;")
        self._declared_banner.setVisible(False)
        outer.addWidget(self._declared_banner)

        form = QFormLayout()
        outer.addLayout(form)

        self._line_of_business = LocksmithLineEdit(
            placeholder_text="e.g. auto, property, casualty")
        self._line_of_business.setObjectName("cuoMandatePage.lineOfBusiness")
        form.addRow("Line of business", self._line_of_business)

        self._jurisdiction = LocksmithLineEdit(placeholder_text="e.g. UT")
        self._jurisdiction.setObjectName("cuoMandatePage.jurisdiction")
        form.addRow("Jurisdiction (US state)", self._jurisdiction)

        self._coverages = LocksmithLineEdit(placeholder_text="e.g. BI,PD")
        self._coverages.setObjectName("cuoMandatePage.coverages")
        form.addRow("Coverages (comma-separated)", self._coverages)

        self._effective_window = LocksmithLineEdit(
            placeholder_text="YYYY-MM-DD/YYYY-MM-DD")
        self._effective_window.setObjectName("cuoMandatePage.effectiveWindow")
        form.addRow("Effective window", self._effective_window)

        self._thesis = LocksmithLineEdit(
            placeholder_text="One sentence of business intent")
        self._thesis.setObjectName("cuoMandatePage.thesis")
        form.addRow("Thesis", self._thesis)

        for field in self._fields():
            field.textChanged.connect(self._update_submit_state)

        self._submit = LocksmithButton("Declare Mandate")
        self._submit.setObjectName("cuoMandatePage.submit")
        # Checkable (not just enabled) so devctl's `is_checked` probe reads a
        # real, live "every field is non-empty" signal — see the task brief's
        # objectName contract.
        self._submit.setCheckable(True)
        self._submit.clicked.connect(self.submit)
        outer.addWidget(self._submit)
        outer.addStretch(1)

        self._update_submit_state()

    # -- validity -------------------------------------------------------------

    def _fields(self) -> tuple[LocksmithLineEdit, ...]:
        return (self._line_of_business, self._jurisdiction, self._coverages,
                self._effective_window, self._thesis)

    def _update_submit_state(self, *_args: Any) -> None:
        valid = all(f.text().strip() for f in self._fields())
        self._submit.setEnabled(valid)
        self._submit.setChecked(valid)

    # -- payload ----------------------------------------------------------------

    def _build_payload(self) -> dict:
        """Turn the form's free-text fields into `declare_product_mandate`'s
        payload shape (micro-app-template.json's `payload_schema`):
        `line_of_business` (lowercase, matches the closed enum), `jurisdiction`
        (`US-<XX>`, matching the schema's `^US-[A-Z]{2}$` pattern — the field
        holds just the state code), `coverages` (split on comma, upper-cased,
        matching `^[A-Z0-9][A-Z0-9-]*$`), `window_opens`/`window_closes` (split
        on `/`), `thesis` (verbatim)."""
        coverages = [c.strip().upper() for c in self._coverages.text().split(",")
                     if c.strip()]
        window_opens, _, window_closes = self._effective_window.text().partition("/")
        jurisdiction = self._jurisdiction.text().strip().upper()
        if jurisdiction and not jurisdiction.startswith("US-"):
            jurisdiction = f"US-{jurisdiction}"
        return {
            "line_of_business": self._line_of_business.text().strip().lower(),
            "jurisdiction": jurisdiction,
            "coverages": coverages,
            "window_opens": window_opens.strip(),
            "window_closes": window_closes.strip(),
            "thesis": self._thesis.text().strip(),
        }

    # -- identifier resolution --------------------------------------------------

    def _cuo_hab(self):
        """The identifier that declares this mandate: whichever local hab
        holds this vault's `cuo_role` credential (the same fact the plugin's
        own gate reveals this page on), falling back to the brand's default
        onboarding identifier when none is found (defensive; the gate should
        already guarantee one exists by the time this page is visible at
        all)."""
        from locksmith.plugins.cuo.plugin import CUO_ROLE_SCHEMA_SAID

        vault = self._app.vault
        hby = vault.hby
        reger = vault.rgy.reger
        for pre, hab in hby.habs.items():
            for saider in reger.subjs.get(keys=(pre,)):
                creder = reger.creds.get(keys=(saider.qb64,))
                if creder is not None and creder.schema == CUO_ROLE_SCHEMA_SAID:
                    return hab
        alias = brand().default_aid_alias or "default"
        return hby.habByName(alias)

    def _ensure_mandate_schema_pinned(self, hby) -> None:
        """Pin `product_mandate`'s schema into `hby.db.schema` if it is not
        there already. `Credentialer.validate` (called from `create()`)
        resolves the schema on the ISSUING side too — the same requirement
        the role-gate credentials already satisfy via the EGF bundle; this
        mandate schema is bundled the same way
        (`brands/usurance/egf/<said>.json`), just not needed by any GATE, so
        nothing else in the boot sequence pins it ahead of time."""
        from keri.core import scheming
        from keri.kering import Kinds

        if hby.db.schema.get(keys=(PRODUCT_MANDATE_SCHEMA_SAID,)) is not None:
            return
        egf_dir = egf_local_dir()
        if egf_dir is None:
            raise RuntimeError(
                "no bundled EGF directory for this brand — cannot resolve "
                "the mandate schema")
        schema_path = egf_dir / f"{PRODUCT_MANDATE_SCHEMA_SAID}.json"
        if not schema_path.is_file():
            raise RuntimeError(
                f"mandate schema not bundled at {schema_path}")
        sad = json.loads(schema_path.read_text())
        schemer = scheming.Schemer(sed=sad, kind=Kinds.json)
        if schemer.said != PRODUCT_MANDATE_SCHEMA_SAID:
            raise RuntimeError("bundled mandate schema does not verify")
        hby.db.schema.pin(keys=(schemer.said,), val=schemer)

    # -- submit / issuance --------------------------------------------------------

    def submit(self, *_qt_args) -> None:
        """Issue the `product_mandate` ACDC declared by the form. See the
        module docstring for the issuance mechanic and why there is no
        grant step."""
        self._error_banner.setVisible(False)
        if self._app is None or getattr(self._app, "vault", None) is None:
            self._show_error("No open vault — cannot declare a mandate.")
            return

        vault = self._app.vault
        hab = self._cuo_hab()
        if hab is None:
            self._show_error("No identifier available to declare a mandate from.")
            return

        try:
            self._ensure_mandate_schema_pinned(vault.hby)
            from keri_serviceaid.providers.issue import ensure_registry
            ensure_registry(vault.hby, hab, vault.rgy,
                            name=PRODUCT_MANDATE_SCHEMA_SAID)
        except Exception as exc:                        # noqa: BLE001
            logger.exception("cuo.mandate.prepare_failed")
            self._show_error(f"Could not prepare to declare the mandate: {exc}")
            return

        payload = self._build_payload()
        signals = vault.signals
        schema_said = PRODUCT_MANDATE_SCHEMA_SAID

        stale = self._pending_listener
        if stale is not None:
            signals.doer_event.disconnect(stale)
            self._pending_listener = None

        def _on_issue_event(doer_name: str, event_type: str, data: dict) -> None:
            if doer_name != "IssueCredentialDoer" or data.get("schema_said") != schema_said:
                return
            if event_type == "credential_issuance_failed":
                self._retire_listener(_on_issue_event)
                self._show_error(data.get("error", "Mandate declaration failed."))
                return
            if event_type != "credential_issued":
                return
            self._retire_listener(_on_issue_event)
            self._show_declared(data.get("said", ""))

        self._pending_listener = _on_issue_event
        signals.doer_event.connect(_on_issue_event)

        issue_doer = ServiceaidIssueDoer(
            self._app,
            schema_said=schema_said,
            recipient=None,             # untargeted — see module docstring
            attributes=payload,
            registry_name=schema_said,
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

    def _show_declared(self, said: str) -> None:
        self._declared_banner.setText(
            f"Mandate declared ({said[:12]}…)." if said else "Mandate declared.")
        self._declared_banner.setVisible(True)
