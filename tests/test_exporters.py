from __future__ import annotations

import json
import zipfile
from io import BytesIO
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

import pytest
from mdict_utils import reader as mdict_reader
from mdict_utils import writer as mdict_writer
from PIL import Image

import jitendex_ru.apple_dictionary as apple_module
import jitendex_ru.mdict as mdict_module
import jitendex_ru.pocketbook as pocketbook_module
from jitendex_ru.apple_dictionary import (
    BASENAME as APPLE_BASENAME,
)
from jitendex_ru.apple_dictionary import (
    _compile as compile_apple,
)
from jitendex_ru.apple_dictionary import (
    render_apple_project,
    verify_apple_source_xml,
)
from jitendex_ru.export_model import (
    ExportCorpus,
    ExportResource,
    entries_from_rows,
    safe_resource_path,
)
from jitendex_ru.export_render import LossLedger, require_xml_text
from jitendex_ru.mdict import (
    _independent_header,
    _mdd_records,
    _write_mdict,
    render_mdict_source,
)
from jitendex_ru.pocketbook import (
    _compile as compile_pocketbook,
)
from jitendex_ru.pocketbook import (
    render_pocketbook_xdxf,
)
from jitendex_ru.util import sha256_file

PROBE_PATH = Path(__file__).parents[1] / "probes" / "exporters" / "common-probe.json"


class _Cursor:
    def __init__(self, row=None):
        self.row = row
        self.rowcount = 1

    def fetchone(self):
        return self.row

    def fetchall(self):
        return []

    def __iter__(self):
        return iter(())


class _ExportConnection:
    backend = "sqlite"

    def __init__(self):
        self.files = []
        self.verified = False

    def execute(self, sql, parameters=()):
        if "INSERT INTO export(" in sql:
            return _Cursor((1,))
        if "SELECT e.id,e.run_id" in sql:
            return _Cursor({"id": 1, "run_id": 59, "jitendex_snapshot_id": 1})
        if "UPDATE export SET verified=1" in sql:
            self.verified = True
        return _Cursor()

    def executemany(self, sql, parameters):
        self.files.extend(parameters)
        return _Cursor()


def _probe_rows() -> list[list[object]]:
    payload = json.loads(PROBE_PATH.read_text(encoding="utf-8"))
    return [[
        item["expression"], item["reading"], item["definition_tags"], item["rules"],
        item["score"], item["glossary"], item["sequence"], item["term_tags"],
    ] for item in payload["cases"]]


def _media_archive(path: Path) -> None:
    image = BytesIO()
    Image.new("RGBA", (2, 2), (20, 30, 40, 128)).save(image, format="AVIF", quality=100)
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="2" height="2"><path d="M0 0h2v2z"/></svg>'
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("probe/image.avif", image.getvalue())
        archive.writestr("probe/vector.svg", svg)


def _corpus(tmp_path: Path) -> ExportCorpus:
    archive = tmp_path / "source.zip"
    _media_archive(archive)
    codes = {
        code
        for row in _probe_rows()
        for field in (row[2], row[7])
        for code in str(field).split()
    }
    mapping = {
        code: {"label_ru": code, "description_ru": f"Описание {code}", "encoded_label_ru": code}
        for code in codes
    }
    return ExportCorpus(
        run_id=59,
        snapshot_id=1,
        source_archive=archive,
        source_sha256=sha256_file(archive),
        title="Jitendex — тест",
        description="Проверка богатой разметки",
        entries=entries_from_rows(_probe_rows()),
        resources=(
            ExportResource(PurePosixPath("probe/image.avif")),
            ExportResource(PurePosixPath("probe/vector.svg")),
        ),
        tag_mapping=mapping,
        tag_catalog_version="test-tags-v1",
        tag_catalog_sha256="0" * 64,
        embedded_summary={},
        tag_bank_references=sum(
            len(str(field).split()) for row in _probe_rows() for field in (row[2], row[7])
        ),
    )


def test_shared_model_groups_variants_and_rejects_unsafe_values():
    entries = entries_from_rows(_probe_rows())
    tomorrow = next(entry for entry in entries if entry.expression == "明日")
    assert len(tomorrow.variants) == 2
    assert tomorrow.readings == ("あした", "みょうにち")
    assert tomorrow.identity.startswith("e-")

    bad = _probe_rows()
    bad[0][0] = "bad\0key"
    with pytest.raises(ValueError, match="NUL"):
        entries_from_rows(bad)
    with pytest.raises(ValueError, match="unsafe media path"):
        safe_resource_path("../image.png")
    with pytest.raises(ValueError, match="invalid XML character"):
        require_xml_text("bad\x01text")


