"""Tests for `locksmith.core.egf_seeding` (Plan B Task 3).

`EgfSeeder.seed_for_role` is exercised against a `MagicMock` app/hby and a
fake resolver built on `keri_serviceaid`'s own `fixture_egf()` (the same
fixture `keri_serviceaid/tests/egf/test_onboarding.py` uses for its "carrier"
role scenario) — so the schema SAIDs / registry-name relationship here is the
same one `derive_request` guarantees for real EGF documents. The scheduling
seam under test is the `LoadSchemaDoer` construction call itself: `locksmith.
core.egf_seeding.LoadSchemaDoer` is monkeypatched to a capturing fake, and
each captured call's `kwargs` is what the assertions read. (`app.vault.extend`
is the *other* real seam — see `test_schedules_via_vault_extend` — but the
`LoadSchemaDoer` kwargs are the one this suite pins its behavioral
assertions to, per the "pick one seam" guidance.)

`make_hoa_resolver` gets both a pure unit test (stock `Brand()` -> None) and
a runtime test against a real tmp brand.json + egf/ bundle dir (carried
forward from Task B2), proving `egf_local_dir()` + `make_hoa_resolver()`
actually resolve a bundled EGF end to end, not just against mocks.
"""
import json
from unittest.mock import MagicMock

import pytest

from keri_serviceaid.egf.documents import EgfDocument
from keri_serviceaid.tests.egf.fixtures.make_fixture_egf import fixture_egf

from locksmith.core import branding
from locksmith.core.egf_seeding import EgfSeeder, make_hoa_resolver

GRANT_SAID = "E" + "L" * 43       # "lic" credential's schema_said in fixture_egf()
APPLICATION_SAID = "E" + "P" * 43  # "app" credential's schema_said in fixture_egf()
MICRO_APP_SAID = "E" + "M" * 43

MICRO_APP = {
    "d": MICRO_APP_SAID,
    "commands": [
        {
            "id": "submit_application",
            "payload_schema": {"type": "object", "properties": {}, "required": []},
        }
    ],
}


def _schema_sad(said: str) -> dict:
    """A minimal, resolver-shaped schema SAD for `said` (fake content — only
    the `$id` round-trip through `EgfSeeder`'s file_content matters here)."""
    return {"$id": said, "title": f"schema {said[:8]}", "version": "1.0.0", "type": "object"}


class FakeResolver:
    """Stands in for `EgfResolver`: only the two methods `derive_request` /
    `EgfSeeder` actually call."""

    def __init__(self):
        self._schemas = {
            GRANT_SAID: _schema_sad(GRANT_SAID),
            APPLICATION_SAID: _schema_sad(APPLICATION_SAID),
        }

    def resolve_micro_app(self, said):
        assert said == MICRO_APP_SAID
        return MICRO_APP

    def resolve_schema(self, said):
        return self._schemas[said]


class SeederEnv:
    """Concrete test harness: a MagicMock app/hby wired to a fake `hby.db.
    schema` store, plus a monkeypatched `LoadSchemaDoer` that captures its
    constructor kwargs instead of building a real doer."""

    def __init__(self, monkeypatch):
        _, sad = fixture_egf()
        self.egf_doc = EgfDocument.from_sad(sad)
        self.resolver = FakeResolver()
        self.app = MagicMock(name="app")
        self.schema_store: dict[str, object] = {}
        self.registry_store: dict[str, object] = {}
        self.scheduled: list = []

        self.app.vault.hby.db.schema.get.side_effect = (
            lambda keys: self.schema_store.get(keys[0])
        )
        self.app.vault.rgy.registryByName.side_effect = (
            lambda name: self.registry_store.get(name)
        )

        def _fake_load_schema_doer(*args, **kwargs):
            fake_doer = MagicMock(name="LoadSchemaDoer")
            fake_doer.kwargs = kwargs
            self.scheduled.append(fake_doer)
            return fake_doer

        monkeypatch.setattr(
            "locksmith.core.egf_seeding.LoadSchemaDoer", _fake_load_schema_doer
        )

    def run(self, role_id: str, issuer_aid=None) -> list:
        """Run one `seed_for_role` pass and return the doers scheduled during
        it (not the cumulative total across calls). Marks every scheduled
        SAID as now-present in the fake schema store — and, for a
        `create_registry=True` doer, the registry as now-existing — mirroring
        what a real successful `LoadSchemaDoer` run would leave behind: the
        mechanism that makes a second `run()` call idempotent."""
        self.scheduled = []
        seeder = EgfSeeder(self.app, self.resolver, self.egf_doc)
        seeder.seed_for_role(role_id, issuer_aid=issuer_aid)
        for doer in self.scheduled:
            said = json.loads(doer.kwargs["file_content"])["$id"]
            self.schema_store[said] = object()
            if doer.kwargs["create_registry"]:
                self.registry_store[said] = object()
        return list(self.scheduled)


