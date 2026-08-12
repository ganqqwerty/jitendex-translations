from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .batch import _approved_tag_catalog
from .db import audit
from .util import json_pointer_get, sha256_bytes


CANONICALIZER_VERSION = "final-run-v1"


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


def _manifest_requirements(connection: sqlite3.Connection, run_id: int) -> dict[str, tuple[str, dict[str, Any]]]:
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


def canonicalize_final_run(connection: sqlite3.Connection, run_id: int) -> dict[str, int | str]:
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
        """SELECT tu.id unit_id,tu.role,tu.json_pointer,a.raw_json,
        t.id translation_id,t.target_text,t.target_sha256
        FROM translation_unit tu JOIN article a ON a.id=tu.article_id
        JOIN translation t ON t.run_id=tu.run_id AND t.unit_id=tu.id AND t.accepted=1
        WHERE tu.run_id=? ORDER BY tu.id""", (run_id,),
    ).fetchall()

    replacements: list[tuple[sqlite3.Row, str, str, dict[str, Any]]] = []
    structured = 0
    for row in rows:
        source = json.loads(row["raw_json"])
        tag = _structured_tag_requirement(source, row["json_pointer"], catalog)
        manifest = requirements.get(row["unit_id"])
        if tag is not None:
            structured += 1
            target, identity = tag
            if manifest is not None and manifest[0] != target:
                raise ValueError(f"conflicting structured and manifest mapping for {row['unit_id']}")
            mapping_source = "approved_jitendex_tag_catalog"
        elif manifest is not None:
            target, identity = manifest
            mapping_source = "manifest_required_terminology"
        else:
            continue
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
        "required_units": len(replacements),
        "changed_units": changed,
        "already_canonical_units": already_canonical,
    }
    audit(connection, "canonicalize_final_run", "run", run_id, result)
    return result
