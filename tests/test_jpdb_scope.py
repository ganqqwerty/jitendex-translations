import json
import sqlite3
import zipfile

from jitendex_ru.db import connect, initialize
from jitendex_ru.jpdb_scope import select_top_terms


def test_select_top_terms_matches_expression_and_reading_and_skips_missing(tmp_path):
    db_path = tmp_path / "progress.sqlite3"
    initialize(db_path)
    with connect(db_path) as connection:
        connection.execute(
            "INSERT INTO source_snapshot(kind,version,url,sha256,local_path,extractor_version) VALUES ('jitendex','v','u','h','p','e')"
        )
        snapshot = connection.execute("SELECT id FROM source_snapshot").fetchone()[0]
        for ordinal, (expression, reading) in enumerate((("猫", "ねこ"), ("有る", "ある"), ("犬", "いぬ"))):
            connection.execute(
                """INSERT INTO article(snapshot_id,bank_number,entry_ordinal,expression,reading,sequence,raw_json,source_sha256)
                VALUES (?,?,?,?,?,?,?,?)""",
                (snapshot, 1, ordinal, expression, reading, ordinal, "[]", f"hash-{ordinal}"),
            )
        connection.commit()

    archive = tmp_path / "jpdb.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("term_meta_bank_1.json", json.dumps([
            ["猫", "freq", {"value": 1}],
            ["ある", "freq", {"value": 2}],
            ["不在", "freq", {"value": 3}],
            ["猫", "freq", {"value": 4}],
        ], ensure_ascii=False))

    with connect(db_path) as connection:
        result = select_top_terms(connection, archive, 4)
        assert result["unique_terms"] == 3
        assert result["matched_terms"] == 2
        assert result["skipped_terms"] == 1
        assert result["selected_articles"] == 2
        assert result["expression_matches"] == 1
        assert result["reading_matches"] == 1
        assert connection.execute("SELECT COUNT(*) FROM article WHERE selected=1").fetchone()[0] == 2
