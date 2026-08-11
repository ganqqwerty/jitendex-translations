#!/usr/bin/env python3
"""Ingest artifact-tool-extracted approved Jitendex tag rows into SQLite."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jitendex_ru.config import Config
from jitendex_ru.db import connect, initialize, transaction
from jitendex_ru.jitendex_tags import ingest_approved_tag_rows
from jitendex_ru.util import sha256_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("config.luna.clean-v1.toml"))
    parser.add_argument("--snapshot-id", type=int, required=True)
    parser.add_argument("--rows-json", type=Path, required=True)
    parser.add_argument("--source-workbook", type=Path, required=True)
    args = parser.parse_args()
    config = Config.load(args.config)
    rows = json.loads(args.rows_json.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("rows JSON must contain a list")
    source = args.source_workbook.resolve()
    initialize(config.db_path)
    connection = connect(config.db_path)
    try:
        with transaction(connection, immediate=True):
            result = ingest_approved_tag_rows(
                connection, args.snapshot_id, rows,
                source_path=str(source), source_sha256=sha256_file(source),
            )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
