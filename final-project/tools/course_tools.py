"""
Owner: Person 2

Purpose:
Course-data retrieval tools: list_curricula, get_course_table, get_course.

`contracts.py` does not yet define shared Curriculum/CourseTableRow/
Course/citation types (see CURRENT_STATE.md - only `normalize()` is
frozen there). Per team decision, the JSON shapes returned here match
SPEC.md section 4/5 exactly as plain dicts, defined locally in this
file rather than added to contracts.py unilaterally.
"""

import sqlite3
from pathlib import Path

YEARBOOK_FILENAME = "שנתון תשפז- מדעי המחשב.pdf"

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "course_data.db"


def _connect(db_path):
    return sqlite3.connect(db_path or DEFAULT_DB_PATH)


def list_curricula(db_path=None):
    """Return all curricula: id, name, degree type, structure, start term, pages."""
    conn = _connect(db_path)
    rows = conn.execute(
        "SELECT curriculum_id, name, degree_type, major_structure, start_term, "
        "page_start, page_end FROM curricula"
    ).fetchall()
    conn.close()
    return [
        {
            "curriculum_id": row[0],
            "name": row[1],
            "degree_type": row[2],
            "major_structure": row[3],
            "start_term": row[4],
            "page_start": row[5],
            "page_end": row[6],
        }
        for row in rows
    ]


def get_course_table(curriculum, year, semester, db_path=None):
    """Return all structured rows for one curriculum/year/semester table.

    Never guesses: an omitted/unknown `curriculum` returns a structured
    ambiguity/unknown-curriculum error listing valid ids instead of
    picking one. A curriculum with no table for that year/semester
    (e.g. `computational_biology`, which has no year/semester tables
    at all) returns an empty `rows` list with a `note`, not an error.
    """
    conn = _connect(db_path)
    valid_curricula = [
        row[0] for row in conn.execute("SELECT curriculum_id FROM curricula").fetchall()
    ]

    if curriculum is None:
        conn.close()
        return {"error": "ambiguous_curriculum", "valid_curricula": valid_curricula}

    if curriculum not in valid_curricula:
        conn.close()
        return {"error": "unknown_curriculum", "valid_curricula": valid_curricula}

    rows = conn.execute(
        "SELECT course_number, course_name, credits, prerequisites_text, page "
        "FROM courses WHERE curriculum_id = ? AND year = ? AND semester = ? "
        "ORDER BY id",
        (curriculum, year, semester),
    ).fetchall()

    if not rows:
        conn.close()
        return {
            "curriculum": curriculum,
            "year": year,
            "semester": semester,
            "rows": [],
            "totals": None,
            "note": "no table for this curriculum/year/semester",
        }

    result_rows = [
        {
            "course_number": row[0],
            "course_name": row[1],
            "credits": row[2],
            "prerequisites_text": row[3],
            "source": YEARBOOK_FILENAME,
            "page": row[4],
        }
        for row in rows
    ]

    totals_row = conn.execute(
        "SELECT credits FROM table_totals WHERE curriculum_id = ? AND year = ? AND semester = ?",
        (curriculum, year, semester),
    ).fetchone()
    conn.close()

    return {
        "curriculum": curriculum,
        "year": year,
        "semester": semester,
        "rows": result_rows,
        "totals": {"credits": totals_row[0]} if totals_row else None,
        "citation": {"source": YEARBOOK_FILENAME, "page": rows[0][4]},
    }


def get_course(query, db_path=None):
    """Find a course by exact course number, exact name, or name substring.

    Always returns a list - duplicate course numbers with different
    catalog entries (e.g. `0121503`) both come back rather than being
    silently collapsed.
    """
    conn = _connect(db_path)
    rows = conn.execute(
        "SELECT course_number, course_name, credits, hours, prerequisites_text, "
        "syllabus, page FROM catalog_courses "
        "WHERE course_number = ? OR course_name LIKE ?",
        (query, f"%{query}%"),
    ).fetchall()
    conn.close()

    return [
        {
            "course_number": row[0],
            "course_name": row[1],
            "credits": row[2],
            "hours": row[3],
            "prerequisites_text": row[4],
            "syllabus": row[5],
            "source": YEARBOOK_FILENAME,
            "page": row[6],
        }
        for row in rows
    ]
