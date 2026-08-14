#!/usr/bin/env python3
"""Write a payload-free PostgreSQL monitoring snapshot for a benchmark stage."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--postgres-url-env", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    url = os.environ.get(args.postgres_url_env)
    if not url:
        raise SystemExit(f"environment variable is not set: {args.postgres_url_env}")
    import psycopg

    with psycopg.connect(url) as connection:
        database = connection.info.dbname
        activity = connection.execute(
            """SELECT state,wait_event_type,wait_event,COUNT(*)
            FROM pg_stat_activity WHERE datname=current_database()
            GROUP BY state,wait_event_type,wait_event ORDER BY state,wait_event_type,wait_event"""
        ).fetchall()
        locks = connection.execute(
            """SELECT mode,granted,COUNT(*) FROM pg_locks l
            JOIN pg_database d ON d.oid=l.database WHERE d.datname=current_database()
            GROUP BY mode,granted ORDER BY mode,granted"""
        ).fetchall()
        statistics = connection.execute(
            """SELECT xact_commit,xact_rollback,blks_read,blks_hit,temp_files,temp_bytes,
            deadlocks,checksum_failures,session_time,active_time,idle_in_transaction_time
            FROM pg_stat_database WHERE datname=current_database()"""
        ).fetchone()
        extension = connection.execute(
            "SELECT 1 FROM pg_extension WHERE extname='pg_stat_statements'"
        ).fetchone()
        statements = None
        if extension:
            statements = connection.execute(
                """SELECT COUNT(*),COALESCE(SUM(calls),0),COALESCE(SUM(total_exec_time),0),
                COALESCE(SUM(rows),0),COALESCE(SUM(shared_blks_read),0),COALESCE(SUM(shared_blks_hit),0)
                FROM pg_stat_statements WHERE dbid=(SELECT oid FROM pg_database WHERE datname=current_database())"""
            ).fetchone()
        result = {
            "schema_version": 1,
            "captured_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "database_name": database,
            "server_version": connection.info.server_version,
            "pg_stat_activity": [list(row) for row in activity],
            "pg_locks": [list(row) for row in locks],
            "pg_stat_database": [float(value) if isinstance(value, Decimal) else value for value in statistics],
            "pg_stat_statements_enabled": bool(extension),
            "pg_stat_statements_totals": [
                float(value) if isinstance(value, Decimal) else value for value in statements
            ] if statements else None,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"event": "postgresql_metrics_snapshot", "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
