import json
import zipfile
from io import BytesIO

import pytest
from PIL import Image

from jitendex_ru.batch import claim, make_batches
from jitendex_ru.apply_translations import _compose_glossary, _localize_mixed_form_restrictions
from jitendex_ru.build_dictionary import _chunk, build, record_yomitan_smoke, verify
from jitendex_ru.db import connect, initialize
from jitendex_ru.extract_units import extract_selected
from jitendex_ru.goldendict import BASENAME as GOLDENDICT_BASENAME, build_goldendict, verify_goldendict
from jitendex_ru.review import apply_adjudication, _review_manifest, _split_review_envelope, ingest_review, make_review_batches
from jitendex_ru.util import canonical_json, sha256_bytes
from jitendex_ru.validate_response import ingest_response


def test_review_envelope_is_split_at_unit_and_byte_limits():
    envelope = {
        "article_id": "a-1",
        "source_sha256": "source",
        "term": "語",
        "reading": "ご",
        "sequence": 1,
        "kaishi_evidence": [],
        "read_only_context": {},
        "units": [
            {
                "unit_id": f"u-{index}",
                "source_sha256": f"hash-{index}",
                "role": "glossary",
                "source_text": "source",
                "protected_tokens": [],
                "local_context": "glossary",
                "candidate_target": "перевод " * 8,
                "candidate_confidence": "high",
                "candidate_review_reason": None,
            }
            for index in range(5)
        ],
    }

    by_units = _split_review_envelope(envelope, max_bytes=49152, max_units=2)
    assert [len(segment["units"]) for segment in by_units] == [2, 2, 1]
    byte_limit = len(_review_manifest("rb-" + "0" * 24, [by_units[0]])[1]) - 1
    by_bytes = _split_review_envelope(envelope, max_bytes=byte_limit, max_units=10)
    assert len(by_bytes) > 1
    assert [unit["unit_id"] for segment in by_bytes for unit in segment["units"]] == [
        unit["unit_id"] for unit in envelope["units"]
    ]


def test_lexicographer_composes_a_different_number_of_russian_definitions():
    source = [
        {"tag": "li", "lang": "en", "content": "to begin"},
        {"tag": "li", "lang": "en", "content": "to start"},
        {"tag": "li", "lang": "en", "content": "to commence"},
    ]
    result = _compose_glossary(source, canonical_json(["начинать", "приступать к"]).decode(), "/glossary")
    assert [item["content"] for item in result] == ["начинать", "приступать к"]
    assert all(item["lang"] == "ru" for item in result)
    scalar_wrapper = {"tag": "li", "content": "to begin"}
    expanded = _compose_glossary(scalar_wrapper, canonical_json(["начинать", "приступать к"]).decode(), "/glossary")
    assert [item["content"] for item in expanded] == ["начинать", "приступать к"]


def test_mixed_japanese_form_restrictions_are_localized():
    article = {
        "content": [
            {"tag": "span", "lang": "ja", "content": "始める only"},
            {"tag": "span", "lang": "ja", "content": "始める"},
        ]
    }
    _localize_mixed_form_restrictions(article)
    assert article["content"][0] == {"tag": "span", "lang": "ru", "content": "только 始める"}
    assert article["content"][1] == {"tag": "span", "lang": "ja", "content": "始める"}


def test_term_bank_chunking_uses_exact_serialized_byte_boundary():
    rows = [["x" * size] for size in (5, 7, 9, 11, 13)]
    max_bytes = len(canonical_json(rows[:2]))

    chunks = _chunk(rows, max_bytes=max_bytes)

    assert chunks[0] == rows[:2]
    assert [row for chunk in chunks for row in chunk] == rows
    assert all(len(canonical_json(chunk)) <= max_bytes or len(chunk) == 1 for chunk in chunks)


def test_scalar_application_preserves_source_whitespace():
    from jitendex_ru.apply_translations import _scalar_source_and_target

    original, translated = _scalar_source_and_target(" as in 牡 ", "as in 牡", "как в 牡")

    assert original == " as in 牡 "
    assert translated == " как в 牡 "


