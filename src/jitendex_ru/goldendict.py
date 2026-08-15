from __future__ import annotations

import html
import codecs
import json
import os
import re
import shutil
import struct
import tempfile
import zipfile
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from urllib.parse import parse_qs, quote, urlsplit

from PIL import Image, ImageOps

from .attribution import DICTIONARY_AUTHORS, PRODUCT_ID, PRODUCT_NAME
from .build_dictionary import FIXED_ZIP_TIME, _frequency_metadata, _paths, materialize_run
from .database import ConnectionLike
from .db import audit
from .jitendex_tags import (
    count_tag_bank_references, load_approved_tag_catalog, localize_embedded_tags,
    localize_tag_bank_rows, tag_bank_mapping,
)
from .util import canonical_json, sha256_bytes, sha256_file


BASENAME = PRODUCT_ID
ALLOWED_TAGS = {
    "a", "br", "details", "div", "img", "li", "ol", "rp", "rt", "ruby",
    "span", "summary", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "ul",
}
VOID_TAGS = {"br", "img"}
STYLE_NAMES = {
    "fontStyle": "font-style", "fontWeight": "font-weight", "fontSize": "font-size",
    "textDecorationLine": "text-decoration-line", "verticalAlign": "vertical-align",
    "textAlign": "text-align", "marginTop": "margin-top", "marginRight": "margin-right",
    "marginBottom": "margin-bottom", "marginLeft": "margin-left", "listStyleType": "list-style-type",
}
DATA_NAMES = {
    "class": "data-sc-class",
    "content": "data-sc-content",
    "code": "data-sc-code",
    "sentence-key": "data-sc-sentence-key",
    "source": "data-sc-source",
    "source-type": "data-sc-source-type",
}
CSS = """.jr-entry,.jr-variant{display:block}.jr-entry{font-family:system-ui,-apple-system,sans-serif;line-height:1.45;color:inherit}
.jr-head{display:flex;align-items:baseline;gap:.65em;margin:0 0 .7em;border-bottom:1px solid #8885}
.jr-expression{font-size:1.45em;font-weight:700}.jr-reading{font-size:1em;opacity:.72}
.jr-variant+.jr-variant{margin-top:1em;padding-top:1em;border-top:1px dashed #8886}
.jr-tags{display:flex;flex-wrap:wrap;gap:.3em;margin:.35em 0}.jr-tag,.tag{font-size:.82em;padding:.08em .38em;border:1px solid #8887;border-radius:.3em;background:#8882}
.sc-glossary{margin:.4em 0;padding-left:1.5em}.sc-sense{margin:.45em 0}.sc-sense-group{margin:.6em 0}
.extra-box{margin:.55em 0;padding:.45em .65em;border-left:.22em solid #6d8fb3;background:#8881}
.extra-label{font-weight:650;margin-bottom:.2em}.sc-attribution{font-size:.78em;opacity:.62;margin-top:.65em}
.jr-entry table{border-collapse:collapse;max-width:100%}.jr-entry td,.jr-entry th{border:1px solid #8887;padding:.25em .4em}
.jr-entry img{max-width:100%;height:auto}.jr-entry ruby rt{font-size:.58em}.jr-entry a{text-decoration:none}
.gloss-image-container{display:inline-block;max-width:100%}.image-background{padding:.2em;background:#fff;border-radius:.25em}
[data-sc-content="sense-groups"]{list-style-type:"＊"}[data-sc-content="glossary"]{padding-left:1.25em}
[data-sc-class="tag"]{border-radius:.3em;font-size:.8em;font-weight:bold;margin-right:.5em;padding:.2em .3em;vertical-align:text-bottom;white-space:nowrap}
[data-sc-content="part-of-speech-info"],[data-sc-content="forms-label"]{background:#565656;color:#fff}
[data-sc-content="misc-info"]{background:brown;color:#fff}[data-sc-content="field-info"]{background:purple;color:#fff}
[data-sc-content="dialect-info"]{background:green;color:#fff}[data-sc-content="lang-source-wasei"]{background:orange;color:#000}
[data-sc-class="extra-box"]{border-left:.22em solid #6d8fb3;border-radius:.4em;margin:.5em 0;padding:.5em;background:#8881}
[data-sc-content="info-gloss"]{border-color:green}[data-sc-content="sense-note"]{border-color:goldenrod}
[data-sc-content="lang-source"]{border-color:purple}[data-sc-content="xref"]{border-color:#1a73e8}
[data-sc-content="antonym"]{border-color:brown}[data-sc-content="example-sentence"]{border-color:currentColor}
[data-sc-content="reference-label"],[data-sc-class="extra-label"]{font-size:.8em;opacity:.72}
[data-sc-content="xref-content"],[data-sc-content="antonym-content"],[data-sc-content="example-sentence-a"]{font-size:1.3em}
[data-sc-content="xref-glossary"],[data-sc-content="antonym-glossary"],[data-sc-content="example-sentence-b"]{font-size:.85em}
[data-sc-content="redirect-glossary"]{font-size:1.8em}[data-sc-content="registered-trademark"]{font-size:.6em;vertical-align:super}
[data-sc-content="example-keyword"]{color:#269326}[data-sc-content="attribution-footnote"],[data-sc-content="graphic-attribution"]{font-size:.75em;opacity:.72}
[data-sc-content="attribution"]{font-size:.7em;text-align:right}[data-sc-content="forms"] table{margin-top:.2em}
[data-sc-content="forms"] th{font-weight:normal;text-align:left}[data-sc-content="forms"] td{text-align:center}
[data-sc-class="form-special"]{color:crimson}[data-sc-class="form-pri"]{color:green}[data-sc-class="form-irr"]{color:crimson}
[data-sc-class="form-out"],[data-sc-class="form-old"]{color:#315fba}[data-sc-class="form-rare"]{color:purple}
[data-sc-class="form-pri"]>span:before{content:"△"}[data-sc-class="form-irr"]>span:before{content:"✕"}
[data-sc-class="form-out"]>span:before{content:"古"}[data-sc-class="form-old"]>span:before{content:"旧"}
[data-sc-class="form-rare"]>span:before{content:"▽"}[data-sc-class="form-valid"]>span:before{content:"◇"}
@media(prefers-color-scheme:dark){.image-monochrome{filter:invert(1)}}
"""


