# Team Rules

These rules exist to keep three people working in parallel on the same
repo without stepping on each other. Follow them for every branch/PR.

1. `main` is the accepted/stable shared branch.
2. Nobody develops directly on `main`.
3. This shared setup branch is merged into `main` first, before any
   feature work starts.
4. All feature branches are created from an up-to-date `main`.
5. Team members avoid editing files owned by another person unless it's
   been explicitly coordinated first (see ownership sections in
   `PERSON_1_PROSE_INDEX.md`, `PERSON_2_COURSE_DATA.md`,
   `PERSON_3_AGENT_UI.md`).
6. Shared contracts in `contracts.py` must not be changed unilaterally.
7. If a contract in `contracts.py` must change, all 3 team members agree
   first, then one person applies the change and announces it.
8. Each branch must merge the latest `main` before opening a final PR.
9. `.env` and secrets are never committed. Use `.env.example` as the
   template.
10. Generated databases/output (`*.db`, `*.sqlite`, `data/extracted/*`)
    are not committed unless explicitly required for grading/submission.
11. Every owner writes tests for their own area under `tests/`.
12. Integration failures are fixed through the shared contract
    (`contracts.py`), not by copying or reimplementing another person's
    logic in your own files.
