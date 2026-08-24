"""
Owner: Person 1

Purpose:
Raw PDF text extraction (pdfplumber).

Extracts text page by page, preserving the original PDF page number and
source identity, and passes every line through the shared normalize()
from contracts.py. This module does not do section detection, table
parsing, or indexing - see extract/sections.py and index/build_fts.py
for the next steps.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pdfplumber

import contracts


@dataclass(frozen=True)
class PageText:
    """One page of extracted text, ready for section detection."""

    source_id: str
    filename: str
    page_number: int  # 1-indexed, matches the original PDF page number
    raw_text: str  # exactly as extracted by pdfplumber, "" if none
    text: str  # raw_text normalized line-by-line via contracts.normalize
    has_text: bool


def _normalize_line(line: str) -> str:
    # Looked up dynamically (not `from contracts import normalize`) so this
    # module still imports even before contracts.normalize is implemented.
    return contracts.normalize(line)


def extract_pdf_pages(pdf_path: str | Path, source_id: str) -> list[PageText]:
    """Extract normalized text for every page of a PDF, in page order.

    Preserves the original 1-indexed PDF page number for each page so
    downstream citations stay accurate. Pages with no extractable text
    (e.g. scanned/blank pages) are returned with empty text rather than
    being skipped, so page numbering stays contiguous.
    """
    pdf_path = Path(pdf_path)
    filename = pdf_path.name
    pages: list[PageText] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            raw_text = page.extract_text() or ""
            if raw_text:
                normalized_lines = [_normalize_line(line) for line in raw_text.split("\n")]
                text = "\n".join(normalized_lines)
            else:
                text = ""
            pages.append(
                PageText(
                    source_id=source_id,
                    filename=filename,
                    page_number=page_number,
                    raw_text=raw_text,
                    text=text,
                    has_text=bool(text.strip()),
                )
            )

    return pages
