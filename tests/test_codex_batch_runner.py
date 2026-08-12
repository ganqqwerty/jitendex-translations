import importlib.util
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from jitendex_ru.db import connect, initialize


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("run_codex_batches", ROOT / "scripts/run_codex_batches.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_parse_codex_usage_events():
    thread_id, usage = MODULE.parse_events(
        '{"type":"thread.started","thread_id":"thread-1"}\n'
        '{"type":"turn.completed","usage":{"input_tokens":10,"cached_input_tokens":4,"output_tokens":3}}\n'
    )
    assert thread_id == "thread-1"
    assert usage == {"input_tokens": 10, "cached_input_tokens": 4, "output_tokens": 3}


def test_manifest_schema_constrains_ordered_ids_hashes_and_target_types():
    manifest = {
        "batch_id": "b-1", "manifest_sha256": "a" * 64,
        "articles": [{"units": [
            {"unit_id": "u-1", "source_sha256": "b" * 64, "role": "glossary_set"},
            {"unit_id": "u-2", "source_sha256": "c" * 64, "role": "example"},
        ]}],
    }
    schema = MODULE.build_output_schema(manifest, "translation")
    translations = schema["properties"]["translations"]
    assert translations["minItems"] == translations["maxItems"] == 2
    alternatives = translations["items"]["anyOf"]
    assert alternatives[0]["properties"]["unit_id"] == {"type": "string", "const": "u-1"}
    assert alternatives[0]["properties"]["source_sha256"] == {"type": "string", "const": "b" * 64}
    assert alternatives[0]["properties"]["target_text"]["type"] == "array"
    assert alternatives[1]["properties"]["target_text"]["type"] == "string"


def _progress_database(tmp_path):
    db_path = tmp_path / "progress.sqlite3"
    initialize(db_path)
    connection = connect(db_path)
    connection.execute(
        "INSERT INTO source_snapshot(kind,version,url,sha256,local_path,extractor_version) "
        "VALUES ('jitendex','v','u','j','j','e')"
    )
    connection.execute(
        "INSERT INTO source_snapshot(kind,version,url,sha256,local_path,extractor_version) "
        "VALUES ('kaishi','v','u','k','k','e')"
    )
    connection.execute(
        """INSERT INTO run(id,jitendex_snapshot_id,kaishi_snapshot_id,selection_sha256,
        extractor_version,prompt_sha256,review_prompt_sha256,terminology_sha256,limits_json)
        VALUES (1,1,2,'s','e','p','rp','t','{}')"""
    )
    for article_id, expression, reading in (
        (1, "同じ", "おなじ"), (2, "同じ", "おなじ"), (3, "別", "べつ"),
    ):
        connection.execute(
            """INSERT INTO article(id,snapshot_id,bank_number,entry_ordinal,expression,reading,
            sequence,raw_json,source_sha256) VALUES (?,1,1,?,?,?,?,?,?)""",
            (article_id, article_id, expression, reading, article_id, "[]", f"h{article_id}"),
        )
    connection.execute(
        "INSERT INTO run_article(run_id,article_id,structural_fingerprint) VALUES (1,1,'f1')"
    )
    connection.commit()
    connection.close()
    return db_path


def test_live_progress_requires_every_article_for_a_duplicate_headword(tmp_path):
    db_path = _progress_database(tmp_path)
    config = SimpleNamespace(db_path=db_path)

    assert MODULE.live_headword_progress(config, 1) == (0, 2)

    connection = connect(db_path)
    connection.execute(
        "INSERT INTO run_article(run_id,article_id,structural_fingerprint) VALUES (1,2,'f2')"
    )
    connection.commit()
    connection.close()
    assert MODULE.live_headword_progress(config, 1) == (1, 2)

    connection = connect(db_path)
    connection.execute(
        """INSERT INTO translation_unit(id,run_id,article_id,json_pointer,role,source_text,
        source_sha256,byte_count) VALUES ('u1',1,2,'/x','glossary','x','h',1)"""
    )
    connection.commit()
    connection.close()
    assert MODULE.live_headword_progress(config, 1) == (0, 2)

    connection = connect(db_path)
    connection.execute(
        """INSERT INTO batch(id,run_id,manifest_sha256,serialized_bytes,article_count,
        unit_count,state,manifest_path) VALUES ('validated',1,'validated',1,1,1,
        'deterministic_validated','m')"""
    )
    connection.execute(
        "INSERT INTO batch_item(batch_id,unit_id,ordinal) VALUES ('validated','u1',0)"
    )
    connection.commit()
    connection.close()
    assert MODULE.live_headword_progress(config, 1) == (1, 2)


def test_progress_tracker_reports_headwords_per_minute():
    tracker = MODULE.ProgressTracker(done=100, sampled_at=10.0)

    report = tracker.sample(current_done=110, total=200, sampled_at=40.0)

    assert report == {
        "event": "progress", "headwords_done": 110,
        "headwords_remaining": 90, "headwords_per_minute": 20.0,
    }


def test_sqlite_retry_retries_only_transient_lock_errors(monkeypatch):
    calls = 0

    def operation():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise sqlite3.OperationalError("database is locked")
        return "done"

    monkeypatch.setattr(MODULE.time, "sleep", lambda _delay: None)
    monkeypatch.setattr(MODULE.random, "uniform", lambda _start, _end: 0)
    assert MODULE.sqlite_retry(operation, attempts=3) == "done"
    assert calls == 3

    with pytest.raises(sqlite3.OperationalError, match="syntax error"):
        MODULE.sqlite_retry(lambda: (_ for _ in ()).throw(
            sqlite3.OperationalError("syntax error")
        ))


def test_interrupted_claim_is_requeued_only_with_its_exact_lease(tmp_path):
    db_path = _progress_database(tmp_path)
    connection = connect(db_path)
    connection.execute(
        """INSERT INTO batch(id,run_id,manifest_sha256,serialized_bytes,article_count,
        unit_count,state,lease_token,manifest_path) VALUES ('b1',1,'m',1,1,0,'leased','lease-1','m')"""
    )
    connection.execute(
        """INSERT INTO attempt(id,batch_id,worker_id,model,prompt_sha256,lease_token,
        request_path,outcome) VALUES ('a1','b1','w','m','p','lease-1','r','claimed')"""
    )
    connection.commit()
    connection.close()

    item = {"attempt_id": "a1", "batch_id": "b1", "lease_token": "wrong"}
    assert not MODULE.interrupt_claim(SimpleNamespace(db_path=db_path), item)

    item["lease_token"] = "lease-1"
    assert MODULE.interrupt_claim(SimpleNamespace(db_path=db_path), item)
    connection = connect(db_path)
    assert tuple(connection.execute(
        "SELECT state,lease_token FROM batch WHERE id='b1'"
    ).fetchone()) == ("ready", None)
    assert connection.execute(
        "SELECT outcome FROM attempt WHERE id='a1'"
    ).fetchone()[0] == "interrupted"
    connection.close()


def test_dispatch_does_not_start_a_child_after_stop(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        '{"batch_id":"b1","manifest_sha256":"m","articles":[]}', encoding="utf-8",
    )
    MODULE.STOP_REQUESTED.set()
    try:
        result = MODULE.dispatch_one({
            "attempt_id": "a1", "batch_id": "b1", "request_path": str(manifest_path),
            "response_path": str(tmp_path / "response.json"), "model_id": "m",
            "reasoning_effort": "medium",
        }, "prompt", "translation")
    finally:
        MODULE.STOP_REQUESTED.clear()

    assert result.interrupted
    assert result.returncode == 130
    assert not MODULE.CHILDREN


def test_stop_terminates_registered_child_process_groups(monkeypatch):
    process = SimpleNamespace(pid=12345, poll=lambda: None)
    signals = []
    MODULE.CHILDREN["a1"] = process
    MODULE.STOP_REQUESTED.clear()
    monkeypatch.setattr(MODULE.os, "killpg", lambda pid, signum: signals.append((pid, signum)))
    try:
        MODULE.request_stop()
    finally:
        MODULE.CHILDREN.clear()
        MODULE.STOP_REQUESTED.clear()

    assert signals == [(12345, MODULE.signal.SIGTERM)]
