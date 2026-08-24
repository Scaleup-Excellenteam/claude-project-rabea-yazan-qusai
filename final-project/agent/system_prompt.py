"""
Owner: Person 3

Purpose:
System prompt text for grounding/refusal/citation/ambiguity policy
(SPEC.md sections 1, 6, 7), plus a small deterministic policy layer
that classifies a completed agent/loop.py outcome into one of six
user-facing statuses so the app never collapses every failure mode
into a single string.

Design note: some behaviors (using only tool evidence, refusing with
the exact string, asking for clarification instead of guessing a
curriculum, surfacing contradictions) are primarily driven by
instructing the model via SYSTEM_PROMPT. classify_outcome() is the
harness-side backstop: it re-derives the safe answer from the raw
tool_calls/loop status rather than trusting the model's free text, so
an uncited or ungrounded answer can never reach the user even if the
model fails to follow the prompt.
"""

REFUSAL_TEXT = "לא מופיע במסמכים"

STATUS_ANSWERED = "answered"
STATUS_REFUSED_MISSING_INFORMATION = "refused_missing_information"
STATUS_CLARIFICATION_REQUIRED = "clarification_required"
STATUS_TECHNICAL_ERROR = "technical_error"
STATUS_MAX_ITERATIONS = "max_iterations"
STATUS_NO_GROUNDED_ANSWER = "no_grounded_answer"

# Tool-result error tags that mean "the retrieval attempt itself
# broke" (dispatch_tool_call failures), as opposed to a structured
# domain result like not_found/ambiguous_curriculum.
TECHNICAL_ERROR_TAGS = {"unknown_tool", "tool_exception"}
AMBIGUITY_TAGS = {"ambiguous_curriculum"}

REGULATIONS_FILENAME_MARKER = "תקנון"

CITATION_KEYS = {
    "source",
    "citation",
    "citations",
    "page",
    "page_start",
    "page_end",
    "section_title",
}

SYSTEM_PROMPT = """You are a Hebrew-language academic assistant answering student questions about Computer Science degree requirements and undergraduate academic regulations, grounded only in two official source PDFs (a course yearbook and an undergraduate regulations document). You do not have direct access to the PDFs; you must call the provided retrieval tools (list_sections, get_section, search, list_curricula, get_course_table, get_course) and answer only from what those tools return this turn.

Grounding rules:
1. Treat only successful tool results returned in this conversation as evidence. Never answer from general knowledge, training data, or assumptions about colleges, courses, or regulations, even if you believe you know the answer.
2. Every factual claim in your final answer must be attributable to a specific tool result, and you must include that source information (document name and page and/or section) next to the claim, in the citation format defined in SPEC.md.
3. If, after an adequate retrieval attempt (checking relevant sections/tables and trying at least one reasonable search), the requested information is not present in the documents, respond with exactly this string and nothing else: לא מופיע במסמכים
   Do not use that string for anything other than "information genuinely absent from the documents." If a tool call fails, times out, or errors, say so plainly as a technical problem instead - never disguise a technical failure as "not in the documents."
4. If the answer depends on which curriculum/plan the student is in (e.g. single-major vs dual-major, fall vs spring start) and the question does not specify one, do not guess or silently default to any curriculum. Call list_curricula, then either ask the student which curriculum they mean or present the answer for each relevant curriculum explicitly, clearly labeled.
5. If different tool results disagree with each other (e.g. two sources give different values for the same fact), do not silently pick one. State both values explicitly with their separate citations. Where the conflict is between the undergraduate regulations document and the yearbook on a matter of formal academic rules (e.g. degree completion conditions, study duration, credit requirements as a matter of policy), the regulations document is authoritative for the rule; still mention the yearbook's differing text for transparency.
6. For policy or conditional questions (e.g. eligibility rules, conditions for spreading studies), prefer retrieving the full section text with get_section over relying on a short search snippet when the exact wording matters.
7. For aggregation or computed answers (e.g. total credits in a year, counts of courses with prerequisites), retrieve the complete relevant table(s) first, compute the value yourself from the structured rows, state clearly that the value is computed, and cite every table/section that contributed to the computation.
8. Never fabricate page numbers, section titles, or document names. Only use the exact values returned by the tools.
9. Keep answers in Hebrew, matching the student's language, unless asked otherwise."""


def _source_document_type(source_filename):
    if not source_filename:
        return None
    return "regulations" if REGULATIONS_FILENAME_MARKER in source_filename else "yearbook"


