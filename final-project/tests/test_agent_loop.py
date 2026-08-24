"""
Owner: Person 3

Tests for agent/loop.py: the Claude tool-use loop. Uses a fake
Anthropic client (tests/fixtures/fake_anthropic.py) so no real API key
or network call is needed. Uses the contract-shaped stub tool registry
(tests/fixtures/stub_tools.py) so no real retrieval logic is needed.
"""

import json

import pytest

from agent.loop import answer_question
from tests.fixtures.fake_anthropic import FakeAnthropicClient, FakeResponse, TextBlock, ToolUseBlock
from tests.fixtures.stub_tools import build_stub_registry


def test_direct_final_response_with_no_tool_call():
    client = FakeAnthropicClient([
        FakeResponse(content=[TextBlock("שלום, איך אפשר לעזור?")], stop_reason="end_turn"),
    ])

    result = answer_question(
        "שאלה כלשהי",
        client=client,
        tool_registry=build_stub_registry(),
        max_iterations=5,
    )

    assert len(client.messages.calls) == 1
    assert result["iterations"] == 1
    assert result["tool_calls"] == []
    assert result["hit_iteration_cap"] is False
    assert result["traces"][0]["stop_reason"] == "end_turn"


def test_one_tool_call_then_final_response():
    client = FakeAnthropicClient([
        FakeResponse(
            content=[ToolUseBlock(id="call_1", name="get_course", input={"course_number": "0111401"})],
            stop_reason="tool_use",
        ),
        FakeResponse(
            content=[TextBlock("מבוא למדעי המחשב, 5 נקודות זכות (עמוד 9).")],
            stop_reason="end_turn",
        ),
    ])

    result = answer_question(
        "כמה נקודות זכות במבוא למדעי המחשב?",
        client=client,
        tool_registry=build_stub_registry(),
        max_iterations=5,
    )

    assert result["iterations"] == 2
    assert result["answer"] == "מבוא למדעי המחשב, 5 נקודות זכות (עמוד 9)."
    assert result["grounded"] is True
    assert result["status"] == "answered"
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["name"] == "get_course"
    assert result["tool_calls"][0]["is_error"] is False


def test_multiple_sequential_tool_calls_then_final_response():
    client = FakeAnthropicClient([
        FakeResponse(
            content=[ToolUseBlock(id="call_1", name="search", input={"query": "מבוא למדעי המחשב"})],
            stop_reason="tool_use",
        ),
        FakeResponse(
            content=[ToolUseBlock(id="call_2", name="get_course", input={"course_number": "0111401"})],
            stop_reason="tool_use",
        ),
        FakeResponse(
            content=[TextBlock("נמצא: מבוא למדעי המחשב, 5 נקודות זכות.")],
            stop_reason="end_turn",
        ),
    ])

    result = answer_question(
        "מצא לי פרטים על מבוא למדעי המחשב",
        client=client,
        tool_registry=build_stub_registry(),
        max_iterations=5,
    )

    assert result["iterations"] == 3
    assert len(result["tool_calls"]) == 2
    assert [call["name"] for call in result["tool_calls"]] == ["search", "get_course"]
    assert result["grounded"] is True
    assert result["answer"] == "נמצא: מבוא למדעי המחשב, 5 נקודות זכות."


def test_unknown_tool_name_handled_safely():
    client = FakeAnthropicClient([
        FakeResponse(
            content=[ToolUseBlock(id="call_1", name="delete_everything", input={})],
            stop_reason="tool_use",
        ),
        FakeResponse(
            content=[TextBlock("המחקתי הכל.")],
            stop_reason="end_turn",
        ),
    ])

    result = answer_question(
        "מחק את כל המסמכים",
        client=client,
        tool_registry=build_stub_registry(),
        max_iterations=5,
    )

    assert result["tool_calls"][0]["is_error"] is True
    assert result["tool_calls"][0]["result"]["error"] == "unknown_tool"
    assert result["grounded"] is False
    assert result["status"] == "no_tool_result"
    assert result["answer"] is None


def test_tool_callable_raises_exception_is_handled_safely():
    def boom(**kwargs):
        raise RuntimeError("db is locked")

    registry = build_stub_registry()
    registry["search"] = boom

    client = FakeAnthropicClient([
        FakeResponse(
            content=[ToolUseBlock(id="call_1", name="search", input={"query": "אלגוריתמים"})],
            stop_reason="tool_use",
        ),
        FakeResponse(
            content=[TextBlock("נמצאו אלגוריתמים.")],
            stop_reason="end_turn",
        ),
    ])

    result = answer_question(
        "חפש אלגוריתמים",
        client=client,
        tool_registry=registry,
        max_iterations=5,
    )

    assert result["tool_calls"][0]["is_error"] is True
    assert result["tool_calls"][0]["result"]["error"] == "tool_exception"
    assert "db is locked" in result["tool_calls"][0]["result"]["message"]
    assert result["grounded"] is False
    assert result["answer"] is None


