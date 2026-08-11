from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .db import audit
from .util import ASCII_WORD_RE, CONTROL_RE, CYRILLIC_RE, LATIN_TAXON_RE, TAG_RE, canonical_json, sha256_bytes


class ValidationFailure(ValueError):
    def __init__(self, issues: list[dict[str, Any]]):
        super().__init__("response validation failed")
        self.issues = issues


def allows_japanese_grammar_label(role: str, source_text: str) -> bool:
    """Allow Japanese-only output when the source is itself a grammar label."""
    return role == "pos" and source_text.strip().lower() in {"suru"}


def _plain_text_issues(
    target: Any, protected: list[str], *, allow_no_cyrillic: bool = False,
) -> list[str]:
    issues: list[str] = []
    if not isinstance(target, str) or not target.strip():
        return ["empty_or_non_string"]
    if TAG_RE.search(target):
        issues.append("markup_detected")
    if CONTROL_RE.search(target):
        issues.append("control_character")
    for token in protected:
        if token not in target:
            issues.append("protected_token_missing")
            break
    if not allow_no_cyrillic and not CYRILLIC_RE.search(target):
        issues.append("no_cyrillic")
    unprotected = target
    for token in protected:
        unprotected = unprotected.replace(token, "")
    unprotected = LATIN_TAXON_RE.sub("", unprotected)
    if len(ASCII_WORD_RE.findall(unprotected)) > 2:
        issues.append("too_much_english")
    return issues


def target_storage(role: str, target: Any) -> str:
    if role == "glossary_set":
        if not isinstance(target, list):
            raise ValueError("glossary_set target must be an array")
        return canonical_json(target).decode()
    if not isinstance(target, str):
        raise ValueError("scalar target must be a string")
    return target


def validate_worker_payload(connection: sqlite3.Connection, attempt: sqlite3.Row, payload: Any) -> list[dict[str, Any]]:
    batch = connection.execute("SELECT * FROM batch WHERE id=?", (attempt["batch_id"],)).fetchone()
    issues: list[dict[str, Any]] = []
    if not isinstance(payload, dict):
        return [{"code": "invalid_shape"}]
    if set(payload) != {"schema_version", "batch_id", "manifest_sha256", "translations"}:
        issues.append({"code": "unexpected_top_level_fields"})
    run = connection.execute("SELECT pipeline_version FROM run WHERE id=?", (batch["run_id"],)).fetchone()
    expected_schema = 2 if run["pipeline_version"] == "lexicographer-v2" else 1
    if payload.get("schema_version") != expected_schema:
        issues.append({"code": "wrong_schema_version"})
    if payload.get("batch_id") != batch["id"]:
        issues.append({"code": "batch_id_mismatch"})
    if payload.get("manifest_sha256") != batch["manifest_sha256"]:
        issues.append({"code": "manifest_hash_mismatch"})
    expected = connection.execute(
        """SELECT tu.* FROM batch_item bi JOIN translation_unit tu ON tu.id=bi.unit_id
        WHERE bi.batch_id=? ORDER BY bi.ordinal""", (batch["id"],)
    ).fetchall()
    required_targets: dict[str, str] = {}
    manifest_path = Path(batch["manifest_path"])
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for article in manifest.get("articles", []):
            for unit in article.get("units", []):
                required = unit.get("required_terminology")
                if isinstance(required, dict) and isinstance(required.get("target_text"), str):
                    required_targets[unit["unit_id"]] = required["target_text"]
    translations = payload.get("translations")
    if not isinstance(translations, list):
        return issues + [{"code": "translations_not_array"}]
    actual_ids = [item.get("unit_id") for item in translations if isinstance(item, dict)]
    expected_ids = [row["id"] for row in expected]
    if actual_ids != expected_ids:
        issues.append({"code": "unit_order_or_set_mismatch", "expected": expected_ids, "actual": actual_ids})
        return issues
    for source, item in zip(expected, translations):
        if set(item) != {"unit_id", "source_sha256", "target_text", "confidence", "review_reason"}:
            issues.append({"code": "unexpected_translation_fields", "unit_id": source["id"]})
        if item.get("source_sha256") != source["source_sha256"]:
            issues.append({"code": "source_hash_mismatch", "unit_id": source["id"]})
        if item.get("confidence") not in {"high", "medium", "low"}:
            issues.append({"code": "invalid_confidence", "unit_id": source["id"]})
        if item.get("confidence") != "high" and not item.get("review_reason"):
            issues.append({"code": "missing_review_reason", "unit_id": source["id"]})
        target = item.get("target_text")
        required_target = required_targets.get(source["id"])
        # Approved whole-leaf terminology is strong generation guidance, but
        # an intermediate JPDB batch is not rejected solely for varying from
        # it. One deterministic pass canonicalizes these leaves and structured
        # tags in the final cumulative run before the definitive export.
        if source["role"] == "glossary_set":
            if not isinstance(target, list) or not 1 <= len(target) <= 12:
                issues.append({"code": "invalid_glossary_set", "unit_id": source["id"]})
                continue
            if len(set(target)) != len(target):
                issues.append({"code": "duplicate_glossary_definition", "unit_id": source["id"]})
            protected = json.loads(source["protected_tokens_json"])
            combined = " ".join(item for item in target if isinstance(item, str))
            missing = [token for token in protected if token not in combined]
            if missing:
                issues.append({"code": "protected_token_missing", "unit_id": source["id"], "tokens": missing})
            for index, definition in enumerate(target):
                for code in _plain_text_issues(
                    definition, [],
                    allow_no_cyrillic=allows_japanese_grammar_label(source["role"], source["source_text"]),
                ):
                    issues.append({"code": code, "unit_id": source["id"], "definition_index": index})
        else:
            for code in _plain_text_issues(
                target,
                [] if required_target is not None else json.loads(source["protected_tokens_json"]),
                allow_no_cyrillic=(
                    (required_target is not None and target == required_target)
                    or allows_japanese_grammar_label(source["role"], source["source_text"])
                ),
            ):
                issues.append({"code": code, "unit_id": source["id"]})
    return issues


