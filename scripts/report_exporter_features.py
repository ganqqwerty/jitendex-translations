#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import zipfile
from collections import Counter
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import parse_qs, urlsplit

from jitendex_ru.util import canonical_json, sha256_file

TERM_BANK_RE = re.compile(r"term_bank_(\d+)\.json")
MEDIA_SUFFIXES = {".avif", ".gif", ".jpeg", ".jpg", ".mp3", ".ogg", ".png", ".svg", ".webp"}


def _bank_key(name: str) -> int:
    match = TERM_BANK_RE.fullmatch(name)
    if match is None:
        raise ValueError(f"invalid term bank name: {name}")
    return int(match.group(1))


def _walk(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _link_kind(value: str) -> str:
    split = urlsplit(value)
    if not split.scheme and not split.netloc and parse_qs(split.query).get("query"):
        return "dictionary-query"
    if split.scheme in {"http", "https"}:
        return "external-http"
    if split.scheme:
        return f"scheme-{split.scheme.lower()}"
    return "relative"


def inspect_archive(path: Path) -> dict[str, Any]:
    counts: dict[str, Counter[str]] = {
        "node_types": Counter(),
        "tags": Counter(),
        "data_classes": Counter(),
        "data_content": Counter(),
        "data_keys": Counter(),
        "style_properties": Counter(),
        "link_kinds": Counter(),
        "image_properties": Counter(),
        "media_suffixes": Counter(),
        "row_tag_codes": Counter(),
        "row_rule_codes": Counter(),
    }
    article_count = 0
    expressions: set[str] = set()
    readings: set[str] = set()
    max_row_bytes = 0
    max_expression_bytes = 0
    max_reading_bytes = 0
    max_glossary_items = 0
    structured_nodes = 0
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        banks = sorted((name for name in names if TERM_BANK_RE.fullmatch(name)), key=_bank_key)
        for name in names:
            suffix = PurePosixPath(name).suffix.lower()
            if suffix in MEDIA_SUFFIXES:
                counts["media_suffixes"][suffix.lstrip(".")] += 1
        for bank in banks:
            rows = json.loads(archive.read(bank))
            if not isinstance(rows, list):
                raise ValueError(f"{bank} is not an array")  # noqa: TRY004
            for row in rows:
                if not isinstance(row, list) or len(row) < 8:
                    raise ValueError(f"invalid row in {bank}")
                article_count += 1
                expression = row[0]
                reading = row[1]
                if isinstance(expression, str):
                    expressions.add(expression)
                    max_expression_bytes = max(max_expression_bytes, len(expression.encode("utf-8")))
                if isinstance(reading, str) and reading:
                    readings.add(reading)
                    max_reading_bytes = max(max_reading_bytes, len(reading.encode("utf-8")))
                max_row_bytes = max(max_row_bytes, len(canonical_json(row)))
                glossary = row[5]
                if isinstance(glossary, list):
                    max_glossary_items = max(max_glossary_items, len(glossary))
                for field, counter_name in ((row[2], "row_tag_codes"), (row[3], "row_rule_codes"), (row[7], "row_tag_codes")):
                    if isinstance(field, str):
                        counts[counter_name].update(code for code in field.split() if code)
                for node in _walk(glossary):
                    structured_nodes += 1
                    node_type = node.get("type")
                    if isinstance(node_type, str):
                        counts["node_types"][node_type] += 1
                    tag = node.get("tag")
                    if isinstance(tag, str):
                        counts["tags"][tag] += 1
                    data = node.get("data")
                    if isinstance(data, dict):
                        counts["data_keys"].update(str(key) for key in data)
                        if isinstance(data.get("class"), str):
                            counts["data_classes"][data["class"]] += 1
                        if isinstance(data.get("content"), str):
                            counts["data_content"][data["content"]] += 1
                    style = node.get("style")
                    if isinstance(style, dict):
                        counts["style_properties"].update(str(key) for key in style)
                    href = node.get("href")
                    if isinstance(href, str):
                        counts["link_kinds"][_link_kind(href)] += 1
                    if tag == "img":
                        for key in (
                            "appearance", "background", "collapsed", "collapsible", "height",
                            "path", "sizeUnits", "title", "width",
                        ):
                            if key in node:
                                counts["image_properties"][key] += 1
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "archive_members": len(names),
        "term_banks": len(banks),
        "articles": article_count,
        "unique_expressions": len(expressions),
        "unique_readings": len(readings),
        "structured_nodes": structured_nodes,
        "max_row_bytes": max_row_bytes,
        "max_expression_bytes": max_expression_bytes,
        "max_reading_bytes": max_reading_bytes,
        "max_glossary_items": max_glossary_items,
        **{name: dict(sorted(counter.items())) for name, counter in counts.items()},
    }