def test_translation_review_and_reproducible_build(tmp_path):
    source_zip = tmp_path / "source.zip"
    source_article = [
        "食べる", "たべる", "", "v1", 0,
        {"type": "structured-content", "content": {"tag": "div", "content": [
            {"tag": "span", "lang": "en", "data": {"content": "glossary"}, "content": "to eat"},
            {"tag": "img", "path": "jitendex/graphics/example.avif", "width": 2, "height": 2, "sizeUnits": "px"},
        ]}},
        42, "★",
    ]
    image_data = BytesIO()
    Image.new("RGB", (2, 2), (210, 40, 30)).save(image_data, format="AVIF", quality=100)
    with zipfile.ZipFile(source_zip, "w") as archive:
        archive.writestr("index.json", json.dumps({"title": "Jitendex", "revision": "v", "format": 3}))
        archive.writestr("styles.css", "span {}")
        archive.writestr("tag_bank_1.json", json.dumps([["★", "popular", 2, "high priority entry", 2]]))
        archive.writestr("jitendex/graphics/example.avif", image_data.getvalue())

    db_path = tmp_path / "progress.sqlite3"
    initialize(db_path)
    connection = connect(db_path)
    connection.execute(
        "INSERT INTO source_snapshot(kind,version,url,sha256,local_path,extractor_version) VALUES ('jitendex','v','u','j',?,'e')",
        (str(source_zip),),
    )
    connection.execute(
        "INSERT INTO source_snapshot(kind,version,url,sha256,local_path,extractor_version) VALUES ('kaishi','v','u','k','k','e')"
    )
    connection.execute(
        """INSERT INTO jitendex_tag(
          snapshot_id,source_kind,source_key,code,category,label_en,description_en,
          source_sha256,occurrence_count,label_ru,description_ru,confidence,
          translation_source,translation_source_sha256,translation_source_path
        ) VALUES (1,'tag_bank','tag_bank_1.json:0','★','popular','★','high priority entry',
          'tag-source',1,'★','Запись с высоким приоритетом','high',
          'approved_workbook','catalog-hash','/approved.csv')"""
    )
    raw = canonical_json(source_article).decode()
    connection.execute(
        """INSERT INTO article(snapshot_id,bank_number,entry_ordinal,expression,reading,sequence,raw_json,source_sha256,selected)
        VALUES (1,1,0,'食べる','たべる',42,?,?,1)""", (raw, sha256_bytes(raw.encode())),
    )
    connection.execute(
        "INSERT INTO run(jitendex_snapshot_id,kaishi_snapshot_id,selection_sha256,extractor_version,prompt_sha256,review_prompt_sha256,terminology_sha256,limits_json) VALUES (1,2,'s','e','p','rp','t','{}')"
    )
    extract_selected(connection, 1)
    untranslated = canonical_json(["月", "つき", "", "", 0, [], 43, ""]).decode()
    connection.execute(
        """INSERT INTO article(snapshot_id,bank_number,entry_ordinal,expression,reading,
        sequence,raw_json,source_sha256,selected) VALUES (1,1,1,'月','つき',43,?,?,1)""",
        (untranslated, sha256_bytes(untranslated.encode())),
    )
    made = make_batches(connection, 1, tmp_path / "inbox", {}, 12, 49152, 200, 16384)
    assert made["batches_created"] == 1
    assert made["phase_metrics"]["article_loading"]["output_rows"] == 1
    connection.commit()

    task = claim(
        connection, "translator", tmp_path / "outbox", run_id=1, kind="translation",
        model_id="gpt-5.6-luna", reasoning_effort="medium", transport="codex-agent",
    )
    manifest = json.loads(open(task["request_path"], encoding="utf-8").read())
    unit = manifest["articles"][0]["units"][0]
    response = {
        "schema_version": 1, "batch_id": task["batch_id"], "manifest_sha256": manifest["manifest_sha256"],
        "translations": [{"unit_id": unit["unit_id"], "source_sha256": unit["source_sha256"],
                          "target_text": "есть", "confidence": "high", "review_reason": None}],
    }
    response_path = tmp_path / "outbox" / f"{task['attempt_id']}.json"
    response_path.write_text(json.dumps(response), encoding="utf-8")
    ingest_response(connection, response_path)
    make_review_batches(connection, 1, tmp_path / "review-inbox")
    connection.commit()

    review_task = claim(
        connection, "reviewer", tmp_path / "review-outbox", run_id=1, kind="review",
        model_id="gpt-5.6-terra", reasoning_effort="medium", transport="codex-agent",
    )
    review_manifest = json.loads(open(review_task["request_path"], encoding="utf-8").read())
    review_response = {
        "schema_version": 1, "batch_id": review_task["batch_id"], "manifest_sha256": review_manifest["manifest_sha256"],
        "reviews": [{"unit_id": unit["unit_id"], "source_sha256": unit["source_sha256"], "decision": "needs_adjudication",
                     "replacement_target": None, "reason": "conflicting evidence"}],
    }
    review_path = tmp_path / "review-outbox" / f"{review_task['attempt_id']}.json"
    review_path.write_text(json.dumps(review_response), encoding="utf-8")
    ingest_review(connection, review_path)
    adjudication_path = tmp_path / "review-outbox" / "adjudication.json"
    adjudication_path.write_text(json.dumps({
        "batch_id": review_task["batch_id"], "unit_id": unit["unit_id"],
        "decision": "accept_candidate", "target_text": "есть", "reason": "Japanese evidence controls",
    }), encoding="utf-8")
    result = apply_adjudication(connection, adjudication_path, "terra-adjudicator-test")
    assert result["decision"] == "accept"
    assert connection.execute("SELECT COUNT(*) FROM review WHERE decision='needs_adjudication'").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM validation_issue WHERE resolved_at IS NULL").fetchone()[0] == 0

    first = tmp_path / "one.zip"
    second = tmp_path / "two.zip"
    first_result = build(connection, 1, first)
    second_result = build(connection, 1, second)
    assert first_result["zip_sha256"] == second_result["zip_sha256"]
    assert verify(connection, first)["verified"]
    with zipfile.ZipFile(first) as archive:
        index = json.loads(archive.read("index.json"))
        assert index["title"].startswith("Колобок 400k v1.0")
        assert index["author"] == "Stephen Kraus; Yuri Katkov"
        assert "jp-ru-kolobok-400k" in index["revision"]
        emitted = json.loads(archive.read("term_bank_1.json"))[0]
        assert emitted[5]["content"]["content"][0]["content"] == "есть"
        assert emitted[5]["content"]["content"][0]["lang"] == "ru"
        assert json.loads(archive.read("tag_bank_1.json"))[0] == [
            "★", "popular", 2, "Запись с высоким приоритетом", 2,
        ]
    golden_one = tmp_path / "golden-one.zip"
    golden_two = tmp_path / "golden-two.zip"
    golden_result = build_goldendict(connection, 1, golden_one)
    assert golden_result["converted_images"] == 1
    assert golden_result["tag_bank_references_replaced"] == 1
    golden_audit = json.loads(connection.execute(
        "SELECT details_json FROM audit_event WHERE event_type='goldendict_build' AND entity_id=?",
        (str(golden_result["export_id"]),),
    ).fetchone()[0])
    assert golden_audit["tag_catalog_version"] == "tags-ru-v1"
    assert golden_audit["tag_bank_references_replaced"] == 1
    assert golden_result["zip_sha256"] == build_goldendict(connection, 1, golden_two)["zip_sha256"]
    assert verify_goldendict(connection, golden_one)["verified"]
    with zipfile.ZipFile(golden_one) as archive:
        assert {
            f"{GOLDENDICT_BASENAME}.ifo", f"{GOLDENDICT_BASENAME}.idx",
            f"{GOLDENDICT_BASENAME}.dict", f"{GOLDENDICT_BASENAME}.syn",
            f"res/{GOLDENDICT_BASENAME}.css",
        } <= set(archive.namelist())
        ifo = archive.read(f"{GOLDENDICT_BASENAME}.ifo").decode()
        assert "bookname=Колобок 400k v1.0" in ifo
        assert "dictionaryversion=1.0" in ifo
        assert "author=Stephen Kraus; Yuri Katkov" in ifo
        golden_article = archive.read(f"{GOLDENDICT_BASENAME}.dict").decode()
        assert "есть" in golden_article
        assert '<span class="jr-tag" title="Запись с высоким приоритетом">★</span>' in golden_article
        assert 'data-rules="v1" data-score="0" data-sequence="42"' in golden_article
        assert 'src="jitendex/graphics/example.png"' in golden_article
        assert "res/jitendex/graphics/example.png" in archive.namelist()
        assert not any(name.endswith(".avif") for name in archive.namelist())
        with Image.open(BytesIO(archive.read("res/jitendex/graphics/example.png"))) as converted:
            assert converted.format == "PNG"
            assert converted.size == (2, 2)
        assert "たべる" in archive.read(f"{GOLDENDICT_BASENAME}.syn").decode(errors="ignore")
        assert "span {}" in archive.read(f"res/{GOLDENDICT_BASENAME}.css").decode()
    smoke_path = tmp_path / "smoke.json"
    smoke_path.write_text(json.dumps({
        "schema_version": 1, "zip_sha256": first_result["zip_sha256"],
        "clean_profile": True, "imported": True,
        "checks": {key: True for key in (
            "expression_lookup", "reading_lookup", "inflected_lookup", "kana_only_lookup",
            "multiple_readings", "xrefs", "ruby", "examples", "tables", "links", "long_entry",
        )},
        "notes": "manual clean-profile smoke passed",
    }), encoding="utf-8")
    assert record_yomitan_smoke(connection, smoke_path, "human-test")["recorded"]
    assert connection.execute("SELECT state FROM run WHERE id=1").fetchone()[0] == "complete"
    connection.execute("UPDATE translation SET target_text='подмена' WHERE accepted=1")
    with pytest.raises(ValueError, match="accepted target hash changed"):
        build(connection, 1, tmp_path / "tampered.zip")
