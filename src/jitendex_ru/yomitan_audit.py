from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any

from .database import ConnectionLike
from .util import atomic_write, canonical_json, sha256_bytes, sha256_file
from .yomitan_remediation import (
    APPROVED_LEXICAL_REMEDIATIONS, FORMS_TOOLTIP_SOURCE, MIXED_ALPHABET_RE, REDIRECT_SOURCE_PREFIX,
    UNFINISHED_TARGET_TEXTS,
    VISIBLE_TOKEN_RE, scan_yomitan_rows,
)


DETECTOR_VERSION = "yomitan-visible-text-v3"
TEMPLATE_SAMPLE_LIMIT = 10


def _target_leaves(role: str, target_text: str) -> list[tuple[str, str]]:
    if role != "glossary_set":
        return [("", target_text)]
    value = json.loads(target_text)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("glossary_set target is not an array of strings")
    return [(f"/{index}", item) for index, item in enumerate(value)]


def audit_yomitan_database(
    connection: ConnectionLike, run_id: int, *, archive_path: Path | None = None,
) -> dict[str, Any]:
    """Audit accepted targets with stable database identities and hashes."""
    run = connection.execute(
        """SELECT r.id,ss.sha256 source_snapshot_sha256
        FROM run r JOIN source_snapshot ss ON ss.id=r.jitendex_snapshot_id
        WHERE r.id=?""",
        (run_id,),
    ).fetchone()
    if run is None:
        raise ValueError(f"unknown run {run_id}")
    rows = connection.execute(
        """SELECT tu.id unit_id,tu.article_id,tu.json_pointer,tu.role,
        tu.source_text,tu.source_sha256,tu.protected_tokens_json,
        t.target_text,t.target_sha256
        FROM translation_unit tu
        JOIN translation t ON t.unit_id=tu.id AND t.run_id=tu.run_id AND t.accepted=1
        WHERE tu.run_id=? ORDER BY tu.article_id,tu.id""",
        (run_id,),
    )
    findings: list[dict[str, Any]] = []
    accepted_targets = 0
    for row in rows:
        accepted_targets += 1
        approved_target = APPROVED_LEXICAL_REMEDIATIONS.get(row["source_text"])
        if approved_target is not None and row["target_text"] in UNFINISHED_TARGET_TEXTS:
            findings.append({
                "run_id": run_id,
                "article_id": row["article_id"],
                "unit_id": row["unit_id"],
                "json_pointer": row["json_pointer"],
                "target_pointer": "",
                "role": row["role"],
                "source_text": row["source_text"],
                "source_sha256": row["source_sha256"],
                "current_target": row["target_text"],
                "target_sha256": row["target_sha256"],
                "detected_token": None,
                "issue_code": "approved_residual_english_remediation",
            })
        for target_pointer, text in _target_leaves(row["role"], row["target_text"]):
            codes_and_tokens: list[tuple[str, str | None]] = []
            if text.startswith(REDIRECT_SOURCE_PREFIX):
                codes_and_tokens.append(("raw_ui_template", REDIRECT_SOURCE_PREFIX.strip()))
            if text == FORMS_TOOLTIP_SOURCE:
                codes_and_tokens.append(("raw_ui_template", FORMS_TOOLTIP_SOURCE))
            for token in VISIBLE_TOKEN_RE.findall(text):
                if MIXED_ALPHABET_RE.search(token):
                    codes_and_tokens.append(("mixed_alphabet_token", token))
            for code, token in codes_and_tokens:
                findings.append({
                    "run_id": run_id,
                    "article_id": row["article_id"],
                    "unit_id": row["unit_id"],
                    "json_pointer": row["json_pointer"],
                    "target_pointer": target_pointer,
                    "role": row["role"],
                    "source_text": row["source_text"],
                    "source_sha256": row["source_sha256"],
                    "current_target": row["target_text"],
                    "target_sha256": row["target_sha256"],
                    "detected_token": token,
                    "issue_code": code,
                })
    counts: dict[str, int] = {}
    for finding in findings:
        code = finding["issue_code"]
        counts[code] = counts.get(code, 0) + 1
    return {
        "schema_version": 1,
        "detector_version": DETECTOR_VERSION,
        "run_id": run_id,
        "source_snapshot_sha256": run["source_snapshot_sha256"],
        "archive_filename": archive_path.name if archive_path else None,
        "archive_sha256": sha256_file(archive_path) if archive_path else None,
        "accepted_target_count": accepted_targets,
        "issue_counts": counts,
        "findings": findings,
    }


