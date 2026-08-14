#!/usr/bin/env python3
"""Benchmark RUN-PREP locally on bounded synthetic data without Luna requests."""

from __future__ import annotations

import argparse
import json
import os
import resource
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from jitendex_ru.batch import _manifest, _pack_envelopes, make_batches
from jitendex_ru.config import Config
from jitendex_ru.database import Database
from jitendex_ru.extract_units import extract_selected
from jitendex_ru.util import atomic_write, canonical_json, sha256_bytes


ROOT = Path(__file__).resolve().parents[1]


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--database-url-env", default="JITENDEX_TEST_POSTGRES_URL")
    result.add_argument("--articles", type=int, default=10_000)
    result.add_argument("--output", type=Path, default=ROOT / "reports/run_prep/synthetic-10000.json")
    return result


def legacy_pack(envelopes: list[dict[str, Any]], terminology: dict[str, str], limits: dict[str, int]):
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []

    def measured(candidate):
        return (
            len(_manifest("b-" + "0" * 24, candidate, terminology)[1]),
            sum(len(article["units"]) for article in candidate),
        )

    for envelope in envelopes:
        article_bytes, article_units = measured([envelope])
        if article_bytes > limits["hard_max_article_bytes"] or article_units > limits["hard_max_article_units"]:
            raise ValueError(f"article {envelope['article_id']} exceeds a hard article limit")
        force_singleton = (
            article_bytes > limits["singleton_threshold_bytes"]
            or article_bytes > limits["soft_max_bytes"]
            or article_units > limits["soft_max_units"]
        )
        candidate = current + [envelope]
        byte_count, unit_count = measured(candidate)
        if current and (
            force_singleton or len(candidate) > limits["soft_max_articles"]
            or byte_count > limits["soft_max_bytes"] or unit_count > limits["soft_max_units"]
        ):
            batches.append(current)
            current = []
        if force_singleton:
            batches.append([envelope])
        else:
            current.append(envelope)
    if current:
        batches.append(current)
    return batches


def sample_envelopes(count: int) -> list[dict[str, Any]]:
    return [{
        "article_id": f"a-{number}", "source_sha256": sha256_bytes(str(number).encode()),
        "term": f"語{number}", "reading": f"ご{number}", "sequence": number,
        "kaishi_evidence": [], "read_only_context": {},
        "units": [{
            "unit_id": f"u-{number}-{unit}", "source_sha256": sha256_bytes(f"{number}-{unit}".encode()),
            "role": "glossary", "protected_tokens": [], "local_context": "glossary",
            "source_text": "definition " * (number % 7 + 1),
        } for unit in range(number % 4 + 1)],
    } for number in range(1, count + 1)]


def timed(operation):
    started = time.monotonic()
    cpu_started = time.process_time()
    result = operation()
    return result, {
        "wall_seconds": round(time.monotonic() - started, 6),
        "cpu_seconds": round(time.process_time() - cpu_started, 6),
    }


