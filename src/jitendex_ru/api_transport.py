from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


class TransportResponseError(ValueError):
    """A Responses API or Batch API envelope is unsafe to ingest."""


class EffectiveModelMismatch(TransportResponseError):
    """The API served a model other than the model requested for the attempt."""


class DuplicateBatchResult(TransportResponseError):
    """A Batch result would make attempt ingestion ambiguous or conflicting."""


@dataclass(frozen=True)
class UsageMetadata:
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class ExtractedResponse:
    payload: dict[str, Any]
    response_id: str
    effective_model: str
    status: str
    finish_reason: str | None
    usage: UsageMetadata


@dataclass(frozen=True)
class BatchResult:
    attempt_id: str
    response: Mapping[str, Any]
    request_id: str | None
    fingerprint: str


@dataclass(frozen=True)
class BatchIngestionPlan:
    pending: tuple[BatchResult, ...]
    idempotent_replays: tuple[str, ...]


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TransportResponseError(f"{label} must be an object")
    return value


def _non_negative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TransportResponseError(f"{label} must be a non-negative integer")
    return value


def verify_effective_model(response: Mapping[str, Any], expected_model: str) -> str:
    """Return the API-reported model, requiring an exact configured-model match."""
    effective_model = response.get("model")
    if not isinstance(effective_model, str) or not effective_model:
        raise TransportResponseError("response.model must be a non-empty string")
    if effective_model != expected_model:
        raise EffectiveModelMismatch(
            f"expected effective model {expected_model!r}, got {effective_model!r}"
        )
    return effective_model


def capture_usage(response: Mapping[str, Any]) -> UsageMetadata:
    """Extract the raw token counters needed for immutable attempt auditing."""
    usage = _mapping(response.get("usage"), "response.usage")
    input_tokens = _non_negative_int(usage.get("input_tokens"), "usage.input_tokens")
    output_tokens = _non_negative_int(usage.get("output_tokens"), "usage.output_tokens")
    total_tokens = _non_negative_int(usage.get("total_tokens"), "usage.total_tokens")
    details = _mapping(usage.get("input_tokens_details", {}), "usage.input_tokens_details")
    cached_tokens = _non_negative_int(details.get("cached_tokens", 0), "usage.input_tokens_details.cached_tokens")
    if cached_tokens > input_tokens:
        raise TransportResponseError("cached input tokens cannot exceed input tokens")
    if total_tokens != input_tokens + output_tokens:
        raise TransportResponseError("total tokens do not equal input plus output tokens")
    return UsageMetadata(input_tokens, cached_tokens, output_tokens, total_tokens)


def extract_responses_result(
    response: Mapping[str, Any], expected_model: str
) -> ExtractedResponse:
    """Extract one strict JSON worker payload from a completed Responses result."""
    response = _mapping(response, "response")
    response_id = response.get("id")
    if not isinstance(response_id, str) or not response_id:
        raise TransportResponseError("response.id must be a non-empty string")
    effective_model = verify_effective_model(response, expected_model)
    status = response.get("status")
    if status != "completed":
        raise TransportResponseError(f"response is not completed: {status!r}")

    output = response.get("output")
    if not isinstance(output, list):
        raise TransportResponseError("response.output must be an array")
    texts: list[str] = []
    for item in output:
        item = _mapping(item, "response.output item")
        if item.get("type") != "message":
            continue
        if item.get("status") not in (None, "completed"):
            raise TransportResponseError("output message is not completed")
        content = item.get("content")
        if not isinstance(content, list):
            raise TransportResponseError("output message content must be an array")
        for part in content:
            part = _mapping(part, "output content item")
            if part.get("type") != "output_text" or not isinstance(part.get("text"), str):
                raise TransportResponseError("message contains non-output_text content")
            texts.append(part["text"])
    if len(texts) != 1:
        raise TransportResponseError(f"expected exactly one output_text, got {len(texts)}")
    try:
        payload = json.loads(texts[0])
    except json.JSONDecodeError as error:
        raise TransportResponseError(f"output_text is not strict JSON: {error.msg}") from error
    if not isinstance(payload, dict):
        raise TransportResponseError("worker payload must be a JSON object")

    incomplete = response.get("incomplete_details")
    finish_reason = None
    if incomplete is not None:
        incomplete = _mapping(incomplete, "response.incomplete_details")
        reason = incomplete.get("reason")
        if reason is not None and not isinstance(reason, str):
            raise TransportResponseError("incomplete_details.reason must be a string or null")
        finish_reason = reason
    return ExtractedResponse(
        payload=payload,
        response_id=response_id,
        effective_model=effective_model,
        status=status,
        finish_reason=finish_reason,
        usage=capture_usage(response),
    )


