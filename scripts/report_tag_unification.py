#!/usr/bin/env python3
"""Compare a historical Yomitan export with its catalog-localized replacement."""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

from jitendex_ru.config import Config
from jitendex_ru.database import Database
from jitendex_ru.jitendex_tags import (
    load_approved_tag_catalog, localize_embedded_tags,
    tag_bank_mapping, verify_localized_embedded_tags, verify_localized_tag_bank_rows,
    verify_localized_term_tag_references,
)
from jitendex_ru.util import atomic_write, sha256_file


ROOT = Path(__file__).resolve().parents[1]
TERM_BANK_RE = re.compile(r"term_bank_(\d+)\.json")
TAG_BANK_RE = re.compile(r"tag_bank_(\d+)\.json")


def _merge_embedded(target: dict[tuple[str, str], dict[str, Any]], report: dict[str, Any]) -> None:
    for item in report["embedded_tags"]:
        key = (item["category"], item["code"])
        merged = target.setdefault(key, {
            key: item[key] for key in (
                "source_kind", "category", "code", "approved_label_ru", "approved_description_ru",
            )
        })
        merged["occurrences"] = merged.get("occurrences", 0) + item["occurrences"]
        for field in ("label_variants", "tooltip_variants"):
            variants = Counter(merged.get(field, {}))
            variants.update(item[field])
            merged[field] = dict(sorted(variants.items()))


