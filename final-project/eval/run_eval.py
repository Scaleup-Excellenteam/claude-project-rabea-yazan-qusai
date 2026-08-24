"""
Owner: Person 3

Purpose:
Evaluation harness that runs the official questions and records
structured per-question results plus aggregate metrics. The production
path uses the existing agent entry point, but tests can inject a fake
agent callable so no API key or network call is required.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable

from agent.loop import answer_question
from agent.metrics import compute_metrics
from agent.system_prompt import (
    STATUS_ANSWERED,
    STATUS_CLARIFICATION_REQUIRED,
    STATUS_MAX_ITERATIONS,
    STATUS_NO_GROUNDED_ANSWER,
    STATUS_REFUSED_MISSING_INFORMATION,
    STATUS_TECHNICAL_ERROR,
    classify_outcome,
)
from agent.ui import build_default_tool_registry, create_anthropic_client, extract_citations
from eval.questions import EVALUATION_QUESTIONS, EvaluationQuestion

COUNTED_STATUSES = (
    STATUS_ANSWERED,
    STATUS_REFUSED_MISSING_INFORMATION,
    STATUS_CLARIFICATION_REQUIRED,
    STATUS_TECHNICAL_ERROR,
    STATUS_MAX_ITERATIONS,
    STATUS_NO_GROUNDED_ANSWER,
)


@dataclass(frozen=True)
class EvaluationRecord:
    question_id: str
    question_number: int
    question_text: str
    category: str
    expected_status: str | None
    expected_exact_answer: str | None
    raw_agent_result: dict
    outcome_status: str
    answer_text: str | None
    citations: list[str]
    iterations: int
    total_tool_calls: int
    tools_used: list[str]
    input_tokens: int | float
    output_tokens: int | float
    cache_read_input_tokens: int | float
    cache_creation_input_tokens: int | float
    latency_seconds: int | float
    hit_iteration_cap: bool
    expected_exact_match: bool | None

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class EvaluationReport:
    records: list[EvaluationRecord]
    summary: dict

    def to_dict(self):
        return {
            "records": [record.to_dict() for record in self.records],
            "summary": dict(self.summary),
        }

    def to_json(self, **kwargs):
        return json.dumps(self.to_dict(), ensure_ascii=False, **kwargs)


def _safe_divide(total, count):
    return total / count if count else 0.0


def _coerce_questions(questions: Iterable[EvaluationQuestion] | None):
    return list(EVALUATION_QUESTIONS if questions is None else questions)


def _default_agent(question_text, *, client=None, tool_registry=None):
    active_client = client or create_anthropic_client()
    active_registry = tool_registry or build_default_tool_registry()
    return answer_question(
        question_text,
        client=active_client,
        tool_registry=active_registry,
        max_iterations=6,
    )


def _policy_from_result(raw_result):
    if (
        raw_result.get("status") in COUNTED_STATUSES
        and ("tool_calls" not in raw_result or raw_result.get("mode") == "full_context_baseline")
    ):
        return {
            "status": raw_result.get("status"),
            "answer": raw_result.get("answer"),
            "message": raw_result.get("message"),
            "options": raw_result.get("options", []),
        }
    return classify_outcome(raw_result)


def _record_for_question(question, raw_result, elapsed_seconds):
    raw_result = raw_result or {}
    if "latency_seconds" not in raw_result:
        raw_result = {**raw_result, "latency_seconds": elapsed_seconds}

    policy = _policy_from_result(raw_result)
    metrics = compute_metrics(raw_result, question_id=question.id, policy=policy)
    answer_text = policy.get("answer")
    expected_exact_match = None
    if question.expected_exact_answer is not None:
        expected_exact_match = answer_text == question.expected_exact_answer

    return EvaluationRecord(
        question_id=question.id,
        question_number=question.number,
        question_text=question.text,
        category=question.category,
        expected_status=question.expected_status,
        expected_exact_answer=question.expected_exact_answer,
        raw_agent_result=raw_result,
        outcome_status=policy.get("status"),
        answer_text=answer_text,
        citations=extract_citations(loop_result=raw_result, policy=policy),
        iterations=metrics["iterations"],
        total_tool_calls=metrics["tool_call_count"],
        tools_used=metrics["tools_used"],
        input_tokens=metrics["input_tokens"],
        output_tokens=metrics["output_tokens"],
        cache_read_input_tokens=metrics["cache_read_input_tokens"],
        cache_creation_input_tokens=metrics["cache_creation_input_tokens"],
        latency_seconds=metrics["latency_seconds"],
        hit_iteration_cap=metrics["hit_iteration_cap"],
        expected_exact_match=expected_exact_match,
    )


def summarize_records(records):
    total_questions = len(records)
    status_counts = {f"{status}_count": 0 for status in COUNTED_STATUSES}
    for record in records:
        key = f"{record.outcome_status}_count"
        if key in status_counts:
            status_counts[key] += 1

    total_tool_calls = sum(record.total_tool_calls for record in records)
    total_iterations = sum(record.iterations for record in records)
    total_latency = sum(record.latency_seconds for record in records)

    return {
        "total_questions": total_questions,
        "answered_count": status_counts[f"{STATUS_ANSWERED}_count"],
        "refused_missing_information_count": status_counts[f"{STATUS_REFUSED_MISSING_INFORMATION}_count"],
        "clarification_required_count": status_counts[f"{STATUS_CLARIFICATION_REQUIRED}_count"],
        "technical_error_count": status_counts[f"{STATUS_TECHNICAL_ERROR}_count"],
        "max_iterations_count": status_counts[f"{STATUS_MAX_ITERATIONS}_count"],
        "no_grounded_answer_count": status_counts[f"{STATUS_NO_GROUNDED_ANSWER}_count"],
        "average_tool_calls": _safe_divide(total_tool_calls, total_questions),
        "average_iterations": _safe_divide(total_iterations, total_questions),
        "total_input_tokens": sum(record.input_tokens for record in records),
        "total_output_tokens": sum(record.output_tokens for record in records),
        "total_cache_read_input_tokens": sum(record.cache_read_input_tokens for record in records),
        "total_cache_creation_input_tokens": sum(record.cache_creation_input_tokens for record in records),
        "average_latency_seconds": _safe_divide(total_latency, total_questions),
    }


def evaluate_questions(
    questions: Iterable[EvaluationQuestion] | None = None,
    *,
    agent_fn: Callable[[str], dict] | None = None,
    client=None,
    tool_registry=None,
):
    """Run questions through the agent and return an in-memory report.

    `agent_fn` is the primary dependency-injection hook for tests. If
    omitted, the harness calls the real `agent.loop.answer_question`
    entry point with a real client and tool registry.
    """
    selected_questions = _coerce_questions(questions)
    run_agent = agent_fn or (lambda text: _default_agent(text, client=client, tool_registry=tool_registry))

    records = []
    for question in selected_questions:
        started_at = time.perf_counter()
        raw_result = run_agent(question.text)
        elapsed = time.perf_counter() - started_at
        records.append(_record_for_question(question, raw_result, elapsed))

    return EvaluationReport(records=records, summary=summarize_records(records))


def write_json_report(report, output_path):
    path = Path(output_path)
    path.write_text(report.to_json(indent=2), encoding="utf-8")
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the fixed Person 3 evaluation questions.")
    parser.add_argument("--json", dest="json_path", help="Optional path for a JSON report.")
    args = parser.parse_args(argv)

    report = evaluate_questions()
    if args.json_path:
        write_json_report(report, args.json_path)
    print(report.to_json(indent=2))
    return report


if __name__ == "__main__":
    main()
