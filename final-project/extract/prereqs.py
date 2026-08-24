"""
Owner: Person 2

Purpose:
Structure verbatim prerequisite text extracted by extract/tables.py
and extract/catalog.py without rewriting it - preserve `raw` exactly,
and additionally surface any course numbers mentioned within it for
future prerequisite-graph/fuzzy-matching use.
"""

import re

_COURSE_NUMBER = re.compile(r"\d{7}")


def parse_prerequisites(raw):
    """Wrap verbatim prerequisites text with any course numbers it mentions.

    `raw` is preserved exactly as extracted. Returns `None` if `raw`
    is `None` (no prerequisites text was extracted for that row/course).
    """
    if raw is None:
        return None
    return {"raw": raw, "mentions": _COURSE_NUMBER.findall(raw)}
