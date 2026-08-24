"""
Owner: Person 2

Purpose:
Geometric row/table extraction for the yearbook's curriculum course
tables (pdfplumber table geometry), reusing the shared `normalize()`
from `contracts.py` for RTL text cells.
"""

import re

from contracts import normalize

_WHITESPACE = re.compile(r"\s+")
_FOOTNOTE_MARKER = re.compile(r"\(\d+\)")


def fix_numeric_cell(raw):
    """Repair a numeric table cell.

    pdfplumber's geometric table extraction sometimes splits a decimal
    number across a cell's internal line break (e.g. a totals cell
    comes back as "18.\n5" instead of "18.5") because the digit after
    the decimal point sits on its own visual line inside the cell.
    Collapsing all whitespace before parsing fixes this without
    affecting already-correct values.
    """
    if raw is None:
        return None
    without_footnote = _FOOTNOTE_MARKER.sub("", raw)
    collapsed = _WHITESPACE.sub("", without_footnote)
    if collapsed == "":
        return None
    if collapsed == "-":
        return 0
    value = float(collapsed)
    return int(value) if value.is_integer() else value


def fix_text_cell(raw):
    """Repair a multi-line Hebrew table cell.

    A wrapped table cell comes back from pdfplumber as multiple
    physical lines, each independently in visual (reversed) order.
    Each line is normalized on its own, then rejoined with a single
    space, since physical top-to-bottom line order already matches
    logical reading order.
    """
    if raw is None:
        return None
    lines = [normalize(line) for line in raw.split("\n")]
    return " ".join(line for line in lines if line != "")


_HEADER_FIELDS = {
    "סה": "total_hours",
    "הס": "total_hours",
    "מ": "lab_hours",
    "ת": "exercise_hours",
    "ש": "lecture_hours",
    "דרישותקדם": "prerequisites_text",
    "זנ": "credits",
    "נז": "credits",
    "שםהקורס": "course_name",
    "מסקורס": "course_number",
}

_NUMERIC_FIELDS = {"total_hours", "lab_hours", "exercise_hours", "lecture_hours", "credits"}

_TOTALS_MARKER = 'סה"כ'

_HEADER_NOISE = re.compile(r"[\s'\"׳״]+")


def _classify_header(header_row):
    """Map column index -> field name using normalized header cell text.

    Header abbreviations render inconsistently across pages (stray
    apostrophes attached to different cells, "ס"ה"/"ה"ס" letter order
    flipped), so classification strips whitespace/quote noise and
    matches on the remaining Hebrew letters rather than the raw label.
    """
    fields = {}
    for index, cell in enumerate(header_row):
        label = fix_text_cell(cell)
        if label is None:
            continue
        cleaned = _HEADER_NOISE.sub("", label)
        field = _HEADER_FIELDS.get(cleaned)
        if field:
            fields[index] = field
    return fields


_ALL_FIELDS = set(_HEADER_FIELDS.values())


def parse_table(raw_table):
    """Parse one pdfplumber-extracted table into course rows + totals.

    `raw_table` is the list-of-lists returned by
    `pdfplumber.Page.extract_tables()` for a single table: a header
    row identifying columns by abbreviation, course data rows, and a
    trailing "סה"כ" (total) row. Every row always carries every known
    field (`None` if this table's geometry didn't expose that column)
    so callers never hit a `KeyError` on a malformed table.
    """
    header_row, *data_rows = raw_table
    column_fields = _classify_header(header_row)
    missing_fields = _ALL_FIELDS - set(column_fields.values())

    rows = []
    totals = {}
    for raw_row in data_rows:
        record = {field: None for field in _ALL_FIELDS}
        for index, field in column_fields.items():
            raw_value = raw_row[index] if index < len(raw_row) else None
            if field in _NUMERIC_FIELDS:
                record[field] = fix_numeric_cell(raw_value)
            else:
                record[field] = fix_text_cell(raw_value)

        if record.get("course_number") == _TOTALS_MARKER:
            record.pop("course_number")
            totals = record
        else:
            rows.append(record)

    result = {"rows": rows, "totals": totals}
    if missing_fields:
        result["extraction_warning"] = (
            f"table header did not expose columns: {sorted(missing_fields)}"
        )
    return result


_YEAR_LETTERS = {"א": 1, "ב": 2, "ג": 3, "ד": 4}

_SEMESTER_LABEL = re.compile(r"שנה\s*([א-ת])'?\s*[-–]\s*סמסטר\s*(\d+)")


def _find_semester_labels(page):
    """Find (year, semester) labels on a page, top-to-bottom.

    Semester header lines (e.g. "שנה ב' - סמסטר 4") sit directly above
    each course table on curriculum pages. Each raw line is normalized
    on its own; physical line order already matches reading order, so
    scanning lines top-to-bottom yields labels in the same order as
    `page.extract_tables()` returns tables.
    """
    text = page.extract_text() or ""
    labels = []
    for line in text.split("\n"):
        match = _SEMESTER_LABEL.search(normalize(line))
        if match:
            year_letter, semester = match.groups()
            labels.append((_YEAR_LETTERS[year_letter], int(semester)))
    return labels


