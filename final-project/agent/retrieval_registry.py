"""
Production registry adapters for the real Person 1/2 retrieval tools.

The retrieval modules own DB queries and result construction.  This file
only binds configured database paths and adapts small Anthropic schema
signature differences, so the agent can dispatch tools by name with the
arguments declared in agent/tool_defs.py.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEXT_DB_PATH = PROJECT_ROOT / "data" / "app.db"
DEFAULT_COURSE_DB_PATH = PROJECT_ROOT / "data" / "course_data.db"

TEXT_DB_ENV = "APP_DB_PATH"
COURSE_DB_ENV = "APP_COURSE_DB_PATH"


class RetrievalSetupError(RuntimeError):
    """Raised when local retrieval databases are absent or incomplete."""


def _project_path(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _path_from_env(env, name: str, default: Path) -> Path:
    source = os.environ if env is None else env
    value = source.get(name)
    return _project_path(value) if value else default


def get_text_db_path(env=None) -> Path:
    return _path_from_env(env, TEXT_DB_ENV, DEFAULT_TEXT_DB_PATH)


def get_course_db_path(env=None) -> Path:
    return _path_from_env(env, COURSE_DB_ENV, DEFAULT_COURSE_DB_PATH)


def _table_count(conn: sqlite3.Connection, table: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    return int(row[0]) if row else 0


def _validate_text_db(path: Path) -> None:
    if not path.exists():
        raise RetrievalSetupError(f"missing prose index database: {path}")
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
                ).fetchall()
            }
            required = {"sections", "sections_fts"}
            missing = sorted(required - tables)
            if missing:
                raise RetrievalSetupError(
                    f"prose index database is missing tables: {', '.join(missing)}"
                )
            if _table_count(conn, "sections") == 0:
                raise RetrievalSetupError("prose index database contains no sections")
        finally:
            conn.close()
    except RetrievalSetupError:
        raise
    except sqlite3.Error as exc:
        raise RetrievalSetupError(f"prose index database cannot be opened: {exc}") from exc


def _validate_course_db(path: Path) -> None:
    if not path.exists():
        raise RetrievalSetupError(f"missing course database: {path}")
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
                ).fetchall()
            }
            required = {
                "curricula",
                "courses",
                "table_totals",
                "catalog_courses",
                "clusters",
                "cluster_courses",
            }
            missing = sorted(required - tables)
            if missing:
                raise RetrievalSetupError(
                    f"course database is missing tables: {', '.join(missing)}"
                )
            if _table_count(conn, "curricula") == 0:
                raise RetrievalSetupError("course database contains no curricula")
            if _table_count(conn, "catalog_courses") == 0:
                raise RetrievalSetupError("course database contains no catalog courses")
        finally:
            conn.close()
    except RetrievalSetupError:
        raise
    except sqlite3.Error as exc:
        raise RetrievalSetupError(f"course database cannot be opened: {exc}") from exc


def build_production_tool_registry(*, text_db_path=None, course_db_path=None, env=None) -> dict:
    """Return the real six-tool registry expected by agent.loop.

    Tests may pass explicit temporary DB paths.  Production uses
    APP_DB_PATH for prose sections and APP_COURSE_DB_PATH for course
    data, both resolved relative to final-project/ when relative.
    """
    from tools import course_tools, text_tools

    text_path = _project_path(text_db_path) if text_db_path else get_text_db_path(env=env)
    course_path = _project_path(course_db_path) if course_db_path else get_course_db_path(env=env)

    _validate_text_db(text_path)
    _validate_course_db(course_path)

    return {
        "list_sections": lambda: text_tools.list_sections(text_path),
        "get_section": lambda section_id: text_tools.get_section(text_path, section_id),
        "search": lambda query, limit=5: text_tools.search(text_path, query, limit=limit),
        "list_curricula": lambda: course_tools.list_curricula(db_path=course_path),
        "get_course_table": (
            lambda curriculum, year, semester: course_tools.get_course_table(
                curriculum, year, semester, db_path=course_path
            )
        ),
        "get_course": lambda course_number: course_tools.get_course(course_number, db_path=course_path),
    }
