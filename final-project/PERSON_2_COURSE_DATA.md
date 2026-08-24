# Person 2: Course Tables, Curricula, Prerequisites

Branch: `feature/course-data` (create from an up-to-date `main`, after
the shared RTL normalization checkpoint - see `START_HERE.md`).

## Ownership

- `extract/tables.py`
- `extract/catalog.py`
- `extract/prereqs.py`
- `index/build_courses.py`
- `tools/course_tools.py`
- related tests under `tests/`

## Responsibilities

- Use the shared `normalize()` from `contracts.py` - do not write a
  second normalizer.
- Parse all five curricula/plans from the yearbook (see `SPEC.md`
  section 4 for the confirmed list: single-major fall/spring,
  computational biology, support-center spread, dual-major
  fall/spring, plus specialization clusters).
- Reconstruct course tables, fixing multi-line course names/cells and
  fragmented decimals (e.g. `18.5`, `3.5` split across lines/cells).
- Preserve prerequisites text exactly as extracted
  (`extract/prereqs.py`).
- Preserve source/page metadata for every course row.
- Normalize course numbers consistently.
- Handle duplicate course numbers correctly - return all matches, do
  not silently collapse them (see `SPEC.md` section 12).
- Store structured curriculum/course/table data via
  `index/build_courses.py`.
- Implement, matching `contracts.py` exactly:
  - `list_curricula`
  - `get_course_table`
  - `get_course`
- Handle ambiguity and contradictions exactly as defined in `SPEC.md`
  (ambiguous curriculum -> structured error listing valid ids, not a
  guess; see `SPEC.md` sections 5 and 7).

## Must not modify

- FTS5/prose pipeline (`extract/pdf_text.py`, `extract/sections.py`,
  `index/schema.sql` prose parts, `index/build_fts.py`,
  `tools/text_tools.py`) - owned by Person 1.
- Agent/UI/evaluation logic (`agent/`, `app.py`, `eval/`) - owned by
  Person 3.
- Shared contracts in `contracts.py` without team approval
  (see `TEAM_RULES.md`).

## Definition of done

- All required course tables parse correctly.
- All five `(year=2, semester=4)` curriculum cases are distinguishable
  via `curriculum` id (see `SPEC.md` section 5, `get_course_table`).
- Decimals like `18.5` and `3.5` parse correctly (not `1`, `8`, `.`, `5`
  as separate fragments).
- Ambiguous course numbers return all matches, not just one.
- Tools match the shapes in `contracts.py`.
- Tests pass.
- No unrelated files changed (check `git status` / `git diff` against
  `main` before opening a PR).
