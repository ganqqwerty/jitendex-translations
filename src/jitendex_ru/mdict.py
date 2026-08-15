from __future__ import annotations

import html
import json
import locale
import shutil
import struct
import tempfile
import threading
import zipfile
import zlib
from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit
from xml.etree import ElementTree

from mdict_utils import reader as mdict_reader
from mdict_utils import writer as mdict_writer

from .attribution import (
    ATTRIBUTION, COMPILATION_DATETIME_UTC, DICTIONARY_VERSION, VERSIONED_PRODUCT_ID,
)
from .database import ConnectionLike
from .export_model import (
    ExportCorpus,
    ExportEntry,
    ExportVariant,
    prepare_export,
    stable_text_key,
)
from .export_render import (
    LossLedger,
    class_name,
    file_manifest,
    materialize_resources,
    record_export,
    require_xml_text,
    verify_recorded_export,
    verify_release_manifest,
    verify_zip_members,
    write_deterministic_zip,
    write_manifest_file,
    zip_member_sha256,
)

BASENAME = VERSIONED_PRODUCT_ID
CAPABILITY_PROFILE = "mdict-2.0-experimental-v1"
WRITER_VERSION = "mdict-utils-1.3.14"
ALLOWED_TAGS = {
    "a", "br", "details", "div", "img", "li", "ol", "rp", "rt", "ruby",
    "span", "summary", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "ul",
}
CSS = """.jr-entry{font-family:system-ui,-apple-system,sans-serif;line-height:1.45;color:inherit}.jr-head{margin:0 0 .5em;border-bottom:1px solid #8885}
.jr-expression{font-size:1.4em;font-weight:700}.jr-reading{opacity:.72}.jr-variant+.jr-variant{margin-top:.8em;padding-top:.8em;border-top:1px dashed #8886}
.jr-tags{margin:.3em 0}.jr-tag,.dc-tag{font-size:.82em;padding:.08em .35em;border:1px solid #8887;border-radius:.3em;background:#8882}
.jr-entry table{border-collapse:collapse;max-width:100%}.jr-entry td,.jr-entry th{border:1px solid #8887;padding:.2em .35em}.jr-entry img{max-width:100%;height:auto}
.jr-entry ruby rt{font-size:.58em}.jr-summary{display:block;font-weight:600}.sc-attribution,.sc-attribution-footnote,.sc-graphic-attribution{font-size:.78em;opacity:.68}
.sc-example-sentence,.sc-xref,.sc-antonym,.dc-extra-box{display:block;margin:.45em 0;padding:.35em .55em;border-left:.2em solid #8888}
.dc-form-pri{color:green}.dc-form-irr{color:crimson}.dc-form-out,.dc-form-old{color:#315fba}.dc-form-rare{color:purple}
.style-list-decimal{list-style-type:decimal}.style-list-disc{list-style-type:disc}.style-list-circle{list-style-type:circle}.style-list-square{list-style-type:square}
.style-font-bold{font-weight:bold}.style-font-italic{font-style:italic}
@media(prefers-color-scheme:dark){.image-monochrome{filter:invert(1)}}
"""
INSTALLATION = (
    "Experimental unencrypted MDict 2.0 package. Official clients are not yet verified.\n"
    f"Keep {BASENAME}.mdx and {BASENAME}.mdd together when importing them.\n"
)
_LOCALE_LOCK = threading.Lock()


def _escape(value: Any, label: str = "text") -> str:
    return html.escape(require_xml_text(str(value), label), quote=True)


