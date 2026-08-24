"""
Owner: Person 2

Unit tests for extract/catalog.py per-course catalog record extraction
(yearbook pp. 25-45, prose blocks rather than geometric tables).
"""

import pdfplumber

from extract.catalog import extract_catalog_courses, parse_course_metadata_line
from tests.support import YEARBOOK_PDF


def test_parse_course_metadata_line_extracts_number_hours_credits():
    result = parse_course_metadata_line('0111401, 4 ש"ס, 5 נ"ז')
    assert result == {"course_number": "0111401", "hours": 4, "credits": 5}


def test_parse_course_metadata_line_handles_decimal_credits():
    result = parse_course_metadata_line('0121503, 3 ש"ס, 3.5 נ"ז')
    assert result["credits"] == 3.5


def test_parse_course_metadata_line_non_matching_returns_none():
    assert parse_course_metadata_line("סוג שיעור: הרצאה") is None


def test_extract_catalog_courses_finds_known_course():
    with pdfplumber.open(YEARBOOK_PDF) as pdf:
        courses = extract_catalog_courses(pdf, pages=range(25, 46))

    intro_cs = [c for c in courses if c["course_number"] == "0111401"]
    assert len(intro_cs) == 1
    assert "מבוא למדעי המחשב" in intro_cs[0]["course_name"]
    assert intro_cs[0]["credits"] == 5
    assert intro_cs[0]["page"] == 26


def test_extract_catalog_courses_preserves_prerequisites_verbatim():
    with pdfplumber.open(YEARBOOK_PDF) as pdf:
        courses = extract_catalog_courses(pdf, pages=range(25, 46))

    algorithms1 = next(c for c in courses if c["course_number"] == "0122407")
    assert algorithms1["prerequisites_text"] == "פרקים במבני נתונים"


def test_extract_catalog_courses_duplicate_course_number_returns_both():
    with pdfplumber.open(YEARBOOK_PDF) as pdf:
        courses = extract_catalog_courses(pdf, pages=range(25, 46))

    duplicates = [c for c in courses if c["course_number"] == "0121503"]
    assert len(duplicates) == 2
    names = {c["course_name"] for c in duplicates}
    credits = {c["credits"] for c in duplicates}
    assert len(names) == 2
    assert credits == {3.5, 3}
