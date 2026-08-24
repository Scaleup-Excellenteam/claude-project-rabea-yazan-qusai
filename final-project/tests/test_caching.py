"""
Owner: Person 3

Tests for the prompt-caching wiring in agent/loop.py (SPEC.md section
2): "the tools/system prompt should be a stable cached prefix; apply
cache_control to the final block of each turn." Verifies the actual
request payloads sent to the (fake) Anthropic client, not just the
final answer. No real API call.
"""

from agent.loop import answer_question
from agent.system_prompt import SYSTEM_PROMPT
from agent.tool_defs import TOOL_DEFINITIONS
from tests.fixtures.fake_anthropic import FakeAnthropicClient, FakeResponse, TextBlock, ToolUseBlock
from tests.fixtures.stub_tools import build_stub_registry


def _run_two_tool_turns():
    client = FakeAnthropicClient([
        FakeResponse(content=[ToolUseBlock(id="c1", name="search", input={"query": "אלגוריתמים"})], stop_reason="tool_use"),
        FakeResponse(content=[ToolUseBlock(id="c2", name="get_course", input={"course_number": "0122407"})], stop_reason="tool_use"),
        FakeResponse(content=[TextBlock("נמצא.")], stop_reason="end_turn"),
    ])
    answer_question("שאלה", client=client, tool_registry=build_stub_registry(), max_iterations=5)
    return client


def test_system_prompt_is_sent_as_a_cached_stable_block():
    client = _run_two_tool_turns()
    system_sent = client.messages.calls[0]["system"]

    assert isinstance(system_sent, list)
    assert system_sent[-1]["text"] == SYSTEM_PROMPT
    assert system_sent[-1]["cache_control"] == {"type": "ephemeral"}


def test_last_tool_definition_is_marked_cacheable_others_are_not():
    client = _run_two_tool_turns()
    tools_sent = client.messages.calls[0]["tools"]

    assert "cache_control" not in tools_sent[0]
    assert tools_sent[-1]["cache_control"] == {"type": "ephemeral"}
    assert [t["name"] for t in tools_sent] == [t["name"] for t in TOOL_DEFINITIONS]


def test_original_tool_definitions_constant_is_not_mutated_by_caching():
    _run_two_tool_turns()
    assert all("cache_control" not in tool for tool in TOOL_DEFINITIONS)


def test_system_and_tools_prefix_is_identical_across_iterations():
    client = _run_two_tool_turns()
    calls = client.messages.calls

    assert len(calls) == 3
    assert calls[0]["system"] == calls[1]["system"] == calls[2]["system"]
    assert calls[0]["tools"] == calls[1]["tools"] == calls[2]["tools"]


def test_final_message_block_of_each_turn_carries_the_cache_marker():
    client = _run_two_tool_turns()
    for call in client.messages.calls:
        last_message = call["messages"][-1]
        content = last_message["content"]
        assert isinstance(content, list)
        assert content[-1]["cache_control"] == {"type": "ephemeral"}


def test_cache_marker_does_not_accumulate_or_leak_onto_earlier_messages():
    client = _run_two_tool_turns()
    last_call_messages = client.messages.calls[-1]["messages"]

    # Every earlier message's content blocks must be marker-free - only
    # the final block of the final message of each request may carry
    # cache_control, so old breakpoints never pile up turn over turn.
    for message in last_call_messages[:-1]:
        content = message["content"]
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    assert "cache_control" not in block

    final_content = last_call_messages[-1]["content"]
    marker_count = sum(1 for block in final_content if isinstance(block, dict) and "cache_control" in block)
    assert marker_count == 1


def test_caching_does_not_change_grounded_answer_result():
    client = FakeAnthropicClient([
        FakeResponse(content=[ToolUseBlock(id="c1", name="get_course", input={"course_number": "0111401"})], stop_reason="tool_use"),
        FakeResponse(content=[TextBlock("מבוא למדעי המחשב, 5 נקודות זכות.")], stop_reason="end_turn"),
    ])
    result = answer_question(
        "כמה נקודות זכות במבוא למדעי המחשב?",
        client=client, tool_registry=build_stub_registry(), max_iterations=5,
    )

    assert result["answer"] == "מבוא למדעי המחשב, 5 נקודות זכות."
    assert result["grounded"] is True
    assert result["status"] == "answered"
    assert len(result["tool_calls"]) == 1


def test_original_stored_messages_do_not_contain_cache_control():
    # result["messages"] is the clean conversation history (used for
    # tool dispatch bookkeeping); cache_control is a request-time-only
    # transformation and must not leak into it.
    client = FakeAnthropicClient([
        FakeResponse(content=[ToolUseBlock(id="c1", name="get_course", input={"course_number": "0111401"})], stop_reason="tool_use"),
        FakeResponse(content=[TextBlock("תשובה.")], stop_reason="end_turn"),
    ])
    result = answer_question(
        "שאלה", client=client, tool_registry=build_stub_registry(), max_iterations=5,
    )
    for message in result["messages"]:
        content = message["content"]
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    assert "cache_control" not in block
