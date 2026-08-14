from __future__ import annotations

import html
import json
import plistlib
import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit
from xml.etree import ElementTree

from .attribution import ATTRIBUTION, PRODUCT_ID, PRODUCT_NAME
from .database import ConnectionLike
from .export_model import ExportCorpus, ExportEntry, ExportVariant, prepare_export
from .export_render import (
    LossLedger,
    class_name,
    file_manifest,
    materialize_resources,
    record_export,
    require_xml_text,
    verify_recorded_export,
    verify_zip_members,
    write_deterministic_zip,
    write_manifest_file,
    zip_member_sha256,
)
from .util import canonical_json, sha256_file

BASENAME = PRODUCT_ID
XML_NAME = f"{PRODUCT_ID}.xml"
CSS_NAME = f"{PRODUCT_ID}.css"
PLIST_NAME = f"{PRODUCT_ID}.plist"
BUNDLE_NAME = f"{BASENAME}.dictionary"
CAPABILITY_PROFILE = "apple-dictionary-ddk-experimental-v1"
DICTIONARY_NAMESPACE = "http://www.apple.com/DTDs/DictionaryService-1.0.rng"
ALLOWED_TAGS = {
    "a", "br", "details", "div", "img", "li", "ol", "rp", "rt", "ruby",
    "span", "summary", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "ul",
}
CSS = """.jr-entry{line-height:1.45;color:inherit}.jr-head{margin:0 0 .5em;border-bottom:1px solid #8885}
.jr-expression{font-size:1.35em;font-weight:700}.jr-reading{opacity:.72}.jr-variant+.jr-variant{margin-top:.8em;padding-top:.8em;border-top:1px dashed #8886}
.jr-tags{margin:.3em 0}.jr-tag,.dc-tag{font-size:.82em;padding:.08em .35em;border:1px solid #8887;border-radius:.3em;background:#8882}
.jr-entry table{border-collapse:collapse;max-width:100%}.jr-entry td,.jr-entry th{border:1px solid #8887;padding:.2em .35em}.jr-entry img{max-width:100%;height:auto}
.jr-entry ruby rt{font-size:.58em}.jr-details{margin:.4em 0}.jr-summary{display:block;font-weight:600}.sc-attribution,.sc-attribution-footnote,.sc-graphic-attribution{font-size:.78em;opacity:.68}
.sc-example-sentence,.sc-xref,.sc-antonym,.dc-extra-box{display:block;margin:.45em 0;padding:.35em .55em;border-left:.2em solid #8888}
.dc-form-pri{color:green}.dc-form-irr{color:crimson}.dc-form-out,.dc-form-old{color:#315fba}.dc-form-rare{color:purple}
.style-list-decimal{list-style-type:decimal}.style-list-disc{list-style-type:disc}.style-list-circle{list-style-type:circle}.style-list-square{list-style-type:square}
"""
INSTALLATION = (
    "Experimental Apple Dictionary build. Dictionary.app and contextual Look Up are not yet verified.\n"
    "After closing the capability gate, place the .dictionary bundle in ~/Library/Dictionaries/.\n"
)


def _escape(value: Any, label: str = "text") -> str:
    return html.escape(require_xml_text(str(value), label), quote=True)


def _semantic_attributes(
    node: Mapping[str, Any], ledger: LossLedger, extra_classes: tuple[str, ...] = (),
) -> str:
    classes: list[str] = [value for value in extra_classes if value]
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
            safe_value = class_name(value)
            if safe_key and safe_value and key not in {"class", "content"}:
                classes.append(f"meta-{safe_key}-{safe_value}")
            ledger.record(f"semantic-data:{key}", "lossless-transform", note="stable CSS class")
    raw_style = node.get("style")
    if isinstance(raw_style, dict):
        for name, value in sorted(raw_style.items()):
            safe_value = class_name(str(value))
            if name == "listStyleType" and safe_value:
                classes.append(f"style-list-{safe_value}")
                ledger.record(f"style:{name}", "lossless-transform", note="stable CSS class")
            else:
                ledger.record(f"style:{name}", "degraded", note="schema-safe CSS profile has no mapping")
    return f' class="{_escape(" ".join(dict.fromkeys(classes)))}"' if classes else ""


