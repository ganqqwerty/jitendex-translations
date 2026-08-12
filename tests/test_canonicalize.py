import json

import pytest

from jitendex_ru.canonicalize import canonicalize_final_run
from jitendex_ru.db import connect, initialize
from jitendex_ru.util import canonical_json, sha256_bytes


def _database(tmp_path, *, approved=True):
    path = tmp_path / "progress.sqlite3"
    initialize(path)
    connection = connect(path)
    connection.execute("INSERT INTO source_snapshot(kind,version,url,sha256,local_path,extractor_version) VALUES ('jitendex','v','u','j','j','e')")
    connection.execute("INSERT INTO source_snapshot(kind,version,url,sha256,local_path,extractor_version) VALUES ('kaishi','v','u','k','k','e')")
    article = [None, None, None, None, None, [{
        "data": {"class": "tag", "content": "part-of-speech-info", "code": "v5b"},
        "content": "5-dan -bu", "title": "Godan verb with 'bu' ending",
    }]]
    raw = canonical_json(article).decode()
    connection.execute("INSERT INTO article(snapshot_id,bank_number,entry_ordinal,expression,reading,sequence,raw_json,source_sha256,selected) VALUES (1,1,0,'語','ご',1,?,?,1)", (raw, sha256_bytes(raw.encode())))
    connection.execute("INSERT INTO run(jitendex_snapshot_id,kaishi_snapshot_id,selection_sha256,extractor_version,prompt_sha256,review_prompt_sha256,terminology_sha256,limits_json) VALUES (1,2,'s','e','p','rp','t','{}')")
    connection.execute("INSERT INTO translation_unit(id,run_id,article_id,json_pointer,role,source_text,source_sha256,byte_count,status) VALUES ('u-1',1,1,'/5/0/content','pos','5-dan -bu','us',9,'translated')")
    connection.execute("INSERT INTO batch(id,run_id,kind,manifest_sha256,serialized_bytes,article_count,unit_count,state,manifest_path) VALUES ('b-1',1,'translation','m',1,1,1,'deterministic_validated',?)", (str(tmp_path / 'manifest.json'),))
    connection.execute("INSERT INTO batch_item(batch_id,unit_id,ordinal) VALUES ('b-1','u-1',0)")
    connection.execute("INSERT INTO attempt(id,batch_id,worker_id,model,prompt_sha256,request_path,outcome) VALUES ('a-1','b-1','w','m','p','r','accepted')")
    target = "вариант"
    connection.execute("INSERT INTO translation(run_id,unit_id,attempt_id,target_text,confidence,target_sha256,accepted) VALUES (1,'u-1','a-1',?,'high',?,1)", (target, sha256_bytes(target.encode())))
    (tmp_path / "manifest.json").write_text(json.dumps({"articles": [{"units": [{"unit_id": "u-1", "required_terminology": {"source": "approved_jitendex_tag_catalog", "category": "part-of-speech-info", "code": "v5b", "target_text": "гл. годан на ぶ"}}]}]}), encoding="utf-8")
    if approved:
        connection.execute("INSERT INTO jitendex_tag(snapshot_id,source_kind,source_key,code,category,label_en,description_en,source_sha256,occurrence_count,label_ru,description_ru,translation_source) VALUES (1,'embedded_tooltip','v5b','v5b','part-of-speech-info','5-dan -bu','Godan verb','ts',1,'гл. годан на ぶ','Глагол годан с окончанием на «ぶ».','approved_workbook')")
    connection.commit()
    return connection


def test_canonicalizes_exact_structured_tag_and_records_immutable_history(tmp_path):
    connection = _database(tmp_path)
    result = canonicalize_final_run(connection, 1)
    connection.commit()
    assert result["changed_units"] == 1
    assert connection.execute("SELECT target_text FROM translation WHERE accepted=1").fetchone()[0] == "гл. годан на ぶ"
    history = connection.execute("SELECT previous_target_text,canonical_target_text,mapping_identity_json FROM translation_canonicalization_history").fetchone()
    assert history[0:2] == ("вариант", "гл. годан на ぶ")
    assert json.loads(history[2]) == {"category": "part-of-speech-info", "code": "v5b", "field": "content"}
    with pytest.raises(Exception, match="immutable"):
        connection.execute("DELETE FROM translation_canonicalization_history")


def test_canonicalizer_is_idempotent(tmp_path):
    connection = _database(tmp_path)
    canonicalize_final_run(connection, 1)
    connection.commit()
    assert canonicalize_final_run(connection, 1)["changed_units"] == 0


def test_missing_approved_structured_tag_fails_without_mutation(tmp_path):
    connection = _database(tmp_path, approved=False)
    with pytest.raises(ValueError, match="missing approved structured tag mapping"):
        canonicalize_final_run(connection, 1)
    assert connection.execute("SELECT target_text FROM translation WHERE accepted=1").fetchone()[0] == "вариант"
    assert connection.execute("SELECT COUNT(*) FROM translation_canonicalization_history").fetchone()[0] == 0
