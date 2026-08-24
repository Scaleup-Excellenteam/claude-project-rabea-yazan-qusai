# Hebrew Agentic Retrieval Chat Over Department Documents

Local Hebrew/RTL Streamlit chat app answering student questions about
Computer Science degree requirements and undergraduate academic
regulations, grounded only in two official source PDFs. Full
specification: `SPEC.md`.

This is the **shared project setup**. No business logic is implemented
yet. Start with `START_HERE.md`.

## Structure

- `pdfs/` - source PDFs (yearbook + regulations).
- `extract/` - PDF text/table extraction (Person 1: `pdf_text.py`,
  `sections.py`; Person 2: `tables.py`, `catalog.py`, `prereqs.py`).
- `index/` - SQLite schema + index builders (Person 1: `build_fts.py`;
  Person 2: `build_courses.py`).
- `tools/` - retrieval tool implementations matching `contracts.py`
  (Person 1: `text_tools.py`; Person 2: `course_tools.py`).
- `agent/` - Claude tool-use loop, system prompt, tool schemas, metrics
  (Person 3).
- `eval/` - evaluation harness and full-context baseline (Person 3).
- `data/extracted/` - generated intermediate extraction output (not
  committed; see `.gitignore`).
- `tests/` - tests, one area per owner.
- `contracts.py` - shared typed contracts/signatures. Do not change
  unilaterally.
- `app.py` - Streamlit entry point (Person 3).

## Team

Three people, one branch each, from `main`:

- `feature/prose-index` - see `PERSON_1_PROSE_INDEX.md`.
- `feature/course-data` - see `PERSON_2_COURSE_DATA.md`.
- `feature/agent-ui` - see `PERSON_3_AGENT_UI.md`.

Collaboration rules: `TEAM_RULES.md`. Order of operations: `START_HERE.md`.

## Setup (once implementation begins)

```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env  # fill in ANTHROPIC_API_KEY
```

Run locally only (per assignment rules - no public deployment):

```bash
streamlit run app.py
```

## Evaluation

Once the agent and UI are integrated, run the 10 official evaluation
questions (`SPEC.md` section 8) via `eval/run_eval.py` and report:

- actual outputs and failure analysis
- average tool calls per question
- a full-context comparison for 3-4 questions (`eval/baseline_context.py`)

These results belong in this README before submission.
