"""
Owner: Person 1

Purpose:
Prose retrieval tools: list_sections, get_section, search.

contracts.py is not finalized yet, so the dict shapes returned here are
a local, documented best-effort approximation of SPEC.md section 5 -
not the frozen contract. In particular:
  - `source_id` is returned (what the sections table actually stores),
    not the `source` filename shown in SPEC.md's list_sections example
    (no sources/filename table exists yet in this schema).
  - get_section()'s not-found shape ({"section_id", "error"}) is a
    placeholder; SPEC.md section 5/7 only says a missing id "returns a
    structured error", without specifying its exact shape.
Once contracts.py freezes these shapes, this module's return values
must be reconciled against it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from index.build_fts import create_schema

_DEFAULT_LIMIT = 5
_MAX_LIMIT = 10
_SNIPPET_TOKENS = 12


def _connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    # Idempotent: makes an empty/fresh db path safe to query immediately,
    # without requiring callers to have run build_index() first.
    create_schema(conn)
    return conn


def list_sections(db_path: str | Path, source_id: str | None = None) -> list[dict]:
    """Return section metadata only (no body text), deterministically ordered.

    If source_id is given, restrict to that source; otherwise return
    sections for all sources.
    """
    conn = _connect(db_path)
    try:
        if source_id is None:
            rows = conn.execute(
                """
                SELECT section_id, source_id, title, page_start, page_end, section_order
                FROM sections
                ORDER BY source_id, section_order, section_id
                """
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT section_id, source_id, title, page_start, page_end, section_order
                FROM sections
                WHERE source_id = ?
                ORDER BY source_id, section_order, section_id
                """,
                (source_id,),
            ).fetchall()
    finally:
        conn.close()

    return [
        {
            "section_id": row[0],
            "source_id": row[1],
            "title": row[2],
            "page_start": row[3],
            "page_end": row[4],
            "section_order": row[5],
        }
        for row in rows
    ]


def get_section(db_path: str | Path, section_id: str) -> dict:
    """Retrieve one section's full text and citation metadata by id.

    Returns a structured {"section_id", "error": "section_not_found"}
    dict when the id is unknown - never silently returns empty text.
    """
    conn = _connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT section_id, source_id, title, text, page_start, page_end
            FROM sections
            WHERE section_id = ?
            """,
            (section_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return {"section_id": section_id, "error": "section_not_found"}

    found_id, found_source_id, title, text, page_start, page_end = row
    return {
        "section_id": found_id,
        "source_id": found_source_id,
        "title": title,
        "text": text,
        "page_start": page_start,
        "page_end": page_end,
        "citations": [
            {
                "source_id": found_source_id,
                "page_start": page_start,
                "page_end": page_end,
            }
        ],
    }


def _quote_as_phrase(query: str) -> str:
    return '"' + query.replace('"', '""') + '"'


_SEARCH_SQL = """
    SELECT
        sections_fts.section_id,
        s.source_id,
        s.title,
        s.page_start,
        s.page_end,
        bm25(sections_fts) AS score,
        snippet(sections_fts, 2, '', '', ' ... ', ?) AS snippet
    FROM sections_fts
    JOIN sections s ON s.section_id = sections_fts.section_id
    WHERE sections_fts MATCH ?
    ORDER BY score
    LIMIT ?
"""


def search(db_path: str | Path, query: str, limit: int = _DEFAULT_LIMIT) -> list[dict]:
    """BM25-ranked lexical search over section title/text via FTS5 MATCH.

    query normalization (e.g. RTL/glyph cleanup) is out of scope here -
    that is the shared contracts.normalize() used upstream at index time
    (extract/pdf_text.py). This function assumes the caller passes a
    query in the same normalized form the index was built from; once
    contracts.normalize() exists, callers (e.g. the agent tool loop)
    should apply it to the query before calling search().

    Returns at most `limit` (clamped to 1..10) results ordered by BM25
    score ascending (more negative = better match). No matches -> [].
    Malformed FTS5 query syntax never raises - it degrades to a safely
    quoted phrase search, and if that still fails, returns [].
    """
    query = (query or "").strip()
    if not query:
        return []

    effective_limit = max(1, min(limit, _MAX_LIMIT))

    conn = _connect(db_path)
    try:
        try:
            rows = conn.execute(
                _SEARCH_SQL, (_SNIPPET_TOKENS, query, effective_limit)
            ).fetchall()
        except sqlite3.OperationalError:
            safe_query = _quote_as_phrase(query)
            try:
                rows = conn.execute(
                    _SEARCH_SQL, (_SNIPPET_TOKENS, safe_query, effective_limit)
                ).fetchall()
            except sqlite3.OperationalError:
                return []
    finally:
        conn.close()

    return [
        {
            "section_id": row[0],
            "source_id": row[1],
            "title": row[2],
            "page_start": row[3],
            "page_end": row[4],
            "score": row[5],
            "snippet": row[6],
        }
        for row in rows
    ]
