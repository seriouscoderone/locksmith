from locksmith.plugins.designer.widgets.state_machine_diagram import (
    StateMachineDiagram, StateTransition,
)


def test_renders_three_transitions(qapp):
    diag = StateMachineDiagram()
    diag.render([
        StateTransition(from_state="pending", to_state="active",
                        tel_primitive="issue"),
        StateTransition(from_state="active", to_state="suspended",
                        tel_primitive="update"),
        StateTransition(from_state="active", to_state="revoked",
                        tel_primitive="revoke"),
    ])
    assert diag.state_count == 4


def test_node_colors_track_arriving_tel_primitive(qapp):
    diag = StateMachineDiagram()
    diag.render([
        StateTransition(from_state="pending", to_state="active",
                        tel_primitive="issue"),
        StateTransition(from_state="active", to_state="revoked",
                        tel_primitive="revoke"),
    ])
    fills = diag.node_fill_map()
    assert fills["pending"] == "#D97757"
    assert fills["revoked"] == "#E94B7B"


def test_transition_labels_are_chip_styled(qapp):
    diag = StateMachineDiagram()
    diag.render([
        StateTransition(from_state="pending", to_state="active",
                        tel_primitive="issue"),
    ])
    labels = diag.transition_label_specs()
    assert len(labels) == 1
    spec = labels[0]
    assert spec["text"] == "issue"
    assert spec["color"] == "#D97757"
    assert spec["chip"] is True


def test_from_state_list_expanded(qapp):
    diag = StateMachineDiagram()
    diag.render([
        StateTransition(from_state=["active", "suspended"], to_state="revoked",
                        tel_primitive="revoke"),
    ])
    assert diag.state_count == 3
