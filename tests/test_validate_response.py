import json

from jitendex_ru.db import connect, initialize
from jitendex_ru.validate_response import validate_worker_payload


def fixture_db(tmp_path):
    path = tmp_path / "db.sqlite3"
    initialize(path)
    connection = connect(path)
    connection.execute("INSERT INTO source_snapshot(kind,version,url,sha256,local_path,extractor_version) VALUES ('jitendex','v','u','h','p','e')")
    connection.execute("INSERT INTO source_snapshot(kind,version,url,sha256,local_path,extractor_version) VALUES ('kaishi','v','u','k','p','e')")
    connection.execute("INSERT INTO run(jitendex_snapshot_id,kaishi_snapshot_id,selection_sha256,extractor_version,prompt_sha256,review_prompt_sha256,terminology_sha256,limits_json) VALUES (1,2,?,?,?,?,?,?)", ("s", "e", "p", "rp", "t", "{}"))
    row = json.dumps(["x", "x", "", "", 0, [], 1, ""])
    connection.execute("INSERT INTO article(snapshot_id,bank_number,entry_ordinal,expression,reading,sequence,raw_json,source_sha256,selected) VALUES (1,1,0,'x','x',1,?,'a',1)", (row,))
    connection.execute("INSERT INTO translation_unit(id,run_id,article_id,json_pointer,role,source_text,source_sha256,protected_tokens_json,byte_count) VALUES ('u1',1,1,'/5/0','glossary','Hello JMdict','sh','[\"JMdict\"]',12)")
    connection.execute("INSERT INTO batch(id,run_id,manifest_sha256,serialized_bytes,article_count,unit_count,manifest_path) VALUES ('b1',1,?,1,1,1,'m')", ("f" * 64,))
    connection.execute("INSERT INTO batch_item VALUES ('b1','u1',0)")
    connection.execute("INSERT INTO attempt(id,batch_id,worker_id,model,prompt_sha256,request_path,response_path) VALUES ('a1','b1','w','m','p','m','o')")
    connection.commit()
    return connection, connection.execute("SELECT * FROM attempt WHERE id='a1'").fetchone()


def test_valid_response(tmp_path):
    connection, attempt = fixture_db(tmp_path)
    payload = {"schema_version": 1, "batch_id": "b1", "manifest_sha256": "f" * 64, "translations": [
        {"unit_id": "u1", "source_sha256": "sh", "target_text": "привет JMdict", "confidence": "high", "review_reason": None}
    ]}
    assert validate_worker_payload(connection, attempt, payload) == []


def test_rejects_order_markup_and_lost_token(tmp_path):
    connection, attempt = fixture_db(tmp_path)
    payload = {"schema_version": 1, "batch_id": "b1", "manifest_sha256": "f" * 64, "translations": [
        {"unit_id": "u1", "source_sha256": "sh", "target_text": "<b>перевод</b>", "confidence": "high", "review_reason": None}
    ]}
    codes = {issue["code"] for issue in validate_worker_payload(connection, attempt, payload)}
    assert {"markup_detected", "protected_token_missing"} <= codes


def test_allows_parenthesized_scientific_taxon(tmp_path):
    connection, attempt = fixture_db(tmp_path)
    connection.execute("UPDATE translation_unit SET protected_tokens_json='[]' WHERE id='u1'")
    payload = {"schema_version": 1, "batch_id": "b1", "manifest_sha256": "f" * 64, "translations": [
        {"unit_id": "u1", "source_sha256": "sh", "target_text": "собака (Canis lupus familiaris)", "confidence": "high", "review_reason": None}
    ]}
    assert validate_worker_payload(connection, attempt, payload) == []


def test_lexicographer_accepts_variable_length_glossary_but_rejects_duplicates(tmp_path):
    connection, attempt = fixture_db(tmp_path)
    connection.execute("UPDATE run SET pipeline_version='lexicographer-v2' WHERE id=1")
    connection.execute("UPDATE translation_unit SET role='glossary_set',protected_tokens_json='[]' WHERE id='u1'")
    payload = {"schema_version": 2, "batch_id": "b1", "manifest_sha256": "f" * 64, "translations": [
        {"unit_id": "u1", "source_sha256": "sh", "target_text": ["начинать", "приступать к"], "confidence": "high", "review_reason": None}
    ]}
    assert validate_worker_payload(connection, attempt, payload) == []
    payload["translations"][0]["target_text"] = ["начинать", "начинать"]
    assert "duplicate_glossary_definition" in {issue["code"] for issue in validate_worker_payload(connection, attempt, payload)}
