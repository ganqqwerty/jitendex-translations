#!/usr/bin/env python3
"""Run one bounded Luna benchmark against a fresh disposable stage database."""

from __future__ import annotations

import argparse
import atexit
import fastjsonschema
import hashlib
import json
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jitendex_ru.config import Config
from jitendex_ru.database import DatabaseMetrics, PostgresConnection
from jitendex_ru.run_integrity import workload_progress


ROOT = Path(__file__).resolve().parents[1]
SAFE_DATABASE = re.compile(r"^jitendex_lcp_[a-z0-9_]+$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def runner_revision_sha256() -> str:
    paths = [
        ROOT / "config.luna.toml", ROOT / "pyproject.toml", ROOT / "uv.lock",
        ROOT / "scripts/run_codex_batches.py", ROOT / "scripts/run_luna_benchmark.py",
        ROOT / "prompts/translate_luna_v4.txt", ROOT / "terminology/ru-v1.json",
    ]
    paths.extend(sorted((ROOT / "src/jitendex_ru").glob("*.py")))
    paths.extend(sorted((ROOT / "migrations").rglob("*")))
    digest = hashlib.sha256()
    for path in sorted((path for path in paths if path.is_file()), key=lambda item: str(item.relative_to(ROOT))):
        relative = str(path.relative_to(ROOT)).encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        data = path.read_bytes()
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def postgres_url_with_database(url: str, database: str) -> str:
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    values = conninfo_to_dict(url)
    values["dbname"] = database
    return make_conninfo(**values)


def clone_postgresql(admin_url: str, template: str, stage_database: str) -> str:
    if not SAFE_DATABASE.fullmatch(template) or not SAFE_DATABASE.fullmatch(stage_database):
        raise RuntimeError("PostgreSQL template and stage names must use the jitendex_lcp_ prefix")
    if template == stage_database:
        raise RuntimeError("PostgreSQL stage database must differ from its template")
    import psycopg
    control_url = postgres_url_with_database(admin_url, "postgres")
    with psycopg.connect(control_url, autocommit=True) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname=%s", (template,),
        ).fetchone()
        if not exists:
            raise RuntimeError(f"PostgreSQL benchmark template does not exist: {template}")
        connection.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s",
            (stage_database,),
        )
        connection.execute(f'DROP DATABASE IF EXISTS "{stage_database}"')
        connection.execute(f'CREATE DATABASE "{stage_database}" TEMPLATE "{template}"')
    return postgres_url_with_database(admin_url, stage_database)


def drop_postgresql(admin_url: str, stage_database: str) -> None:
    if not SAFE_DATABASE.fullmatch(stage_database):
        raise RuntimeError("refusing to drop a database without the jitendex_lcp_ prefix")
    import psycopg
    with psycopg.connect(postgres_url_with_database(admin_url, "postgres"), autocommit=True) as connection:
        connection.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s",
            (stage_database,),
        )
        connection.execute(f'DROP DATABASE IF EXISTS "{stage_database}"')


def connect_stage(backend: str, location: str):
    if backend == "sqlite":
        connection = sqlite3.connect(location)
        connection.row_factory = sqlite3.Row
        return connection
    import psycopg
    raw = psycopg.connect(location)
    return PostgresConnection(raw, lambda connection: connection.close(), DatabaseMetrics())


def scalar(connection: Any, sql: str, parameters: tuple[Any, ...]) -> int:
    return int(connection.execute(sql, parameters).fetchone()[0] or 0)


def marker(connection: Any, stage_id: str, corpus_sha256: str, run_id: int) -> None:
    row = connection.execute(
        "SELECT corpus_sha256,run_id FROM benchmark_marker WHERE stage_id=?",
        (stage_id,),
    ).fetchone()
    if row is None or row[0] != corpus_sha256 or int(row[1]) != run_id:
        raise RuntimeError("benchmark marker does not match the stage definition")


def rename_marker(connection: Any, old_stage_id: str, trial_id: str) -> None:
    updated = connection.execute(
        "UPDATE benchmark_marker SET stage_id=? WHERE stage_id=?",
        (trial_id, old_stage_id),
    ).rowcount
    if updated != 1:
        raise RuntimeError("could not bind the disposable database to the trial ID")
    connection.commit()


def workload_counts(connection: Any, run_id: int) -> dict[str, int]:
    return workload_progress(connection, run_id)


