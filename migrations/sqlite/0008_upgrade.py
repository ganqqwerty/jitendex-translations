"""Compatibility upgrade for SQLite databases created before logical schema v8."""

from __future__ import annotations


def apply(connection) -> None:
    frequency_article_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(frequency_article)")
    }
    if "term" not in frequency_article_columns:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.executescript(
            """
            BEGIN IMMEDIATE;
            DROP INDEX IF EXISTS frequency_term_rank;
            ALTER TABLE frequency_article RENAME TO frequency_article_v6;
            ALTER TABLE frequency_term RENAME TO frequency_term_v6;
            CREATE TABLE frequency_term(
              source TEXT NOT NULL, source_sha256 TEXT NOT NULL, rank INTEGER NOT NULL,
              term TEXT NOT NULL, matched INTEGER NOT NULL DEFAULT 0 CHECK(matched IN (0,1)),
              PRIMARY KEY(source, source_sha256, term)
            );
            CREATE INDEX frequency_term_rank ON frequency_term(source,source_sha256,rank);
            CREATE TABLE frequency_article(
              source TEXT NOT NULL, source_sha256 TEXT NOT NULL, rank INTEGER NOT NULL, term TEXT NOT NULL,
              article_id INTEGER NOT NULL REFERENCES article(id),
              match_kind TEXT NOT NULL CHECK(match_kind IN ('expression','reading')),
              PRIMARY KEY(source, source_sha256, term, article_id),
              FOREIGN KEY(source, source_sha256, term)
                REFERENCES frequency_term(source, source_sha256, term)
            );
            INSERT INTO frequency_term(source,source_sha256,rank,term,matched)
            SELECT source,source_sha256,rank,term,matched FROM frequency_term_v6;
            INSERT INTO frequency_article(source,source_sha256,rank,term,article_id,match_kind)
            SELECT fa.source,fa.source_sha256,fa.rank,ft.term,fa.article_id,fa.match_kind
            FROM frequency_article_v6 fa JOIN frequency_term_v6 ft
              ON ft.source=fa.source AND ft.source_sha256=fa.source_sha256 AND ft.rank=fa.rank;
            DROP TABLE frequency_article_v6;
            DROP TABLE frequency_term_v6;
            COMMIT;
            """
        )
        connection.execute("PRAGMA foreign_keys = ON")
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"frequency migration produced foreign-key violations: {violations}")
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(run)")}
    if "pipeline_version" not in columns:
        connection.execute(
            "ALTER TABLE run ADD COLUMN pipeline_version TEXT NOT NULL DEFAULT 'scalar-v1'"
        )
    attempt_columns = {row["name"] for row in connection.execute("PRAGMA table_info(attempt)")}
    audit_columns = {
        "effective_model_id": "TEXT", "reasoning_effort": "TEXT",
        "transport": "TEXT CHECK(transport IS NULL OR transport IN ('responses-sync','batch-api','codex-agent'))",
        "api_request_id": "TEXT", "api_custom_id": "TEXT", "api_job_id": "TEXT",
        "input_tokens": "INTEGER CHECK(input_tokens IS NULL OR input_tokens >= 0)",
        "cached_input_tokens": "INTEGER CHECK(cached_input_tokens IS NULL OR cached_input_tokens >= 0)",
        "output_tokens": "INTEGER CHECK(output_tokens IS NULL OR output_tokens >= 0)",
        "total_tokens": "INTEGER CHECK(total_tokens IS NULL OR total_tokens >= 0)",
        "finish_reason": "TEXT", "status_reason": "TEXT",
        "latency_ms": "INTEGER CHECK(latency_ms IS NULL OR latency_ms >= 0)",
    }
    for name, declaration in audit_columns.items():
        if name not in attempt_columns:
            connection.execute(f"ALTER TABLE attempt ADD COLUMN {name} {declaration}")
    tag_columns = {row["name"] for row in connection.execute("PRAGMA table_info(jitendex_tag)")}
    for name, declaration in {
        "translation_source": "TEXT", "translation_source_sha256": "TEXT",
        "translation_source_path": "TEXT", "approved_at": "TEXT",
    }.items():
        if name not in tag_columns:
            connection.execute(f"ALTER TABLE jitendex_tag ADD COLUMN {name} {declaration}")
    connection.execute(
        """INSERT INTO run_article(run_id,article_id,structural_fingerprint)
        SELECT DISTINCT tu.run_id,tu.article_id,a.structural_fingerprint
        FROM translation_unit tu JOIN article a ON a.id=tu.article_id
        WHERE a.structural_fingerprint IS NOT NULL
        ON CONFLICT(run_id,article_id) DO NOTHING"""
    )
