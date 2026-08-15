from jitendex_ru.all_article_scope import select_all_article_scope
from jitendex_ru.build_dictionary import _frequency_metadata
from jitendex_ru.db import connect, initialize


def _database(tmp_path):
    path = tmp_path / "progress.sqlite3"
    initialize(path)
    connection = connect(path)
    connection.execute("INSERT INTO source_snapshot(kind,version,url,sha256,local_path,extractor_version) VALUES ('jitendex','v','u','j','j','e')")
    connection.execute("INSERT INTO source_snapshot(kind,version,url,sha256,local_path,extractor_version) VALUES ('kaishi','v','u','k','k','e')")
    for index in range(5):
        connection.execute("INSERT INTO article(snapshot_id,bank_number,entry_ordinal,expression,reading,sequence,raw_json,source_sha256,selected,structural_fingerprint) VALUES (1,?,?,?, ?,?,?,?,0,'f')", (2 if index < 2 else 1, index, f'e{index}', f'r{index}', index, '[]', f'h{index}'))
    connection.execute("INSERT INTO run(jitendex_snapshot_id,kaishi_snapshot_id,selection_sha256,extractor_version,prompt_sha256,review_prompt_sha256,terminology_sha256,limits_json) VALUES (1,2,'s','e','p','rp','t','{}')")
    connection.execute("INSERT INTO run_article(run_id,article_id,structural_fingerprint) VALUES (1,1,'f')")
    connection.execute("INSERT INTO run_article(run_id,article_id,structural_fingerprint) VALUES (1,3,'f')")
    connection.commit()
    return connection


def test_all_article_scope_carries_source_and_adds_source_order(tmp_path):
    connection = _database(tmp_path)
    result = select_all_article_scope(connection, 1, 2)
    assert result == {"source_run_id": 1, "source_articles": 2, "articles_added": 2, "selected_articles": 4, "total_articles": 5, "remaining_articles": 1, "complete": False}
    assert [row[0] for row in connection.execute("SELECT id FROM article WHERE selected=1 ORDER BY id")] == [1, 3, 4, 5]


def test_all_article_scope_caps_final_increment_and_metadata(tmp_path):
    connection = _database(tmp_path)
    result = select_all_article_scope(connection, 1, 10)
    assert result["articles_added"] == 3
    assert result["complete"] is True
    connection.execute("INSERT INTO run(jitendex_snapshot_id,kaishi_snapshot_id,selection_sha256,extractor_version,prompt_sha256,review_prompt_sha256,terminology_sha256,limits_json) VALUES (1,2,'all','e','p','rp','t','{}')")
    connection.execute("INSERT INTO run_article(run_id,article_id,structural_fingerprint) SELECT 2,id,'f' FROM article")
    assert _frequency_metadata(connection, 2)[0] == "Колобок 400k v1.0"
