"""
Owner: Person 3

Tests for agent/system_prompt.py: the policy layer that classifies a
completed agent/loop.py outcome into a small set of user-facing
statuses (answered / refused_missing_information /
clarification_required / technical_error / max_iterations /
no_grounded_answer), enforcing the grounding/citation/refusal/
ambiguity/contradiction rules from SPEC.md on top of the raw
tool-use loop. Uses a fake Anthropic client and stub tool data only -
no real API calls.
"""

from agent.loop import answer_question
from agent.system_prompt import (
    REFUSAL_TEXT,
    STATUS_ANSWERED,
    STATUS_CLARIFICATION_REQUIRED,
    STATUS_MAX_ITERATIONS,
    STATUS_NO_GROUNDED_ANSWER,
    STATUS_REFUSED_MISSING_INFORMATION,
    STATUS_TECHNICAL_ERROR,
    apply_regulations_precedence,
    classify_outcome,
    detect_contradictions,
)
from tests.fixtures.fake_anthropic import FakeAnthropicClient, FakeResponse, TextBlock, ToolUseBlock
from tests.fixtures.stub_tools import build_stub_registry


def test_successful_grounded_factual_answer_with_citation():
    client = FakeAnthropicClient([
        FakeResponse(
            content=[ToolUseBlock(id="call_1", name="get_course", input={"course_number": "0111401"})],
            stop_reason="tool_use",
        ),
        FakeResponse(
            content=[TextBlock("מבוא למדעי המחשב, 5 נקודות זכות (שנתון, עמוד 9).")],
            stop_reason="end_turn",
        ),
    ])

    loop_result = answer_question(
        "כמה נקודות זכות במבוא למדעי המחשב?",
        client=client,
        tool_registry=build_stub_registry(),
        max_iterations=5,
    )
    policy = classify_outcome(loop_result)

    assert policy["status"] == STATUS_ANSWERED
    assert policy["answer"] == "מבוא למדעי המחשב, 5 נקודות זכות (שנתון, עמוד 9)."
    assert policy["contradictions"] == []


def test_missing_information_returns_exact_refusal_string():
    client = FakeAnthropicClient([
        FakeResponse(
            content=[ToolUseBlock(id="call_1", name="search", input={"query": "שעות קבלה של המזכירות"})],
            stop_reason="tool_use",
        ),
        FakeResponse(
            content=[TextBlock("לא נמצא מידע.")],
            stop_reason="end_turn",
        ),
    ])

    loop_result = answer_question(
        "מהן שעות הקבלה של המזכירות האקדמית?",
        client=client,
        tool_registry=build_stub_registry(),
        max_iterations=5,
    )
    policy = classify_outcome(loop_result)

    assert policy["status"] == STATUS_REFUSED_MISSING_INFORMATION
    assert policy["answer"] == REFUSAL_TEXT
    assert policy["answer"] == "לא מופיע במסמכים"


def test_technical_failure_does_not_return_refusal_string():
    def boom(**kwargs):
        raise RuntimeError("db is locked")

    registry = build_stub_registry()
    registry["search"] = boom

    client = FakeAnthropicClient([
        FakeResponse(
            content=[ToolUseBlock(id="call_1", name="search", input={"query": "אלגוריתמים"})],
            stop_reason="tool_use",
        ),
        FakeResponse(content=[TextBlock("תשובה.")], stop_reason="end_turn"),
    ])

    loop_result = answer_question(
        "חפש אלגוריתמים", client=client, tool_registry=registry, max_iterations=5,
    )
    policy = classify_outcome(loop_result)

    assert policy["status"] == STATUS_TECHNICAL_ERROR
    assert policy["answer"] is None
    assert policy["answer"] != REFUSAL_TEXT
    assert "db is locked" in policy["message"]