def _render_ruby(
    node: Mapping[str, Any], resources: Mapping[str, str], ledger: LossLedger,
) -> str:
    content = node.get("content")
    values = content if isinstance(content, list) else [content]
    output = []
    for value in values:
        if isinstance(value, dict) and value.get("tag") == "rt":
            output.append(f"<rt>{_render_content(value.get('content'), resources, ledger)}</rt>")
        else:
            output.append(_render_content(value, resources, ledger))
    ledger.record("ruby", "exact", note="XHTML ruby pending schema probe")
    return f"<ruby>{''.join(output)}</ruby>"


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
        ledger.record(f"tag:{tag}", "omitted", note="no Apple Dictionary mapping")
        raise ValueError(f"unsupported structured-content tag: {tag!r}")
    attributes = _semantic_attributes(node, ledger)
    if tag == "a":
        body = _render_content(node.get("content"), resources, ledger)
        href = node.get("href")
        if not isinstance(href, str):
            ledger.record("link:missing", "degraded", note="visible text retained")
            return body
        split = urlsplit(href)
        query = parse_qs(split.query).get("query") if not split.scheme and not split.netloc else None
        if query and query[0]:
            target = quote(query[0], safe="")
            ledger.record("link:internal", "lossless-transform", note="x-dictionary definition URI")
            return f'<a href="x-dictionary:d:{target}"{attributes}>{body or _escape(query[0])}</a>'
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
        attributes = _semantic_attributes(node, ledger, extra_classes)
        dimensions = []
        dimension_styles = []
        units = node.get("sizeUnits")
        for name in ("width", "height"):
            value = node.get(name)
            if isinstance(value, (int, float)) and value > 0:
                if units == "em":
                    dimension_styles.append(f"{name}:{value:g}em")
                else:
                    dimensions.append(f' {name}="{value:g}"')
                ledger.record(f"image:{name}", "lossless-transform")
        if dimension_styles:
            dimensions.append(f' style="{_escape(";".join(dimension_styles))}"')
        for name in ("appearance", "background", "sizeUnits"):
            if name in node:
                ledger.record(f"image:{name}", "lossless-transform", note="class or dimension unit")
        for name in ("collapsible", "collapsed"):
            if name in node:
                ledger.record(f"image:{name}", "lossless-transform", note="image emitted expanded")
        title = node.get("title")
        title_attribute = f' title="{_escape(title)}"' if isinstance(title, str) else ""
        ledger.record("image", "lossless-transform", note="bundle resource with alt text")
        return (
            f'<img src="Images/{_escape(resources[source], "resource path")}" alt="{_escape(alt)}"'
            f'{"".join(dimensions)}{attributes}{title_attribute}/>'
        )
    if tag == "details":
        ledger.record("details", "lossless-transform", note="expanded XHTML block")
        return f'<div class="jr-details">{_render_content(node.get("content"), resources, ledger)}</div>'
    if tag == "summary":
        return f'<span class="jr-summary">{_render_content(node.get("content"), resources, ledger)}</span>'
    if tag == "ruby":
        return _render_ruby(node, resources, ledger)
    if tag in {"rt", "rp"}:
        return _render_content(node.get("content"), resources, ledger)
    if tag == "br":
        ledger.record("tag:br", "exact")
        return "<br/>"
    body = _render_content(node.get("content"), resources, ledger)
    title = node.get("title")
    title_attribute = f' title="{_escape(title)}"' if isinstance(title, str) else ""
    span_tags = {"div", "span", "ol", "ul", "li", "table", "tbody", "thead", "tfoot", "tr", "td", "th"}
    if tag not in span_tags:
        raise AssertionError(tag)
    ledger.record(f"tag:{tag}", "exact")
    return f"<{tag}{attributes}{title_attribute}>{body}</{tag}>"


def _tag_badges(variant: ExportVariant, mapping: Mapping[str, Mapping[str, str]], ledger: LossLedger) -> str:
    badges = []
    for code in variant.tag_codes:
        approved = mapping.get(code)
        if approved is None:
            raise ValueError(f"missing approved Apple Dictionary tag mapping for {code!r}")
        badges.append(
            f'<span class="jr-tag" title="{_escape(approved["description_ru"])}">'
            f'{_escape(approved["label_ru"])}</span>'
        )
        ledger.record("tag-tooltip", "exact")
    return f'<div class="jr-tags">{"".join(badges)}</div>' if badges else ""


