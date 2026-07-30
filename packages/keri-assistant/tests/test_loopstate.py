import json

import pytest
from keri_assistant.loopstate import LoopState, observation_for
from keri_assistant.tools import ToolResult


def test_defaults():
    s = LoopState(utterance="attest the rating")
    assert (s.iteration, s.tool_calls, s.observations) == (0, 0, ())


def test_is_frozen():
    with pytest.raises(Exception):
        LoopState(utterance="x").iteration = 5        # type: ignore[misc]


def test_advanced_returns_a_new_state_and_never_mutates():
    a = LoopState(utterance="x")
    b = a.advanced(observation="saw 42 rows", tool_call=True)
    assert (a.iteration, a.tool_calls, a.observations) == (0, 0, ())
    assert b.iteration == 1
    assert b.tool_calls == 1
    assert b.observations == ("saw 42 rows",)


def test_advanced_without_a_tool_call_does_not_count_one():
    b = LoopState(utterance="x").advanced()
    assert (b.iteration, b.tool_calls) == (1, 0)


def test_observations_accumulate_in_order():
    s = LoopState(utterance="x").advanced(observation="first").advanced(observation="second")
    assert s.observations == ("first", "second")


def test_round_trips_through_json_unchanged():
    s = LoopState(utterance="attest", iteration=2, tool_calls=1, observations=("a", "b"))
    again = LoopState.from_dict(json.loads(json.dumps(s.to_dict())))
    assert again == s


def test_to_dict_is_json_serializable_with_no_custom_encoder():
    # 2C persists this; anything needing a custom encoder is a defect here, not there
    json.dumps(LoopState(utterance="x", observations=("a",)).to_dict())


def test_from_dict_rejects_a_missing_utterance():
    with pytest.raises(KeyError):
        LoopState.from_dict({"iteration": 1})


def test_observation_for_marks_the_source_and_carries_content():
    text = observation_for(ToolResult(tool_id="doc-parse", ok=True, content="42 rows"))
    assert "doc-parse" in text
    assert "42 rows" in text


def test_observation_for_a_failure_says_so_and_keeps_the_detail():
    text = observation_for(ToolResult(tool_id="board", ok=False, content="", detail="timed out"))
    assert "board" in text
    assert "timed out" in text
    assert "fail" in text.lower() or "error" in text.lower()