def test_api_failure_does_not_return_refusal_string():
    class ExplodingClient:
        class messages:
            @staticmethod
            def create(**kwargs):
                raise ConnectionError("network unreachable")

    loop_result = answer_question(
        "שאלה כלשהי", client=ExplodingClient(), tool_registry=build_stub_registry(), max_iterations=5,
    )
    policy = classify_outcome(loop_result)

    assert policy["status"] == STATUS_TECHNICAL_ERROR
    assert policy["answer"] is None
    assert policy["answer"] != REFUSAL_TEXT
    assert "network unreachable" in policy["message"]


def test_no_successful_tool_result_cannot_become_factual_answer():
    client = FakeAnthropicClient([
        FakeResponse(content=[TextBlock("התשובה היא 42 נקודות זכות.")], stop_reason="end_turn"),
    ])

    loop_result = answer_question(
        "כמה נקודות זכות בשנה ג'?", client=client, tool_registry=build_stub_registry(), max_iterations=5,
    )
    policy = classify_outcome(loop_result)

    assert policy["status"] == STATUS_REFUSED_MISSING_INFORMATION
    assert policy["answer"] == REFUSAL_TEXT


def test_ambiguous_curriculum_does_not_silently_choose_one():
    client = FakeAnthropicClient([
        FakeResponse(
            content=[ToolUseBlock(
                id="call_1", name="get_course_table",
                input={"curriculum": "not_a_real_curriculum", "year": 2, "semester": 4},
            )],
            stop_reason="tool_use",
        ),
        FakeResponse(
            content=[TextBlock("אנא ציין תוכנית לימודים: חד־חוגי סתיו / חד־חוגי אביב.")],
            stop_reason="end_turn",
        ),
    ])

    loop_result = answer_question(
        "כמה נקודות זכות בשנה ב סמסטר 4?", client=client, tool_registry=build_stub_registry(), max_iterations=5,
    )
    policy = classify_outcome(loop_result)

    assert policy["status"] == STATUS_CLARIFICATION_REQUIRED
    assert policy["answer"] != REFUSAL_TEXT


def test_ambiguity_produces_clarification_behavior_with_options_listed():
    client = FakeAnthropicClient([
        FakeResponse(
            content=[ToolUseBlock(
                id="call_1", name="get_course_table",
                input={"curriculum": "not_a_real_curriculum", "year": 2, "semester": 4},
            )],
            stop_reason="tool_use",
        ),
        FakeResponse(content=[TextBlock("יש כמה תוכניות אפשריות.")], stop_reason="end_turn"),
    ])

    loop_result = answer_question(
        "כמה נקודות זכות בשנה ב סמסטר 4?", client=client, tool_registry=build_stub_registry(), max_iterations=5,
    )
    policy = classify_outcome(loop_result)

    assert policy["status"] == STATUS_CLARIFICATION_REQUIRED
    assert policy["options"] == ["single_major_fall"]


def test_contradictory_sources_are_surfaced_with_both_citations():
    tool_calls = [
        {
            "iteration": 1,
            "name": "get_course",
            "input": {"course_number": "0122407"},
            "is_error": False,
            "result": {
                "course_number": "0122407",
                "credits": 5,
                "source": "שנתון תשפז- מדעי המחשב.pdf",
                "page": 10,
            },
        },
        {
            "iteration": 2,
            "name": "get_course",
            "input": {"course_number": "0122407"},
            "is_error": False,
            "result": {
                "course_number": "0122407",
                "credits": 4,
                "source": "תקנון לתואר ראשון - תשפו.pdf",
                "page": 3,
            },
        },
    ]

    contradictions = detect_contradictions(tool_calls)

    assert len(contradictions) == 1
    values = {v["value"] for v in contradictions[0]["values"]}
    assert values == {5, 4}
    citations = [v["citation"] for v in contradictions[0]["values"]]
    assert {"source": "שנתון תשפז- מדעי המחשב.pdf", "page": 10} in citations
    assert {"source": "תקנון לתואר ראשון - תשפו.pdf", "page": 3} in citations