def _scan_archive(path: Path, catalog: dict[str, Any], *, localized: bool) -> dict[str, Any]:
    embedded: dict[tuple[str, str], dict[str, Any]] = {}
    labels_replaced = 0
    tooltips_replaced = 0
    references: Counter[str] = Counter()
    references_rewritten = 0
    reference_fields_rewritten = 0
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        tag_names = sorted(
            (name for name in names if TAG_BANK_RE.fullmatch(name)),
            key=lambda name: int(TAG_BANK_RE.fullmatch(name).group(1)),
        )
        tag_rows = [row for name in tag_names for row in json.loads(archive.read(name))]
        tag_bank_rows: dict[str, dict[str, str]] = {}
        if localized:
            mapping = verify_localized_tag_bank_rows(tag_rows, catalog)
            reverse = {item["encoded_label_ru"]: code for code, item in mapping.items()}
            for row in tag_rows:
                code = reverse[row[0]]
                tag_bank_rows[code] = {"label": row[0], "description": row[3]}
        else:
            mapping = tag_bank_mapping(catalog)
            reverse = {code: code for code in mapping}
            seen: set[str] = set()
            for row in tag_rows:
                if len(row) < 4 or not all(isinstance(row[index], str) for index in (0, 1, 3)):
                    raise ValueError("historical archive contains an invalid tag-bank row")
                code = row[0]
                approved = catalog["tag_bank"].get(code)
                if approved is None or row[1] != approved["category"] or code in seen:
                    raise ValueError(f"historical archive has an unknown or duplicate tag-bank row {code!r}")
                seen.add(code)
                tag_bank_rows[code] = {"label": row[0], "description": row[3]}
            missing = set(mapping) - seen
            if missing:
                raise ValueError(f"historical archive lacks tag-bank rows: {sorted(missing)}")
        term_names = sorted(
            (name for name in names if TERM_BANK_RE.fullmatch(name)),
            key=lambda name: int(TERM_BANK_RE.fullmatch(name).group(1)),
        )
        articles = 0
        for name in term_names:
            rows = json.loads(archive.read(name))
            articles += len(rows)
            report = (
                verify_localized_embedded_tags(rows, catalog)
                if localized else localize_embedded_tags(rows, catalog)
            )
            _merge_embedded(embedded, report)
            labels_replaced += report["embedded_labels_replaced"]
            tooltips_replaced += report["embedded_tooltips_replaced"]
            if localized:
                verify_localized_term_tag_references(rows, mapping)
            for row in rows:
                for index in (2, 7):
                    value = row[index]
                    if not isinstance(value, str) or not value:
                        continue
                    tags = [item for item in value.split(" ") if item]
                    for tag in tags:
                        code = reverse.get(tag)
                        if code is None:
                            raise ValueError(f"archive contains an unknown tag-bank reference {tag!r}")
                        references[code] += 1
                    if not localized:
                        localized_tags = [mapping[tag]["encoded_label_ru"] for tag in tags]
                        references_rewritten += sum(
                            tag != localized_tag
                            for tag, localized_tag in zip(tags, localized_tags, strict=True)
                        )
                        reference_fields_rewritten += int(" ".join(localized_tags) != value)
    return {
        "path": str(path), "sha256": sha256_file(path), "articles": articles,
        "embedded_tag_occurrences": sum(item["occurrences"] for item in embedded.values()),
        "embedded_labels_replaced": labels_replaced,
        "embedded_tooltips_replaced": tooltips_replaced,
        "embedded_tags": [item for _key, item in sorted(embedded.items())],
        "tag_bank_rows": tag_bank_rows,
        "tag_bank_reference_counts": dict(sorted(references.items())),
        "tag_bank_references_rewritten": references_rewritten,
        "tag_bank_reference_fields_rewritten": reference_fields_rewritten,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "config.luna.toml")
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = Config.load(args.config)
    database = Database(config)
    connection = database.connect()
    try:
        run = connection.execute(
            "SELECT jitendex_snapshot_id FROM run WHERE id=?", (args.run_id,),
        ).fetchone()
        if run is None:
            raise ValueError(f"unknown run {args.run_id}")
        catalog = load_approved_tag_catalog(connection, run["jitendex_snapshot_id"])
        before = _scan_archive(args.before.resolve(), catalog, localized=False)
        after = _scan_archive(args.after.resolve(), catalog, localized=True)
        if before["articles"] != after["articles"]:
            raise ValueError("before/after archives contain different article counts")
        if before["embedded_tag_occurrences"] != after["embedded_tag_occurrences"]:
            raise ValueError("before/after archives contain different embedded tag counts")
        mapping = tag_bank_mapping(catalog)
        tag_bank = [
            {
                "code": code,
                "approved_label_ru": item["label_ru"],
                "approved_description_ru": item["description_ru"],
                "before_label": before["tag_bank_rows"][code]["label"],
                "before_description": before["tag_bank_rows"][code]["description"],
                "after_label": after["tag_bank_rows"][code]["label"],
                "after_description": after["tag_bank_rows"][code]["description"],
                "before_references": before["tag_bank_reference_counts"].get(code, 0),
                "after_references": after["tag_bank_reference_counts"].get(code, 0),
            }
            for code, item in sorted(mapping.items())
        ]
        payload = {
            "schema_version": 1, "run_id": args.run_id,
            "tag_catalog_version": catalog["version"],
            "tag_catalog_sha256": catalog["source_sha256"],
            "tag_catalog_path": catalog["source_path"],
            "summary": {
                "articles": after["articles"],
                "embedded_tag_occurrences": after["embedded_tag_occurrences"],
                "embedded_labels_replaced": before["embedded_labels_replaced"],
                "embedded_tooltips_replaced": before["embedded_tooltips_replaced"],
                "tag_bank_references": sum(before["tag_bank_reference_counts"].values()),
                "tag_bank_references_rewritten": before["tag_bank_references_rewritten"],
                "tag_bank_reference_fields_rewritten": before["tag_bank_reference_fields_rewritten"],
                "missing_mappings": 0,
            },
            "before": before, "after": after, "tag_bank": tag_bank,
        }
        atomic_write(
            args.output.resolve(),
            (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
        )
        print(json.dumps({
            "output": str(args.output.resolve()), **payload["summary"],
            "tag_catalog_sha256": catalog["source_sha256"],
        }, ensure_ascii=False, sort_keys=True))
        return 0
    finally:
        connection.close()
        database.close()


if __name__ == "__main__":
    raise SystemExit(main())