def extract_worker_payload(response: Mapping[str, Any], expected_model: str) -> dict[str, Any]:
    """Convenience wrapper returning only the object accepted by worker validation."""
    return extract_responses_result(response, expected_model).payload


def parse_batch_jsonl(text: str) -> tuple[dict[str, Any], ...]:
    """Parse a Batch output artifact without ignoring blank or malformed records."""
    if not text:
        return ()
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            raise TransportResponseError(f"blank Batch result line {line_number}")
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise TransportResponseError(
                f"invalid JSON on Batch result line {line_number}: {error.msg}"
            ) from error
        if not isinstance(record, dict):
            raise TransportResponseError(f"Batch result line {line_number} must be an object")
        records.append(record)
    return tuple(records)


def _result_fingerprint(record: Mapping[str, Any]) -> str:
    stable = {"response": record.get("response"), "error": record.get("error")}
    encoded = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def plan_batch_ingestion(
    records: Iterable[Mapping[str, Any]],
    expected_attempt_ids: Iterable[str],
    ingested_fingerprints: Mapping[str, str] | None = None,
) -> BatchIngestionPlan:
    """Match results by attempt ID and identify safe replays without using row order.

    A repeated result inside one artifact is always invalid. Across ingestion
    runs, an identical fingerprint is an idempotent no-op; a different result
    for an already-ingested attempt is rejected.
    """
    expected_list = list(expected_attempt_ids)
    expected = set(expected_list)
    if len(expected) != len(expected_list):
        raise DuplicateBatchResult("expected attempt IDs are not unique")
    prior = dict(ingested_fingerprints or {})
    unknown_prior = set(prior) - expected
    if unknown_prior:
        raise TransportResponseError(f"ingested fingerprints contain unexpected attempt IDs: {sorted(unknown_prior)!r}")

    seen: set[str] = set()
    pending: list[BatchResult] = []
    replays: list[str] = []
    for raw_record in records:
        record = _mapping(raw_record, "Batch result")
        attempt_id = record.get("custom_id")
        if not isinstance(attempt_id, str) or not attempt_id:
            raise TransportResponseError("Batch result custom_id must be a non-empty attempt ID")
        if attempt_id in seen:
            raise DuplicateBatchResult(f"duplicate Batch result for attempt {attempt_id!r}")
        seen.add(attempt_id)
        if attempt_id not in expected:
            raise TransportResponseError(f"unexpected Batch result attempt ID {attempt_id!r}")
        if record.get("error") is not None:
            raise TransportResponseError(f"Batch result for {attempt_id!r} contains an API error")
        wrapper = _mapping(record.get("response"), "Batch result response")
        status_code = wrapper.get("status_code")
        if isinstance(status_code, bool) or not isinstance(status_code, int) or not 200 <= status_code < 300:
            raise TransportResponseError(f"Batch result for {attempt_id!r} has non-success status")
        body = _mapping(wrapper.get("body"), "Batch result response body")
        request_id = wrapper.get("request_id")
        if request_id is not None and not isinstance(request_id, str):
            raise TransportResponseError("Batch request_id must be a string or null")
        fingerprint = _result_fingerprint(record)
        if attempt_id in prior:
            if prior[attempt_id] != fingerprint:
                raise DuplicateBatchResult(
                    f"conflicting result for already-ingested attempt {attempt_id!r}"
                )
            replays.append(attempt_id)
            continue
        pending.append(BatchResult(attempt_id, body, request_id, fingerprint))

    missing = expected - seen
    if missing:
        raise TransportResponseError(f"missing Batch results for attempt IDs: {sorted(missing)!r}")
    return BatchIngestionPlan(tuple(pending), tuple(replays))
