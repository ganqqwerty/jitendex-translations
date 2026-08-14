#!/usr/bin/env python3
"""Copy one stopped SQLite database to an empty PostgreSQL database."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path

from jitendex_ru.database_tools import (
    IDENTITY_TABLES, OPTIONAL_TABLES, TABLES, file_sha256, require_migration_safe,
    sqlite_readonly, table_columns, utc_timestamp,
)

ROOT = Path(__file__).resolve().parents[1]
TIMESTAMP_SUFFIXES = ("_at", "_expires_at")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("source", type=Path)
    result.add_argument("--postgres-url-env", required=True)
    result.add_argument("--report", type=Path, required=True)
    result.add_argument("--disposable-test-source", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    url = os.environ.get(args.postgres_url_env)
    if not url:
        raise SystemExit(f"environment variable is not set: {args.postgres_url_env}")
    try:
        import psycopg
    except ImportError as error:
        raise SystemExit("install the pinned PostgreSQL dependency first") from error

    source = sqlite_readonly(args.source)
    safety = require_migration_safe(source, disposable_test=args.disposable_test_source)
    sqlite_version = source.execute("SELECT sqlite_version()").fetchone()[0]
    schema_version = source.execute("SELECT MAX(version) FROM schema_meta").fetchone()[0]
    verified_export = source.execute(
        "SELECT zip_sha256 FROM export WHERE verified=1 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    counts: dict[str, int] = {}
    try:
        with psycopg.connect(url, autocommit=True) as target:
            existing = target.execute(
                "SELECT COUNT(*) FROM pg_tables WHERE schemaname='public'"
            ).fetchone()[0]
            if existing:
                raise RuntimeError("PostgreSQL public schema is not empty; refusing to overwrite it")
            target.execute("SET timezone = 'UTC'")
            target.execute((ROOT / "migrations/postgresql/0008_schema.sql").read_text())
            for table in TABLES:
                columns = table_columns(source, table, backend="sqlite")
                if not columns:
                    raise RuntimeError(f"SQLite source is missing table: {table}")
                timestamp_offsets = {
                    index for index, name in enumerate(columns)
                    if name.endswith(TIMESTAMP_SUFFIXES)
                }
                rows = source.execute(f'SELECT * FROM "{table}"')
                with target.cursor().copy(
                    f'COPY "{table}" ({",".join(columns)}) FROM STDIN'
                ) as copy:
                    count = 0
                    for row in rows:
                        values = list(row)
                        for offset in timestamp_offsets:
                            values[offset] = utc_timestamp(values[offset])
                        copy.write_row(values)
                        count += 1
                counts[table] = count
            target.execute((ROOT / "migrations/postgresql/0008_post_load.sql").read_text())
            for migration in sorted((ROOT / "migrations/postgresql").glob("[0-9][0-9][0-9][0-9]_*.sql")):
                version = int(migration.name.split("_", 1)[0])
                if version <= 8 or migration.name.endswith("_post_load.sql"):
                    continue
                target.execute(migration.read_text(encoding="utf-8"))
                target.execute(
                    "INSERT INTO schema_meta(version) VALUES (%s) ON CONFLICT(version) DO NOTHING",
                    (version,),
                )
            for table in OPTIONAL_TABLES:
                columns = table_columns(source, table, backend="sqlite")
                if not columns:
                    continue
                rows = source.execute(f'SELECT * FROM "{table}"')
                with target.cursor().copy(
                    f'COPY "{table}" ({",".join(columns)}) FROM STDIN'
                ) as copy:
                    count = 0
                    for row in rows:
                        values = list(row)
                        for offset, name in enumerate(columns):
                            if name.endswith(TIMESTAMP_SUFFIXES):
                                values[offset] = utc_timestamp(values[offset])
                        copy.write_row(values)
                        count += 1
                counts[table] = count
            for table in IDENTITY_TABLES:
                sequence = target.execute(
                    "SELECT pg_get_serial_sequence(%s, 'id')", (table,)
                ).fetchone()[0]
                if sequence:
                    target.execute(
                        f"SELECT setval(%s, COALESCE(MAX(id), 1), COUNT(*) > 0) FROM {table}",
                        (sequence,),
                    )
            postgresql_server = target.info.server_version
    finally:
        source.close()
    report = {
        "schema_version": schema_version, "source_path": str(args.source.resolve()),
        "source_sha256": file_sha256(args.source), "source_safety": safety,
        "table_counts": counts, "postgresql_driver": psycopg.__version__,
        "postgresql_server": postgresql_server, "sqlite_version": sqlite_version,
        "verified_export_sha256": verified_export[0] if verified_export else None,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"event": "migration_complete", "report": str(args.report)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