def _sort_key(value: str) -> tuple[bytes, bytes]:
    raw = value.encode("utf-8")
    return bytes(byte + 32 if 65 <= byte <= 90 else byte for byte in raw), raw


def _class_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-")
    return cleaned or None


def _internal_href(value: str) -> str:
    split = urlsplit(value)
    if not split.scheme and not split.netloc:
        query = parse_qs(split.query).get("query")
        if query and query[0]:
            return "bword://" + quote(query[0], safe="")
    return value


def _style(node: dict[str, Any]) -> str | None:
    declarations: list[str] = []
    raw_style = node.get("style")
    if isinstance(raw_style, dict):
        for source_name, css_name in STYLE_NAMES.items():
            value = raw_style.get(source_name)
            if isinstance(value, (str, int, float)):
                declarations.append(f"{css_name}:{value}")
    units = node.get("sizeUnits")
    if units in {"px", "em"}:
        for name in ("width", "height"):
            value = node.get(name)
            if isinstance(value, (int, float)):
                declarations.append(f"{name}:{value:g}{units}")
    return ";".join(declarations) or None


def render_content(node: Any, resource_paths: dict[str, str] | None = None) -> str:
    """Render trusted Yomitan structured content as escaped GoldenDict HTML."""
    if node is None:
        return ""
    if isinstance(node, (str, int, float)) and not isinstance(node, bool):
        return html.escape(str(node))
    if isinstance(node, list):
        return "".join(render_content(item, resource_paths) for item in node)
    if not isinstance(node, dict):
        raise ValueError(f"unsupported structured-content value: {type(node).__name__}")
    if node.get("type") == "structured-content":
        return render_content(node.get("content"), resource_paths)
    tag = node.get("tag")
    if tag not in ALLOWED_TAGS:
        raise ValueError(f"unsupported structured-content tag: {tag!r}")
    attributes: list[tuple[str, str]] = []
    classes: list[str] = []
    data = node.get("data")
    if isinstance(data, dict):
        regular_class = _class_name(data.get("class"))
        semantic_class = _class_name(data.get("content"))
        if regular_class:
            classes.append(regular_class)
        if semantic_class:
            classes.append(f"sc-{semantic_class}")
        for source_name, output_name in DATA_NAMES.items():
            value = data.get(source_name)
            if isinstance(value, (str, int, float)) and not isinstance(value, bool):
                attributes.append((output_name, str(value)))
    if tag == "img":
        appearance = _class_name(node.get("appearance"))
        classes.append("gloss-image")
        if appearance:
            classes.append(f"image-{appearance}")
        if node.get("background") is True:
            classes.append("image-background")
        for name, attribute_name in (
            ("appearance", "appearance"), ("collapsible", "collapsible"),
            ("collapsed", "collapsed"), ("background", "background"), ("sizeUnits", "size-units"),
        ):
            value = node.get(name)
            if isinstance(value, bool):
                attributes.append((f"data-sc-{attribute_name}", str(value).lower()))
            elif isinstance(value, str):
                attributes.append((f"data-sc-{attribute_name}", value))
    if classes:
        attributes.append(("class", " ".join(classes)))
    for name in ("title", "lang"):
        value = node.get(name)
        if isinstance(value, str):
            attributes.append((name, value))
    for source_name, output_name in (("colSpan", "colspan"), ("rowSpan", "rowspan")):
        value = node.get(source_name)
        if isinstance(value, int) and value > 0:
            attributes.append((output_name, str(value)))
    style = _style(node)
    if style:
        attributes.append(("style", style))
    if tag == "a" and isinstance(node.get("href"), str):
        attributes.append(("href", _internal_href(node["href"])))
    if tag == "img":
        path = node.get("path")
        if not isinstance(path, str) or not path:
            raise ValueError("structured-content image has no path")
        path = (resource_paths or {}).get(path, path)
        alt = node.get("alt")
        if not isinstance(alt, str):
            alt = node.get("title") if isinstance(node.get("title"), str) else ""
        attributes.extend((("src", path), ("alt", alt)))
    serialized = "".join(
        f' {name}="{html.escape(str(value), quote=True)}"' for name, value in attributes
    )
    if tag in VOID_TAGS:
        element = f"<{tag}{serialized}>"
        if tag == "img":
            if node.get("collapsible") is True:
                open_attribute = "" if node.get("collapsed") is True else " open"
                label = html.escape(alt or "Изображение")
                return f'<details class="gloss-image-container"{open_attribute}><summary>{label}</summary>{element}</details>'
            return f'<span class="gloss-image-container">{element}</span>'
        return element
    return f"<{tag}{serialized}>{render_content(node.get('content'), resource_paths)}</{tag}>"


