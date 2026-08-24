"""
Owner: Person 3

Purpose:
Claude tool-use schema definitions matching the retrieval tool
contracts in SPEC.md section 5, plus the name->callable dispatch used
by agent/loop.py to invoke either stub or real tool implementations
without changing the loop itself.
"""

TOOL_DEFINITIONS = [
    {
        "name": "list_sections",
        "description": (
            "List the document table of contents: concise metadata for "
            "every structured section available across both source "
            "PDFs (title, source, page range). Does not return full "
            "section text; use get_section for that."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_section",
        "description": (
            "Retrieve the full text of one known section by its exact "
            "section_id (from list_sections or search), for when a "
            "search snippet is insufficient or exact policy wording "
            "matters."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "section_id": {
                    "type": "string",
                    "description": "Exact section_id from list_sections or search.",
                },
            },
            "required": ["section_id"],
        },
    },
    {
        "name": "search",
        "description": (
            "BM25 lexical search (SQLite FTS5) over normalized section "
            "text. Use for factual lookup by course name, policy term, "
            "or phrase. Not semantic search."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Hebrew or mixed Hebrew/English search query.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return, default 5, cap 10.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_curricula",
        "description": (
            "List curriculum/plan ids and display names (degree type, "
            "start term, page range) to disambiguate before calling "
            "get_course_table."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_course_table",
        "description": (
            "Return all structured course rows for one curriculum/"
            "year/semester table, plus computed credit totals. "
            "curriculum must be an exact id from list_curricula."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "curriculum": {
                    "type": "string",
                    "description": (
                        "Curriculum id, e.g. single_major_fall, "
                        "single_major_spring, dual_major_fall, "
                        "dual_major_spring, support_center_spread, "
                        "computational_biology."
                    ),
                },
                "year": {
                    "type": "integer",
                    "description": "Study year, 1-4.",
                },
                "semester": {
                    "type": "integer",
                    "description": "Semester number, 1-7 depending on plan.",
                },
            },
            "required": ["curriculum", "year", "semester"],
        },
    },
    {
        "name": "get_course",
        "description": (
            "Look up a single course by its exact course number, "
            "returning its stored fields (name, credits, hours, "
            "prerequisites, requirement type) with citation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "course_number": {
                    "type": "string",
                    "description": "Exact course number, e.g. 0122407.",
                },
            },
            "required": ["course_number"],
        },
    },
]

TOOL_NAMES = frozenset(tool["name"] for tool in TOOL_DEFINITIONS)


def dispatch_tool_call(name, arguments, registry):
    """Invoke the backend callable registered for `name` with `arguments`.

    Never raises: unknown tool names and callable exceptions both come
    back as structured error dicts so a single bad/failing tool call
    cannot crash the agent loop.
    """
    if name not in registry:
        return {"error": "unknown_tool", "tool_name": name}
    try:
        return registry[name](**arguments)
    except Exception as exc:
        return {"error": "tool_exception", "tool_name": name, "message": str(exc)}
