#!/usr/bin/env python3
"""Create a slim immutable SQLite benchmark template without model requests."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from jitendex_ru.batch import make_batches
from jitendex_ru.config import Config
from jitendex_ru.database_tools import canonical_json_hash, file_sha256, sqlite_readonly, table_columns
from jitendex_ru.db import connect, initialize
from jitendex_ru.extract_units import extract_selected


ROOT = Path(__file__).resolve().parents[1]


def corpus(connection: Any, run_id: int) -> list[dict[str, object]]:
    """Return one workload record per indivisible expression/reading headword."""
    rows = connection.execute(
        """WITH unit_stats AS (
          SELECT article_id,COUNT(*) unit_count,COALESCE(SUM(byte_count),0) source_bytes
          FROM translation_unit WHERE run_id=? GROUP BY article_id
        ), issue_stats AS (
          SELECT tu.article_id,COUNT(vi.id) issue_count
          FROM translation_unit tu LEFT JOIN validation_issue vi ON vi.unit_id=tu.id
          WHERE tu.run_id=? GROUP BY tu.article_id
        )
        SELECT a.expression,a.reading,GROUP_CONCAT(a.id),COUNT(DISTINCT a.id),
               COALESCE(SUM(us.unit_count),0),COALESCE(SUM(us.source_bytes),0),
               COALESCE(SUM(ins.issue_count),0)
        FROM run_article ra JOIN article a ON a.id=ra.article_id
        LEFT JOIN unit_stats us ON us.article_id=a.id
        LEFT JOIN issue_stats ins ON ins.article_id=a.id
        WHERE ra.run_id=?
        GROUP BY a.expression,a.reading ORDER BY a.expression,a.reading""",
        (run_id, run_id, run_id),
    )
    result = []
    for expression, reading, ids, articles, units, source_bytes, issues in rows:
        result.append({
            "headword_sha256": hashlib.sha256(
                (expression + "\0" + reading).encode("utf-8")
            ).hexdigest(),
            "article_count": int(articles),
            "unit_count": int(units),
            "source_characters": int(source_bytes),
            "estimated_serialized_bytes": int(source_bytes) + 512 * int(units) + 1024 * int(articles),
            "historical_validation_issues": int(issues),
            "article_ids": [int(value) for value in ids.split(",")],
        })
    return result


def select_corpus(headwords: list[dict[str, object]], count: int) -> list[dict[str, object]]:
    """Keep difficult cases and a deterministic broad normal-work sample."""
    if count >= len(headwords):
        return headwords
    difficult_count = max(1, count // 5)
    difficult = sorted(
        headwords,
        key=lambda item: (
            int(item["historical_validation_issues"]), int(item["source_characters"]),
            str(item["headword_sha256"]),
        ),
        reverse=True,
    )[:difficult_count]
    chosen = {str(item["headword_sha256"]) for item in difficult}
    normal = sorted(
        (item for item in headwords if str(item["headword_sha256"]) not in chosen),
        key=lambda item: str(item["headword_sha256"]),
    )[:count - difficult_count]
    return sorted(difficult + normal, key=lambda item: str(item["headword_sha256"]))


def copy_rows(
    source: Any, target: Any, table: str,
    where: str = "", parameters: Iterable[Any] = (),
) -> int:
    columns = table_columns(source, table, backend="sqlite")
    names = ",".join(f'"{column}"' for column in columns)
    placeholders = ",".join("?" for _ in columns)
    rows = source.execute(f'SELECT {names} FROM "{table}" {where}', tuple(parameters))
    cursor = target.executemany(
        f'INSERT INTO "{table}" ({names}) VALUES ({placeholders})', rows,
    )
    return cursor.rowcount


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--stage-id", required=True)
    parser.add_argument("--headwords", type=int, default=60_000)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--report-dir", type=Path,
        default=ROOT / "reports/luna_performance/stage-definitions",
    )
    parser.add_argument("--create-disposable-stage-database", action="store_true")
    args = parser.parse_args()
    if args.headwords < 1:
        parser.error("--headwords must be positive")
    if not args.create_disposable_stage_database:
        parser.error("creating the template requires --create-disposable-stage-database")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error("--output-dir must be absent or empty")
    if not args.report_dir.resolve().is_relative_to(
        ROOT / "reports/luna_performance/stage-definitions"
    ):
        parser.error("--report-dir must stay under reports/luna_performance/stage-definitions")

    source = sqlite_readonly(args.source)
    source_run = source.execute("SELECT * FROM run WHERE id=?", (args.run_id,)).fetchone()
    if source_run is None:
        parser.error("unknown source run")
    if source.execute(
        "SELECT COUNT(*) FROM translation_unit tu WHERE tu.run_id=? AND NOT EXISTS ("
        "SELECT 1 FROM translation t WHERE t.run_id=tu.run_id AND t.unit_id=tu.id AND t.accepted=1)",
        (args.run_id,),
    ).fetchone()[0]:
        parser.error("source run must have complete accepted translation coverage")
    headwords = select_corpus(corpus(source, args.run_id), args.headwords)
    if not headwords:
        parser.error("source run has no benchmark corpus")
    article_ids = sorted({article for item in headwords for article in item["article_ids"]})

    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_base = {
        "schema_version": 1,
        "source_database_sha256": file_sha256(args.source),
        "source_run_id": args.run_id,
        "selection": {
            "method": "difficulty-fifth-plus-hash-sample-v1",
            "headword_count": len(headwords),
            "article_count": len(article_ids),
            "unit_count": sum(int(item["unit_count"]) for item in headwords),
            "source_characters": sum(int(item["source_characters"]) for item in headwords),
        },
        "headwords": headwords,
    }
    corpus_sha256 = canonical_json_hash(manifest_base)
    manifest = {**manifest_base, "corpus_sha256": corpus_sha256}
    manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    (args.output_dir / "corpus_manifest.json").write_text(manifest_text, encoding="utf-8")

    database_path = args.output_dir / "template.sqlite3"
    initialize(database_path)
    target = connect(database_path)
    try:
        snapshot_ids = (source_run["jitendex_snapshot_id"], source_run["kaishi_snapshot_id"])
        copy_rows(source, target, "source_snapshot", "WHERE id IN (?,?)", snapshot_ids)
        for start in range(0, len(article_ids), 500):
            chunk = article_ids[start:start + 500]
            marks = ",".join("?" for _ in chunk)
            copy_rows(source, target, "article", f"WHERE id IN ({marks})", chunk)
        copy_rows(
            source, target, "jitendex_tag", "WHERE snapshot_id=?",
            (source_run["jitendex_snapshot_id"],),
        )
        target.execute("UPDATE article SET selected=1")
        selection_sha256 = hashlib.sha256(
            (corpus_sha256 + "\0" + args.stage_id).encode("utf-8")
        ).hexdigest()
        new_run = target.execute(
            """INSERT INTO run(jitendex_snapshot_id,kaishi_snapshot_id,selection_sha256,
            extractor_version,prompt_sha256,review_prompt_sha256,terminology_sha256,
            limits_json,pipeline_version,state)
            VALUES (?,?,?,?,?,?,?,?,?,'active') RETURNING id""",
            (
                source_run["jitendex_snapshot_id"], source_run["kaishi_snapshot_id"],
                selection_sha256, source_run["extractor_version"], source_run["prompt_sha256"],
                source_run["review_prompt_sha256"], source_run["terminology_sha256"],
                source_run["limits_json"], source_run["pipeline_version"],
            ),
        ).fetchone()
        benchmark_run_id = int(new_run[0])
        extraction = extract_selected(target, benchmark_run_id)
        config = Config.load(args.config)
        limits = config.raw["batch"]
        terminology = json.loads(
            (config.root / "terminology/ru-v1.json").read_text(encoding="utf-8")
        )
        batching = make_batches(
            target, benchmark_run_id, args.output_dir / "inbox", terminology,
            limits["soft_max_articles"], limits["soft_max_bytes"], limits["soft_max_units"],
            limits["singleton_threshold_bytes"], limits.get("hard_max_article_bytes"),
            limits.get("hard_max_article_units"),
        )
        target.execute(
            "INSERT INTO benchmark_marker(stage_id,corpus_sha256,run_id) VALUES (?,?,?)",
            (args.stage_id, corpus_sha256, benchmark_run_id),
        )
        target.commit()
    finally:
        target.close()
        source.close()

    stage = {
        "schema_version": 1,
        "stage_id": args.stage_id,
        "corpus_sha256": corpus_sha256,
        "database_backend": "sqlite",
        "database_path": str(database_path.resolve()),
        "run_id": benchmark_run_id,
        "source_run_id": args.run_id,
        **manifest["selection"],
        "batch_count": batching["batches_created"],
        "extracted_units": extraction["units_added"],
        "template": True,
    }
    stage_text = json.dumps(stage, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    (args.output_dir / "stage.json").write_text(stage_text, encoding="utf-8")
    args.report_dir.mkdir(parents=True, exist_ok=True)
    (args.report_dir / f"{args.stage_id}.corpus.json").write_text(
        manifest_text, encoding="utf-8",
    )
    (args.report_dir / f"{args.stage_id}.stage.json").write_text(
        stage_text, encoding="utf-8",
    )
    print(json.dumps({"event": "benchmark_template_prepared", **stage}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
