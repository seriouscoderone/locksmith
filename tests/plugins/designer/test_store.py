# -*- encoding: utf-8 -*-
"""TemplateStore: file-on-disk read/write/list for micro-app templates."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from locksmith.plugins.designer.store import (
    TemplateStore,
    TemplateRef,
    TemplateNotFound,
    TemplateAlreadyExists,
)


VALID_FIXTURE = {
    "d": "E" + "A" * 43,
    "spec_version": "micro-app-template/0.1",
    "header": {"label": "Test Template", "description": "test", "version": "1.0"},
    "role": {"id": "r1", "name": "tester", "kind": "individual"},
    "credentials": {"imports": [], "exports": []},
    "commands": [],
    "aggregates": [],
    "reactions": [],
    "workflows": [],
    "projections": [],
    "rules": [],
}

VALID_METADATA = {"ecosystems": [], "tags": [], "notes": ""}


@pytest.fixture
def store(tmp_path):
    return TemplateStore(root=tmp_path)


def test_list_empty_workspace(store):
    assert store.list_templates() == []


def test_save_and_load_draft(store):
    ref = store.save_draft(local_id="abc-123", doc=VALID_FIXTURE, metadata=VALID_METADATA)
    assert ref.kind == "draft"
    assert ref.local_id == "abc-123"
    listed = store.list_templates()
    assert len(listed) == 1
    assert listed[0].local_id == "abc-123"

    loaded_doc, loaded_meta = store.load(ref)
    assert loaded_doc["header"]["label"] == "Test Template"
    assert loaded_meta == VALID_METADATA


def test_save_registered_uses_said_as_dir(store):
    said = VALID_FIXTURE["d"]
    ref = store.save_registered(said=said, doc=VALID_FIXTURE, metadata=VALID_METADATA)
    assert ref.kind == "registered"
    assert ref.said == said
    target = store.root / "templates" / "registered" / said / "micro-app-template.json"
    assert target.exists()
    assert json.loads(target.read_text())["d"] == said


def test_load_missing_raises(store):
    ref = TemplateRef(kind="draft", local_id="does-not-exist", said=None)
    with pytest.raises(TemplateNotFound):
        store.load(ref)


def test_save_registered_twice_raises(store):
    said = VALID_FIXTURE["d"]
    store.save_registered(said=said, doc=VALID_FIXTURE, metadata=VALID_METADATA)
    with pytest.raises(TemplateAlreadyExists):
        store.save_registered(said=said, doc=VALID_FIXTURE, metadata=VALID_METADATA)


def test_save_registered_with_overwrite(store):
    said = VALID_FIXTURE["d"]
    store.save_registered(said=said, doc=VALID_FIXTURE, metadata=VALID_METADATA)
    updated = {**VALID_FIXTURE, "header": {**VALID_FIXTURE["header"], "label": "Updated"}}
    ref = store.save_registered(said=said, doc=updated, metadata=VALID_METADATA, overwrite=True)
    loaded_doc, _ = store.load(ref)
    assert loaded_doc["header"]["label"] == "Updated"


def test_promote_draft_to_registered(store):
    draft_ref = store.save_draft(local_id="d1", doc=VALID_FIXTURE, metadata=VALID_METADATA)
    promoted = store.promote_to_registered(draft_ref, said=VALID_FIXTURE["d"])
    assert promoted.kind == "registered"
    assert (store.root / "templates" / "drafts" / "d1").exists() is False
    assert (store.root / "templates" / "registered" / VALID_FIXTURE["d"]).exists()

    loaded_doc, _ = store.load(promoted)
    assert loaded_doc["d"] == VALID_FIXTURE["d"]
    assert loaded_doc["header"]["label"] == "Test Template"


def test_delete_draft(store):
    ref = store.save_draft(local_id="d1", doc=VALID_FIXTURE, metadata=VALID_METADATA)
    store.delete(ref)
    assert store.list_templates() == []


def test_list_returns_drafts_and_registered(store):
    store.save_draft(local_id="d1", doc=VALID_FIXTURE, metadata=VALID_METADATA)
    store.save_registered(said=VALID_FIXTURE["d"], doc=VALID_FIXTURE, metadata=VALID_METADATA)
    refs = store.list_templates()
    kinds = {r.kind for r in refs}
    assert kinds == {"draft", "registered"}


def test_delete_missing_raises(store):
    ref = TemplateRef(kind="draft", local_id="never-saved", said=None)
    with pytest.raises(TemplateNotFound):
        store.delete(ref)
