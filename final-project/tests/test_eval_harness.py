"""
Owner: Person 3

Tests for the Milestone 7 evaluation harness. These use injected fake
agent results only, so they never require an Anthropic API key or a
network call.
"""

import pytest

from agent.system_prompt import (
    STATUS_ANSWERED,
    STATUS_CLARIFICATION_REQUIRED,
    STATUS_REFUSED_MISSING_INFORMATION,
    STATUS_TECHNICAL_ERROR,
)
from eval.questions import EVALUATION_QUESTIONS, Q10_EXPECTED_REFUSAL
from eval.run_eval import evaluate_questions


def _loop_result(
    *,
    answer="answer",
    tool_calls=None,
    iterations=1,
    usage=None,
    latency_seconds=0.25,
    status="answered",
    hit_iteration_cap=False,
):
    if tool_calls is None:
        tool_calls = [
            {
                "iteration": 1,
                "name": "search",
                "input": {"query": "q"},
                "is_error": False,
                "result": {"source": "source.pdf", "page": 1},
            }
        ]
    return {
        "answer": answer,
        "status": status,
        "grounded": True,
        "iterations": iterations,
        "hit_iteration_cap": hit_iteration_cap,
        "tool_calls": tool_calls,
        "traces": [],
        "messages": [],
        "usage": usage or [],
        "latency_seconds": latency_seconds,
    }


def test_evaluation_question_list_has_exact_required_count_and_order():
    assert [question.number for question in EVALUATION_QUESTIONS] == list(range(1, 11))
    assert EVALUATION_QUESTIONS[0].text == 'Course number and credits for "׳\u009e׳‘׳•׳ ׳׳\u009e׳“׳¢׳™ ׳”׳\u009e׳—׳©׳‘"'
    assert EVALUATION_QUESTIONS[-1].text == "Academic secretariat office hours"


def test_q10_is_required_office_hours_question():
    q10 = EVALUATION_QUESTIONS[9]
    assert q10.number == 10
    assert "office hours" in q10.text
    assert q10.expected_status == STATUS_REFUSED_MISSING_INFORMATION
    assert q10.expected_exact_answer == Q10_EXPECTED_REFUSAL


def test_single_question_evaluation_result_collection():
    report = evaluate_questions(
        [EVALUATION_QUESTIONS[0]],
        agent_fn=lambda question: _loop_result(answer=f"answered: {question}"),
    )

    record = report.records[0]
    assert record.question_id == "q1"
    assert record.question_text == EVALUATION_QUESTIONS[0].text
    assert record.answer_text == f"answered: {EVALUATION_QUESTIONS[0].text}"
    assert record.outcome_status == STATUS_ANSWERED
    assert record.iterations == 1
    assert record.total_tool_calls == 1
    assert record.tools_used == ["search"]
    assert len(record.citations) == 1
    assert record.citations[0].startswith("source.pdf")
    assert record.citations[0].endswith("1")
    assert record.raw_agent_result["answer"] == f"answered: {EVALUATION_QUESTIONS[0].text}"


def test_multi_question_evaluation():
    report = evaluate_questions(
        EVALUATION_QUESTIONS[:3],
        agent_fn=lambda question: _loop_result(answer=question),
    )

    assert len(report.records) == 3
    assert report.summary["total_questions"] == 3
    assert [record.question_id for record in report.records] == ["q1", "q2", "q3"]


def test_answered_refused_error_status_counting():
    results = [
        _loop_result(),
        _loop_result(tool_calls=[], status="no_tool_result", answer=None, usage=[]),
        _loop_result(status="api_error", answer=None, tool_calls=[], usage=[], latency_seconds=0.1),
        _loop_result(
            answer="clarify",
            tool_calls=[
                {
                    "iteration": 1,
                    "name": "get_course_table",
                    "input": {},
                    "is_error": True,
                    "result": {"error": "ambiguous_curriculum", "valid_curricula": ["single_major_fall"]},
                }
            ],
        ),
        _loop_result(status="max_iterations", answer=None, hit_iteration_cap=True),
        _loop_result(tool_calls=[{"iteration": 1, "name": "search", "input": {}, "is_error": False, "result": {"total": 1}}]),
    ]

    report = evaluate_questions(EVALUATION_QUESTIONS[:6], agent_fn=lambda question: results.pop(0))

    assert report.summary["answered_count"] == 1
    assert report.summary["refused_missing_information_count"] == 1
    assert report.summary["technical_error_count"] == 1
    assert report.summary["clarification_required_count"] == 1
    assert report.summary["max_iterations_count"] == 1
    assert report.summary["no_grounded_answer_count"] == 1


