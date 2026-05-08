# -*- encoding: utf-8 -*-
"""Tests for the Sugiyama layout helper. Pure-Python, no Qt required."""
from __future__ import annotations

import pytest

from locksmith.plugins.ecosystem_viewer.layout import (
    LayoutOptions,
    layout_hierarchical,
)


def _layers_of(result, nodes):
    """Group nodes by their result.layers index for assertion convenience."""
    layer_index = {}
    for i, layer in enumerate(result.layers):
        for n in layer:
            layer_index[n] = i
    return [layer_index[n] for n in nodes]


def test_simple_chain_three_layers():
    # A -> B -> C
    result = layout_hierarchical(
        nodes=["A", "B", "C"],
        edges=[("A", "B"), ("B", "C")],
    )
    layers = _layers_of(result, ["A", "B", "C"])
    assert layers == [0, 1, 2]
    assert result.feedback_edges == []


def test_diamond_lays_out_in_three_layers():
    # A -> B, A -> C, B -> D, C -> D
    result = layout_hierarchical(
        nodes=["A", "B", "C", "D"],
        edges=[("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")],
    )
    layers = _layers_of(result, ["A", "B", "C", "D"])
    assert layers == [0, 1, 1, 2]
    # B and C share layer 1 — confirm both are present.
    assert set(result.layers[1]) == {"B", "C"}
    assert result.feedback_edges == []


def test_two_independent_roots_share_layer_zero():
    # A -> B, C -> D; A and C are independent roots.
    result = layout_hierarchical(
        nodes=["A", "B", "C", "D"],
        edges=[("A", "B"), ("C", "D")],
    )
    assert set(result.layers[0]) == {"A", "C"}
    assert set(result.layers[1]) == {"B", "D"}


def test_isolated_node_lands_in_layer_zero():
    # X has no edges at all.
    result = layout_hierarchical(
        nodes=["A", "B", "X"],
        edges=[("A", "B")],
    )
    assert "X" in result.layers[0]
    assert "A" in result.layers[0]
    assert "B" in result.layers[1]


def test_cycle_breaks_with_one_feedback_edge():
    # A -> B -> C -> A
    result = layout_hierarchical(
        nodes=["A", "B", "C"],
        edges=[("A", "B"), ("B", "C"), ("C", "A")],
    )
    assert len(result.feedback_edges) == 1
    # The remaining graph is acyclic so all three nodes get distinct layers.
    layer_indices = sorted(_layers_of(result, ["A", "B", "C"]))
    assert layer_indices == [0, 1, 2]


def test_bottom_row_nodes_pinned_below_chain():
    # Schemas A->B->C; issuer AID I belongs in the bottom row.
    result = layout_hierarchical(
        nodes=["A", "B", "C", "I"],
        edges=[("A", "B"), ("B", "C"), ("I", "C")],  # membership-style edge
        bottom_row_nodes=["I"],
    )
    # Chain layers for A/B/C should not be perturbed by I's edges.
    layers = _layers_of(result, ["A", "B", "C"])
    assert layers == [0, 1, 2]
    # I is in the final layer, beyond C's layer.
    layer_index = {n: i for i, lyr in enumerate(result.layers) for n in lyr}
    assert layer_index["I"] > layer_index["C"]


def test_positions_are_centered_about_origin_in_tb():
    # Single-layer ordering: three siblings at layer 0 should center on x=0.
    opts = LayoutOptions(node_width=100, node_spacing=20)
    result = layout_hierarchical(
        nodes=["A", "B", "C"],
        edges=[],
        options=opts,
    )
    xs = sorted(result.positions[n][0] for n in ["A", "B", "C"])
    # Three slots of (100+20)=120 wide → range from -120 to +120, with 0 in middle.
    assert xs == [-120.0, 0.0, 120.0]


def test_layer_spacing_scales_with_options():
    opts = LayoutOptions(node_height=50, layer_spacing=100)
    result = layout_hierarchical(
        nodes=["A", "B"],
        edges=[("A", "B")],
        options=opts,
    )
    y_a = result.positions["A"][1]
    y_b = result.positions["B"][1]
    assert y_b - y_a == 50 + 100  # node_height + layer_spacing


def test_left_to_right_orientation_swaps_axes():
    opts = LayoutOptions(orientation="left-to-right", node_width=80, layer_spacing=60)
    result = layout_hierarchical(
        nodes=["A", "B"],
        edges=[("A", "B")],
        options=opts,
    )
    x_a = result.positions["A"][0]
    x_b = result.positions["B"][0]
    assert x_b - x_a == 80 + 60  # node_width + layer_spacing
    # Y for both should be 0 (single sibling per layer).
    assert result.positions["A"][1] == 0.0
    assert result.positions["B"][1] == 0.0


def test_self_loop_is_dropped_silently():
    # A -> A is meaningless; the layout filters it out.
    result = layout_hierarchical(
        nodes=["A", "B"],
        edges=[("A", "A"), ("A", "B")],
    )
    assert _layers_of(result, ["A", "B"]) == [0, 1]
    assert result.feedback_edges == []


def test_empty_graph_returns_empty_result():
    result = layout_hierarchical(nodes=[], edges=[])
    assert result.positions == {}
    assert result.layers == []
    assert result.feedback_edges == []


def test_bottom_row_reorders_by_barycenter_of_connecting_edges():
    # Three schemas at top (after layout: A, B, C left-to-right at layer 0).
    # Three issuers at bottom; without reordering they sort alphabetically.
    # With bottom_row_ordering_edges = [(I1, A), (I2, C), (I3, B)], the
    # bottom row should reorder to I1, I3, I2 (mean-x of neighbors: I1's
    # only neighbor is A=leftmost, I3 connects to B=middle, I2 to
    # C=rightmost).
    result = layout_hierarchical(
        nodes=["A", "B", "C", "I1", "I2", "I3"],
        edges=[],  # no chain-of-authority edges in this test
        bottom_row_nodes=["I1", "I2", "I3"],
        bottom_row_ordering_edges=[("I1", "A"), ("I2", "C"), ("I3", "B")],
    )
    bottom = result.layers[-1]
    assert bottom == ["I1", "I3", "I2"]


def test_bottom_row_ordering_edges_default_no_reorder():
    # Without the new param, behavior is unchanged: bottom row stays in
    # the alphabetical order produced by _group_into_layers + the
    # bottom-row append.
    result = layout_hierarchical(
        nodes=["A", "B", "C", "I1", "I2", "I3"],
        edges=[("A", "B")],
        bottom_row_nodes=["I1", "I2", "I3"],
    )
    bottom = result.layers[-1]
    assert bottom == ["I1", "I2", "I3"]


def test_bottom_row_node_with_no_ordering_edges_keeps_relative_position():
    # If a bottom-row node has zero ordering edges, it should retain its
    # original order relative to other unconnected siblings (stable sort).
    result = layout_hierarchical(
        nodes=["A", "B", "I1", "I2", "I3"],
        edges=[],
        bottom_row_nodes=["I1", "I2", "I3"],
        bottom_row_ordering_edges=[("I2", "A")],
    )
    bottom = result.layers[-1]
    # I2 should land near A (leftmost). I1 and I3 have no ordering edges
    # — they retain their alphabetical order from each other but follow
    # I2 since I2 has the lowest barycenter.
    assert bottom[0] == "I2"
    assert bottom[1:] == ["I1", "I3"]