def postflight(connection: Any, run_id: int) -> dict[str, int]:
    checks = {
        "claimed_attempts": scalar(
            connection,
            """SELECT COUNT(*) FROM attempt a JOIN batch b ON b.id=a.batch_id
            WHERE b.run_id=? AND a.outcome='claimed'""", (run_id,),
        ),
        "leased_batches": scalar(
            connection, "SELECT COUNT(*) FROM batch WHERE run_id=? AND state='leased'", (run_id,),
        ),
        "missing_units": scalar(
            connection,
            """SELECT COUNT(*) FROM translation_unit tu WHERE tu.run_id=? AND NOT EXISTS (
            SELECT 1 FROM batch_item bi WHERE bi.unit_id=tu.id AND EXISTS (
            SELECT 1 FROM batch b WHERE b.id=bi.batch_id AND b.run_id=tu.run_id))""",
            (run_id,),
        ),
        "duplicate_deterministic_translations": scalar(
            connection,
            """SELECT COUNT(*) FROM (SELECT unit_id,COUNT(*) count FROM translation
            WHERE run_id=? GROUP BY unit_id HAVING COUNT(*) > 1) duplicates""", (run_id,),
        ),
        "blocking_errors": scalar(
            connection,
            """SELECT COUNT(*) FROM validation_issue WHERE run_id=?
            AND severity IN ('blocking','error') AND resolved_at IS NULL""", (run_id,),
        ),
    }
    expected = {}
    for row in connection.execute(
        "SELECT id,source_sha256 FROM translation_unit WHERE run_id=?", (run_id,),
    ):
        expected[row[0]] = row[1]
    source_hash_mismatches = 0
    for row in connection.execute(
        "SELECT manifest_path FROM batch WHERE run_id=?", (run_id,),
    ):
        payload = json.loads(Path(row[0]).read_text(encoding="utf-8"))
        for article in payload.get("articles", []):
            for unit in article.get("units", []):
                if expected.get(unit.get("unit_id")) != unit.get("source_sha256"):
                    source_hash_mismatches += 1
    checks["source_hash_mismatches"] = source_hash_mismatches
    if any(checks.values()):
        raise RuntimeError(f"benchmark postflight failed: {checks}")
    return checks


def postgres_snapshot(url: str) -> dict[str, Any]:
    import psycopg
    with psycopg.connect(url) as connection:
        activity = connection.execute(
            """SELECT state,wait_event_type,wait_event,COUNT(*) FROM pg_stat_activity
            WHERE datname=current_database() GROUP BY state,wait_event_type,wait_event
            ORDER BY state,wait_event_type,wait_event"""
        ).fetchall()
        locks = connection.execute(
            """SELECT mode,granted,COUNT(*) FROM pg_locks l JOIN pg_database d ON d.oid=l.database
            WHERE d.datname=current_database() GROUP BY mode,granted ORDER BY mode,granted"""
        ).fetchall()
        database = connection.execute(
            """SELECT xact_commit,xact_rollback,blks_read,blks_hit,temp_files,temp_bytes,
            deadlocks,session_time,active_time,idle_in_transaction_time
            FROM pg_stat_database WHERE datname=current_database()"""
        ).fetchone()
        statements = connection.execute(
            """SELECT COUNT(*),COALESCE(SUM(calls),0),COALESCE(SUM(total_exec_time),0),
            COALESCE(SUM(rows),0),COALESCE(SUM(shared_blks_read),0),COALESCE(SUM(shared_blks_hit),0)
            FROM pg_stat_statements WHERE dbid=(SELECT oid FROM pg_database WHERE datname=current_database())"""
        ).fetchone()
        return {
            "captured_at": utc_now(), "activity": [list(row) for row in activity],
            "locks": [list(row) for row in locks], "database": [float(value) for value in database],
            "statements": [float(value) for value in statements],
        }


