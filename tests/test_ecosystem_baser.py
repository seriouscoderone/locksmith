# -*- encoding: utf-8 -*-
"""Tests for EcosystemBaser — temp LMDB, no Qt or vault required."""
from __future__ import annotations

import pytest

from locksmith.plugins.ecosystem_viewer.db import (
    AnnotationKind,
    AnnotationRecord,
    DiscoveryEvent,
    EcosystemBaser,
    EcosystemRecord,
)


@pytest.fixture
def baser():
    """Per-test EcosystemBaser backed by an LMDB temp directory."""
    db = EcosystemBaser(name="test_ecosys", temp=True, reopen=True)
    yield db
    db.close(clear=True)


def test_create_and_get_ecosystem(baser):
    rec = EcosystemRecord(
        name="insurance-ca",
        description="California insurance proxy ecosystem",
        schema_saids=["ESchemaA", "ESchemaB"],
        issuer_aids=["EIssuer1"],
        source_kind="manual",
    )
    baser.put_ecosystem(rec)
    fetched = baser.get_ecosystem("insurance-ca")
    assert fetched is not None
    assert fetched.name == "insurance-ca"
    assert fetched.description == "California insurance proxy ecosystem"
    assert fetched.schema_saids == ["ESchemaA", "ESchemaB"]
    assert fetched.issuer_aids == ["EIssuer1"]


def test_list_ecosystems_returns_all(baser):
    baser.put_ecosystem(EcosystemRecord(name="a", description="A"))
    baser.put_ecosystem(EcosystemRecord(name="b", description="B"))
    names = sorted(e.name for e in baser.list_ecosystems())
    assert names == ["a", "b"]


def test_delete_ecosystem(baser):
    baser.put_ecosystem(EcosystemRecord(name="doomed", description="x"))
    assert baser.get_ecosystem("doomed") is not None
    baser.delete_ecosystem("doomed")
    assert baser.get_ecosystem("doomed") is None


def test_add_remove_schema_member(baser):
    baser.put_ecosystem(EcosystemRecord(name="eco", description=""))
    baser.add_schema_to_ecosystem("eco", "ESchemaX")
    rec = baser.get_ecosystem("eco")
    assert rec is not None
    assert "ESchemaX" in rec.schema_saids
    # Idempotent
    baser.add_schema_to_ecosystem("eco", "ESchemaX")
    assert baser.get_ecosystem("eco").schema_saids.count("ESchemaX") == 1
    baser.remove_schema_from_ecosystem("eco", "ESchemaX")
    rec2 = baser.get_ecosystem("eco")
    assert rec2 is not None
    assert "ESchemaX" not in rec2.schema_saids


def test_add_remove_aid_member(baser):
    baser.put_ecosystem(EcosystemRecord(name="eco", description=""))
    baser.add_aid_to_ecosystem("eco", "EIssuerY")
    rec = baser.get_ecosystem("eco")
    assert rec is not None
    assert "EIssuerY" in rec.issuer_aids
    baser.remove_aid_from_ecosystem("eco", "EIssuerY")
    rec = baser.get_ecosystem("eco")
    assert rec is not None
    assert "EIssuerY" not in rec.issuer_aids


def test_membership_lookup_by_schema(baser):
    baser.put_ecosystem(EcosystemRecord(name="alpha", description=""))
    baser.put_ecosystem(EcosystemRecord(name="beta", description=""))
    baser.add_schema_to_ecosystem("alpha", "ESharedSchema")
    baser.add_schema_to_ecosystem("beta", "ESharedSchema")
    names = sorted(baser.ecosystems_for_schema("ESharedSchema"))
    assert names == ["alpha", "beta"]


def test_membership_lookup_by_aid(baser):
    baser.put_ecosystem(EcosystemRecord(name="alpha", description=""))
    baser.put_ecosystem(EcosystemRecord(name="beta", description=""))
    baser.add_aid_to_ecosystem("alpha", "EIssuerShared")
    baser.add_aid_to_ecosystem("beta", "EIssuerShared")
    names = sorted(baser.ecosystems_for_aid("EIssuerShared"))
    assert names == ["alpha", "beta"]


