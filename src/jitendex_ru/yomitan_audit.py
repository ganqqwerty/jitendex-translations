from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any

from .util import atomic_write, canonical_json, sha256_file
from .yomitan_remediation import scan_yomitan_rows


DETECTOR_VERSION = "yomitan-visible-text-v1"
TEMPLATE_SAMPLE_LIMIT = 10


def audit_yomitan_archive(path: Path, *, run_id: int | None = None) -> dict[str, Any]:
    """Audit a Yomitan ZIP without requiring database access or worker agents."""
    counts: dict[str, int] = {}
    findings: list[dict[str, Any]] = []
    samples: dict[str, list[dict[str, Any]]] = {}
    article_count = 0
    with zipfile.ZipFile(path) as archive:
        index = json.loads(archive.read("index.json"))
        term_names = sorted(
            (name for name in archive.namelist() if re.fullmatch(r"term_bank_\d+\.json", name)),
            key=lambda name: int(re.search(r"\d+", name)[0]),
        )
        for member in term_names:
            rows = json.loads(archive.read(member))
            article_count += len(rows)
            scan = scan_yomitan_rows(rows)
            for code, count in scan["issue_counts"].items():
                counts[code] = counts.get(code, 0) + count
            for issue in scan["issues"]:
                enriched = {"member": member, **issue}
                if issue["code"] == "mixed_alphabet_token":
                    findings.append(enriched)
                elif len(samples.setdefault(issue["code"], [])) < TEMPLATE_SAMPLE_LIMIT:
                    samples[issue["code"]].append(enriched)
    version_match = re.search(r"(?:^|-)v(\d+(?:\.\d+)+)(?:-|$)", str(index.get("revision", "")))
    return {
        "schema_version": 1,
        "detector_version": DETECTOR_VERSION,
        "archive_dictionary_version": version_match.group(1) if version_match else None,
        "run_id": run_id,
        "archive_filename": path.name,
        "archive_sha256": sha256_file(path),
        "article_count": article_count,
        "index": index,
        "issue_counts": counts,
        "template_samples": samples,
        "mixed_alphabet_findings": findings,
    }


def write_yomitan_archive_audit(
    path: Path, output: Path, *, run_id: int | None = None,
) -> dict[str, Any]:
    report = audit_yomitan_archive(path, run_id=run_id)
    atomic_write(output, canonical_json(report) + b"\n")
    return report