@pytest.fixture
def seeder_env(monkeypatch):
    return SeederEnv(monkeypatch)


def test_seeds_missing_schemas_registry_only_for_application(seeder_env):
    issuer = "E" + "I" * 43
    scheduled = seeder_env.run("carrier", issuer_aid=issuer)
    assert {(s.kwargs["file_content"] is not None, s.kwargs["create_registry"]) for s in scheduled} \
           == {(True, True), (True, False)}
    # The one create_registry=True call is the application schema.
    registry_call = next(s for s in scheduled if s.kwargs["create_registry"])
    assert json.loads(registry_call.kwargs["file_content"])["$id"] == APPLICATION_SAID


def test_seeds_schema_only_when_no_issuer_aid_yet(seeder_env):
    """The acceptance-demo defect (live log: 'LoadSchemaDoer failed: Issuer
    AID is required for registry creation'): the very first seeding pass,
    before the vault's default identifier exists, must degrade to a
    schema-only seed for the registry-bearing SAID rather than schedule a
    doer doomed to fail. Both schemas are still pinned (create_registry is
    False for BOTH, never None-issuer + create_registry=True)."""
    scheduled = seeder_env.run("carrier")  # issuer_aid defaults to None
    assert len(scheduled) == 2
    assert {s.kwargs["create_registry"] for s in scheduled} == {False}
    assert all(s.kwargs["issuer_aid"] is None for s in scheduled)


def test_second_run_with_issuer_aid_retries_registry_after_schema_only_pass(seeder_env):
    """Two-gate retry, end to end: a first pass with no issuer_aid pins both
    schemas but creates no registry; a SECOND pass, now with an issuer_aid,
    must retry ONLY the registry-bearing SAID (the plain schema is already
    pinned and needs nothing further)."""
    first = seeder_env.run("carrier")
    assert len(first) == 2
    assert all(not s.kwargs["create_registry"] for s in first)

    issuer = "E" + "I" * 43
    second = seeder_env.run("carrier", issuer_aid=issuer)
    assert len(second) == 1
    (doer,) = second
    assert doer.kwargs["create_registry"] is True
    assert doer.kwargs["issuer_aid"] == issuer
    assert json.loads(doer.kwargs["file_content"])["$id"] == APPLICATION_SAID


def test_second_run_is_noop(seeder_env):
    first = seeder_env.run("carrier")
    assert len(first) == 2
    assert seeder_env.run("carrier") == []


def test_schedules_via_vault_extend(seeder_env):
    """Corroborating check on the other real seam: newly scheduled doers are
    handed to `app.vault.extend`, matching `AddSchemaDialog.
    _create_load_schema_doer`'s `self.app.vault.extend([doer])` pattern."""
    scheduled = seeder_env.run("carrier")
    seeder_env.app.vault.extend.assert_called_once()
    (extended_doers,), _ = seeder_env.app.vault.extend.call_args
    assert list(extended_doers) == scheduled