def test_loss_ledger_rejects_omissions():
    ledger = LossLedger("probe")
    ledger.record("ruby", "degraded", note="fallback")
    ledger.record("unknown", "omitted")
    with pytest.raises(ValueError, match="omitted"):
        ledger.require_no_omissions()
    assert ledger.as_dict()["totals"]["degraded"] == 1


def test_pocketbook_renders_keys_rich_fallbacks_and_compiler_contract(tmp_path):
    corpus = _corpus(tmp_path)
    output = tmp_path / "jitendex-ru.xdxf"
    ledger = LossLedger("pocketbook")
    counts = render_pocketbook_xdxf(
        corpus, output,
        {"probe/image.avif": "probe/image.png", "probe/vector.svg": "probe/vector.svg"},
        ledger,
    )
    root = ElementTree.parse(output).getroot()
    assert root.tag == "xdxf"
    assert counts["headwords"] == 5
    tomorrow = next(article for article in root.findall("ar") if article.findtext("./head/k") == "明日")
    assert [item.text for item in tomorrow.findall("./head/k")] == ["明日", "あした", "みょうにち"]
    rendered = output.read_text(encoding="utf-8")
    assert "│" in rendered
    assert "(あした)" in rendered
    assert "<kref>昨日</kref>" in rendered
    assert "resources/probe/image.png" in rendered

    language = tmp_path / "jaK"
    language.mkdir()
    for name in ("keyboard.txt", "collates.txt", "morphems.txt"):
        (language / name).write_text(name, encoding="utf-8")
    compiler = tmp_path / "fake-pocketbook"
    compiler.write_text(
        '#!/bin/sh\ninput="$1"\ncp "$input" "${input%.xdxf}.dic"\n',
        encoding="utf-8",
    )
    compiler.chmod(0o755)
    dic, tools = compile_pocketbook(
        tmp_path / "compile", output, compiler, language,
        compiler_sha256=sha256_file(compiler),
    )
    assert dic.read_bytes() == output.read_bytes()
    assert tools["language_files_sha256"]


def test_apple_project_preserves_xhtml_yomi_and_compiler_contract(tmp_path):
    corpus = _corpus(tmp_path)
    root = tmp_path / "apple"
    ledger = LossLedger("apple-dictionary")
    project = render_apple_project(corpus, root, ledger)
    verified = verify_apple_source_xml(project["xml_path"])
    assert verified == {"headwords": 5, "indexes": project["indexes"]}
    source = project["xml_path"].read_text(encoding="utf-8")
    assert 'd:value="明日"' in source
    assert 'd:yomi="あした"' in source
    assert "<ruby>明日<rt>あした</rt></ruby>" in source
    assert "<table>" in source
    assert "Images/probe/image.png" in source

    tool = tmp_path / "fake-build-dict"
    tool.write_text(
        '#!/bin/sh\nmkdir -p "objects/$1.dictionary/Contents"\n'
        'cp "$4" "objects/$1.dictionary/Contents/Info.plist"\n'
        'cp "$2" "objects/$1.dictionary/Contents/Body.data"\n'
        'cp "$2" "objects/$1.dictionary/Contents/KeyText.data"\n'
        'cp "$2" "objects/$1.dictionary/Contents/KeyText.index"\n',
        encoding="utf-8",
    )
    tool.chmod(0o755)
    bundle, details = compile_apple(
        root, project, tool,
        build_tool_sha256=sha256_file(tool), schema=None, schema_sha256=None,
    )
    assert bundle.name == f"{APPLE_BASENAME}.dictionary"
    assert (bundle / "Contents" / "Body.data").is_file()
    assert details["command"][1] == APPLE_BASENAME


