"""
Owner: Person 1

Purpose:
Prose section extraction.

Consumes the PageText list produced by extract.pdf_text.extract_pdf_pages()
and groups normalized lines into sections with stable, deterministic
section ids, preserving original page references. Does not touch
SQLite/FTS5 (index/build_fts.py) or the public tools (tools/text_tools.py)
- see those modules for the next steps.

Heading detection here is a conservative heuristic (short line, no
trailing sentence punctuation). It has not been validated against the
real project PDFs yet (they are not available in this repository), so
it will likely need tuning once real documents are checked in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from extract.pdf_text import PageText

_HEADING_MAX_CHARS = 60
_HEADING_MAX_WORDS = 8
_HEADING_END_PUNCTUATION = (".",)

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


def _looks_like_heading(line: str) -> bool:
    if not line:
        return False
    if len(line) > _HEADING_MAX_CHARS:
        return False
    if len(line.split()) > _HEADING_MAX_WORDS:
        return False
    if line.endswith(_HEADING_END_PUNCTUATION):
        return False
    return True


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
        for raw_line in page.text.split("\n"):
            line = raw_line.strip()
            if not line:
                continue

            if current is None:
                # No heading seen yet; adopt the first content line as an
                # implicit leading section title so no text is dropped.
                current = _SectionBuilder(line, page.page_number, next_order)
                next_order += 1
                continue

            if _looks_like_heading(line):
                sections.append(current.build(source_id, seen_ids))
                current = _SectionBuilder(line, page.page_number, next_order)
                next_order += 1
                continue

            current.add_line(line, page.page_number)

    if current is not None:
        sections.append(current.build(source_id, seen_ids))

    return sections
