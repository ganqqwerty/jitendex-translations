#!/usr/bin/env python3
"""Dispatch isolated translation or review manifests through the bundled Codex CLI.

The model process runs in an ephemeral, read-only temporary workspace and receives
only the configured prompt plus one manifest on stdin. The coordinator owns all
database access, response ingestion, retry state, and usage auditing.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jitendex_ru.batch import claim, retry_or_split
from jitendex_ru.config import Config
from jitendex_ru.db import audit, connect, record_attempt_usage, transaction
from jitendex_ru.review import ingest_review
from jitendex_ru.validate_response import ValidationFailure, ingest_response


CODEX = Path("/Applications/ChatGPT.app/Contents/Resources/codex")


@dataclass(frozen=True)
class DispatchResult:
    claim: dict[str, str]
    returncode: int
    stdout: str
    stderr: str
    thread_id: str | None
    usage: dict[str, int] | None
    latency_ms: int


def parse_events(stdout: str) -> tuple[str | None, dict[str, int] | None]:
    thread_id = None
    usage = None
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "thread.started":
            thread_id = event.get("thread_id")
        if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
            usage = event["usage"]
    return thread_id, usage


def _target_schema(role: str) -> dict[str, Any]:
    if role == "glossary_set":
        return {
            "type": "array", "items": {"type": "string"},
        }
    return {"type": "string"}


def build_output_schema(manifest: dict[str, Any], kind: str) -> dict[str, Any]:
    units = [unit for article in manifest["articles"] for unit in article["units"]]
    items = []
    for unit in units:
        if kind == "translation":
            properties = {
                "unit_id": {"type": "string", "const": unit["unit_id"]},
                "source_sha256": {"type": "string", "const": unit["source_sha256"]},
                "target_text": _target_schema(unit["role"]),
                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                "review_reason": {"type": ["string", "null"]},
            }
        else:
            properties = {
                "unit_id": {"type": "string", "const": unit["unit_id"]},
                "source_sha256": {"type": "string", "const": unit["source_sha256"]},
                "decision": {"type": "string", "enum": ["accept", "replace", "needs_adjudication"]},
                "replacement_target": {"anyOf": [_target_schema(unit["role"]), {"type": "null"}]},
                "reason": {"type": ["string", "null"]},
            }
        items.append({
            "type": "object", "additionalProperties": False,
            "required": list(properties), "properties": properties,
        })
    collection = "translations" if kind == "translation" else "reviews"
    properties = {
        "schema_version": {"type": "integer", "const": 2},
        "batch_id": {"type": "string", "const": manifest["batch_id"]},
        "manifest_sha256": {"type": "string", "const": manifest["manifest_sha256"]},
        collection: {
            "type": "array", "minItems": len(items), "maxItems": len(items),
            "items": {"anyOf": items},
        },
    }
    return {
        "type": "object", "additionalProperties": False,
        "required": list(properties), "properties": properties,
    }


def dispatch_one(item: dict[str, str], prompt: str, kind: str) -> DispatchResult:
    manifest_text = Path(item["request_path"]).read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    model_input = f"{prompt.rstrip()}\n\nSUPPLIED BATCH\n{manifest_text}"
    schema_file = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".json", prefix="jitendex-schema-",
        dir="/private/tmp", delete=False,
    )
    try:
        json.dump(build_output_schema(manifest, kind), schema_file, ensure_ascii=False)
        schema_file.close()
        schema_path = Path(schema_file.name)
    except Exception:
        schema_file.close()
        Path(schema_file.name).unlink(missing_ok=True)
        raise
    command = [
        str(CODEX), "exec", "--ephemeral", "--ignore-user-config", "--ignore-rules",
        "--skip-git-repo-check", "-s", "read-only", "-C", "/private/tmp",
        "-m", item["model_id"], "-c", f'model_reasoning_effort="{item["reasoning_effort"]}"',
        "--output-schema", str(schema_path), "--json", "-o", item["response_path"], "-",
    ]
    started = time.monotonic()
    try:
        completed = subprocess.run(command, input=model_input, text=True, capture_output=True, check=False)
    finally:
        schema_path.unlink(missing_ok=True)
    latency_ms = round((time.monotonic() - started) * 1000)
    thread_id, usage = parse_events(completed.stdout)
    return DispatchResult(
        claim=item, returncode=completed.returncode, stdout=completed.stdout,
        stderr=completed.stderr, thread_id=thread_id, usage=usage, latency_ms=latency_ms,
    )


def reject_transport(config: Config, kind: str, result: DispatchResult, reason: str) -> None:
    connection = connect(config.db_path)
    try:
        with transaction(connection, immediate=True):
            connection.execute(
                "UPDATE attempt SET outcome='rejected',error_json=?,completed_at=CURRENT_TIMESTAMP WHERE id=?",
                (json.dumps({"transport_error": reason}), result.claim["attempt_id"]),
            )
            connection.execute(
                "UPDATE batch SET state='retryable' WHERE id=?", (result.claim["batch_id"],),
            )
            audit(connection, "reject", "attempt", result.claim["attempt_id"], {"transport_error": reason})
        if kind == "translation":
            retry_or_split(connection, result.claim["batch_id"])
            connection.commit()
        else:
            batch = connection.execute(
                "SELECT attempt_count FROM batch WHERE id=?", (result.claim["batch_id"],),
            ).fetchone()
            state = "ready" if batch["attempt_count"] < 3 else "blocked"
            connection.execute(
                "UPDATE batch SET state=?,lease_token=NULL,lease_expires_at=NULL WHERE id=?",
                (state, result.claim["batch_id"]),
            )
            audit(connection, "retry" if state == "ready" else "block", "review_batch", result.claim["batch_id"], {
                "attempt_count": batch["attempt_count"], "reason": reason,
            })
            connection.commit()
    finally:
        connection.close()


def ingest(config: Config, kind: str, result: DispatchResult) -> tuple[bool, str]:
    response_path = Path(result.claim["response_path"])
    if result.returncode or result.usage is None or not response_path.is_file():
        reason = (result.stdout + "\n" + result.stderr).strip()[-5000:] or f"Codex exited {result.returncode} without usage/response"
        reject_transport(config, kind, result, reason)
        return False, reason

    input_tokens = int(result.usage.get("input_tokens", 0))
    cached_tokens = int(result.usage.get("cached_input_tokens", 0))
    output_tokens = int(result.usage.get("output_tokens", 0))
    connection = connect(config.db_path)
    try:
        record_attempt_usage(
            connection, result.claim["attempt_id"],
            effective_model_id=result.claim["model_id"],
            reasoning_effort=result.claim["reasoning_effort"], transport="codex-agent",
            input_tokens=input_tokens, cached_input_tokens=cached_tokens,
            output_tokens=output_tokens, total_tokens=input_tokens + output_tokens,
            api_request_id=result.thread_id, finish_reason="turn.completed",
            status_reason="isolated bundled Codex route", latency_ms=result.latency_ms,
        )
        # Usage belongs to the completed model request even if deterministic
        # ingestion rejects its payload, so persist it independently first.
        connection.commit()
        if kind == "translation":
            outcome = ingest_response(connection, response_path)
        else:
            outcome = ingest_review(connection, response_path)
        connection.commit()
        return True, json.dumps(outcome, ensure_ascii=False, sort_keys=True)
    except ValidationFailure as error:
        connection.commit()
        retry_or_split(connection, result.claim["batch_id"])
        connection.commit()
        return False, json.dumps(error.issues, ensure_ascii=False)
    except Exception as error:
        connection.rollback()
        reject_transport(config, kind, result, str(error))
        return False, str(error)
    finally:
        connection.close()


def next_claim(config: Config, run_id: int, kind: str, worker_id: str) -> dict[str, str] | None:
    connection = connect(config.db_path)
    try:
        model = config.model(kind)
        return claim(
            connection, worker_id, config.work_dir / "outbox", run_id=run_id, kind=kind,
            model_id=model["id"], reasoning_effort=model["reasoning_effort"],
            transport="codex-agent",
        )
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--kind", choices=("translation", "review"), required=True)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--worker-prefix", required=True)
    parser.add_argument("--max-submissions", type=int)
    args = parser.parse_args()
    if args.concurrency < 1:
        parser.error("--concurrency must be positive")
    if not CODEX.is_file():
        parser.error(f"bundled Codex CLI not found: {CODEX}")

    config = Config.load(args.config)
    prompt_key = "translation_prompt" if args.kind == "translation" else "review_prompt"
    prompt_name = config.raw["versions"][prompt_key].replace("-", "_")
    prompt = (config.root / "prompts" / f"{prompt_name}.txt").read_text(encoding="utf-8")
    submitted = completed = failed = 0
    active: dict[Future[DispatchResult], str] = {}

    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        while True:
            while len(active) < args.concurrency:
                if args.max_submissions is not None and submitted >= args.max_submissions:
                    break
                submitted += 1
                item = next_claim(
                    config, args.run_id, args.kind, f"{args.worker_prefix}-{submitted:04d}",
                )
                if item is None:
                    submitted -= 1
                    break
                active[executor.submit(dispatch_one, item, prompt, args.kind)] = item["batch_id"]
                print(json.dumps({"event": "submitted", "number": submitted, "batch_id": item["batch_id"]}), flush=True)
            if not active:
                break
            done, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in done:
                batch_id = active.pop(future)
                try:
                    result = future.result()
                    ok, detail = ingest(config, args.kind, result)
                except Exception as error:
                    ok, detail = False, str(error)
                completed += 1
                failed += int(not ok)
                print(json.dumps({
                    "event": "completed", "batch_id": batch_id, "ok": ok,
                    "detail": detail, "completed": completed, "failed": failed,
                }, ensure_ascii=False), flush=True)

    print(json.dumps({"submitted": submitted, "completed": completed, "failed_attempts": failed}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