def _tag_badges(codes: str, tag_mapping: dict[str, dict[str, str]]) -> str:
    badges = []
    for code in (item for item in codes.split(" ") if item):
        approved = tag_mapping.get(code)
        if approved is None:
            raise ValueError(f"missing approved GoldenDict tag mapping for {code!r}")
        title_attribute = f' title="{html.escape(approved["description_ru"], quote=True)}"'
        badges.append(
            f'<span class="jr-tag"{title_attribute}>{html.escape(approved["label_ru"])}</span>'
        )
    return '<div class="jr-tags">' + "".join(badges) + "</div>" if badges else ""


def _article_html(
    expression: str, rows: list[list[Any]], tag_mapping: dict[str, dict[str, str]],
    resource_paths: dict[str, str] | None = None,
) -> str:
    sections = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 8:
            raise ValueError("invalid Yomitan term row")
        reading = row[1] if isinstance(row[1], str) else ""
        reading_html = (
            f'<span class="jr-reading">【{html.escape(reading)}】</span>'
            if reading and reading != expression else ""
        )
        glossary = row[5]
        if isinstance(glossary, list):
            glossary_items = glossary
        elif isinstance(glossary, (dict, str)):
            glossary_items = [glossary]
        else:
            raise ValueError(f"invalid glossary for {expression!r}")
        body = "".join(
            render_content(item, resource_paths)
            if isinstance(item, dict) else f"<p>{render_content(item, resource_paths)}</p>"
            for item in glossary_items
        )
        tags = " ".join(value for value in (row[2], row[7]) if isinstance(value, str))
        variant_attributes = (
            f' data-rules="{html.escape(row[3], quote=True)}"'
            f' data-score="{row[4]}" data-sequence="{row[6]}"'
        )
        sections.append(
            f'<section class="jr-variant"{variant_attributes}><div class="jr-head">'
            f'<span class="jr-expression" lang="ja">{html.escape(expression)}</span>{reading_html}'
            f"</div>{_tag_badges(tags, tag_mapping)}{body}</section>"
        )
    return (
        f'<link rel="stylesheet" href="{BASENAME}.css">'
        '<article class="jr-entry" lang="ru">' + "".join(sections) + "</article>"
    )


