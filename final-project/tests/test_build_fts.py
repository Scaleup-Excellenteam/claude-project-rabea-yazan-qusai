"""
Owner: Person 1

Tests for index/schema.sql + index/build_fts.py.

Real PDFs are not available in this repository yet, so these tests
build synthetic Section objects directly and index them into a
temporary on-disk SQLite database. search() itself is out of scope
here - see tools/text_tools.py for a later checkpoint.
"""

from __future__ import annotations

import sqlite3

import pytest

from extract.sections import Section
from index.build_fts import build_index, create_schema, upsert_sections


def _section(
    section_id: str,
    source_id: str = "yb",
    title: str = "Heading",
    text: str = "Body text.",
    page_start: int = 1,
    page_end: int = 1,
    section_order: int = 0,
) -> Section:
    return Section(
        section_id=section_id,
        source_id=source_id,
        title=title,
        normalized_title=title,
        parent_section_id=None,
        page_start=page_start,
        page_end=page_end,
        section_order=section_order,
        text=text,
        text_quality_notes=None,
    )


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "app.db"


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')").fetchall()
    return {row[0] for row in rows}


def test_schema_creation_creates_sections_and_fts_tables(db_path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        create_schema(conn)
        names = _table_names(conn)
        assert "sections" in names
        assert "sections_fts" in names
    finally:
        conn.close()


def test_schema_creation_is_idempotent(db_path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        create_schema(conn)
        create_schema(conn)  # must not raise
        names = _table_names(conn)
        assert "sections" in names
    finally:
        conn.close()


def test_sections_are_inserted_correctly(db_path) -> None:
    section = _section("yb:001:Heading", title="Heading", text="Body text.")
    build_index(db_path, [section])

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT section_id, source_id, title, text FROM sections WHERE section_id = ?",
            (section.section_id,),
        ).fetchone()
    finally:
        conn.close()

    assert row == (section.section_id, "yb", "Heading", "Body text.")


def test_page_start_and_page_end_are_preserved(db_path) -> None:
    section = _section("yb:005:Chapter", page_start=5, page_end=7)
    build_index(db_path, [section])

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT page_start, page_end FROM sections WHERE section_id = ?",
            (section.section_id,),
        ).fetchone()
    finally:
        conn.close()

    assert row == (5, 7)


def test_stable_section_id_is_preserved_as_primary_key(db_path) -> None:
    section = _section("yb:001:Stable-Id")
    build_index(db_path, [section])

    conn = sqlite3.connect(db_path)
    try:
        ids = [r[0] for r in conn.execute("SELECT section_id FROM sections").fetchall()]
    finally:
        conn.close()

    assert ids == ["yb:001:Stable-Id"]


def test_fts5_table_is_populated(db_path) -> None:
    sections = [_section("yb:001:A", title="A"), _section("yb:002:B", title="B", page_start=2, page_end=2)]
    build_index(db_path, sections)

    conn = sqlite3.connect(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM sections_fts").fetchone()[0]
    finally:
        conn.close()

    assert count == 2


def test_hebrew_unicode_text_is_queryable_via_fts_match(db_path) -> None:
    section = _section(
        "yb:001:Hebrew",
        title="פרק ראשון",
        text="חובת השתתפות לימודים ותרגילים.",
    )
    build_index(db_path, [section])

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT section_id FROM sections_fts WHERE sections_fts MATCH ?",
            ("לימודים",),
        ).fetchall()
    finally:
        conn.close()

    assert rows == [(section.section_id,)]


def test_bm25_ranking_function_is_usable_on_fts_table(db_path) -> None:
    sections = [
        _section("yb:001:A", title="לימודים", text="לימודים לימודים לימודים"),
        _section("yb:002:B", title="אחר", text="לימודים פעם אחת"),
    ]
    build_index(db_path, sections)

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT section_id, bm25(sections_fts) AS score
            FROM sections_fts
            WHERE sections_fts MATCH ?
            ORDER BY score
            """,
            ("לימודים",),
        ).fetchall()
    finally:
        conn.close()

    assert [r[0] for r in rows] == ["yb:001:A", "yb:002:B"]


def test_rebuilding_with_the_same_sections_does_not_duplicate_rows(db_path) -> None:
    sections = [_section("yb:001:A"), _section("yb:002:B", page_start=2, page_end=2)]

    build_index(db_path, sections)
    build_index(db_path, sections)  # rebuild

    conn = sqlite3.connect(db_path)
    try:
        sections_count = conn.execute("SELECT COUNT(*) FROM sections").fetchone()[0]
        fts_count = conn.execute("SELECT COUNT(*) FROM sections_fts").fetchone()[0]
    finally:
        conn.close()

    assert sections_count == 2
    assert fts_count == 2


def test_rebuild_with_updated_text_replaces_fts_row_not_appends(db_path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        create_schema(conn)
        upsert_sections(conn, [_section("yb:001:A", text="original text")])
        upsert_sections(conn, [_section("yb:001:A", text="updated text")])

        text = conn.execute(
            "SELECT text FROM sections WHERE section_id = ?", ("yb:001:A",)
        ).fetchone()[0]
        fts_rows = conn.execute(
            "SELECT text FROM sections_fts WHERE section_id = ?", ("yb:001:A",)
        ).fetchall()
    finally:
        conn.close()

    assert text == "updated text"
    assert fts_rows == [("updated text",)]


def test_multiple_sources_can_coexist(db_path) -> None:
    sections = [
        _section("yb:001:A", source_id="yearbook", title="A"),
        _section("reg:001:B", source_id="regulations", title="B"),
    ]
    build_index(db_path, sections)

    conn = sqlite3.connect(db_path)
    try:
        source_ids = {
            row[0]
            for row in conn.execute("SELECT DISTINCT source_id FROM sections").fetchall()
        }
    finally:
        conn.close()

    assert source_ids == {"yearbook", "regulations"}


def test_empty_section_list_is_handled_safely(db_path) -> None:
    build_index(db_path, [])  # must not raise

    conn = sqlite3.connect(db_path)
    try:
        names = _table_names(conn)
        count = conn.execute("SELECT COUNT(*) FROM sections").fetchone()[0]
    finally:
        conn.close()

    assert "sections" in names
    assert count == 0