_COURSE_NUMBER = re.compile(r"^\d{7}$")
_NUMERIC_CELL = re.compile(r"^-?\d+(\.\d+)?$")


def parse_flat_course_list(raw_table):
    """Parse a flat elective-course table (no year/semester columns).

    Used for tracks like computational biology (yearbook p.16) that
    list eligible courses without organizing them into a
    year/semester curriculum table. Header/data cell positions are
    misaligned in this table's geometry (merged header cells vs.
    unmerged data cells), so fields are identified by content shape
    per row rather than by header column index.
    """
    _header_row, *data_rows = raw_table

    rows = []
    for raw_row in data_rows:
        record = {"course_number": None, "course_name": None, "credits": None}
        name_parts = []
        for raw_value in raw_row:
            collapsed = _WHITESPACE.sub("", raw_value) if raw_value else ""
            if _COURSE_NUMBER.match(collapsed):
                record["course_number"] = collapsed
            elif _NUMERIC_CELL.match(collapsed):
                record["credits"] = fix_numeric_cell(raw_value)
            elif raw_value:
                name_parts.append(raw_value)
        if name_parts:
            record["course_name"] = fix_text_cell(" ".join(name_parts))
        rows.append(record)
    return rows


_CLUSTER_TITLE = re.compile(r"^\d+\.\s*(.+)$")
_CLUSTER_BULLET = re.compile(r"^•\s*(.+?)\s+מס'\s*קורס\s*(\d{7})\s*[–-]\s*(-?\d+(?:\.\d+)?)\s*נ\"ז")
_REQUIRED_HEADING = "קורסי חובה:"
_RECOMMENDED_HEADING = "קורסי בחירה מומלצים:"


def parse_cluster_bullet_line(line):
    """Parse one specialization-cluster bullet line into a course entry.

    Cluster course lists (yearbook pp.13-15) are prose bullets like
    `"• מבוא לעיבוד אותות מס' קורס 0199423 – 3.5 נ"ז"`, not geometric
    tables. Returns `None` for lines that aren't a course bullet.
    """
    match = _CLUSTER_BULLET.match(line)
    if not match:
        return None
    name, course_number, credits = match.groups()
    return {
        "course_name": name.strip(),
        "course_number": course_number,
        "credits": fix_numeric_cell(credits),
    }


def extract_clusters(pdf, pages):
    """Extract specialization clusters (yearbook pp.13-15).

    Each cluster has a numbered title line, a "required courses"
    section, and a "recommended elective courses" section. The first
    cluster's required courses also appear as a real geometric table
    (page 13); its rows are folded in alongside the bullet-parsed ones.
    """
    clusters = []
    current = None
    section = None

    for page_number in pages:
        page = pdf.pages[page_number - 1]
        text = page.extract_text() or ""
        for line in text.split("\n"):
            normalized = normalize(line)

            title_match = _CLUSTER_TITLE.match(normalized)
            if title_match and "מקבץ" in title_match.group(1):
                # skip the intro numbered list ("1. מקבץ פיתוח תוכנה"),
                # which precedes the real per-cluster section headers.
                continue
            if title_match:
                current = {
                    "name": title_match.group(1),
                    "required": [],
                    "recommended": [],
                    "source_page": page_number,
                }
                clusters.append(current)
                section = None
                continue

            if normalized == _REQUIRED_HEADING:
                section = "required"
                continue
            if normalized == _RECOMMENDED_HEADING:
                section = "recommended"
                continue

            course = parse_cluster_bullet_line(normalized)
            if course and current is not None and section is not None:
                current[section].append(course)

        if page_number == pages[0]:
            for raw_table in page.extract_tables():
                parsed = parse_table(raw_table)
                for row in parsed["rows"]:
                    clusters[0]["required"].append(
                        {
                            "course_name": row["course_name"],
                            "course_number": row["course_number"],
                            "credits": row["credits"],
                        }
                    )

    return clusters


def extract_curriculum_tables(pdf, pages):
    """Extract all (year, semester) course tables across a curriculum's pages.

    `pdf` is an open `pdfplumber.PDF`. `pages` are 1-indexed page
    numbers. Returns `{(year, semester): parse_table(...)}`.
    """
    tables = {}
    for page_number in pages:
        page = pdf.pages[page_number - 1]
        labels = _find_semester_labels(page)
        raw_tables = page.extract_tables()
        for (year, semester), raw_table in zip(labels, raw_tables):
            parsed = parse_table(raw_table)
            parsed["page"] = page_number
            tables[(year, semester)] = parsed
    return tables
