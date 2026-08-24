"""
Owner: Person 2

Integration tests for index/build_courses.py: builds a real SQLite DB
from the yearbook PDF and checks the structured data landed correctly.
"""

import sqlite3

import pytest

from index.build_courses import CURRICULA, build_courses_db
from tests.support import YEARBOOK_PDF


@pytest.fixture(scope="module")
def db_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "courses.db"
    build_courses_db(YEARBOOK_PDF, path)
    return path


def test_curricula_table_has_six_curricula(db_path):
    conn = sqlite3.connect(db_path)
    (count,) = conn.execute("SELECT COUNT(*) FROM curricula").fetchone()
    conn.close()
    assert count == len(CURRICULA) == 6


def test_courses_table_has_five_curricula_at_year_2_semester_4(db_path):
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT DISTINCT curriculum_id FROM courses WHERE year = 2 AND semester = 4"
    ).fetchall()
    conn.close()
    curricula_with_year2_sem4 = {row[0] for row in rows}
    assert curricula_with_year2_sem4 == {
        "single_major_fall",
        "single_major_spring",
        "support_center_spread",
        "dual_major_fall",
        "dual_major_spring",
    }


def test_computational_biology_has_no_year_semester_rows(db_path):
    conn = sqlite3.connect(db_path)
    (count,) = conn.execute(
        "SELECT COUNT(*) FROM courses "
        "WHERE curriculum_id = 'computational_biology' AND year IS NOT NULL"
    ).fetchone()
    (total,) = conn.execute(
        "SELECT COUNT(*) FROM courses WHERE curriculum_id = 'computational_biology'"
    ).fetchone()
    conn.close()
    assert count == 0
    assert total > 0


def test_catalog_courses_has_duplicate_course_number(db_path):
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT course_name, credits FROM catalog_courses WHERE course_number = '0121503'"
    ).fetchall()
    conn.close()
    assert len(rows) == 2


def test_cluster_courses_populated(db_path):
    conn = sqlite3.connect(db_path)
    (count,) = conn.execute("SELECT COUNT(*) FROM cluster_courses").fetchone()
    conn.close()
    assert count > 0
