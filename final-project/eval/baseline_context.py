"""
Owner: Person 3

Purpose:
Whole-corpus, full-context baseline comparison for 3-4 questions.
This is deliberately not agentic retrieval: callers provide already
prepared document context, and the baseline sends that full context
plus one dynamic question to Claude in a single turn.
"""

from __future__ import annotations

import time

from agent.loop import DEFAULT_MAX_TOKENS, DEFAULT_MODEL
from agent.system_prompt import (
    STATUS_ANSWERED,
    STATUS_REFUSED_MISSING_INFORMATION,
    STATUS_TECHNICAL_ERROR,
)

CACHE_CONTROL = {"type": "ephemeral"}
BASELINE_REFUSAL_TEXT = "לא מופיע במסמכים"

BASELINE_SYSTEM_PROMPT = """You are a Hebrew-language academic assistant evaluating a whole-context baseline for Computer Science degree requirements and undergraduate academic regulations.

You receive all available prepared document context directly in the system prompt. Answer only from that provided context.

Rules:
1. Do not use outside knowledge, general college knowledge, web knowledge, or model memory.
2. Every factual answer should cite source metadata that appears in the provided context, such as document name, section, and page.
3. If the requested information is not present in the provided context, respond with exactly: לא מופיע במסמכים
4. Do not use the missing-information refusal for technical/API failures.
5. If the question depends on curriculum/plan and the context does not uniquely resolve it, ask for clarification or explicitly list the relevant alternatives. Do not silently choose one.
6. Do not invent pages, sections, document names, course numbers, credits, or source metadata.
7. Keep answers in Hebrew unless the user asks otherwise."""


def _extract_text(content_blocks):
    parts = [block.text for block in content_blocks if getattr(block, "type", None) == "text"]
    return "".join(parts) if parts else None


def _usage_to_dict(usage):
    if usage is None:
        return {}
    fields = (
        "input_tokens",
        "output_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
    )
    return {
        field: getattr(usage, field)
        for field in fields
        if getattr(usage, field, None) is not None
    }


def _safe_number(value):
    return value if isinstance(value, (int, float)) else 0


def _usage_value(usage, field):
    if isinstance(usage, dict):
        return _safe_number(usage.get(field))
    return _safe_number(getattr(usage, field, None))


def _build_system(document_context):
    return [
        {"type": "text", "text": BASELINE_SYSTEM_PROMPT},
        {
            "type": "text",
            "text": str(document_context),
            "cache_control": dict(CACHE_CONTROL),
        },
    ]


def _build_messages(question):
    return [
        {
            "role": "user",
            "content": [{"type": "text", "text": question}],
        }
    ]


def _metrics(usage_records, latency_seconds, status):
    return {
        "iterations": 1 if usage_records else 0,
        "tool_call_count": 0,
        "tools_used": [],
        "hit_iteration_cap": False,
        "input_tokens": sum(_usage_value(usage, "input_tokens") for usage in usage_records),
        "output_tokens": sum(_usage_value(usage, "output_tokens") for usage in usage_records),
        "cache_read_input_tokens": sum(
            _usage_value(usage, "cache_read_input_tokens") for usage in usage_records
        ),
        "cache_creation_input_tokens": sum(
            _usage_value(usage, "cache_creation_input_tokens") for usage in usage_records
        ),
        "latency_seconds": max(0, _safe_number(latency_seconds)),
        "outcome": status,
        "tool_calls": [],
    }


def _status_for_answer(answer):
    if answer == BASELINE_REFUSAL_TEXT:
        return STATUS_REFUSED_MISSING_INFORMATION
    return STATUS_ANSWERED


def answer_question_with_full_context(
    question,
    *,
    document_context,
    client,
    model=DEFAULT_MODEL,
    max_tokens=DEFAULT_MAX_TOKENS,
):
    """Answer one question by sending full prepared context to Claude.

    The result intentionally mirrors the evaluation fields used by the
    agentic retrieval path where practical, but `tool_calls` is always
    an empty list and no retrieval tools are supplied to the model.
    """
    started_at = time.perf_counter()
    usage_records = []
    messages = _build_messages(question)

    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=_build_system(document_context),
            messages=messages,
        )
    except Exception as exc:
        latency_seconds = time.perf_counter() - started_at
        status = STATUS_TECHNICAL_ERROR
        return {
            "mode": "full_context_baseline",
            "answer": None,
            "status": status,
            "error_message": str(exc),
            "grounded": False,
            "iterations": 0,
            "hit_iteration_cap": False,
            "tool_calls": [],
            "traces": [],
            "messages": messages,
            "usage": usage_records,
            "latency_seconds": latency_seconds,
            "metrics": _metrics(usage_records, latency_seconds, status),
        }

    usage = _usage_to_dict(getattr(response, "usage", None))
    usage_records.append(usage)
    answer = _extract_text(response.content)
    status = _status_for_answer(answer)
    latency_seconds = time.perf_counter() - started_at

    return {
        "mode": "full_context_baseline",
        "answer": answer,
        "status": status,
        "grounded": status == STATUS_ANSWERED,
        "iterations": 1,
        "hit_iteration_cap": False,
        "tool_calls": [],
        "traces": [
            {
                "iteration": 1,
                "stop_reason": response.stop_reason,
                "block_types": [getattr(block, "type", None) for block in response.content],
                "usage": usage,
            }
        ],
        "messages": messages,
        "usage": usage_records,
        "latency_seconds": latency_seconds,
        "metrics": _metrics(usage_records, latency_seconds, status),
    }


def make_baseline_agent_fn(*, document_context, client, model=DEFAULT_MODEL, max_tokens=DEFAULT_MAX_TOKENS):
    """Return an `agent_fn(question) -> dict` for eval.run_eval."""

    def run_baseline(question):
        return answer_question_with_full_context(
            question,
            document_context=document_context,
            client=client,
            model=model,
            max_tokens=max_tokens,
        )

    return run_baseline
