#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import resource
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from jitendex_ru.config import Config
from jitendex_ru.database import Database
from jitendex_ru.prep_metrics import peak_memory_bytes
from jitendex_ru.util import atomic_write, canonical_json


ROOT = Path(__file__).resolve().parents[1]


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Prepare and verify one productive PostgreSQL Luna run")
    result.add_argument("--config", type=Path, default=ROOT / "config.luna.toml")
    result.add_argument("--source-run-id", type=int, required=True)
    result.add_argument("--add-articles", type=int, default=10_000)
    result.add_argument("--report-dir", type=Path, default=ROOT / "reports/run_prep")
    return result


def run_phase(config: Path, phase: str, arguments: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    executable = Path(sys.executable).with_name("translationctl")
    command = [str(executable), "--config", str(config), *arguments]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    started = time.monotonic()
    cpu_started = resource.getrusage(resource.RUSAGE_CHILDREN)
    process = subprocess.Popen(
        command, cwd=ROOT, env=environment, text=True, stdout=subprocess.PIPE,
    )
    try:
        stdout, _ = process.communicate()
    except BaseException:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        raise
    seconds = time.monotonic() - started
    cpu_finished = resource.getrusage(resource.RUSAGE_CHILDREN)
    if process.returncode:
        raise RuntimeError(f"{phase} failed after {seconds:.3f}s")
    payload = json.loads(stdout)
    measurement = {
        "wall_seconds": round(seconds, 6),
        "cpu_seconds": round(
            cpu_finished.ru_utime + cpu_finished.ru_stime - cpu_started.ru_utime - cpu_started.ru_stime, 6,
        ),
        "peak_memory_bytes": payload.get("phase_metrics", {}).get(
            next(reversed(payload.get("phase_metrics", {})), ""), {}
        ).get("peak_memory_bytes"),
        "details": payload.get("phase_metrics", {}),
    }
    print(json.dumps({
        "event": "run_prep_phase", "phase": phase, **measurement, "result": payload,
    }, ensure_ascii=False, sort_keys=True), flush=True)
    return payload, measurement


def verify_source(config: Config, source_run_id: int) -> dict[str, int]:
    database = Database(config)
    connection = database.connect()
    try:
        result = {
            "units": connection.execute(
                "SELECT COUNT(*) FROM translation_unit WHERE run_id=?", (source_run_id,),
            ).fetchone()[0],
            "acceptance_gaps": connection.execute(
                """SELECT COUNT(*) FROM translation_unit source WHERE source.run_id=? AND NOT EXISTS (
                SELECT 1 FROM translation accepted
                WHERE accepted.unit_id=source.id AND accepted.accepted=1)""", (source_run_id,),
            ).fetchone()[0],
            "unfinished_batches": connection.execute(
                """SELECT COUNT(*) FROM batch
                WHERE run_id=? AND state IN ('ready','leased','retryable')""", (source_run_id,),
            ).fetchone()[0],
            "claimed_attempts": connection.execute(
                "SELECT COUNT(*) FROM attempt WHERE outcome='claimed'",
            ).fetchone()[0],
            "unresolved_errors": connection.execute(
                """SELECT COUNT(*) FROM validation_issue
                WHERE run_id=? AND severity='error' AND resolved_at IS NULL""", (source_run_id,),
            ).fetchone()[0],
            "verified_exports": connection.execute(
                "SELECT COUNT(*) FROM export WHERE run_id=? AND verified=1", (source_run_id,),
            ).fetchone()[0],
        }
    finally:
        connection.close()
        database.close()
    if (
        result["units"] < 1 or result["acceptance_gaps"] or result["unfinished_batches"]
        or result["claimed_attempts"] or result["unresolved_errors"] or result["verified_exports"] < 1
    ):
        raise RuntimeError(f"source-run preflight failed: {result}")
    return result


def verify(config: Config, source_run_id: int, target_run_id: int, expected_articles: int) -> dict[str, int]:
    database = Database(config)
    connection = database.connect()
    try:
        result = {
            "articles": connection.execute(
                "SELECT COUNT(*) FROM run_article WHERE run_id=?", (target_run_id,),
            ).fetchone()[0],
            "units": connection.execute(
                "SELECT COUNT(*) FROM translation_unit WHERE run_id=?", (target_run_id,),
            ).fetchone()[0],
            "ready_units": connection.execute(
                "SELECT COUNT(*) FROM translation_unit WHERE run_id=? AND status='ready'", (target_run_id,),
            ).fetchone()[0],
            "ready_batches": connection.execute(
                "SELECT COUNT(*) FROM batch WHERE run_id=? AND state='ready'", (target_run_id,),
            ).fetchone()[0],
            "unbatched_ready_units": connection.execute(
                """SELECT COUNT(*) FROM translation_unit tu
                WHERE tu.run_id=? AND tu.status='ready' AND NOT EXISTS (
                  SELECT 1 FROM batch_item bi JOIN batch b ON b.id=bi.batch_id
                  WHERE bi.unit_id=tu.id AND b.run_id=tu.run_id AND b.kind='translation')""",
                (target_run_id,),
            ).fetchone()[0],
            "claimed_attempts": connection.execute(
                "SELECT COUNT(*) FROM attempt WHERE outcome='claimed'",
            ).fetchone()[0],
            "unresolved_errors": connection.execute(
                """SELECT COUNT(*) FROM validation_issue
                WHERE run_id=? AND severity='error' AND resolved_at IS NULL""", (target_run_id,),
            ).fetchone()[0],
            "source_identity_gaps": connection.execute(
                """SELECT COUNT(*) FROM translation_unit old WHERE old.run_id=? AND NOT EXISTS (
                SELECT 1 FROM translation_unit target
                WHERE target.run_id=? AND target.article_id=old.article_id
                  AND target.json_pointer=old.json_pointer AND target.role=old.role
                  AND target.source_sha256=old.source_sha256)""", (source_run_id, target_run_id),
            ).fetchone()[0],
            "source_acceptance_gaps": connection.execute(
                """SELECT COUNT(*) FROM translation_unit source WHERE source.run_id=? AND NOT EXISTS (
                SELECT 1 FROM translation accepted
                WHERE accepted.unit_id=source.id AND accepted.accepted=1)""", (source_run_id,),
            ).fetchone()[0],
            "source_unfinished_batches": connection.execute(
                """SELECT COUNT(*) FROM batch
                WHERE run_id=? AND state IN ('ready','leased','retryable')""", (source_run_id,),
            ).fetchone()[0],
            "source_verified_exports": connection.execute(
                "SELECT COUNT(*) FROM export WHERE run_id=? AND verified=1", (source_run_id,),
            ).fetchone()[0],
        }
    finally:
        connection.close()
        database.close()
    if result["articles"] != expected_articles:
        raise RuntimeError(f"RUN-PREP article mismatch: {result['articles']}/{expected_articles}")
    blocking = (
        "source_identity_gaps", "unbatched_ready_units", "claimed_attempts", "unresolved_errors",
        "source_acceptance_gaps", "source_unfinished_batches",
    )
    if any(result[key] for key in blocking) or result["source_verified_exports"] < 1:
        raise RuntimeError(f"RUN-PREP integrity gate failed: {result}")
    if result["ready_units"] < 1 or result["ready_batches"] < 1:
        raise RuntimeError(f"RUN-PREP produced no productive Luna work: {result}")
    return result


def main() -> int:
    args = parser().parse_args()
    if args.add_articles < 1:
        raise ValueError("add-articles must be positive")
    config_path = args.config.resolve()
    timings: dict[str, dict[str, Any]] = {}
    config = Config.load(config_path)
    started = time.monotonic()
    cpu_started = time.process_time()
    source = verify_source(config, args.source_run_id)
    timings["source_preflight"] = {
        "wall_seconds": round(time.monotonic() - started, 6),
        "cpu_seconds": round(time.process_time() - cpu_started, 6),
        "peak_memory_bytes": peak_memory_bytes(), "input_rows": source["units"],
    }
    print(json.dumps({
        "event": "run_prep_phase", "phase": "source_preflight",
        **timings["source_preflight"], "result": source,
    }, ensure_ascii=False, sort_keys=True), flush=True)
    selection, timings["select_scope"] = run_phase(config_path, "select_scope", [
        "select-all-article-scope", "--source-run-id", str(args.source_run_id),
        "--add-articles", str(args.add_articles),
    ])
    extraction, timings["extract_units"] = run_phase(config_path, "extract_units", [
        "extract-units", "--source-run-id", str(args.source_run_id),
    ])
    target_run_id = int(extraction["run_id"])
    _, timings["reuse_translations"] = run_phase(config_path, "reuse_translations", [
        "reuse-translations", "--source-run-id", str(args.source_run_id),
        "--target-run-id", str(target_run_id),
    ])
    _, timings["make_batches"] = run_phase(config_path, "make_batches", [
        "make-batches", "--run-id", str(target_run_id),
    ])
    started = time.monotonic()
    cpu_started = time.process_time()
    counts = verify(
        config, args.source_run_id, target_run_id, int(selection["selected_articles"]),
    )
    timings["verify"] = {
        "wall_seconds": round(time.monotonic() - started, 6),
        "cpu_seconds": round(time.process_time() - cpu_started, 6),
        "peak_memory_bytes": peak_memory_bytes(), "input_rows": counts["units"],
    }
    completed = {
        "event": "run_prep_complete", "source_run_id": args.source_run_id,
        "target_run_id": target_run_id, "counts": counts,
        "phases": timings,
        "total_seconds": round(sum(value["wall_seconds"] for value in timings.values()), 6),
        "peak_memory_bytes": max(
            (value.get("peak_memory_bytes") or 0 for value in timings.values()), default=0,
        ),
    }
    report_path = args.report_dir.resolve() / f"run-{target_run_id}-prep.json"
    atomic_write(report_path, canonical_json(completed) + b"\n")
    completed["report_path"] = str(report_path)
    print(json.dumps(completed, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