def _attributes(
    node: Mapping[str, Any], ledger: LossLedger, extra_classes: Iterable[str] = (),
) -> str:
    classes: list[str] = [value for value in extra_classes if value]
    attributes: list[tuple[str, str]] = []
    data = node.get("data")
    if isinstance(data, dict):
        semantic_class = class_name(data.get("class"))
        semantic_content = class_name(data.get("content"))
        if semantic_class:
            classes.append(f"dc-{semantic_class}")
        if semantic_content:
            classes.append(f"sc-{semantic_content}")
        for key, value in sorted(data.items()):
            safe_key = class_name(key)
            if safe_key and isinstance(value, (str, int, float)) and not isinstance(value, bool):
                attributes.append((f"data-sc-{safe_key}", str(value)))
                ledger.record(f"semantic-data:{key}", "exact", note="HTML data attribute")
    style = node.get("style")
    if isinstance(style, dict):
        for name, value in sorted(style.items()):
            safe_value = class_name(str(value))
            if name == "listStyleType" and safe_value:
                classes.append(f"style-list-{safe_value}")
                ledger.record(f"style:{name}", "lossless-transform", note="CSS class")
            elif name == "fontWeight" and value in {"bold", 600, 700, 800, 900}:
                classes.append("style-font-bold")
                ledger.record(f"style:{name}", "lossless-transform", note="CSS class")
            elif name == "fontStyle" and value == "italic":
                classes.append("style-font-italic")
                ledger.record(f"style:{name}", "lossless-transform", note="CSS class")
            else:
                ledger.record(f"style:{name}", "degraded", note="portable MDict CSS profile has no mapping")
    if classes:
        attributes.append(("class", " ".join(dict.fromkeys(classes))))
    for name in ("title", "lang"):
        value = node.get(name)
        if isinstance(value, str):
            attributes.append((name, value))
    for source_name, output_name in (("colSpan", "colspan"), ("rowSpan", "rowspan")):
        value = node.get(source_name)
        if isinstance(value, int) and value > 0:
            attributes.append((output_name, str(value)))
    return "".join(f' {name}="{_escape(value)}"' for name, value in attributes)


def _render_content(node: Any, resources: Mapping[str, str], ledger: LossLedger) -> str:
    if node is None:
        return ""
    if isinstance(node, (str, int, float)) and not isinstance(node, bool):
        return _escape(node)
    if isinstance(node, list):
        return "".join(_render_content(item, resources, ledger) for item in node)
    if not isinstance(node, dict):
        raise ValueError(f"unsupported structured-content value: {type(node).__name__}")  # noqa: TRY004
    if node.get("type") == "structured-content":
        ledger.record("structured-content", "lossless-transform")
        return _render_content(node.get("content"), resources, ledger)
    tag = node.get("tag")
    if tag not in ALLOWED_TAGS:
        ledger.record(f"tag:{tag}", "omitted", note="no MDict mapping")
        raise ValueError(f"unsupported structured-content tag: {tag!r}")
    attributes = _attributes(node, ledger)
    if tag == "a":
        body = _render_content(node.get("content"), resources, ledger)
        href = node.get("href")
        if not isinstance(href, str):
            ledger.record("link:missing", "degraded", note="visible text retained")
            return body
        split = urlsplit(href)
        query = parse_qs(split.query).get("query") if not split.scheme and not split.netloc else None
        if query and query[0]:
            ledger.record("link:internal", "lossless-transform", note="entry URI")
            return f'<a href="entry://{quote(query[0], safe="")}"{attributes}>{body or _escape(query[0])}</a>'
        if split.scheme in {"http", "https"}:
            ledger.record("link:external", "exact")
            return f'<a href="{_escape(href, "link")}"{attributes}>{body or _escape(href)}</a>'
        ledger.record("link:other", "degraded", note="visible text retained")
        return body or _escape(href)
    if tag == "img":
        source = node.get("path")
        if not isinstance(source, str) or source not in resources:
            raise ValueError(f"structured-content image has invalid path {source!r}")
        alt = node.get("alt") or node.get("title") or "Изображение"
        if not isinstance(alt, str):
            alt = "Изображение"
        appearance = class_name(node.get("appearance"))
        extra_classes = (
            "gloss-image",
            f"image-{appearance}" if appearance else "",
            "image-background" if node.get("background") is True else "",
        )
        attributes = _attributes(
            node, ledger, extra_classes,
        )
        style_values = []
        units = node.get("sizeUnits")
        if units not in {"px", "em"}:
            units = "px"
        for name in ("width", "height"):
            value = node.get(name)
            if isinstance(value, (int, float)) and value > 0:
                style_values.append(f"{name}:{value:g}{units}")
                ledger.record(f"image:{name}", "lossless-transform")
        style_attribute = f' style="{_escape(";".join(style_values))}"' if style_values else ""
        for name in ("appearance", "background", "sizeUnits"):
            if name in node:
                ledger.record(f"image:{name}", "lossless-transform", note="class or dimension unit")
        for name in ("collapsible", "collapsed"):
            if name in node:
                ledger.record(f"image:{name}", "lossless-transform", note="image emitted expanded")
        ledger.record("image", "lossless-transform", note="MDD resource with alt text")
        return (
            f'<img src="media/{_escape(resources[source], "resource path")}" alt="{_escape(alt)}"'
            f'{attributes}{style_attribute}/>'
        )
    if tag == "details":
        ledger.record("details", "lossless-transform", note="expanded HTML block")
        return f'<div class="jr-details">{_render_content(node.get("content"), resources, ledger)}</div>'
    if tag == "summary":
        return f'<span class="jr-summary">{_render_content(node.get("content"), resources, ledger)}</span>'
    if tag == "br":
        ledger.record("tag:br", "exact")
        return "<br>"
    body = _render_content(node.get("content"), resources, ledger)
    ledger.record(f"tag:{tag}", "exact")
    return f"<{tag}{attributes}>{body}</{tag}>"


