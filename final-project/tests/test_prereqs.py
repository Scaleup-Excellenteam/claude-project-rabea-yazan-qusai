"""
Owner: Person 2

Unit tests for extract/prereqs.py.
"""

from extract.prereqs import parse_prerequisites


def test_parse_prerequisites_preserves_raw_text_verbatim():
    raw = "פרקים במבני נתונים"
    result = parse_prerequisites(raw)
    assert result["raw"] == raw


def test_parse_prerequisites_extracts_mentioned_course_numbers():
    raw = "חדו״א 1 (0111101), אלגברה ליניארית(מ)"
    result = parse_prerequisites(raw)
    assert result["mentions"] == ["0111101"]


def test_parse_prerequisites_no_course_numbers_is_empty_list():
    result = parse_prerequisites("פרקים במבני נתונים")
    assert result["mentions"] == []


def test_parse_prerequisites_empty_string():
    result = parse_prerequisites("")
    assert result == {"raw": "", "mentions": []}


def test_parse_prerequisites_none_is_none():
    assert parse_prerequisites(None) is None
