# -*- encoding: utf-8 -*-
"""
locksmith.ui.onboarding.request_flow module

``RequestFlow`` — the controller behind ``OnboardingHomePage.on_submit``
(Task 6): the full "persona pick to presented application" pipeline, off
the page, so the page stays a pure Qt view over the vault-derived state
machine. Drives ACDC issuance end to end on the serverless serviceaid path
(Task 7's bridge doers) using the EGF request-access orchestration (Task 6's
``derive_request``/``validate_payload``/``build_attributes``/
``select_authority``) and Task 3's idempotent ``EgfSeeder``.

``submit(role_id, payload, context)`` runs, in order:

1. ``derive_request`` — resolve the role's onboarding ``RequestPlan`` (the
   application + grant credential entries, the command's payload schema,
   the schema SAIDs to seed, the registry name) from the EGF document.
2. ``validate_payload`` — fail closed against the plan's JSON-Schema.
3. The shared-context-dimension guard (B6 carry-forward): any dimension in
   ``context`` that resolves to ``None`` is treated as a validation error,
   not passed downstream to ``select_authority`` (where it would either
   silently fail to match any authority, or — pathologically — match one
   whose context dict happens to have a ``None`` value). This lives HERE
   rather than in ``OnboardingHomePage`` because ``submit()`` is the single
   choke point regardless of caller: the page's own ``submit()`` already
   guarantees no dedicated combo is left unselected (see
   ``OnboardingHomePage.submit``'s inline combo-required check), but a
   *shared* dimension's value is read straight out of the validated form
   payload via ``_dotted_get`` — a payload shape mismatch (e.g. a nested
   property path that doesn't fully resolve) is the one way a shared
   dimension could still reach here as ``None``, and this flow is the
   right place to fail closed on it since any future caller of
   ``RequestFlow.submit`` gets the guard for free.
4. ``build_attributes`` — the application credential's ACDC attribute
   block (payload plus the ``submitted_at`` autofill).
5. ``select_authority`` — the single ``Authority`` (within
   ``accept_phases``) the resulting grant credential is addressed to.
6. ``EgfSeeder.seed_for_role`` — idempotent (two-gate; see
   ``egf_seeding.py``): ensures the role's onboarding schemas, and the
   application schema's credential registry, are pinned in the vault
   BEFORE issuance, using the vault's default identifier as registry
   issuer.
7. Schedule a ``ServiceaidIssueDoer`` — self-issued application credential
   (issuer == holder == the default identifier, per the EGF's
   ``self_issued`` entry).
8. On THAT issuance's ``credential_issued`` doer_event (matched by
   ``schema_said``), schedule a ``ServiceaidGrantDoer`` chaining the fresh
   credential's SAID to the selected ``Authority``'s AID. The listener
   disconnects itself the moment it fires (see
   ``_schedule_issue_then_grant``'s ``_on_credential_issued`` closure) —
   one-shot per ``submit()`` call, so a LATER, unrelated issuance for the
   same schema (e.g. a second application after a rejected first one)
   can never silently re-trigger THIS grant.

Every ``EgfError`` subclass (``EgfDocumentError``, ``NoAuthorityError``) and
the guard's plain ``ValueError`` are caught in ``submit()`` and surfaced as
a ``request_failed`` doer_event — never raised into Qt (the page's
``submit()`` call site has no try/except of its own around ``on_submit``;
an escaping exception would crash the click handler).

Precondition: ``app.vault`` must already be open (a ``RequestFlow`` is only
ever constructed — see ``ui/window.py`` — once ``make_hoa_resolver(brand())``
resolved an EGF for an onboarding-enabled HOA vault page, which itself only
happens after a vault is open).

Date-time autofill gap (found while wiring this task, closed here): Task 5's
``SchemaFormBuilder`` never renders a ``string``+``format: date-time``
property — see its ``hidden_autofill_fields()`` — and documents "the caller
auto-fills these (client clock) at submit". Task 6's
``OnboardingHomePage.submit()`` does not call ``hidden_autofill_fields()``,
so the payload it hands to ``on_submit`` is simply missing that key. The
REAL insurance EGF's carrier ``submit_application`` payload_schema
(``docs/insurance/egf/EBSxJSWpGHcTyBYOreTj1NKBudwU5xHPA8pw003XCTDc.json`` in
the ugard repo) marks its own ``submitted_at`` (format: date-time) BOTH
required AND "Client-supplied (the command binding has no runtime clock)"
— so, unpatched, ``validate_payload`` would reject every real submission
for a field nothing ever populated. ``_autofill_date_time_fields`` below
closes this HERE (schema-driven, not dependent on a specific
``SchemaFormBuilder`` instance) so the fix also covers any future non-Qt
caller of ``RequestFlow.submit``.
"""
from __future__ import annotations

import datetime
from typing import Iterable, Optional

from keri_serviceaid.egf.documents import EgfDocument
from keri_serviceaid.egf.errors import EgfError
from keri_serviceaid.egf.onboarding import (
    RequestPlan,
    build_attributes,
    derive_request,
    select_authority,
    validate_payload,
)

from locksmith.core.branding import brand
from locksmith.core.egf_seeding import EgfSeeder
from locksmith.core.serviceaid_bridge import ServiceaidGrantDoer, ServiceaidIssueDoer


def _autofill_date_time_fields(payload_schema: dict, payload: dict) -> dict:
    """Return a COPY of ``payload`` with any top-level ``string`` +
    ``format: date-time`` property missing a value filled in with the
    current UTC instant (see the module docstring's "Date-time autofill
    gap" for why this exists). Never mutates the caller's ``payload`` dict.
    """
    properties = (payload_schema or {}).get("properties", {}) or {}
    filled = dict(payload)
    now_iso: Optional[str] = None
    for key, subschema in properties.items():
        if (
            subschema.get("type") == "string"
            and subschema.get("format") == "date-time"
            and key not in filled
        ):
            if now_iso is None:
                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            filled[key] = now_iso
    return filled