def test_regulations_precedence_applies_only_to_regulations_vs_yearbook_conflicts():
    tool_calls = [
        {"iteration": 1, "name": "get_course", "input": {}, "is_error": False, "result": {
            "course_number": "0122407", "credits": 5, "source": "שנתון תשפז- מדעי המחשב.pdf", "page": 10,
        }},
        {"iteration": 2, "name": "get_course", "input": {}, "is_error": False, "result": {
            "course_number": "0122407", "credits": 4, "source": "תקנון לתואר ראשון - תשפו.pdf", "page": 3,
        }},
    ]
    contradiction = detect_contradictions(tool_calls)[0]
    preferred = apply_regulations_precedence(contradiction)
    assert preferred["value"] == 4
    assert preferred["document_type"] == "regulations"

    # Two yearbook-only sources disagreeing: precedence rule does not apply.
    yearbook_only_calls = [
        {"iteration": 1, "name": "get_course", "input": {}, "is_error": False, "result": {
            "course_number": "0122407", "credits": 5, "source": "שנתון תשפז- מדעי המחשב.pdf", "page": 10,
        }},
        {"iteration": 2, "name": "get_course", "input": {}, "is_error": False, "result": {
            "course_number": "0122407", "credits": 6, "source": "שנתון תשפז- מדעי המחשב.pdf", "page": 21,
        }},
    ]
    yearbook_contradiction = detect_contradictions(yearbook_only_calls)[0]
    assert apply_regulations_precedence(yearbook_contradiction) is None


def test_uncited_factual_answer_is_rejected():
    loop_result = {
        "answer": "יש 20 נקודות זכות.",
        "status": "answered",
        "grounded": True,
        "iterations": 1,
        "hit_iteration_cap": False,
        "tool_calls": [
            {
                "iteration": 1,
                "name": "search",
                "input": {"query": "נקודות זכות"},
                "is_error": False,
                "result": {"total_credits": 20},  # no source/page/citation at all
            }
        ],
        "traces": [],
        "messages": [],
    }

    policy = classify_outcome(loop_result)

    assert policy["status"] == STATUS_NO_GROUNDED_ANSWER
    assert policy["answer"] is None


def test_computed_aggregation_answer_requires_contributing_citations():
    loop_result = {
        "answer": "סה\"כ 18.5 נקודות זכות בשנה ב סמסטר 4.",
        "status": "answered",
        "grounded": True,
        "iterations": 1,
        "hit_iteration_cap": False,
        "tool_calls": [
            {
                "iteration": 1,
                "name": "get_course_table",
                "input": {"curriculum": "single_major_fall", "year": 2, "semester": 4},
                "is_error": False,
                "result": {
                    "curriculum": "single_major_fall",
                    "year": 2,
                    "semester": 4,
                    "rows": [{"course_number": "0122407", "credits": 5}],
                    "totals": {"credits": 18.5},
                    "citation": {"source": "שנתון תשפז- מדעי המחשב.pdf", "page": 10},
                },
            }
        ],
        "traces": [],
        "messages": [],
    }

    policy = classify_outcome(loop_result)

    assert policy["status"] == STATUS_ANSWERED
    assert policy["answer"] == "סה\"כ 18.5 נקודות זכות בשנה ב סמסטר 4."


def test_max_iteration_outcome_is_not_mislabeled_as_missing_information():
    responses = [
        FakeResponse(
            content=[ToolUseBlock(id=f"call_{i}", name="list_sections", input={})],
            stop_reason="tool_use",
        )
        for i in range(5)
    ]
    client = FakeAnthropicClient(responses)

    loop_result = answer_question(
        "שאלה שלא נגמרת", client=client, tool_registry=build_stub_registry(), max_iterations=5,
    )
    policy = classify_outcome(loop_result)

    assert policy["status"] == STATUS_MAX_ITERATIONS
    assert policy["answer"] is None
    assert policy["answer"] != REFUSAL_TEXT
