"""
Owner: Person 1

Purpose:
Build SQLite sections table and FTS5 (unicode61) index with BM25 ranking.

Consumes Section records produced by extract.sections.extract_sections()
and persists them into the canonical `sections` table plus the
`sections_fts` FTS5 virtual table for prose search (index/schema.sql).
Does not implement search() itself - that belongs to tools/text_tools.py
(a later checkpoint).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path

from extract.sections import Section

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

_UPSERT_SECTION_SQL = """
    INSERT INTO sections (
        section_id, source_id, title, normalized_title,
        parent_section_id, page_start, page_end, section_order,
        text, text_quality_notes
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(section_id) DO UPDATE SET
        source_id = excluded.source_id,
        title = excluded.title,
        normalized_title = excluded.normalized_title,
        parent_section_id = excluded.parent_section_id,
        page_start = excluded.page_start,
        page_end = excluded.page_end,
        section_order = excluded.section_order,
        text = excluded.text,
        text_quality_notes = excluded.text_quality_notes
"""


def create_schema(conn: sqlite3.Connection) -> None:
    """Create the sections table and FTS5 index if they don't exist yet."""
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema_sql)


def upsert_sections(conn: sqlite3.Connection, sections: Iterable[Section]) -> None:
    """Insert or replace Section records, keeping sections_fts in sync.

    Matched by the stable section_id, so calling this repeatedly with
    the same sections never creates duplicate rows in either table.
    """
    with conn:
        for section in sections:
            conn.execute(
                _UPSERT_SECTION_SQL,
                (
                    section.section_id,
                    section.source_id,
                    section.title,
                    section.normalized_title,
                    section.parent_section_id,
                    section.page_start,
                    section.page_end,
                    section.section_order,
                    section.text,
                    section.text_quality_notes,
                ),
            )
            conn.execute(
                "DELETE FROM sections_fts WHERE section_id = ?",
                (section.section_id,),
            )
            conn.execute(
                "INSERT INTO sections_fts (section_id, title, text) VALUES (?, ?, ?)",
                (section.section_id, section.title, section.text),
            )


def build_index(db_path: str | Path, sections: Iterable[Section]) -> None:
    """Create the schema and replace the index with the given sections.

    ``build_index`` represents a complete rebuild, so rows absent from the
    new extraction must not survive as stale searchable sections.  Callers
    that need incremental behavior can use ``upsert_sections`` directly.
    """
    sections = list(sections)
    conn = sqlite3.connect(db_path)
    try:
        create_schema(conn)
        with conn:
            conn.execute("DELETE FROM sections_fts")
            conn.execute("DELETE FROM sections")
        upsert_sections(conn, sections)
    finally:
        conn.close()
