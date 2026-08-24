"""
Owner: Person 3

Purpose:
Tool-call logging/metrics for evaluation.
"""


def _safe_number(value):
    return value if isinstance(value, (int, float)) else 0


def _usage_value(usage, field):
    if isinstance(usage, dict):
        return _safe_number(usage.get(field))
    return _safe_number(getattr(usage, field, None))


def _result_count(result):
    if result is None:
        return 0
    if isinstance(result, list):
        return len(result)
    if isinstance(result, dict):
        if "result_count" in result:
            return _safe_number(result["result_count"])
        if "rows" in result and isinstance(result["rows"], list):
            return len(result["rows"])
        if result.get("error"):
            return 0
        return 1 if result else 0
    return 1


def _tool_log_entry(call):
    return {
        "iteration": call.get("iteration"),
        "tool_name": call.get("name"),
        "parameters": call.get("input", {}),
        "timestamp": call.get("timestamp"),
        "success": not call.get("is_error", False),
        "result_count": _result_count(call.get("result")),
    }


def compute_metrics(loop_result, *, question_id=None, policy=None):
    """Derive per-question evaluation metrics from answer_question().

    Missing usage objects or usage fields are treated as zero so tests,
    stub clients, older SDK responses, and API-error paths all remain
    safe to summarize.
    """
    tool_calls = loop_result.get("tool_calls", [])
    usage_records = loop_result.get("usage")
    if usage_records is None:
        usage_records = [
            trace.get("usage", {})
            for trace in loop_result.get("traces", [])
            if isinstance(trace, dict)
        ]

    input_tokens = sum(_usage_value(usage, "input_tokens") for usage in usage_records)
    output_tokens = sum(_usage_value(usage, "output_tokens") for usage in usage_records)
    cache_read_tokens = sum(
        _usage_value(usage, "cache_read_input_tokens") for usage in usage_records
    )
    cache_creation_tokens = sum(
        _usage_value(usage, "cache_creation_input_tokens") for usage in usage_records
    )

    outcome = policy["status"] if policy and "status" in policy else loop_result.get("status")

    return {
        "question_id": question_id,
        "iterations": loop_result.get("iterations", 0),
        "tool_call_count": len(tool_calls),
        "tools_used": sorted({call.get("name") for call in tool_calls if call.get("name")}),
        "hit_iteration_cap": bool(loop_result.get("hit_iteration_cap", False)),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_input_tokens": cache_read_tokens,
        "cache_creation_input_tokens": cache_creation_tokens,
        "latency_seconds": max(0, _safe_number(loop_result.get("latency_seconds"))),
        "outcome": outcome,
        "tool_calls": [_tool_log_entry(call) for call in tool_calls],
    }


def average_tool_calls(metrics_list):
    """Return average dispatched tool calls per evaluated question."""
    if not metrics_list:
        return 0.0
    total = sum(metric.get("tool_call_count", 0) for metric in metrics_list)
    return total / len(metrics_list)
