# Start Here

Read this before doing anything else. It defines the order of operations
for the whole team. See `SPEC.md` for full technical detail and
`TEAM_RULES.md` for collaboration rules.

1. Merge this shared setup branch (`shared-setup`) into `main`.
2. All 3 team members work together first on RTL normalization - do not
   split into solo branches yet.
3. Inspect raw PDF extraction output together (both PDFs in
   `final-project/pdfs/`) so everyone sees the real artifacts (glyph
   issues, visual-order RTL text, etc. - see `SPEC.md` section 12).
4. Implement and test `normalize(raw_line: str) -> str` in `contracts.py`
   together. This is the first shared implementation task.
5. Inspect normalized output manually against a few known-tricky pages
   (TOC, pages 9-12, pages 13-24, key regulation pages).
6. Freeze the shared contracts in `contracts.py` (schemas, tool
   signatures, citation shape, curriculum id enum) per `SPEC.md`
   section 10.
7. Merge those shared changes into `main`.
8. Each person pulls the updated `main`.
9. Each person creates their own feature branch from `main`:
   - `feature/prose-index` (Person 1)
   - `feature/course-data` (Person 2)
   - `feature/agent-ui` (Person 3)
10. Each person uses their dedicated instruction file
    (`PERSON_1_PROSE_INDEX.md`, `PERSON_2_COURSE_DATA.md`,
    `PERSON_3_AGENT_UI.md`) as the brief for their own work (with
    Claude/Codex or by hand).
11. Each person merges their feature branch back into `main` via a pull
    request, after merging the latest `main` into their branch first.
12. Person 3 performs final integration (real tools + real agent +
    Streamlit UI) and runs the evaluation described in `SPEC.md`
    section 8.