def test_put_get_annotation(baser):
    ann = AnnotationRecord(
        kind=AnnotationKind.SCHEMA,
        target="ESchemaSaid",
        note="This is the canonical NFL trainer cert.",
        tags=["nfl", "trainer"],
    )
    baser.put_annotation(ann)
    got = baser.get_annotation(AnnotationKind.SCHEMA, "ESchemaSaid")
    assert got is not None
    assert got.note == "This is the canonical NFL trainer cert."
    assert got.tags == ["nfl", "trainer"]


def test_history_append_and_iter(baser):
    baser.append_history(DiscoveryEvent(kind="oobi_resolved", payload={"oobi": "x"}))
    baser.append_history(DiscoveryEvent(kind="ecosystem_added", payload={"name": "y"}))
    events = list(baser.iter_history())
    assert len(events) == 2
    kinds = sorted(e.kind for e in events)
    assert kinds == ["ecosystem_added", "oobi_resolved"]


def test_put_ecosystem_overwrite_removes_stale_reverse_index(baser):
    """Regression test: overwriting an EcosystemRecord with a reduced member list
    must drop the corresponding reverse-membership entries; otherwise
    ecosystems_for_schema/ecosystems_for_aid reports stale memberships.
    """
    baser.put_ecosystem(EcosystemRecord(name="eco", schema_saids=["EA", "EB"]))
    assert sorted(baser.ecosystems_for_schema("EB")) == ["eco"]

    # Overwrite with EB removed
    rec = baser.get_ecosystem("eco")
    rec.schema_saids = ["EA"]
    baser.put_ecosystem(rec)

    assert sorted(baser.ecosystems_for_schema("EA")) == ["eco"]
    assert baser.ecosystems_for_schema("EB") == []  # must be empty, not ["eco"]


def test_put_ecosystem_overwrite_removes_stale_aid_reverse_index(baser):
    """Same as above but for issuer_aids -> aid_membership."""
    baser.put_ecosystem(EcosystemRecord(name="eco", issuer_aids=["EAID1", "EAID2"]))
    assert sorted(baser.ecosystems_for_aid("EAID2")) == ["eco"]

    rec = baser.get_ecosystem("eco")
    rec.issuer_aids = ["EAID1"]
    baser.put_ecosystem(rec)

    assert sorted(baser.ecosystems_for_aid("EAID1")) == ["eco"]
    assert baser.ecosystems_for_aid("EAID2") == []


# ---------------------------------------------------------------------------
# Permitted issuers (Stage 9 EGF overlay)
# ---------------------------------------------------------------------------


def _seed_eco(baser, name="eco", schemas=("ES1", "ES2"), aids=("EA1", "EA2")):
    baser.put_ecosystem(EcosystemRecord(
        name=name,
        schema_saids=list(schemas),
        issuer_aids=list(aids),
    ))


def test_permitted_issuers_default_empty(baser):
    _seed_eco(baser)
    assert baser.permitted_issuers_for("eco", "ES1") == []


def test_set_permitted_issuers_persists_and_dedupes(baser):
    _seed_eco(baser)
    baser.set_permitted_issuers("eco", "ES1", ["EA2", "EA1", "EA1"])
    assert baser.permitted_issuers_for("eco", "ES1") == ["EA1", "EA2"]
    rec = baser.get_ecosystem("eco")
    assert rec.permitted_issuers == {"ES1": ["EA1", "EA2"]}


def test_set_permitted_issuers_empty_list_clears_entry(baser):
    _seed_eco(baser)
    baser.set_permitted_issuers("eco", "ES1", ["EA1"])
    baser.set_permitted_issuers("eco", "ES1", [])
    assert baser.permitted_issuers_for("eco", "ES1") == []
    rec = baser.get_ecosystem("eco")
    assert "ES1" not in rec.permitted_issuers


def test_add_and_remove_permitted_issuer(baser):
    _seed_eco(baser)
    baser.add_permitted_issuer("eco", "ES1", "EA1")
    baser.add_permitted_issuer("eco", "ES1", "EA2")
    baser.add_permitted_issuer("eco", "ES1", "EA1")  # idempotent
    assert baser.permitted_issuers_for("eco", "ES1") == ["EA1", "EA2"]

    baser.remove_permitted_issuer("eco", "ES1", "EA1")
    assert baser.permitted_issuers_for("eco", "ES1") == ["EA2"]
    baser.remove_permitted_issuer("eco", "ES1", "EA1")  # idempotent
    assert baser.permitted_issuers_for("eco", "ES1") == ["EA2"]


