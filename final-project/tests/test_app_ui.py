"""
Owner: Person 3

Tests for UI-adjacent Streamlit behavior without launching a browser.
The production app renders the display models prepared here; these
tests verify status mapping, citation preservation, debug safety, and
local API-key setup behavior without real Anthropic calls.
"""

import pytest

from agent.system_prompt import (
    REFUSAL_TEXT,
    STATUS_ANSWERED,
    STATUS_CLARIFICATION_REQUIRED,
    STATUS_MAX_ITERATIONS,
    STATUS_NO_GROUNDED_ANSWER,
    STATUS_REFUSED_MISSING_INFORMATION,
    STATUS_TECHNICAL_ERROR,
)
from agent.ui import (
    MISSING_API_KEY_MESSAGE,
    TechnicalSetupError,
    create_anthropic_client,
    extract_citations,
    prepare_display,
)


def test_missing_api_key_is_handled_gracefully(tmp_path):
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("ANTHROPIC_API_KEY=your-api-key-here\n", encoding="utf-8")

    with pytest.raises(TechnicalSetupError) as exc:
        create_anthropic_client(env={}, dotenv_path=dotenv_path)

    assert str(exc.value) == MISSING_API_KEY_MESSAGE


def test_answered_status_maps_to_answer_rendering():
    display = prepare_display(
        {"status": STATUS_ANSWERED, "answer": "תשובה עם מקור."},
        loop_result={},
        metrics={},
    )

    assert display["kind"] == "answer"
    assert display["body"] == "תשובה עם מקור."


def test_refused_missing_information_maps_to_exact_refusal_text():
    display = prepare_display(
        {"status": STATUS_REFUSED_MISSING_INFORMATION, "answer": REFUSAL_TEXT},
        loop_result={},
        metrics={},
    )

    assert display["kind"] == "missing_information"
    assert display["body"] == "לא מופיע במסמכים"


def test_clarification_required_renders_text_and_options():
    display = prepare_display(
        {
            "status": STATUS_CLARIFICATION_REQUIRED,
            "answer": "איזו תוכנית לימודים רלוונטית?",
            "options": ["single_major_fall", "dual_major_spring"],
        },
        loop_result={},
        metrics={},
    )

    assert display["kind"] == "clarification"
    assert display["body"] == "איזו תוכנית לימודים רלוונטית?"
    assert display["options"] == ["single_major_fall", "dual_major_spring"]


def test_technical_error_does_not_render_refusal_string():
    display = prepare_display(
        {"status": STATUS_TECHNICAL_ERROR, "answer": None, "message": "network unreachable"},
        loop_result={},
        metrics={},
    )

    assert display["kind"] == "technical_error"
    assert display["body"] == "network unreachable"
    assert display["body"] != REFUSAL_TEXT


def test_max_iterations_handled_safely():
    display = prepare_display({"status": STATUS_MAX_ITERATIONS, "answer": None})

    assert display["kind"] == "max_iterations"
    assert display["body"]
    assert display["body"] != REFUSAL_TEXT


def test_no_grounded_answer_handled_safely():
    display = prepare_display({"status": STATUS_NO_GROUNDED_ANSWER, "answer": None})

    assert display["kind"] == "no_grounded_answer"
    assert display["body"]
    assert display["body"] != REFUSAL_TEXT


def test_citations_source_metadata_are_preserved_for_display():
    loop_result = {
        "tool_calls": [
            {
                "is_error": False,
                "result": {
                    "course_number": "0111401",
                    "source": "שנתון תשפז - מדעי המחשב.pdf",
                    "page": 9,
                },
            },
            {
                "is_error": False,
                "result": {
                    "citations": [
                        {
                            "source": "תקנון לתואר ראשון.pdf",
                            "page_start": 3,
                            "page_end": 4,
                            "section_title": "משך הלימודים",
                        }
                    ]
                },
            },
        ]
    }

    citations = extract_citations(loop_result=loop_result)

    assert "שנתון תשפז - מדעי המחשב.pdf | עמוד 9" in citations
    assert "תקנון לתואר ראשון.pdf | משך הלימודים | עמודים 3-4" in citations


def test_metrics_debug_data_can_render_model_without_missing_fields_crashing():
    display = prepare_display(
        {"status": STATUS_ANSWERED, "answer": "תשובה"},
        loop_result={"tool_calls": [{"name": "search"}]},
        metrics={"tool_call_count": 1},
    )

    assert display["debug"]["metrics"]["tool_call_count"] == 1
    assert display["debug"]["tool_trace"] == [{"name": "search"}]