def test_seed_for_role_passes_issuer_aid_only_for_registry_schema(seeder_env):
    issuer = "E" + "I" * 43
    scheduled = seeder_env.run("carrier", issuer_aid=issuer)
    registry_call = next(s for s in scheduled if s.kwargs["create_registry"])
    assert registry_call.kwargs["issuer_aid"] == issuer  # positive propagation
    for s in scheduled:
        if s.kwargs["create_registry"]:
            continue
        assert s.kwargs["issuer_aid"] is None


def test_partial_failure_retry_schedules_registry_despite_pinned_schema(seeder_env):
    """The Important fix: LoadSchemaDoer pins the schema BEFORE registry
    creation and swallows registry failures, so 'schema pinned, registry
    missing' is a reachable partial-failure state. A later seed_for_role
    call (now WITH an issuer_aid) must still schedule the create_registry
    doer — schema presence alone must not gate the registry SAID."""
    issuer = "E" + "I" * 43
    # Simulate the aftermath of a failed first pass: both schemas pinned,
    # but no registry was ever created.
    seeder_env.schema_store[GRANT_SAID] = object()
    seeder_env.schema_store[APPLICATION_SAID] = object()

    scheduled = seeder_env.run("carrier", issuer_aid=issuer)
    assert len(scheduled) == 1
    (doer,) = scheduled
    assert doer.kwargs["create_registry"] is True
    assert doer.kwargs["issuer_aid"] == issuer
    assert json.loads(doer.kwargs["file_content"])["$id"] == APPLICATION_SAID


def test_fully_seeded_run_schedules_nothing(seeder_env):
    """Both gates satisfied — schemas pinned AND registryByName returns a
    registry — nothing is scheduled."""
    seeder_env.schema_store[GRANT_SAID] = object()
    seeder_env.schema_store[APPLICATION_SAID] = object()
    seeder_env.registry_store[APPLICATION_SAID] = object()  # registry_name == application schema SAID

    assert seeder_env.run("carrier", issuer_aid="E" + "I" * 43) == []


# ---------------------------------------------------------------------------
# Apply-mode seeding (Task 10, HOA #4): schema-only, no registry ever.
# ---------------------------------------------------------------------------

class ApplyModeResolver:
    """Stands in for `EgfResolver` for the apply-mode role: only
    `resolve_schema` is ever called (no micro-app to resolve — apply-mode
    has no form)."""

    def __init__(self, schema_said: str):
        self._schemas = {schema_said: _schema_sad(schema_said)}

    def resolve_micro_app(self, said):
        raise AssertionError("apply-mode seeding must never resolve a micro-app")

    def resolve_schema(self, said):
        return self._schemas[said]


class ApplyModeSeederEnv:
    """Mirrors `SeederEnv` above, but for an apply-mode EGF (one persona,
    "actuary", no chained application — see `apply_mode_egf`)."""

    def __init__(self, monkeypatch):
        from keri_serviceaid.tests.egf.fixtures.make_fixture_egf import (
            ACTUARY_ROLE_SCHEMA_SAID, apply_mode_egf)
        self.schema_said = ACTUARY_ROLE_SCHEMA_SAID
        self.egf_doc = EgfDocument.from_sad(
            apply_mode_egf({"grant_credential_id": "actuary_role"}))
        self.resolver = ApplyModeResolver(self.schema_said)
        self.app = MagicMock(name="app")
        self.schema_store: dict[str, object] = {}
        self.scheduled: list = []

        self.app.vault.hby.db.schema.get.side_effect = (
            lambda keys: self.schema_store.get(keys[0])
        )

        def _fake_load_schema_doer(*args, **kwargs):
            fake_doer = MagicMock(name="LoadSchemaDoer")
            fake_doer.kwargs = kwargs
            self.scheduled.append(fake_doer)
            return fake_doer

        monkeypatch.setattr(
            "locksmith.core.egf_seeding.LoadSchemaDoer", _fake_load_schema_doer
        )

    def run(self, role_id: str = "actuary", issuer_aid=None) -> list:
        self.scheduled = []
        seeder = EgfSeeder(self.app, self.resolver, self.egf_doc)
        seeder.seed_for_role(role_id, issuer_aid=issuer_aid)
        for doer in self.scheduled:
            said = json.loads(doer.kwargs["file_content"])["$id"]
            self.schema_store[said] = object()
        return list(self.scheduled)


