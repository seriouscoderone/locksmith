from locksmith.plugins.designer.widgets.swimlane_diagram import (
    SwimlaneDiagram, SwimlaneStep,
)


def test_renders_basic_lane_and_steps(qapp):
    diag = SwimlaneDiagram()
    diag.render(
        lanes=["self", "counterparty"],
        steps=[
            SwimlaneStep(step_id="a", label="step a", actor="self"),
            SwimlaneStep(step_id="b", label="step b", actor="counterparty"),
        ],
    )
    assert diag.step_count == 2


def test_step_numbers_are_assigned_sequentially(qapp):
    diag = SwimlaneDiagram()
    diag.render(
        lanes=["self"],
        steps=[
            SwimlaneStep(step_id="a", label="A", actor="self"),
            SwimlaneStep(step_id="b", label="B", actor="self"),
            SwimlaneStep(step_id="c", label="C", actor="self"),
        ],
    )
    numbers = diag.step_number_map()
    assert numbers["a"] == "1"
    assert numbers["b"] == "2"
    assert numbers["c"] == "3"


def test_branch_outcomes_get_letter_suffixes(qapp):
    # decide is step 1, branches lead to 2a (grant) and 2b (deny).
    diag = SwimlaneDiagram()
    diag.render(
        lanes=["self"],
        steps=[
            SwimlaneStep(step_id="decide", label="Decide", actor="self",
                          branches=[
                              {"rule_ref": "outcome_a", "next_step": "grant"},
                              {"rule_ref": "outcome_b", "next_step": "deny"},
                          ]),
            SwimlaneStep(step_id="grant", label="Grant", actor="self"),
            SwimlaneStep(step_id="deny", label="Deny", actor="self"),
        ],
    )
    numbers = diag.step_number_map()
    assert numbers["decide"] == "1"
    assert numbers["grant"] == "2a"
    assert numbers["deny"] == "2b"


def test_internal_step_marked(qapp):
    diag = SwimlaneDiagram()
    diag.render(
        lanes=["self"],
        steps=[
            SwimlaneStep(step_id="x", label="X", actor="self",
                          is_internal=True),
        ],
    )
    assert diag.internal_step_ids() == ["x"]


def test_time_bound_string_stored(qapp):
    diag = SwimlaneDiagram()
    diag.render(
        lanes=["self"],
        steps=[
            SwimlaneStep(step_id="x", label="X", actor="self",
                          time_bound="30-day bound · on expiry → terminate"),
        ],
    )
    bounds = diag.time_bound_map()
    assert "30-day" in bounds["x"]