def test_malformed_tool_arguments_are_handled_safely():
    # get_section requires section_id; missing it triggers a TypeError
    # inside the stub callable, which dispatch_tool_call must catch.
    client = FakeAnthropicClient([
        FakeResponse(
            content=[ToolUseBlock(id="call_1", name="get_section", input={})],
            stop_reason="tool_use",
        ),
        FakeResponse(
            content=[TextBlock("תשובה כלשהי.")],
            stop_reason="end_turn",
        ),
    ])

    result = answer_question(
        "מה כתוב בסעיף?",
        client=client,
        tool_registry=build_stub_registry(),
        max_iterations=5,
    )

    assert result["tool_calls"][0]["is_error"] is True
    assert result["tool_calls"][0]["result"]["error"] == "tool_exception"
    assert result["answer"] is None


def test_max_iteration_cap_is_enforced_and_never_loops_forever():
    # The model keeps requesting tools forever; the loop must stop at
    # max_iterations rather than calling the client indefinitely.
    responses = [
        FakeResponse(
            content=[ToolUseBlock(id=f"call_{i}", name="list_sections", input={})],
            stop_reason="tool_use",
        )
        for i in range(5)
    ]
    client = FakeAnthropicClient(responses)

    result = answer_question(
        "שאלה שלא נגמרת",
        client=client,
        tool_registry=build_stub_registry(),
        max_iterations=5,
    )

    assert len(client.messages.calls) == 5
    assert result["iterations"] == 5
    assert result["hit_iteration_cap"] is True
    assert result["status"] == "max_iterations"
    assert result["answer"] is None


def test_no_successful_tool_result_means_no_factual_answer():
    # The model answers directly with something that looks factual,
    # but never grounded it in any successful tool result.
    client = FakeAnthropicClient([
        FakeResponse(
            content=[TextBlock("התשובה היא 42 נקודות זכות.")],
            stop_reason="end_turn",
        ),
    ])

    result = answer_question(
        "כמה נקודות זכות בשנה ג'?",
        client=client,
        tool_registry=build_stub_registry(),
        max_iterations=5,
    )

    assert result["grounded"] is False
    assert result["status"] == "no_tool_result"
    assert result["answer"] is None


def test_tool_result_is_appended_back_into_conversation_correctly():
    client = FakeAnthropicClient([
        FakeResponse(
            content=[ToolUseBlock(id="call_1", name="get_course", input={"course_number": "0111401"})],
            stop_reason="tool_use",
        ),
        FakeResponse(
            content=[TextBlock("מבוא למדעי המחשב, 5 נקודות זכות.")],
            stop_reason="end_turn",
        ),
    ])
    registry = build_stub_registry()
    expected_result = registry["get_course"](course_number="0111401")

    result = answer_question(
        "כמה נקודות זכות במבוא למדעי המחשב?",
        client=client,
        tool_registry=registry,
        max_iterations=5,
    )

    messages = result["messages"]
    # messages[0] is the initial user question.
    assert messages[1]["role"] == "assistant"
    tool_result_message = messages[2]
    assert tool_result_message["role"] == "user"
    tool_result_block = tool_result_message["content"][0]
    assert tool_result_block["type"] == "tool_result"
    assert tool_result_block["tool_use_id"] == "call_1"
    assert tool_result_block["is_error"] is False
    assert json.loads(tool_result_block["content"]) == expected_result


def test_registry_swapping_changes_results_without_changing_the_loop():
    def fake_get_course(course_number):
        return {"course_number": course_number, "course_name": "COURSE FROM ALT REGISTRY", "credits": 99}

    alt_registry = {"get_course": fake_get_course}

    def make_client():
        return FakeAnthropicClient([
            FakeResponse(
                content=[ToolUseBlock(id="call_1", name="get_course", input={"course_number": "0111401"})],
                stop_reason="tool_use",
            ),
            FakeResponse(content=[TextBlock("תשובה.")], stop_reason="end_turn"),
        ])

    stub_result = answer_question(
        "שאלה", client=make_client(), tool_registry=build_stub_registry(), max_iterations=5,
    )
    alt_result = answer_question(
        "שאלה", client=make_client(), tool_registry=alt_registry, max_iterations=5,
    )

    assert stub_result["tool_calls"][0]["result"]["course_name"] == "מבוא למדעי המחשב"
    assert alt_result["tool_calls"][0]["result"]["course_name"] == "COURSE FROM ALT REGISTRY"


def test_max_iterations_out_of_spec_range_is_rejected():
    with pytest.raises(ValueError):
        answer_question(
            "שאלה",
            client=FakeAnthropicClient([]),
            tool_registry=build_stub_registry(),
            max_iterations=10,
        )
