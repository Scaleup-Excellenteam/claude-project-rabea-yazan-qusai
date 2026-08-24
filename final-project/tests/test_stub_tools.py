"""
Owner: Person 3

Tests for the contract-shaped stub tool fixtures used to build/test
the agent loop before Person 1/2's real tools land, per SPEC.md
section 5 and PERSON_3_AGENT_UI.md.
"""

from tests.fixtures.stub_tools import build_stub_registry


def test_registry_exposes_exactly_the_expected_tool_family():
    registry = build_stub_registry()
    assert set(registry.keys()) == {
        "list_sections",
        "get_section",
        "search",
        "list_curricula",
        "get_course_table",
        "get_course",
    }


def test_list_sections_returns_concise_metadata_list():
    registry = build_stub_registry()
    sections = registry["list_sections"]()
    assert isinstance(sections, list) and sections
    entry = sections[0]
    assert set(entry.keys()) >= {"section_id", "title", "source", "page_start", "page_end"}
    assert "text" not in entry


def test_get_section_known_id_returns_text_and_citations():
    registry = build_stub_registry()
    sections = registry["list_sections"]()
    known_id = sections[0]["section_id"]
    result = registry["get_section"](section_id=known_id)
    assert result["section_id"] == known_id
    assert isinstance(result["text"], str) and result["text"]
    assert isinstance(result["citations"], list) and result["citations"]


def test_get_section_unknown_id_returns_structured_error_not_empty_text():
    registry = build_stub_registry()
    result = registry["get_section"](section_id="does-not-exist")
    assert result["error"] == "not_found"


def test_search_known_term_returns_ranked_results_with_citation_fields():
    registry = build_stub_registry()
    results = registry["search"](query="מבוא למדעי המחשב")
    assert isinstance(results, list) and results
    entry = results[0]
    assert set(entry.keys()) >= {"section_id", "title", "snippet", "score", "source", "page_start", "page_end"}


def test_search_unmatched_term_returns_empty_list():
    registry = build_stub_registry()
    results = registry["search"](query="קורס שלא קיים בכלל")
    assert results == []


def test_list_curricula_returns_ids_and_display_names():
    registry = build_stub_registry()
    curricula = registry["list_curricula"]()
    assert isinstance(curricula, list) and curricula
    entry = curricula[0]
    assert set(entry.keys()) >= {"curriculum_id", "name", "degree_type", "start_term"}


def test_get_course_table_valid_curriculum_returns_rows_and_totals():
    registry = build_stub_registry()
    table = registry["get_course_table"](curriculum="single_major_fall", year=2, semester=4)
    assert table["curriculum"] == "single_major_fall"
    assert isinstance(table["rows"], list) and table["rows"]
    assert "credits" in table["totals"]
    assert "citation" in table


def test_get_course_table_unknown_curriculum_returns_ambiguity_error_with_options():
    registry = build_stub_registry()
    result = registry["get_course_table"](curriculum="not_a_real_curriculum", year=2, semester=4)
    assert result["error"] == "ambiguous_curriculum"
    assert isinstance(result["valid_curricula"], list) and result["valid_curricula"]


def test_get_course_known_number_returns_row():
    registry = build_stub_registry()
    course = registry["get_course"](course_number="0111401")
    assert course["course_number"] == "0111401"
    assert "credits" in course


def test_get_course_unknown_number_returns_structured_error():
    registry = build_stub_registry()
    result = registry["get_course"](course_number="9999999")
    assert result["error"] == "not_found"
