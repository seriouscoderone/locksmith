# -*- encoding: utf-8 -*-
"""TemplateModel tests: signals, mutations, dirty tracking."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from locksmith.plugins.designer.model import TemplateModel


FIXTURE = {
    "d": "E" + "A" * 43,
    "spec_version": "micro-app-template/0.1",
    "header": {
        "id": "test-app",
        "display_name": "Original",
        "description": "Test",
        "version": "1.0",
        "expression_language": "UEL/1.0",
    },
    "role": {
        "id": "tester",
        "display_name": "Tester",
        "description": "Test role",
        "kind": "individual",
        "keri_infrastructure": {
            "witness_pool": False, "watcher_network": False,
            "mailbox": False, "acdc_registry": False,
        },
    },
    "credentials": {"imports": [], "exports": []},
    "commands": [],
    "aggregates": [],
    "reactions": [],
    "workflows": [],
    "projections": [],
    "rules": [],
}


def test_initial_state(qapp):
    m = TemplateModel(FIXTURE)
    assert m.doc == FIXTURE
    assert m.dirty is False


def test_set_path_changes_value_and_marks_dirty(qapp):
    m = TemplateModel(FIXTURE)
    m.set_path("/header/display_name", "Updated")
    assert m.doc["header"]["display_name"] == "Updated"
    assert m.dirty is True


def test_set_path_emits_changed(qapp):
    m = TemplateModel(FIXTURE)
    received: list[str] = []
    m.changed.connect(lambda path: received.append(path))
    m.set_path("/header/display_name", "Updated")
    assert received == ["/header/display_name"]


def test_append_to_collection(qapp):
    m = TemplateModel(FIXTURE)
    m.append_to("/commands", {"id": "c1", "name": "Do Thing",
                              "description": "desc", "route": "/do",
                              "payload_schema": {},
                              "idempotency_key_expression": "x",
                              "emissions": []})
    assert len(m.doc["commands"]) == 1
    assert m.doc["commands"][0]["id"] == "c1"
    assert m.dirty is True


def test_remove_from_collection(qapp):
    seeded = {**FIXTURE, "commands": [{"id": "c1", "name": "Do",
                                       "description": "x", "route": "/r",
                                       "payload_schema": {},
                                       "idempotency_key_expression": "x",
                                       "emissions": []}]}
    m = TemplateModel(seeded)
    m.remove_from("/commands", 0)
    assert m.doc["commands"] == []
    assert m.dirty is True


def test_replace_doc_clears_dirty(qapp):
    m = TemplateModel(FIXTURE)
    m.set_path("/header/display_name", "Updated")
    new_fixture = {**FIXTURE,
                   "header": {**FIXTURE["header"], "display_name": "Reloaded"}}
    m.replace_doc(new_fixture)
    assert m.doc["header"]["display_name"] == "Reloaded"
    assert m.dirty is False


def test_mark_clean(qapp):
    m = TemplateModel(FIXTURE)
    m.set_path("/header/display_name", "x")
    m.mark_clean()
    assert m.dirty is False


def test_set_path_on_root_raises(qapp):
    m = TemplateModel(FIXTURE)
    with pytest.raises(ValueError):
        m.set_path("", "something")


def test_append_to_non_list_raises(qapp):
    m = TemplateModel(FIXTURE)
    with pytest.raises(TypeError):
        m.append_to("/header", {"x": 1})
