# Project Specification: Hebrew Agentic Retrieval Chat Over Department Documents

## 1. Project Goal

Build a local Hebrew/RTL Streamlit chat application for students who ask practical questions about Computer Science degree requirements and undergraduate academic regulations.

The application answers only from these official project documents:

- `final-project/pdfs/שנתון תשפז- מדעי המחשב.pdf` - 45-page Computer Science yearbook for 2026/27, including single-major and dual-major curricula, course tables, specialization clusters, prerequisites, credits, and course descriptions.
- `final-project/pdfs/תקנון לתואר ראשון - תשפו.pdf` - 13-page undergraduate regulations document, including rules for admission, course registration, credits, progression, interruptions, completion, excellence, and degree eligibility.
- `final-project/README.md` / `assignment-he.pdf` - assignment brief, not an answer source for student questions.

Allowed answers:

- Facts explicitly present in the two source PDFs.
- Aggregations computed from extracted structured rows, such as total credits per year or counts of courses with prerequisites.
- Cross-document answers when every factual claim is grounded in one of the PDFs.

Required refusal:

- If the answer is not present in the PDFs, answer exactly: `לא מופיע במסמכים`.
- Never fill gaps from general knowledge, college websites, assumptions, or model memory.

## 2. Mandatory Assignment Requirements

Confirmed hard requirements from the README/brief:

- Every factual answer must include source citation: source document plus section and/or page.
- Missing information must return `לא מופיע במסמכים`.
- Use Agentic Retrieval tools over structured document data, not a classic automatic top-k RAG pipeline.
- Implement SQLite FTS5 lexical search with BM25 ranking.
- Avoid unnecessary infrastructure: embeddings, vector databases, Postgres, pgvector, Chroma, torch.
- Use prompt caching in the Claude tool loop. The tools/system prompt should be a stable cached prefix; apply `cache_control` to the final block of each turn.
- Enforce `max_iterations` between 5 and 8 for the tool-use loop.
- Measure and report average tool calls per evaluation question in the README.
- Run locally only. Do not deploy publicly.
- Keep the project API key in `.env`; `.env` must be ignored by git.
- The lecturer's API key is for this app only, not global `ANTHROPIC_API_KEY` for Claude Code.
- Submission README must include runnable setup instructions, tool-design rationale, actual evaluation outputs and failure analysis, average tool calls/question, and a short comparison against a full-context approach for 3-4 questions.
- Submit a public GitHub repo plus 3-minute video or live demo.

Recommended stack from the brief:

- Python 3.11+
- `pdfplumber`
- `python-bidi`
- SQLite FTS5 with `unicode61`
- `anthropic` SDK and `claude-sonnet-5`
- Streamlit with `st.chat_message` / `st.chat_input`

## 3. Architecture

Data flow:

```text
PDFs
-> PDF extraction
-> RTL/text cleanup and manual verification
-> structured sections + structured course tables
-> SQLite tables + SQLite FTS5 index
-> retrieval tool functions
-> Claude tool-use loop with prompt caching and max_iterations
-> Streamlit Hebrew RTL chat UI
-> cited answer or refusal
```

This is Agentic Retrieval because the model chooses which retrieval tool to call at runtime. The app does not automatically retrieve top-k chunks for every question. The documents already have meaningful structure: sections, headings, page numbers, course-plan tables, specialization clusters, and course descriptions. The retrieval layer must preserve that structure and expose it as tools.

## 4. Data Model

Minimum source metadata:

```text
sources
- source_id
- filename
- title
- document_type: yearbook | regulations
- academic_year: תשפז | תשפו
- page_count
```

Document sections:

```text
sections
- section_id
- source_id
- title
- normalized_title
- parent_section_id nullable
- page_start
- page_end
- section_order
- text
- text_quality_notes nullable
```

Course rows:

```text
courses
- course_id
- source_id
- page
- curriculum_id
- year_number nullable
- semester_number nullable
- course_number
- course_name
- credits
- lecture_hours nullable
- exercise_hours nullable
- lab_hours nullable
- total_hours nullable
- prerequisites_text nullable
- requirement_type: חובה | בחירה | סדנה | השתלמות | מקבץ חובה | מקבץ מומלץ | אחר
- notes nullable
```

Curricula / plans:

```text
curricula
- curriculum_id
- name
- degree_type: B.Sc. | B.A.
- major_structure: single_major | dual_major | computational_biology | support_center_spread | specialization_cluster
- start_term: fall | spring | any
- description
- source_page_start
- source_page_end
```

