#!/usr/bin/env python3
"""Ingest exact catalog text for terminal Luna leaves with required terminology."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jitendex_ru.batch import claim
from jitendex_ru.config import Config
from jitendex_ru.database import Database, transaction
from jitendex_ru.validate_response import ingest_response


LEAF_SQL = """
WITH split_ids AS (
  SELECT DISTINCT entity_id FROM audit_event WHERE event_type='split'
)
SELECT b.id,b.manifest_path
FROM batch b
LEFT JOIN split_ids s ON s.entity_id=b.id
WHERE b.run_id=? AND b.kind='translation' AND b.state='blocked'
  AND s.entity_id IS NULL
ORDER BY b.id
"""


def required_payload(manifest: dict) -> dict | None:
    translations = []
    for article in manifest.get("articles", []):
        for unit in article.get("units", []):
            required = unit.get("required_terminology")
            if not isinstance(required, dict) or not isinstance(required.get("target_text"), str):
                return None
            translations.append({
                "unit_id": unit["unit_id"],
                "source_sha256": unit["source_sha256"],
                "target_text": required["target_text"],
                "confidence": "high",
                "review_reason": None,
            })
    if not translations:
        return None
    return {
        "schema_version": 2,
        "batch_id": manifest["batch_id"],
        "manifest_sha256": manifest["manifest_sha256"],
        "translations": translations,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--worker-id", default="required-terminology-repair")
    args = parser.parse_args()

    config = Config.load(args.config)
    database = Database(config)
    connection = database.connect()
    try:
        repairs = []
        for row in connection.execute(LEAF_SQL, (args.run_id,)).fetchall():
            manifest = json.loads(Path(row["manifest_path"]).read_text(encoding="utf-8"))
            payload = required_payload(manifest)
            if payload is not None:
                repairs.append((row["id"], payload))
        with transaction(connection, immediate=True):
            connection.executemany(
                "UPDATE batch SET state='ready',lease_token=NULL,lease_expires_at=NULL WHERE id=? AND state='blocked'",
                ((batch_id,) for batch_id, _ in repairs),
            )
    finally:
        connection.close()

    model = config.model("translation")
    repaired = 0
    for batch_id, payload in repairs:
        connection = database.connect()
        try:
            item = claim(
                connection, args.worker_id, config.work_dir / "outbox",
                run_id=args.run_id, kind="translation", batch_id=batch_id,
                model_id=model["id"], reasoning_effort=model["reasoning_effort"],
                transport="codex-agent",
            )
            if item is None:
                raise RuntimeError(f"could not claim {batch_id}")
            response_path = Path(item["response_path"])
            response_path.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            ingest_response(connection, response_path)
            connection.commit()
            repaired += 1
        finally:
            connection.close()

    database.close()
    print(json.dumps({"run_id": args.run_id, "repaired_batches": repaired}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
