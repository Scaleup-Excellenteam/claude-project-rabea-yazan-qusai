"""
Owner: Person 1

Purpose:
Prose section extraction.

Consumes the PageText list produced by extract.pdf_text.extract_pdf_pages()
and groups normalized lines into sections with stable, deterministic
section ids, preserving original page references. Does not touch
SQLite/FTS5 (index/build_fts.py) or the public tools (tools/text_tools.py)
- see those modules for the next steps.

Heading detection is deliberately conservative and informed by the real
yearbook and regulations PDFs.  In particular, table rows, course
metadata, page footers, and table-of-contents pages are not promoted to
searchable sections.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from extract.pdf_text import PageText

_HEADING_MAX_CHARS = 75
_HEADING_MAX_WORDS = 10
_HEADING_END_PUNCTUATION = (".", ",", ";", ":")

_PAGE_NUMBER_RE = re.compile(r"^\s*\d+\s*$")
_COURSE_ROW_RE = re.compile(r"^\s*\d{6,7}(?:\s|,)")
_TOTAL_RE = re.compile(r'^\s*סה["״]?כ\b')
_DOTTED_TOC_RE = re.compile(r"\.{5,}\s*\d+\s*$")
_NUMBERED_ITEM_RE = re.compile(r"^\s*\d+[.)]\s+")
_LEADING_NUMERIC_RE = re.compile(r"^\s*\d")
_COURSE_METADATA_RE = re.compile(r'\b(?:ש["״]ס|נ["״]ז)\b')
_INSTRUCTOR_RE = re.compile(r"^(?:ד[\"״]ר|פרופ(?:סור)?['׳]?|מר |הגב['׳]? |גב['׳]? )")
_TABLE_HEADER_WORDS = frozenset({"ה", "ז ה", "קורס", "מס' קורס שם קורס נקודות זכות"})
_STRONG_HEADING_WORDS = (
    "לימודים", "תכנית", "תוכנית", "תכניות", "תוכניות", "קורסים",
    "קורסי", "מסלול", "דרישות", "תנאי", "זכאות", "הצטיינות",
    "רישום", "נקודות זכות", "מבוא", "פרויקט", "מלגות", "מקבצי",
    "הפסקת", "הפסקו", "חזרה", "ציון", "נוכחות", "השתתפות",
    "התנהלות", "מעקב", "השמטה", "עדכון", "שומעים", "מתכונת",
    "הערכת", "ערעור", "פטור", "תוכן עניינים", "פירוט", "פרק",
    "תואר", "אי ", "מעבר", "אחסון", "פרישה", "ה שהיית", "השהיית",
    "סיום", "ימי ", "רשימת",
    "מערכת", "למתחילים", "שנה ", "קבלת", "צבירת",
)

_SLUG_KEEP_RE = re.compile(r"[^\w֐-׿]+", re.UNICODE)


@dataclass(frozen=True)
class Section:
    """A contiguous span of prose text, grouped under one heading."""

    section_id: str
    source_id: str
    title: str
    normalized_title: str
    parent_section_id: str | None
    page_start: int
    page_end: int
    section_order: int
    text: str
    text_quality_notes: str | None


def _is_table_or_metadata_line(line: str) -> bool:
    return bool(
        _PAGE_NUMBER_RE.fullmatch(line)
        or _COURSE_ROW_RE.match(line)
        or _TOTAL_RE.match(line)
        or _DOTTED_TOC_RE.search(line)
        or _COURSE_METADATA_RE.search(line)
        or _INSTRUCTOR_RE.match(line)
        or line in _TABLE_HEADER_WORDS
        or line.startswith(("סוג שיעור:", "דרישות קדם:", "מס' ", "•"))
    )


def _looks_like_heading(
    line: str,
    next_line: str = "",
    *,
    real_document: bool = False,
    table_heavy: bool = False,
) -> bool:
    if not line:
        return False
    if _is_table_or_metadata_line(line):
        return False
    if len(line) > _HEADING_MAX_CHARS:
        return False
    if len(line.split()) > _HEADING_MAX_WORDS:
        return False
    if line.endswith(_HEADING_END_PUNCTUATION):
        return False
    # Numbered lines in these PDFs are overwhelmingly requirements, lists,
    # or table content.  Primary headings are available from the TOC and do
    # not need this weak signal.
    if _NUMBERED_ITEM_RE.match(line):
        return False
    if _LEADING_NUMERIC_RE.match(line):
        return False
    if line.startswith("דרישות לקורס מקביל"):
        return False
    if table_heavy and line.startswith("פרקים") and not _INSTRUCTOR_RE.match(next_line):
        return False
    if line.startswith(_STRONG_HEADING_WORDS):
        return True
    # Course-description titles are followed by an instructor line.
    if next_line and _INSTRUCTOR_RE.match(next_line):
        return True
    if real_document:
        return False
    # Retain a small generic fallback for simple documents and headings such
    # as "הערות": a short candidate must be followed by unmistakable prose.
    return bool(next_line) and (len(next_line) > _HEADING_MAX_CHARS or next_line.endswith("."))


def _is_toc_page(lines: list[str]) -> bool:
    return bool(lines and lines[0].strip() == "תוכן עניינים" and sum(
        bool(_DOTTED_TOC_RE.search(line)) for line in lines[1:]
    ) >= 3)


def _slugify(title: str) -> str:
    slug = _SLUG_KEEP_RE.sub("-", title).strip("-")
    return slug or "section"


def _make_section_id(source_id: str, page_start: int, title: str, seen: dict[str, int]) -> str:
    base = f"{source_id}:{page_start:03d}:{_slugify(title)}"
    count = seen.get(base, 0)
    seen[base] = count + 1
    if count == 0:
        return base
    return f"{base}-{count + 1}"


class _SectionBuilder:
    """Accumulates lines for one in-progress section."""

    def __init__(self, title: str, page_number: int, section_order: int) -> None:
        self.title = title
        self.page_start = page_number
        self.page_end = page_number
        self.section_order = section_order
        self.lines: list[str] = []

    def add_line(self, line: str, page_number: int) -> None:
        self.lines.append(line)
        self.page_end = page_number

    def build(self, source_id: str, seen_ids: dict[str, int]) -> Section:
        text = "\n".join(self.lines)
        return Section(
            section_id=_make_section_id(source_id, self.page_start, self.title, seen_ids),
            source_id=source_id,
            title=self.title,
            normalized_title=self.title,
            parent_section_id=None,
            page_start=self.page_start,
            page_end=self.page_end,
            section_order=self.section_order,
            text=text,
            text_quality_notes=None,
        )


def extract_sections(pages: list[PageText]) -> list[Section]:
    """Group normalized page text into sections, in document order.

    Pages must already be normalized (see extract_pdf_pages), sorted by
    page_number, and all share the same source_id - a mix of source_ids
    raises ValueError rather than silently relabeling sections under the
    first page's source_id. Pages with no text are skipped; they do not
    break an in-progress section's page range, since page_start/page_end
    already express an inclusive range.
    """
    if not pages:
        return []

    source_id = pages[0].source_id
    real_document = source_id in {"yearbook", "regulations"}
    for page in pages:
        if page.source_id != source_id:
            raise ValueError(
                "extract_sections() requires all pages to share one source_id, "
                f"got {source_id!r} and {page.source_id!r} (page {page.page_number})"
            )

    seen_ids: dict[str, int] = {}
    sections: list[Section] = []
    current: _SectionBuilder | None = None
    next_order = 0

    for page in pages:
        if not page.has_text:
            continue
        page_lines = [line.strip() for line in page.text.split("\n") if line.strip()]
        if _is_toc_page(page_lines):
            continue
        table_heavy = sum(bool(_COURSE_ROW_RE.match(line)) for line in page_lines) >= 2
        for line_index, line in enumerate(page_lines):
            next_line = page_lines[line_index + 1] if line_index + 1 < len(page_lines) else ""
            if _PAGE_NUMBER_RE.fullmatch(line):
                continue

            if current is None:
                # No heading seen yet; adopt the first content line as an
                # implicit leading section title so no text is dropped.
                current = _SectionBuilder(line, page.page_number, next_order)
                next_order += 1
                continue

            if _looks_like_heading(
                line,
                next_line,
                real_document=real_document,
                table_heavy=table_heavy,
            ):
                if current.lines:
                    sections.append(current.build(source_id, seen_ids))
                    current = _SectionBuilder(line, page.page_number, next_order)
                    next_order += 1
                else:
                    # Adjacent display headings are commonly a parent title
                    # followed by its child.  Keep both without emitting an
                    # empty FTS row.
                    current.title = f"{current.title} — {line}"
                continue

            current.add_line(line, page.page_number)

    if current is not None:
        sections.append(current.build(source_id, seen_ids))

    return sections
