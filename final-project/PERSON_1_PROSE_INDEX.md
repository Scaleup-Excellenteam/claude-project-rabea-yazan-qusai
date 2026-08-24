# Person 1: Prose Extraction, Sections, SQLite FTS5

Branch: `feature/prose-index` (create from an up-to-date `main`, after
the shared RTL normalization checkpoint - see `START_HERE.md`).

## Ownership

- `extract/pdf_text.py`
- `extract/sections.py`
- `index/schema.sql`
- `index/build_fts.py`
- `tools/text_tools.py`
- related tests under `tests/`

## Responsibilities

- Use the shared `normalize()` from `contracts.py` - do not write a
  second normalizer.
- Extract normal prose text from both PDFs (`extract/pdf_text.py`).
- Split both PDFs into meaningful sections (`extract/sections.py`).
- Generate stable `section_id` values (do not regenerate them on every
  build in a way that breaks citations).
- Preserve source/page metadata for every section.
- Build the SQLite `sections` table (`index/schema.sql`,
  `index/build_fts.py`).
- Build the FTS5 index using `unicode61` tokenization.
- Use BM25 ranking for search results.
- Implement, matching `contracts.py` exactly:
  - `list_sections`
  - `get_section`
  - `search`
- Ensure normalized Hebrew text is what gets indexed, not raw
  extraction artifacts - but keep citations pointing at original pages.
- Test search quality and section/page correctness.

## Must not modify

- Course-table extraction (`extract/tables.py`, `extract/catalog.py`,
  `extract/prereqs.py`, `index/build_courses.py`,
  `tools/course_tools.py`) - owned by Person 2.
- Agent/UI/evaluation logic (`agent/`, `app.py`, `eval/`) - owned by
  Person 3.
- Shared contracts in `contracts.py` without team approval
  (see `TEAM_RULES.md`).

## Definition of done

- Prose sections are correctly stored with stable ids and accurate
  page ranges.
- FTS5 search works end-to-end.
- `search("הלימודים")` finds the correct normalized section.
- All text tools return data matching the shapes in `contracts.py`.
- Tests pass.
- No unrelated files changed (check `git status` / `git diff` against
  `main` before opening a PR).
