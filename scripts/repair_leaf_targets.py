#!/usr/bin/env python3
"""Claim terminal singleton leaves and ingest explicitly supplied targets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jitendex_ru.batch import claim
from jitendex_ru.config import Config
from jitendex_ru.database import Database, transaction
from jitendex_ru.validate_response import ingest_response


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--targets", type=Path, required=True)
    parser.add_argument("--worker-id", default="targeted-leaf-repair")
    args = parser.parse_args()

    config = Config.load(args.config)
    database = Database(config)
    targets = json.loads(args.targets.read_text(encoding="utf-8"))
    model = config.model("translation")
    repaired = 0

    for entry in targets:
        batch_id = entry["batch_id"]
        connection = database.connect()
        try:
            with transaction(connection, immediate=True):
                updated = connection.execute(
                    "UPDATE batch SET state='ready',lease_token=NULL,lease_expires_at=NULL "
                    "WHERE id=? AND run_id=? AND kind='translation' AND state='blocked'",
                    (batch_id, args.run_id),
                )
                if updated.rowcount != 1:
                    raise RuntimeError(f"{batch_id} is not a terminal blocked batch in run {args.run_id}")
            item = claim(
                connection, args.worker_id, config.work_dir / "outbox",
                run_id=args.run_id, kind="translation", batch_id=batch_id,
                model_id=model["id"], reasoning_effort=model["reasoning_effort"],
                transport="codex-agent",
            )
            if item is None:
                raise RuntimeError(f"could not claim {batch_id}")
            manifest = json.loads(Path(item["request_path"]).read_text(encoding="utf-8"))
            units = [unit for article in manifest["articles"] for unit in article["units"]]
            if len(units) != 1:
                raise RuntimeError(f"{batch_id} is not a singleton leaf")
            unit = units[0]
            payload = {
                "schema_version": 2,
                "batch_id": manifest["batch_id"],
                "manifest_sha256": manifest["manifest_sha256"],
                "translations": [{
                    "unit_id": unit["unit_id"],
                    "source_sha256": unit["source_sha256"],
                    "target_text": entry["target_text"],
                    "confidence": "high",
                    "review_reason": None,
                }],
            }
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