def _tag_badges(variant: ExportVariant, mapping: Mapping[str, Mapping[str, str]], ledger: LossLedger) -> str:
    badges = []
    for code in variant.tag_codes:
        approved = mapping.get(code)
        if approved is None:
            raise ValueError(f"missing approved MDict tag mapping for {code!r}")
        badges.append(
            f'<span class="jr-tag" title="{_escape(approved["description_ru"])}">'
            f'{_escape(approved["label_ru"])}</span>'
        )
        ledger.record("tag-tooltip", "exact")
    return f'<div class="jr-tags">{"".join(badges)}</div>' if badges else ""


def _article_html(
    entry: ExportEntry,
    resources: Mapping[str, str],
    mapping: Mapping[str, Mapping[str, str]],
    ledger: LossLedger,
    related_targets: Iterable[str] = (),
) -> str:
    sections = []
    for variant in entry.variants:
        reading = (
            f'<span class="jr-reading" lang="ja">【{_escape(variant.reading)}】</span>'
            if variant.reading and variant.reading != entry.expression else ""
        )
        body = "".join(_render_content(item, resources, ledger) for item in variant.glossary)
        sections.append(
            '<section class="jr-variant"><div class="jr-head">'
            f'<span class="jr-expression" lang="ja">{_escape(entry.expression)}</span>{reading}'
            f'</div>{_tag_badges(variant, mapping, ledger)}{body}</section>'
        )
    related = tuple(dict.fromkeys(target for target in related_targets if target != entry.expression))
    if related:
        links = "".join(
            f'<li><a href="entry://{quote(target, safe="")}">{_escape(target)}</a></li>'
            for target in related
        )
        sections.append(f'<aside class="jr-related"><b>Другие статьи с этим чтением</b><ul>{links}</ul></aside>')
        ledger.record("index:reading-collision", "lossless-transform", len(related), note="visible related-entry links")
    ledger.record("index:expression", "exact")
    return (
        '<link rel="stylesheet" type="text/css" href="jitendex.css">'
        f'<article class="jr-entry" lang="ru">{"".join(sections)}</article>'
    )