def test_set_permitted_issuers_rejects_non_member_schema(baser):
    _seed_eco(baser)
    with pytest.raises(ValueError, match="not a member"):
        baser.set_permitted_issuers("eco", "ES_UNKNOWN", ["EA1"])


def test_set_permitted_issuers_rejects_non_member_aid(baser):
    _seed_eco(baser)
    with pytest.raises(ValueError, match="not members"):
        baser.set_permitted_issuers("eco", "ES1", ["EA1", "EA_UNKNOWN"])


def test_set_permitted_issuers_rejects_unknown_ecosystem(baser):
    with pytest.raises(KeyError):
        baser.set_permitted_issuers("nope", "ES1", [])


def test_removing_schema_drops_permitted_entry(baser):
    _seed_eco(baser)
    baser.set_permitted_issuers("eco", "ES1", ["EA1"])
    baser.remove_schema_from_ecosystem("eco", "ES1")
    rec = baser.get_ecosystem("eco")
    assert "ES1" not in rec.permitted_issuers
    assert baser.permitted_issuers_for("eco", "ES1") == []


def test_removing_aid_strips_it_from_permitted_lists(baser):
    _seed_eco(baser)
    baser.set_permitted_issuers("eco", "ES1", ["EA1", "EA2"])
    baser.set_permitted_issuers("eco", "ES2", ["EA1"])
    baser.remove_aid_from_ecosystem("eco", "EA1")
    rec = baser.get_ecosystem("eco")
    # ES1 keeps EA2; ES2 had only EA1, so the entry is removed entirely.
    assert rec.permitted_issuers == {"ES1": ["EA2"]}


def test_permitted_issuers_survives_round_trip(baser):
    """A record stored and re-fetched preserves the dict structure."""
    _seed_eco(baser)
    baser.set_permitted_issuers("eco", "ES1", ["EA2"])
    baser.set_permitted_issuers("eco", "ES2", ["EA1", "EA2"])

    fresh = baser.get_ecosystem("eco")
    assert fresh.permitted_issuers == {
        "ES1": ["EA2"],
        "ES2": ["EA1", "EA2"],
    }


def test_legacy_record_with_no_permitted_field_still_round_trips(baser):
    """An EcosystemRecord constructed without permitted_issuers (the
    field defaults to {}) round-trips cleanly — covers existing on-disk
    records written before stage 9 added the field."""
    rec = EcosystemRecord(
        name="legacy", schema_saids=["ES1"], issuer_aids=["EA1"]
    )
    baser.put_ecosystem(rec)
    fresh = baser.get_ecosystem("legacy")
    assert fresh.permitted_issuers == {}


# ---------------------------------------------------------------------------
# Stage 12: EcosystemRecord field additions
# ---------------------------------------------------------------------------


def test_new_ecosystem_record_has_default_role_fields(baser):
    """A freshly-created EcosystemRecord initializes the four new fields
    with safe defaults — empty dict / list / 1 / empty string."""
    rec = EcosystemRecord(name="eco")
    assert rec.issuer_qualification_rules == {}
    assert rec.role_names == []
    assert rec.schema_version == 1
    assert rec.governance_url == ""


def test_ecosystem_record_round_trips_new_fields(baser):
    """Setting the new fields persists across put/get."""
    rec = EcosystemRecord(
        name="eco",
        schema_saids=["ES1"],
        issuer_qualification_rules={"ES1": "state-doi"},
        role_names=["state-doi"],
        schema_version=1,
        governance_url="https://example.com/charter",
    )
    baser.put_ecosystem(rec)
    fresh = baser.get_ecosystem("eco")
    assert fresh.issuer_qualification_rules == {"ES1": "state-doi"}
    assert fresh.role_names == ["state-doi"]
    assert fresh.schema_version == 1
    assert fresh.governance_url == "https://example.com/charter"


def test_legacy_record_constructor_without_new_fields_still_works(baser):
    """An EcosystemRecord built without the new fields (the way every
    pre-Stage-12 caller does it) round-trips cleanly with defaulted
    new fields. Validates the non-breaking-change discipline."""
    rec = EcosystemRecord(name="legacy", schema_saids=["ES1"], issuer_aids=["EA1"])
    baser.put_ecosystem(rec)
    fresh = baser.get_ecosystem("legacy")
    assert fresh.issuer_qualification_rules == {}
    assert fresh.role_names == []
    assert fresh.schema_version == 1
    assert fresh.governance_url == ""