def test_mdict_binary_is_deterministic_and_queryable(tmp_path):
    corpus = _corpus(tmp_path)
    resources = tmp_path / "mdd"
    resources.mkdir()
    (resources / "jitendex.css").write_text(".jr-entry{}", encoding="utf-8")
    media = resources / "media" / "probe"
    media.mkdir(parents=True)
    (media / "image.png").write_bytes(b"png")
    (media / "vector.svg").write_text("<svg/>", encoding="utf-8")
    source = tmp_path / "records.txt"
    ledger = LossLedger("mdict")
    counts = render_mdict_source(
        corpus, source,
        {"probe/image.avif": "probe/image.png", "probe/vector.svg": "probe/vector.svg"},
        ledger,
    )
    records = mdict_writer.pack_mdx_txt(str(source), encoding="UTF-8")
    first = tmp_path / "first.mdx"
    second = tmp_path / "second.mdx"
    _write_mdict(first, records, corpus, is_mdd=False)
    records_again = mdict_writer.pack_mdx_txt(str(source), encoding="UTF-8")
    _write_mdict(second, records_again, corpus, is_mdd=False)
    assert first.read_bytes() == second.read_bytes()
    header = _independent_header(first.read_bytes(), mdd=False)
    assert header["CreationDate"] == "1980-1-1"
    assert mdict_reader.query(str(first), "明日").startswith('<link rel="stylesheet"')
    assert mdict_reader.query(str(first), "みょうにち").rstrip("\n\0") == "@@@LINK=明日"
    assert counts["redirects"] >= 1
    assert "Другие статьи с этим чтением" in mdict_reader.query(str(first), "あした")

    mdd = tmp_path / "test.mdd"
    mdd_second = tmp_path / "test-second.mdd"
    _write_mdict(mdd, _mdd_records(resources), corpus, is_mdd=True)
    _write_mdict(mdd_second, _mdd_records(resources), corpus, is_mdd=True)
    assert mdd.read_bytes() == mdd_second.read_bytes()
    _independent_header(mdd.read_bytes(), mdd=True)
    assert "\\jitendex.css" in list(mdict_reader.get_keys(str(mdd)))


def test_compiled_export_packages_build_and_verify_with_probe_tools(tmp_path, monkeypatch):
    corpus = _corpus(tmp_path)

    language = tmp_path / "jaK"
    language.mkdir()
    for name in ("keyboard.txt", "collates.txt", "morphems.txt"):
        (language / name).write_text(name, encoding="utf-8")
    pocket_compiler = tmp_path / "fake-pocketbook"
    pocket_compiler.write_text(
        '#!/bin/sh\ninput="$1"\ncp "$input" "${input%.xdxf}.dic"\n', encoding="utf-8",
    )
    pocket_compiler.chmod(0o755)
    monkeypatch.setattr(pocketbook_module, "prepare_export", lambda connection, run_id: corpus)
    pocket_connection = _ExportConnection()
    pocket_output = tmp_path / "pocketbook.zip"
    pocket_result = pocketbook_module.build_pocketbook(
        pocket_connection, 59, pocket_output,
        compiler=pocket_compiler,
        compiler_sha256=sha256_file(pocket_compiler),
        language_dir=language,
    )
    assert pocket_result["headwords"] == 5
    assert pocketbook_module.verify_pocketbook(pocket_connection, pocket_output)["verified"]

    apple_tool = tmp_path / "fake-build-dict"
    apple_tool.write_text(
        '#!/bin/sh\nmkdir -p "objects/$1.dictionary/Contents"\n'
        'cp "$4" "objects/$1.dictionary/Contents/Info.plist"\n'
        'cp "$2" "objects/$1.dictionary/Contents/Body.data"\n'
        'cp "$2" "objects/$1.dictionary/Contents/KeyText.data"\n'
        'cp "$2" "objects/$1.dictionary/Contents/KeyText.index"\n',
        encoding="utf-8",
    )
    apple_tool.chmod(0o755)
    monkeypatch.setattr(apple_module, "prepare_export", lambda connection, run_id: corpus)
    apple_connection = _ExportConnection()
    apple_output = tmp_path / "apple.zip"
    apple_result = apple_module.build_apple_dictionary(
        apple_connection, 59, apple_output,
        build_tool=apple_tool, build_tool_sha256=sha256_file(apple_tool),
    )
    assert apple_result["indexes"] >= apple_result["headwords"]
    assert apple_module.verify_apple_dictionary(apple_connection, apple_output)["verified"]

    monkeypatch.setattr(mdict_module, "prepare_export", lambda connection, run_id: corpus)
    mdict_connection = _ExportConnection()
    first_output = tmp_path / "mdict-first.zip"
    second_output = tmp_path / "mdict-second.zip"
    first_result = mdict_module.build_mdict(mdict_connection, 59, first_output)
    second_result = mdict_module.build_mdict(mdict_connection, 59, second_output)
    assert first_output.read_bytes() == second_output.read_bytes()
    assert first_result["records"] == second_result["records"]
    assert mdict_module.verify_mdict(mdict_connection, first_output)["verified"]
