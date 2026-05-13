# -*- encoding: utf-8 -*-
"""DesignerBaser: per-vault LMDB index for the Designer plugin."""
from __future__ import annotations

import pytest

from locksmith.plugins.designer.db import (
    DesignerBaser,
    TemplateIndexRecord,
    OpenStateRecord,
)


@pytest.fixture
def db(tmp_path):
    db = DesignerBaser(
        name="designer-test",
        headDirPath=str(tmp_path),
        reopen=True,
    )
    yield db
    db.close()


def test_put_and_get_index_record(db):
    rec = TemplateIndexRecord(
        ref_key="draft:abc-123",
        kind="draft",
        label="My Template",
        role_kind="individual",
        validation_summary="valid",
        modified_at="2026-05-12T10:00:00Z",
        source="manual",
    )
    db.put_index(rec)
    got = db.get_index("draft:abc-123")
    assert got is not None
    assert got.label == "My Template"
    assert got.kind == "draft"


def test_list_index_records(db):
    db.put_index(TemplateIndexRecord(
        ref_key="draft:a", kind="draft", label="A", role_kind="individual",
        validation_summary="valid", modified_at="2026-05-12T10:00:00Z",
        source="manual",
    ))
    db.put_index(TemplateIndexRecord(
        ref_key="registered:E" + "A" * 43, kind="registered", label="B",
        role_kind="organization", validation_summary="valid",
        modified_at="2026-05-12T11:00:00Z", source="manual",
    ))
    recs = db.list_index()
    assert len(recs) == 2


def test_delete_index_record(db):
    db.put_index(TemplateIndexRecord(
        ref_key="draft:x", kind="draft", label="X", role_kind="individual",
        validation_summary="valid", modified_at="2026-05-12T10:00:00Z",
        source="manual",
    ))
    db.delete_index("draft:x")
    assert db.get_index("draft:x") is None


def test_open_state_round_trip(db):
    db.put_open_state(OpenStateRecord(
        last_opened_ref_key="draft:abc",
        last_opened_at="2026-05-12T10:00:00Z",
    ))
    got = db.get_open_state()
    assert got is not None
    assert got.last_opened_ref_key == "draft:abc"


def test_get_open_state_when_unset(db):
    assert db.get_open_state() is None