def _table(title: str, prefix: str, values: dict[str, int]) -> list[str]:
    lines = [f"## {prefix} — {title}", "", "| ID | Feature | Count |", "|---|---|---:|"]
    for index, (name, count) in enumerate(sorted(values.items()), start=1):
        lines.append(f"| {prefix}-{index:03d} | `{name}` | {count:,} |")
    lines.append("")
    return lines


def render_markdown(source: dict[str, Any], translated: dict[str, Any]) -> str:
    lines = [
        "# EXPINV — Exporter Source Feature Inventory",
        "",
        "## EXPINV-SCOPE — Scope",
        "",
        f"EXPINV-SCOPE-1 — Source archive: `{source['path']}`, SHA-256 `{source['sha256']}`.",
        "",
        f"EXPINV-SCOPE-2 — Translated archive: `{translated['path']}`, SHA-256 `{translated['sha256']}`.",
        "",
        "EXPINV-SCOPE-3 — Counts below use the translated archive. Source and translated structural totals are compared first.",
        "",
        "## EXPINV-SUM — Structural totals",
        "",
        "| ID | Measure | Source | Translated |",
        "|---|---|---:|---:|",
    ]
    measures = (
        "archive_members", "term_banks", "articles", "unique_expressions", "unique_readings",
        "structured_nodes", "max_row_bytes", "max_expression_bytes", "max_reading_bytes",
        "max_glossary_items",
    )
    for index, measure in enumerate(measures, start=1):
        lines.append(
            f"| EXPINV-SUM-{index} | `{measure}` | {source[measure]:,} | {translated[measure]:,} |"
        )
    lines.append("")
    sections = (
        ("Structured node types", "EXPINV-TYPE", "node_types"),
        ("Structured tags", "EXPINV-TAG", "tags"),
        ("Semantic classes", "EXPINV-CLASS", "data_classes"),
        ("Semantic content names", "EXPINV-CONT", "data_content"),
        ("Semantic data keys", "EXPINV-DATA", "data_keys"),
        ("Inline style properties", "EXPINV-STYLE", "style_properties"),
        ("Link forms", "EXPINV-LINK", "link_kinds"),
        ("Image properties", "EXPINV-IMG", "image_properties"),
        ("Archive media codecs", "EXPINV-MEDIA", "media_suffixes"),
        ("Term tag codes", "EXPINV-TCODE", "row_tag_codes"),
        ("Inflection rule codes", "EXPINV-RULE", "row_rule_codes"),
    )
    for title, prefix, key in sections:
        lines.extend(_table(title, prefix, translated[key]))
    lines.extend([
        "## EXPINV-GATE — Mapping gate",
        "",
        "EXPINV-GATE-1 — Every tag, semantic value, style property, link form, image property, and media codec above needs a target mapping or an explicit build failure.",
        "",
        "EXPINV-GATE-2 — Exporter tests must compare their handled feature set with this inventory before a full release.",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--translated", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = inspect_archive(args.source.resolve())
    translated = inspect_archive(args.translated.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_markdown(source, translated), encoding="utf-8", newline="\n")
    args.output.with_suffix(".json").write_bytes(canonical_json({"source": source, "translated": translated}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
