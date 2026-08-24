-- Owner: Person 1 / shared where required
-- SQLite schema for prose sections + FTS5 search.
-- Idempotent: safe to execute against an existing database.

CREATE TABLE IF NOT EXISTS sections (
    section_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    title TEXT NOT NULL,
    normalized_title TEXT NOT NULL,
    parent_section_id TEXT,
    page_start INTEGER NOT NULL,
    page_end INTEGER NOT NULL,
    section_order INTEGER NOT NULL,
    text TEXT NOT NULL,
    text_quality_notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_sections_source_id ON sections (source_id);

-- Standalone FTS5 table (not content= linked, since section_id is TEXT
-- and FTS5 external-content requires an integer rowid mapping).
-- section_id is carried as UNINDEXED so callers can join back to the
-- canonical `sections` table for metadata/citations.
CREATE VIRTUAL TABLE IF NOT EXISTS sections_fts USING fts5(
    section_id UNINDEXED,
    title,
    text,
    tokenize = 'unicode61'
);