def _safe_resource_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"unsafe media path {value!r}")
    return path


def _goldendict_resource_path(path: PurePosixPath) -> PurePosixPath:
    return path.with_suffix(".png") if path.suffix.lower() == ".avif" else path


def _write_resource(source: Any, source_path: PurePosixPath, destination: Path) -> bool:
    """Copy a resource, transcoding AVIF to deterministic PNG when needed."""
    if source_path.suffix.lower() != ".avif":
        with destination.open("wb") as target:
            shutil.copyfileobj(source, target, length=1024 * 1024)
        return False
    try:
        with Image.open(source) as image:
            converted = ImageOps.exif_transpose(image)
            converted.load()
            options: dict[str, Any] = {"compress_level": 9, "optimize": False}
            icc_profile = image.info.get("icc_profile")
            if isinstance(icc_profile, bytes):
                options["icc_profile"] = icc_profile
            converted.save(destination, format="PNG", **options)
    except (OSError, ValueError) as error:
        raise ValueError(
            f"failed to transcode AVIF resource {source_path}; Pillow with AVIF support is required"
        ) from error
    return True


def _ifo_value(value: Any) -> str:
    return re.sub(r"[\r\n]+", "<br>", str(value))


def _write_zip_member(archive: zipfile.ZipFile, name: str, path: Path) -> None:
    info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    with path.open("rb") as source, archive.open(info, "w", force_zip64=True) as target:
        shutil.copyfileobj(source, target, length=1024 * 1024)


def _manifest(paths: Iterable[tuple[str, Path]]) -> list[dict[str, Any]]:
    return [
        {"path": name, "sha256": sha256_file(path), "bytes": path.stat().st_size}
        for name, path in paths
    ]


