#!/usr/bin/env python3
"""Translate the snapshot-scoped Jitendex tag catalog with isolated Luna calls."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from jitendex_ru.config import Config
from jitendex_ru.db import connect, initialize
from jitendex_ru.jitendex_tags import (
    import_jitendex_tags,
    ingest_tag_translations,
    translation_manifest,
)
from jitendex_ru.util import atomic_write, canonical_json, sha256_bytes


CODEX = Path("/Applications/ChatGPT.app/Contents/Resources/codex")


def _output_schema(manifest: dict[str, Any]) -> dict[str, Any]:
    choices = []
    for tag in manifest["tags"]:
        properties = {
            "tag_id": {"type": "integer", "const": tag["tag_id"]},
            "source_sha256": {"type": "string", "const": tag["source_sha256"]},
            "label_ru": {"type": "string"},
            "tooltip_description_ru": {"type": "string"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "review_reason": {"type": ["string", "null"]},
        }
        choices.append({
            "type": "object", "additionalProperties": False,
            "required": list(properties), "properties": properties,
        })
    properties = {
        "schema_version": {"type": "integer", "const": 1},
        "batch_id": {"type": "string", "const": manifest["batch_id"]},
        "translations": {
            "type": "array", "minItems": len(choices), "maxItems": len(choices),
            "items": {"anyOf": choices},
        },
    }
    return {
        "type": "object", "additionalProperties": False,
        "required": list(properties), "properties": properties,
    }


def _dispatch(
    manifest_path: Path, response_path: Path, prompt: str, model: str, reasoning_effort: str,
) -> dict[str, Any]:
    manifest_text = manifest_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".json", prefix="jitendex-tag-schema-",
        dir="/private/tmp", delete=False,
    ) as schema_file:
        json.dump(_output_schema(manifest), schema_file, ensure_ascii=False)
        schema_path = Path(schema_file.name)
    command = [
        str(CODEX), "exec", "--ephemeral", "--ignore-user-config", "--ignore-rules",
        "--skip-git-repo-check", "-s", "read-only", "-C", "/private/tmp",
        "-m", model, "-c", f'model_reasoning_effort="{reasoning_effort}"',
        "--output-schema", str(schema_path), "--json", "-o", str(response_path), "-",
    ]
    try:
        completed = subprocess.run(
            command,
            input=f"{prompt.rstrip()}\n\nSUPPLIED TAG MANIFEST\n{manifest_text}",
            text=True,
            capture_output=True,
            check=False,
        )
    finally:
        schema_path.unlink(missing_ok=True)
    if completed.returncode or not response_path.is_file():
        details = (completed.stdout + "\n" + completed.stderr).strip()[-5000:]
        raise RuntimeError(f"Luna failed for {manifest['batch_id']}: {details}")
    return json.loads(response_path.read_text(encoding="utf-8"))


def _escape(value: object) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def write_reports(connection, snapshot_id: int, report_dir: Path) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    rows = connection.execute(
        """SELECT source_kind,category,code,label_en,label_ru,description_en,description_ru,
                  occurrence_count,confidence,COALESCE(review_reason,'') review_reason,
                  COALESCE(translation_source,'luna') translation_source
        FROM jitendex_tag WHERE snapshot_id=?
        ORDER BY source_kind,category,code,label_en""", (snapshot_id,),
    ).fetchall()
    csv_path = report_dir / "jitendex-tags-ru.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(rows[0].keys() if rows else [])
        writer.writerows(tuple(row) for row in rows)
    markdown_path = report_dir / "jitendex-tags-ru.md"
    lines = [
        "# Jitendex tag translations — Luna v1", "",
        f"Snapshot ID: {snapshot_id}  ",
        f"Rows: {len(rows)}", "",
    ]
    for source_kind, title in (
        ("embedded_tooltip", "Embedded linguistic and usage tooltips"),
        ("tag_bank", "Yomitan tag-bank tooltips"),
    ):
        lines.extend([
            f"## {title}", "",
            "| Category | Code | English label | Russian label | English tooltip | Russian tooltip | Occurrences | Confidence | Review note | Source |",
            "|---|---|---|---|---|---|---:|---|---|---|",
        ])
        for row in rows:
            if row["source_kind"] != source_kind:
                continue
            lines.append("| " + " | ".join(_escape(row[key]) for key in (
                "category", "code", "label_en", "label_ru", "description_en", "description_ru",
                "occurrence_count", "confidence", "review_reason", "translation_source",
            )) + " |")
        lines.append("")
    atomic_write(markdown_path, ("\n".join(lines) + "\n").encode())
    return markdown_path, csv_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("config.luna.clean-v1.toml"))
    parser.add_argument("--batch-size", type=int, default=80)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--model", default="gpt-5.6-luna")
    parser.add_argument("--reasoning-effort", default="medium")
    args = parser.parse_args()
    config = Config.load(args.config)
    prompt_path = config.root / "prompts/translate_jitendex_tags_luna_v1.txt"
    prompt = prompt_path.read_text(encoding="utf-8")
    prompt_hash = sha256_bytes(prompt.encode())
    initialize(config.db_path)
    connection = connect(config.db_path)
    try:
        snapshot = connection.execute(
            "SELECT * FROM source_snapshot WHERE kind='jitendex' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if snapshot is None:
            raise ValueError("no Jitendex snapshot; run import-sources first")
        import_result = import_jitendex_tags(connection, snapshot["id"], Path(snapshot["local_path"]))
        connection.commit()
        rows = connection.execute(
            """SELECT * FROM jitendex_tag
            WHERE snapshot_id=? AND COALESCE(translation_source,'')!='approved_workbook'
            ORDER BY source_kind,category,code,label_en""",
            (snapshot["id"],),
        ).fetchall()
        work_dir = config.work_dir / "tag-translation"
        inbox = work_dir / "inbox"
        outbox = work_dir / "outbox"
        inbox.mkdir(parents=True, exist_ok=True)
        outbox.mkdir(parents=True, exist_ok=True)
        jobs = []
        for offset in range(0, len(rows), args.batch_size):
            batch_rows = rows[offset:offset + args.batch_size]
            identity = sha256_bytes(canonical_json([
                (row["id"], row["source_sha256"]) for row in batch_rows
            ]))[:20]
            batch_id = f"jt-{identity}"
            manifest = translation_manifest(batch_rows, batch_id)
            manifest_path = inbox / f"{batch_id}.json"
            response_path = outbox / f"{batch_id}.json"
            atomic_write(manifest_path, canonical_json(manifest) + b"\n")
            jobs.append((batch_rows, manifest_path, response_path))

        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = {
                pool.submit(
                    _dispatch, manifest_path, response_path, prompt, args.model, args.reasoning_effort,
                ): batch_rows
                for batch_rows, manifest_path, response_path in jobs
            }
            translated = 0
            for future in as_completed(futures):
                batch_rows = futures[future]
                payload = future.result()
                translated += ingest_tag_translations(
                    connection, payload, batch_rows,
                    model=args.model, reasoning_effort=args.reasoning_effort,
                    prompt_sha256=prompt_hash,
                )
                connection.commit()
        markdown_path, csv_path = write_reports(
            connection, snapshot["id"], config.work_dir / "reports",
        )
        print(json.dumps({
            **import_result,
            "translated": translated,
            "model": args.model,
            "reasoning_effort": args.reasoning_effort,
            "prompt_sha256": prompt_hash,
            "markdown_report": str(markdown_path),
            "csv_report": str(csv_path),
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