Confirmed curricula/parallel plans in the yearbook:

- Single-major `B.Sc.` Computer Science, fall start, pages around 9-10.
- Single-major `B.Sc.` Computer Science, spring start, pages around 11-12.
- Computational Biology within the single-major route, page 16.
- Support-center partial study spread, pages around 19-20, including year 4 / semester 7.
- Dual-major `B.A.` with CS and another department, fall start, pages around 21-22.
- Dual-major `B.A.` with CS and another department, spring start, pages around 23-24.
- Specialization clusters: Software Development, Signal Processing and Computational Learning, Computational Learning and AI, Real-Time Systems and Networks, pages around 13-15.

Specialization clusters:

```text
clusters
- cluster_id
- name
- source_page_start
- source_page_end
- description
```

Cluster course membership:

```text
cluster_courses
- cluster_id
- course_number
- course_name
- credits
- requirement_type: required | recommended
- source_page
```

Citation metadata returned by every retrieval path:

```text
citation
- source_id
- filename
- page
- section_id nullable
- section_title nullable
- row_id nullable
```

## 5. Retrieval Tool Contracts

### `list_sections()`

Purpose: let Claude inspect the document table of contents and available structured sections.

Parameters: none.

Output:

```json
[
  {
    "section_id": "yearbook:course-plans:single-fall",
    "title": "מערכת לימודים מוצעת לקורסי החובה למתחילים בסמסטר סתיו/א'",
    "source": "שנתון תשפז- מדעי המחשב.pdf",
    "page_start": 9,
    "page_end": 10
  }
]
```

Edge cases:

- If extraction quality for a section is questionable, include `text_quality_notes`.
- Return concise metadata only, not full text.

### `get_section(section_id: str)`

Purpose: retrieve full text for a known section when search snippets are insufficient or when policy wording matters.

Parameters:

- `section_id`: exact id from `list_sections` or `search`.

Output:

```json
{
  "section_id": "...",
  "title": "...",
  "text": "...",
  "citations": [{"source": "...", "page_start": 4, "page_end": 6}]
}
```

Edge cases:

- Missing id returns a structured error, not empty text.
- Very large sections may be split by page while preserving section id and citations.

### `search(query: str, limit: int = 5)`

Purpose: BM25 lexical search over normalized section text using SQLite FTS5.

Parameters:

- `query`: Hebrew or mixed Hebrew/English query.
- `limit`: default 5, cap at 10.

Output:

```json
[
  {
    "section_id": "...",
    "title": "...",
    "snippet": "...",
    "score": -3.42,
    "source": "...",
    "page_start": 10,
    "page_end": 10
  }
]
```

Edge cases:

- No results returns `[]`.
- Normalize known extraction artifacts, but keep citations to original pages.
- Do not silently broaden into semantic search.

### `get_course_table(curriculum: str, year: int, semester: int)`

The README suggests `get_course_table(year, semester)`, but the actual yearbook has multiple valid tables for the same year/semester. Example: year B / semester 4 differs between single-major fall start, single-major spring start, support-center spread, dual-major fall start, and dual-major spring start. Therefore the smallest safe change is adding `curriculum`.

Purpose: return all structured rows for one curriculum/year/semester table.

Parameters:

- `curriculum`: enum/id such as `single_major_fall`, `single_major_spring`, `dual_major_fall`, `dual_major_spring`, `support_center_spread`, `computational_biology`.
- `year`: 1-4.
- `semester`: 1-7 depending on plan.

Output:

```json
{
  "curriculum": "single_major_fall",
  "year": 2,
  "semester": 4,
  "rows": [
    {
      "course_number": "0122407",
      "course_name": "אלגוריתמים 1",
      "credits": 5,
      "prerequisites_text": "פרקים במבני נתונים",
      "source": "שנתון תשפז- מדעי המחשב.pdf",
      "page": 10
    }
  ],
  "totals": {"credits": 18.5},
  "citation": {"source": "שנתון תשפז- מדעי המחשב.pdf", "page": 10}
}
```

Edge cases:

- If `curriculum` is omitted or ambiguous, return an ambiguity error listing valid curriculum ids.
- If table is absent, return a not-found error with the nearest matching curricula/semesters.
- Rows must preserve prerequisites and credits exactly as extracted.

Recommended additional helper:

### `list_curricula()`

Purpose: let Claude disambiguate before calling `get_course_table`.

Output: curriculum ids, display names, degree type, start term, page range.

## 6. Agent Behavior

