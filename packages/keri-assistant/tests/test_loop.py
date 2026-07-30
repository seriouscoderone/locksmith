import pytest
from keri_assistant.decide import ANSWER, CALL_TOOL, PROPOSE
from keri_assistant.enforcement import EnforcementStrength
from keri_assistant.loop import AgentLoop, LoopBudget
from keri_assistant.tools import ToolResult
from tests.fakes import RecordingToolExecutor, ScriptedBinding
from tests.fixtures.loop_fixtures import COUNTERPARTY, G, REG, ROLE, SURF

CP = COUNTERPARTY              # local alias: the grounded counterparty AID


def _loop(script, **kw):
    ex = kw.pop("executor", None) or RecordingToolExecutor(
        {"doc-parse": ToolResult(tool_id="doc-parse", ok=True, content="42 rows")})
    b = ScriptedBinding(script)
    return AgentLoop(binding=b, surface=SURF, grounding=G, registry=REG,
                     executor=ex, role=ROLE, **kw), b, ex


def test_answer_exits_immediately():
    loop, b, ex = _loop([{"action": ANSWER, "text": "nothing to do"}])
    out = loop.run("hello")
    assert out.status == "answer"
    assert out.answer == "nothing to do"
    assert ex.calls == []


def test_tool_call_runs_autonomously_then_the_loop_continues():
    loop, b, ex = _loop([
        {"action": CALL_TOOL, "tool_id": "doc-parse"},   # decide
        {"path": "/tmp/x.xlsx"},                          # shape the tool args
        {"action": ANSWER, "text": "42 rows"},            # decide again
    ])
    out = loop.run("how many rows")
    assert out.status == "answer"
    assert ex.calls == [("doc-parse", {"path": "/tmp/x.xlsx"})]
    assert out.state.tool_calls == 1


def test_tool_output_reaches_the_model_as_DATA_never_as_instruction():
    loop, b, ex = _loop([
        {"action": CALL_TOOL, "tool_id": "doc-parse"},
        {"path": "/tmp/x.xlsx"},
        {"action": ANSWER, "text": "ok"},
    ])
    loop.run("go")
    last = b.requests[-1]
    assert any("42 rows" in c for c in last.data_context)
    assert "42 rows" not in last.instruction        # never merged into the instruction


def test_observations_are_source_marked():
    loop, b, ex = _loop([
        {"action": CALL_TOOL, "tool_id": "doc-parse"},
        {"path": "/tmp/x.xlsx"},
        {"action": ANSWER, "text": "ok"},
    ])
    out = loop.run("go")
    assert out.state.observations[0].startswith("[tool:doc-parse]")


def test_a_read_tool_skips_the_argument_ask_and_receives_an_empty_dict():
    # I1: read tools carry `_NO_ARGS` -- an empty-object schema -- as their WHOLE input_schema, not
    # one branch of a larger oneOf. Asking the model to shape it anyway is both a wasted decode
    # (the only possible answer is `{}`) and, per actionschema.py's own warning, a schema shape
    # that can break grammar compilation entirely (llama.cpp #25923). "board" is the projection-
    # derived read tool from loop_fixtures.SURF.
    ex = RecordingToolExecutor({"board": ToolResult(tool_id="board", ok=True, content="3 open")})
    loop, b, _ = _loop([
        {"action": CALL_TOOL, "tool_id": "board"},   # decide
        {"action": ANSWER, "text": "3 open"},        # decide again -- no args-shaping ask between
    ], executor=ex)
    out = loop.run("what's on the board")
    assert out.status == "answer"
    assert len(b.requests) == 2, "a read tool must not spend a backend call shaping empty args"
    assert ex.calls == [("board", {})]


def test_a_failing_tool_is_reported_and_the_loop_keeps_going():
    ex = RecordingToolExecutor({"doc-parse": ToolResult(tool_id="doc-parse", ok=False,
                                                        content="", detail="file missing")})
    loop, b, _ = _loop([
        {"action": CALL_TOOL, "tool_id": "doc-parse"},
        {"path": "/nope"},
        {"action": ANSWER, "text": "could not read it"},
    ], executor=ex)
    out = loop.run("go")
    assert out.status == "answer"
    assert "file missing" in out.state.observations[0]


def test_propose_exits_the_loop_with_a_grounded_proposal():
    loop, b, ex = _loop([
        {"action": PROPOSE},
        {"verb_id": "submit_report", "receiver_aid": CP, "payload": {"amount": 10}},
    ])
    out = loop.run("file the report")
    assert out.status == "proposal"
    assert out.proposal.status == "intent"
    assert out.proposal.intent.verb_id == "submit_report"
    assert out.proposal.intent.receiver_aid == CP


