from __future__ import annotations

import json
import sqlite3
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

from .batch import _article_envelope
from .db import audit
from .util import CYRILLIC_RE, TAG_RE, atomic_write, canonical_json, sha256_bytes
from .validate_response import _plain_text_issues, target_storage


def _review_manifest(batch_id: str, articles: list[dict[str, Any]]) -> tuple[dict[str, Any], bytes]:
    lexicographer = any(
        "preservation_inventory" in article.get("read_only_context", {})
        or any(unit["role"] == "glossary_set" for unit in article["units"])
        for article in articles
    )
    payload = {"schema_version": 2 if lexicographer else 1, "batch_id": batch_id, "manifest_sha256": "", "target_language": "ru", "articles": articles}
    if lexicographer:
        payload["pipeline"] = "lexicographer-v2"
    digest = sha256_bytes(canonical_json(payload))
    payload["manifest_sha256"] = digest
    return payload, canonical_json(payload)


def _split_review_envelope(
    envelope: dict[str, Any], max_bytes: int, max_units: int,
) -> list[dict[str, Any]]:
    """Split one article across review batches without dropping its context."""
    segments: list[dict[str, Any]] = []
    current_units: list[dict[str, Any]] = []
    for unit in envelope["units"]:
        candidate_units = current_units + [unit]
        candidate = {**envelope, "units": candidate_units}
        _, data = _review_manifest("rb-" + "0" * 24, [candidate])
        if current_units and (len(data) > max_bytes or len(candidate_units) > max_units):
            segments.append({**envelope, "units": current_units})
            current_units = [unit]
            candidate = {**envelope, "units": current_units}
            _, data = _review_manifest("rb-" + "0" * 24, [candidate])
        else:
            current_units = candidate_units
        if len(data) > max_bytes or len(current_units) > max_units:
            raise ValueError(f"review unit {unit['unit_id']} exceeds review limits")
    if current_units:
        segments.append({**envelope, "units": current_units})
    return segments


def make_review_batches(
    connection: sqlite3.Connection, run_id: int, inbox: Path,
    max_articles: int = 6, max_bytes: int = 49152, max_units: int = 120,
) -> dict[str, int]:
    grouped: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for row in connection.execute(
        """SELECT tu.*,t.id translation_id,t.target_text,t.confidence,t.review_reason
        FROM translation t JOIN translation_unit tu ON tu.id=t.unit_id
        WHERE t.run_id=? AND t.accepted=0 AND NOT EXISTS (SELECT 1 FROM review r WHERE r.translation_id=t.id)
        ORDER BY tu.article_id,tu.json_pointer""", (run_id,)
    ):
        grouped[row["article_id"]].append(row)
    article_rows = {row["id"]: row for row in connection.execute("SELECT * FROM article WHERE selected=1")}
    envelopes = []
    for article_id, units in sorted(grouped.items()):
        base = _article_envelope(connection, article_rows[article_id], units)
        translations = {row["id"]: row for row in units}
        for unit in base["units"]:
            candidate = translations[unit["unit_id"]]
            unit["candidate_target"] = json.loads(candidate["target_text"]) if unit["role"] == "glossary_set" else candidate["target_text"]
            unit["candidate_confidence"] = candidate["confidence"]
            unit["candidate_review_reason"] = candidate["review_reason"]
        envelopes.extend(_split_review_envelope(base, max_bytes, max_units))

    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for envelope in envelopes:
        candidate = current + [envelope]
        _, data = _review_manifest("rb-" + "0" * 24, candidate)
        units = sum(len(item["units"]) for item in candidate)
        if current and (len(candidate) > max_articles or len(data) > max_bytes or units > max_units):
            groups.append(current)
            current = [envelope]
        else:
            current = candidate
    if current:
        groups.append(current)

    for group in groups:
        identity = {"run_id": run_id, "candidates": [
            [unit["unit_id"], sha256_bytes(
                canonical_json(unit["candidate_target"])
                if isinstance(unit["candidate_target"], list)
                else unit["candidate_target"].encode()
            )]
            for article in group for unit in article["units"]
        ]}
        batch_id = f"rb-{sha256_bytes(canonical_json(identity))[:24]}"
        manifest, data = _review_manifest(batch_id, group)
        path = inbox / f"{batch_id}.json"
        atomic_write(path, data + b"\n")
        units = [unit for article in group for unit in article["units"]]
        connection.execute(
            """INSERT INTO batch(id,run_id,kind,manifest_sha256,serialized_bytes,article_count,unit_count,manifest_path)
            VALUES (?,?,?,?,?,?,?,?)""",
            (batch_id, run_id, "review", manifest["manifest_sha256"], len(data), len(group), len(units), str(path)),
        )
        connection.executemany(
            "INSERT INTO batch_item(batch_id,unit_id,ordinal) VALUES (?,?,?)",
            ((batch_id, unit["unit_id"], index) for index, unit in enumerate(units)),
        )
        audit(connection, "create", "review_batch", batch_id, {"units": len(units)})
    return {"review_batches_created": len(groups), "units": sum(len(group) for group in grouped.values())}