def main() -> int:
    args = parser().parse_args()
    if args.articles < 1:
        raise ValueError("articles must be positive")
    if not os.environ.get(args.database_url_env):
        raise RuntimeError(f"{args.database_url_env} is required")
    temporary = Path(tempfile.mkdtemp(prefix="jitendex-run-prep-"))
    try:
        config = Config(temporary, {
            "project": {"work_dir": str(temporary / "work"), "dist_dir": str(temporary / "dist")},
            "database": {"backend": "postgresql", "url_env": args.database_url_env, "pool_max": 4},
        })
        database = Database(config)
        database.migrate()
        connection = database.connect()
        try:
            connection.execute(
                """INSERT INTO source_snapshot(id,kind,version,url,sha256,local_path,extractor_version)
                VALUES (1,'jitendex','v','u','j','p','e'),(2,'kaishi','v','u','k','p','e')"""
            )
            connection.execute(
                """INSERT INTO run(id,jitendex_snapshot_id,kaishi_snapshot_id,selection_sha256,
                extractor_version,prompt_sha256,review_prompt_sha256,terminology_sha256,limits_json,
                pipeline_version) VALUES (1,1,2,'selection','e','p','r','t','{}','lexicographer-v2')"""
            )
            raw = canonical_json([
                "語", "ご", "", "", 0,
                {"type": "structured-content", "content": {"tag": "span", "lang": "en",
                 "data": {"content": "glossary"}, "content": "definition"}}, 1, "",
            ]).decode()
            article_rows = [(
                number, 1, (number - 1) // 10_000 + 1, (number - 1) % 10_000,
                f"語{number}", f"ご{number}", number, raw, sha256_bytes(f"article-{number}".encode()), 1,
            ) for number in range(1, args.articles + 1)]
            connection.copy_rows(
                "article", ("id", "snapshot_id", "bank_number", "entry_ordinal", "expression",
                            "reading", "sequence", "raw_json", "source_sha256", "selected"), article_rows,
            )
            connection.commit()
            extraction, extraction_time = timed(lambda: extract_selected(connection, 1))
            connection.commit()
            batching, batching_time = timed(lambda: make_batches(
                connection, 1, temporary / "work/inbox", {}, 12, 49_152, 200, 16_384,
            ))
            connection.commit()
            batch_rows = [tuple(row[index] for index in range(len(row))) for row in connection.execute(
                """SELECT id,run_id,kind,manifest_sha256,serialized_bytes,article_count,
                unit_count,manifest_path FROM batch ORDER BY id"""
            ).fetchall()]
            item_rows = [tuple(row[index] for index in range(len(row))) for row in connection.execute(
                "SELECT batch_id,unit_id,ordinal FROM batch_item ORDER BY batch_id,ordinal"
            ).fetchall()]
            audit_rows = [tuple(row[index] for index in range(len(row))) for row in connection.execute(
                """SELECT event_type,entity_type,entity_id,details_json FROM audit_event
                WHERE event_type='create' AND entity_type='batch' ORDER BY entity_id"""
            ).fetchall()]
            connection.execute("CREATE TEMP TABLE bench_batch (LIKE batch INCLUDING DEFAULTS)")
            connection.execute("CREATE TEMP TABLE bench_item (LIKE batch_item INCLUDING DEFAULTS)")
            connection.execute(
                """CREATE TEMP TABLE bench_audit (
                event_type TEXT NOT NULL,entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,details_json TEXT NOT NULL)"""
            )

            def legacy_load():
                for batch_row, audit_row in zip(batch_rows, audit_rows, strict=True):
                    connection.execute(
                        """INSERT INTO bench_batch(id,run_id,kind,manifest_sha256,serialized_bytes,
                        article_count,unit_count,manifest_path) VALUES (?,?,?,?,?,?,?,?)""", batch_row,
                    )
                    connection.executemany(
                        "INSERT INTO bench_item(batch_id,unit_id,ordinal) VALUES (?,?,?)",
                        (row for row in item_rows if row[0] == batch_row[0]),
                    )
                    connection.execute(
                        """INSERT INTO bench_audit(event_type,entity_type,entity_id,details_json)
                        VALUES (?,?,?,?)""", audit_row,
                    )

            _, legacy_load_time = timed(legacy_load)
            legacy_count_row = connection.execute(
                """SELECT (SELECT COUNT(*) FROM bench_batch),(SELECT COUNT(*) FROM bench_item),
                (SELECT COUNT(*) FROM bench_audit)"""
            ).fetchone()
            legacy_load_counts = tuple(legacy_count_row[index] for index in range(len(legacy_count_row)))
            connection.execute("TRUNCATE bench_batch,bench_item,bench_audit")

            def copy_load():
                connection.copy_rows(
                    "bench_batch", ("id", "run_id", "kind", "manifest_sha256", "serialized_bytes",
                                    "article_count", "unit_count", "manifest_path"), batch_rows,
                )
                connection.copy_rows("bench_item", ("batch_id", "unit_id", "ordinal"), item_rows)
                connection.copy_rows(
                    "bench_audit", ("event_type", "entity_type", "entity_id", "details_json"), audit_rows,
                )

            _, copy_load_time = timed(copy_load)
            copy_count_row = connection.execute(
                """SELECT (SELECT COUNT(*) FROM bench_batch),(SELECT COUNT(*) FROM bench_item),
                (SELECT COUNT(*) FROM bench_audit)"""
            ).fetchone()
            copy_load_counts = tuple(copy_count_row[index] for index in range(len(copy_count_row)))
            database_counts = {
                "articles": connection.execute("SELECT COUNT(*) FROM run_article WHERE run_id=1").fetchone()[0],
                "units": connection.execute("SELECT COUNT(*) FROM translation_unit WHERE run_id=1").fetchone()[0],
                "batches": connection.execute("SELECT COUNT(*) FROM batch WHERE run_id=1").fetchone()[0],
                "batch_items": connection.execute("SELECT COUNT(*) FROM batch_item").fetchone()[0],
                "batch_audits": connection.execute(
                    "SELECT COUNT(*) FROM audit_event WHERE event_type='create' AND entity_type='batch'"
                ).fetchone()[0],
            }
        finally:
            connection.close()
            database.close()

        envelopes = sample_envelopes(args.articles)
        limits = {
            "soft_max_articles": 12, "soft_max_bytes": 49_152, "soft_max_units": 200,
            "singleton_threshold_bytes": 16_384, "hard_max_article_bytes": 49_152,
            "hard_max_article_units": 200,
        }
        legacy, legacy_time = timed(lambda: legacy_pack(envelopes, {}, limits))
        optimized, optimized_time = timed(lambda: _pack_envelopes(envelopes, {}, **limits))
        legacy_bytes = [_manifest("b-" + "0" * 24, batch, {})[1] for batch in legacy]
        optimized_bytes = [_manifest("b-" + "0" * 24, batch, {})[1] for batch in optimized]
        parity = {
            "ordered_groups_match": [
                [article["article_id"] for article in batch] for batch in legacy
            ] == [
                [article["article_id"] for article in batch] for batch in optimized
            ],
            "manifest_bytes_match": legacy_bytes == optimized_bytes,
        }
        report = {
            "schema_version": 1, "article_count": args.articles, "luna_requests": 0,
            "extraction": {**extraction_time, **extraction},
            "batching": {**batching_time, **batching}, "database_counts": database_counts,
            "packing_comparison": {
                "legacy": legacy_time, "optimized": optimized_time,
                "speedup": round(legacy_time["wall_seconds"] / optimized_time["wall_seconds"], 3),
                **parity,
            },
            "database_loading_comparison": {
                "legacy": legacy_load_time, "copy": copy_load_time,
                "speedup": round(legacy_load_time["wall_seconds"] / copy_load_time["wall_seconds"], 3),
                "row_counts_match": legacy_load_counts == copy_load_counts,
                "row_counts": list(copy_load_counts),
            },
            "peak_memory_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        }
        if not all(parity.values()):
            raise RuntimeError(f"packing parity failed: {parity}")
        if legacy_load_counts != copy_load_counts:
            raise RuntimeError("database loading count mismatch")
        if database_counts != {
            "articles": args.articles, "units": args.articles, "batches": batching["batches_created"],
            "batch_items": args.articles, "batch_audits": batching["batches_created"],
        }:
            raise RuntimeError(f"database count mismatch: {database_counts}")
        atomic_write(args.output.resolve(), canonical_json(report) + b"\n")
        print(json.dumps({**report, "report_path": str(args.output.resolve())}, indent=2, sort_keys=True))
        return 0
    finally:
        shutil.rmtree(temporary)


if __name__ == "__main__":
    raise SystemExit(main())
