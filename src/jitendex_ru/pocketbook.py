from __future__ import annotations

import html
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import parse_qs, urlsplit
from xml.etree import ElementTree

from .attribution import ATTRIBUTION, PRODUCT_ID
from .database import ConnectionLike
from .export_model import ExportCorpus, ExportEntry, ExportVariant, prepare_export
from .export_render import (
    LossLedger,
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
from .util import canonical_json, sha256_bytes, sha256_file

BASENAME = PRODUCT_ID
CAPABILITY_PROFILE = "pocketbook-xdxf-experimental-v1"
ALLOWED_TAGS = {
    "a", "br", "details", "div", "img", "li", "ol", "rp", "rt", "ruby",
    "span", "summary", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "ul",
}
INSTALLATION = (
    "Experimental PocketBook build. Device compatibility is not yet verified.\n"
    f"After closing the capability gate, copy {PRODUCT_ID}.dic to /system/dictionaries/ on the device.\n"
)


def _escape(value: Any, label: str = "text") -> str:
    text = require_xml_text(str(value), label)
    return html.escape(text, quote=True)


def _children(node: Mapping[str, Any]) -> Any:
    return node.get("content")


def _render_list(
    node: Mapping[str, Any], resources: Mapping[str, str], ledger: LossLedger, ordered: bool,
) -> str:
    style = node.get("style")
    if isinstance(style, dict) and "listStyleType" in style:
        ledger.record("style:listStyleType", "degraded", note="number or bullet prefix")
    content = node.get("content")
    items = content if isinstance(content, list) else [content]
    rendered: list[str] = []
    for index, item in enumerate(items, 1):
        prefix = f"{index}. " if ordered else "• "
        if isinstance(item, dict) and item.get("tag") == "li":
            item_style = item.get("style")
            if isinstance(item_style, dict) and "listStyleType" in item_style:
                ledger.record("style:listStyleType", "degraded", note="number or bullet prefix")
            body = _render_content(item.get("content"), resources, ledger)
        else:
            body = _render_content(item, resources, ledger)
        rendered.append(_escape(prefix) + body + "<br/>")
    ledger.record("ordered-list" if ordered else "unordered-list", "degraded", note="visible prefixes")
    return "".join(rendered)


def _render_table(
    node: Mapping[str, Any], resources: Mapping[str, str], ledger: LossLedger,
) -> str:
    rows = node.get("content")
    row_values = rows if isinstance(rows, list) else [rows]
    output: list[str] = []
    for row in row_values:
        if not isinstance(row, dict) or row.get("tag") != "tr":
            output.append(_render_content(row, resources, ledger))
            continue
        cells = row.get("content")
        cell_values = cells if isinstance(cells, list) else [cells]
        rendered_cells = []
        for cell in cell_values:
            if isinstance(cell, dict) and cell.get("tag") in {"th", "td"}:
                value = _render_content(cell.get("content"), resources, ledger)
                rendered_cells.append(f"<b>{value}</b>" if cell.get("tag") == "th" else value)
            else:
                rendered_cells.append(_render_content(cell, resources, ledger))
        output.append(" │ ".join(rendered_cells) + "<br/>")
    ledger.record("table", "degraded", note="labeled text rows")
    return "".join(output)


def _render_ruby(
    node: Mapping[str, Any], resources: Mapping[str, str], ledger: LossLedger,
) -> str:
    content = node.get("content")
    values = content if isinstance(content, list) else [content]
    base: list[str] = []
    readings: list[str] = []
    for value in values:
        if isinstance(value, dict) and value.get("tag") == "rt":
            readings.append(_render_content(value.get("content"), resources, ledger))
        else:
            base.append(_render_content(value, resources, ledger))
    ledger.record("ruby", "degraded", note="base followed by parenthesized reading")
    suffix = f" <small>({' / '.join(readings)})</small>" if readings else ""
    return "".join(base) + suffix


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
        ledger.record(f"tag:{tag}", "omitted", note="no PocketBook mapping")
        raise ValueError(f"unsupported structured-content tag: {tag!r}")
    data = node.get("data")
    if isinstance(data, dict):
        for key in sorted(data):
            ledger.record(f"semantic-data:{key}", "degraded", note="XDXF has no portable data attributes")
    if tag in {"div", "tbody", "thead", "tfoot"}:
        ledger.record(f"tag:{tag}", "lossless-transform")
        return _render_content(_children(node), resources, ledger) + ("<br/>" if tag == "div" else "")
    if tag == "span":
        body = _render_content(_children(node), resources, ledger)
        style = node.get("style")
        if isinstance(style, dict):
            if style.get("fontWeight") in {"bold", 600, 700, 800, 900}:
                body = f"<b>{body}</b>"
                ledger.record("style:fontWeight", "lossless-transform")
            if style.get("fontStyle") == "italic":
                body = f"<i>{body}</i>"
                ledger.record("style:fontStyle", "lossless-transform")
            for name in sorted(set(style) - {"fontWeight", "fontStyle"}):
                ledger.record(f"style:{name}", "degraded", note="no tested XDXF visual equivalent")
        title = node.get("title")
        if isinstance(title, str) and title:
            body = f"<abr>{body}</abr><co> — {_escape(title)}</co>"
            ledger.record("tag-tooltip", "lossless-transform", note="description made visible")
        return body
    if tag == "br":
        ledger.record("tag:br", "exact")
        return "<br/>"
    if tag == "ol":
        return _render_list(node, resources, ledger, True)
    if tag == "ul":
        return _render_list(node, resources, ledger, False)
    if tag == "li":
        return _render_content(_children(node), resources, ledger)
    if tag == "table":
        return _render_table(node, resources, ledger)
    if tag in {"tr", "td", "th"}:
        return _render_content(_children(node), resources, ledger)
    if tag == "ruby":
        return _render_ruby(node, resources, ledger)
    if tag in {"rt", "rp"}:
        return _render_content(_children(node), resources, ledger)
    if tag == "a":
        body = _render_content(_children(node), resources, ledger)
        href = node.get("href")
        if not isinstance(href, str):
            ledger.record("link:missing", "degraded", note="visible text retained")
            return body
        split = urlsplit(href)
        query = parse_qs(split.query).get("query") if not split.scheme and not split.netloc else None
        if query and query[0]:
            ledger.record("link:internal", "lossless-transform")
            return f"<kref>{body or _escape(query[0])}</kref>"
        if split.scheme in {"http", "https"}:
            ledger.record("link:external", "lossless-transform")
            return f'<iref href="{_escape(href, "link")}">{body or _escape(href)}</iref>'
        ledger.record("link:other", "degraded", note="visible text retained")
        return body or _escape(href)
    if tag == "img":
        source = node.get("path")
        if not isinstance(source, str) or source not in resources:
            raise ValueError(f"structured-content image has invalid path {source!r}")
        alt = node.get("alt") or node.get("title") or "Изображение"
        if not isinstance(alt, str):
            alt = "Изображение"
        for name in ("appearance", "background", "width", "height", "sizeUnits"):
            if name in node:
                ledger.record(f"image:{name}", "degraded", note="text alternative and resource retained")
        for name in ("collapsible", "collapsed"):
            if name in node:
                ledger.record(f"image:{name}", "lossless-transform", note="image emitted expanded")
        ledger.record("image", "lossless-transform", note="resource reference plus text alternative")
        return f"<rref>{_escape('resources/' + resources[source], 'resource path')}</rref> <small>{_escape(alt)}</small>"
    if tag == "details":
        ledger.record("details", "lossless-transform", note="expanded")
        return _render_content(_children(node), resources, ledger)
    if tag == "summary":
        return f"<b>{_render_content(_children(node), resources, ledger)}</b><br/>"
    raise AssertionError(tag)


def _tag_badges(variant: ExportVariant, mapping: Mapping[str, Mapping[str, str]], ledger: LossLedger) -> str:
    output: list[str] = []
    for code in variant.tag_codes:
        approved = mapping.get(code)
        if approved is None:
            raise ValueError(f"missing approved PocketBook tag mapping for {code!r}")
        output.append(
            f"<abr>{_escape(approved['label_ru'])}</abr>"
            f"<co> — {_escape(approved['description_ru'])}</co>"
        )
        ledger.record("tag-tooltip", "lossless-transform", note="description made visible")
    return (" ".join(output) + "<br/>") if output else ""


def _render_entry(
    entry: ExportEntry, resources: Mapping[str, str], mapping: Mapping[str, Mapping[str, str]], ledger: LossLedger,
) -> str:
    keys = [entry.expression, *entry.readings]
    head = "".join(f"<k>{_escape(key, 'headword')}</k>" for key in keys)
    sections: list[str] = []
    for number, variant in enumerate(entry.variants, 1):
        reading = (
            f"<b>{_escape(entry.expression)}</b> 【{_escape(variant.reading)}】<br/>"
            if variant.reading and variant.reading != entry.expression
            else f"<b>{_escape(entry.expression)}</b><br/>"
        )
        body = "".join(_render_content(item, resources, ledger) for item in variant.glossary)
        sections.append(
            (f"<br/><b>{number}.</b> " if number > 1 else "")
            + reading + _tag_badges(variant, mapping, ledger) + body
        )
    ledger.record("index:expression", "exact")
    ledger.record("index:reading", "lossless-transform", len(entry.readings), note="additional XDXF keys")
    return f"<ar><head>{head}</head><def>{''.join(sections)}</def></ar>\n"


def render_pocketbook_xdxf(
    corpus: ExportCorpus, output: Path, resources: Mapping[str, str], ledger: LossLedger,
) -> dict[str, int]:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        stream.write('<xdxf lang_from="jaK" lang_to="ru" format="visual">\n')
        stream.write(f"<full_name>{_escape(corpus.title)}</full_name>\n")
        stream.write(f"<description>{_escape(corpus.description)}</description>\n")
        for entry in corpus.entries:
            stream.write(_render_entry(entry, resources, corpus.tag_mapping, ledger))
        stream.write("</xdxf>\n")
    return {
        "headwords": len(corpus.entries),
        "index_keys": sum(1 + len(entry.readings) for entry in corpus.entries),
    }


def _directory_sha256(path: Path) -> str:
    rows = []
    for item in sorted((item for item in path.rglob("*") if item.is_file()), key=lambda item: item.relative_to(path).as_posix()):
        rows.append({"path": item.relative_to(path).as_posix(), "sha256": sha256_file(item)})
    return sha256_bytes(canonical_json(rows))


def _compile(
    root: Path,
    xdxf_path: Path,
    compiler: Path,
    language_dir: Path,
    *,
    compiler_sha256: str,
) -> tuple[Path, dict[str, Any]]:
    root.mkdir(parents=True, exist_ok=True)
    if not compiler.is_file():
        raise ValueError(f"PocketBook compiler does not exist: {compiler}")
    if sha256_file(compiler) != compiler_sha256:
        raise ValueError("PocketBook compiler SHA-256 mismatch")
    required = {"keyboard.txt", "collates.txt", "morphems.txt"}
    missing = required - {item.name for item in language_dir.iterdir() if item.is_file()} if language_dir.is_dir() else required
    if missing:
        raise ValueError(f"PocketBook language directory lacks {sorted(missing)}")
    staged_xdxf = root / xdxf_path.name
    if xdxf_path.resolve() != staged_xdxf.resolve():
        shutil.copy2(xdxf_path, staged_xdxf)
    staged_compiler = root / compiler.name
    shutil.copy2(compiler, staged_compiler)
    staged_language = root / language_dir.name
    shutil.copytree(language_dir, staged_language)
    if staged_compiler.suffix.lower() == ".exe" and os.name != "nt":
        runtime = shutil.which("wine")
        if runtime is None:
            raise ValueError("PocketBook compiler is a Windows executable, but Wine is unavailable")
        command = [runtime, staged_compiler.name, staged_xdxf.name, staged_language.name]
    else:
        command = [str(staged_compiler), staged_xdxf.name, staged_language.name]
    result = subprocess.run(command, cwd=root, text=True, capture_output=True, check=False)
    if result.returncode:
        message = (result.stderr or result.stdout).strip()
        raise ValueError(f"PocketBook compiler failed with exit {result.returncode}: {message[:500]}")
    dic_path = staged_xdxf.with_suffix(".dic")
    if not dic_path.is_file() or not dic_path.stat().st_size:
        raise ValueError("PocketBook compiler did not produce a non-empty .dic file")
    recorded_command = [Path(command[0]).name, *command[1:]]
    return dic_path, {
        "compiler_sha256": compiler_sha256,
        "language_files_sha256": _directory_sha256(language_dir),
        "command": recorded_command,
    }


def build_pocketbook(
    connection: ConnectionLike,
    run_id: int,
    output: Path,
    *,
    compiler: Path,
    compiler_sha256: str,
    language_dir: Path,
) -> dict[str, Any]:
    corpus = prepare_export(connection, run_id)
    output.parent.mkdir(parents=True, exist_ok=True)
    ledger = LossLedger("pocketbook")
    with tempfile.TemporaryDirectory(prefix="pocketbook-", dir=output.parent) as temporary:
        root = Path(temporary)
        resource_map, converted = materialize_resources(
            corpus, root, prefix=PurePosixPath("resources"),
        )
        ledger.record("media:avif", "lossless-transform", converted, note="deterministic PNG")
        xdxf_path = root / f"{BASENAME}.xdxf"
        counts = render_pocketbook_xdxf(corpus, xdxf_path, resource_map, ledger)
        _dic_path, tool_details = _compile(
            root, xdxf_path, compiler.resolve(), language_dir.resolve(),
            compiler_sha256=compiler_sha256,
        )
        (root / "ATTRIBUTION.txt").write_text(ATTRIBUTION, encoding="utf-8", newline="\n")
        (root / "INSTALL.txt").write_text(INSTALLATION, encoding="utf-8", newline="\n")
        payload = [
            (path.relative_to(root).as_posix(), path)
            for path in root.rglob("*")
            if path.is_file() and path not in {root / compiler.name} and language_dir.name not in path.parts
        ]
        payload_manifest = file_manifest(payload)
        manifest_path = root / "manifest.json"
        write_manifest_file(
            manifest_path, corpus,
            format_name="pocketbook-dic",
            capability_profile=CAPABILITY_PROFILE,
            files=payload_manifest,
            ledger=ledger,
            tools=tool_details,
        )
        bundle_paths = payload + [("manifest.json", manifest_path)]
        recorded_manifest = file_manifest(bundle_paths)
        write_deterministic_zip(output, bundle_paths)
    export_id, output_hash = record_export(
        connection, corpus, output, recorded_manifest,
        format_name="pocketbook",
        details={**counts, "capability_profile": CAPABILITY_PROFILE},
    )
    return {
        "export_id": export_id,
        "format": "pocketbook-dic",
        "capability_profile": CAPABILITY_PROFILE,
        "articles": corpus.article_count,
        **counts,
        "resources": len(corpus.resources),
        "converted_images": converted,
        "files": len(recorded_manifest),
        "zip_sha256": output_hash,
    }


def verify_pocketbook(connection: ConnectionLike, path: Path) -> dict[str, Any]:
    export, output_hash = verify_recorded_export(connection, path)
    with zipfile.ZipFile(path) as archive:
        names = verify_zip_members(archive, required={
            f"{BASENAME}.xdxf", f"{BASENAME}.dic", "manifest.json", "ATTRIBUTION.txt", "INSTALL.txt",
        })
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("format") != "pocketbook-dic" or manifest.get("capability_profile") != CAPABILITY_PROFILE:
            raise ValueError("unexpected PocketBook manifest profile")
        for item in manifest.get("files", []):
            name = item.get("path")
            if name not in names or zip_member_sha256(archive, name) != item.get("sha256"):
                raise ValueError(f"PocketBook member hash mismatch: {name}")
        with archive.open(f"{BASENAME}.xdxf") as source:
            headwords = 0
            index_keys = 0
            for event, element in ElementTree.iterparse(source, events=("end",)):
                if element.tag == "ar":
                    headwords += 1
                    index_keys += len(element.findall("./head/k"))
                    if not element.findtext("./head/k") or element.find("./def") is None:
                        raise ValueError("invalid PocketBook XDXF article")
                    element.clear()
        if headwords != manifest.get("headwords"):
            raise ValueError("PocketBook XDXF headword count mismatch")
        if archive.getinfo(f"{BASENAME}.dic").file_size <= 0:
            raise ValueError("empty PocketBook dictionary")
    connection.execute("UPDATE export SET verified=1 WHERE id=?", (export["id"],))
    return {
        "verified": True,
        "format": "pocketbook-dic",
        "capability_profile": CAPABILITY_PROFILE,
        "headwords": headwords,
        "index_keys": index_keys,
        "files": len(names),
        "zip_sha256": output_hash,
    }