def render_mdict_source(
    corpus: ExportCorpus,
    output: Path,
    resources: Mapping[str, str],
    ledger: LossLedger,
) -> dict[str, int]:
    expressions = {entry.expression for entry in corpus.entries}
    reading_targets: dict[str, list[str]] = {}
    for entry in corpus.entries:
        for reading in entry.readings:
            reading_targets.setdefault(reading, []).append(entry.expression)
    related_count = 0
    redirects = 0
    disambiguations = 0
    record_count = 0
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as stream:
        def write_record(key: str, body: str) -> None:
            if not key or "\x00" in key or "\r" in key or "\n" in key:
                raise ValueError(f"invalid MDict key {key!r}")
            if "\n</>\n" in body:
                raise ValueError(f"MDict record for {key!r} contains the source delimiter")
            stream.write(f"{key}\n{body}\n</>\n")
        for entry in corpus.entries:
            related = reading_targets.get(entry.expression, ())
            related_count += len([target for target in related if target != entry.expression])
            write_record(
                entry.expression,
                _article_html(entry, resources, corpus.tag_mapping, ledger, related),
            )
            record_count += 1
        for reading, targets in sorted(reading_targets.items(), key=lambda item: stable_text_key(item[0])):
            unique_targets = tuple(dict.fromkeys(targets))
            if reading in expressions:
                continue
            if len(unique_targets) == 1:
                body = f"@@@LINK={unique_targets[0]}"
                redirects += 1
                ledger.record("index:reading", "lossless-transform", note="MDict redirect")
            else:
                links = "".join(
                    f'<li><a href="entry://{quote(target, safe="")}">{_escape(target)}</a></li>'
                    for target in unique_targets
                )
                body = (
                    '<link rel="stylesheet" type="text/css" href="jitendex.css">'
                    f'<article class="jr-disambiguation"><h1>{_escape(reading)}</h1><ul>{links}</ul></article>'
                )
                disambiguations += 1
                ledger.record("index:reading", "lossless-transform", note="disambiguation record")
            write_record(reading, body)
            record_count += 1
    return {
        "headwords": len(corpus.entries),
        "records": record_count,
        "redirects": redirects,
        "disambiguations": disambiguations,
        "related_links": related_count,
    }


class _DeterministicWriter(mdict_writer.MDictWriter):
    def _write_header(self, stream: Any) -> None:
        if not self._is_mdd:
            header = (
                '<Dictionary GeneratedByEngineVersion="2.0" RequiredEngineVersion="2.0" '
                f'Encrypted="No" Encoding="{self._encoding}" Format="Html" Stripkey="Yes" '
                f'CreationDate="{COMPILATION_DATETIME_UTC[:10]}" Compact="Yes" Compat="Yes" KeyCaseSensitive="No" '
                f'Description="{html.escape(self._description, quote=True)}" '
                f'Title="{html.escape(self._title, quote=True)}" DataSourceFormat="106" '
                'StyleSheet="" Left2Right="Yes" RegisterBy="" />\r\n\x00'
            )
        else:
            header = (
                '<Library_Data GeneratedByEngineVersion="2.0" RequiredEngineVersion="2.0" '
                f'Encrypted="No" Encoding="" Format="" CreationDate="{COMPILATION_DATETIME_UTC[:10]}" '
                'KeyCaseSensitive="No" Stripkey="No" '
                f'Description="{html.escape(self._description, quote=True)}" '
                f'Title="{html.escape(self._title, quote=True)}" RegisterBy="" />\r\n\x00'
            )
        encoded = header.encode("utf-16-le")
        stream.write(struct.pack(">L", len(encoded)))
        stream.write(encoded)
        stream.write(struct.pack("<L", zlib.adler32(encoded) & 0xFFFFFFFF))


@contextmanager
def _c_collation() -> Any:
    with _LOCALE_LOCK:
        previous = locale.setlocale(locale.LC_COLLATE)
        locale.setlocale(locale.LC_COLLATE, "C")
        try:
            yield
        finally:
            locale.setlocale(locale.LC_COLLATE, previous)


def _close_writer_files() -> None:
    for value in mdict_writer.MDICT_OBJ.values():
        close = getattr(value, "close", None)
        if close:
            close()
    mdict_writer.MDICT_OBJ.clear()


def _write_mdict(path: Path, records: list[dict[str, Any]], corpus: ExportCorpus, *, is_mdd: bool) -> None:
    try:
        with _c_collation():
            writer = _DeterministicWriter(
                records,
                title=corpus.title,
                description=corpus.description,
                key_size=32768,
                record_size=65536,
                encoding="UTF-8",
                version="2.0",
                is_mdd=is_mdd,
            )
        with path.open("wb") as stream:
            writer.write(stream)
    finally:
        _close_writer_files()


def _mdd_records(root: Path) -> list[dict[str, Any]]:
    records = []
    for path in sorted((path for path in root.rglob("*") if path.is_file()), key=lambda path: path.relative_to(root).as_posix()):
        key = "\\" + path.relative_to(root).as_posix().replace("/", "\\")
        records.append({"key": key, "pos": 0, "path": str(path), "size": path.stat().st_size})
    return records