def machine_snapshot() -> dict[str, Any]:
    def command(*parts: str) -> str:
        result = subprocess.run(parts, capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else "unavailable"

    return {
        "captured_at": utc_now(), "platform": platform.platform(),
        "vm_stat": command("vm_stat"), "swap_usage": command("sysctl", "vm.swapusage"),
        "power_state": command("pmset", "-g", "batt"),
    }


def stage_identity(connection: Any, backend: str, run_id: int) -> dict[str, Any]:
    run = connection.execute(
        "SELECT prompt_sha256,limits_json,pipeline_version FROM run WHERE id=?", (run_id,),
    ).fetchone()
    if run is None:
        raise RuntimeError(f"benchmark run does not exist: {run_id}")
    schema_version = int(connection.execute("SELECT MAX(version) FROM schema_meta").fetchone()[0])
    if backend == "sqlite":
        driver_version = f"python-stdlib-{platform.python_version()}"
        server_version = sqlite3.sqlite_version
    else:
        import psycopg
        driver_version = psycopg.__version__
        server_version = connection.execute("SHOW server_version").fetchone()[0]
    return {
        "database_driver_version": driver_version,
        "database_server_version": server_version,
        "database_schema_version": schema_version,
        "prompt_sha256": run[0],
        "limits_sha256": hashlib.sha256(str(run[1]).encode("utf-8")).hexdigest(),
        "pipeline_version": run[2],
    }


def production_runner_active() -> bool:
    result = subprocess.run(
        ["pgrep", "-f", "scripts/run_codex_batches.py"], capture_output=True, text=True,
    )
    return any(line.strip() and int(line) != os.getpid() for line in result.stdout.splitlines())


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * fraction))]


