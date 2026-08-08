from __future__ import annotations

import json
import math
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping

from .util import atomic_write, canonical_json, sha256_bytes


TRANSLATION_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "batch_id", "manifest_sha256", "translations"],
    "properties": {
        "schema_version": {"type": "integer", "const": 2},
        "batch_id": {"type": "string"},
        "manifest_sha256": {"type": "string"},
        "translations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["unit_id", "source_sha256", "target_text", "confidence", "review_reason"],
                "properties": {
                    "unit_id": {"type": "string"},
                    "source_sha256": {"type": "string"},
                    "target_text": {
                        "anyOf": [
                            {"type": "string", "minLength": 1},
                            {
                                "type": "array", "minItems": 1, "maxItems": 12,
                                "uniqueItems": True, "items": {"type": "string", "minLength": 1},
                            },
                        ]
                    },
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "review_reason": {"anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}]},
                },
            },
        },
    },
}


def build_translation_request(
    *, model: str, reasoning_effort: str, instructions: str, manifest: str,
) -> dict[str, Any]:
    """Build the identical tool-free body used for counting and Responses dispatch."""
    return {
        "model": model,
        "instructions": instructions,
        "input": [{
            "role": "user",
            "content": [{"type": "input_text", "text": manifest}],
        }],
        "reasoning": {"effort": reasoning_effort, "context": "current_turn"},
        "tools": [],
        "store": False,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "translation_payload",
                "strict": True,
                "schema": TRANSLATION_RESPONSE_SCHEMA,
            }
        },
    }


def count_input_tokens(
    request_body: Mapping[str, Any], api_key: str, *,
    base_url: str = "https://api.openai.com/v1",
    opener: Callable[..., Any] = urllib.request.urlopen,
    timeout: float = 60,
) -> int:
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required for exact input-token counting")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/responses/input_tokens",
        data=canonical_json(dict(request_body)),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with opener(request, timeout=timeout) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise ValueError(f"input-token API failed with HTTP {error.code}: {detail}") from error
    if not isinstance(payload, dict) or isinstance(payload.get("input_tokens"), bool) or not isinstance(payload.get("input_tokens"), int):
        raise ValueError("input-token API returned an invalid payload")
    if payload["input_tokens"] < 0:
        raise ValueError("input-token API returned a negative count")
    return payload["input_tokens"]


def _percentile(sorted_values: list[int], fraction: float) -> int:
    return sorted_values[min(len(sorted_values) - 1, math.ceil(fraction * len(sorted_values)) - 1)]


def audit_run_input_tokens(
    connection: sqlite3.Connection, run_id: int, *, prompt: str, model: str,
    reasoning_effort: str, api_key: str, counter: Callable[[Mapping[str, Any], str], int] = count_input_tokens,
) -> dict[str, Any]:
    batches = connection.execute(
        "SELECT * FROM batch WHERE run_id=? AND kind='translation' ORDER BY id", (run_id,)
    ).fetchall()
    if not batches:
        raise ValueError(f"run {run_id} has no translation batches")
    results = []
    for batch in batches:
        manifest = Path(batch["manifest_path"]).read_text(encoding="utf-8")
        request_body = build_translation_request(
            model=model, reasoning_effort=reasoning_effort, instructions=prompt, manifest=manifest,
        )
        results.append({
            "batch_id": batch["id"],
            "request_sha256": sha256_bytes(canonical_json(request_body)),
            "input_tokens": counter(request_body, api_key),
        })
    values = sorted(item["input_tokens"] for item in results)
    report = {
        "run_id": run_id,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "prompt_sha256": sha256_bytes(prompt.encode()),
        "request_count": len(results),
        "minimum_input_tokens": values[0],
        "median_input_tokens": _percentile(values, 0.50),
        "p95_input_tokens": _percentile(values, 0.95),
        "p99_input_tokens": _percentile(values, 0.99),
        "maximum_input_tokens": values[-1],
        "total_input_tokens": sum(values),
        "context_window": 1_050_000,
        "headroom_factor": 1_050_000 / values[-1],
        "requests": results,
    }
    report["passed"] = report["headroom_factor"] >= 4
    return report


def write_token_audit(path: Path, report: Mapping[str, Any]) -> None:
    atomic_write(path, canonical_json(dict(report)) + b"\n")