def _citation_from_result(result):
    if "citation" in result and result["citation"]:
        return result["citation"]
    citation = {key: result[key] for key in ("source", "page", "page_start", "page_end") if key in result}
    return citation or None


def _contains_citation_keys(value):
    if isinstance(value, dict):
        if any(value.get(key) for key in CITATION_KEYS):
            return True
        return any(_contains_citation_keys(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_citation_keys(v) for v in value)
    return False


def _has_citation_metadata(successful_calls):
    return any(_contains_citation_keys(call["result"]) for call in successful_calls)


def detect_contradictions(tool_calls, key_field="course_number", value_field="credits"):
    """Find successful tool results that agree on `key_field` but
    disagree on `value_field` (e.g. two sources giving different
    credit counts for the same course number).

    Returns a list of {"key", "field", "values": [{"value", "citation",
    "document_type"}, ...]} entries, one per contradicting key. Never
    resolves the conflict itself - see apply_regulations_precedence.
    """
    by_key = {}
    for call in tool_calls:
        if call["is_error"]:
            continue
        result = call["result"]
        if not isinstance(result, dict):
            continue
        if key_field not in result or value_field not in result:
            continue
        by_key.setdefault(result[key_field], []).append(result)

    contradictions = []
    for key, results in by_key.items():
        distinct_values = {r[value_field] for r in results}
        if len(distinct_values) > 1:
            contradictions.append({
                "key": key,
                "field": value_field,
                "values": [
                    {
                        "value": r[value_field],
                        "citation": _citation_from_result(r),
                        "document_type": _source_document_type(r.get("source")),
                    }
                    for r in results
                ],
            })
    return contradictions


def apply_regulations_precedence(contradiction):
    """Given one detect_contradictions() entry, return the regulations
    value as authoritative if the conflict is specifically between a
    regulations-document value and a yearbook-document value.

    Returns None when the precedence rule does not apply (e.g. both
    conflicting values come from the yearbook) - callers must keep
    surfacing all values in that case rather than picking one.
    """
    doc_types = {v["document_type"] for v in contradiction["values"]}
    if doc_types == {"regulations", "yearbook"}:
        return next(v for v in contradiction["values"] if v["document_type"] == "regulations")
    return None


def classify_outcome(loop_result):
    """Turn a raw agent.loop.answer_question() result into a safe,
    user-facing policy decision. Never trusts the model's free text as
    a factual answer unless the tool evidence backing it is present.

    Returns a dict always containing "status" and "answer"; additional
    keys ("message", "options", "contradictions") are present depending
    on status.
    """
    if loop_result.get("status") == "api_error":
        return {
            "status": STATUS_TECHNICAL_ERROR,
            "answer": None,
            "message": loop_result.get("error_message", "technical failure"),
        }

    if loop_result.get("hit_iteration_cap") or loop_result.get("status") == "max_iterations":
        return {"status": STATUS_MAX_ITERATIONS, "answer": None}

    tool_calls = loop_result.get("tool_calls", [])

    ambiguous_calls = [
        call for call in tool_calls
        if isinstance(call["result"], dict) and call["result"].get("error") in AMBIGUITY_TAGS
    ]
    if ambiguous_calls:
        options = ambiguous_calls[-1]["result"].get("valid_curricula", [])
        return {
            "status": STATUS_CLARIFICATION_REQUIRED,
            "answer": loop_result.get("answer"),
            "options": options,
        }

    technical_calls = [
        call for call in tool_calls
        if isinstance(call["result"], dict) and call["result"].get("error") in TECHNICAL_ERROR_TAGS
    ]
    successful_calls = [call for call in tool_calls if not call["is_error"]]
    non_empty_successful_calls = [call for call in successful_calls if call["result"]]

    if not non_empty_successful_calls:
        if technical_calls and not successful_calls:
            last = technical_calls[-1]["result"]
            return {
                "status": STATUS_TECHNICAL_ERROR,
                "answer": None,
                "message": last.get("message", last.get("error")),
            }
        return {"status": STATUS_REFUSED_MISSING_INFORMATION, "answer": REFUSAL_TEXT}

    if not _has_citation_metadata(non_empty_successful_calls):
        return {"status": STATUS_NO_GROUNDED_ANSWER, "answer": None}

    return {
        "status": STATUS_ANSWERED,
        "answer": loop_result.get("answer"),
        "contradictions": detect_contradictions(tool_calls),
    }
