import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from jitendex_ru.config import Config
from jitendex_ru.database import (
    ErrorCategory, HybridRow, _postgres_sql, classify_database_error,
)
from jitendex_ru.database_tools import normalized_table_hash, require_migration_safe
from jitendex_ru.db import SCHEMA_VERSION, connect, initialize


def test_database_config_defaults_to_sqlite_and_reads_url_only_from_environment(tmp_path, monkeypatch):
    config = Config(tmp_path, {"project": {"work_dir": "work", "dist_dir": "dist"}})
    assert config.db_backend == "sqlite"
    assert config.db_path == tmp_path / "work/progress.sqlite3"
    assert config.db_pool_max == 4

    postgres = Config(tmp_path, {
        "project": {"work_dir": "work", "dist_dir": "dist"},
        "database": {"backend": "postgresql", "url_env": "TEST_DATABASE_URL"},
    })
    with pytest.raises(ValueError, match="TEST_DATABASE_URL"):
        postgres.database_url()
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://example.invalid/db")
    assert postgres.database_url() == "postgresql://example.invalid/db"
    monkeypatch.setenv("JITENDEX_BENCHMARK_DATABASE_BACKEND", "sqlite")
    assert postgres.db_backend == "sqlite"
    monkeypatch.setenv("JITENDEX_BENCHMARK_WORK_DIR", str(tmp_path / "benchmark-work"))
    monkeypatch.setenv("JITENDEX_BENCHMARK_DIST_DIR", str(tmp_path / "benchmark-dist"))
    assert postgres.work_dir == (tmp_path / "benchmark-work").resolve()
    assert postgres.dist_dir == (tmp_path / "benchmark-dist").resolve()


def test_parameter_conversion_preserves_question_marks_in_literals():
    assert _postgres_sql("SELECT '?' label, value FROM item WHERE id=? AND note='it''s ?'") == (
        "SELECT '?' label, value FROM item WHERE id=%s AND note='it''s ?'"
    )


def test_hybrid_row_supports_mapping_and_offset_access():
    row = HybridRow((7, "ready"), ("id", "state"))
    assert row[0] == row["id"] == 7
    assert dict(row) == {"id": 7, "state": "ready"}


def test_normalized_table_hash_ignores_backend_row_order_but_preserves_duplicates():
    rows = [("u-2", "b"), ("u-10", "a")]
    assert normalized_table_hash(rows) == normalized_table_hash(reversed(rows))
    assert normalized_table_hash(rows) != normalized_table_hash(rows + [rows[0]])


def test_database_error_categories_cover_retry_and_constraint_cases():
    assert classify_database_error(sqlite3.OperationalError("database is locked")) is ErrorCategory.TRANSIENT
    assert classify_database_error(sqlite3.IntegrityError("unique failed")) is ErrorCategory.CONSTRAINT
    assert classify_database_error(sqlite3.OperationalError("syntax error")) is ErrorCategory.PERMANENT


def test_current_sqlite_migration_adds_benchmark_marker(tmp_path):
    path = tmp_path / "stage.sqlite3"
    initialize(path)
    with connect(path) as connection:
        assert connection.execute("SELECT MAX(version) FROM schema_meta").fetchone()[0] == SCHEMA_VERSION
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='benchmark_marker'"
        ).fetchone()[0] == 1


def test_migration_safety_refuses_claimed_or_unfinished_production(tmp_path):
    path = tmp_path / "source.sqlite3"
    initialize(path)
    connection = connect(path)
    connection.execute(
        "INSERT INTO source_snapshot(id,kind,version,url,sha256,local_path,extractor_version) "
        "VALUES (1,'jitendex','v','u','j','p','e'),(2,'kaishi','v','u','k','p','e')"
    )
    connection.execute(
        """INSERT INTO run(id,jitendex_snapshot_id,kaishi_snapshot_id,selection_sha256,
        extractor_version,prompt_sha256,review_prompt_sha256,terminology_sha256,limits_json)
        VALUES (1,1,2,'s','e','p','r','t','{}')"""
    )
    connection.execute(
        """INSERT INTO batch(id,run_id,manifest_sha256,serialized_bytes,article_count,
        unit_count,state,manifest_path) VALUES ('b',1,'m',1,0,0,'ready','m')"""
    )
    connection.commit()
    with pytest.raises(RuntimeError, match="unfinished production work"):
        require_migration_safe(connection, disposable_test=False)
    assert require_migration_safe(connection, disposable_test=True)["unfinished_batches"] == 1
    connection.execute(
        """INSERT INTO attempt(id,batch_id,worker_id,model,prompt_sha256,request_path)
        VALUES ('a','b','w','m','p','r')"""
    )
    connection.commit()
    with pytest.raises(RuntimeError, match="claimed attempts"):
        require_migration_safe(connection, disposable_test=True)
    connection.close()


def test_postgresql_schema_uses_timezone_aware_timestamps_and_current_indexes():
    root = Path(__file__).resolve().parents[1]
    schema = (root / "migrations/postgresql/0008_schema.sql").read_text()
    indexes = (root / "migrations/postgresql/0009_benchmark_marker.sql").read_text()
    assert "TIMESTAMPTZ" in schema
    assert "lease_expires_at TEXT" not in schema
    assert "batch_claim_order" in indexes
    claim_source = (root / "src/jitendex_ru/batch.py").read_text()
    assert "FOR UPDATE SKIP LOCKED" in claim_source
    assert "CURRENT_TIMESTAMP + (? * INTERVAL '1 minute')" in claim_source
    assert "lease_expires_at::timestamptz" not in claim_source
    assert "INTERVAL '1 minute'))::text" not in claim_source
