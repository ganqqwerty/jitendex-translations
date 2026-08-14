#!/usr/bin/env python3
"""Verify logical parity between a SQLite source and PostgreSQL copy."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from jitendex_ru.database_tools import (
    IDENTITY_TABLES, OPTIONAL_TABLES, TABLES, canonical_json_hash, normalized_table_hash,
    normalized_value, primary_key_columns, sqlite_readonly, table_columns, utc_timestamp,
)


def run_fingerprints(connection, run_ids: list[int]) -> dict[str, str]:
    def rows(sql: str):
        return [[normalized_value(value) for value in row] for row in connection.execute(sql)]

    result = {}
    for run_id in run_ids:
        # Text ordering is locale-dependent in PostgreSQL and bytewise in
        # SQLite.  Fingerprint accepted identities as a multiset so equal
        # rows cannot fail parity merely because the backends sort Japanese
        # unit IDs differently.
        accepted = normalized_table_hash(connection.execute(
            f"SELECT unit_id,target_sha256 FROM translation "
            f"WHERE run_id={run_id} AND accepted=1"
        ))
        payload = {
            "run": rows(
                f"""SELECT id,jitendex_snapshot_id,kaishi_snapshot_id,selection_sha256,
                extractor_version,prompt_sha256,review_prompt_sha256,terminology_sha256,
                limits_json,pipeline_version,state FROM run WHERE id={run_id}"""
            ),
            "accepted": accepted,
            "attempt_usage": rows(
                f"""SELECT a.id,a.outcome,a.input_tokens,a.cached_input_tokens,a.output_tokens,a.total_tokens
                FROM attempt a JOIN batch b ON b.id=a.batch_id WHERE b.run_id={run_id} ORDER BY a.id"""
            ),
            "unresolved": rows(
                f"""SELECT unit_id,attempt_id,validator,severity,code,details_json
                FROM validation_issue WHERE run_id={run_id} AND resolved_at IS NULL ORDER BY id"""
            ),
            "exports": rows(
                f"SELECT output_path,manifest_sha256,zip_sha256,verified FROM export WHERE run_id={run_id} ORDER BY id"
            ),
        }
        result[str(run_id)] = canonical_json_hash(payload)
    return result


def probe_identity_insert(connection, table: str) -> dict[str, object]:
    """Insert through the real identity default and roll back the probe row."""
    sequence = connection.execute(
        "SELECT pg_get_serial_sequence(%s,'id')", (table,),
    ).fetchone()[0]
    maximum = connection.execute(f'SELECT COALESCE(MAX(id),0) FROM "{table}"').fetchone()[0]
    state = connection.execute(f"SELECT last_value,is_called FROM {sequence}").fetchone()
    nullable_for_probe = [
        row[0] for row in connection.execute(
            """SELECT attname FROM pg_attribute
            WHERE attrelid=%s::regclass AND attnum > 0 AND NOT attisdropped
              AND attnotnull AND attname <> 'id' ORDER BY attnum""",
            (table,),
        )
    ]
    connection.execute("SAVEPOINT identity_insert_probe")
    try:
        for column in nullable_for_probe:
            connection.execute(
                f'ALTER TABLE "{table}" ALTER COLUMN "{column}" DROP NOT NULL'
            )
        tested = connection.execute(
            f'INSERT INTO "{table}" DEFAULT VALUES RETURNING id'
        ).fetchone()[0]
    finally:
        connection.execute("ROLLBACK TO SAVEPOINT identity_insert_probe")
        connection.execute("RELEASE SAVEPOINT identity_insert_probe")
    rolled_back = connection.execute(
        f'SELECT COUNT(*)=0 FROM "{table}" WHERE id=%s', (tested,),
    ).fetchone()[0]
    return {
        "last_value": state[0], "is_called": state[1], "maximum_id": maximum,
        "tested_insert_id": tested, "probe_row_rolled_back": rolled_back,
        "safe": tested > maximum and rolled_back,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("sqlite", type=Path)
    parser.add_argument("--postgres-url-env", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--sqlite-zip", type=Path)
    parser.add_argument("--postgresql-zip", type=Path)
    args = parser.parse_args()
    url = os.environ.get(args.postgres_url_env)
    if not url:
        raise SystemExit(f"environment variable is not set: {args.postgres_url_env}")
    import psycopg

    sqlite = sqlite_readonly(args.sqlite)
    report: dict[str, object] = {"tables": {}, "mismatches": []}
    mismatches: list[str] = report["mismatches"]  # type: ignore[assignment]
    with psycopg.connect(url) as postgres:
        postgres.execute("SET timezone = 'UTC'")
        parity_tables = list(TABLES)
        parity_tables.extend(
            table for table in OPTIONAL_TABLES
            if table_columns(sqlite, table, backend="sqlite")
        )
        for table in parity_tables:
            columns = table_columns(sqlite, table, backend="sqlite")
            selected_columns = ",".join(f'"{column}"' for column in columns)
            keys = primary_key_columns(sqlite, table, backend="sqlite")
            if not keys:
                raise RuntimeError(f"parity table has no primary key: {table}")
            timestamp_offsets = {
                index for index, name in enumerate(columns)
                if name.endswith(("_at", "_expires_at"))
            }
            sqlite_count = sqlite.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            postgresql_count = postgres.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]

            def sqlite_rows():
                for row in sqlite.execute(f'SELECT {selected_columns} FROM "{table}"'):
                    values = list(row)
                    for offset in timestamp_offsets:
                        values[offset] = utc_timestamp(values[offset])
                    yield tuple(values)

            postgresql_rows = postgres.cursor(name=f"parity_{table}")
            postgresql_rows.itersize = 10_000
            postgresql_rows.execute(f'SELECT {selected_columns} FROM "{table}"')
            postgresql_hash = normalized_table_hash(postgresql_rows)
            postgresql_rows.close()
            item = {
                "sqlite_count": sqlite_count, "postgresql_count": postgresql_count,
                "sqlite_sha256": normalized_table_hash(sqlite_rows()),
                "postgresql_sha256": postgresql_hash,
            }
            report["tables"][table] = item  # type: ignore[index]
            if item["sqlite_count"] != item["postgresql_count"]:
                mismatches.append(f"{table}:count")
            if item["sqlite_sha256"] != item["postgresql_sha256"]:
                mismatches.append(f"{table}:hash")
        report["postgresql_constraints_unvalidated"] = postgres.execute(
            "SELECT COUNT(*) FROM pg_constraint WHERE NOT convalidated"
        ).fetchone()[0]
        if report["postgresql_constraints_unvalidated"]:
            mismatches.append("postgresql:unvalidated_constraints")
        sequence_safety = {}
        for table in IDENTITY_TABLES:
            sequence_safety[table] = probe_identity_insert(postgres, table)
            if not sequence_safety[table]["safe"]:
                mismatches.append(f"{table}:identity_sequence")
        report["identity_sequences"] = sequence_safety
        report["immutable_history_triggers"] = postgres.execute(
            """SELECT COUNT(*) FROM pg_trigger WHERE NOT tgisinternal AND tgname IN
            ('attempt_cost_report_no_update','attempt_cost_report_no_delete',
             'translation_canonicalization_history_no_update',
             'translation_canonicalization_history_no_delete')"""
        ).fetchone()[0]
        if report["immutable_history_triggers"] != 4:
            mismatches.append("postgresql:immutable_history_triggers")
        report["postgresql_server"] = postgres.info.server_version
        report["postgresql_driver"] = psycopg.__version__
        run_ids = [row[0] for row in sqlite.execute("SELECT id FROM run ORDER BY id")]
        sqlite_runs = run_fingerprints(sqlite, run_ids)
        postgresql_runs = run_fingerprints(postgres, run_ids)
        report["run_fingerprints"] = {
            "sqlite": sqlite_runs, "postgresql": postgresql_runs,
        }
        if sqlite_runs != postgresql_runs:
            mismatches.append("run_fingerprints")
    sqlite.close()
    if args.sqlite_zip or args.postgresql_zip:
        if not args.sqlite_zip or not args.postgresql_zip:
            raise SystemExit("both dictionary ZIP paths are required for build parity")
        from jitendex_ru.database_tools import file_sha256
        report["dictionary_builds"] = {
            "sqlite_sha256": file_sha256(args.sqlite_zip),
            "postgresql_sha256": file_sha256(args.postgresql_zip),
        }
        if report["dictionary_builds"]["sqlite_sha256"] != report["dictionary_builds"]["postgresql_sha256"]:  # type: ignore[index]
            mismatches.append("dictionary_zip:hash")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"event": "parity", "ok": not mismatches, "report": str(args.report)}))
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