def _independent_header_stream(stream: Any, *, mdd: bool) -> dict[str, str]:
    prefix = stream.read(4)
    if len(prefix) != 4:
        raise ValueError("truncated MDict file")
    header_size = struct.unpack(">L", prefix)[0]
    if header_size <= 0:
        raise ValueError("invalid MDict header length")
    header_data = stream.read(header_size)
    checksum_data = stream.read(4)
    if len(header_data) != header_size or len(checksum_data) != 4 or not stream.read(1):
        raise ValueError("truncated MDict header")
    checksum = struct.unpack("<L", checksum_data)[0]
    if checksum != zlib.adler32(header_data) & 0xFFFFFFFF:
        raise ValueError("MDict header checksum mismatch")
    try:
        text = header_data.decode("utf-16-le").rstrip("\x00\r\n")
        element = ElementTree.fromstring(text)
    except (UnicodeDecodeError, ElementTree.ParseError) as error:
        raise ValueError("invalid MDict header XML") from error
    if element.tag != ("Library_Data" if mdd else "Dictionary"):
        raise ValueError("unexpected MDict header type")
    attributes = dict(element.attrib)
    required = {
        "GeneratedByEngineVersion": "2.0",
        "RequiredEngineVersion": "2.0",
        "Encrypted": "No",
        "CreationDate": COMPILATION_DATETIME_UTC[:10],
    }
    if any(attributes.get(key) != value for key, value in required.items()):
        raise ValueError("unsupported or nondeterministic MDict header")
    if not mdd and (attributes.get("Encoding") != "UTF-8" or attributes.get("Format") != "Html"):
        raise ValueError("unexpected MDX encoding or format")
    return attributes


def _independent_header(data: bytes, *, mdd: bool) -> dict[str, str]:
    return _independent_header_stream(BytesIO(data), mdd=mdd)


def _independent_header_path(path: Path, *, mdd: bool) -> dict[str, str]:
    with path.open("rb") as stream:
        return _independent_header_stream(stream, mdd=mdd)


def build_mdict(connection: ConnectionLike, run_id: int, output: Path) -> dict[str, Any]:
    corpus = prepare_export(connection, run_id)
    output.parent.mkdir(parents=True, exist_ok=True)
    ledger = LossLedger("mdict")
    with tempfile.TemporaryDirectory(prefix="mdict-", dir=output.parent) as temporary:
        root = Path(temporary)
        resources_root = root / "mdd"
        resource_map, converted = materialize_resources(
            corpus, resources_root, prefix=PurePosixPath("media"),
        )
        ledger.record("media:avif", "lossless-transform", converted, note="deterministic PNG")
        (resources_root / "jitendex.css").write_text(CSS, encoding="utf-8", newline="\n")
        source_path = root / f"{BASENAME}.txt"
        counts = render_mdict_source(corpus, source_path, resource_map, ledger)
        mdx_records = mdict_writer.pack_mdx_txt(str(source_path), encoding="UTF-8")
        if len(mdx_records) != counts["records"]:
            raise ValueError("MDict source record count mismatch")
        mdx_path = root / f"{BASENAME}.mdx"
        mdd_path = root / f"{BASENAME}.mdd"
        _write_mdict(mdx_path, mdx_records, corpus, is_mdd=False)
        mdd_records = _mdd_records(resources_root)
        _write_mdict(mdd_path, mdd_records, corpus, is_mdd=True)
        _independent_header_path(mdx_path, mdd=False)
        _independent_header_path(mdd_path, mdd=True)
        (root / "ATTRIBUTION.txt").write_text(ATTRIBUTION, encoding="utf-8", newline="\n")
        (root / "INSTALL.txt").write_text(INSTALLATION, encoding="utf-8", newline="\n")
        payload = [
            (f"{BASENAME}.mdx", mdx_path), (f"{BASENAME}.mdd", mdd_path),
            ("ATTRIBUTION.txt", root / "ATTRIBUTION.txt"),
            ("INSTALL.txt", root / "INSTALL.txt"),
        ]
        payload_manifest = file_manifest(payload)
        manifest_path = root / "manifest.json"
        manifest_data = write_manifest_file(
            manifest_path, corpus,
            format_name="mdict-2.0",
            capability_profile=CAPABILITY_PROFILE,
            files=payload_manifest,
            ledger=ledger,
            tools={
                "writer": WRITER_VERSION,
                "header_date": COMPILATION_DATETIME_UTC[:10],
                "collation": "C",
                **counts,
                "mdd_records": len(mdd_records),
            },
        )
        bundle_paths = payload + [("manifest.json", manifest_path)]
        recorded_manifest = file_manifest(bundle_paths)
        write_deterministic_zip(output, bundle_paths)
    export_id, output_hash = record_export(
        connection, corpus, output, recorded_manifest,
        format_name="mdict",
        details={**counts, "capability_profile": CAPABILITY_PROFILE},
    )
    return {
        "export_id": export_id,
        "format": "mdict-2.0",
        "capability_profile": CAPABILITY_PROFILE,
        "articles": corpus.article_count,
        **counts,
        "resources": len(corpus.resources),
        "mdd_records": manifest_data["tools"]["mdd_records"],
        "converted_images": converted,
        "files": len(recorded_manifest),
        "zip_sha256": output_hash,
    }


