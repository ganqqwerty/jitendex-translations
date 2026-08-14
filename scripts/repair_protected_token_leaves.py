#!/usr/bin/env python3
"""Create audited corrected-manifest children for blocked protected-token leaves."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jitendex_ru.batch import _manifest
from jitendex_ru.config import Config
from jitendex_ru.database import Database, transaction
from jitendex_ru.db import audit
from jitendex_ru.extract_units import protected_tokens
from jitendex_ru.util import atomic_write, canonical_json, sha256_bytes


LEAF_SQL = """
SELECT b.* FROM batch b
WHERE b.run_id=? AND b.kind='translation' AND b.state='blocked'
  AND NOT EXISTS (
    SELECT 1 FROM audit_event ae WHERE ae.entity_id=b.id AND ae.event_type='split'
  )
  AND EXISTS (
    SELECT 1 FROM validation_issue vi JOIN attempt a ON a.id=vi.attempt_id
    WHERE a.batch_id=b.id AND vi.resolved_at IS NULL
      AND vi.code='protected_token_missing'
  )
ORDER BY b.id
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--run-id", type=int, required=True)
    args = parser.parse_args()

    config = Config.load(args.config)
    database = Database(config)
    connection = database.connect()
    created = 0
    try:
        leaves = connection.execute(LEAF_SQL, (args.run_id,)).fetchall()
        with transaction(connection, immediate=True):
            for parent in leaves:
                manifest = json.loads(Path(parent["manifest_path"]).read_text(encoding="utf-8"))
                units = [unit for article in manifest["articles"] for unit in article["units"]]
                if len(units) != 1:
                    raise RuntimeError(f"{parent['id']} is not a singleton leaf")
                manifest_unit = units[0]
                source = connection.execute(
                    "SELECT role,source_text FROM translation_unit WHERE id=?",
                    (manifest_unit["unit_id"],),
                ).fetchone()
                additions = [
                    token for token in protected_tokens(source["role"], source["source_text"])
                    if token not in manifest_unit.get("protected_tokens", [])
                ]
                if not additions:
                    raise RuntimeError(f"{parent['id']} has no missing manifest tokens to repair")
                manifest_unit["protected_tokens"] = [
                    *manifest_unit.get("protected_tokens", []), *additions,
                ]
                identity = {
                    "parent": parent["id"],
                    "repair": "manifest-protected-tokens-v1",
                    "unit_id": manifest_unit["unit_id"],
                    "tokens": additions,
                }
                child_id = f"b-{sha256_bytes(canonical_json(identity))[:24]}"
                child_manifest, data = _manifest(
                    child_id, manifest["articles"], manifest.get("terminology", {}),
                )
                child_path = Path(parent["manifest_path"]).parent / f"{child_id}.json"
                atomic_write(child_path, data + b"\n")
                connection.execute(
                    """INSERT INTO batch
                    (id,run_id,kind,manifest_sha256,serialized_bytes,article_count,unit_count,manifest_path)
                    VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        child_id, parent["run_id"], parent["kind"],
                        child_manifest["manifest_sha256"], len(data),
                        parent["article_count"], 1, str(child_path),
                    ),
                )
                connection.execute(
                    "INSERT INTO batch_item(batch_id,unit_id,ordinal) VALUES (?,?,0)",
                    (child_id, manifest_unit["unit_id"]),
                )
                connection.execute(
                    """UPDATE validation_issue SET resolved_at=CURRENT_TIMESTAMP,
                    waiver_reason='superseded by corrected protected-token manifest child'
                    WHERE resolved_at IS NULL AND attempt_id IN (
                      SELECT id FROM attempt WHERE batch_id=?
                    )""",
                    (parent["id"],),
                )
                audit(connection, "split", "batch", parent["id"], {
                    "children": [child_id],
                    "reason": "correct protected tokens missing from model manifest",
                    "tokens": additions,
                })
                audit(connection, "manifest_repair", "batch", child_id, {
                    "parent": parent["id"], "tokens_added": additions,
                })
                created += 1
    finally:
        connection.close()
        database.close()

    print(json.dumps({"run_id": args.run_id, "corrected_children_created": created}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
