"""
Owner: Person 3

Purpose:
Claude tool-use loop. Sends the question plus tool definitions to an
injected Anthropic-compatible client, dispatches any requested tool
calls against an injected tool registry (stub now, real tools later -
see PERSON_3_AGENT_UI.md), feeds tool results back into the
conversation, and repeats until Claude returns a final (non-tool-use)
response or `max_iterations` is reached.

Grounding invariant (SPEC.md section 1/6/7): a final answer is only
handed back to the caller if at least one tool call in the
conversation actually succeeded. If Claude produces final text without
any successful tool result behind it, that text is discarded (not
returned as `answer`) so the caller can never present an ungrounded
answer as fact. Deciding the exact user-facing refusal wording/
citation formatting is out of scope here - see agent/system_prompt.py
(Milestone 4).

Client contract expected here (matches the Anthropic Python SDK's
`client.messages.create(...)`, and satisfied by
tests/fixtures/fake_anthropic.py in tests):
- `client.messages.create(**kwargs)` returns an object with
  `.content` (list of blocks; each has `.type`, and either `.text`
  or `.id`/`.name`/`.input`) and `.stop_reason`.

API/network failures from `client.messages.create` are caught here and
surfaced as a distinct `"api_error"` status (with `error_message`)
rather than raising or being mistaken for "information not in the
documents" - see agent/system_prompt.py's classify_outcome(), which
maps this to STATUS_TECHNICAL_ERROR.
"""

import copy
import json
import time
from datetime import datetime, timezone

from agent.system_prompt import SYSTEM_PROMPT
from agent.tool_defs import TOOL_DEFINITIONS, dispatch_tool_call

DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_MAX_TOKENS = 1024
MIN_MAX_ITERATIONS = 5
MAX_MAX_ITERATIONS = 8
CACHE_CONTROL = {"type": "ephemeral"}


def _extract_text(content_blocks):
    parts = [block.text for block in content_blocks if getattr(block, "type", None) == "text"]
    return "".join(parts) if parts else None


def _tool_use_blocks(content_blocks):
    return [block for block in content_blocks if getattr(block, "type", None) == "tool_use"]


def _cacheable_system(system):
    if isinstance(system, list):
        blocks = copy.deepcopy(system)
    else:
        blocks = [{"type": "text", "text": system}]
    blocks[-1]["cache_control"] = dict(CACHE_CONTROL)
    return blocks


def _cacheable_tools(tools):
    cacheable = copy.deepcopy(tools)
    cacheable[-1]["cache_control"] = dict(CACHE_CONTROL)
    return cacheable


def _content_block_to_dict(block):
    if isinstance(block, dict):
        return copy.deepcopy(block)
    block_type = getattr(block, "type", None)
    if block_type == "text":
        return {"type": "text", "text": block.text}
    if block_type == "tool_use":
        return {
            "type": "tool_use",
            "id": block.id,
            "name": block.name,
            "input": block.input,
        }
    return copy.deepcopy(block)


def _message_for_request(message):
    request_message = {"role": message["role"]}
    content = message["content"]
    if isinstance(content, str):
        request_message["content"] = [{"type": "text", "text": content}]
    elif isinstance(content, list):
        request_message["content"] = [_content_block_to_dict(block) for block in content]
    else:
        request_message["content"] = content
    return request_message


def _cacheable_messages(messages):
    request_messages = [_message_for_request(message) for message in messages]
    last_content = request_messages[-1]["content"]
    if isinstance(last_content, str):
        request_messages[-1]["content"] = [
            {"type": "text", "text": last_content, "cache_control": dict(CACHE_CONTROL)}
        ]
    elif isinstance(last_content, list) and last_content:
        last_content[-1]["cache_control"] = dict(CACHE_CONTROL)
    return request_messages


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


def answer_question(
    question,
    *,
    client,
    tool_registry,
    system=SYSTEM_PROMPT,
    model=DEFAULT_MODEL,
    max_iterations=6,
    max_tokens=DEFAULT_MAX_TOKENS,
):
    """Run the tool-use loop for one question and return a result dict.

    Returns:
        {
          "answer": str | None,           # None unless grounded in a
                                           # successful tool result
          "status": "answered" | "no_tool_result" | "no_text_answer"
                    | "max_iterations",
          "grounded": bool,                # any tool call succeeded
          "iterations": int,
          "hit_iteration_cap": bool,
          "tool_calls": [ {iteration, name, input, result, is_error} ],
          "traces": [ {iteration, stop_reason, block_types} ],
          "messages": list,                # full conversation, for
                                            # debugging/metrics later
        }
    """
    if not (MIN_MAX_ITERATIONS <= max_iterations <= MAX_MAX_ITERATIONS):
        raise ValueError(
            f"max_iterations must be between {MIN_MAX_ITERATIONS} and "
            f"{MAX_MAX_ITERATIONS} per SPEC.md, got {max_iterations}"
        )

    messages = [{"role": "user", "content": question}]
    tool_calls = []
    traces = []
    usage_records = []
    any_tool_succeeded = False
    final_answer = None
    hit_iteration_cap = False
    started_at = time.perf_counter()

    for iteration in range(1, max_iterations + 1):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=_cacheable_system(system),
                tools=_cacheable_tools(TOOL_DEFINITIONS),
                messages=_cacheable_messages(messages),
            )
        except Exception as exc:
            return {
                "answer": None,
                "status": "api_error",
                "error_message": str(exc),
                "grounded": any_tool_succeeded,
                "iterations": len(traces),
                "hit_iteration_cap": False,
                "tool_calls": tool_calls,
                "traces": traces,
                "messages": messages,
                "usage": usage_records,
                "latency_seconds": time.perf_counter() - started_at,
            }
        content_blocks = response.content
        stop_reason = response.stop_reason
        usage = _usage_to_dict(getattr(response, "usage", None))
        usage_records.append(usage)

        traces.append({
            "iteration": iteration,
            "stop_reason": stop_reason,
            "block_types": [getattr(b, "type", None) for b in content_blocks],
            "usage": usage,
        })

        messages.append({"role": "assistant", "content": content_blocks})

        if stop_reason != "tool_use":
            final_answer = _extract_text(content_blocks)
            break

        tool_result_content = []
        for block in _tool_use_blocks(content_blocks):
            result = dispatch_tool_call(block.name, block.input, tool_registry)
            is_error = isinstance(result, dict) and "error" in result
            if not is_error:
                any_tool_succeeded = True
            tool_calls.append({
                "iteration": iteration,
                "name": block.name,
                "input": block.input,
                "result": result,
                "is_error": is_error,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            tool_result_content.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result, ensure_ascii=False),
                "is_error": is_error,
            })

        messages.append({"role": "user", "content": tool_result_content})
    else:
        hit_iteration_cap = True

    if hit_iteration_cap:
        status = "max_iterations"
        final_answer = None
    elif not any_tool_succeeded:
        status = "no_tool_result"
        final_answer = None
    elif final_answer is None:
        status = "no_text_answer"
    else:
        status = "answered"

    return {
        "answer": final_answer,
        "status": status,
        "grounded": any_tool_succeeded,
        "iterations": len(traces),
        "hit_iteration_cap": hit_iteration_cap,
        "tool_calls": tool_calls,
        "traces": traces,
        "messages": messages,
        "usage": usage_records,
        "latency_seconds": time.perf_counter() - started_at,
    }
