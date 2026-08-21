import copy
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

from jitendex_ru.attribution import DICTIONARY_VERSION
from jitendex_ru.yomitan_audit import (
    audit_yomitan_archive, verify_yomitan_visible_latin_approval,
    write_yomitan_visible_latin_approval,
)
from jitendex_ru.yomitan_remediation import (
    FORMS_TOOLTIP_RU,
    PROJECT_URL,
    REDIRECT_RU_PREFIX,
    RELEASE_DOWNLOAD_URL,
    UPDATE_INDEX_URL,
    build_yomitan_index,
    localize_yomitan_rows,
    scan_yomitan_rows,
    validate_yomitan_metadata,
    write_yomitan_update_index,
    yomitan_revision,
)
from jitendex_ru.util import sha256_file


SMOKE_FIXTURE_PATH = Path(__file__).parents[1] / "scripts" / "prepare_yomitan_update_smoke_fixture.py"
SMOKE_FIXTURE_SPEC = importlib.util.spec_from_file_location("yomitan_smoke_fixture", SMOKE_FIXTURE_PATH)
assert SMOKE_FIXTURE_SPEC is not None and SMOKE_FIXTURE_SPEC.loader is not None
SMOKE_FIXTURE = importlib.util.module_from_spec(SMOKE_FIXTURE_SPEC)
SMOKE_FIXTURE_SPEC.loader.exec_module(SMOKE_FIXTURE)


def _row(glossary):
    return ["語", "ご", "", "", 0, glossary, 1, ""]


def test_localizes_every_fixed_v1_shape_without_touching_correct_only_uses():
    rows = [_row([
        ["redirected from 社会情報學"],
        ["redirected from 社會情報學"],
        ["redirected from あ・うん"],
        {"tag": "span", "title": "valid only for these forms and/or readings"},
        {"tag": "span", "lang": "ja", "content": "始める only"},
        {"tag": "span", "lang": "ja", "content": "３０ only"},
        {"tag": "span", "lang": "ja", "content": "Ω only"},
        {"tag": "span", "lang": "ja", "content": "ＡＮＤ only"},
        {"tag": "div", "data": {"content": "graphic-attribution"}, "content": [
            {"tag": "a", "content": "Photo"}, " by ",
            {"tag": "a", "content": "Unknown author"}, " by Unknown author (1909) (",
        ]},
        "read-only member",
        "download-only member",
        "IF-AND-ONLY-IF",
    ])]

    counts = localize_yomitan_rows(rows)

    assert counts == {
        "redirects_localized": 3,
        "tooltips_localized": 1,
        "short_restrictions_localized": 4,
        "graphic_by_localized": 2,
        "graphic_photo_localized": 1,
        "graphic_unknown_author_localized": 2,
    }
    glossary = rows[0][5]
    assert glossary[0][0] == f"{REDIRECT_RU_PREFIX}社会情報學"
    assert glossary[1][0] == f"{REDIRECT_RU_PREFIX}社會情報學"
    assert glossary[2][0] == f"{REDIRECT_RU_PREFIX}あ・うん"
    assert glossary[3]["title"] == FORMS_TOOLTIP_RU
    assert [item["content"] for item in glossary[4:8]] == [
        "только 始める", "только ３０", "только Ω", "только ＡＮＤ",
    ]
    assert all(item["lang"] == "ru" for item in glossary[4:8])
    assert glossary[8]["content"] == [
        {"tag": "a", "content": "Фото"}, " — автор: ",
        {"tag": "a", "content": "неизвестный автор"},
        " — автор: неизвестный автор (1909) (",
    ]
    assert glossary[9:] == ["read-only member", "download-only member", "IF-AND-ONLY-IF"]
    assert localize_yomitan_rows(rows) == {
        "redirects_localized": 0,
        "tooltips_localized": 0,
        "short_restrictions_localized": 0,
        "graphic_by_localized": 0,
        "graphic_photo_localized": 0,
        "graphic_unknown_author_localized": 0,
    }


