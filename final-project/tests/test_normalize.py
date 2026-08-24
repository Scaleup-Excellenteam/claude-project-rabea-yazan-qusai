"""
Owner: Shared (all 3 team members)

Purpose:
Focused tests for the shared `normalize()` RTL contract in
contracts.py, covering the confirmed failure modes found by inspecting
real pdfplumber extraction of both source PDFs (see contracts.py
docstring and data/extracted/rtl_*_samples.txt for the full
inspection).
"""

from contracts import normalize
from tests.support import REGULATIONS_PDF, YEARBOOK_PDF, extract_raw_lines

# Raw lines exactly as returned by pdfplumber.Page.extract_text(),
# captured from the yearbook PDF (pages 9 and 10).
RAW_LINE_COURSE_0111401 = "8 (1)2 2 4 5 בשחמה יעדמל אובמ 0111401"
RAW_LINE_COURSE_0122407 = "6 - 2 4 םינותנ ינבמב םיקרפ 5 1 םימתירוגלא 0122407"

# Raw lines with parentheses, captured from the regulations PDF (page 2)
# and the yearbook PDF (page 13).
RAW_LINE_PARENS_HEBREW = (
    "הב דומילה יללכ ,היתודסומ בכרה ,)הללכמה :ןלהל( יח-לת תימדקאה הללכמה ת ודוא עדימ ואצמת ןונקתב"
)
RAW_LINE_PARENS_LATIN = "(AI) תיתוכאלמ הניבו תיבושיח הדימל ץבקמ .3"


def test_reverses_pure_hebrew_word_order():
    raw = "בשחמה יעדמל גוחה"
    assert normalize(raw) == "החוג למדעי המחשב"


def test_preserves_course_number_digit_order():
    # Naive whole-string reversal would corrupt "0111401" into "1041110".
    result = normalize(RAW_LINE_COURSE_0111401)
    assert "0111401" in result
    assert "1041110" not in result


def test_course_number_and_name_read_in_correct_order():
    result = normalize(RAW_LINE_COURSE_0111401)
    assert result.startswith("0111401")
    assert "מבוא למדעי המחשב" in result


def test_preserves_decimal_and_prerequisite_text():
    result = normalize(RAW_LINE_COURSE_0122407)
    assert result.startswith("0122407")
    assert "אלגוריתמים 1" in result
    assert "פרקים במבני נתונים" in result


def test_preserves_english_terms_embedded_in_hebrew():
    raw = "קורס טקיורפ תונכת ססובמ AI"
    result = normalize(raw)
    assert "AI" in result


def test_collapses_incidental_extraction_whitespace():
    raw = "הבוחה   יסרוקל  תעצומ"
    result = normalize(raw)
    assert "  " not in result


def test_empty_and_blank_lines_pass_through():
    assert normalize("") == ""
    assert normalize("   ") == ""
    assert normalize(None) is None


def test_multiline_input_normalizes_each_line():
    raw = "בשחמה יעדמל גוחה\n" + RAW_LINE_COURSE_0111401
    result = normalize(raw)
    lines = result.split("\n")
    assert lines[0] == "החוג למדעי המחשב"
    assert lines[1].startswith("0111401")


def test_yearbook_course_table_page_normalizes_end_to_end():
    raw_lines = extract_raw_lines(YEARBOOK_PDF, page_number=9)
    normalized = [normalize(line) for line in raw_lines]
    joined = "\n".join(normalized)
    assert "מבוא למדעי המחשב" in joined
    assert "0111401" in joined
    assert "מערכת לימודים מוצעת לקורסי החובה" in joined


def test_regulations_prose_page_normalizes_end_to_end():
    raw_lines = extract_raw_lines(REGULATIONS_PDF, page_number=3)
    normalized = [normalize(line) for line in raw_lines]
    joined = "\n".join(normalized)
    assert "מתכונת הלימודים" in joined


def test_fixes_reversed_parens_around_hebrew_content():
    # get_display() mirrors parens resolved to RTL level, which is
    # wrong for our visual-to-logical use case: it turns logical
    # "(להלן: המכללה)" into ")להלן: המכללה(". normalize() detects the
    # resulting negative paren balance and swaps them back.
    result = normalize(RAW_LINE_PARENS_HEBREW)
    assert "(להלן: המכללה)" in result
    assert ")להלן" not in result


def test_leaves_correct_parens_around_latin_content_untouched():
    # Parens wrapping non-Hebrew content (e.g. "(AI)") resolve to LTR
    # level and are already correct - must not be swapped.
    result = normalize(RAW_LINE_PARENS_LATIN)
    assert "(AI)" in result


def test_known_limitation_isolated_letter_split_is_not_silently_hidden():
    # Documented known limitation (see contracts.py): a stray space can
    # split the last letter of a word into its own token because a
    # single-letter token is NOT safely mergeable in general (it is
    # also a legitimate course-table column-header abbreviation, e.g.
    # "ש"/"ת"/"מ" for lecture/exercise/lab hours). This test pins the
    # current, documented behavior rather than papering over it.
    raw_lines = extract_raw_lines(REGULATIONS_PDF, page_number=2)
    normalized = [normalize(line) for line in raw_lines]
    joined = "\n".join(normalized)
    assert "אודו ת המכללה" in joined
