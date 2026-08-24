"""
Owner: Person 3

Tests for agent/metrics.py: per-question metrics derived from a
completed agent.loop.answer_question() result, per SPEC.md section 8
(tool_name, parameters, success/result_count-style logging) plus
token/cache/latency tracking. No real API call.
"""

import math

from agent.loop import answer_question
from agent.metrics import average_tool_calls, compute_metrics
from agent.system_prompt import classify_outcome
from tests.fixtures.fake_anthropic import FakeAnthropicClient, FakeResponse, TextBlock, ToolUseBlock, Usage
from tests.fixtures.stub_tools import build_stub_registry


def _run_one_tool_call():
    client = FakeAnthropicClient([
        FakeResponse(
            content=[ToolUseBlock(id="call_1", name="get_course", input={"course_number": "0111401"})],
            stop_reason="tool_use",
            usage=Usage(input_tokens=500, output_tokens=20, cache_read_input_tokens=0, cache_creation_input_tokens=500),
        ),
        FakeResponse(
            content=[TextBlock("מבוא למדעי המחשב, 5 נקודות זכות.")],
            stop_reason="end_turn",
            usage=Usage(input_tokens=520, output_tokens=15, cache_read_input_tokens=500, cache_creation_input_tokens=0),
        ),
    ])
    return answer_question(
        "כמה נקודות זכות במבוא למדעי המחשב?",
        client=client,
        tool_registry=build_stub_registry(),
        max_iterations=5,
    )


def test_one_call_metrics_reports_basic_fields():
    loop_result = _run_one_tool_call()
    metrics = compute_metrics(loop_result, question_id="q1")

    assert metrics["question_id"] == "q1"
    assert metrics["iterations"] == 2
    assert metrics["tool_call_count"] == 1
    assert metrics["tools_used"] == ["get_course"]
    assert metrics["hit_iteration_cap"] is False


def test_multi_iteration_metrics_counts_iterations():
    client = FakeAnthropicClient([
        FakeResponse(content=[ToolUseBlock(id="c1", name="search", input={"query": "אלגוריתמים"})], stop_reason="tool_use"),
        FakeResponse(content=[ToolUseBlock(id="c2", name="get_course", input={"course_number": "0122407"})], stop_reason="tool_use"),
        FakeResponse(content=[TextBlock("נמצא.")], stop_reason="end_turn"),
    ])
    loop_result = answer_question(
        "שאלה", client=client, tool_registry=build_stub_registry(), max_iterations=5,
    )
    metrics = compute_metrics(loop_result)

    assert metrics["iterations"] == 3
    assert metrics["tool_call_count"] == 2


def test_tool_call_count_matches_number_of_dispatches():
    loop_result = _run_one_tool_call()
    metrics = compute_metrics(loop_result)
    assert metrics["tool_call_count"] == len(loop_result["tool_calls"]) == 1


def test_unique_tools_used_deduplicates_and_sorts():
    client = FakeAnthropicClient([
        FakeResponse(content=[
            ToolUseBlock(id="c1", name="search", input={"query": "א"}),
            ToolUseBlock(id="c2", name="search", input={"query": "ב"}),
            ToolUseBlock(id="c3", name="get_course", input={"course_number": "0111401"}),
        ], stop_reason="tool_use"),
        FakeResponse(content=[TextBlock("סיכום.")], stop_reason="end_turn"),
    ])
    loop_result = answer_question(
        "שאלה", client=client, tool_registry=build_stub_registry(), max_iterations=5,
    )
    metrics = compute_metrics(loop_result)

    assert metrics["tool_call_count"] == 3
    assert metrics["tools_used"] == ["get_course", "search"]


def test_iteration_cap_flag_is_reported():
    responses = [
        FakeResponse(content=[ToolUseBlock(id=f"c{i}", name="list_sections", input={})], stop_reason="tool_use")
        for i in range(5)
    ]
    client = FakeAnthropicClient(responses)
    loop_result = answer_question(
        "שאלה שלא נגמרת", client=client, tool_registry=build_stub_registry(), max_iterations=5,
    )
    metrics = compute_metrics(loop_result)

    assert metrics["hit_iteration_cap"] is True


def test_input_and_output_tokens_are_accumulated_across_iterations():
    loop_result = _run_one_tool_call()
    metrics = compute_metrics(loop_result)

    assert metrics["input_tokens"] == 500 + 520
    assert metrics["output_tokens"] == 20 + 15


def test_cache_read_tokens_are_accumulated_across_iterations():
    loop_result = _run_one_tool_call()
    metrics = compute_metrics(loop_result)

    assert metrics["cache_read_input_tokens"] == 0 + 500


def test_cache_creation_tokens_are_accumulated_across_iterations():
    loop_result = _run_one_tool_call()
    metrics = compute_metrics(loop_result)

    assert metrics["cache_creation_input_tokens"] == 500 + 0


def test_latency_field_is_present_and_non_negative():
    loop_result = _run_one_tool_call()
    metrics = compute_metrics(loop_result)

    assert isinstance(metrics["latency_seconds"], (int, float))
    assert metrics["latency_seconds"] >= 0
    assert not math.isnan(metrics["latency_seconds"])


def test_missing_usage_fields_are_handled_safely():
    client = FakeAnthropicClient([
        FakeResponse(content=[TextBlock("שלום")], stop_reason="end_turn", usage=None),
    ])
    loop_result = answer_question(
        "שאלה", client=client, tool_registry=build_stub_registry(), max_iterations=5,
    )
    metrics = compute_metrics(loop_result)  # must not raise

    assert metrics["input_tokens"] == 0
    assert metrics["output_tokens"] == 0
    assert metrics["cache_read_input_tokens"] == 0
    assert metrics["cache_creation_input_tokens"] == 0


def test_missing_usage_object_attributes_are_handled_safely():
    class PartialUsage:
        def __init__(self):
            self.input_tokens = 100
            # output_tokens / cache fields intentionally absent

    client = FakeAnthropicClient([
        FakeResponse(content=[TextBlock("שלום")], stop_reason="end_turn", usage=PartialUsage()),
    ])
    loop_result = answer_question(
        "שאלה", client=client, tool_registry=build_stub_registry(), max_iterations=5,
    )
    metrics = compute_metrics(loop_result)  # must not raise

    assert metrics["input_tokens"] == 100
    assert metrics["output_tokens"] == 0


def test_outcome_field_reflects_policy_status_when_provided():
    loop_result = _run_one_tool_call()
    policy = classify_outcome(loop_result)
    metrics = compute_metrics(loop_result, policy=policy)

    assert metrics["outcome"] == policy["status"] == "answered"


def test_outcome_field_falls_back_to_loop_status_without_policy():
    loop_result = _run_one_tool_call()
    metrics = compute_metrics(loop_result)

    assert metrics["outcome"] == loop_result["status"] == "answered"


def test_average_tool_calls_over_multiple_questions():
    metrics_list = [
        {"tool_call_count": 1},
        {"tool_call_count": 3},
        {"tool_call_count": 2},
    ]
    assert average_tool_calls(metrics_list) == 2.0


def test_average_tool_calls_of_empty_list_is_zero():
    assert average_tool_calls([]) == 0.0
