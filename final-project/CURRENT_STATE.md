# Current State

Shared handoff snapshot for anyone (human or Claude/Codex) starting work
on this repo. Read this together with `SPEC.md`, `TEAM_RULES.md`,
`START_HERE.md`, and your own `PERSON_*.md` file before writing any code.

## 1. Project Goal

A local Hebrew/RTL Streamlit chat app that answers student questions
about Computer Science degree requirements and undergraduate academic
regulations, grounded only in two official PDFs
(`final-project/pdfs/`). It uses **Agentic Retrieval** (Claude chooses
which retrieval tool to call at runtime) rather than classic top-k RAG.
Every factual answer must carry a source citation (document + page/
section); if the answer isn't in the PDFs, the app must answer exactly
`לא מופיע במסמכים`. Full detail: `SPEC.md`.

## 2. Current Shared Git State

- Current branch: `feature/shared-rtl-normalization`.
- Working tree: clean, up to date with `origin/feature/shared-rtl-normalization`.
- Expected shared base branch per `START_HERE.md`: `shared-setup`, merged
  into `main` first, then RTL normalization done together, then merged
  back into `main` before anyone branches off for solo feature work.
- `shared-setup` **has already been merged into `main`** (`main` is at
  merge commit `f058056`, "Merge pull request #1 from
  Scaleup-Excellenteam/shared-setup").
- The RTL normalization work (commit `4f2ddd0`, "Implement shared RTL
  normalization") **exists only on `feature/shared-rtl-normalization`**.
  It is **not yet merged into `main`** and not yet merged into
  `shared-setup`. This is the next required step per `START_HERE.md`
  step 7 before anyone should start solo feature branches.
- Two solo feature branches already exist in the repo
  (`feature/person3-agent-ui` locally, `origin/feature/person1-prose-index`
  remotely), but as of this snapshot they only contain the base shared
  structure (same as `shared-setup`) — no RTL work and no
  person-specific implementation yet. They have not branched from a
  `main` that includes RTL normalization.
- Branches intended next, per `START_HERE.md`: merge
  `feature/shared-rtl-normalization` into `main` (via `shared-setup` or
  directly, team's call), then each person branches fresh from that
  updated `main` as `feature/prose-index`, `feature/course-data`,
  `feature/agent-ui`.

## 3. Shared Work Already Completed

Verified by reading the actual files and running the test suite
(`python -m pytest -q` from `final-project/`: **13 passed**, all in
`tests/test_normalize.py`).

- Shared project folder structure (`extract/`, `index/`, `tools/`,
  `agent/`, `eval/`, `tests/`, `data/extracted/`, `pdfs/`) exists per
  `README.md`.
- All role/process docs exist: `SPEC.md`, `README.md`, `TEAM_RULES.md`,
  `START_HERE.md`, `PERSON_1_PROSE_INDEX.md`, `PERSON_2_COURSE_DATA.md`,
  `PERSON_3_AGENT_UI.md`.
- Both source PDFs are committed under `final-project/pdfs/`:
  `שנתון תשפז- מדעי המחשב.pdf` (yearbook) and
  `תקנון לתואר ראשון - תשפו.pdf` (regulations).
- Shared RTL normalization is implemented: `normalize(raw_line)` in
  `final-project/contracts.py`.
- A minimal PDF-line extraction helper for RTL testing exists:
  `tests/support.py` (`extract_raw_lines`) — explicitly documented as
  **not** the real extraction pipeline; that is Person 1's future
  `extract/pdf_text.py`.
- RTL unit/integration tests exist in `tests/test_normalize.py`.
- **13 tests passing**, 0 failing.
- Sample raw/normalized inspection dumps exist:
  `data/extracted/rtl_raw_samples.txt`, `data/extracted/rtl_normalized_samples.txt`.
- `requirements.txt` lists shared baseline deps: `pdfplumber`,
  `python-bidi`, `anthropic`, `streamlit`, `pytest`.
- `.env.example` and `.gitignore` exist (not deeply audited here beyond
  presence).

Everything else in `extract/`, `index/`, `tools/`, `agent/`, `eval/`,
and `app.py` is a **9-line stub** — a docstring only, stating the
owner and "TODO: Implement according to SPEC.md" — with no logic.
None of that should be treated as implemented.

## 4. RTL Milestone Summary

- Implemented in `final-project/contracts.py`, function
  `normalize(raw_line: str) -> str`.
- Real problems it fixes (confirmed against both PDFs with
  `pdfplumber`):
  - `pdfplumber` extracts Hebrew lines in **visual left-to-right order**
    instead of logical reading order. `normalize()` runs each line
    through the Unicode Bidirectional Algorithm (`python-bidi`,
    `get_display(line, base_dir="R")`) to restore logical order while
    leaving embedded LTR runs (course numbers, decimals, Latin terms)
    untouched.
  - `get_display()` incorrectly mirrors parentheses that wrap Hebrew
    content when un-reversing already-visual text (e.g. logical
    `(להלן: המכללה)` becomes `)להלן: המכללה(`). `normalize()` detects
    this via a paren-balance check and swaps `(`/`)` back only on
    affected lines, leaving parens around Latin content (e.g. `(AI)`)
    untouched.
  - Collapses incidental multi-space/tab extraction whitespace.
  - Passes through `None` and blank lines unchanged; normalizes
    multi-line input line-by-line.
- What it deliberately does **not** fix yet: a stray space can split
  the final letter of a Hebrew word into its own token (e.g. `אודות` →
  `אודו ת`). This is **not auto-merged** because a single-letter token
  is also a legitimate course-table column-header abbreviation (e.g.
  `ש`/`ת`/`מ` for lecture/exercise/lab hours), so disambiguating
  requires table-structure context that is out of scope for this
  shared milestone. This is pinned by
  `test_known_limitation_isolated_letter_split_is_not_silently_hidden`
  in `tests/test_normalize.py` and is left for Person 1 (prose/section
  parsing) and Person 2 (course-table parsing) to resolve with
  column-aware context.
- Tests live in `final-project/tests/test_normalize.py`, using the
  helper in `final-project/tests/support.py`.
- Representative examples (see test file for full list):
  - `"בשחמה יעדמל גוחה"` → `"החוג למדעי המחשב"`.
  - Course-table line with `"0111401"` normalizes with the course
    number preserved in correct digit order and `"מבוא למדעי המחשב"`
    readable, instead of corrupting the digits (naive reversal would
    produce `"1041110"`).
  - `"(AI)"` stays as-is; `)להלן: המכללה(` → `(להלן: המכללה)`.

**Future teammates must call the shared `normalize()` from
`contracts.py` and must not write a second/competing RTL normalizer.**
This is stated explicitly as a "must not" in `PERSON_1_PROSE_INDEX.md`
and `PERSON_2_COURSE_DATA.md`.

## 5. Shared Contracts/Interfaces (`contracts.py`)

- Currently implemented: only the `normalize(raw_line)` RTL function
  and its supporting `_fix_reversed_parens` helper.
- Still only a TODO/placeholder: the module docstring explicitly lists
  the remaining shared contracts as **not yet defined** — `SourceRef`,
  `Section`, `Curriculum`, `CourseTableRow`, `Course`, the citation
  shape, and the retrieval tool input/output shapes (`list_sections`,
  `get_section`, `search`, `list_curricula`, `get_course_table`,
  `get_course`), per `SPEC.md` sections 4, 5, and 10.
- These remaining interfaces must be finalized **together** by all
  three team members before solo feature branches begin (`START_HERE.md`
  step 6: "Freeze the shared contracts in `contracts.py`").
- Per `TEAM_RULES.md`, changes to `contracts.py` require all three team
  members to agree first; no unilateral changes.
- **Explicit status: contracts are not fully frozen yet.** Only the
  RTL contract is done. The rest of `START_HERE.md` step 4-6 (schema/
  tool-signature/citation-shape freeze) has not happened.

## 6. What Is NOT Implemented Yet

All of the following are still missing (stub files only, no logic):

- Prose section parsing (`extract/sections.py`)
- Section IDs / source metadata generation
- SQLite `sections` table and schema (`index/schema.sql`, `index/build_fts.py`)
- FTS5/BM25 indexing
- `list_sections`, `get_section`, `search` (`tools/text_tools.py`)
- Course-table parsing (`extract/tables.py`)
- Curricula parsing (`extract/catalog.py`)
- Course catalog construction
- Prerequisites extraction (`extract/prereqs.py`)
- Structured course database (`index/build_courses.py`)
- `list_curricula`, `get_course_table`, `get_course` (`tools/course_tools.py`)
- Claude tool-use loop (`agent/loop.py`)
- Tool schemas (`agent/tool_defs.py`) and system prompt (`agent/system_prompt.py`)
- Prompt caching
- `max_iterations` enforcement (5-8)
- Tool-call metrics (`agent/metrics.py`)
- Citations/refusal integration in the agent loop
- Streamlit UI (`app.py`)
- Evaluation harness (`eval/run_eval.py`, `eval/questions.py`)
- Full-context baseline comparison (`eval/baseline_context.py`)
- Final integration (real tools wired into the real agent loop and UI)

## 7. Team Division (from `SPEC.md` section 9 / `README.md`)

### Person 1 — Prose / Index

Owns: `extract/pdf_text.py`, `extract/sections.py`, `index/schema.sql`,
`index/build_fts.py`, `tools/text_tools.py`, related tests.
Responsible for prose extraction, section parsing, SQLite/FTS5 with
BM25 ranking, and the `list_sections`/`get_section`/`search` tools.
Role file: `PERSON_1_PROSE_INDEX.md`.

### Person 2 — Course Data

Owns: `extract/tables.py`, `extract/catalog.py`, `extract/prereqs.py`,
`index/build_courses.py`, `tools/course_tools.py`, related tests.
Responsible for curricula, course tables, course catalog,
prerequisites, and the structured `list_curricula`/`get_course_table`/
`get_course` tools.
Role file: `PERSON_2_COURSE_DATA.md`.

### Person 3 — Agent / UI / Evaluation

Owns: `agent/loop.py`, `agent/system_prompt.py`, `agent/tool_defs.py`,
`agent/metrics.py`, `app.py`, `eval/questions.py`, `eval/run_eval.py`,
`eval/baseline_context.py`, related tests.
Responsible for the Claude tool-use loop, tool schemas, prompt
caching/iteration cap/metrics, the Streamlit UI, the evaluation
harness, the full-context baseline, and final integration.
Role file: `PERSON_3_AGENT_UI.md`.

## 8. Shared Rules for All Three

- Branch from the latest `main` after it includes shared RTL work (per
  `START_HERE.md`), not from `shared-setup` directly.
- Do not work directly on `shared-setup`.
- Do not modify files owned by another person unless explicitly
  coordinated first.
- Do not reimplement RTL normalization — reuse `normalize()` from
  `contracts.py`.
- Do not change shared contracts in `contracts.py` unilaterally; all
  three must agree first.
- Do not commit secrets; `.env` stays out of git, use `.env.example`.
- Do not add embeddings, a vector database, or classic top-k RAG — this
  project is lexical (FTS5/BM25) Agentic Retrieval only.
- Keep every answer grounded only in the two PDFs; no filling gaps from
  general knowledge or model memory.
- Preserve citations/source metadata (document + page/section) on every
  factual claim.
- Preserve curriculum ambiguity — return a structured ambiguity error
  listing valid curriculum ids instead of silently guessing/defaulting.

## 9. Next Step for Each Person

- **Person 1**: Start from normalized text (via `contracts.normalize`)
  and implement sections + FTS5 + text tools
  (`list_sections`/`get_section`/`search`).
- **Person 2**: Start from normalized PDF/table data (via
  `contracts.normalize`) and implement curricula/course structures +
  course tools (`list_curricula`/`get_course_table`/`get_course`).
- **Person 3**: Start against stubs matching the shared tool contracts
  and implement the Claude loop/UI/evaluation without waiting for
  Persons 1 and 2, then integrate their real tools once merged to
  `main`.

Note: per section 2/5 above, the shared contracts (`contracts.py`)
beyond `normalize()` are not frozen yet — coordinate on freezing
schemas/tool signatures/citation shape before building against them in
earnest, per `START_HERE.md` steps 4-6.

## 10. Recommended Startup Prompt for Future Claude Sessions

Read before coding:

1. `SPEC.md`
2. `CURRENT_STATE.md`
3. `TEAM_RULES.md`
4. your own `PERSON_*.md`
5. `contracts.py`
6. `README.md`

Then:

- Inspect current branch.
- Run `git status`.
- Inspect existing tests.
- Inspect already implemented shared code.
- Do not redo completed work.
- Stay inside your owned files unless a shared contract change is
  explicitly agreed by all three team members.

## 11. Person 2 (Course Data) - Implementation Complete (branch `course-data`)

- `extract/tables.py`: geometric row/table extraction for all 6
  curriculum ids via pdfplumber table geometry - `single_major_fall`,
  `single_major_spring`, `computational_biology` (flat elective list,
  no year/semester), `support_center_spread`, `dual_major_fall`,
  `dual_major_spring`. Fixes fragmented decimals (e.g. `"18.\n5"` ->
  `18.5`), multi-line cells, footnote markers (`(1)`), and totals rows.
  Also extracts the 4 specialization clusters (pp. 13-15, prose bullet
  format) into required/recommended course lists.
- `extract/catalog.py`: per-course catalog records from the prose
  blocks on pp. 25-45 (not geometric tables). Confirmed and handled
  the real duplicate course number `0121503` (two distinct catalog
  entries, 3.5 credits vs 3 credits) via composite identity
  (course_number, course_name) - both are preserved, never collapsed.
- `extract/prereqs.py`: thin wrapper preserving prerequisites text
  verbatim while also surfacing any course numbers mentioned within it.
- `index/build_courses.py`: builds a SQLite DB (curricula, courses,
  table_totals, catalog_courses, clusters, cluster_courses) from the
  yearbook PDF via the above extractors.
- `tools/course_tools.py`: `list_curricula`, `get_course_table`,
  `get_course` matching the JSON shapes in `SPEC.md` section 4/5 as
  plain dicts (contracts.py still only has `normalize()` - see section
  5 above; team decided not to add types there unilaterally).
  `get_course_table` returns a structured `ambiguous_curriculum`/
  `unknown_curriculum` error (never guesses) and an empty-`rows`+`note`
  shape for curricula with no table at a given year/semester.
- Known documented limitation (same spirit as the RTL milestone's
  documented limitations): the `dual_major_fall` year 2/semester 4
  table (yearbook p.21, 4th table) has malformed pdfplumber geometry
  that drops the `course_number`/`total_hours` columns entirely for
  that one table; `extract/tables.py` surfaces this via an
  `extraction_warning` field rather than crashing or guessing values.
  All other 5 curricula's year=2/semester=4 tables parse cleanly.
- Tests: `tests/test_tables.py`, `tests/test_catalog.py`,
  `tests/test_prereqs.py`, `tests/test_build_courses.py`,
  `tests/test_course_tools.py` - 46 new tests, all against the real
  yearbook PDF (no mocked fixtures for the integration-level tests).
  Full suite: `python -m pytest -q` from `final-project/` -> 66 passed.
