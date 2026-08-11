import json
import zipfile

import pytest

from jitendex_ru.db import connect, initialize
from jitendex_ru.jitendex_tags import (
    import_jitendex_tags,
    ingest_approved_tag_rows,
    ingest_tag_translations,
    translated_tag_notes,
)


def _database(tmp_path):
    path = tmp_path / "progress.sqlite3"
    initialize(path)
    connection = connect(path)
    connection.execute(
        """INSERT INTO source_snapshot(kind,version,url,sha256,local_path,extractor_version)
        VALUES ('jitendex','v','u','hash','source.zip','extractor')"""
    )
    return connection


def _archive(tmp_path):
    path = tmp_path / "source.zip"
    tag = {"tag": "span", "title": "noun (common) (futsuumeishi)",
           "data": {"class": "tag", "code": "n", "content": "part-of-speech-info"},
           "content": "noun"}
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("term_bank_1.json", json.dumps([["語", "ご", "", "", 0, [tag, tag], 1, ""]]))
        archive.writestr("tag_bank_1.json", json.dumps([["★", "popular", 2, "high priority entry", 2]]))
    return path


def test_imports_embedded_and_yomitan_tag_banks_idempotently(tmp_path):
    connection = _database(tmp_path)
    result = import_jitendex_tags(connection, 1, _archive(tmp_path))
    assert result == {"jitendex_tags": 2, "embedded_tooltips": 1, "tag_bank_tags": 1}
    assert [tuple(row) for row in connection.execute(
        "SELECT source_kind,code,label_en,description_en,occurrence_count FROM jitendex_tag ORDER BY source_kind"
    )] == [
        ("embedded_tooltip", "n", "noun", "noun (common) (futsuumeishi)", 2),
        ("tag_bank", "★", "★", "high priority entry", 1),
    ]
    import_jitendex_tags(connection, 1, _archive(tmp_path))
    assert connection.execute("SELECT COUNT(*) FROM jitendex_tag").fetchone()[0] == 2


def test_ingests_exact_ordered_luna_results_and_exposes_tag_bank_notes(tmp_path):
    connection = _database(tmp_path)
    import_jitendex_tags(connection, 1, _archive(tmp_path))
    rows = connection.execute("SELECT * FROM jitendex_tag ORDER BY id").fetchall()
    payload = {"schema_version": 1, "batch_id": "tags-1", "translations": [
        {"tag_id": rows[0]["id"], "source_sha256": rows[0]["source_sha256"],
         "label_ru": "сущ.", "tooltip_description_ru": "имя существительное (обычное)",
         "confidence": "high", "review_reason": None},
        {"tag_id": rows[1]["id"], "source_sha256": rows[1]["source_sha256"],
         "label_ru": "★", "tooltip_description_ru": "высокоприоритетная словарная статья",
         "confidence": "high", "review_reason": None},
    ]}
    assert ingest_tag_translations(
        connection, payload, rows, model="gpt-5.6-luna", reasoning_effort="medium", prompt_sha256="p",
    ) == 2
    assert translated_tag_notes(connection, 1) == {
        "high priority entry": "высокоприоритетная словарная статья",
    }
    bad = {**payload, "translations": list(reversed(payload["translations"]))}
    with pytest.raises(ValueError, match="order"):
        ingest_tag_translations(
            connection, bad, rows, model="gpt-5.6-luna", reasoning_effort="medium", prompt_sha256="p",
        )


def test_approved_catalog_replaces_luna_with_history_and_blocks_model_overwrite(tmp_path):
    connection = _database(tmp_path)
    import_jitendex_tags(connection, 1, _archive(tmp_path))
    database_rows = connection.execute("SELECT * FROM jitendex_tag ORDER BY id").fetchall()
    approved = [{
        "source_kind": row["source_kind"], "category": row["category"],
        "code": row["code"] or None, "label_en": row["label_en"],
        "description_en": row["description_en"], "occurrence_count": row["occurrence_count"],
        "label_ru": "сущ." if row["code"] == "n" else "★",
        "description_ru": (
            "Нарицательное существительное" if row["code"] == "n"
            else "Запись с высоким приоритетом"
        ),
        "confidence": "high", "review_reason": None,
    } for row in database_rows]
    result = ingest_approved_tag_rows(
        connection, 1, approved, source_path="/approved.xlsx", source_sha256="workbook-hash",
    )
    assert result["rows_reconciled"] == 2
    assert result["rows_replaced"] == 2
    assert connection.execute(
        "SELECT COUNT(*) FROM jitendex_tag_translation_history"
    ).fetchone()[0] == 2
    row = connection.execute("SELECT * FROM jitendex_tag WHERE code='n'").fetchone()
    assert row["translation_source"] == "approved_workbook"
    assert row["translation_source_sha256"] == "workbook-hash"
    payload = {"schema_version": 1, "batch_id": "tags-1", "translations": [{
        "tag_id": row["id"], "source_sha256": row["source_sha256"],
        "label_ru": "сущ.", "tooltip_description_ru": "Нарицательное существительное",
        "confidence": "high", "review_reason": None,
    }]}
    with pytest.raises(ValueError, match="approved workbook"):
        ingest_tag_translations(
            connection, payload, [row], model="gpt-5.6-luna",
            reasoning_effort="medium", prompt_sha256="new-prompt",
        )