def _indexes(entry: ExportEntry) -> tuple[tuple[str, str], ...]:
    readings = entry.readings or (entry.expression,)
    indexes: list[tuple[str, str]] = []
    for reading in readings:
        indexes.append((entry.expression, reading))
        if reading != entry.expression:
            indexes.append((reading, reading))
    return tuple(dict.fromkeys(indexes))


def _render_entry(
    entry: ExportEntry, resources: Mapping[str, str], mapping: Mapping[str, Mapping[str, str]], ledger: LossLedger,
) -> tuple[str, int]:
    index_markup = []
    for value, yomi in _indexes(entry):
        index_markup.append(
            f'<d:index d:value="{_escape(value, "index")}" d:title="{_escape(entry.expression)}" '
            f'd:yomi="{_escape(yomi, "yomi")}"/>'
        )
    sections = []
    for variant in entry.variants:
        reading = (
            f'<span class="jr-reading" lang="ja">【{_escape(variant.reading)}】</span>'
            if variant.reading and variant.reading != entry.expression else ""
        )
        body = "".join(_render_content(item, resources, ledger) for item in variant.glossary)
        sections.append(
            '<div class="jr-variant"><div class="jr-head">'
            f'<span class="jr-expression" lang="ja">{_escape(entry.expression)}</span>{reading}'
            f'</div>{_tag_badges(variant, mapping, ledger)}{body}</div>'
        )
    ledger.record("index:expression", "exact")
    ledger.record("index:yomi", "exact", len(entry.readings))
    markup = (
        f'<d:entry id="{entry.identity}" d:title="{_escape(entry.expression)}">'
        f'{"".join(index_markup)}<div class="jr-entry">{"".join(sections)}</div></d:entry>\n'
    )
    return markup, len(index_markup)


def _plist(corpus: ExportCorpus) -> bytes:
    return plistlib.dumps({
        "CFBundleDevelopmentRegion": "Russian",
        "CFBundleDisplayName": corpus.title,
        "CFBundleIdentifier": "org.kolobok.dictionary.jp-ru-400k",
        "CFBundleName": PRODUCT_ID,
        "CFBundleShortVersionString": "1.0",
        "DCSDictionaryCopyright": "Jitendex/JMdict/Tatoeba; Russian derivative CC BY-SA 4.0",
        "DCSDictionaryManufacturerName": "Колобок 400k; Юрий Катков",
        "DCSDictionaryFrontMatterReferenceID": "front_back_matter",
    }, fmt=plistlib.FMT_XML, sort_keys=True)


def render_apple_project(
    corpus: ExportCorpus, root: Path, ledger: LossLedger,
) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    resources_root = root / "OtherResources"
    resource_map, converted = materialize_resources(
        corpus, resources_root, prefix=PurePosixPath("Images"),
    )
    ledger.record("media:avif", "lossless-transform", converted, note="deterministic PNG")
    xml_path = root / XML_NAME
    index_count = 0
    with xml_path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        stream.write(
            f'<d:dictionary xmlns="http://www.w3.org/1999/xhtml" xmlns:d="{DICTIONARY_NAMESPACE}">\n'
        )
        stream.write(
            f'<d:entry id="front_back_matter" d:title="{PRODUCT_NAME} — сведения">'
            f'<h1>{_escape(corpus.title)}</h1><p>{_escape(corpus.description)}</p>'
            '<p>Jitendex, JMdict, Tatoeba; русская производная версия CC BY-SA 4.0. '
            'Соавтор русской редакции: Юрий Катков.</p></d:entry>\n'
        )
        for entry in corpus.entries:
            markup, indexes = _render_entry(entry, resource_map, corpus.tag_mapping, ledger)
            stream.write(markup)
            index_count += indexes
        stream.write("</d:dictionary>\n")
    (root / CSS_NAME).write_text(CSS, encoding="utf-8", newline="\n")
    (root / PLIST_NAME).write_bytes(_plist(corpus))
    (root / "Makefile").write_text(
        f'DICT_NAME = {BASENAME}\n'
        f'DICT_SRC_PATH = {XML_NAME}\n'
        f'CSS_PATH = {CSS_NAME}\n'
        f'PLIST_PATH = {PLIST_NAME}\n'
        'DICT_BUILD_TOOL ?= /Developer/Extras/Dictionary\\ Development\\ Kit/bin/build_dict.sh\n\n'
        'all:\n\t$(DICT_BUILD_TOOL) "$(DICT_NAME)" "$(DICT_SRC_PATH)" "$(CSS_PATH)" "$(PLIST_PATH)"\n',
        encoding="utf-8", newline="\n",
    )
    return {
        "xml_path": xml_path,
        "css_path": root / CSS_NAME,
        "plist_path": root / PLIST_NAME,
        "headwords": len(corpus.entries),
        "indexes": index_count,
        "converted_images": converted,
        "resource_map": resource_map,
    }


