"""
Owner: Person 2

Purpose:
Build SQLite curricula/courses/catalog/clusters tables from the
yearbook PDF, using extract/tables.py, extract/catalog.py, and
extract/prereqs.py.
"""

import sqlite3

import pdfplumber

from extract.catalog import extract_catalog_courses
from extract.prereqs import parse_prerequisites
from extract.tables import extract_clusters, extract_curriculum_tables, parse_flat_course_list

CATALOG_PAGES = range(25, 46)

CLUSTER_PAGES = [13, 14, 15]

CURRICULA = [
    {
        "id": "single_major_fall",
        "name": 'תוכנית לימודים מוצעת לקורסי החובה למתחילים בסמסטר סתיו/א',
        "degree_type": "B.Sc.",
        "major_structure": "single_major",
        "start_term": "fall",
        "pages": [9, 10],
    },
    {
        "id": "single_major_spring",
        "name": 'תוכנית לימודים מוצעת לקורסי החובה למתחילים בסמסטר אביב/ב',
        "degree_type": "B.Sc.",
        "major_structure": "single_major",
        "start_term": "spring",
        "pages": [11, 12],
    },
    {
        "id": "computational_biology",
        "name": "מסלול לימודים בביולוגיה חישובית",
        "degree_type": "B.Sc.",
        "major_structure": "computational_biology",
        "start_term": "any",
        "pages": [16],
    },
    {
        "id": "support_center_spread",
        "name": "תוכנית פריסת לימודים לסטודנטים ממרכז התמיכה",
        "degree_type": "B.Sc.",
        "major_structure": "support_center_spread",
        "start_term": "fall",
        "pages": [19, 20],
    },
    {
        "id": "dual_major_fall",
        "name": "תוכנית לתואר ראשון דו-חוגי משותפת למדעי המחשב וחוג נוסף - למתחילים בסמסטר סתיו/א",
        "degree_type": "B.A.",
        "major_structure": "dual_major",
        "start_term": "fall",
        "pages": [21, 22],
    },
    {
        "id": "dual_major_spring",
        "name": "תוכנית לתואר ראשון דו-חוגי משותפת למדעי המחשב וחוג נוסף - למתחילים בסמסטר אביב/ב",
        "degree_type": "B.A.",
        "major_structure": "dual_major",
        "start_term": "spring",
        "pages": [23, 24],
    },
]

_SCHEMA = """
CREATE TABLE curricula (
    curriculum_id TEXT PRIMARY KEY,
    name TEXT,
    degree_type TEXT,
    major_structure TEXT,
    start_term TEXT,
    page_start INTEGER,
    page_end INTEGER
);

CREATE TABLE courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    curriculum_id TEXT,
    year INTEGER,
    semester INTEGER,
    course_number TEXT,
    course_name TEXT,
    credits REAL,
    lecture_hours REAL,
    exercise_hours REAL,
    lab_hours REAL,
    total_hours REAL,
    prerequisites_text TEXT,
    prerequisites_mentions TEXT,
    page INTEGER
);

CREATE TABLE catalog_courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_number TEXT,
    course_name TEXT,
    credits REAL,
    hours REAL,
    prerequisites_text TEXT,
    prerequisites_mentions TEXT,
    syllabus TEXT,
    page INTEGER
);

CREATE TABLE table_totals (
    curriculum_id TEXT,
    year INTEGER,
    semester INTEGER,
    credits REAL,
    PRIMARY KEY (curriculum_id, year, semester)
);

CREATE TABLE clusters (
    cluster_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    source_page INTEGER
);

CREATE TABLE cluster_courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id INTEGER,
    course_number TEXT,
    course_name TEXT,
    credits REAL,
    requirement_type TEXT
);
"""


def build_courses_db(pdf_path, db_path):
    """Build the course-data SQLite DB at `db_path` from `pdf_path`.

    Overwrites any existing tables at `db_path` (safe to re-run).
    """
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)

    with pdfplumber.open(pdf_path) as pdf:
        for curriculum in CURRICULA:
            conn.execute(
                "INSERT INTO curricula VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    curriculum["id"],
                    curriculum["name"],
                    curriculum["degree_type"],
                    curriculum["major_structure"],
                    curriculum["start_term"],
                    curriculum["pages"][0],
                    curriculum["pages"][-1],
                ),
            )

            if curriculum["major_structure"] == "computational_biology":
                page = pdf.pages[curriculum["pages"][0] - 1]
                rows = parse_flat_course_list(page.extract_tables()[0])
                for row in rows:
                    _insert_course(conn, curriculum["id"], None, None, row, curriculum["pages"][0])
                continue

            tables = extract_curriculum_tables(pdf, curriculum["pages"])
            for (year, semester), table in tables.items():
                for row in table["rows"]:
                    _insert_course(conn, curriculum["id"], year, semester, row, table["page"])
                total_credits = table["totals"].get("credits")
                if total_credits is not None:
                    conn.execute(
                        "INSERT INTO table_totals (curriculum_id, year, semester, credits) "
                        "VALUES (?, ?, ?, ?)",
                        (curriculum["id"], year, semester, total_credits),
                    )

        catalog_courses = extract_catalog_courses(pdf, CATALOG_PAGES)
        for course in catalog_courses:
            prereqs = parse_prerequisites(course.get("prerequisites_text") or None)
            conn.execute(
                "INSERT INTO catalog_courses "
                "(course_number, course_name, credits, hours, prerequisites_text, "
                "prerequisites_mentions, syllabus, page) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    course["course_number"],
                    course["course_name"],
                    course["credits"],
                    course["hours"],
                    prereqs["raw"] if prereqs else None,
                    ",".join(prereqs["mentions"]) if prereqs else None,
                    course["syllabus"],
                    course["page"],
                ),
            )

        clusters = extract_clusters(pdf, CLUSTER_PAGES)
        for cluster in clusters:
            cursor = conn.execute(
                "INSERT INTO clusters (name, source_page) VALUES (?, ?)",
                (cluster["name"], cluster["source_page"]),
            )
            cluster_id = cursor.lastrowid
            for requirement_type, courses in (
                ("required", cluster["required"]),
                ("recommended", cluster["recommended"]),
            ):
                for course in courses:
                    conn.execute(
                        "INSERT INTO cluster_courses "
                        "(cluster_id, course_number, course_name, credits, requirement_type) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (
                            cluster_id,
                            course["course_number"],
                            course["course_name"],
                            course["credits"],
                            requirement_type,
                        ),
                    )

    conn.commit()
    conn.close()


def _insert_course(conn, curriculum_id, year, semester, row, page):
    prereqs = parse_prerequisites(row.get("prerequisites_text") or None)
    conn.execute(
        "INSERT INTO courses "
        "(curriculum_id, year, semester, course_number, course_name, credits, "
        "lecture_hours, exercise_hours, lab_hours, total_hours, prerequisites_text, "
        "prerequisites_mentions, page) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            curriculum_id,
            year,
            semester,
            row.get("course_number"),
            row.get("course_name"),
            row.get("credits"),
            row.get("lecture_hours"),
            row.get("exercise_hours"),
            row.get("lab_hours"),
            row.get("total_hours"),
            prereqs["raw"] if prereqs else None,
            ",".join(prereqs["mentions"]) if prereqs else None,
            page,
        ),
    )
