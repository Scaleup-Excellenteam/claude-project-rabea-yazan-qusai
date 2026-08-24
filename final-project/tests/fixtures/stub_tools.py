"""
Owner: Person 3

Purpose:
Contract-shaped stub tool implementations for testing agent/loop.py
and agent/tool_defs.py before Person 1/2's real tools
(tools/text_tools.py, tools/course_tools.py) are merged. Shapes match
SPEC.md section 5 exactly. This is fixture data only, not real
retrieval logic, and must not be mistaken for it.
"""

_SOURCE_YEARBOOK = "שנתון תשפז- מדעי המחשב.pdf"

_SECTIONS = [
    {
        "section_id": "yearbook:course-plans:single-fall",
        "title": "מערכת לימודים מוצעת לקורסי החובה למתחילים בסמסטר סתיו/א'",
        "source": _SOURCE_YEARBOOK,
        "page_start": 9,
        "page_end": 10,
        "text": (
            "מבוא למדעי המחשב (0111401), 5 נקודות זכות. "
            "אלגוריתמים 1 (0122407), 5 נקודות זכות, דרישות קדם: פרקים במבני נתונים."
        ),
    },
]

_CURRICULA = [
    {
        "curriculum_id": "single_major_fall",
        "name": "חד־חוגי מדעי המחשב, תחילת לימודים סתיו",
        "degree_type": "B.Sc.",
        "start_term": "fall",
        "source_page_start": 9,
        "source_page_end": 10,
    },
]

_COURSE_TABLE_ROWS = {
    ("single_major_fall", 2, 4): [
        {
            "course_number": "0122407",
            "course_name": "אלגוריתמים 1",
            "credits": 5,
            "prerequisites_text": "פרקים במבני נתונים",
            "source": _SOURCE_YEARBOOK,
            "page": 10,
        },
    ],
}

_COURSES = {
    "0111401": {
        "course_number": "0111401",
        "course_name": "מבוא למדעי המחשב",
        "credits": 5,
        "prerequisites_text": None,
        "source": _SOURCE_YEARBOOK,
        "page": 9,
    },
    "0122407": {
        "course_number": "0122407",
        "course_name": "אלגוריתמים 1",
        "credits": 5,
        "prerequisites_text": "פרקים במבני נתונים",
        "source": _SOURCE_YEARBOOK,
        "page": 10,
    },
}


def _list_sections():
    return [
        {k: v for k, v in section.items() if k != "text"}
        for section in _SECTIONS
    ]


def _get_section(section_id):
    for section in _SECTIONS:
        if section["section_id"] == section_id:
            return {
                "section_id": section["section_id"],
                "title": section["title"],
                "text": section["text"],
                "citations": [
                    {
                        "source": section["source"],
                        "page_start": section["page_start"],
                        "page_end": section["page_end"],
                    }
                ],
            }
    return {"error": "not_found", "section_id": section_id}


def _search(query, limit=5):
    results = []
    for section in _SECTIONS:
        if query in section["text"] or query in section["title"]:
            results.append(
                {
                    "section_id": section["section_id"],
                    "title": section["title"],
                    "snippet": section["text"][:80],
                    "score": -1.0,
                    "source": section["source"],
                    "page_start": section["page_start"],
                    "page_end": section["page_end"],
                }
            )
    return results[:limit]


def _list_curricula():
    return list(_CURRICULA)


def _get_course_table(curriculum, year, semester):
    valid_ids = [c["curriculum_id"] for c in _CURRICULA]
    if curriculum not in valid_ids:
        return {"error": "ambiguous_curriculum", "valid_curricula": valid_ids}
    rows = _COURSE_TABLE_ROWS.get((curriculum, year, semester))
    if rows is None:
        return {"error": "not_found", "curriculum": curriculum, "year": year, "semester": semester}
    total_credits = sum(row["credits"] for row in rows)
    return {
        "curriculum": curriculum,
        "year": year,
        "semester": semester,
        "rows": rows,
        "totals": {"credits": total_credits},
        "citation": {"source": _SOURCE_YEARBOOK, "page": rows[0]["page"]},
    }


def _get_course(course_number):
    course = _COURSES.get(course_number)
    if course is None:
        return {"error": "not_found", "course_number": course_number}
    return dict(course)


def build_stub_registry():
    """Return a name->callable registry matching agent.tool_defs.TOOL_NAMES."""
    return {
        "list_sections": _list_sections,
        "get_section": _get_section,
        "search": _search,
        "list_curricula": _list_curricula,
        "get_course_table": _get_course_table,
        "get_course": _get_course,
    }
