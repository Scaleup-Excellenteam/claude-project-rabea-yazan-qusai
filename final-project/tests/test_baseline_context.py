"""
Owner: Person 3

Tests for eval/baseline_context.py: the whole-context comparison
baseline. Uses fake Anthropic clients only; no real API key, network,
retrieval tools, FTS, or agent tool loop.
"""

import pytest

from agent.system_prompt import (
    STATUS_ANSWERED,
    STATUS_REFUSED_MISSING_INFORMATION,
    STATUS_TECHNICAL_ERROR,
)
from eval.baseline_context import (
    BASELINE_REFUSAL_TEXT,
    BASELINE_SYSTEM_PROMPT,
    answer_question_with_full_context,
    make_baseline_agent_fn,
)
from eval.questions import EVALUATION_QUESTIONS
from eval.run_eval import evaluate_questions
from tests.fixtures.fake_anthropic import FakeAnthropicClient, FakeResponse, TextBlock, Usage


PREPARED_CONTEXT = (
    "[source: yearbook.pdf | page: 9 | section: courses]\n"
    "מבוא למדעי המחשב: course_number=0111401, credits=5.\n"
    "[source: regulations.pdf | page: 3 | section: duration]\n"
    "משך הלימודים הרגיל הוא שלוש שנים."
)


def _client(answer="answer with citation", usage=None):
    return FakeAnthropicClient([
        FakeResponse(content=[TextBlock(answer)], stop_reason="end_turn", usage=usage),
    ])


def test_baseline_sends_full_provided_context_to_model():
    client = _client()

    answer_question_with_full_context(
        "question",
        document_context=PREPARED_CONTEXT,
        client=client,
    )

    system = client.messages.calls[0]["system"]
    assert any(block["text"] == PREPARED_CONTEXT for block in system)


def test_question_is_included_separately_and_dynamically():
    client = _client()

    answer_question_with_full_context(
        "What is the course number?",
        document_context=PREPARED_CONTEXT,
        client=client,
    )

    call = client.messages.calls[0]
    assert PREPARED_CONTEXT not in call["messages"][0]["content"][0]["text"]
    assert call["messages"][0]["content"][0]["text"] == "What is the course number?"


def test_no_retrieval_tools_are_sent_or_called():
    client = _client()

    answer_question_with_full_context(
        "question",
        document_context=PREPARED_CONTEXT,
        client=client,
    )

    call = client.messages.calls[0]
    assert "tools" not in call


def test_tool_call_count_remains_zero():
    result = answer_question_with_full_context(
        "question",
        document_context=PREPARED_CONTEXT,
        client=_client(),
    )

    assert result["tool_calls"] == []
    assert result["metrics"]["tool_call_count"] == 0


def test_successful_answer_is_returned_in_structured_form():
    result = answer_question_with_full_context(
        "question",
        document_context=PREPARED_CONTEXT,
        client=_client("0111401, 5 credits (yearbook.pdf, page 9)."),
    )

    assert result["mode"] == "full_context_baseline"
    assert result["status"] == STATUS_ANSWERED
    assert result["answer"] == "0111401, 5 credits (yearbook.pdf, page 9)."
    assert result["iterations"] == 1


def test_exact_missing_information_refusal_is_preserved():
    result = answer_question_with_full_context(
        "office hours?",
        document_context=PREPARED_CONTEXT,
        client=_client(BASELINE_REFUSAL_TEXT),
    )

    assert result["status"] == STATUS_REFUSED_MISSING_INFORMATION
    assert result["answer"] == BASELINE_REFUSAL_TEXT


def test_api_client_failure_becomes_technical_error_not_missing_information():
    class ExplodingClient:
        class messages:
            @staticmethod
            def create(**kwargs):
                raise ConnectionError("network unreachable")

    result = answer_question_with_full_context(
        "question",
        document_context=PREPARED_CONTEXT,
        client=ExplodingClient(),
    )

    assert result["status"] == STATUS_TECHNICAL_ERROR
    assert result["answer"] is None
    assert result["answer"] != BASELINE_REFUSAL_TEXT
    assert "network unreachable" in result["error_message"]


def test_usage_tokens_are_collected():
    result = answer_question_with_full_context(
        "question",
        document_context=PREPARED_CONTEXT,
        client=_client(usage=Usage(input_tokens=100, output_tokens=20)),
    )

    assert result["metrics"]["input_tokens"] == 100
    assert result["metrics"]["output_tokens"] == 20


def test_cache_read_and_creation_tokens_are_collected():
    result = answer_question_with_full_context(
        "question",
        document_context=PREPARED_CONTEXT,
        client=_client(usage=Usage(cache_read_input_tokens=30, cache_creation_input_tokens=70)),
    )

    assert result["metrics"]["cache_read_input_tokens"] == 30
    assert result["metrics"]["cache_creation_input_tokens"] == 70


def test_latency_is_recorded():
    result = answer_question_with_full_context(
        "question",
        document_context=PREPARED_CONTEXT,
        client=_client(),
    )

    assert isinstance(result["latency_seconds"], (int, float))
    assert result["latency_seconds"] >= 0
    assert result["metrics"]["latency_seconds"] == result["latency_seconds"]


def test_missing_usage_fields_default_safely():
    class PartialUsage:
        input_tokens = 12

    result = answer_question_with_full_context(
        "question",
        document_context=PREPARED_CONTEXT,
        client=_client(usage=PartialUsage()),
    )

    assert result["metrics"]["input_tokens"] == 12
    assert result["metrics"]["output_tokens"] == 0
    assert result["metrics"]["cache_read_input_tokens"] == 0
    assert result["metrics"]["cache_creation_input_tokens"] == 0


def test_stable_context_caching_metadata_is_applied_correctly():
    client = _client()

    answer_question_with_full_context(
        "question",
        document_context=PREPARED_CONTEXT,
        client=client,
    )

    system = client.messages.calls[0]["system"]
    assert system[0]["text"] == BASELINE_SYSTEM_PROMPT
    assert "cache_control" not in system[0]
    assert system[1]["text"] == PREPARED_CONTEXT
    assert system[1]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in client.messages.calls[0]["messages"][0]["content"][0]


def test_repeated_calls_do_not_mutate_or_accumulate_cache_markers():
    client = FakeAnthropicClient([
        FakeResponse(content=[TextBlock("first")], stop_reason="end_turn"),
        FakeResponse(content=[TextBlock("second")], stop_reason="end_turn"),
    ])

    answer_question_with_full_context("q1", document_context=PREPARED_CONTEXT, client=client)
    answer_question_with_full_context("q2", document_context=PREPARED_CONTEXT, client=client)

    for call in client.messages.calls:
        system = call["system"]
        marker_count = sum(1 for block in system if "cache_control" in block)
        assert marker_count == 1
        assert system[1]["cache_control"] == {"type": "ephemeral"}


def test_evaluation_runner_compatibility_with_injected_baseline_function():
    baseline_fn = make_baseline_agent_fn(
        document_context=PREPARED_CONTEXT,
        client=_client("answer from full context (yearbook.pdf, page 9)."),
    )

    report = evaluate_questions([EVALUATION_QUESTIONS[0]], agent_fn=baseline_fn)

    record = report.records[0]
    assert record.outcome_status == STATUS_ANSWERED
    assert record.answer_text == "answer from full context (yearbook.pdf, page 9)."
    assert record.total_tool_calls == 0
    assert report.summary["average_tool_calls"] == pytest.approx(0.0)