def write_yomitan_database_audit(
    connection: ConnectionLike, run_id: int, output: Path, *, archive_path: Path | None = None,
) -> dict[str, Any]:
    report = audit_yomitan_database(connection, run_id, archive_path=archive_path)
    atomic_write(output, canonical_json(report) + b"\n")
    return report


def audit_yomitan_archive(path: Path, *, run_id: int | None = None) -> dict[str, Any]:
    """Audit a Yomitan ZIP without requiring database access or worker agents."""
    counts: dict[str, int] = {}
    findings: list[dict[str, Any]] = []
    samples: dict[str, list[dict[str, Any]]] = {}
    article_count = 0
    classification_counts = {"MUST_TRANSLATE": 0, "MUST_PRESERVE": 0, "REVIEW": 0}
    preserve_rule_counts: dict[str, int] = {}
    review_groups: dict[str, dict[str, Any]] = {}
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
            for classification, count in scan["classification_counts"].items():
                classification_counts[classification] += count
            for rule, count in scan["must_preserve_rule_counts"].items():
                preserve_rule_counts[rule] = preserve_rule_counts.get(rule, 0) + count
            for review in scan["review_records"]:
                identity = review["identity_sha256"]
                group = review_groups.setdefault(identity, {
                    "identity_sha256": identity,
                    "text": review["text"],
                    "selector": review["selector"],
                    "lang": review["lang"],
                    "occurrences": 0,
                    "reason": "Reviewed Russian prose with an intentional brand, taxon, acronym, romanized term, quotation, or creator identity.",
                })
                group["occurrences"] += 1
            for issue in scan["issues"]:
                enriched = {"member": member, **issue}
                if issue["code"] == "mixed_alphabet_token":
                    findings.append(enriched)
                elif len(samples.setdefault(issue["code"], [])) < TEMPLATE_SAMPLE_LIMIT:
                    samples[issue["code"]].append(enriched)
    version_match = re.search(r"(?:^|-)v(\d+(?:\.\d+)+)(?:-|$)", str(index.get("revision", "")))
    review_records = sorted(review_groups.values(), key=lambda item: item["identity_sha256"])
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
        "classification_counts": classification_counts,
        "must_preserve_rule_counts": preserve_rule_counts,
        "review_records": review_records,
        "review_records_sha256": sha256_bytes(canonical_json(review_records)),
    }


def write_yomitan_archive_audit(
    path: Path, output: Path, *, run_id: int | None = None,
) -> dict[str, Any]:
    report = audit_yomitan_archive(path, run_id=run_id)
    atomic_write(output, canonical_json(report) + b"\n")
    return report


def write_yomitan_visible_latin_approval(path: Path, output: Path) -> dict[str, Any]:
    report = audit_yomitan_archive(path)
    if report["classification_counts"]["MUST_TRANSLATE"] or report["issue_counts"]:
        raise ValueError("cannot approve visible Latin while MUST_TRANSLATE issues remain")
    approval = {
        "schema_version": 1,
        "detector_version": report["detector_version"],
        "reviewer": "main-thread-manual-and-scripted-review",
        "source_archive_sha256": report["archive_sha256"],
        "classification_counts": report["classification_counts"],
        "must_preserve_rule_counts": report["must_preserve_rule_counts"],
        "review_records_sha256": report["review_records_sha256"],
        "review_records": report["review_records"],
    }
    atomic_write(output, canonical_json(approval) + b"\n")
    return approval


def verify_yomitan_visible_latin_approval(
    path: Path, approval_path: Path,
) -> dict[str, Any]:
    report = audit_yomitan_archive(path)
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    if report["classification_counts"]["MUST_TRANSLATE"] or report["issue_counts"]:
        raise ValueError("visible-Latin release gate has MUST_TRANSLATE issues")
    for key in (
        "detector_version", "classification_counts", "must_preserve_rule_counts",
        "review_records_sha256",
    ):
        if approval.get(key) != report.get(key):
            raise ValueError(f"visible-Latin approval mismatch for {key}")
    if approval.get("review_records") != report["review_records"]:
        raise ValueError("visible-Latin approval records do not match the archive")
    return {
        "visible_latin_approved": True,
        "classification_counts": report["classification_counts"],
        "must_preserve_rule_counts": report["must_preserve_rule_counts"],
        "review_records_sha256": report["review_records_sha256"],
    }
