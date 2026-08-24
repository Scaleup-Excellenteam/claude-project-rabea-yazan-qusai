"""
Owner: Person 2

Unit tests for extract/tables.py geometric table extraction.
"""

import pdfplumber

from extract.tables import (
    extract_clusters,
    extract_curriculum_tables,
    fix_numeric_cell,
    fix_text_cell,
    parse_cluster_bullet_line,
    parse_flat_course_list,
    parse_table,
)
from tests.support import YEARBOOK_PDF

PAGE_9_TABLE_0 = [
    ['"ס\nה', "'מ", "'ת", "ש\n'", 'םדק תושירד', 'ז"נ', 'סרוקה םש', "'סמ\nסרוק"],
    ['6', '-', '2', '4', '', '0', '*א"ודחל אובמ', '0111100'],
    ['6', '-', '2', '4', 'ליבקמ עדי וא א"ודחל אובמ', '5', '** (מ)1 א"ודח', '0111101'],
    ['32', '3', '10', '19', '', '20', '', 'כ"הס'],
]

PAGE_10_TABLE_0_TOTALS_ROW = ['24', '4', '6', '14', '', '18.\n5', '', 'כ"הס']


def test_fix_numeric_cell_joins_decimal_split_across_lines():
    assert fix_numeric_cell("18.\n5") == 18.5


def test_fix_numeric_cell_joins_another_decimal_split():
    assert fix_numeric_cell("15.\n5") == 15.5


def test_fix_numeric_cell_plain_decimal():
    assert fix_numeric_cell("3.5") == 3.5


def test_fix_numeric_cell_plain_integer():
    assert fix_numeric_cell("18") == 18


def test_fix_numeric_cell_dash_means_zero_hours():
    assert fix_numeric_cell("-") == 0


def test_fix_numeric_cell_empty_string_is_none():
    assert fix_numeric_cell("") is None


def test_fix_numeric_cell_strips_footnote_marker():
    assert fix_numeric_cell("(1)2") == 2


def test_fix_numeric_cell_strips_footnote_marker_with_space():
    assert fix_numeric_cell("(1) 2") == 2


def test_fix_text_cell_joins_multiline_course_name():
    raw = "תויתרפס תוכרעמ\nהנבמל אובמו\nבשחמה"
    assert fix_text_cell(raw) == "מערכות ספרתיות ומבוא למבנה המחשב"


def test_fix_text_cell_single_line():
    assert fix_text_cell("(מ)תיראיניל הרבגלא") == "אלגברה ליניארית(מ)"


def test_fix_text_cell_none_is_none():
    assert fix_text_cell(None) is None


def test_fix_text_cell_empty_is_empty():
    assert fix_text_cell("") == ""


def test_parse_table_extracts_course_rows():
    result = parse_table(PAGE_9_TABLE_0)
    assert len(result["rows"]) == 2
    first = result["rows"][0]
    assert first["course_number"] == "0111100"
    assert "מבוא" in first["course_name"]
    assert first["credits"] == 0
    assert first["lecture_hours"] == 4
    assert first["exercise_hours"] == 2
    assert first["lab_hours"] == 0
    assert first["total_hours"] == 6


def test_parse_table_second_row_has_prerequisites_text():
    result = parse_table(PAGE_9_TABLE_0)
    second = result["rows"][1]
    assert second["course_number"] == "0111101"
    assert second["prerequisites_text"] != ""


def test_parse_table_totals_row_excluded_from_rows():
    result = parse_table(PAGE_9_TABLE_0)
    course_numbers = [r["course_number"] for r in result["rows"]]
    assert "כ\"הס" not in course_numbers
    assert len(result["rows"]) == 2


def test_parse_table_totals_credits():
    result = parse_table(PAGE_9_TABLE_0)
    assert result["totals"]["credits"] == 20


def test_parse_table_fixes_fragmented_decimal_in_totals():
    table = [PAGE_9_TABLE_0[0], PAGE_10_TABLE_0_TOTALS_ROW]
    result = parse_table(table)
    assert result["totals"]["credits"] == 18.5


def test_extract_curriculum_tables_maps_year_semester_from_page_labels():
    with pdfplumber.open(YEARBOOK_PDF) as pdf:
        tables = extract_curriculum_tables(pdf, pages=[9, 10])

    assert (1, 1) in tables
    assert (1, 2) in tables
    assert (2, 3) in tables
    assert (2, 4) in tables
    assert (3, 5) in tables
    assert (3, 6) in tables


def test_extract_curriculum_tables_year_2_semester_4_has_algorithms_course():
    with pdfplumber.open(YEARBOOK_PDF) as pdf:
        tables = extract_curriculum_tables(pdf, pages=[9, 10])

    year2_sem4 = tables[(2, 4)]
    course_numbers = [r["course_number"] for r in year2_sem4["rows"]]
    assert "0122407" in course_numbers


COMPUTATIONAL_BIOLOGY_TABLE = [
    ['', 'תוכז תודוקנ', '', '', 'סרוק םש', '', '', "סרוק 'סמ", ''],
    ['3.5', None, None, 'אתה לש היגולויב', None, None, '1011221', None, None],
    ['4', None, None, 'הקיטנג', None, None, '1021205', None, None],
]


def test_parse_flat_course_list_extracts_rows():
    rows = parse_flat_course_list(COMPUTATIONAL_BIOLOGY_TABLE)
    assert len(rows) == 2
    assert rows[0]["course_number"] == "1011221"
    assert rows[0]["credits"] == 3.5
    assert "ביולוגיה" in rows[0]["course_name"]


def test_parse_cluster_bullet_line_extracts_course():
    line = "• מבוא לעיבוד אותות מס' קורס 0199423 – 3.5 נ\"ז"
    result = parse_cluster_bullet_line(line)
    assert result["course_number"] == "0199423"
    assert result["course_name"] == "מבוא לעיבוד אותות"
    assert result["credits"] == 3.5


def test_parse_cluster_bullet_line_non_bullet_returns_none():
    assert parse_cluster_bullet_line("קורסי חובה:") is None


def test_extract_clusters_returns_four_clusters_with_required_courses():
    with pdfplumber.open(YEARBOOK_PDF) as pdf:
        clusters = extract_clusters(pdf, pages=[13, 14, 15])

    assert len(clusters) == 4
    signal_ml = next(c for c in clusters if "0199423" in [r["course_number"] for r in c["required"]])
    required_numbers = [r["course_number"] for r in signal_ml["required"]]
    assert "0199423" in required_numbers
    assert "0199835" in required_numbers