def test_the_loop_NEVER_confirms_or_dispatches_anything():
    # 2B must not re-implement approval; a proposal leaves the loop for the existing ceremony.
    # Assert on the AST, not the source text: a substring check would match this module's own
    # explanatory prose, and would MISS an import made under an alias.
    import ast
    import inspect

    import keri_assistant.loop as loopmod
    tree = ast.parse(inspect.getsource(loopmod))
    imported = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            imported |= {a.name for a in n.names}
            if isinstance(n, ast.ImportFrom) and n.module:
                imported.add(n.module)
    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "Confirmer" not in imported
    assert "Dispatcher" not in imported
    assert not any(m.endswith("seams") for m in imported)
    assert "dispatch" not in called
    assert "confirm" not in called


def test_iteration_budget_exhaustion_is_explicit_not_silent():
    # a loop that stops because it ran out must be distinguishable from one that finished
    script = [{"action": CALL_TOOL, "tool_id": "doc-parse"}, {"path": "/x"}] * 10
    loop, b, ex = _loop(script, budget=LoopBudget(max_iterations=3, max_tool_calls=99))
    out = loop.run("loop forever")
    assert out.status == "budget_exhausted"
    assert "iteration" in out.reason
    assert out.state.iteration == 3


def test_tool_call_budget_exhaustion_is_explicit():
    script = [{"action": CALL_TOOL, "tool_id": "doc-parse"}, {"path": "/x"}] * 10
    loop, b, ex = _loop(script, budget=LoopBudget(max_iterations=99, max_tool_calls=2))
    out = loop.run("loop forever")
    assert out.status == "budget_exhausted"
    assert "tool" in out.reason
    assert out.state.tool_calls == 2


def test_the_standing_instruction_carries_the_role_purpose():
    loop, b, ex = _loop([{"action": ANSWER, "text": "ok"}])
    loop.run("go")
    assert "Reporter" in b.requests[0].instruction
    assert "submit reports" in b.requests[0].instruction


def test_decide_pass_is_handed_the_decide_schema_not_the_proposal_schema():
    loop, b, ex = _loop([{"action": ANSWER, "text": "ok"}])
    loop.run("go")
    actions = [a["properties"]["action"]["const"] for a in b.requests[0].schema["oneOf"]]
    assert actions == [CALL_TOOL, PROPOSE, ANSWER]


def test_shape_pass_is_handed_the_proposal_schema():
    loop, b, ex = _loop([
        {"action": PROPOSE},
        {"verb_id": "submit_report", "receiver_aid": CP, "payload": {"amount": 1}},
    ])
    loop.run("go")
    consts = {a["properties"]["verb_id"]["const"] for a in b.requests[1].schema["oneOf"]}
    assert "submit_report" in consts


def test_a_soft_binding_is_refused_for_the_shape_pass():
    # authority-bearing proposals require HARD enforcement (spec 8.1)
    from keri_assistant.enforcement import SoftEnforcementError
    b = ScriptedBinding([{"action": PROPOSE},
                         {"verb_id": "submit_report", "receiver_aid": CP,
                          "payload": {"amount": 1}}],
                        strength=EnforcementStrength.SOFT)
    loop = AgentLoop(binding=b, surface=SURF, grounding=G, registry=REG,
                     executor=RecordingToolExecutor(), role=ROLE)
    with pytest.raises(SoftEnforcementError):
        loop.run("file the report")


def test_a_soft_binding_is_FINE_for_reads_and_answers():
    # only authority-bearing work needs the hard guarantee; helpfulness must not require it -- and
    # that must be shown for the TOOL CALL too, not just the eventual answer. A3: this test's own
    # name promised "reads", but the original script never called a tool, so that half was unpinned.
    ex = RecordingToolExecutor({"doc-parse": ToolResult(tool_id="doc-parse", ok=True,
                                                        content="42 rows")})
    b = ScriptedBinding([
        {"action": CALL_TOOL, "tool_id": "doc-parse"},
        {"path": "/tmp/x.xlsx"},
        {"action": ANSWER, "text": "ok"},
    ], strength=EnforcementStrength.SOFT)
    loop = AgentLoop(binding=b, surface=SURF, grounding=G, registry=REG,
                     executor=ex, role=ROLE)
    out = loop.run("hi")
    assert out.status == "answer"
    assert ex.calls == [("doc-parse", {"path": "/tmp/x.xlsx"})]
