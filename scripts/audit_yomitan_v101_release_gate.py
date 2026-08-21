#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

import fastjsonschema

from jitendex_ru.build_dictionary import YOMITAN_SMOKE_CHECKS
from jitendex_ru.yomitan_remediation import (
    RELEASE_DOWNLOAD_URL,
    UPDATE_INDEX_URL,
    validate_yomitan_metadata,
)


EXPECTED_ARTIFACTS = {
    "jp-ru-kolobok-400k-v1.0.1-yomitan.zip": (
        "f0e8a6d8823398401994d0c7738aee4dca83b225bf276f9b08282cafbbac68b7"
    ),
    "jp-ru-kolobok-400k-v1.0.1-goldendict.zip": (
        "506396de7a00009074d956a62fc66c56cf0f8645c0470ad1a75868b622c5be51"
    ),
    "jp-ru-kolobok-400k-v1.0.1-mdict.zip": (
        "f22238c020b7ddebfeffc2df83256816fc23e00e02042b3eff321ce8c5145b4d"
    ),
    "jp-ru-kolobok-400k-v1.0.1-pocketbook.zip": (
        "e757ea8ddde01a2380485c6f498610f86565dda2076a993e3c9c9611374d31cc"
    ),
    "jp-ru-kolobok-400k-v1.0.1-apple-dictionary.zip": (
        "57b828929cb674aeb1bc0be9c833aadfc4185ea81d40855a6cf20be93c150c1c"
    ),
}
REQUIRED_REPORTS = (
    "reports/exporters/run59-v1.0.1-apple-dictionary-build.json",
    "reports/exporters/run59-v1.0.1-apple-dictionary-verify.json",
    "reports/exporters/run59-v1.0.1-goldendict-build.json",
    "reports/exporters/run59-v1.0.1-goldendict-verify.json",
    "reports/exporters/run59-v1.0.1-mdict-build.json",
    "reports/exporters/run59-v1.0.1-mdict-verify.json",
    "reports/exporters/run59-v1.0.1-pocketbook-build.json",
    "reports/exporters/run59-v1.0.1-pocketbook-verify.json",
    "reports/exporters/run59-v1.0.1-rich-lexical-audit.json",
    "reports/yomitan_localization/run59-v1.0.1-final-yomitan-build.json",
    "reports/yomitan_localization/run59-v1.0.1-final-yomitan-verify.json",
    "reports/yomitan_localization/run59-v1.0.1-update-index-verify.json",
    "reports/yomitan_localization/run59-v1.0.1-smoke-cases.json",
    "reports/yomitan_localization/v1.0.1-release-notes.md",
)
FORBIDDEN_OPERATIONAL_TEXT = (
    "jitendex.org/static/yomitan.json",
    "jitendex-yomitan.zip",
    "github.com/stephenmk/",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_checksums(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        digest, filename = line.split(maxsplit=1)
        result[Path(filename.lstrip("* ")).name] = digest
    return result


def audit_release_gate(
    root: Path,
    *,
    schema: Path,
    smoke: Path,
    allow_manual_pending: bool,
) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    artifacts: dict[str, dict[str, Any]] = {}
    for filename, expected in EXPECTED_ARTIFACTS.items():
        path = root / "dist" / filename
        if not path.is_file():
            findings.append({"code": "missing_artifact", "path": str(path)})
            continue
        actual = _sha256(path)
        artifacts[filename] = {"bytes": path.stat().st_size, "sha256": actual}
        if actual != expected:
            findings.append({"code": "artifact_hash_mismatch", "path": str(path)})

    checksum_path = root / "dist" / "jp-ru-kolobok-400k-v1.0.1-SHA256SUMS.txt"
    if not checksum_path.is_file():
        findings.append({"code": "missing_checksum_manifest", "path": str(checksum_path)})
        checksums: dict[str, str] = {}
    else:
        checksums = _parse_checksums(checksum_path)
        if checksums != EXPECTED_ARTIFACTS:
            findings.append({"code": "checksum_manifest_mismatch", "path": str(checksum_path)})

    hosted_path = root / "site-home" / "yomitan.json"
    yomitan_path = root / "dist" / "jp-ru-kolobok-400k-v1.0.1-yomitan.zip"
    if hosted_path.is_file() and yomitan_path.is_file():
        hosted_raw = hosted_path.read_bytes()
        hosted = json.loads(hosted_raw)
        validate_yomitan_metadata(hosted, require_updatable=True)
        fastjsonschema.compile(json.loads(schema.read_text(encoding="utf-8")))(hosted)
        with zipfile.ZipFile(yomitan_path) as archive:
            archive_index_raw = archive.read("index.json")
        if hosted_raw != archive_index_raw:
            findings.append({"code": "hosted_archive_index_mismatch", "path": str(hosted_path)})
        if hosted.get("indexUrl") != UPDATE_INDEX_URL:
            findings.append({"code": "wrong_index_url", "path": str(hosted_path)})
        if hosted.get("downloadUrl") != RELEASE_DOWNLOAD_URL:
            findings.append({"code": "wrong_download_url", "path": str(hosted_path)})
    else:
        findings.append({"code": "missing_hosted_or_yomitan_index", "path": str(hosted_path)})
        hosted_raw = b""

    homepage_path = root / "site-home" / "index.html"
    homepage = homepage_path.read_text(encoding="utf-8") if homepage_path.is_file() else ""
    for filename in EXPECTED_ARTIFACTS:
        if f"releases/download/v1.0.1/{filename}" not in homepage:
            findings.append({"code": "homepage_missing_asset", "path": filename})
    if "один раз импортируйте его вручную" not in homepage:
        findings.append({"code": "homepage_missing_manual_upgrade_warning", "path": str(homepage_path)})
    operational_text = (hosted_raw.decode("utf-8", errors="replace") + "\n" + homepage).lower()
    for forbidden in FORBIDDEN_OPERATIONAL_TEXT:
        if forbidden in operational_text:
            findings.append({"code": "foreign_operational_endpoint", "path": forbidden})

    missing_reports = [relative for relative in REQUIRED_REPORTS if not (root / relative).is_file()]
    findings.extend({"code": "missing_report", "path": relative} for relative in missing_reports)

    manual_smoke = "passed"
    if not smoke.is_file():
        manual_smoke = "pending"
        if not allow_manual_pending:
            findings.append({"code": "manual_smoke_pending", "path": str(smoke)})
    else:
        payload = json.loads(smoke.read_text(encoding="utf-8"))
        checks = payload.get("checks")
        valid = (
            payload.get("schema_version") == 1
            and payload.get("zip_sha256") == EXPECTED_ARTIFACTS[
                "jp-ru-kolobok-400k-v1.0.1-yomitan.zip"
            ]
            and payload.get("clean_profile") is True
            and payload.get("imported") is True
            and isinstance(checks, dict)
            and set(checks) == YOMITAN_SMOKE_CHECKS
            and all(value is True for value in checks.values())
            and isinstance(payload.get("notes"), str)
        )
        if not valid:
            manual_smoke = "invalid"
            findings.append({"code": "invalid_manual_smoke", "path": str(smoke)})

    return {
        "schema_version": 1,
        "release": "v1.0.1",
        "artifacts": artifacts,
        "artifact_count": len(artifacts),
        "checksum_manifest_matches": checksums == EXPECTED_ARTIFACTS,
        "hosted_index_sha256": _sha256(hosted_path) if hosted_path.is_file() else None,
        "manual_smoke": manual_smoke,
        "required_report_count": len(REQUIRED_REPORTS),
        "missing_report_count": len(missing_reports),
        "findings": findings,
        "status": "ready_for_draft" if not findings and manual_smoke == "passed" else (
            "manual_smoke_pending" if not findings and manual_smoke == "pending" else "blocked"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--smoke", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-manual-pending", action="store_true")
    args = parser.parse_args()
    report = audit_release_gate(
        args.root.resolve(),
        schema=args.schema.resolve(),
        smoke=args.smoke.resolve(),
        allow_manual_pending=args.allow_manual_pending,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if report["status"] != "blocked" else 2


if __name__ == "__main__":
    sys.exit(main())