def ingest_review(connection: sqlite3.Connection, path: Path) -> dict[str, int]:
    attempt = connection.execute(
        """SELECT a.*,b.run_id,b.manifest_sha256,b.kind FROM attempt a JOIN batch b ON b.id=a.batch_id
        WHERE a.response_path=?""", (str(path),)
    ).fetchone()
    if attempt is None or attempt["kind"] != "review":
        raise ValueError(f"no review attempt expects {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if set(payload) != {"schema_version", "batch_id", "manifest_sha256", "reviews"}:
        raise ValueError("unexpected review response fields")
    run = connection.execute("SELECT pipeline_version FROM run WHERE id=?", (attempt["run_id"],)).fetchone()
    expected_schema = 2 if run["pipeline_version"] == "lexicographer-v2" else 1
    if payload.get("schema_version") != expected_schema or payload.get("batch_id") != attempt["batch_id"] or payload.get("manifest_sha256") != attempt["manifest_sha256"]:
        raise ValueError("review envelope mismatch")
    expected = connection.execute(
        """SELECT tu.*,t.id translation_id,source_attempt.worker_id source_worker_id
        FROM batch_item bi JOIN translation_unit tu ON tu.id=bi.unit_id
        JOIN translation t ON t.unit_id=tu.id AND t.run_id=?
        JOIN attempt source_attempt ON source_attempt.id=t.attempt_id
        WHERE bi.batch_id=? ORDER BY bi.ordinal""",
        (attempt["run_id"], attempt["batch_id"]),
    ).fetchall()
    reviews = payload.get("reviews")
    if not isinstance(reviews, list) or [item.get("unit_id") for item in reviews] != [row["id"] for row in expected]:
        raise ValueError("review unit order or set mismatch")
    accepted = adjudication = 0
    for source, item in zip(expected, reviews):
        if set(item) != {"unit_id", "source_sha256", "decision", "replacement_target", "reason"}:
            raise ValueError(f"unexpected review fields for {source['id']}")
        if source["source_worker_id"] == attempt["worker_id"]:
            raise ValueError(f"reviewer also produced translation for {source['id']}")
        if item.get("source_sha256") != source["source_sha256"]:
            raise ValueError(f"review source hash mismatch for {source['id']}")
        decision = item.get("decision")
        replacement = item.get("replacement_target")
        if decision not in {"accept", "replace", "needs_adjudication"}:
            raise ValueError(f"invalid review decision for {source['id']}")
        stored_replacement = None
        if decision == "replace":
            try:
                stored_replacement = target_storage(source["role"], replacement)
            except ValueError as error:
                raise ValueError(f"invalid review replacement for {source['id']}: {error}") from error
            values = replacement if source["role"] == "glossary_set" else [replacement]
            if not 1 <= len(values) <= 12 or any(_plain_text_issues(value, []) for value in values):
                raise ValueError(f"invalid review replacement for {source['id']}")
        if decision == "replace":
            for token in json.loads(source["protected_tokens_json"]):
                if token not in stored_replacement:
                    raise ValueError(f"review replacement lost protected token for {source['id']}")
        connection.execute(
            "INSERT INTO review(translation_id,attempt_id,decision,replacement_target,reason) VALUES (?,?,?,?,?)",
            (source["translation_id"], attempt["id"], decision, stored_replacement, item.get("reason")),
        )
        if decision in {"accept", "replace"}:
            if decision == "replace":
                connection.execute(
                    """INSERT INTO translation(run_id,unit_id,attempt_id,target_text,confidence,review_reason,target_sha256,accepted)
                    VALUES (?,?,?,?,?,?,?,1)""",
                    (attempt["run_id"], source["id"], attempt["id"], stored_replacement, "high", item.get("reason"), sha256_bytes(stored_replacement.encode())),
                )
            else:
                connection.execute("UPDATE translation SET accepted=1 WHERE id=?", (source["translation_id"],))
            connection.execute("UPDATE translation_unit SET status='reviewed' WHERE id=?", (source["id"],))
            accepted += 1
        else:
            connection.execute(
                """INSERT INTO validation_issue(run_id,unit_id,attempt_id,validator,severity,code,details_json)
                VALUES (?,?,?,'review-v1','error','needs_adjudication',?)""",
                (attempt["run_id"], source["id"], attempt["id"], json.dumps({"reason": item.get("reason")}, ensure_ascii=False)),
            )
            adjudication += 1
    connection.execute("UPDATE attempt SET outcome='accepted',completed_at=CURRENT_TIMESTAMP WHERE id=?", (attempt["id"],))
    connection.execute("UPDATE batch SET state=? WHERE id=?", ("complete" if not adjudication else "blocked", attempt["batch_id"]))
    connection.execute(
        """UPDATE batch SET state='complete' WHERE run_id=? AND kind='translation'
        AND state='deterministic_validated' AND NOT EXISTS (
          SELECT 1 FROM batch_item bi WHERE bi.batch_id=batch.id AND NOT EXISTS (
            SELECT 1 FROM translation t WHERE t.unit_id=bi.unit_id AND t.run_id=batch.run_id AND t.accepted=1
          )
        )""", (attempt["run_id"],)
    )
    audit(connection, "ingest", "review_attempt", attempt["id"], {"accepted": accepted, "adjudication": adjudication})
    return {"accepted": accepted, "needs_adjudication": adjudication}


def apply_adjudication(connection: sqlite3.Connection, path: Path, actor: str) -> dict[str, Any]:
    """Resolve one review conflict while retaining the original review record."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {"batch_id", "unit_id", "decision", "target_text", "reason"}
    if set(payload) != required:
        raise ValueError("unexpected adjudication fields")
    if payload["decision"] not in {"accept_candidate", "replace"}:
        raise ValueError("invalid adjudication decision")
    if not isinstance(payload["reason"], str) or not payload["reason"].strip():
        raise ValueError("adjudication reason is required")
    source = connection.execute(
        """SELECT r.id review_id,r.translation_id,r.attempt_id review_attempt_id,
        t.run_id,t.unit_id,t.target_text,tu.role,tu.source_sha256,tu.protected_tokens_json,
        b.manifest_path,run.review_prompt_sha256
        FROM review r JOIN attempt a ON a.id=r.attempt_id
        JOIN batch b ON b.id=a.batch_id JOIN translation t ON t.id=r.translation_id
        JOIN translation_unit tu ON tu.id=t.unit_id JOIN run ON run.id=t.run_id
        WHERE b.id=? AND t.unit_id=? AND r.decision='needs_adjudication'""",
        (payload["batch_id"], payload["unit_id"]),
    ).fetchone()
    if source is None:
        raise ValueError("no matching unresolved review conflict")
    target = payload["target_text"]
    if payload["decision"] == "accept_candidate" and source["role"] == "glossary_set" and isinstance(target, list):
        target = target_storage(source["role"], target)
    elif payload["decision"] == "replace":
        target = target_storage(source["role"], target)
    if not isinstance(target, str) or (source["role"] != "glossary_set" and (not CYRILLIC_RE.search(target) or TAG_RE.search(target))):
        raise ValueError("invalid adjudication target")
    if payload["decision"] == "accept_candidate" and target != source["target_text"]:
        raise ValueError("accepted target differs from candidate")
    for token in json.loads(source["protected_tokens_json"]):
        if token not in target:
            raise ValueError(f"adjudication lost protected token {token}")
    existing = connection.execute("SELECT id FROM attempt WHERE response_path=?", (str(path),)).fetchone()
    if existing:
        return {"adjudicated": 0, "attempt_id": existing["id"], "already_applied": True}
    attempt_id = f"adj-{uuid.uuid4().hex}"
    connection.execute(
        """INSERT INTO attempt(id,batch_id,worker_id,model,prompt_sha256,request_path,response_path,outcome,completed_at)
        VALUES (?,?,?,?,?,?,?,'accepted',CURRENT_TIMESTAMP)""",
        (attempt_id, payload["batch_id"], actor, "gpt-5.6-terra", source["review_prompt_sha256"],
         source["manifest_path"], str(path)),
    )
    decision = "accept" if payload["decision"] == "accept_candidate" else "replace"
    connection.execute(
        "INSERT INTO review(translation_id,attempt_id,decision,replacement_target,reason) VALUES (?,?,?,?,?)",
        (source["translation_id"], attempt_id, decision, None if decision == "accept" else target, payload["reason"]),
    )
    if decision == "accept":
        connection.execute("UPDATE translation SET accepted=1 WHERE id=?", (source["translation_id"],))
    else:
        connection.execute(
            """INSERT INTO translation(run_id,unit_id,attempt_id,target_text,confidence,review_reason,target_sha256,accepted)
            VALUES (?,?,?,?,?,?,?,1)""",
            (source["run_id"], source["unit_id"], attempt_id, target, "low", payload["reason"], sha256_bytes(target.encode())),
        )
    connection.execute("UPDATE translation_unit SET status='reviewed' WHERE id=?", (source["unit_id"],))
    connection.execute(
        """UPDATE validation_issue SET resolved_at=CURRENT_TIMESTAMP,waiver_reason=?
        WHERE attempt_id=? AND unit_id=? AND code='needs_adjudication' AND resolved_at IS NULL""",
        (f"adjudicated by {actor}: {payload['reason']}", source["review_attempt_id"], source["unit_id"]),
    )
    remaining = connection.execute(
        """SELECT COUNT(*) FROM validation_issue vi JOIN attempt a ON a.id=vi.attempt_id
        WHERE a.batch_id=? AND vi.code='needs_adjudication' AND vi.resolved_at IS NULL""",
        (payload["batch_id"],),
    ).fetchone()[0]
    if not remaining:
        connection.execute("UPDATE batch SET state='complete' WHERE id=?", (payload["batch_id"],))
    connection.execute(
        """UPDATE batch SET state='complete' WHERE run_id=? AND kind='translation'
        AND state='deterministic_validated' AND NOT EXISTS (
          SELECT 1 FROM batch_item bi WHERE bi.batch_id=batch.id AND NOT EXISTS (
            SELECT 1 FROM translation t WHERE t.unit_id=bi.unit_id AND t.run_id=batch.run_id AND t.accepted=1
          )
        )""",
        (source["run_id"],),
    )
    audit(connection, "adjudicate", "review", source["review_id"], {
        "actor": actor, "attempt_id": attempt_id, "decision": decision, "reason": payload["reason"],
    })
    return {"adjudicated": 1, "attempt_id": attempt_id, "decision": decision}