def test_scanner_rejects_raw_templates_and_adjacent_alphabets_only():
    rows = [_row([
        "redirected from 社会情報學",
        {"title": "valid only for these forms and/or readings"},
        {"lang": "ja", "content": "Ω only"},
        "ошибки гikun и emphатично",
        "сталagmíт",
        "JIT-компилятор; 3D-принтер; USB-концентратор",
    ])]

    scan = scan_yomitan_rows(rows)

    assert scan["issue_counts"] == {
        "raw_redirect_template": 1,
        "raw_forms_tooltip": 1,
        "mixed_alphabet_token": 3,
        "raw_short_restriction": 1,
    }
    assert {issue.get("token") for issue in scan["issues"]} >= {
        "гikun", "emphатично", "сталagmíт",
    }


def test_yomitan_metadata_is_stable_and_foreign_update_fields_are_removed():
    upstream = {
        "title": "Jitendex",
        "revision": "2026.07.09.0",
        "format": 3,
        "sequenced": True,
        "attribution": "Jitendex, JMdict and Tatoeba",
        "url": "https://jitendex.org",
        "isUpdatable": True,
        "indexUrl": "https://jitendex.org/static/yomitan.json",
        "downloadUrl": "https://github.com/stephenmk/x/jitendex-yomitan.zip",
    }
    revision = yomitan_revision("jp-ru-kolobok-400k-v" + DICTIONARY_VERSION)

    index = build_yomitan_index(
        upstream, description="Производный словарь на основе Jitendex.", revision=revision,
    )

    assert index["title"] == "Колобок 400k"
    assert index["url"] == PROJECT_URL
    assert index["attribution"] == upstream["attribution"]
    assert not {"isUpdatable", "indexUrl", "downloadUrl"} & set(index)
    assert upstream["revision"] not in index["revision"]
    validate_yomitan_metadata(index, require_updatable=False)
    broken_title = dict(index, title="Колобок 400k v1.0.1")
    with pytest.raises(ValueError, match="stable"):
        validate_yomitan_metadata(broken_title)


def test_independent_revision_sorts_by_compilation_date():
    older = yomitan_revision("full", compilation_datetime="2026-08-19T01:00:00Z")
    current = yomitan_revision("full", compilation_datetime="2026-08-20T01:00:00Z")
    newer = yomitan_revision("full", compilation_datetime="2026-08-21T01:00:00Z")
    assert older < current < newer
    assert "2026.07.09.0" not in current


def test_owned_update_tuple_is_all_or_nothing():
    index = build_yomitan_index(
        {"format": 3, "attribution": "Jitendex"},
        description="Описание", revision=yomitan_revision("full"), updatable=True,
    )
    assert index["indexUrl"] == UPDATE_INDEX_URL
    assert index["downloadUrl"] == RELEASE_DOWNLOAD_URL
    validate_yomitan_metadata(index, require_updatable=True)

    broken = copy.deepcopy(index)
    broken["downloadUrl"] = "https://jitendex.org/jitendex-yomitan.zip"
    with pytest.raises(ValueError, match="owned release channel|foreign operational"):
        validate_yomitan_metadata(broken)


def test_hosted_index_is_generated_from_archive_metadata(tmp_path):
    archive_path = tmp_path / "dictionary.zip"
    output_path = tmp_path / "yomitan.json"
    archive_index = build_yomitan_index(
        {"format": 3, "attribution": "Jitendex/JMdict/Tatoeba"},
        description="Описание", revision=yomitan_revision("full"),
    )
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("index.json", json.dumps(archive_index))

    hosted = write_yomitan_update_index(archive_path, output_path)

    assert json.loads(output_path.read_text()) == hosted
    assert hosted["title"] == archive_index["title"]
    assert hosted["revision"] == archive_index["revision"]
    assert hosted["isUpdatable"] is True

    updatable_archive = tmp_path / "updatable.zip"
    updatable_index = build_yomitan_index(
        {"format": 3, "attribution": "Jitendex/JMdict/Tatoeba"},
        description="Описание", revision=yomitan_revision("full"), updatable=True,
    )
    with zipfile.ZipFile(updatable_archive, "w") as archive:
        archive.writestr("index.json", json.dumps(updatable_index))
    assert write_yomitan_update_index(updatable_archive, output_path) == updatable_index


