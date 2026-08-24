"""
Owner: Person 1

Tests for tools/text_tools.py (list_sections, get_section, search).

Real PDFs are not available yet, so these tests build a temporary
SQLite database from synthetic Section fixtures using the existing
Checkpoint 4 build_index() function, then exercise the retrieval API
against it. contracts.py is not finalized - see text_tools.py's module
docstring for the documented shape assumptions this relies on.
"""

from __future__ import annotations

import pytest

from extract.sections import Section
from index.build_fts import build_index
from tools.text_tools import get_section, list_sections, search


def _section(
    section_id: str,
    source_id: str = "yb",
    title: str = "Heading",
    text: str = "Body text.",
    page_start: int = 1,
    page_end: int = 1,
    section_order: int = 0,
) -> Section:
    return Section(
        section_id=section_id,
        source_id=source_id,
        title=title,
        normalized_title=title,
        parent_section_id=None,
        page_start=page_start,
        page_end=page_end,
        section_order=section_order,
        text=text,
        text_quality_notes=None,
    )


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "app.db"


def test_list_sections_returns_metadata_in_deterministic_order(db_path) -> None:
    sections = [
        _section("yb:002:B", title="B", page_start=2, page_end=2, section_order=1),
        _section("yb:001:A", title="A", page_start=1, page_end=1, section_order=0),
    ]
    build_index(db_path, sections)

    result = list_sections(db_path)

    assert [r["section_id"] for r in result] == ["yb:001:A", "yb:002:B"]
    for r in result:
        assert set(r.keys()) == {
            "section_id",
            "source_id",
            "title",
            "page_start",
            "page_end",
            "section_order",
        }
    assert "text" not in result[0]


def test_list_sections_is_stable_across_repeated_calls(db_path) -> None:
    sections = [_section("yb:001:A"), _section("yb:002:B", page_start=2, page_end=2, section_order=1)]
    build_index(db_path, sections)

    first = list_sections(db_path)
    second = list_sections(db_path)

    assert first == second


def test_list_sections_works_with_multiple_sources(db_path) -> None:
    sections = [
        _section("yb:001:A", source_id="yearbook", title="A"),
        _section("reg:001:B", source_id="regulations", title="B"),
    ]
    build_index(db_path, sections)

    all_sections = list_sections(db_path)
    yearbook_only = list_sections(db_path, source_id="yearbook")

    assert {r["source_id"] for r in all_sections} == {"yearbook", "regulations"}
    assert [r["section_id"] for r in yearbook_only] == ["yb:001:A"]


def test_get_section_returns_full_section_data(db_path) -> None:
    section = _section("yb:001:A", title="A", text="Full body text.", page_start=3, page_end=4)
    build_index(db_path, [section])

    result = get_section(db_path, "yb:001:A")

    assert result["section_id"] == "yb:001:A"
    assert result["source_id"] == "yb"
    assert result["title"] == "A"
    assert result["text"] == "Full body text."
    assert result["page_start"] == 3
    assert result["page_end"] == 4
    assert result["citations"] == [{"source_id": "yb", "page_start": 3, "page_end": 4}]
    assert "error" not in result


def test_get_section_missing_id_returns_structured_error_not_empty_text(db_path) -> None:
    build_index(db_path, [_section("yb:001:A")])

    result = get_section(db_path, "does-not-exist")

    assert result == {"section_id": "does-not-exist", "error": "section_not_found"}
    assert "text" not in result


def test_search_finds_matching_hebrew_text(db_path) -> None:
    section = _section(
        "yb:001:Hebrew",
        title="פרק ראשון",
        text="חובת השתתפות לימודים ותרגילים.",
    )
    build_index(db_path, [section])

    results = search(db_path, "לימודים")

    assert len(results) == 1
    assert results[0]["section_id"] == "yb:001:Hebrew"
    assert "לימודים" in results[0]["snippet"]


def test_search_respects_bm25_ranking_order(db_path) -> None:
    sections = [
        _section("yb:002:B", title="אחר", text="לימודים פעם אחת"),
        _section("yb:001:A", title="לימודים", text="לימודים לימודים לימודים"),
    ]
    build_index(db_path, sections)

    results = search(db_path, "לימודים")

    assert [r["section_id"] for r in results] == ["yb:001:A", "yb:002:B"]
    assert results[0]["score"] <= results[1]["score"]


def test_search_respects_limit(db_path) -> None:
    sections = [
        _section(f"yb:{i:03d}:S{i}", title=f"S{i}", text="לימודים", page_start=i, page_end=i, section_order=i)
        for i in range(1, 6)
    ]
    build_index(db_path, sections)

    results = search(db_path, "לימודים", limit=2)

    assert len(results) == 2


def test_search_limit_is_capped_at_ten(db_path) -> None:
    sections = [
        _section(f"yb:{i:03d}:S{i}", title=f"S{i}", text="לימודים", page_start=i, page_end=i, section_order=i)
        for i in range(1, 21)
    ]
    build_index(db_path, sections)

    results = search(db_path, "לימודים", limit=1000)

    assert len(results) == 10


def test_search_no_matches_returns_empty_list(db_path) -> None:
    build_index(db_path, [_section("yb:001:A", text="something else entirely")])

    results = search(db_path, "לימודים")

    assert results == []


def test_search_preserves_page_metadata(db_path) -> None:
    section = _section("yb:001:A", text="לימודים", page_start=9, page_end=10)
    build_index(db_path, [section])

    results = search(db_path, "לימודים")

    assert results[0]["page_start"] == 9
    assert results[0]["page_end"] == 10
    assert results[0]["source_id"] == "yb"


def test_search_malformed_query_does_not_raise(db_path) -> None:
    build_index(db_path, [_section("yb:001:A", text="לימודים")])

    # Unbalanced quote and a dangling NOT/OR operator are invalid FTS5
    # query syntax on their own - must degrade gracefully, not raise.
    for bad_query in ['"unterminated', "NOT", "OR", '"" OR "', "-"]:
        results = search(db_path, bad_query)
        assert isinstance(results, list)


def test_search_empty_query_returns_empty_list(db_path) -> None:
    build_index(db_path, [_section("yb:001:A")])

    assert search(db_path, "") == []
    assert search(db_path, "   ") == []


def test_empty_database_is_handled_safely(db_path) -> None:
    # No build_index() call at all - db_path doesn't exist yet.
    assert list_sections(db_path) == []
    assert search(db_path, "anything") == []
    assert get_section(db_path, "anything") == {
        "section_id": "anything",
        "error": "section_not_found",
    }
