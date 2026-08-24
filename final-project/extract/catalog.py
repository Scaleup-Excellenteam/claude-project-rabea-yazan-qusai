"""
Owner: Person 2

Purpose:
Per-course catalog record extraction from the yearbook's course
description pages (pp. 25-45). These pages are prose blocks, not
geometric tables, so parsing works line-by-line over
`contracts.normalize()`-ed text rather than `pdfplumber` table
geometry (see extract/tables.py for that).
"""

import re

from contracts import normalize

_METADATA_LINE = re.compile(
    r'^(\d{7}),\s*(-?\d+(?:\.\d+)?)\s*ש[״"]ס,\s*(-?\d+(?:\.\d+)?)\s*נ[״"]ז$'
)
_INSTRUCTOR_MARKER = "(סמ"
_PREREQUISITES_PREFIX = "דרישות קדם:"
_COURSE_TYPE_PREFIX = "סוג שיעור:"


def parse_course_metadata_line(line):
    """Parse a catalog metadata line, e.g. `'0111401, 4 ש"ס, 5 נ"ז'`.

    Returns `None` if `line` isn't a course metadata line.
    """
    match = _METADATA_LINE.match(line)
    if not match:
        return None
    course_number, hours, credits = match.groups()
    hours_value = float(hours)
    credits_value = float(credits)
    return {
        "course_number": course_number,
        "hours": int(hours_value) if hours_value.is_integer() else hours_value,
        "credits": int(credits_value) if credits_value.is_integer() else credits_value,
    }


def extract_catalog_courses(pdf, pages):
    """Extract one record per course description block.

    Each block: course name line, 0+ instructor lines (contain
    "(סמ"), a metadata line (`parse_course_metadata_line`), a course
    type line, an optional prerequisites line, then syllabus prose
    until the next course's name line. Returns a list of dicts (not
    deduplicated by course number - duplicate course numbers with
    different names are preserved, e.g. `0121503`).
    """
    entries = []
    for page_number in pages:
        page = pdf.pages[page_number - 1]
        text = page.extract_text() or ""
        lines = [normalize(line) for line in text.split("\n")]
        entries.extend(_extract_page_blocks(lines, page_number))
    return entries


def _extract_page_blocks(lines, page_number):
    metadata_indices = [
        index for index, line in enumerate(lines) if _METADATA_LINE.match(line)
    ]

    blocks = []
    for position, metadata_index in enumerate(metadata_indices):
        name_index = metadata_index - 1
        while name_index >= 0 and _INSTRUCTOR_MARKER in lines[name_index]:
            name_index -= 1
        if name_index < 0:
            continue

        next_name_index = (
            metadata_indices[position + 1] - 1
            if position + 1 < len(metadata_indices)
            else len(lines)
        )
        while (
            next_name_index > metadata_index
            and _INSTRUCTOR_MARKER in lines[next_name_index - 1]
        ):
            next_name_index -= 1

        metadata = parse_course_metadata_line(lines[metadata_index])
        body_lines = lines[metadata_index + 1 : next_name_index]
        prerequisites_text = ""
        syllabus_lines = []
        for line in body_lines:
            if line.startswith(_COURSE_TYPE_PREFIX):
                continue
            if line.startswith(_PREREQUISITES_PREFIX):
                prerequisites_text = line[len(_PREREQUISITES_PREFIX) :].strip()
                continue
            if line != "":
                syllabus_lines.append(line)

        blocks.append(
            {
                "course_number": metadata["course_number"],
                "course_name": lines[name_index],
                "credits": metadata["credits"],
                "hours": metadata["hours"],
                "prerequisites_text": prerequisites_text,
                "syllabus": " ".join(syllabus_lines),
                "page": page_number,
            }
        )
    return blocks
