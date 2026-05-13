# -*- encoding: utf-8 -*-
"""JsonSourceView: two-way bound JSON editor."""
from __future__ import annotations

import json

import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest

from locksmith.plugins.designer.widgets.json_source_view import JsonSourceView


FIXTURE = {
    "d": "E" + "A" * 43,
    "spec_version": "micro-app-template/0.1",
    "header": {
        "id": "test-app",
        "display_name": "Test",
        "description": "Test",
        "version": "1.0",
        "expression_language": "UEL/1.0",
    },
    "role": {
        "id": "tester", "display_name": "Tester", "description": "T",
        "kind": "individual",
        "keri_infrastructure": {
            "witness_pool": False, "watcher_network": False,
            "mailbox": False, "acdc_registry": False,
        },
    },
    "credentials": {"imports": [], "exports": []},
    "commands": [], "aggregates": [], "reactions": [],
    "workflows": [], "projections": [], "rules": [],
}


def test_set_doc_renders_formatted_json(qapp):
    view = JsonSourceView()
    view.set_doc(FIXTURE)
    text = view.editor.toPlainText()
    assert "header" in text
    parsed = json.loads(text)
    assert parsed == FIXTURE


def test_user_edit_emits_applied_after_debounce(qapp):
    view = JsonSourceView()
    view.set_doc(FIXTURE)
    received: list[dict] = []
    view.applied.connect(lambda d: received.append(d))
    updated = {**FIXTURE, "header": {**FIXTURE["header"], "display_name": "Updated"}}
    view.editor.setPlainText(json.dumps(updated))
    QTest.qWait(450)
    qapp.processEvents()
    assert received, "applied signal not emitted"
    assert received[-1]["header"]["display_name"] == "Updated"


def test_invalid_json_emits_parse_error(qapp):
    view = JsonSourceView()
    view.set_doc(FIXTURE)
    errors: list[str] = []
    view.parse_error.connect(lambda msg: errors.append(msg))
    view.editor.setPlainText("{not: valid json")
    QTest.qWait(450)
    qapp.processEvents()
    assert errors, "parse_error not emitted"


def test_set_doc_does_not_emit_applied(qapp):
    view = JsonSourceView()
    received: list[dict] = []
    view.applied.connect(lambda d: received.append(d))
    view.set_doc(FIXTURE)
    QTest.qWait(450)
    qapp.processEvents()
    assert received == [], "set_doc should not trigger applied"
