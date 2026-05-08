# -*- encoding: utf-8 -*-
"""Tests for role-row layout integration in layout_hierarchical."""
from __future__ import annotations

from locksmith.plugins.ecosystem_viewer.layout import layout_hierarchical


def test_role_row_orders_by_qualification_schema_barycenter():
    # Schemas A, B, C in layer 0. Roles R1 (qualifies via A) and
    # R2 (qualifies via C). Issuers I1, I2 in the bottom row.
    result = layout_hierarchical(
        nodes=["A", "B", "C", "R1", "R2", "I1", "I2"],
        edges=[],
        bottom_row_nodes=["I1", "I2"],
        bottom_row_ordering_edges=[],
        role_row_nodes=["R1", "R2"],
        role_row_ordering_edges=[("A", "R1"), ("C", "R2")],
    )
    role_layer = next(
        (i for i, layer in enumerate(result.layers) if "R1" in layer), None
    )
    assert role_layer is not None, "Role layer should exist"
    issuer_layer = next(
        i for i, layer in enumerate(result.layers) if "I1" in layer
    )
    assert role_layer < issuer_layer, "Roles must come before issuers"

    role_layer_nodes = result.layers[role_layer]
    # R1 should be left of R2 because A is left of C in the schema layer
    assert role_layer_nodes.index("R1") < role_layer_nodes.index("R2")


def test_role_row_omitted_when_no_role_nodes():
    result = layout_hierarchical(
        nodes=["A", "I1"],
        edges=[],
        bottom_row_nodes=["I1"],
        bottom_row_ordering_edges=[],
    )
    # No role layer present; behaviour identical to before.
    assert len(result.layers) == 2  # schemas + issuers
    assert "A" in result.layers[0]
    assert "I1" in result.layers[1]


def test_role_with_no_ordering_edge_falls_back_to_alphabetical():
    # R_zebra has an ordering edge; R_alpha doesn't.
    # Alphabetical fallback should put R_alpha after R_zebra in the layer.
    result = layout_hierarchical(
        nodes=["A", "R_alpha", "R_zebra", "I1"],
        edges=[],
        bottom_row_nodes=["I1"],
        bottom_row_ordering_edges=[],
        role_row_nodes=["R_alpha", "R_zebra"],
        role_row_ordering_edges=[("A", "R_zebra")],
    )
    role_layer = next(
        (i for i, layer in enumerate(result.layers) if "R_alpha" in layer)
    )
    role_layer_nodes = result.layers[role_layer]
    assert role_layer_nodes == ["R_zebra", "R_alpha"], (
        f"Expected zebra (with edge) before alpha (alphabetical fallback), "
        f"got {role_layer_nodes}"
    )


def test_role_row_y_position_between_schemas_and_issuers():
    result = layout_hierarchical(
        nodes=["A", "R1", "I1"],
        edges=[],
        bottom_row_nodes=["I1"],
        bottom_row_ordering_edges=[],
        role_row_nodes=["R1"],
        role_row_ordering_edges=[("A", "R1")],
    )
    schema_y = result.positions["A"][1]
    role_y = result.positions["R1"][1]
    issuer_y = result.positions["I1"][1]
    assert schema_y < role_y < issuer_y
