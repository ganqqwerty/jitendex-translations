#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable

from mdict_utils.reader import MDX

from jitendex_ru.build_dictionary import materialize_localized_run
from jitendex_ru.config import Config
from jitendex_ru.database import Database
from jitendex_ru.util import canonical_json, sha256_file
from jitendex_ru.yomitan_remediation import (
    FORMS_TOOLTIP_SOURCE,
    REDIRECT_SOURCE_PREFIX,
    scan_yomitan_rows,
)


FORBIDDEN_TEMPLATES = (REDIRECT_SOURCE_PREFIX, FORMS_TOOLTIP_SOURCE)


def _zip_payloads(path: Path) -> Iterable[bytes]:
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name.endswith("/"):
                continue
            yield archive.read(name)


def _mdict_records(path: Path) -> Iterable[bytes]:
    with tempfile.TemporaryDirectory(prefix="rich-audit-") as temporary:
        destination = Path(temporary) / "dictionary.mdx"
        with zipfile.ZipFile(path) as archive:
            member = next(name for name in archive.namelist() if name.endswith(".mdx"))
            destination.write_bytes(archive.read(member))
        for _key, value in MDX(str(destination)).items():
            yield value


def _template_counts(payloads: Iterable[bytes]) -> dict[str, int]:
    encoded = {template: template.casefold().encode("utf-8") for template in FORBIDDEN_TEMPLATES}
    counts = {template: 0 for template in FORBIDDEN_TEMPLATES}
    for payload in payloads:
        folded = payload.lower()
        for template, token in encoded.items():
            counts[template] += folded.count(token)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--yomitan", type=Path, required=True)
    parser.add_argument("--goldendict", type=Path, required=True)
    parser.add_argument("--mdict", type=Path, required=True)
    parser.add_argument("--pocketbook", type=Path, required=True)
    parser.add_argument("--apple", type=Path, required=True)
    parser.add_argument("--visible-latin-approval", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    database = Database(Config.load(args.config))
    connection = database.connect()
    try:
        _run, _source, rows, localization = materialize_localized_run(connection, args.run_id)
        source_scan = scan_yomitan_rows(rows)
    finally:
        connection.close()
        database.close()
    if source_scan["issue_counts"]:
        raise ValueError(f"shared rich-source localization gate failed: {source_scan['issue_counts']}")

    archives = {
        "yomitan": args.yomitan,
        "goldendict": args.goldendict,
        "mdict": args.mdict,
        "pocketbook": args.pocketbook,
        "apple_dictionary": args.apple,
    }
    artifact_results: dict[str, object] = {}
    for name, path in archives.items():
        counts = _template_counts(_zip_payloads(path))
        if name == "mdict":
            decoded = _template_counts(_mdict_records(path))
            counts = {template: counts[template] + decoded[template] for template in counts}
        if any(counts.values()):
            raise ValueError(f"{name} retains source templates: {counts}")
        artifact_results[name] = {
            "path": path.as_posix(),
            "sha256": sha256_file(path),
            "raw_template_counts": counts,
        }

    report = {
        "schema_version": 1,
        "run_id": args.run_id,
        "articles_scanned": len(rows),
        "shared_source_issue_counts": source_scan["issue_counts"],
        "shared_source_localization_counts": localization,
        "visible_latin_approval_sha256": sha256_file(args.visible_latin_approval),
        "artifacts": artifact_results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json(report) + b"\n")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