def validated_stage(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads(
        (ROOT / "reports/luna_performance/stage.schema.json").read_text(encoding="utf-8")
    )
    fastjsonschema.compile(schema)(payload)
    return payload


def measured_window_seconds(phases: list[dict[str, Any]]) -> float:
    measurements = [event for event in phases if event.get("phase") == "measurement"]
    shutdowns = [event for event in phases if event.get("phase") == "shutdown"]
    if len(measurements) != 1 or len(shutdowns) != 1:
        raise RuntimeError("benchmark did not record exactly one measurement and shutdown phase")
    return float(shutdowns[0]["elapsed_seconds"]) - float(measurements[0]["elapsed_seconds"])


def measurement_summary(
    events: list[dict[str, Any]], phases: list[dict[str, Any]], final: dict[str, Any],
) -> dict[str, Any]:
    measurement = next(event for event in phases if event.get("phase") == "measurement")
    shutdown = next(event for event in phases if event.get("phase") == "shutdown")
    start = float(measurement["elapsed_seconds"])
    end = float(shutdown["elapsed_seconds"])
    completed = [
        event for event in events
        if event.get("event") == "completed"
        and start <= float(event.get("elapsed_seconds", -1)) <= end
    ]
    submitted = [
        event for event in events
        if event.get("event") == "submitted"
        and start <= float(event.get("elapsed_seconds", -1)) <= end
    ]
    progress = [
        event for event in events
        if event.get("event") == "progress"
        and start <= float(event.get("elapsed_seconds", -1)) <= end
    ]
    before_metrics = measurement.get("metrics")
    after_metrics = shutdown.get("metrics")
    if not isinstance(before_metrics, dict) or not isinstance(after_metrics, dict):
        raise RuntimeError("measurement and shutdown phases must contain metric snapshots")

    def delta(key: str) -> float:
        value = float(after_metrics.get(key, 0)) - float(before_metrics.get(key, 0))
        if value < -1e-6:
            raise RuntimeError(f"cumulative benchmark metric went backwards: {key}")
        return max(value, 0.0)

    latencies = [float(event["latency_ms"]) for event in completed if event.get("latency_ms") is not None]
    worker_memory = [int(event.get("worker_peak_memory_bytes", 0)) for event in completed]
    connections = [int(event.get("connections_in_use", 0)) for event in progress]
    workers = [int(event.get("workers_active", 0)) for event in progress]
    return {
        **final,
        "submitted": len(submitted), "completed": len(completed),
        "failed_attempts": sum(not bool(event.get("ok")) for event in completed),
        "input_tokens": sum(int(event.get("input_tokens", 0)) for event in completed),
        "cached_input_tokens": sum(int(event.get("cached_input_tokens", 0)) for event in completed),
        "output_tokens": sum(int(event.get("output_tokens", 0)) for event in completed),
        "rate_limits": sum(bool(event.get("rate_limit")) for event in completed),
        "timeouts": sum(bool(event.get("timeout")) for event in completed),
        "transport_failures": sum(bool(event.get("transport_failure")) for event in completed),
        "validation_rejections": sum(bool(event.get("validation_rejection")) for event in completed),
        "retries": sum(bool(event.get("retry")) for event in completed),
        "splits": sum(bool(event.get("split")) for event in completed),
        "latency_p50_ms": percentile(latencies, 0.50),
        "latency_p95_ms": percentile(latencies, 0.95),
        "latency_p99_ms": percentile(latencies, 0.99),
        "worker_peak_memory_bytes": max(worker_memory, default=0),
        "progress_query_seconds": delta("progress_query_seconds"),
        "claim_milliseconds": delta("claim_milliseconds"),
        "ingestion_milliseconds": delta("ingestion_milliseconds"),
        "pool_wait_milliseconds": delta("pool_wait_milliseconds"),
        "database_checkouts": round(delta("database_checkouts")),
        "database_retries": round(delta("database_retries")),
        "transaction_milliseconds": delta("transaction_milliseconds"),
        "connections_in_use": max(connections, default=0),
        "workers_active": max(workers, default=0),
    }


def monitoring_summary(samples: list[dict[str, Any]]) -> dict[str, float | int]:
    ungranted = []
    lock_waiters = []
    for sample in samples:
        ungranted.append(sum(int(row[2]) for row in sample["locks"] if not bool(row[1])))
        lock_waiters.append(sum(
            int(row[3]) for row in sample["activity"] if row[1] == "Lock"
        ))
    active_time_delta = 0.0
    statement_exec_delta = 0.0
    if len(samples) >= 2:
        active_time_delta = max(float(samples[-1]["database"][8]) - float(samples[0]["database"][8]), 0.0)
        statement_exec_delta = max(float(samples[-1]["statements"][2]) - float(samples[0]["statements"][2]), 0.0)
    return {
        "sample_count": len(samples),
        "lock_wait_sample_count": sum(value > 0 for value in ungranted),
        "max_ungranted_locks": max(ungranted, default=0),
        "max_lock_waiting_sessions": max(lock_waiters, default=0),
        "postgresql_active_time_delta_milliseconds": active_time_delta,
        "postgresql_statement_exec_delta_milliseconds": statement_exec_delta,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", type=Path)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--trial-id", required=True)
    parser.add_argument("--database-backend", choices=("sqlite", "postgresql"), required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--concurrency", type=int, required=True)
    parser.add_argument("--startup-seconds", type=float, required=True)
    parser.add_argument("--measurement-seconds", type=float, default=1200.0)
    parser.add_argument("--measure-from", choices=("measurement", "first-launch"), default="measurement")
    parser.add_argument("--postgres-admin-url-env", default="JITENDEX_POSTGRES_URL")
    parser.add_argument("--postgres-template-database")
    parser.add_argument("--postgres-stage-database")
    parser.add_argument("--keep-stage-database", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.concurrency < 1 or args.startup_seconds < 0 or args.measurement_seconds <= 0:
        parser.error("invalid concurrency or timing setting")
    if production_runner_active():
        parser.error("another Luna runner is active; benchmark preflight refused")
    trial_root = (ROOT / "work/luna_performance/trials").resolve()
    if args.work_dir.resolve() == trial_root or not args.work_dir.resolve().is_relative_to(trial_root):
        parser.error("benchmark work directory must be a child of work/luna_performance/trials")
    result_root = (ROOT / "reports/luna_performance/stages").resolve()
    if args.result.resolve() == result_root or not args.result.resolve().is_relative_to(result_root):
        parser.error("benchmark result must be stored under reports/luna_performance/stages")
    if args.work_dir.exists():
        parser.error("benchmark work directory must not already exist")
    stage = validated_stage(args.stage)
    if stage.get("template") is not True or stage.get("run_id") == stage.get("source_run_id"):
        parser.error("stage definition is not a disposable benchmark template")
    args.work_dir.mkdir(parents=True)
    args.result.parent.mkdir(parents=True, exist_ok=True)

    admin_url = None
    stage_database = None
    database_cleanup = None
    if args.database_backend == "sqlite":
        template_path = Path(str(stage["database_path"])).resolve()
        production_path = Config.load(args.config).db_path.resolve()
        if template_path == production_path:
            parser.error("production SQLite database cannot be used as a benchmark template")
        if not template_path.is_relative_to((ROOT / "work/luna_performance").resolve()):
            parser.error("SQLite benchmark template must stay under work/luna_performance")
        stage_location = str(args.work_dir / "stage.sqlite3")
        shutil.copy2(template_path, stage_location)
    else:
        if not args.postgres_template_database or not args.postgres_stage_database:
            parser.error("PostgreSQL stages require template and stage database names")
        admin_url = os.environ.get(args.postgres_admin_url_env)
        if not admin_url:
            parser.error(f"missing PostgreSQL admin URL environment: {args.postgres_admin_url_env}")
        production_database = __import__("psycopg").conninfo.conninfo_to_dict(admin_url).get("dbname")
        if args.postgres_stage_database == production_database:
            parser.error("benchmark PostgreSQL database must differ from production")
        stage_database = args.postgres_stage_database
        stage_location = clone_postgresql(
            admin_url, args.postgres_template_database, stage_database,
        )
        if not args.keep_stage_database:
            database_cleanup = lambda: drop_postgresql(admin_url, stage_database)  # type: ignore[arg-type]
            atexit.register(database_cleanup)

    started_at = utc_now()
    connection = connect_stage(args.database_backend, stage_location)
    try:
        rename_marker(connection, str(stage["stage_id"]), args.trial_id)
        marker(connection, args.trial_id, str(stage["corpus_sha256"]), int(stage["run_id"]))
        identity = stage_identity(connection, args.database_backend, int(stage["run_id"]))
        before = workload_counts(connection, int(stage["run_id"]))
    finally:
        connection.close()

    events: list[dict[str, Any]] = []
    measurement_before = dict(before)
    log_path = args.work_dir / "runner.jsonl"
    monitor: list[dict[str, Any]] = []
    machine_monitor: list[dict[str, Any]] = []
    monitor_errors: list[str] = []
    monitor_stop = threading.Event()

    def monitor_stage() -> None:
        while not monitor_stop.is_set():
            try:
                machine_monitor.append(machine_snapshot())
                if args.database_backend == "postgresql":
                    monitor.append(postgres_snapshot(stage_location))
            except Exception as error:
                monitor_errors.append(f"{type(error).__name__}: {error}")
                monitor_stop.set()
                return
            monitor_stop.wait(60)

    thread = threading.Thread(target=monitor_stage, daemon=True)
    thread.start()

    runner_exit = 0
    if not args.dry_run:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT / "src")
        environment["JITENDEX_BENCHMARK_DATABASE_BACKEND"] = args.database_backend
        environment["JITENDEX_BENCHMARK_WORK_DIR"] = str(args.work_dir.resolve())
        environment["JITENDEX_BENCHMARK_DIST_DIR"] = str((args.work_dir / "dist").resolve())
        if args.database_backend == "sqlite":
            environment["JITENDEX_BENCHMARK_DATABASE"] = stage_location
        else:
            environment["JITENDEX_POSTGRES_URL"] = stage_location
        command = [
            str(ROOT / ".venv/bin/python"), str(ROOT / "scripts/run_codex_batches.py"),
            "--config", str(args.config.resolve()), "--run-id", str(stage["run_id"]),
            "--kind", "translation", "--concurrency", str(args.concurrency),
            "--worker-prefix", args.trial_id, "--progress-interval", "60",
            "--startup-seconds", str(args.startup_seconds),
            "--stop-after-seconds", str(args.measurement_seconds),
            "--measure-from", args.measure_from,
        ]
        process = subprocess.Popen(
            command, cwd=ROOT, env=environment, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        assert process.stdout is not None
        with log_path.open("w", encoding="utf-8") as log:
            for line in process.stdout:
                log.write(line)
                log.flush()
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                events.append(event)
                if event.get("event") == "phase" and event.get("phase") == "measurement":
                    phase_connection = connect_stage(args.database_backend, stage_location)
                    try:
                        measurement_before = workload_counts(
                            phase_connection, int(stage["run_id"]),
                        )
                    finally:
                        phase_connection.close()
        runner_exit = process.wait()
        if runner_exit not in {0, 130}:
            raise RuntimeError(f"benchmark runner failed with exit code {runner_exit}")
    else:
        log_path.write_text("", encoding="utf-8")

    monitor_stop.set()
    thread.join(timeout=30)
    machine_monitor.append(machine_snapshot())
    if args.database_backend == "postgresql":
        monitor.append(postgres_snapshot(stage_location))
    if monitor_errors:
        raise RuntimeError(f"benchmark monitoring failed: {monitor_errors[0]}")

    connection = connect_stage(args.database_backend, stage_location)
    try:
        after = workload_counts(connection, int(stage["run_id"]))
        checks = postflight(connection, int(stage["run_id"]))
    finally:
        connection.close()

    summaries = [event for event in events if event.get("event") == "summary"]
    summary_defaults = {
        "submitted": 0, "completed": 0, "failed_attempts": 0,
        "input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0,
        "total_tokens": 0, "rate_limits": 0, "timeouts": 0,
        "transport_failures": 0, "validation_rejections": 0,
        "retries": 0, "splits": 0, "latency_p50_ms": None,
        "latency_p95_ms": None, "latency_p99_ms": None,
        "worker_peak_memory_bytes": 0, "pool_wait_milliseconds": 0.0,
        "database_checkouts": 0, "database_retries": 0,
        "transaction_milliseconds": 0.0, "connections_in_use": 0,
        "progress_query_seconds": 0.0, "claim_milliseconds": 0.0,
        "ingestion_milliseconds": 0.0, "database_backend": args.database_backend,
        "workers_active": 0, "headwords_done": after["headwords"],
        "headwords_remaining": int(stage["headword_count"]) - after["headwords"],
        "headwords_per_minute": 0.0,
    }
    summary = {**summary_defaults, **(summaries[-1] if summaries else {})}
    phases = [event for event in events if event.get("event") == "phase"]
    if not args.dry_run:
        measured_seconds = measured_window_seconds(phases)
        if measured_seconds + 1 < args.measurement_seconds:
            raise RuntimeError(
                f"benchmark measured window was incomplete: {measured_seconds:.3f} seconds"
            )
        summary = measurement_summary(events, phases, summary)
    else:
        measured_seconds = 0.0
    launches = [event for event in events if event.get("event") == "launched"]
    deltas = {key: after[key] - measurement_before[key] for key in measurement_before}
    measured_minutes = measured_seconds / 60 if measured_seconds else args.measurement_seconds / 60
    rates = {f"{key}_per_minute": value / measured_minutes for key, value in deltas.items()}
    summary["total_tokens"] = int(summary["input_tokens"]) + int(summary["output_tokens"])
    summary["database_duty_cycle"] = (
        float(summary["transaction_milliseconds"]) / (measured_seconds * 1000)
        if measured_seconds else 0.0
    )
    completed_requests = int(summary["completed"])
    denominator = max(completed_requests, 1)
    error_rates = {
        "failure_rate": int(summary["failed_attempts"]) / denominator,
        "rate_limit_rate": int(summary["rate_limits"]) / denominator,
        "timeout_rate": int(summary["timeouts"]) / denominator,
        "transport_failure_rate": int(summary["transport_failures"]) / denominator,
        "validation_rejection_rate": int(summary["validation_rejections"]) / denominator,
    }
    launch_delays = [
        float(event["actual_launch_seconds"]) - float(event["requested_launch_seconds"])
        for event in launches
    ]
    result = {
        "schema_version": 1,
        "configuration": {
            "stage_id": args.trial_id, "database_backend": args.database_backend,
            "database_workers": 1, "pool_max": Config.load(args.config).db_pool_max,
            "model": Config.load(args.config).model("translation")["id"],
            "reasoning_effort": Config.load(args.config).model("translation")["reasoning_effort"],
            "concurrency": args.concurrency, "startup_seconds": args.startup_seconds,
            "measurement_seconds": args.measurement_seconds, "measure_from": args.measure_from,
            "dry_run": args.dry_run, **identity,
        },
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "runner_revision_sha256": runner_revision_sha256(),
        "worktree_diff_sha256": hashlib.sha256(
            subprocess.check_output(["git", "diff", "--binary"], cwd=ROOT)
        ).hexdigest(),
        "corpus_sha256": stage["corpus_sha256"],
        "started_at": started_at, "ended_at": utc_now(),
        "phases": phases,
        "counters": {
            **summary, "runner_exit": runner_exit, "before": before,
            "measurement_before": measurement_before,
            "after": after, "deltas": deltas, "rates": rates,
            "error_rates": error_rates,
            "measured_seconds": measured_seconds,
            "launch_delay_p50_seconds": percentile(launch_delays, 0.50),
            "launch_delay_p95_seconds": percentile(launch_delays, 0.95),
            "launch_delay_p99_seconds": percentile(launch_delays, 0.99),
        },
        "postgresql_monitoring": monitor if args.database_backend == "postgresql" else None,
        "monitoring_summary": monitoring_summary(monitor),
        "machine_monitoring": machine_monitor,
        "runner_log_sha256": file_sha256(log_path),
        "postflight": checks,
    }
    args.result.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.database_backend == "postgresql" and not args.keep_stage_database:
        assert admin_url is not None and stage_database is not None
        drop_postgresql(admin_url, stage_database)
        assert database_cleanup is not None
        atexit.unregister(database_cleanup)
    print(json.dumps({
        "event": "benchmark_complete", "result": str(args.result),
        "headwords_per_minute": rates["headwords_per_minute"], "postflight": checks,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"event": "benchmark_failed", "error": str(error)}), file=sys.stderr)
        raise