def ingest_response(connection: sqlite3.Connection, path: Path) -> dict[str, int]:
    attempt = connection.execute("SELECT * FROM attempt WHERE response_path=?", (str(path),)).fetchone()
    if attempt is None:
        raise ValueError(f"no claimed attempt expects {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        payload = None
        issues = [{"code": "invalid_json", "error": str(error)}]
    else:
        issues = validate_worker_payload(connection, attempt, payload)
    if issues:
        for issue in issues:
            connection.execute(
                """INSERT INTO validation_issue(run_id,unit_id,attempt_id,validator,severity,code,details_json)
                SELECT b.run_id,?,?, 'deterministic-v1','error',?,? FROM batch b WHERE b.id=?""",
                (issue.get("unit_id"), attempt["id"], issue["code"], json.dumps(issue, ensure_ascii=False), attempt["batch_id"]),
            )
        connection.execute("UPDATE attempt SET outcome='rejected',error_json=?,completed_at=CURRENT_TIMESTAMP WHERE id=?", (json.dumps(issues), attempt["id"]))
        connection.execute("UPDATE batch SET state='retryable' WHERE id=?", (attempt["batch_id"],))
        audit(connection, "reject", "attempt", attempt["id"], {"issues": issues})
        raise ValidationFailure(issues)
    batch = connection.execute("SELECT * FROM batch WHERE id=?", (attempt["batch_id"],)).fetchone()
    for item in payload["translations"]:
        source = connection.execute("SELECT role FROM translation_unit WHERE id=?", (item["unit_id"],)).fetchone()
        stored_target = target_storage(source["role"], item["target_text"])
        connection.execute(
            """INSERT INTO translation(run_id,unit_id,attempt_id,target_text,confidence,review_reason,target_sha256)
            VALUES (?,?,?,?,?,?,?)""",
            (batch["run_id"], item["unit_id"], attempt["id"], stored_target, item["confidence"],
             item["review_reason"], sha256_bytes(stored_target.encode())),
        )
        connection.execute("UPDATE translation_unit SET status='translated' WHERE id=?", (item["unit_id"],))
    connection.execute("UPDATE attempt SET outcome='accepted',completed_at=CURRENT_TIMESTAMP WHERE id=?", (attempt["id"],))
    connection.execute("UPDATE batch SET state='deterministic_validated' WHERE id=?", (attempt["batch_id"],))
    connection.execute(
        """UPDATE validation_issue SET resolved_at=CURRENT_TIMESTAMP,
        waiver_reason='superseded by a later deterministically valid response for the same batch'
        WHERE resolved_at IS NULL AND validator='deterministic-v1' AND attempt_id IN (
          SELECT id FROM attempt WHERE batch_id=? AND id<>?
        )""",
        (attempt["batch_id"], attempt["id"]),
    )
    audit(connection, "ingest", "attempt", attempt["id"], {"translations": len(payload["translations"])})
    return {"translations_ingested": len(payload["translations"])}
