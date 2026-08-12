import json
import sqlite3
import zipfile

from jitendex_ru.build_dictionary import _frequency_metadata
from jitendex_ru.combined_frequency_scope import (
    EXTERNAL_SOURCES,
    combined_coverage_report,
    select_combined_scope,
)
from jitendex_ru.db import connect, initialize
from jitendex_ru.resolve_selection import selection_manifest_hash


def _frequency_zip(path, rows_by_bank, *, title="Frequency", revision="v1"):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("index.json", json.dumps({"title": title, "revision": revision}))
        for number, rows in enumerate(rows_by_bank, 1):
            archive.writestr(
                f"term_meta_bank_{number}.json",
                json.dumps(rows, ensure_ascii=False),
            )


def _database(tmp_path):
    db_path = tmp_path / "progress.sqlite3"
    initialize(db_path)
    with connect(db_path) as connection:
        connection.execute(
            """INSERT INTO source_snapshot(kind,version,url,sha256,local_path,extractor_version)
            VALUES ('jitendex','v','u','jitendex-hash','source.zip','e')"""
        )
        snapshot = connection.execute("SELECT id FROM source_snapshot").fetchone()[0]
        rows = (
            ("猫", "ねこ"),
            ("有る", "ある"),
            ("ガ", "が"),
            ("犬", "いぬ"),
            ("鳥", "とり"),
            ("外部一", "がいぶいち"),
            ("外部二", "がいぶに"),
            ("外部三", "がいぶさん"),
            ("外部四", "がいぶよん"),
            ("外部五", "がいぶご"),
        )
        for ordinal, (expression, reading) in enumerate(rows):
            connection.execute(
                """INSERT INTO article
                (snapshot_id,bank_number,entry_ordinal,expression,reading,sequence,raw_json,source_sha256,
                 structural_fingerprint)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (snapshot, 1, ordinal, expression, reading, ordinal + 1, "[]", f"hash-{ordinal}", f"fp-{ordinal}"),
            )
        connection.commit()
    return db_path


def test_combined_scope_preserves_ties_and_matches_expressions_readings_and_nfc(tmp_path):
    db_path = _database(tmp_path)
    jpdb = tmp_path / "jpdb.zip"
    _frequency_zip(jpdb, [[
        ["猫", "freq", {"value": 99}],
        ["ある", "freq", {"value": 1}],
        ["不存在", "freq", {"value": 2}],
        ["範囲外", "freq", {"value": 3}],
    ]], title="JPDB")
    external_paths = {}
    source_terms = {
        "aozora_bunko": [[
            ["猫", "freq", {"value": 1}],
            ["カ\u3099", "freq", {"frequency": 2}],
            ["犬", "freq", {"value": 4}],
        ], [
            ["鳥", "freq", {"value": 4}],
            ["猫", "freq", {"value": 4}],
            ["範囲外", "freq", {"value": 5}],
        ]],
        "bccwj": [[["外部一", "freq", 1]]],
        "cc100": [[["外部二", "freq", {"frequency": 1}]]],
        "monodicts_206k": [[["外部三", "freq", {"value": 1}]]],
        "wikipedia_v2": [[["外部四", "freq", 1]]],
        "kokugo_jiten": [[["外部五", "freq", 1]]],
    }
    for source in EXTERNAL_SOURCES:
        path = tmp_path / f"{source}.zip"
        _frequency_zip(path, source_terms[source], title=source)
        external_paths[source] = path

    with connect(db_path) as connection:
        result = select_combined_scope(connection, jpdb, 3, external_paths, 4)
        assert result["sources"][0]["unique_terms"] == 3
        aozora = next(item for item in result["sources"] if item["source"] == "aozora_bunko")
        assert aozora["unique_terms"] == 4
        assert aozora["matched_terms"] == 4
        assert result["selected_articles"] == 10
        tied = connection.execute(
            """SELECT rank,term FROM frequency_term
            WHERE source='aozora_bunko' AND rank=4 ORDER BY term"""
        ).fetchall()
        assert [(row["rank"], row["term"]) for row in tied] == [(4, "犬"), (4, "鳥")]
        assert connection.execute(
            "SELECT match_kind FROM frequency_article WHERE source='jpdb' AND term='ある'"
        ).fetchone()[0] == "reading"
        assert connection.execute(
            "SELECT match_kind FROM frequency_article WHERE source='aozora_bunko' AND term='ガ'"
        ).fetchone()[0] == "expression"
        first_hash = selection_manifest_hash(connection)
        connection.execute("UPDATE frequency_source SET rank_limit=5 WHERE source='aozora_bunko'")
        assert selection_manifest_hash(connection) != first_hash


def test_combined_coverage_and_metadata_use_the_selected_scope(tmp_path):
    db_path = _database(tmp_path)
    jpdb = tmp_path / "jpdb.zip"
    _frequency_zip(jpdb, [[["猫", "freq", 1], ["不存在", "freq", 2]]], title="JPDB")
    external_paths = {}
    for index, source in enumerate(EXTERNAL_SOURCES):
        path = tmp_path / f"{source}.zip"
        _frequency_zip(path, [[[f"外部{'一二三四五一'[index]}", "freq", 1]]], title=source)
        external_paths[source] = path

    with connect(db_path) as connection:
        select_combined_scope(connection, jpdb, 2, external_paths, 40_000)
        connection.execute(
            """INSERT INTO source_snapshot(kind,version,url,sha256,local_path,extractor_version)
            VALUES ('kaishi','v','u','kaishi-hash','kaishi.apkg','e')"""
        )
        connection.execute(
            """INSERT INTO run
            (jitendex_snapshot_id,kaishi_snapshot_id,selection_sha256,extractor_version,prompt_sha256,
             review_prompt_sha256,terminology_sha256,limits_json)
            VALUES (1,2,'selection','e','p','rp','t','{}')"""
        )
        selected = connection.execute(
            "SELECT id,structural_fingerprint FROM article WHERE selected=1 ORDER BY id"
        ).fetchall()
        connection.executemany(
            "INSERT INTO run_article(run_id,article_id,structural_fingerprint) VALUES (1,?,?)",
            ((row["id"], row["structural_fingerprint"]) for row in selected),
        )
        report = combined_coverage_report(connection, 1)
        assert report["complete"]
        assert report["missing_mapped_articles"] == 0
        assert report["fully_accepted_articles"] == report["selected_articles"]
        title, suffix, description = _frequency_metadata(connection, 1)
        assert title == "Jitendex JPDB 2 + frequency-six top40k — русский"
        assert suffix == "jpdb-2-freq6-40k-ru"
        assert "40,000" in description
        connection.execute("DELETE FROM run_article WHERE run_id=1 AND article_id=?", (selected[0]["id"],))
        assert not combined_coverage_report(connection, 1)["complete"]


def test_schema_v6_frequency_rows_migrate_without_losing_term_identity(tmp_path):
    db_path = tmp_path / "progress.sqlite3"
    initialize(db_path)
    with connect(db_path) as connection:
        connection.execute(
            """INSERT INTO source_snapshot(kind,version,url,sha256,local_path,extractor_version)
            VALUES ('jitendex','v','u','j','source.zip','e')"""
        )
        connection.execute(
            """INSERT INTO article
            (id,snapshot_id,bank_number,entry_ordinal,expression,reading,sequence,raw_json,source_sha256)
            VALUES (42,1,1,1,'猫','ねこ',1,'[]','article-hash')"""
        )
        connection.execute("DROP TABLE frequency_article")
        connection.execute("DROP TABLE frequency_term")
        connection.execute(
            """CREATE TABLE frequency_term(
            source TEXT NOT NULL,source_sha256 TEXT NOT NULL,rank INTEGER NOT NULL,term TEXT NOT NULL,
            matched INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(source,source_sha256,rank),
            UNIQUE(source,source_sha256,term))"""
        )
        connection.execute(
            """CREATE TABLE frequency_article(
            source TEXT NOT NULL,source_sha256 TEXT NOT NULL,rank INTEGER NOT NULL,article_id INTEGER NOT NULL,
            match_kind TEXT NOT NULL,PRIMARY KEY(source,source_sha256,rank,article_id))"""
        )
        connection.execute("INSERT INTO frequency_term VALUES ('jpdb','hash',1,'猫',1)")
        connection.execute("INSERT INTO frequency_article VALUES ('jpdb','hash',1,42,'expression')")
        connection.commit()

    initialize(db_path)

    with sqlite3.connect(db_path) as connection:
        columns = [row[1] for row in connection.execute("PRAGMA table_info(frequency_article)")]
        assert "term" in columns
        assert connection.execute(
            "SELECT source,source_sha256,rank,term,article_id,match_kind FROM frequency_article"
        ).fetchone() == ("jpdb", "hash", 1, "猫", 42, "expression")