def test_average_tool_calls_calculation():
    results = [
        _loop_result(tool_calls=[]),
        _loop_result(tool_calls=[{"iteration": 1, "name": "search", "input": {}, "is_error": False, "result": {"source": "s", "page": 1}}]),
        _loop_result(tool_calls=[
            {"iteration": 1, "name": "search", "input": {}, "is_error": False, "result": {"source": "s", "page": 1}},
            {"iteration": 2, "name": "get_course", "input": {}, "is_error": False, "result": {"source": "s", "page": 2}},
        ]),
    ]
    report = evaluate_questions(EVALUATION_QUESTIONS[:3], agent_fn=lambda question: results.pop(0))

    assert report.summary["average_tool_calls"] == pytest.approx(1.0)


def test_average_iterations_calculation():
    results = [
        _loop_result(iterations=1),
        _loop_result(iterations=2),
        _loop_result(iterations=3),
    ]
    report = evaluate_questions(EVALUATION_QUESTIONS[:3], agent_fn=lambda question: results.pop(0))

    assert report.summary["average_iterations"] == pytest.approx(2.0)


def test_token_aggregation():
    results = [
        _loop_result(usage=[{"input_tokens": 10, "output_tokens": 2}]),
        _loop_result(usage=[{"input_tokens": 20, "output_tokens": 3}]),
    ]
    report = evaluate_questions(EVALUATION_QUESTIONS[:2], agent_fn=lambda question: results.pop(0))

    assert report.summary["total_input_tokens"] == 30
    assert report.summary["total_output_tokens"] == 5


def test_cache_token_aggregation():
    results = [
        _loop_result(usage=[{"cache_read_input_tokens": 7, "cache_creation_input_tokens": 11}]),
        _loop_result(usage=[{"cache_read_input_tokens": 13, "cache_creation_input_tokens": 17}]),
    ]
    report = evaluate_questions(EVALUATION_QUESTIONS[:2], agent_fn=lambda question: results.pop(0))

    assert report.summary["total_cache_read_input_tokens"] == 20
    assert report.summary["total_cache_creation_input_tokens"] == 28


def test_latency_aggregation():
    results = [_loop_result(latency_seconds=0.25), _loop_result(latency_seconds=0.75)]
    report = evaluate_questions(EVALUATION_QUESTIONS[:2], agent_fn=lambda question: results.pop(0))

    assert report.summary["average_latency_seconds"] == pytest.approx(0.5)


def test_zero_question_safe_behavior():
    report = evaluate_questions([], agent_fn=lambda question: _loop_result())

    assert report.records == []
    assert report.summary["total_questions"] == 0
    assert report.summary["average_tool_calls"] == 0.0
    assert report.summary["average_iterations"] == 0.0
    assert report.summary["average_latency_seconds"] == 0.0


def test_q10_exact_refusal_is_preserved():
    report = evaluate_questions(
        [EVALUATION_QUESTIONS[9]],
        agent_fn=lambda question: {
            "status": STATUS_REFUSED_MISSING_INFORMATION,
            "answer": Q10_EXPECTED_REFUSAL,
        },
    )

    record = report.records[0]
    assert record.outcome_status == STATUS_REFUSED_MISSING_INFORMATION
    assert record.answer_text == Q10_EXPECTED_REFUSAL
    assert record.expected_exact_match is True


def test_missing_optional_metrics_fields_do_not_crash():
    report = evaluate_questions(
        [EVALUATION_QUESTIONS[0]],
        agent_fn=lambda question: {"answer": "partial", "status": "answered", "tool_calls": []},
    )

    record = report.records[0]
    assert record.iterations == 0
    assert record.input_tokens == 0
    assert record.output_tokens == 0
    assert record.latency_seconds >= 0


def test_dependency_injection_works_without_anthropic_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    calls = []

    def fake_agent(question):
        calls.append(question)
        return _loop_result(answer="injected")

    report = evaluate_questions([EVALUATION_QUESTIONS[0]], agent_fn=fake_agent)

    assert calls == [EVALUATION_QUESTIONS[0].text]
    assert report.records[0].answer_text == "injected"
