"""
Owner: Person 1

End-to-end integration tests for the full Person 1 pipeline:

    PageText -> extract_sections() -> build_index()
             -> list_sections() / get_section() / search()

Real PDFs are still missing, so this uses a synthetic Hebrew
mini-"document" built directly as PageText objects (as if it had
already been extracted and normalized by extract_pdf_pages()), across
two source_ids, with one section spanning multiple pages and one
completely blank page. Unit-level behavior of each stage is already
covered by test_pdf_text.py, test_sections.py, test_build_fts.py, and
test_text_tools.py - this file only checks that the stages compose
correctly together.
"""

from __future__ import annotations

import pytest

from extract.pdf_text import PageText
from extract.sections import extract_sections
from index.build_fts import build_index
from tools.text_tools import get_section, list_sections, search


def _page(source_id: str, page_number: int, text: str) -> PageText:
    return PageText(
        source_id=source_id,
        filename=f"{source_id}.pdf",
        page_number=page_number,
        raw_text=text,
        text=text,
        has_text=bool(text.strip()),
    )


def _yearbook_pages() -> list[PageText]:
    return [
        _page(
            "yearbook",
            1,
            "מבוא\n"
            "זהו טקסט הקדמה.\n"
            "פרק ראשון\n"
            "זהו תחילת הפרק הראשון והוא ממשיך.",
        ),
        _page("yearbook", 2, "פרק ראשון נמשך גם בעמוד השני."),
        _page("yearbook", 3, "פרק שני\nלימודים לימודים לימודים בפרק זה."),
    ]


def _regulations_pages() -> list[PageText]:
    return [
        _page("regulations", 1, "תקנון\nיש חובת השתתפות לימודים אחת בשנה."),
        _page("regulations", 2, ""),  # blank page, no extractable text
    ]


def _build_full_index(db_path):
    """Run the full pipeline and return the extracted sections for comparison."""
    yearbook_sections = extract_sections(_yearbook_pages())
    regulations_sections = extract_sections(_regulations_pages())
    all_sections = yearbook_sections + regulations_sections
    build_index(db_path, all_sections)
    return all_sections


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "app.db"


def test_extract_sections_produces_expected_structure() -> None:
    yearbook_sections = extract_sections(_yearbook_pages())
    regulations_sections = extract_sections(_regulations_pages())

    assert [s.title for s in yearbook_sections] == ["מבוא", "פרק ראשון", "פרק שני"]
    spanning = yearbook_sections[1]
    assert spanning.page_start == 1
    assert spanning.page_end == 2
    assert spanning.text == (
        "זהו תחילת הפרק הראשון והוא ממשיך.\nפרק ראשון נמשך גם בעמוד השני."
    )

    assert [s.title for s in regulations_sections] == ["תקנון"]
    # The blank page 2 must not corrupt the page range of the last section.
    assert regulations_sections[0].page_start == 1
    assert regulations_sections[0].page_end == 1


def test_section_ids_are_stable_from_extraction_through_retrieval(db_path) -> None:
    sections = _build_full_index(db_path)
    extracted_ids = {s.section_id for s in sections}

    listed_ids = {r["section_id"] for r in list_sections(db_path)}
    assert listed_ids == extracted_ids

    for section in sections:
        retrieved = get_section(db_path, section.section_id)
        assert retrieved["section_id"] == section.section_id


def test_page_start_and_page_end_survive_the_full_pipeline(db_path) -> None:
    sections = _build_full_index(db_path)
    spanning = next(s for s in sections if s.title == "פרק ראשון")

    retrieved = get_section(db_path, spanning.section_id)

    assert retrieved["page_start"] == spanning.page_start == 1
    assert retrieved["page_end"] == spanning.page_end == 2


def test_section_text_survives_the_full_pipeline(db_path) -> None:
    sections = _build_full_index(db_path)
    spanning = next(s for s in sections if s.title == "פרק ראשון")

    retrieved = get_section(db_path, spanning.section_id)

    assert retrieved["text"] == spanning.text


def test_multiple_sections_are_indexed(db_path) -> None:
    sections = _build_full_index(db_path)

    assert len(sections) == 4
    assert len(list_sections(db_path)) == 4


def test_multiple_sources_coexist_end_to_end(db_path) -> None:
    _build_full_index(db_path)

    yearbook_only = list_sections(db_path, source_id="yearbook")
    regulations_only = list_sections(db_path, source_id="regulations")

    assert len(yearbook_only) == 3
    assert len(regulations_only) == 1
    assert all(r["source_id"] == "yearbook" for r in yearbook_only)
    assert all(r["source_id"] == "regulations" for r in regulations_only)


def test_list_sections_returns_expected_metadata(db_path) -> None:
    sections = _build_full_index(db_path)

    result = list_sections(db_path)
    result_by_id = {r["section_id"]: r for r in result}

    for section in sections:
        r = result_by_id[section.section_id]
        assert r["title"] == section.title
        assert r["source_id"] == section.source_id
        assert r["page_start"] == section.page_start
        assert r["page_end"] == section.page_end
        assert "text" not in r


def test_get_section_returns_expected_full_section(db_path) -> None:
    sections = _build_full_index(db_path)
    target = next(s for s in sections if s.title == "פרק שני")

    result = get_section(db_path, target.section_id)

    assert result["title"] == "פרק שני"
    assert result["text"] == target.text
    assert result["citations"] == [
        {
            "source_id": target.source_id,
            "page_start": target.page_start,
            "page_end": target.page_end,
        }
    ]


def test_hebrew_search_returns_the_correct_section(db_path) -> None:
    sections = _build_full_index(db_path)
    target = next(s for s in sections if s.title == "פרק שני")

    results = search(db_path, "לימודים")

    result_ids = [r["section_id"] for r in results]
    assert target.section_id in result_ids


def test_bm25_ranking_is_sensible_across_multiple_matching_sections(db_path) -> None:
    _build_full_index(db_path)

    results = search(db_path, "לימודים")

    # "פרק שני" repeats the term 3x, the regulations section only once -
    # denser section should rank first (more negative/lower bm25 score).
    assert len(results) == 2
    titles = [r["title"] for r in results]
    assert titles[0] == "פרק שני"
    assert titles[1] == "תקנון"
    assert results[0]["score"] <= results[1]["score"]


def test_zero_match_search_returns_empty_list(db_path) -> None:
    _build_full_index(db_path)

    assert search(db_path, "קוונטים") == []


def test_rebuilding_the_full_index_does_not_duplicate_sections(db_path) -> None:
    sections = _build_full_index(db_path)
    build_index(db_path, sections)  # rebuild with the same extracted sections

    assert len(list_sections(db_path)) == 4


def test_repeated_full_pipeline_runs_are_deterministic(tmp_path) -> None:
    db_path_a = tmp_path / "a.db"
    db_path_b = tmp_path / "b.db"

    sections_a = _build_full_index(db_path_a)
    sections_b = _build_full_index(db_path_b)

    assert [s.section_id for s in sections_a] == [s.section_id for s in sections_b]
    assert list_sections(db_path_a) == list_sections(db_path_b)

    results_a = search(db_path_a, "לימודים")
    results_b = search(db_path_b, "לימודים")
    assert [r["section_id"] for r in results_a] == [r["section_id"] for r in results_b]
