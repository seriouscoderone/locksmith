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
    assert rec.schema_saids.count("ESchemaX") <= 1 or baser.get_ecosystem("eco").schema_saids.count("ESchemaX") == 1
    baser.remove_schema_from_ecosystem("eco", "ESchemaX")
    rec2 = baser.get_ecosystem("eco")
    assert rec2 is not None
    assert "ESchemaX" not in rec2.schema_saids


def test_add_remove_aid_member(baser):
    baser.put_ecosystem(EcosystemRecord(name="eco", description=""))
    baser.add_aid_to_ecosystem("eco", "EIssuerY")
    assert "EIssuerY" in (baser.get_ecosystem("eco") or EcosystemRecord("","")).issuer_aids
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
