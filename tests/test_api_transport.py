import json

import pytest

from jitendex_ru.api_transport import (
    DuplicateBatchResult,
    EffectiveModelMismatch,
    TransportResponseError,
    extract_responses_result,
    extract_worker_payload,
    parse_batch_jsonl,
    plan_batch_ingestion,
)


MODEL = "gpt-5.6-luna"
PAYLOAD = {
    "schema_version": 2,
    "batch_id": "batch-1",
    "manifest_sha256": "f" * 64,
    "translations": [],
}


def response(payload=PAYLOAD, *, model=MODEL):
    return {
        "id": "resp_1",
        "model": model,
        "status": "completed",
        "output": [
            {"type": "reasoning", "summary": []},
            {
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": json.dumps(payload)}],
            },
        ],
        "usage": {
            "input_tokens": 100,
            "input_tokens_details": {"cached_tokens": 25},
            "output_tokens": 30,
            "total_tokens": 130,
        },
    }


def batch_record(attempt_id, body=None):
    return {
        "id": f"batch_req_{attempt_id}",
        "custom_id": attempt_id,
        "response": {"status_code": 200, "request_id": f"req_{attempt_id}", "body": body or response()},
        "error": None,
    }


def test_extracts_exact_worker_payload_and_audit_metadata():
    extracted = extract_responses_result(response(), MODEL)
    assert extracted.payload == PAYLOAD
    assert extract_worker_payload(response(), MODEL) == PAYLOAD
    assert extracted.response_id == "resp_1"
    assert extracted.effective_model == MODEL
    assert extracted.status == "completed"
    assert extracted.finish_reason is None
    assert extracted.usage.input_tokens == 100
    assert extracted.usage.cached_input_tokens == 25
    assert extracted.usage.output_tokens == 30
    assert extracted.usage.total_tokens == 130


def test_rejects_wrong_effective_model_before_ingestion():
    with pytest.raises(EffectiveModelMismatch):
        extract_worker_payload(response(model="gpt-5.6-terra"), MODEL)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda item: item.update(status="incomplete"),
        lambda item: item["output"][1]["content"].append({"type": "refusal", "refusal": "no"}),
        lambda item: item["usage"].update(total_tokens=999),
    ],
)
def test_rejects_incomplete_ambiguous_or_inconsistent_responses(mutation):
    wrapped = response()
    mutation(wrapped)
    with pytest.raises(TransportResponseError):
        extract_responses_result(wrapped, MODEL)


def test_batch_results_match_attempt_ids_not_result_order():
    records = [batch_record("attempt-2"), batch_record("attempt-1")]
    plan = plan_batch_ingestion(records, ["attempt-1", "attempt-2"])
    assert [item.attempt_id for item in plan.pending] == ["attempt-2", "attempt-1"]
    assert [item.request_id for item in plan.pending] == ["req_attempt-2", "req_attempt-1"]
    assert plan.idempotent_replays == ()


def test_batch_duplicate_in_same_artifact_is_rejected():
    record = batch_record("attempt-1")
    with pytest.raises(DuplicateBatchResult):
        plan_batch_ingestion([record, record], ["attempt-1"])


def test_identical_prior_ingestion_is_noop_but_conflicting_replay_is_rejected():
    record = batch_record("attempt-1")
    first = plan_batch_ingestion([record], ["attempt-1"])
    fingerprint = first.pending[0].fingerprint

    replay = plan_batch_ingestion([record], ["attempt-1"], {"attempt-1": fingerprint})
    assert replay.pending == ()
    assert replay.idempotent_replays == ("attempt-1",)

    changed = batch_record("attempt-1", response({**PAYLOAD, "batch_id": "changed"}))
    with pytest.raises(DuplicateBatchResult):
        plan_batch_ingestion([changed], ["attempt-1"], {"attempt-1": fingerprint})


def test_batch_requires_complete_exact_attempt_coverage_and_success():
    with pytest.raises(TransportResponseError, match="missing Batch results"):
        plan_batch_ingestion([batch_record("attempt-1")], ["attempt-1", "attempt-2"])
    with pytest.raises(TransportResponseError, match="unexpected Batch result"):
        plan_batch_ingestion([batch_record("other")], ["attempt-1"])
    failed = batch_record("attempt-1")
    failed["response"]["status_code"] = 500
    with pytest.raises(TransportResponseError, match="non-success"):
        plan_batch_ingestion([failed], ["attempt-1"])


def test_parse_batch_jsonl_rejects_blank_and_malformed_records():
    line = json.dumps(batch_record("attempt-1"))
    assert parse_batch_jsonl(line)[0]["custom_id"] == "attempt-1"
    with pytest.raises(TransportResponseError, match="blank"):
        parse_batch_jsonl(f"{line}\n\n{line}")
    with pytest.raises(TransportResponseError, match="invalid JSON"):
        parse_batch_jsonl("{")
