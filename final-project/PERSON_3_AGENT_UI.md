# Person 3: Agent Loop, Streamlit UI, Evaluation

Branch: `feature/agent-ui` (create from an up-to-date `main`, after the
shared RTL normalization checkpoint - see `START_HERE.md`).

## Ownership

- `agent/loop.py`
- `agent/system_prompt.py`
- `agent/tool_defs.py`
- `agent/metrics.py`
- `app.py`
- `eval/questions.py`
- `eval/run_eval.py`
- `eval/baseline_context.py`
- related tests under `tests/`

## Responsibilities

- Build the Claude tool-use loop (`agent/loop.py`).
- Define tool schemas matching `contracts.py` exactly
  (`agent/tool_defs.py`).
- Initially work against stubs/fixtures, not real tools - Person 1 and
  Person 2's real implementations may not be merged yet.
- Implement the grounding/refusal policy: no tool result grounding the
  claim means no factual answer.
- Implement citations on every factual answer (document + section/page).
- Implement prompt caching: stable cached prefix for tools/system
  prompt, `cache_control` on the final block of each turn (`SPEC.md`
  section 2).
- Enforce a `max_iterations` limit between 5 and 8 for the tool-use loop.
- Track tool calls and metrics (`agent/metrics.py`): question_id,
  tool_name, parameters, timestamp, success, result_count.
- Build the Streamlit Hebrew/RTL chat (`app.py`).
- Implement the evaluation harness (`eval/run_eval.py`,
  `eval/questions.py`).
- Integrate real tools (`tools/text_tools.py`, `tools/course_tools.py`)
  once Person 1 and Person 2 merge into `main`.
- Run the 10 official evaluation questions and record actual outputs.
- Implement whole-corpus baseline comparison for 3-4 questions
  (`eval/baseline_context.py`).

## Must not modify

- Person 1's extraction/index internals (`extract/pdf_text.py`,
  `extract/sections.py`, `index/schema.sql`, `index/build_fts.py`,
  `tools/text_tools.py` internals).
- Person 2's structured course extraction internals
  (`extract/tables.py`, `extract/catalog.py`, `extract/prereqs.py`,
  `index/build_courses.py`, `tools/course_tools.py` internals).
- Shared contracts in `contracts.py` without team approval
  (see `TEAM_RULES.md`).

## Definition of done

- Agent can call stub tools first, then real tools, without changing
  its own code (only the tool implementations swap in).
- No tool result means no factual answer.
- Missing information produces the exact string `לא מופיע במסמכים`.
- Every factual answer has a citation.
- Max iteration behavior works as specified (5-8).
- Prompt caching is measured (e.g. cache hit/miss reporting).
- Q10 (academic secretariat office hours) refuses correctly.
- Streamlit app works locally (`streamlit run app.py`).
- Evaluation results and metrics are captured and ready to drop into
  the README.