def build_goldendict(
    connection: ConnectionLike, run_id: int, output: Path,
) -> dict[str, Any]:
    """Build a deterministic StarDict bundle for GoldenDict."""
    run, source_row, rows = materialize_run(connection, run_id)
    catalog = load_approved_tag_catalog(connection, run["jitendex_snapshot_id"])
    embedded = localize_embedded_tags(rows, catalog)
    groups: dict[str, list[list[Any]]] = defaultdict(list)
    for row in rows:
        if not isinstance(row, list) or not row or not isinstance(row[0], str) or not row[0]:
            raise ValueError("invalid Yomitan term row expression")
        groups[row[0]].append(row)
    expressions = sorted(groups, key=_sort_key)
    media = sorted({_safe_resource_path(path) for row in rows for path in _paths(row)}, key=str)
    resource_paths = {str(path): str(_goldendict_resource_path(path)) for path in media}
    if len(set(resource_paths.values())) != len(resource_paths):
        raise ValueError("media paths collide after AVIF-to-PNG conversion")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="goldendict-", dir=output.parent) as temporary:
        root = Path(temporary)
        dict_path = root / f"{BASENAME}.dict"
        idx_path = root / f"{BASENAME}.idx"
        syn_path = root / f"{BASENAME}.syn"
        res_dir = root / "res"
        res_dir.mkdir()
        synonyms: list[tuple[str, int]] = []
        offset = 0
        with zipfile.ZipFile(source_row["local_path"]) as source, \
                dict_path.open("wb") as dictionary, idx_path.open("wb") as index:
            source_names = set(source.namelist())
            tag_bank_names = sorted(
                (name for name in source_names if re.fullmatch(r"tag_bank_\d+\.json", name)),
                key=lambda name: int(re.search(r"\d+", name)[0]),
            )
            source_tag_rows = [
                row for name in tag_bank_names for row in json.loads(source.read(name))
            ]
            _localized_tag_rows, tag_mapping = localize_tag_bank_rows(source_tag_rows, catalog)
            tag_bank_references_replaced = count_tag_bank_references(rows, tag_mapping)
            source_css = source.read("styles.css").decode("utf-8") if "styles.css" in source_names else ""
            for source_path, output_path in resource_paths.items():
                source_css = source_css.replace(source_path, output_path)
            (res_dir / f"{BASENAME}.css").write_text(
                CSS + ("\n" + source_css if source_css else ""), encoding="utf-8", newline="\n",
            )
            for entry_index, expression in enumerate(expressions):
                article = _article_html(
                    expression, groups[expression], tag_mapping, resource_paths,
                ).encode("utf-8")
                if offset > 0xFFFFFFFF or len(article) > 0xFFFFFFFF or offset + len(article) > 0xFFFFFFFF:
                    raise ValueError("StarDict 2.4.2 offset limit exceeded")
                dictionary.write(article)
                encoded_expression = expression.encode("utf-8")
                if b"\0" in encoded_expression:
                    raise ValueError("headword contains NUL")
                index.write(encoded_expression + b"\0" + struct.pack(">II", offset, len(article)))
                for row in groups[expression]:
                    reading = row[1]
                    if isinstance(reading, str) and reading and reading != expression:
                        synonyms.append((reading, entry_index))
                offset += len(article)
            converted_images = 0
            for source_path in media:
                name = str(source_path)
                if name not in source_names:
                    raise ValueError(f"missing referenced media {name}")
                output_path = _goldendict_resource_path(source_path)
                destination = res_dir.joinpath(*output_path.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with source.open(name) as source_file:
                    converted_images += int(_write_resource(source_file, source_path, destination))
        synonyms = sorted(set(synonyms), key=lambda item: (_sort_key(item[0]), item[1]))
        if synonyms:
            with syn_path.open("wb") as synonym_file:
                for synonym, entry_index in synonyms:
                    encoded = synonym.encode("utf-8")
                    if b"\0" in encoded:
                        raise ValueError("reading contains NUL")
                    synonym_file.write(encoded + b"\0" + struct.pack(">I", entry_index))
        frequency_metadata = _frequency_metadata(connection, run_id)
        title = frequency_metadata[0] if frequency_metadata else PRODUCT_NAME
        description = frequency_metadata[2] if frequency_metadata else (
            "Производный русскоязычный словарь на основе Jitendex. "
            "Атрибуция Jitendex/JMdict/Tatoeba и условия CC BY-SA 4.0 сохранены."
        )
        ifo_lines = [
            "StarDict's dict ifo file", "version=2.4.2", f"bookname={_ifo_value(title)} (ja-ru)",
            f"wordcount={len(expressions)}", f"idxfilesize={idx_path.stat().st_size}",
        ]
        if synonyms:
            ifo_lines.append(f"synwordcount={len(synonyms)}")
        ifo_lines.extend([
            "sametypesequence=h", f"author={DICTIONARY_AUTHORS}",
            "website=https://ganqqwerty.github.io/jp-ru-kolobok-dictionary/", f"description={_ifo_value(description)}",
        ])
        (root / f"{BASENAME}.ifo").write_text("\n".join(ifo_lines) + "\n", encoding="utf-8", newline="\n")
        bundle_paths = sorted(
            ((path.relative_to(root).as_posix(), path) for path in root.rglob("*") if path.is_file()),
            key=lambda item: item[0],
        )
        manifest = _manifest(bundle_paths)
        fd, temporary_output_name = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
        os.close(fd)
        temporary_output = Path(temporary_output_name)
        try:
            with zipfile.ZipFile(temporary_output, "w", allowZip64=True) as archive:
                for name, path in bundle_paths:
                    _write_zip_member(archive, name, path)
            os.replace(temporary_output, output)
        finally:
            temporary_output.unlink(missing_ok=True)
    manifest_hash = sha256_bytes(canonical_json(manifest))
    zip_hash = sha256_file(output)
    cursor = connection.execute(
        """INSERT INTO export(run_id,output_path,manifest_sha256,zip_sha256)
        VALUES (?,?,?,?) RETURNING id""",
        (run_id, str(output), manifest_hash, zip_hash),
    )
    export_id = cursor.fetchone()[0]
    connection.executemany(
        "INSERT INTO export_file(export_id,path,sha256,byte_count) VALUES (?,?,?,?)",
        ((export_id, item["path"], item["sha256"], item["bytes"]) for item in manifest),
    )
    tag_summary = {
        "tag_catalog_version": catalog["version"],
        "tag_catalog_sha256": catalog["source_sha256"],
        "embedded_tag_occurrences": embedded["embedded_tag_occurrences"],
        "embedded_labels_replaced": embedded["embedded_labels_replaced"],
        "embedded_tooltips_replaced": embedded["embedded_tooltips_replaced"],
        "tag_bank_rows": len(catalog["tag_bank"]),
        "tag_bank_references_replaced": tag_bank_references_replaced,
    }
    audit(connection, "goldendict_build", "export", export_id, {
        "output": str(output), "zip_sha256": zip_hash, "format": "stardict-2.4.2", **tag_summary,
    })
    return {
        "export_id": export_id, "format": "stardict-2.4.2", "articles": len(rows),
        "headwords": len(expressions), "synonyms": len(synonyms), "files": len(manifest),
        "converted_images": converted_images, "zip_sha256": zip_hash, **tag_summary,
    }


def _parse_ifo(data: bytes) -> dict[str, str]:
    lines = data.decode("utf-8").splitlines()
    if not lines or lines[0] != "StarDict's dict ifo file":
        raise ValueError("invalid StarDict ifo header")
    values: dict[str, str] = {}
    for line in lines[1:]:
        key, separator, value = line.partition("=")
        if not separator or not key:
            raise ValueError("invalid StarDict ifo line")
        values[key] = value
    return values


def _parse_records(data: bytes, trailer_size: int) -> list[tuple[str, bytes]]:
    records: list[tuple[str, bytes]] = []
    position = 0
    while position < len(data):
        end = data.find(b"\0", position)
        if end < position or end + 1 + trailer_size > len(data):
            raise ValueError("truncated StarDict index record")
        try:
            word = data[position:end].decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("StarDict index contains invalid UTF-8") from error
        if not word:
            raise ValueError("StarDict index contains an empty word")
        trailer = data[end + 1:end + 1 + trailer_size]
        records.append((word, trailer))
        position = end + 1 + trailer_size
    return records


class _GoldenTagVerifier(HTMLParser):
    def __init__(self, catalog: dict[str, Any]):
        super().__init__(convert_charrefs=True)
        self.catalog = catalog
        self.tag_bank_by_label = {
            item["label_ru"]: item["description_ru"]
            for item in tag_bank_mapping(catalog).values()
        }
        self.capture: dict[str, Any] | None = None
        self.embedded_tag_occurrences = 0
        self.tag_bank_references = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.capture is not None:
            self.capture["depth"] += 1
            return
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if attributes.get("data-sc-class") == "tag":
            category = attributes.get("data-sc-content")
            code = attributes.get("data-sc-code", "")
            approved = self.catalog["embedded"].get((category, code))
            if approved is None:
                raise ValueError(f"GoldenDict contains an unapproved embedded tag {(category, code)}")
            if attributes.get("title") != approved["description_ru"]:
                raise ValueError(f"GoldenDict embedded tag tooltip differs from the catalog for {(category, code)}")
            self.capture = {"depth": 1, "expected": approved["label_ru"], "text": [], "kind": "embedded"}
        elif "jr-tag" in classes:
            self.capture = {
                "depth": 1, "expected_title": attributes.get("title"), "text": [], "kind": "tag_bank",
            }

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.capture is not None:
            self.capture["depth"] += 1
            self.capture["depth"] -= 1

    def handle_data(self, data: str) -> None:
        if self.capture is not None:
            self.capture["text"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.capture is None:
            return
        self.capture["depth"] -= 1
        if self.capture["depth"]:
            return
        text = "".join(self.capture["text"])
        if self.capture["kind"] == "embedded":
            if text != self.capture["expected"]:
                raise ValueError("GoldenDict embedded tag label differs from the approved catalog")
            self.embedded_tag_occurrences += 1
        else:
            expected_title = self.tag_bank_by_label.get(text)
            if expected_title is None or self.capture["expected_title"] != expected_title:
                raise ValueError(f"GoldenDict tag badge differs from the approved catalog: {text!r}")
            self.tag_bank_references += 1
        self.capture = None

    def finish(self) -> None:
        self.close()
        if self.capture is not None:
            raise ValueError("GoldenDict tag markup is truncated")


def verify_goldendict(connection: ConnectionLike, path: Path) -> dict[str, Any]:
    """Validate the StarDict structures and their recorded export hash."""
    zip_hash = sha256_file(path)
    export = connection.execute(
        """SELECT e.id,e.run_id,r.jitendex_snapshot_id FROM export e
        JOIN run r ON r.id=e.run_id
        WHERE e.output_path=? AND e.zip_sha256=? ORDER BY e.id DESC LIMIT 1""",
        (str(path), zip_hash),
    ).fetchone()
    if export is None:
        raise ValueError("bundle has no matching export record")
    catalog = load_approved_tag_catalog(connection, export["jitendex_snapshot_id"])
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("duplicate ZIP members")
        required = {f"{BASENAME}.ifo", f"{BASENAME}.idx", f"{BASENAME}.dict", f"res/{BASENAME}.css"}
        missing = required - set(names)
        if missing:
            raise ValueError(f"missing GoldenDict members: {sorted(missing)}")
        if any(PurePosixPath(name).suffix.lower() == ".avif" for name in names):
            raise ValueError("GoldenDict bundle contains an unconverted AVIF resource")
        info = _parse_ifo(archive.read(f"{BASENAME}.ifo"))
        if info.get("version") != "2.4.2" or info.get("sametypesequence") != "h":
            raise ValueError("unsupported StarDict metadata")
        index_data = archive.read(f"{BASENAME}.idx")
        if int(info.get("idxfilesize", -1)) != len(index_data):
            raise ValueError("StarDict idxfilesize mismatch")
        records = _parse_records(index_data, 8)
        if int(info.get("wordcount", -1)) != len(records):
            raise ValueError("StarDict wordcount mismatch")
        if [word for word, _ in records] != sorted((word for word, _ in records), key=_sort_key):
            raise ValueError("StarDict index is not sorted")
        dictionary_size = archive.getinfo(f"{BASENAME}.dict").file_size
        previous_end = 0
        for _word, trailer in records:
            offset, size = struct.unpack(">II", trailer)
            if offset != previous_end or offset + size > dictionary_size:
                raise ValueError("invalid StarDict article offset")
            previous_end = offset + size
        if previous_end != dictionary_size:
            raise ValueError("unindexed StarDict article data")
        tag_verifier = _GoldenTagVerifier(catalog)
        decoder = codecs.getincrementaldecoder("utf-8")()
        with archive.open(f"{BASENAME}.dict") as dictionary:
            for chunk in iter(lambda: dictionary.read(1024 * 1024), b""):
                tag_verifier.feed(decoder.decode(chunk))
        tag_verifier.feed(decoder.decode(b"", final=True))
        tag_verifier.finish()
        synonym_count = int(info.get("synwordcount", 0))
        if synonym_count:
            if f"{BASENAME}.syn" not in names:
                raise ValueError("missing StarDict synonym index")
            synonym_records = _parse_records(archive.read(f"{BASENAME}.syn"), 4)
            if len(synonym_records) != synonym_count:
                raise ValueError("StarDict synwordcount mismatch")
            if synonym_records != sorted(
                synonym_records, key=lambda item: (_sort_key(item[0]), struct.unpack(">I", item[1])[0]),
            ):
                raise ValueError("StarDict synonym index is not sorted")
            for _synonym, trailer in synonym_records:
                if struct.unpack(">I", trailer)[0] >= len(records):
                    raise ValueError("StarDict synonym points outside the index")
    connection.execute("UPDATE export SET verified=1 WHERE id=?", (export["id"],))
    return {
        "verified": True, "format": "stardict-2.4.2", "headwords": len(records),
        "synonyms": synonym_count, "files": len(names), "zip_sha256": zip_hash,
        "tag_catalog_version": catalog["version"],
        "tag_catalog_sha256": catalog["source_sha256"],
        "embedded_tag_occurrences": tag_verifier.embedded_tag_occurrences,
        "tag_bank_references": tag_verifier.tag_bank_references,
    }
