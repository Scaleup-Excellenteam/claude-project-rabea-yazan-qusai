"""
Owner: Shared (all 3 team members)

Purpose:
This file will later hold the shared typed contracts agreed by all
three team members: SourceRef, Section, Curriculum, CourseTableRow,
Course, citation shape, retrieval tool input/output shapes, and the
RTL normalizer contract.

The first shared coding task is RTL normalization, and shared
contracts here are finalized together before the three feature
branches begin.

TODO:
Define the remaining contracts together per SPEC.md sections 4, 5,
and 10 (SourceRef, Section, Curriculum, CourseTableRow, Course,
citation shape, tool I/O shapes). Do not implement individually.

RTL normalization (done - see SPEC.md section 12 "RTL extraction
quality"):

`pdfplumber.Page.extract_text()` returns Hebrew lines in physical
left-to-right visual order instead of logical reading order, because
the underlying PDF content stream places glyphs by x-position and
extract_text() walks positions left-to-right. For a pure-RTL line this
looks like the whole line reversed; for a mixed line (Hebrew prose with
embedded course numbers, decimals, or English/Latin terms) a naive
whole-string reversal is wrong because it also reverses the LTR runs
(e.g. course number "0111401" becomes "1041110").

Confirmed by inspecting both source PDFs directly with pdfplumber
(see data/extracted/ inspection dumps generated for this milestone):

- Yearbook pages 1, 9-12, 13-15, 21: prose and course-table lines are
  extracted in reversed logical order; embedded course numbers,
  decimals (e.g. "3.5"), and Latin terms (e.g. "Real-Time",
  "Introduction to Linux") are already extracted in correct LTR order.
- Regulations pages 1-3, 6: same visual-order issue in prose lines.

`normalize()` fixes this by running each line through the Unicode
Bidirectional Algorithm (`python-bidi`) with a Hebrew (RTL) base
direction, which correctly reorders RTL runs while leaving embedded
LTR runs (numbers, Latin words) untouched, then collapses incidental
extraction whitespace.

Confirmed second failure mode - reversed parentheses: `get_display()`
mirrors bracket-like characters when it resolves them to an RTL
embedding level, which is correct when its input is true logical text
being prepared for visual display, but wrong here because our input is
already-visual pdfplumber text being converted back to logical order.
For parentheses wrapping Hebrew content, this flips the parens (e.g.
regulations page 2: logical "(להלן: המכללה)" comes back as
")להלן: המכללה("). Parens wrapping non-Hebrew content (numbers, Latin
terms such as "(AI)", "(1)") are unaffected because those runs resolve
to LTR level, where no mirroring is applied - confirmed by inspecting
both PDFs: every yearbook paren pair inspected is already correct
(non-Hebrew content), while regulations paren pairs wrapping Hebrew
text are consistently reversed. `normalize()` detects this with a
parenthesis-balance check (a ")" appearing before its matching "(" on
the same line) and swaps `(`/`)` on that line only when doing so is
needed to make the parens well-formed - this leaves already-correct
lines untouched and does not depend on which source PDF a line came
from.

Known remaining limitation (documented, not auto-fixed - see
data/extracted/rtl_normalized_samples.txt for examples): some single
Hebrew letters are occasionally extracted as their own token, split
from the word they belong to by a stray space (e.g. "אודות" ->
"אודו ת" in the regulations prose). This is NOT safe to auto-merge
generically: single-letter tokens are also legitimately used as course
table column-header abbreviations (e.g. "ש", "ת", "מ" for
lecture/exercise/lab hours). Disambiguating the two requires table
structure that is out of scope for this shared milestone; it is left
for Person 1 (section/prose parsing) and Person 2 (course-table
parsing) to resolve with column-aware context.
"""

import re

from bidi.algorithm import get_display

_WHITESPACE_RUN = re.compile(r"[ \t]+")


def _fix_reversed_parens(line: str) -> str:
    """Swap `(`/`)` on this line if they are only well-formed when swapped.

    get_display() mirrors parens resolved to RTL level, which is wrong
    when un-reversing already-visual pdfplumber text (see module
    docstring). A ")" appearing before its matching "(" is the
    signature of this: well-formed parens never go negative when
    scanned left to right treating "(" as +1 and ")" as -1.
    """
    if "(" not in line and ")" not in line:
        return line
    if line.count("(") != line.count(")"):
        return line

    depth = 0
    reversed_order = False
    for ch in line:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                reversed_order = True
                break

    if not reversed_order:
        return line
    return line.translate(str.maketrans("()", ")("))


def normalize(raw_line: str) -> str:
    """Convert a raw pdfplumber-extracted Hebrew/RTL line into logical
    reading order and collapse incidental extraction whitespace.

    Safe on already-correct or pure-LTR input (English-only lines pass
    through unchanged other than whitespace collapsing). Operates
    line-by-line so a multi-line block can also be passed in.
    """
    if raw_line is None:
        return raw_line

    fixed_lines = []
    for line in raw_line.split("\n"):
        if line.strip() == "":
            fixed_lines.append("")
            continue
        display_line = get_display(line, base_dir="R")
        display_line = _fix_reversed_parens(display_line)
        display_line = _WHITESPACE_RUN.sub(" ", display_line).strip()
        fixed_lines.append(display_line)
    return "\n".join(fixed_lines)
