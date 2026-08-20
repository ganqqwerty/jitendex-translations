from __future__ import annotations

from .database import ConnectionLike, RowLike

import json
from pathlib import Path
from typing import Any

from .batch import _approved_tag_catalog
from .db import audit
from .util import json_pointer_get, sha256_bytes


CANONICALIZER_VERSION = "final-run-v2"
REMEDIATION_SCHEMA_VERSION = 1


def _structured_tag_requirement(
    source: Any, pointer: str, catalog: dict[tuple[str, str], dict[str, str]],
) -> tuple[str, dict[str, str]] | None:
    parent_pointer, separator, field = pointer.rpartition("/")
    if not separator or field not in {"content", "title"}:
        return None
    parent = json_pointer_get(source, parent_pointer)
    if not isinstance(parent, dict):
        return None
    data = parent.get("data")
    if not isinstance(data, dict) or data.get("class") != "tag":
        return None
    category = data.get("content")
    code = data.get("code", "")
    if not isinstance(category, str) or not isinstance(code, str):
        raise ValueError(f"invalid structured tag metadata at {pointer}")
    approved = catalog.get((category, code))
    if approved is None:
        raise ValueError(f"missing approved structured tag mapping for {(category, code, field)}")
    target = approved["label_ru" if field == "content" else "description_ru"]
    return target, {"category": category, "code": code, "field": field}


def _manifest_requirements(connection: ConnectionLike, run_id: int) -> dict[str, tuple[str, dict[str, Any]]]:
    requirements: dict[str, tuple[str, dict[str, Any]]] = {}
    paths = connection.execute(
        "SELECT manifest_path FROM batch WHERE run_id=? AND kind='translation' ORDER BY id", (run_id,),
    ).fetchall()
    for row in paths:
        path = Path(row["manifest_path"])
        if not path.is_file():
            raise ValueError(f"missing batch manifest required for canonicalization: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        for article in payload.get("articles", []):
            for unit in article.get("units", []):
                required = unit.get("required_terminology")
                if required is None:
                    continue
                unit_id = unit.get("unit_id")
                target = required.get("target_text") if isinstance(required, dict) else None
                if not isinstance(unit_id, str) or not isinstance(target, str) or not target:
                    raise ValueError(f"invalid required_terminology in {path}")
                identity = {key: value for key, value in required.items() if key != "target_text"}
                candidate = (target, identity)
                previous = requirements.get(unit_id)
                if previous is not None and previous != candidate:
                    raise ValueError(f"ambiguous required terminology for {unit_id}")
                requirements[unit_id] = candidate
    return requirements


def _remediation_requirements(path: Path, run_id: int) -> tuple[str, str, dict[str, dict[str, str]]]:
    if not path.is_file():
        raise ValueError(f"missing remediation manifest: {path}")
    payload_bytes = path.read_bytes()
    payload = json.loads(payload_bytes)
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version", "run_id", "mapping_source", "changes",
    }:
        raise ValueError("invalid remediation manifest fields")
    if payload["schema_version"] != REMEDIATION_SCHEMA_VERSION:
        raise ValueError("unsupported remediation manifest schema")
    if payload["run_id"] != run_id:
        raise ValueError("remediation manifest run mismatch")
    mapping_source = payload["mapping_source"]
    if not isinstance(mapping_source, str) or not mapping_source.startswith("approved_yomitan_"):
        raise ValueError("remediation mapping source is not approved")
    changes = payload["changes"]
    if not isinstance(changes, list) or not changes:
        raise ValueError("remediation manifest changes must be a non-empty array")
    requirements: dict[str, dict[str, str]] = {}
    for change in changes:
        if not isinstance(change, dict) or set(change) != {
            "unit_id", "source_sha256", "previous_target_sha256", "canonical_target_text",
        }:
            raise ValueError("invalid remediation change fields")
        if not all(isinstance(change[key], str) and change[key] for key in change):
            raise ValueError("remediation change values must be non-empty strings")
        unit_id = change["unit_id"]
        if unit_id in requirements:
            raise ValueError(f"duplicate remediation unit {unit_id}")
        requirements[unit_id] = change
    return mapping_source, sha256_bytes(payload_bytes), requirements