- Use `list_sections` at the start of uncertain questions or when deciding whether the answer is in a policy section, course table, cluster, or course description.
- Use `search` for factual lookup by course name, policy term, or phrase.
- Use `get_section` when the answer depends on exact wording, regulations, cross-document comparison, or search snippets are too thin.
- Use `get_course_table` for year/semester questions, prerequisite table lookup, credit totals, course counts, and required course lists.
- For aggregation questions, retrieve complete relevant tables first, then calculate from structured rows.
- For cross-document questions, retrieve at least one relevant section/table from each needed document and cite each source used.
- Determine absence only after an adequate retrieval attempt: search relevant terms, inspect likely section list/table, and check no structured row matches.
- Citations should be attached to each factual paragraph or bullet: document name + section title or page.
- Prevent hallucination with a system prompt that requires tool-grounded answers only, cites all facts, and refuses with `לא מופיע במסמכים` when unsupported.

## 7. Error and Refusal Behavior

- No search results: try one narrower/broader lexical query if appropriate; if still absent, answer `לא מופיע במסמכים`.
- Ambiguous curriculum: ask the user which curriculum/start term they mean, or state the ambiguity and list options. Do not pick silently.
- Missing section id: return a tool error; model should call `list_sections` or `search` again.
- Parsing/index errors: UI should show a clear local error and not produce a factual answer.
- Tool failure: retry once if transient; otherwise explain that retrieval failed and do not answer from memory.
- API failure: show an API error in the UI; do not fabricate a response.
- Max tool iterations reached: answer that the system could not verify the answer from the documents, or `לא מופיע במסמכים` if retrieval was exhausted.
- Missing information: exact refusal string `לא מופיע במסמכים`.

## 8. Evaluation Strategy

Evaluation questions from the assignment:

| # | Question | Category | Components tested |
|---|---|---|---|
| 1 | Course number and credits for "מבוא למדעי המחשב" | factual/table lookup | course row extraction, search, citation |
| 2 | Usual duration of undergraduate studies by regulations | factual policy lookup | regulations extraction, section retrieval |
| 3 | Year B semester 4 courses and credits | table lookup | curriculum disambiguation, `get_course_table` |
| 4 | Prerequisites for "אלגוריתמים 1" | table lookup | row lookup across tables/course descriptions |
| 5 | Required courses in "עיבוד אותות ולמידה חישובית" | cluster table lookup | cluster model, required/recommended distinction |
| 6 | Total credits required in year C | aggregation | full table retrieval, sum credits, curriculum handling |
| 7 | Count year A courses with prerequisites | aggregation | complete year A rows, prerequisite detection |
| 8 | Difference between single-major and dual-major, and relevance to CS | cross-document/section reasoning | yearbook degree routes, possibly regulations terminology |
| 9 | Conditions for spreading studies to four years | cross-document/policy lookup | regulations + yearbook partial spread text |
| 10 | Academic secretariat office hours | refusal | absence detection and exact refusal |

Measure average tool calls/question by logging each tool invocation with:

```text
question_id, tool_name, parameters, timestamp, success, result_count
```

Then compute:

```text
average_tool_calls = total_tool_calls_for_10_questions / 10
```

Also keep full trace logs for failure analysis, but do not expose API keys or private prompt content in public files.

## 9. Team Division

The README names four workstreams, but with three people the best split is:

### Person 1: Extraction, Parsing, SQLite/FTS5

Owns:

- `src/extraction/`
- `src/indexing/`
- SQLite schema and index build scripts
- sample extracted text/table verification outputs

Responsibilities:

- Extract both PDFs.
- Fix RTL/text normalization enough for reliable search and display.
- Detect sections and page ranges.
- Extract course tables, curricula, cluster tables, credits, prerequisites.
- Build SQLite tables and FTS5 index.

Inputs needed:

- Final shared schemas and citation shape.

Outputs/contracts:

- `data/app.db` or equivalent local DB.
- documented schema.
- parser verification notes for known risky pages.

Parallel work:

- Can begin immediately after schema checkpoint.

Tests:

- DB contains 2 sources.
- Expected page counts: 45 and 13.
- Known rows exist: `0111401` "מבוא למדעי המחשב"; `0122407` "אלגוריתמים 1".
- Multiple curricula are present.
- FTS search returns cited section ids.

### Person 2: Retrieval Tools and Claude Agent Loop

Owns:

- `src/tools.py`
- `src/agent.py`
- system prompt
- prompt caching and iteration limit
- tool-call metrics

Responsibilities:

