import sqlite3
from decimal import Decimal

import pytest

from jitendex_ru.db import SCHEMA_VERSION, connect, initialize, record_attempt_cost, record_attempt_usage


def _insert_attempt(connection, attempt_id="att-audit"):
    connection.execute(
        """INSERT INTO source_snapshot(kind,version,url,sha256,local_path,extractor_version)
        VALUES ('jitendex','v','u','j','j','e'),('kaishi','v','u','k','k','e')"""
    )
    connection.execute(
        """INSERT INTO run(
        jitendex_snapshot_id,kaishi_snapshot_id,selection_sha256,extractor_version,
        prompt_sha256,review_prompt_sha256,terminology_sha256,limits_json)
        VALUES (1,2,'s','e','p','r','t','{}')"""
    )
    connection.execute(
        """INSERT INTO batch(id,run_id,manifest_sha256,serialized_bytes,article_count,unit_count,manifest_path)
        VALUES ('batch-audit',1,'m',1,1,1,'request.json')"""
    )
    connection.execute(
        """INSERT INTO attempt(id,batch_id,worker_id,model,prompt_sha256,request_path)
        VALUES (?,'batch-audit','worker','configured-model','p','request.json')""",
        (attempt_id,),
    )


def test_initialize_migrates_attempt_audit_columns_without_rewriting_history(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE schema_meta(version INTEGER PRIMARY KEY, applied_at TEXT);
            CREATE TABLE attempt(
              id TEXT PRIMARY KEY, batch_id TEXT NOT NULL, worker_id TEXT NOT NULL,
              model TEXT NOT NULL, prompt_sha256 TEXT NOT NULL, lease_token TEXT,
              request_path TEXT NOT NULL, response_path TEXT, outcome TEXT NOT NULL DEFAULT 'claimed',
              error_json TEXT, created_at TEXT, completed_at TEXT
            );
            INSERT INTO attempt(id,batch_id,worker_id,model,prompt_sha256,request_path)
            VALUES ('historical','batch','worker','gpt-5.6-terra','prompt','request');
            """
        )

    initialize(path)

    with connect(path) as connection:
        row = connection.execute("SELECT * FROM attempt WHERE id='historical'").fetchone()
        columns = set(row.keys())
        assert {
            "effective_model_id", "reasoning_effort", "transport", "api_request_id",
            "api_custom_id", "api_job_id", "input_tokens", "cached_input_tokens",
            "output_tokens", "total_tokens", "finish_reason", "status_reason", "latency_ms",
        } <= columns
        assert row["model"] == "gpt-5.6-terra"
        assert row["effective_model_id"] is None
        assert connection.execute("SELECT MAX(version) FROM schema_meta").fetchone()[0] == SCHEMA_VERSION
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_records_raw_usage_and_immutable_cost_snapshot(tmp_path):
    path = tmp_path / "progress.sqlite3"
    initialize(path)
    with connect(path) as connection:
        _insert_attempt(connection)
        record_attempt_usage(
            connection,
            "att-audit",
            effective_model_id="gpt-5.6-luna",
            reasoning_effort="medium",
            transport="batch-api",
            api_request_id="req_1",
            api_custom_id="att-audit",
            api_job_id="batch_1",
            input_tokens=1_000_000,
            cached_input_tokens=200_000,
            output_tokens=100_000,
            total_tokens=1_100_000,
            finish_reason="stop",
            status_reason="completed",
            latency_ms=1234,
        )
        cost = record_attempt_cost(
            connection,
            "att-audit",
            price_snapshot_date="2026-08-09",
            input_price_per_million="0.20",
            cached_input_price_per_million="0.02",
            output_price_per_million="1.20",
            price_multiplier="0.5",
        )

        attempt = connection.execute("SELECT * FROM attempt WHERE id='att-audit'").fetchone()
        report = connection.execute(
            "SELECT * FROM attempt_cost_report WHERE attempt_id='att-audit'"
        ).fetchone()
        events = connection.execute(
            "SELECT event_type FROM audit_event WHERE entity_id='att-audit' ORDER BY id"
        ).fetchall()
        assert attempt["effective_model_id"] == "gpt-5.6-luna"
        assert attempt["reasoning_effort"] == "medium"
        assert attempt["transport"] == "batch-api"
        assert attempt["api_request_id"] == "req_1"
        assert attempt["api_custom_id"] == "att-audit"
        assert attempt["api_job_id"] == "batch_1"
        assert tuple(attempt[name] for name in (
            "input_tokens", "cached_input_tokens", "output_tokens", "total_tokens"
        )) == (1_000_000, 200_000, 100_000, 1_100_000)
        assert cost == Decimal("0.1420")
        assert Decimal(report["computed_cost"]) == cost
        assert report["price_snapshot_date"] == "2026-08-09"
        assert [row[0] for row in events] == ["record_usage", "record_cost"]

        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE attempt_cost_report SET computed_cost='0' WHERE attempt_id='att-audit'"
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute("DELETE FROM attempt_cost_report WHERE attempt_id='att-audit'")


def test_usage_rejects_inconsistent_token_totals(tmp_path):
    path = tmp_path / "progress.sqlite3"
    initialize(path)
    with connect(path) as connection:
        _insert_attempt(connection)
        with pytest.raises(ValueError, match="total tokens"):
            record_attempt_usage(
                connection,
                "att-audit",
                effective_model_id="gpt-5.6-luna",
                reasoning_effort="medium",
                transport="responses-sync",
                input_tokens=10,
                cached_input_tokens=0,
                output_tokens=5,
                total_tokens=14,
            )