def _compile(
    root: Path,
    project: Mapping[str, Any],
    build_tool: Path,
    *,
    build_tool_sha256: str,
    schema: Path | None,
    schema_sha256: str | None,
) -> tuple[Path, dict[str, Any]]:
    if not build_tool.is_file() or sha256_file(build_tool) != build_tool_sha256:
        raise ValueError("Apple Dictionary build tool is missing or its SHA-256 differs")
    tools: dict[str, Any] = {"build_tool_sha256": build_tool_sha256}
    if schema is not None:
        if not schema.is_file() or not schema_sha256 or sha256_file(schema) != schema_sha256:
            raise ValueError("Apple Dictionary schema is missing or its SHA-256 differs")
        validator = shutil.which("xmllint")
        if validator is None:
            raise ValueError("xmllint is required for the supplied Apple Dictionary schema")
        validation = subprocess.run(
            [validator, "--noout", "--relaxng", str(schema), str(project["xml_path"])],
            cwd=root, text=True, capture_output=True, check=False,
        )
        if validation.returncode:
            raise ValueError(f"Apple Dictionary XML schema validation failed: {validation.stderr.strip()[:500]}")
        tools["schema_sha256"] = schema_sha256
    command = [
        str(build_tool), BASENAME, Path(project["xml_path"]).name,
        Path(project["css_path"]).name, Path(project["plist_path"]).name,
    ]
    result = subprocess.run(command, cwd=root, text=True, capture_output=True, check=False)
    if result.returncode:
        message = (result.stderr or result.stdout).strip()
        raise ValueError(f"Apple Dictionary build failed with exit {result.returncode}: {message[:500]}")
    bundle = root / "objects" / BUNDLE_NAME
    contents = bundle / "Contents"
    if not (contents / "Info.plist").is_file():
        raise ValueError(f"Apple Dictionary build tool did not produce objects/{BUNDLE_NAME}")
    compiled_payloads = ("Body.data", "KeyText.data", "KeyText.index")
    if any(
        not (contents / name).is_file() or not (contents / name).stat().st_size
        for name in compiled_payloads
    ):
        raise ValueError("Apple Dictionary bundle has incomplete compiled payloads")
    tools["command"] = [build_tool.name, *command[1:]]
    return bundle, tools