class RequestFlow:
    """Persona-pick-to-presented-application controller (Plan B Task 8).

    Args:
        app: The ``LocksmithApplication`` (its ``vault`` must already be
            open — see the module docstring's precondition).
        resolver: An ``EgfResolver``-shaped object (``resolve_micro_app``,
            ``resolve_schema``) — the same one ``make_hoa_resolver``
            produces.
        egf_doc: The ecosystem's typed ``EgfDocument``.
        accept_phases: Governance phases (e.g. ``("bootstrap",
            "production")``) forwarded to ``select_authority``.
    """

    def __init__(
        self,
        app,
        resolver,
        egf_doc: EgfDocument,
        accept_phases: Iterable[str] = ("production",),
    ):
        self.app = app
        self.resolver = resolver
        self.egf_doc = egf_doc
        self.accept_phases = tuple(accept_phases)
        self._seeder = EgfSeeder(app, resolver, egf_doc)

    # -- default identifier -------------------------------------------------

    def _default_hab(self):
        """The vault's default identifier (``brand().default_aid_alias``),
        or ``None`` if it hasn't been created yet. This is the identifier
        that issues (self-issues) the application credential and later
        frames the grant — the same alias ``bootstrap_default_environment``
        creates on first run (see ``core/bootstrapping.py``)."""
        alias = brand().default_aid_alias
        return self.app.vault.hby.habByName(alias)

    # -- seeding --------------------------------------------------------------

    def seed_all_personas(self) -> None:
        """Seed EVERY onboardable role's schemas (+ the application schema's
        registry, for whichever role's registry_name needs it) via
        ``EgfSeeder`` — idempotent, safe to call on every vault open (Task
        8's window wiring does exactly that). Uses the default identifier as
        registry issuer when one already exists; when it doesn't yet (e.g.
        a vault opened before bootstrap's identifier-creation step
        completed), seeds schemas only — ``EgfSeeder``/``LoadSchemaDoer``'s
        own documented degraded mode — and a later ``submit()`` (which
        always has a hab by then, or fails closed) retries the registry
        step."""
        hab = self._default_hab()
        issuer_aid = hab.pre if hab is not None else None
        for persona in self.egf_doc.personas():
            self._seeder.seed_for_role(persona.id, issuer_aid=issuer_aid)

    # -- submit ---------------------------------------------------------------

    def submit(self, role_id: str, payload: dict, context: dict) -> None:
        """``OnboardingHomePage.on_submit`` callback — see the module
        docstring for the full 8-step pipeline. Never raises: every
        ``EgfError`` and the context-guard's ``ValueError`` are caught and
        surfaced as a ``request_failed`` doer_event."""
        signals = self.app.vault.signals
        try:
            plan = derive_request(self.resolver, self.egf_doc, role_id)
            payload = _autofill_date_time_fields(plan.payload_schema, payload)
            validate_payload(plan, payload)

            unresolved = sorted(k for k, v in context.items() if v is None)
            if unresolved:
                raise ValueError(
                    f"context is missing a value for dimension(s) {unresolved} "
                    f"(role {role_id!r}) — cannot select an authority"
                )

            attributes = build_attributes(plan, payload)
            authority = select_authority(self.egf_doc, plan, context, self.accept_phases)

            hab = self._default_hab()
            if hab is None:
                raise ValueError(
                    "no default identifier found for this vault — cannot "
                    f"issue the application credential for role {role_id!r}"
                )

            self._seeder.seed_for_role(role_id, issuer_aid=hab.pre)
            self._schedule_issue_then_grant(plan, hab, authority, attributes)
        except (EgfError, ValueError) as exc:
            signals.emit_doer_event("RequestFlow", "request_failed", {"message": str(exc)})

    def _schedule_issue_then_grant(
        self, plan: RequestPlan, hab, authority, attributes: dict,
    ) -> None:
        """Schedule the ``ServiceaidIssueDoer`` for the application
        credential, and wire a one-shot listener on ``vault.signals.
        doer_event`` that schedules the follow-up ``ServiceaidGrantDoer``
        the moment (and only the first time) THIS issuance's
        ``credential_issued`` event lands.

        One-shot mechanism: the listener disconnects itself (``signals.
        doer_event.disconnect(_on_credential_issued)``) as its first action
        once it matches — before scheduling the grant doer — so a second,
        unrelated ``credential_issued`` event for the same schema_said
        (e.g. a later application, post-rejection) can never reach this
        closure again and double-grant.
        """
        signals = self.app.vault.signals
        schema_said = plan.registry_name  # == application_credential.schema_said

        def _on_credential_issued(doer_name: str, event_type: str, data: dict) -> None:
            if (
                doer_name != "IssueCredentialDoer"
                or event_type != "credential_issued"
                or data.get("schema_said") != schema_said
            ):
                return
            signals.doer_event.disconnect(_on_credential_issued)
            grant_doer = ServiceaidGrantDoer(
                self.app,
                credential_said=data["said"],
                recipient=authority.aid,
                hab_pre=hab.pre,
            )
            self.app.vault.extend([grant_doer])

        signals.doer_event.connect(_on_credential_issued)

        issue_doer = ServiceaidIssueDoer(
            self.app,
            schema_said=schema_said,
            recipient=hab.pre,
            attributes=attributes,
            registry_name=plan.registry_name,
        )
        self.app.vault.extend([issue_doer])
