# -*- encoding: utf-8 -*-
"""Stage 14 T7: page wires graph-view qualification signals to the plugin
handlers, and persistence flows end-to-end through the EcosystemBaser."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from types import SimpleNamespace

from locksmith.plugins.ecosystem_viewer.db import (
    EcosystemBaser,
    EcosystemRecord,
    RoleRecord,
)
from locksmith.plugins.ecosystem_viewer.pages import EcosystemDetailPage


def _make_page_with_baser(qapp):
    db = EcosystemBaser(name="test_t7_wiring", temp=True, reopen=True)
    db.put_ecosystem(EcosystemRecord(
        name="Insurance",
        schema_saids=["ESchema1"],
        issuer_aids=[],
    ))
    db.put_role(RoleRecord(
        ecosystem_name="Insurance",
        name="state-doi",
        qualification_schema_said="ESchema1",
    ))
    fake_app = SimpleNamespace(vault=None)
    page = EcosystemDetailPage(app=fake_app)
    page.set_db(db)
    page._current_name = "Insurance"
    return page, db


def test_add_qualification_rule_signal_persists_via_db(qapp):
    page, db = _make_page_with_baser(qapp)

    # Simulate the plugin's _set_qualification_rule handler — same body
    # as plugin.py's method but using the local db.
    def set_rule(eco_name, schema_said, role_name):
        eco = db.get_ecosystem(eco_name)
        eco.issuer_qualification_rules = dict(eco.issuer_qualification_rules)
        eco.issuer_qualification_rules[schema_said] = role_name
        db.put_ecosystem(eco)

    page.set_qualification_rule_clicked.connect(set_rule)

    # Fire the signal the graph view would emit on a successful drag.
    page._graph_view.add_qualification_rule_requested.emit(
        "ESchema1", "state-doi"
    )
    qapp.processEvents()

    rec = db.get_ecosystem("Insurance")
    assert rec.issuer_qualification_rules == {"ESchema1": "state-doi"}


def test_remove_qualification_rule_signal_persists_via_db(qapp):
    page, db = _make_page_with_baser(qapp)
    # Pre-seed the rule so we can verify removal.
    eco = db.get_ecosystem("Insurance")
    eco.issuer_qualification_rules = {"ESchema1": "state-doi"}
    db.put_ecosystem(eco)

    def remove_rule(eco_name, schema_said):
        rec = db.get_ecosystem(eco_name)
        rec.issuer_qualification_rules = dict(rec.issuer_qualification_rules)
        rec.issuer_qualification_rules.pop(schema_said, None)
        db.put_ecosystem(rec)

    page.remove_qualification_rule_clicked.connect(remove_rule)

    page._graph_view.remove_qualification_rule_requested.emit(
        "ESchema1", "state-doi"
    )
    qapp.processEvents()

    rec = db.get_ecosystem("Insurance")
    assert rec.issuer_qualification_rules == {}


def test_add_qualification_signal_no_emit_when_no_current_name(qapp):
    """Sanity: page swallows the signal if no ecosystem is loaded.
    Without this guard, a stray drag could fire with a None ecosystem
    name and corrupt the DB."""
    db = EcosystemBaser(name="test_t7_guard", temp=True, reopen=True)
    fake_app = SimpleNamespace(vault=None)
    page = EcosystemDetailPage(app=fake_app)
    page.set_db(db)
    page._current_name = None  # explicit

    captured: list = []
    page.set_qualification_rule_clicked.connect(
        lambda *args: captured.append(args)
    )

    page._graph_view.add_qualification_rule_requested.emit(
        "ESchema1", "state-doi"
    )
    qapp.processEvents()

    assert captured == [], "should not bubble up when no current ecosystem"