def test_local_update_smoke_fixture_keeps_title_and_serves_final_archive(tmp_path):
    final_archive = tmp_path / "jp-ru-kolobok-400k-v1.0.1-yomitan.zip"
    final_index = build_yomitan_index(
        {"format": 3, "attribution": "Jitendex/JMdict/Tatoeba"},
        description="Описание", revision=yomitan_revision("full"), updatable=True,
    )
    with zipfile.ZipFile(final_archive, "w") as archive:
        archive.writestr("index.json", json.dumps(final_index))
        archive.writestr("term_bank_1.json", "[]")

    fixture_dir = tmp_path / "fixture"
    report = SMOKE_FIXTURE.prepare_fixture(final_archive, fixture_dir)

    hosted = json.loads((fixture_dir / "yomitan.json").read_text())
    with zipfile.ZipFile(fixture_dir / report["old_archive"]) as archive:
        old = json.loads(archive.read("index.json"))
        assert archive.read("term_bank_1.json") == b"[]"
    assert old["title"] == hosted["title"] == "Колобок 400k"
    assert old["revision"] == SMOKE_FIXTURE.OLD_REVISION
    assert hosted["revision"] == final_index["revision"]
    assert old["indexUrl"] == f"{SMOKE_FIXTURE.LOCAL_BASE_URL}yomitan.json"
    assert hosted["downloadUrl"].endswith(final_archive.name)
    assert report["final_archive_sha256"] == sha256_file(final_archive)
    assert "jitendex.org" not in json.dumps(hosted).lower()


def test_archive_audit_records_reproducible_locations_and_counts(tmp_path):
    archive_path = tmp_path / "v1.zip"
    index = {"revision": "2026.07.09.0-jp-ru-kolobok-400k-v1.0-tags-ru-v1"}
    rows = [_row(["redirected from 社会情報學", "ошибка гikun"])]
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("index.json", json.dumps(index))
        archive.writestr("term_bank_1.json", json.dumps(rows))

    report = audit_yomitan_archive(archive_path, run_id=59)

    assert report["archive_filename"] == "v1.zip"
    assert report["archive_dictionary_version"] == "1.0"
    assert report["issue_counts"] == {
        "raw_redirect_template": 1,
        "mixed_alphabet_token": 1,
    }
    assert report["mixed_alphabet_findings"][0]["member"] == "term_bank_1.json"


def test_visible_latin_approval_covers_every_review_identity(tmp_path):
    archive_path = tmp_path / "reviewed.zip"
    approval_path = tmp_path / "approval.json"
    rows = [_row([
        {"content": ["JMdict", " | Tatoeba "], "data": {"content": "attribution"}, "tag": "div"},
        {"content": "Португальский: «espada»", "data": {"content": "lang-source-content"}, "tag": "div"},
        {"content": "бренд Windows", "tag": "li"},
    ])]
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("index.json", json.dumps({"revision": "test-v1.0.1"}))
        archive.writestr("term_bank_1.json", json.dumps(rows))

    approval = write_yomitan_visible_latin_approval(archive_path, approval_path)

    assert approval["classification_counts"] == {
        "MUST_TRANSLATE": 0, "MUST_PRESERVE": 3, "REVIEW": 1,
    }
    assert verify_yomitan_visible_latin_approval(
        archive_path, approval_path,
    )["visible_latin_approved"]
