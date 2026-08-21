#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path


LOCAL_BASE_URL = "http://127.0.0.1:8766/"
OLD_REVISION = "2026.08.20.0-jp-ru-kolobok-400k-v1.0.0-local-smoke"


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_fixture(final_archive: Path, output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    old_archive = output_dir / "jp-ru-kolobok-400k-v1.0.0-local-smoke-yomitan.zip"
    served_final = output_dir / final_archive.name
    update_index = output_dir / "yomitan.json"

    with zipfile.ZipFile(final_archive) as source:
        final_index = json.loads(source.read("index.json"))
        old_index = dict(final_index)
        old_index.update({
            "revision": OLD_REVISION,
            "description": f'{final_index["description"]} Локальный smoke-fixture: старая версия.',
            "isUpdatable": True,
            "indexUrl": f"{LOCAL_BASE_URL}yomitan.json",
            "downloadUrl": f"{LOCAL_BASE_URL}{old_archive.name}",
        })
        with zipfile.ZipFile(old_archive, "w") as target:
            for info in source.infolist():
                payload = _canonical_json(old_index) if info.filename == "index.json" else source.read(info)
                target.writestr(info, payload)

    hosted_index = dict(final_index)
    hosted_index.update({
        "isUpdatable": True,
        "indexUrl": f"{LOCAL_BASE_URL}yomitan.json",
        "downloadUrl": f"{LOCAL_BASE_URL}{served_final.name}",
    })
    update_index.write_bytes(_canonical_json(hosted_index))
    shutil.copyfile(final_archive, served_final)

    serialized = json.dumps(hosted_index, ensure_ascii=False).lower()
    if "jitendex.org/static/yomitan.json" in serialized or "jitendex-yomitan.zip" in serialized:
        raise ValueError("fixture contains a foreign operational endpoint")
    if old_index["title"] != final_index["title"]:
        raise ValueError("fixture changed the stable installed title")

    return {
        "schema_version": 1,
        "base_url": LOCAL_BASE_URL,
        "old_archive": old_archive.name,
        "old_archive_sha256": _sha256(old_archive),
        "old_revision": old_index["revision"],
        "final_archive": served_final.name,
        "final_archive_sha256": _sha256(served_final),
        "final_revision": hosted_index["revision"],
        "index": update_index.name,
        "index_sha256": _sha256(update_index),
        "title": hosted_index["title"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("final_archive", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    report = prepare_fixture(args.final_archive.resolve(), args.output_dir.resolve())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
