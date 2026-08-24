"""
Owner: Person 1

Tests for extract/sections.py.

Real PDFs are not available in this repository yet, so these tests
build synthetic PageText objects directly (PageText already represents
normalized, per-page text as produced by extract_pdf_pages - see
tests/test_pdf_text.py for extraction-level tests). Heading detection
here is a conservative heuristic and will likely need tuning once real
documents are checked in - see extract/sections.py's module docstring.
"""

from __future__ import annotations

import pytest

from extract.pdf_text import PageText
from extract.sections import extract_sections


def _page(source_id: str, page_number: int, text: str) -> PageText:
    return PageText(
        source_id=source_id,
        filename="doc.pdf",
        page_number=page_number,
        raw_text=text,
        text=text,
        has_text=bool(text.strip()),
    )


def test_one_section_on_one_page() -> None:
    pages = [
        _page("yb", 1, "Intro Heading\nSome body text here.\nMore body text."),
    ]

    sections = extract_sections(pages)

    assert len(sections) == 1
    section = sections[0]
    assert section.title == "Intro Heading"
    assert section.page_start == 1
    assert section.page_end == 1
    assert section.section_order == 0
    assert section.text == "Some body text here.\nMore body text."
    assert section.source_id == "yb"
    assert section.parent_section_id is None


def test_section_spanning_multiple_pages() -> None:
    pages = [
        _page("yb", 1, "Chapter One\nLine A on page one."),
        _page("yb", 2, "Line B on page two."),
    ]

    sections = extract_sections(pages)

    assert len(sections) == 1
    section = sections[0]
    assert section.title == "Chapter One"
    assert section.page_start == 1
    assert section.page_end == 2
    assert section.text == "Line A on page one.\nLine B on page two."


def test_multiple_sections_on_one_page() -> None:
    pages = [
        _page("yb", 5, "Heading A\nBody A text.\nHeading B\nBody B text."),
    ]

    sections = extract_sections(pages)

    assert [s.title for s in sections] == ["Heading A", "Heading B"]
    assert [s.section_order for s in sections] == [0, 1]
    assert all(s.page_start == 5 and s.page_end == 5 for s in sections)
    assert sections[0].text == "Body A text."
    assert sections[1].text == "Body B text."


def test_repeated_similar_titles_get_distinct_ids() -> None:
    pages = [
        _page("yb", 1, "הערות\nText1.\nהערות\nText2."),
    ]

    sections = extract_sections(pages)

    assert len(sections) == 2
    assert sections[0].title == sections[1].title == "הערות"
    ids = [s.section_id for s in sections]
    assert len(set(ids)) == 2
    assert ids[1] == f"{ids[0]}-2"


def test_repeated_titles_on_different_pages_get_naturally_distinct_ids() -> None:
    pages = [
        _page("yb", 1, "הערות\nText1."),
        _page("yb", 2, "הערות\nText2."),
    ]

    sections = extract_sections(pages)

    ids = [s.section_id for s in sections]
    assert len(set(ids)) == 2
    assert not ids[1].endswith("-2")


def test_pages_with_no_text_do_not_break_a_spanning_section() -> None:
    pages = [
        _page("yb", 1, "Chapter One\nLine A."),
        _page("yb", 2, ""),
        _page("yb", 3, "Line B continues."),
    ]

    sections = extract_sections(pages)

    assert len(sections) == 1
    section = sections[0]
    assert section.page_start == 1
    assert section.page_end == 3
    assert section.text == "Line A.\nLine B continues."


def test_leading_body_text_before_any_heading_is_not_dropped() -> None:
    pages = [
        _page("yb", 1, "This is a sentence.\nMore text follows."),
    ]

    sections = extract_sections(pages)

    assert len(sections) == 1
    # First line is adopted as the implicit leading title even though it
    # ends with a period and would not otherwise pass the heading check.
    assert sections[0].title == "This is a sentence."
    assert sections[0].text == "More text follows."


