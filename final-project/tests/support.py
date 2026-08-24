"""
Owner: Shared (all 3 team members)

Purpose:
Minimal PDF-line extraction helper used only to exercise `normalize()`
in `contracts.py` against real pdfplumber output for this shared RTL
milestone. This is intentionally NOT the real extraction pipeline -
that is Person 1's `extract/pdf_text.py`, implemented later per
START_HERE.md / PERSON_1_PROSE_INDEX.md.
"""

from pathlib import Path

import pdfplumber

PDF_DIR = Path(__file__).resolve().parent.parent / "pdfs"
YEARBOOK_PDF = PDF_DIR / "שנתון תשפז- מדעי המחשב.pdf"
REGULATIONS_PDF = PDF_DIR / "תקנון לתואר ראשון - תשפו.pdf"


def extract_raw_lines(pdf_path: Path, page_number: int) -> list[str]:
    """Return the raw (un-normalized) text lines for a single 1-indexed page."""
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_number - 1]
        text = page.extract_text() or ""
    return text.split("\n")