def canonicalize_final_run(
    connection: ConnectionLike, run_id: int, remediation_manifest: Path | None = None,
) -> dict[str, int | str]:
    run = connection.execute("SELECT * FROM run WHERE id=?", (run_id,)).fetchone()
    if run is None:
        raise ValueError(f"unknown run {run_id}")
    total = connection.execute("SELECT COUNT(*) FROM translation_unit WHERE run_id=?", (run_id,)).fetchone()[0]
    accepted = connection.execute(
        "SELECT COUNT(*) FROM translation WHERE run_id=? AND accepted=1", (run_id,),
    ).fetchone()[0]
    if not total or accepted != total:
        raise ValueError(f"run {run_id} is not fully accepted: {accepted}/{total}")

    catalog = _approved_tag_catalog(connection, run["jitendex_snapshot_id"])
    requirements = _manifest_requirements(connection, run_id)
    rows = connection.execute(
        """WITH selected AS (
          SELECT tu.id unit_id,tu.article_id,tu.role,tu.json_pointer,tu.source_sha256,
          t.id translation_id,t.target_text,t.target_sha256,
          ROW_NUMBER() OVER (PARTITION BY tu.article_id ORDER BY tu.id) article_row
          FROM translation_unit tu
          JOIN translation t ON t.unit_id=tu.id AND t.accepted=1
          WHERE tu.run_id=?
        )
        SELECT selected.*,
        CASE WHEN selected.article_row=1 THEN a.raw_json ELSE NULL END raw_json
        FROM selected JOIN article a ON a.id=selected.article_id
        ORDER BY selected.article_id,selected.unit_id""", (run_id,),
    ).fetchall()

    remediation_source = ""
    remediation_hash = ""
    remediation: dict[str, dict[str, str]] = {}
    if remediation_manifest is not None:
        remediation_source, remediation_hash, remediation = _remediation_requirements(
            remediation_manifest, run_id,
        )
    rows_by_unit = {row["unit_id"]: row for row in rows}
    for unit_id, requirement in remediation.items():
        row = rows_by_unit.get(unit_id)
        if row is None:
            raise ValueError(f"unknown or unaccepted remediation unit {unit_id}")
        if row["source_sha256"] != requirement["source_sha256"]:
            raise ValueError(f"remediation source hash mismatch for {unit_id}")
        if sha256_bytes(row["target_text"].encode()) != row["target_sha256"]:
            raise ValueError(f"stored target hash mismatch for {unit_id}")
        canonical_hash = sha256_bytes(requirement["canonical_target_text"].encode())
        if row["target_sha256"] == requirement["previous_target_sha256"]:
            continue
        if row["target_sha256"] != canonical_hash:
            raise ValueError(f"remediation previous target hash mismatch for {unit_id}")
        history = connection.execute(
            """SELECT 1 FROM translation_canonicalization_history
            WHERE run_id=? AND unit_id=? AND previous_target_sha256=?
              AND canonical_target_sha256=? AND mapping_source=? LIMIT 1""",
            (run_id, unit_id, requirement["previous_target_sha256"], canonical_hash, remediation_source),
        ).fetchone()
        if history is None and requirement["previous_target_sha256"] != canonical_hash:
            raise ValueError(f"remediation canonical target lacks matching history for {unit_id}")

    replacements: list[tuple[RowLike, str, str, dict[str, Any]]] = []
    structured = 0
    source: dict[str, Any] | None = None
    for row in rows:
        if row["raw_json"] is not None:
            source = json.loads(row["raw_json"])
        if source is None:
            raise ValueError(f"missing article JSON for {row['unit_id']}")
        tag = _structured_tag_requirement(source, row["json_pointer"], catalog)
        manifest = requirements.get(row["unit_id"])
        approved_repair = remediation.get(row["unit_id"])
        if tag is not None:
            structured += 1
            target, identity = tag
            if manifest is not None and manifest[0] != target:
                raise ValueError(f"conflicting structured and manifest mapping for {row['unit_id']}")
            mapping_source = "approved_jitendex_tag_catalog"
            if approved_repair is not None and approved_repair["canonical_target_text"] != target:
                raise ValueError(f"conflicting structured and remediation mapping for {row['unit_id']}")
        elif manifest is not None:
            target, identity = manifest
            mapping_source = "manifest_required_terminology"
            if approved_repair is not None and approved_repair["canonical_target_text"] != target:
                raise ValueError(f"conflicting manifest and remediation mapping for {row['unit_id']}")
        elif approved_repair is not None:
            target = approved_repair["canonical_target_text"]
            mapping_source = remediation_source
            identity = {
                "manifest_path": str(remediation_manifest),
                "manifest_sha256": remediation_hash,
                "source_sha256": approved_repair["source_sha256"],
                "previous_target_sha256": approved_repair["previous_target_sha256"],
            }
        else:
            continue
        if approved_repair is not None:
            mapping_source = remediation_source
            identity = {
                "manifest_path": str(remediation_manifest),
                "manifest_sha256": remediation_hash,
                "source_sha256": approved_repair["source_sha256"],
                "previous_target_sha256": approved_repair["previous_target_sha256"],
            }
        if row["role"] == "glossary_set":
            raise ValueError(f"required terminology is not a whole scalar leaf for {row['unit_id']}")
        replacements.append((row, target, mapping_source, identity))

    changed = 0
    already_canonical = 0
    for row, target, mapping_source, identity in replacements:
        canonical_hash = sha256_bytes(target.encode())
        if row["target_text"] == target and row["target_sha256"] == canonical_hash:
            already_canonical += 1
            continue
        connection.execute(
            """INSERT INTO translation_canonicalization_history(
              run_id,unit_id,translation_id,previous_target_text,previous_target_sha256,
              canonical_target_text,canonical_target_sha256,mapping_source,mapping_identity_json,
              canonicalizer_version
            ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (run_id, row["unit_id"], row["translation_id"], row["target_text"], row["target_sha256"],
             target, canonical_hash, mapping_source,
             json.dumps(identity, ensure_ascii=False, sort_keys=True), CANONICALIZER_VERSION),
        )
        connection.execute(
            "UPDATE translation SET target_text=?,target_sha256=? WHERE id=? AND run_id=? AND accepted=1",
            (target, canonical_hash, row["translation_id"], run_id),
        )
        changed += 1

    result: dict[str, int | str] = {
        "run_id": run_id,
        "canonicalizer_version": CANONICALIZER_VERSION,
        "structured_tag_units": structured,
        "remediation_units": len(remediation),
        "required_units": len(replacements),
        "changed_units": changed,
        "already_canonical_units": already_canonical,
    }
    audit(connection, "canonicalize_final_run", "run", run_id, result)
    return result