def test_section_ids_are_stable_across_repeated_runs() -> None:
    pages = [
        _page("yb", 1, "Heading A\nBody A."),
        _page("yb", 2, "Heading B\nBody B."),
    ]

    first_run_ids = [s.section_id for s in extract_sections(pages)]
    second_run_ids = [s.section_id for s in extract_sections(pages)]

    assert first_run_ids == second_run_ids
    assert first_run_ids  # sanity: not empty


def test_no_random_uuid_like_ids() -> None:
    pages = [_page("yb", 1, "Heading A\nBody A.")]

    section = extract_sections(pages)[0]

    assert section.section_id == "yb:001:Heading-A"


def test_empty_page_list_returns_no_sections() -> None:
    assert extract_sections([]) == []


def test_all_blank_pages_return_no_sections() -> None:
    pages = [_page("yb", 1, ""), _page("yb", 2, "")]

    assert extract_sections(pages) == []


def test_mixed_source_ids_raise_value_error_instead_of_relabeling() -> None:
    pages = [
        _page("yb", 1, "Heading A\nBody A."),
        _page("reg", 2, "Heading B\nBody B."),
    ]

    with pytest.raises(ValueError):
        extract_sections(pages)


def test_single_source_id_does_not_raise() -> None:
    pages = [
        _page("yb", 1, "Heading A\nBody A."),
        _page("yb", 2, "Heading B\nBody B."),
    ]

    sections = extract_sections(pages)  # must not raise

    assert all(s.source_id == "yb" for s in sections)


def test_real_pdf_noise_stays_body_instead_of_becoming_headings() -> None:
    pages = [_page(
        "yearbook",
        9,
        "מערכת לימודים מוצעת לקורסי החובה\n"
        "0111100 מבוא לחדו\"א 0 4 2 - 6\n"
        "סה\"כ 20 19 10 3 32\n"
        "9",
    )]

    sections = extract_sections(pages)

    assert [s.title for s in sections] == ["מערכת לימודים מוצעת לקורסי החובה"]
    assert "0111100" in sections[0].text
    assert "סה\"כ" in sections[0].text
    assert "\n9" not in sections[0].text


def test_course_metadata_and_instructor_are_body_under_course_title() -> None:
    pages = [_page(
        "yearbook",
        25,
        "מבוא לחדו\"א\n"
        "הגב' אבו סאלח הנד (סמס' א')\n"
        "0111100, 4 ש\"ס, 0 נ\"ז\n"
        "סוג שיעור: הרצאה + 2 ש\"ס תרגיל\n"
        "תיאור משמעותי של הקורס.",
    )]

    sections = extract_sections(pages)

    assert len(sections) == 1
    assert sections[0].title == "מבוא לחדו\"א"
    assert "0111100" in sections[0].text
    assert "סוג שיעור" in sections[0].text


def test_toc_page_is_not_emitted_as_authoritative_prose() -> None:
    pages = [
        _page(
            "regulations",
            1,
            "תוכן עניינים\n"
            "מבוא ................................ 2\n"
            "תנאי קבלה .......................... 3\n"
            "זכאות לתואר ........................ 4",
        ),
        _page("regulations", 2, "מבוא\nזהו גוף משמעותי."),
    ]

    sections = extract_sections(pages)

    assert [s.title for s in sections] == ["מבוא"]
    assert sections[0].page_start == 2


def test_consecutive_real_headings_do_not_create_empty_sections() -> None:
    pages = [_page(
        "yearbook",
        4,
        "תכניות הלימודים\n"
        "תואר ראשון במסלול החד-חוגי\n"
        "זהו גוף משמעותי.",
    )]

    sections = extract_sections(pages)

    assert len(sections) == 1
    assert sections[0].title == "תכניות הלימודים — תואר ראשון במסלול החד-חוגי"
    assert sections[0].text == "זהו גוף משמעותי."
