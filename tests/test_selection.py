import json

from jitendex_ru.db import connect, initialize
from jitendex_ru.resolve_selection import generate_candidates


def add_article(connection, ordinal, expression, reading, sequence):
    row = [expression, reading, "", "", 0, [], sequence, ""]
    connection.execute(
        "INSERT INTO article(snapshot_id,bank_number,entry_ordinal,expression,reading,sequence,raw_json,source_sha256) VALUES (1,1,?,?,?,?,?,?)",
        (ordinal, expression, reading, sequence, json.dumps(row), f"h{ordinal}"),
    )


def test_unique_sequence_auto_resolves_and_homophone_does_not(tmp_path):
    path = tmp_path / "db.sqlite3"
    initialize(path)
    connection = connect(path)
    connection.execute("INSERT INTO source_snapshot(kind,version,url,sha256,local_path,extractor_version) VALUES ('jitendex','v','u','j','p','e')")
    connection.execute("INSERT INTO source_snapshot(kind,version,url,sha256,local_path,extractor_version) VALUES ('kaishi','v','u','k','p','e')")
    add_article(connection, 0, "下さい", "ください", 10)
    add_article(connection, 1, "下る", "くださる", 20)
    connection.execute("INSERT INTO kaishi_note(snapshot_id,note_id,word,reading,meaning_en,sentence_ja,sentence_en,source_sha256) VALUES (2,1,'ください','ください','please','','','n1')")
    result = generate_candidates(connection)
    assert result["auto_resolved"] == 1
    assert connection.execute("SELECT sequence FROM selection_decision WHERE decision='included'").fetchone()[0] == 10
    assert connection.execute("SELECT COUNT(*) FROM article WHERE selected=1").fetchone()[0] == 1