def build_apple_dictionary(
    connection: ConnectionLike,
    run_id: int,
    output: Path,
    *,
    build_tool: Path,
    build_tool_sha256: str,
    schema: Path | None = None,
    schema_sha256: str | None = None,
) -> dict[str, Any]:
    corpus = prepare_export(connection, run_id)
    output.parent.mkdir(parents=True, exist_ok=True)
    ledger = LossLedger("apple-dictionary")
    with tempfile.TemporaryDirectory(prefix="apple-dictionary-", dir=output.parent) as temporary:
        root = Path(temporary)
        project = render_apple_project(corpus, root, ledger)
        bundle, tools = _compile(
            root, project, build_tool.resolve(),
            build_tool_sha256=build_tool_sha256,
            schema=schema.resolve() if schema else None,
            schema_sha256=schema_sha256,
        )
        (root / "ATTRIBUTION.txt").write_text(ATTRIBUTION, encoding="utf-8", newline="\n")
        (root / "INSTALL.txt").write_text(INSTALLATION, encoding="utf-8", newline="\n")
        source_report = {
            "xml_sha256": sha256_file(project["xml_path"]),
            "css_sha256": sha256_file(project["css_path"]),
            "plist_sha256": sha256_file(project["plist_path"]),
            "headwords": project["headwords"],
            "indexes": project["indexes"],
            "resources": len(corpus.resources),
        }
        (root / "source-report.json").write_bytes(canonical_json(source_report) + b"\n")
        payload = [
            (path.relative_to(bundle.parent).as_posix(), path)
            for path in bundle.rglob("*") if path.is_file()
        ] + [
            (name, root / name)
            for name in ("ATTRIBUTION.txt", "INSTALL.txt", "source-report.json")
        ]
        payload_manifest = file_manifest(payload)
        manifest_path = root / "manifest.json"
        write_manifest_file(
            manifest_path, corpus,
            format_name="apple-dictionary",
            capability_profile=CAPABILITY_PROFILE,
            files=payload_manifest,
            ledger=ledger,
            tools=tools,
        )
        bundle_paths = payload + [("manifest.json", manifest_path)]
        recorded_manifest = file_manifest(bundle_paths)
        write_deterministic_zip(output, bundle_paths)
    export_id, output_hash = record_export(
        connection, corpus, output, recorded_manifest,
        format_name="apple_dictionary",
        details={
            "headwords": project["headwords"], "indexes": project["indexes"],
            "capability_profile": CAPABILITY_PROFILE,
        },
    )
    return {
        "export_id": export_id,
        "format": "apple-dictionary",
        "capability_profile": CAPABILITY_PROFILE,
        "articles": corpus.article_count,
        "headwords": project["headwords"],
        "indexes": project["indexes"],
        "resources": len(corpus.resources),
        "converted_images": project["converted_images"],
        "files": len(recorded_manifest),
        "zip_sha256": output_hash,
    }


def verify_apple_dictionary(connection: ConnectionLike, path: Path) -> dict[str, Any]:
    export, output_hash = verify_recorded_export(connection, path)
    with zipfile.ZipFile(path) as archive:
        names = verify_zip_members(archive, required={
            "manifest.json", "source-report.json", "ATTRIBUTION.txt", "INSTALL.txt",
        })
        bundle_prefix = f"{BUNDLE_NAME}/"
        bundle_info = f"{bundle_prefix}Contents/Info.plist"
        compiled_payloads = {
            f"{bundle_prefix}Contents/Body.data",
            f"{bundle_prefix}Contents/KeyText.data",
            f"{bundle_prefix}Contents/KeyText.index",
        }
        if bundle_info not in names or not compiled_payloads.issubset(names):
            raise ValueError("Apple Dictionary package has an incomplete bundle structure")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("format") != "apple-dictionary" or manifest.get("capability_profile") != CAPABILITY_PROFILE:
            raise ValueError("unexpected Apple Dictionary manifest profile")
        for item in manifest.get("files", []):
            name = item.get("path")
            if name not in names or zip_member_sha256(archive, name) != item.get("sha256"):
                raise ValueError(f"Apple Dictionary member hash mismatch: {name}")
        source_report = json.loads(archive.read("source-report.json"))
        if source_report.get("headwords") != manifest.get("headwords"):
            raise ValueError("Apple Dictionary source report count mismatch")
    connection.execute("UPDATE export SET verified=1 WHERE id=?", (export["id"],))
    return {
        "verified": True,
        "format": "apple-dictionary",
        "capability_profile": CAPABILITY_PROFILE,
        "headwords": source_report["headwords"],
        "indexes": source_report["indexes"],
        "files": len(names),
        "zip_sha256": output_hash,
    }


def verify_apple_source_xml(path: Path) -> dict[str, int]:
    """Independently count and validate a generated project XML file."""
    entries = 0
    indexes = 0
    namespace = f"{{{DICTIONARY_NAMESPACE}}}"
    for _event, element in ElementTree.iterparse(path, events=("end",)):
        if element.tag == namespace + "entry":
            if element.get("id") != "front_back_matter":
                entries += 1
                child_indexes = [child for child in element if child.tag == namespace + "index"]
                if not child_indexes:
                    raise ValueError("Apple Dictionary entry has no index")
                indexes += len(child_indexes)
            element.clear()
    return {"headwords": entries, "indexes": indexes}
