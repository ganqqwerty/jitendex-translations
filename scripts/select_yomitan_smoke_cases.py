#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterator


TERM_BANK_RE = re.compile(r"term_bank_(\d+)\.json")
TARGET_TEXT = {
    "brand": "операционная система Windows компании Microsoft",
    "taxon": "чавыча (Oncorhynchus tshawytscha), королевский лосось",
    "acronym": "синий экран смерти (экран ошибки Windows); BSoD",
    "quoted_english_grammar": "У слова «that» только два падежа",
    "mixed_alphabet_repair": (
        "Мы вчера вечером, выпив, ходили по всему городу и вовсю кутили."
    ),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _nodes(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _nodes(child)


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)


def _case(row: list[Any], member: str, row_index: int, evidence: str) -> dict[str, Any]:
    return {
        "expression": row[0],
        "reading": row[1],
        "member": member,
        "row": row_index,
        "evidence": evidence,
    }


def select_cases(archive_path: Path) -> dict[str, Any]:
    cases: dict[str, dict[str, Any]] = {}
    readings: dict[str, set[str]] = defaultdict(set)
    longest: dict[str, Any] | None = None
    with zipfile.ZipFile(archive_path) as archive:
        members = sorted(
            (name for name in archive.namelist() if TERM_BANK_RE.fullmatch(name)),
            key=lambda name: int(TERM_BANK_RE.fullmatch(name).group(1)),  # type: ignore[union-attr]
        )
        for member in members:
            for row_index, row in enumerate(json.loads(archive.read(member))):
                expression, reading = row[0], row[1]
                if expression in {"食べる", "ありがとう", "生"}:
                    readings[expression].add(reading)
                serialized_chars = len(
                    json.dumps(row[5], ensure_ascii=False, separators=(",", ":")),
                )
                if longest is None or serialized_chars > longest["serialized_chars"]:
                    longest = {
                        **_case(row, member, row_index, "largest structured glossary"),
                        "serialized_chars": serialized_chars,
                    }

                nodes = list(_nodes(row[5]))
                strings = list(_strings(row[5]))
                if expression == "悪どい":
                    if any(
                        isinstance(node.get("data"), dict)
                        and node["data"].get("content") == "xref"
                        for node in nodes
                    ):
                        cases.setdefault("xref", _case(row, member, row_index, "data.content=xref"))
                    hrefs = []
                    for node in nodes:
                        if node.get("tag") != "a":
                            continue
                        data = node.get("data") if isinstance(node.get("data"), dict) else {}
                        href = node.get("href") or data.get("href")
                        if isinstance(href, str):
                            hrefs.append(href)
                    if any(href.startswith("?query=") for href in hrefs) and any(
                        href.startswith("http") for href in hrefs
                    ):
                        cases.setdefault(
                            "links",
                            _case(row, member, row_index, "internal dictionary and external attribution links"),
                        )
                    if "JMdict" in strings:
                        cases.setdefault(
                            "jmdict_attribution",
                            _case(row, member, row_index, "JMdict attribution is visible"),
                        )
                if expression == "明白" and reading == "めいはく" and any(
                    node.get("tag") == "ruby" for node in nodes
                ):
                    cases.setdefault("ruby", _case(row, member, row_index, "tag=ruby"))
                if expression == "ＣＤプレーヤー":
                    if any(
                        isinstance(node.get("data"), dict)
                        and node["data"].get("content") == "example-sentence"
                        for node in nodes
                    ):
                        cases.setdefault(
                            "example_and_tatoeba",
                            _case(row, member, row_index, "example sentence with Tatoeba attribution"),
                        )
                    if any(node.get("tag") == "table" for node in nodes):
                        cases.setdefault("table", _case(row, member, row_index, "tag=table"))
                if expression == "スベタ":
                    source_form = next(
                        (
                            node.get("content")
                            for node in nodes
                            if isinstance(node.get("data"), dict)
                            and node["data"].get("content") == "lang-source-content"
                        ),
                        None,
                    )
                    if isinstance(source_form, str) and "espada" in source_form:
                        cases.setdefault(
                            "source_language_form",
                            _case(row, member, row_index, source_form),
                        )

                for key, needle in TARGET_TEXT.items():
                    match = next((text for text in strings if needle in text), None)
                    if match is not None:
                        cases.setdefault(key, _case(row, member, row_index, match))
                if expression == "社会情報學" and "вариант написания: 社会情報學" in strings:
                    cases.setdefault(
                        "redirect_localization",
                        _case(row, member, row_index, "вариант написания: 社会情報學"),
                    )
                restriction_targets = {
                    "中２": ("numeric_restriction", "только 中２・中二"),
                    "オメガ": ("greek_restriction", "только Ω"),
                    "アンド": ("fullwidth_restriction", "только ＡＮＤ"),
                }
                if expression in restriction_targets:
                    key, label = restriction_targets[expression]
                    if label in strings and "допустимо только для этих форм и/или чтений" in strings:
                        cases.setdefault(
                            key,
                            _case(
                                row,
                                member,
                                row_index,
                                f"{label}; tooltip: допустимо только для этих форм и/или чтений",
                            ),
                        )

    basic = {
        "expression_lookup": {"query": "食べる", "expected_expression": "食べる"},
        "reading_lookup": {"query": "たべる", "expected_expression": "食べる"},
        "inflected_lookup": {"query": "食べました", "expected_expression": "食べる"},
        "kana_only_lookup": {"query": "ありがとう", "expected_expression": "ありがとう"},
        "multiple_readings": {"query": "生", "expected_readings": sorted(readings["生"])},
    }
    if readings["食べる"] != {"たべる"} or readings["ありがとう"] != {"ありがとう"}:
        raise ValueError("basic lookup fixtures are missing from the archive")
    required_cases = {
        "xref", "links", "ruby", "example_and_tatoeba", "table",
        "jmdict_attribution", "source_language_form",
        "brand", "taxon", "acronym", "quoted_english_grammar",
        "mixed_alphabet_repair", "redirect_localization", "numeric_restriction",
        "greek_restriction", "fullwidth_restriction",
    }
    missing = sorted(required_cases - cases.keys())
    if missing or longest is None:
        raise ValueError(f"missing Yomitan smoke cases: {missing}")
    return {
        "schema_version": 1,
        "archive": archive_path.name,
        "archive_sha256": _sha256(archive_path),
        "basic_lookups": basic,
        "render_cases": cases,
        "long_entry": longest,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = select_cases(args.archive.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