- Implement `list_sections`, `get_section`, `search`, `list_curricula`, `get_course_table`.
- Implement Anthropic tool-use loop.
- Enforce citations/refusal behavior.
- Enforce `max_iterations` 5-8.
- Add prompt caching.
- Log tool calls.

Inputs needed:

- SQLite schema and stable tool output shapes from Person 1.

Outputs/contracts:

- `answer_question(question) -> {answer, citations, tool_calls, traces}`.
- retrieval errors are structured and UI-safe.

Parallel work:

- Can build against a tiny fixture DB before real extraction is complete.

Tests:

- Unit tests for each tool.
- Agent refuses known missing question.
- Agent handles ambiguous curriculum without guessing.
- Tool-call count is recorded.

### Person 3: Streamlit UI, Evaluation, Integration Support

Owns:

- `app.py`
- `src/evaluation/`
- README evaluation table/failure analysis draft
- `.env.example` and run instructions

Responsibilities:

- Build Hebrew RTL Streamlit chat.
- Display citations and errors clearly.
- Run the 10 evaluation questions and save actual outputs.
- Run 3-4 full-context comparison questions.
- Help integration and final README.

Inputs needed:

- `answer_question` contract from Person 2.
- DB build command from Person 1.

Outputs/contracts:

- Local app runnable with `streamlit run app.py`.
- evaluation result table.
- average tool calls/question.

Parallel work:

- Can build UI with mocked `answer_question`.
- Can prepare evaluation harness before final agent is ready.

Tests:

- UI smoke test imports and runs.
- RTL layout is applied.
- Evaluation harness records answer, citations, tool_calls, pass/fail notes.

## 10. Shared Contract / First Checkpoint

Before splitting, the whole team must finalize:

- `section` schema and section id naming.
- `course row` schema, including how to store credits, prerequisites, year, semester, and curriculum.
- `curriculum_id` enum values.
- Citation object shape used everywhere.
- Tool input/output JSON shapes and error shapes.
- Normalization policy: keep original text/page citation, but store normalized text for search.

This checkpoint unblocks parallel work because Person 1 can produce the DB, Person 2 can code tools against the schema, and Person 3 can mock UI/evaluation against the same response contract.

## 11. Implementation Order

1. Inspect PDFs manually as a team.
2. Build extraction prototype for both PDFs.
3. Manually verify extracted text for TOC, pages 9-12, pages 13-24, and key regulation pages.
4. Finalize schemas/contracts from section 10.
5. In parallel:
   - Person 1 finishes extraction/index.
   - Person 2 builds tools/agent against fixture DB.
   - Person 3 builds UI/evaluation harness against mock agent.
6. Integrate real DB with retrieval tools.
7. Integrate agent with Streamlit UI.
8. Run the 10 evaluation questions and record actual outputs.
9. Fix extraction/tool/prompt failures based on traces.
10. Run full-context comparison for 3-4 questions.
11. Finish README, verify clean local setup, record demo.

## 12. Open Questions / Decisions

### Course table signature ambiguity

1. Found: multiple curricula have tables for the same year/semester.
2. Why it matters: `get_course_table(2, 4)` can return different valid rows.
3. Recommended decision: use `get_course_table(curriculum, year, semester)` plus `list_curricula`.
4. Confirmation needed: team decision; lecturer confirmation optional because this is a minimal refinement of the suggested signature.

### RTL extraction quality

1. Found: yearbook extraction is mostly readable but contains glyph artifacts; regulations text may appear in visual RTL order.
2. Why it matters: bad normalization harms FTS search, snippets, and citations.
3. Recommended decision: store both raw and normalized text, manually verify high-value sections/tables.
4. Confirmation needed: team only.

### Regulations section granularity

1. Found: regulations document is section-based and not table-heavy; extraction is less clean than the yearbook.
2. Why it matters: overly small chunks may break policy wording; overly large sections cost tool iterations.
3. Recommended decision: split by visible section headings from the TOC/pages and preserve page ranges.
4. Confirmation needed: team only after extraction prototype.

### Answering ambiguous user questions

1. Found: many student questions omit curriculum/start term.
2. Why it matters: aggregation and table answers may differ by plan.
3. Recommended decision: if a question depends on plan and no plan is given, ask a clarification or answer with explicit comparison across plans when small.
4. Confirmation needed: team policy decision.

### Full-context comparison

1. Found: assignment explicitly requires 3-4 question comparison against putting all documents in context.
2. Why it matters: must be planned into evaluation, not left for the end.
3. Recommended decision: Person 3 owns harness; Person 2 exposes a full-context baseline function if time allows.
4. Confirmation needed: team only.
