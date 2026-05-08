# -*- encoding: utf-8 -*-
"""Stage 14 T4: EcosystemGraphView integrates RoleNode + QualificationEdge."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest

from locksmith.plugins.ecosystem_viewer.db import EcosystemRecord, RoleRecord
from locksmith.plugins.ecosystem_viewer.graph_items import (
    QualificationEdge,
    RoleNode,
)
from locksmith.plugins.ecosystem_viewer.graph_view import EcosystemGraphView


SHOTS_DIR = Path(__file__).parent / "_screenshots"


def _grab(widget, name):
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = SHOTS_DIR / f"{name}.png"
    pixmap = widget.grab()
    assert pixmap.save(str(path))
    return path


# ---------------------------------------------------------------------------
# Vault stub
#
# render_ecosystem reads vault.hby.db.schema, vault.hby.kevers, vault.hby.habs,
# vault.org.list. We need just enough to keep _build_scene happy when the
# ecosystem references a schema SAID we want to resolve to a real
# ACDCSchemaInspection.
# ---------------------------------------------------------------------------


class _Schemer:
    def __init__(self, sed):
        self.sed = sed


class _SchemaDB:
    def __init__(self, mapping):
        self._m = mapping

    def get(self, keys):
        if isinstance(keys, tuple):
            said = keys[0]
        else:
            said = keys
        return self._m.get(said)


class _Hby:
    def __init__(self, schema_map):
        self.db = type("_DB", (), {"schema": _SchemaDB(schema_map)})()
        self.kevers = {}
        self.habs = {}

    def habByPre(self, _aid):
        return None


class _Org:
    @staticmethod
    def list():
        return []


class _VaultStub:
    def __init__(self, schema_map):
        self.hby = _Hby(schema_map)
        self.org = _Org()


def _producer_schema_sed(said: str) -> dict:
    """Minimal ACDC schema doc with attribute section so inspect_acdc_schema yields a partial-tier inspection."""
    return {
        "$id": said,
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "Producer Credential",
        "type": "object",
        "properties": {
            "v": {"type": "string"},
            "d": {"type": "string"},
            "i": {"type": "string"},
            "s": {"type": "string"},
            "a": {
                "oneOf": [
                    {"type": "string"},
                    {
                        "type": "object",
                        "properties": {
                            "i": {"type": "string"},
                            "dt": {"type": "string"},
                        },
                    },
                ],
            },
        },
        "required": ["v", "d", "i", "s", "a"],
    }


def test_graph_view_renders_role_node_and_qualification_edge(qapp):
    said = "ECmEfS_Producer"
    eco = EcosystemRecord(
        name="Insurance",
        schema_saids=[said],
        issuer_aids=["EBOG_AID_1"],
        role_names=["state-doi"],
        issuer_qualification_rules={said: "state-doi"},
    )
    role = RoleRecord(
        ecosystem_name="Insurance",
        name="state-doi",
        qualification_schema_said=said,
        root_issuer_aids=["EBOG_AID_1"],
    )
    vault = _VaultStub({said: _Schemer(_producer_schema_sed(said))})

    view = EcosystemGraphView()
    view.resize(800, 500)
    view.show()
    QTest.qWait(50)
    qapp.processEvents()
    view.render_ecosystem(
        eco,
        vault,
        get_role=lambda n: role if n == "state-doi" else None,
        list_roles=lambda eco_name: [role] if eco_name == "Insurance" else [],
        find_credentials_of_schema=lambda s: [],
    )
    QTest.qWait(300)
    qapp.processEvents()
    view.fit_to_content()
    qapp.processEvents()

    items = view._scene.items()
    role_nodes = [i for i in items if isinstance(i, RoleNode)]
    qualification_edges = [i for i in items if isinstance(i, QualificationEdge)]
    assert len(role_nodes) == 1, f"expected 1 RoleNode, got {len(role_nodes)}"
    assert role_nodes[0].role_name == "state-doi"
    assert len(qualification_edges) == 1
    assert qualification_edges[0].schema_said == said
    assert qualification_edges[0].role_name == "state-doi"

    shot = _grab(view, "graph_view_one_role_one_qualification_edge")
    assert shot.exists()


def test_graph_view_emits_role_selected_on_role_click(qapp):
    eco = EcosystemRecord(
        name="Insurance",
        schema_saids=[],
        issuer_aids=[],
        role_names=["state-doi"],
        issuer_qualification_rules={},
    )
    role = RoleRecord(ecosystem_name="Insurance", name="state-doi")
    vault = _VaultStub({})

    view = EcosystemGraphView()
    view.render_ecosystem(
        eco,
        vault,
        get_role=lambda n: role,
        list_roles=lambda en: [role],
        find_credentials_of_schema=lambda s: [],
    )
    view.show()
    QTest.qWait(200)
    qapp.processEvents()

    captured = []
    view.role_selected.connect(lambda rname: captured.append(rname))

    role_node = next(i for i in view._scene.items() if isinstance(i, RoleNode))
    role_node.clicked.emit()
    qapp.processEvents()
    assert captured == ["state-doi"]


def test_graph_view_emits_remove_qualification_on_edge_signal(qapp):
    said = "ECmEfS_Producer"
    eco = EcosystemRecord(
        name="Insurance",
        schema_saids=[said],
        issuer_aids=[],
        role_names=["state-doi"],
        issuer_qualification_rules={said: "state-doi"},
    )
    role = RoleRecord(
        ecosystem_name="Insurance",
        name="state-doi",
        qualification_schema_said=said,
    )
    vault = _VaultStub({said: _Schemer(_producer_schema_sed(said))})

    view = EcosystemGraphView()
    view.render_ecosystem(
        eco,
        vault,
        get_role=lambda n: role,
        list_roles=lambda en: [role],
        find_credentials_of_schema=lambda s: [],
    )
    view.show()
    QTest.qWait(200)
    qapp.processEvents()

    captured = []
    view.remove_qualification_rule_requested.connect(
        lambda s, r: captured.append((s, r))
    )
    edge = next(i for i in view._scene.items() if isinstance(i, QualificationEdge))
    edge._emitter.remove_requested.emit(edge.schema_said, edge.role_name)
    qapp.processEvents()
    assert captured == [("ECmEfS_Producer", "state-doi")]


def test_drag_from_role_to_schema_emits_add_qualification_rule(qapp):
    said = "ECmEfS_Producer"
    eco = EcosystemRecord(
        name="Insurance",
        schema_saids=[said],
        issuer_aids=[],
        role_names=["state-doi"],
        issuer_qualification_rules={},  # rule not yet set
    )
    role = RoleRecord(
        ecosystem_name="Insurance",
        name="state-doi",
        qualification_schema_said=said,
    )
    vault = _VaultStub({said: _Schemer(_producer_schema_sed(said))})

    view = EcosystemGraphView()
    view.resize(800, 500)
    view.show()
    QTest.qWait(50)
    qapp.processEvents()
    view.render_ecosystem(
        eco,
        vault,
        get_role=lambda n: role if n == "state-doi" else None,
        list_roles=lambda en: [role] if en == "Insurance" else [],
        find_credentials_of_schema=lambda s: [],
    )
    QTest.qWait(200)
    qapp.processEvents()

    captured = []
    view.add_qualification_rule_requested.connect(
        lambda s, r: captured.append((s, r))
    )

    role_node = next(i for i in view._scene.items() if isinstance(i, RoleNode))
    schema_node = next(
        i for i in view._scene.items()
        if hasattr(i, "said") and getattr(i, "said", None) == said
    )

    inner = view._view
    inner._begin_drag_from(role_node)
    inner._end_drag(schema_node)
    qapp.processEvents()

    assert captured == [(said, "state-doi")]


def test_graph_view_role_click_populates_side_panel_via_show_role(qapp, monkeypatch):
    said = "ECmEfS_Producer"
    eco = EcosystemRecord(
        name="Insurance",
        schema_saids=[said],
        issuer_aids=[],
        role_names=["state-doi"],
        issuer_qualification_rules={},
    )
    role = RoleRecord(
        ecosystem_name="Insurance",
        name="state-doi",
        qualification_schema_said=said,
        root_issuer_aids=["EBOG_AID_root"],
    )
    vault = _VaultStub({said: _Schemer(_producer_schema_sed(said))})

    view = EcosystemGraphView()
    view.resize(800, 500)
    view.show()
    QTest.qWait(50)
    qapp.processEvents()
    view.render_ecosystem(
        eco,
        vault,
        get_role=lambda n: role if n == "state-doi" else None,
        list_roles=lambda en: [role] if en == "Insurance" else [],
        find_credentials_of_schema=lambda s: [],
    )
    QTest.qWait(200)
    qapp.processEvents()

    captured = {}
    real_show_role = view._side_panel.show_role

    def spy(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return real_show_role(*args, **kwargs)

    monkeypatch.setattr(view._side_panel, "show_role", spy)

    role_node = next(i for i in view._scene.items() if isinstance(i, RoleNode))
    role_node.clicked.emit()
    qapp.processEvents()

    assert "args" in captured or "kwargs" in captured
    passed_role = captured["kwargs"].get("role")
    if passed_role is None and captured.get("args"):
        passed_role = captured["args"][0]
    assert passed_role is not None
    assert passed_role.name == "state-doi"
    # Root role: no issuer_role_label.
    assert captured["kwargs"].get("issuer_role_label") is None


def test_drag_from_role_to_already_qualifying_schema_does_not_emit(qapp):
    said = "ECmEfS_Producer"
    eco = EcosystemRecord(
        name="Insurance",
        schema_saids=[said],
        issuer_aids=[],
        role_names=["state-doi"],
        issuer_qualification_rules={said: "state-doi"},  # already set
    )
    role = RoleRecord(
        ecosystem_name="Insurance",
        name="state-doi",
        qualification_schema_said=said,
    )
    vault = _VaultStub({said: _Schemer(_producer_schema_sed(said))})

    view = EcosystemGraphView()
    view.resize(800, 500)
    view.show()
    QTest.qWait(50)
    qapp.processEvents()
    view.render_ecosystem(
        eco,
        vault,
        get_role=lambda n: role,
        list_roles=lambda en: [role],
        find_credentials_of_schema=lambda s: [],
    )
    QTest.qWait(200)
    qapp.processEvents()

    captured = []
    view.add_qualification_rule_requested.connect(
        lambda s, r: captured.append((s, r))
    )

    role_node = next(i for i in view._scene.items() if isinstance(i, RoleNode))
    schema_node = next(
        i for i in view._scene.items()
        if hasattr(i, "said") and getattr(i, "said", None) == said
    )

    inner = view._view
    inner._begin_drag_from(role_node)
    inner._end_drag(schema_node)
    qapp.processEvents()

    assert captured == [], "should not emit when rule already exists"
