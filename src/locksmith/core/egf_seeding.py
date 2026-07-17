# -*- encoding: utf-8 -*-
"""EGF-driven schema + registry seeding for HOA onboarding.

`EgfSeeder` walks a role's onboarding "submit application" `RequestPlan`
(derived via `keri_serviceaid.egf.onboarding.derive_request`) and schedules a
`LoadSchemaDoer` for every schema SAID the role's onboarding flow needs that
isn't already present in the vault's `hby.db.schema` table. Idempotent via
TWO independent gates — schema presence and registry presence are checked
separately, because `LoadSchemaDoer` pins the schema BEFORE attempting
registry creation and swallows registry failures (its `load_schema_do`
catches everything), so "schema pinned" does NOT imply "registry exists":

- a plain (non-registry) schema already present in `hby.db.schema` is
  skipped outright — never redundantly re-fetched or re-loaded;
- the one schema that also needs a credential registry (the plan's own
  `registry_name`, always the self-issued *application* credential's schema —
  see `keri_serviceaid.egf.onboarding.derive_request`) is gated on
  `rgy.registryByName(...)` INDEPENDENTLY of schema presence: as long as the
  registry is missing, a `create_registry=True` doer is scheduled even when
  the schema is already pinned (a partial-failure state — e.g. an earlier
  pass ran without `issuer_aid`, pinned the schema, then failed the registry
  step). Re-pinning the schema inside the doer is idempotent, and
  `LoadSchemaDoer._create_registry` is itself `registryByName`-idempotent,
  so a lost race still cannot double-create the registry. Only when BOTH the
  schema is pinned AND the registry exists is that SAID skipped.

`make_hoa_resolver` is the brand-to-resolver bridge: it turns a `Brand`'s
`egf_*` fields (plus the sibling `egf/` bundle dir resolved by
`locksmith.core.branding.egf_local_dir`) into a ready `(EgfResolver,
EgfDocument)` pair, or `None` when the brand has no EGF pinned (the stock,
non-onboarding case) — callers never special-case a bare `Brand()` before
reaching for an EGF.
"""
import json
from typing import Optional, Tuple

from keri_serviceaid.egf.config import EgfConfig, make_resolver
from keri_serviceaid.egf.documents import EgfDocument
from keri_serviceaid.egf.onboarding import derive_request
from keri_serviceaid.egf.resolver import EgfResolver

from locksmith.core.branding import Brand, egf_local_dir
from locksmith.core.credentialing import LoadSchemaDoer


class EgfSeeder:
    """Seeds a role's onboarding schemas (and, for the application schema,
    its credential registry) into the currently open vault.

    `resolver`/`egf_doc` are the pair `make_hoa_resolver` produces — this
    class does no brand or resolver construction of its own, so it is equally
    usable against a real bundled EGF or a fake resolver/document in tests.
    """

    def __init__(self, app, resolver: EgfResolver, egf_doc: EgfDocument):
        self.app = app
        self.resolver = resolver
        self.egf_doc = egf_doc

    def seed_for_role(self, role_id: str, issuer_aid: Optional[str] = None) -> None:
        """Schedule a `LoadSchemaDoer` for each of `role_id`'s onboarding
        schemas whose seeding is incomplete, judged by two independent gates
        (see the module docstring): schema presence in `hby.db.schema` for
        every SAID, plus registry presence via `rgy.registryByName` for the
        plan's `registry_name` SAID. A pinned schema with a missing registry
        (partial failure from an earlier pass) is therefore retried with
        `create_registry=True` rather than skipped forever.

        `issuer_aid` is the identifier that will issue the application
        credential's registry. It only matters for the one schema whose SAID
        equals the derived plan's `registry_name` (`create_registry=True`) —
        `LoadSchemaDoer` only requires it once its doer actually reaches
        `_create_registry`. A caller without a role identifier yet (e.g. the
        very first seeding pass, before the user has an AID for this role)
        may omit it to seed schemas only; the registry step will then fail
        closed (`LoadSchemaDoer` raises) rather than create one with no
        issuer, which is preferable to guessing one — and a later call WITH
        `issuer_aid` retries the registry (gate 2 still sees it missing).
        """
        hby = self.app.vault.hby
        rgy = self.app.vault.rgy
        plan = derive_request(self.resolver, self.egf_doc, role_id)

        doers = []
        for said in plan.schema_saids_to_seed:
            schema_present = hby.db.schema.get(keys=(said,)) is not None

            if said == plan.registry_name:
                # Gate 2 (independent of gate 1): the application schema also
                # needs its credential registry. LoadSchemaDoer pins the
                # schema BEFORE creating the registry and swallows registry
                # failures, so schema presence alone must never gate this
                # SAID — only schema AND registry both present skip it.
                registry_present = rgy.registryByName(plan.registry_name) is not None
                if schema_present and registry_present:
                    continue  # fully seeded — idempotent no-op
                create_registry = not registry_present
            else:
                # Gate 1: plain schema — presence is the whole story.
                if schema_present:
                    continue  # already seeded — idempotent no-op
                create_registry = False

            schema_sad = self.resolver.resolve_schema(said)
            # as-parsed rule: `schema_sad` is the resolver-verified dict in its
            # as-parsed field order (json.loads/json.dumps both preserve dict
            # insertion order). Re-serializing it here must NOT re-sort keys —
            # doing so could change the field order the SAID was derived over,
            # and the SAID `LoadSchemaDoer` re-derives from these bytes (via
            # `scheming.Schemer`) would then no longer match `said`.
            file_content = json.dumps(schema_sad).encode("utf-8")

            doer = LoadSchemaDoer(
                app=self.app,
                file_content=file_content,
                create_registry=create_registry,
                issuer_aid=issuer_aid if create_registry else None,
            )
            doers.append(doer)

        if doers:
            # Matches the established UI scheduling seam (see
            # `locksmith.ui.vault.credentials.schema.add.AddSchemaDialog.
            # _create_load_schema_doer`): `Vault` is itself a `DoDoer` running
            # inside the vault's `QtTask`/`Doist`, so extending it — not the
            # `QtTask` wrapper — is how a freshly built doer joins the running
            # vault.
            self.app.vault.extend(doers)


def make_hoa_resolver(brand: Brand) -> Optional[Tuple[EgfResolver, EgfDocument]]:
    """Build `(resolver, document)` for `brand`'s pinned EGF, or `None` when
    the brand has no EGF pinned — the stock `Brand()` default, or any
    non-onboarding brand.toml that simply omits `[egf]`.

    Never constructs an `EgfConfig`/resolver in that case, so a stock brand
    can never hit `make_resolver`'s `local` + no-`local_dir` `ValueError`.
    """
    if not brand.egf_document_said:
        return None

    cfg = EgfConfig(
        source=brand.egf_source,
        document_said=brand.egf_document_said,
        accept_phases=brand.egf_accept_phases,
        local_dir=egf_local_dir(),
    )
    resolver = make_resolver(cfg)
    egf_doc = resolver.resolve_egf(brand.egf_document_said)
    return resolver, egf_doc
