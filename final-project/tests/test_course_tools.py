"""
Owner: Person 2

Unit tests for tools/course_tools.py: list_curricula, get_course_table,
get_course - matching the JSON shapes in SPEC.md section 5.
"""

import pytest

from index.build_courses import CURRICULA, build_courses_db
from tests.support import YEARBOOK_PDF
from tools.course_tools import get_course, get_course_table, list_curricula


@pytest.fixture(scope="module")
def db_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "courses.db"
    build_courses_db(YEARBOOK_PDF, path)
    return path


def test_list_curricula_returns_all_six(db_path):
    curricula = list_curricula(db_path=db_path)
    assert len(curricula) == len(CURRICULA)
    ids = {c["curriculum_id"] for c in curricula}
    assert "single_major_fall" in ids
    assert "computational_biology" in ids


def test_list_curricula_shape(db_path):
    curricula = list_curricula(db_path=db_path)
    single_fall = next(c for c in curricula if c["curriculum_id"] == "single_major_fall")
    assert single_fall["degree_type"] == "B.Sc."
    assert single_fall["start_term"] == "fall"
    assert single_fall["page_start"] == 9
    assert single_fall["page_end"] == 10


@pytest.mark.parametrize(
    "curriculum",
    [
        "single_major_fall",
        "single_major_spring",
        "support_center_spread",
        "dual_major_spring",
    ],
)
def test_get_course_table_year_2_semester_4_has_rows(db_path, curriculum):
    result = get_course_table(curriculum, 2, 4, db_path=db_path)
    assert result["rows"], f"{curriculum} year 2 semester 4 should have rows"
    assert result["curriculum"] == curriculum


def test_get_course_table_five_curricula_are_distinguishable(db_path):
    curricula = [
        "single_major_fall",
        "single_major_spring",
        "support_center_spread",
        "dual_major_fall",
        "dual_major_spring",
    ]
    course_number_sets = []
    for curriculum in curricula:
        result = get_course_table(curriculum, 2, 4, db_path=db_path)
        numbers = frozenset(r["course_number"] for r in result["rows"] if r["course_number"])
        course_number_sets.append(numbers)

    # Not all five tables are identical - at least one differs from the rest.
    assert len(set(course_number_sets)) > 1


def test_get_course_table_totals_credits_decimal_parses_correctly(db_path):
    result = get_course_table("single_major_fall", 2, 4, db_path=db_path)
    assert result["totals"]["credits"] == 18.5


def test_get_course_table_unknown_curriculum_returns_structured_error(db_path):
    result = get_course_table("does_not_exist", 2, 4, db_path=db_path)
    assert result["error"] == "unknown_curriculum"
    assert "single_major_fall" in result["valid_curricula"]


def test_get_course_table_ambiguous_curriculum_returns_structured_error(db_path):
    result = get_course_table(None, 2, 4, db_path=db_path)
    assert result["error"] == "ambiguous_curriculum"
    assert len(result["valid_curricula"]) == len(CURRICULA)


def test_get_course_table_empty_table_edge_case(db_path):
    result = get_course_table("computational_biology", 2, 4, db_path=db_path)
    assert result["rows"] == []
    assert result["totals"] is None
    assert "note" in result


def test_get_course_duplicate_course_number_returns_both(db_path):
    results = get_course("0121503", db_path=db_path)
    assert len(results) == 2
    credits = {r["credits"] for r in results}
    assert credits == {3.5, 3}


def test_get_course_by_name_substring(db_path):
    results = get_course("אלגוריתמים 1", db_path=db_path)
    assert any(r["course_number"] == "0122407" for r in results)


def test_get_course_unknown_returns_empty_list(db_path):
    assert get_course("קורס שלא קיים בשום מקום", db_path=db_path) == []