@pytest.fixture
def apply_mode_seeder_env(monkeypatch):
    return ApplyModeSeederEnv(monkeypatch)


def test_apply_mode_seeds_schema_only_no_registry(apply_mode_seeder_env):
    """The core Task 10 assertion: an apply-mode role's grant schema is
    pinned, and create_registry is False -- never True, even though an
    issuer_aid IS supplied (unlike the form-mode branch, there is no
    application schema here to ever need one)."""
    scheduled = apply_mode_seeder_env.run(issuer_aid="E" + "I" * 43)
    assert len(scheduled) == 1
    (doer,) = scheduled
    assert doer.kwargs["create_registry"] is False
    assert doer.kwargs["issuer_aid"] is None
    assert json.loads(doer.kwargs["file_content"])["$id"] == apply_mode_seeder_env.schema_said


def test_apply_mode_skips_already_pinned_schema(apply_mode_seeder_env):
    """Idempotent: a second pass, with the schema now pinned, schedules
    nothing."""
    first = apply_mode_seeder_env.run()
    assert len(first) == 1
    assert apply_mode_seeder_env.run() == []


def test_apply_mode_never_resolves_a_micro_app(apply_mode_seeder_env):
    """Sanity check on the resolver seam itself: apply-mode seeding must
    never touch resolve_micro_app (ApplyModeResolver raises if it does) --
    proves seed_for_role branches BEFORE ever calling derive_request (which
    would resolve a micro-app for a form-mode role)."""
    apply_mode_seeder_env.run()  # must not raise


def test_apply_mode_schedules_via_vault_extend(apply_mode_seeder_env):
    scheduled = apply_mode_seeder_env.run()
    apply_mode_seeder_env.app.vault.extend.assert_called_once()
    (extended_doers,), _ = apply_mode_seeder_env.app.vault.extend.call_args
    assert list(extended_doers) == scheduled


def test_make_hoa_resolver_none_for_stock_brand():
    from locksmith.core.branding import Brand
    assert make_hoa_resolver(Brand()) is None


def test_make_hoa_resolver_resolves_bundled_egf_from_real_brand_json(tmp_path, monkeypatch):
    """Runtime (not mocked) carry-forward from Task B2: a real tmp brand.json
    + sibling egf/ dir, resolved through the actual LOCKSMITH_BRAND_CONFIG env
    injection + egf_local_dir() + make_resolver() chain."""
    said, sad = fixture_egf()

    egf_dir = tmp_path / "egf"
    egf_dir.mkdir()
    (egf_dir / f"{said}.json").write_text(json.dumps(sad))

    brand_json = tmp_path / "brand.json"
    brand_json.write_text(json.dumps({
        "id": "test-hoa",
        "egf": {
            "source": "local",
            "document_said": said,
            "accept_phases": ["bootstrap", "production"],
        },
        "onboarding": {"enabled": True},
    }))

    monkeypatch.setenv(branding.BRAND_CONFIG_ENV_VAR, str(brand_json))
    branding._reset_cache_for_tests()
    try:
        b = branding.brand()
        assert b.egf_document_said == said

        result = make_hoa_resolver(b)
        assert result is not None
        resolver, egf_doc = result
        assert egf_doc.said == said
        # A working resolver: resolving the same SAID again round-trips to
        # the identical (cached) verified document.
        assert resolver.resolve_egf(said) is egf_doc
    finally:
        branding._reset_cache_for_tests()