def verify_mdict(connection: ConnectionLike, path: Path) -> dict[str, Any]:
    export, output_hash = verify_recorded_export(connection, path)
    with zipfile.ZipFile(path) as archive:
        names = verify_zip_members(archive, required={
            f"{BASENAME}.mdx", f"{BASENAME}.mdd", "manifest.json", "ATTRIBUTION.txt", "INSTALL.txt",
        })
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("format") != "mdict-2.0" or manifest.get("capability_profile") != CAPABILITY_PROFILE:
            raise ValueError("unexpected MDict manifest profile")
        verify_release_manifest(manifest)
        for item in manifest.get("files", []):
            name = item.get("path")
            if name not in names or zip_member_sha256(archive, name) != item.get("sha256"):
                raise ValueError(f"MDict member hash mismatch: {name}")
        with tempfile.TemporaryDirectory(prefix="verify-mdict-") as temporary:
            root = Path(temporary)
            mdx_path = root / f"{BASENAME}.mdx"
            mdd_path = root / f"{BASENAME}.mdd"
            for name, destination in ((f"{BASENAME}.mdx", mdx_path), (f"{BASENAME}.mdd", mdd_path)):
                with archive.open(name) as source, destination.open("wb") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
            mdx_header = _independent_header_path(mdx_path, mdd=False)
            mdd_header = _independent_header_path(mdd_path, mdd=True)
            for header in (mdx_header, mdd_header):
                if f"v{DICTIONARY_VERSION}" not in header.get("Title", ""):
                    raise ValueError("MDict title lacks the dictionary version")
                if COMPILATION_DATETIME_UTC not in header.get("Description", ""):
                    raise ValueError("MDict description lacks the compilation datetime")
            mdx_meta = mdict_reader.meta(str(mdx_path))
            mdd_meta = mdict_reader.meta(str(mdd_path))
            keys = list(mdict_reader.get_keys(str(mdx_path)))
            mdd_keys = list(mdict_reader.get_keys(str(mdd_path)))
            if len(keys) != manifest.get("tools", {}).get("records"):
                raise ValueError("MDX record count mismatch")
            if len(mdd_keys) != manifest.get("tools", {}).get("mdd_records"):
                raise ValueError("MDD resource count mismatch")
            if "\\jitendex.css" not in mdd_keys:
                raise ValueError("MDD lacks the dictionary stylesheet")
            if mdx_meta.get("version") != 2.0 or mdd_meta.get("version") != 2.0:
                raise ValueError("unexpected MDict binary version")
    connection.execute("UPDATE export SET verified=1 WHERE id=?", (export["id"],))
    return {
        "verified": True,
        "format": "mdict-2.0",
        "capability_profile": CAPABILITY_PROFILE,
        "records": len(keys),
        "resources": len(mdd_keys),
        "files": len(names),
        "zip_sha256": output_hash,
    }
