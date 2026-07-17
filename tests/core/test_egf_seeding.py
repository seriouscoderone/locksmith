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

    def run(self, role_id: str) -> list:
        """Run one `seed_for_role` pass and return the doers scheduled during
        it (not the cumulative total across calls). Marks every scheduled
        SAID as now-present in the fake schema store, mirroring what a real
        successful `LoadSchemaDoer` run would leave behind — the mechanism
        that makes a second `run()` call idempotent."""
        self.scheduled = []
        seeder = EgfSeeder(self.app, self.resolver, self.egf_doc)
        seeder.seed_for_role(role_id)
        for doer in self.scheduled:
            said = json.loads(doer.kwargs["file_content"])["$id"]
            self.schema_store[said] = object()
        return list(self.scheduled)


@pytest.fixture
def seeder_env(monkeypatch):
    return SeederEnv(monkeypatch)


def test_seeds_missing_schemas_registry_only_for_application(seeder_env):
    scheduled = seeder_env.run("carrier")
    assert {(s.kwargs["file_content"] is not None, s.kwargs["create_registry"]) for s in scheduled} \
           == {(True, True), (True, False)}
    # The one create_registry=True call is the application schema.
    registry_call = next(s for s in scheduled if s.kwargs["create_registry"])
    assert json.loads(registry_call.kwargs["file_content"])["$id"] == APPLICATION_SAID


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
    scheduled = seeder_env.run("carrier")
    for s in scheduled:
        if s.kwargs["create_registry"]:
            continue
        assert s.kwargs["issuer_aid"] is None


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
