#!/usr/bin/env python3
"""Validate benchmark stage/result contracts and payload-safety rules."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

import fastjsonschema

from jitendex_ru.database_tools import canonical_json_hash


ROOT = Path(__file__).resolve().parents[1]
SECRET_KEYS = ("password", "postgresql://", "api_key", "authorization")


def validate_file(payload_path: Path, schema_path: Path) -> dict:
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    fastjsonschema.compile(schema)(payload)
    lowered = payload_path.read_text(encoding="utf-8").lower()
    if any(key in lowered for key in SECRET_KEYS):
        raise RuntimeError(f"possible credential material in {payload_path}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--result", type=Path)
    args = parser.parse_args()
    stage = validate_file(
        args.stage, ROOT / "reports/luna_performance/stage.schema.json",
    )
    corpus_path = args.corpus
    if corpus_path is None:
        if args.stage.name.endswith(".stage.json"):
            corpus_path = args.stage.with_name(args.stage.name.replace(".stage.json", ".corpus.json"))
        else:
            corpus_path = args.stage.with_name("corpus_manifest.json")
    corpus = validate_file(
        corpus_path, ROOT / "reports/luna_performance/corpus.schema.json",
    )
    claimed_hash = corpus.pop("corpus_sha256")
    if canonical_json_hash(corpus) != claimed_hash or claimed_hash != stage["corpus_sha256"]:
        raise RuntimeError("corpus manifest hash is invalid")
    headword_hashes = [item["headword_sha256"] for item in corpus["headwords"]]
    article_ids = [article_id for item in corpus["headwords"] for article_id in item["article_ids"]]
    if len(headword_hashes) != len(set(headword_hashes)):
        raise RuntimeError("corpus contains duplicate headwords")
    if len(article_ids) != len(set(article_ids)):
        raise RuntimeError("corpus splits an article across headwords")
    selection = corpus["selection"]
    derived = {
        "headword_count": len(corpus["headwords"]),
        "article_count": len(article_ids),
        "unit_count": sum(item["unit_count"] for item in corpus["headwords"]),
        "source_characters": sum(item["source_characters"] for item in corpus["headwords"]),
    }
    if any(item["article_count"] != len(item["article_ids"]) for item in corpus["headwords"]):
        raise RuntimeError("corpus headword article counts are inconsistent")
    if any(derived[key] != selection[key] for key in derived):
        raise RuntimeError("corpus aggregate counts are inconsistent")
    for key in ("headword_count", "article_count", "unit_count", "source_characters", "method"):
        if selection[key] != stage[key]:
            raise RuntimeError(f"corpus selection does not match stage: {key}")
    database_path = Path(stage["database_path"]).resolve()
    if database_path == (ROOT / "work/progress.sqlite3").resolve():
        raise RuntimeError("production SQLite database is not a benchmark stage")
    connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
    marker = connection.execute(
        "SELECT corpus_sha256,run_id FROM benchmark_marker WHERE stage_id=?",
        (stage["stage_id"],),
    ).fetchone()
    connection.close()
    if marker != (stage["corpus_sha256"], stage["run_id"]):
        raise RuntimeError("benchmark marker does not match the stage definition")
    result = None
    if args.result:
        result = validate_file(
            args.result, ROOT / "reports/luna_performance/result.schema.json",
        )
        if result["corpus_sha256"] != stage["corpus_sha256"]:
            raise RuntimeError("result corpus hash does not match stage")
        if any(result["postflight"].values()):
            raise RuntimeError("result postflight contains nonzero failures")
        configuration = result["configuration"]
        counters = result["counters"]
        connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
        try:
            identity = connection.execute(
                "SELECT prompt_sha256,limits_json,pipeline_version FROM run WHERE id=?",
                (stage["run_id"],),
            ).fetchone()
        finally:
            connection.close()
        expected_limits = hashlib.sha256(identity[1].encode("utf-8")).hexdigest()
        if configuration["prompt_sha256"] != identity[0]:
            raise RuntimeError("result prompt hash does not match stage")
        if configuration["limits_sha256"] != expected_limits:
            raise RuntimeError("result batch-limits hash does not match stage")
        if configuration["pipeline_version"] != identity[2]:
            raise RuntimeError("result pipeline version does not match stage")
        if counters["total_tokens"] != counters["input_tokens"] + counters["output_tokens"]:
            raise RuntimeError("result token total is inconsistent")
        if counters["completed"] > counters["submitted"]:
            raise RuntimeError("result completed count exceeds submissions")
        if counters["failed_attempts"] > counters["completed"]:
            raise RuntimeError("result failure count exceeds completions")
        if configuration["dry_run"]:
            if counters["submitted"] or counters["measured_seconds"] or result["phases"]:
                raise RuntimeError("dry-run result contains measured work")
        else:
            phases = result["phases"]
            measurements = [item for item in phases if item["phase"] == "measurement"]
            shutdowns = [item for item in phases if item["phase"] == "shutdown"]
            if len(measurements) != 1 or len(shutdowns) != 1:
                raise RuntimeError("measured result needs exactly one measurement and shutdown phase")
            minimum = float(configuration["measurement_seconds"]) - 1
            if float(counters["measured_seconds"]) < minimum:
                raise RuntimeError("result measured window is incomplete")
    print(json.dumps({
        "event": "benchmark_contract_valid", "stage_id": stage["stage_id"],
        "result_validated": result is not None,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
