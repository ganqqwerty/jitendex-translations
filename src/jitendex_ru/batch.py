from __future__ import annotations

import datetime as dt
import json
import secrets
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from .db import audit, transaction
from .extract_units import glossary_evidence, lexicographic_context, semantic_context
from .util import atomic_write, canonical_json, sha256_bytes


def _evidence(connection: sqlite3.Connection, article_id: int) -> list[dict[str, str]]:
    rows = connection.execute(
        """SELECT DISTINCT kn.word,kn.reading,kn.meaning_en,kn.sentence_ja,kn.sentence_en
        FROM selection_candidate sc JOIN kaishi_note kn ON kn.id=sc.note_id
        JOIN selection_decision sd ON sd.note_id=sc.note_id AND sd.sequence=sc.sequence
        WHERE sc.article_id=? AND sd.decision='included' AND sd.review_status='accepted' ORDER BY kn.id""",
        (article_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _article_envelope(connection: sqlite3.Connection, article: sqlite3.Row, units: list[sqlite3.Row]) -> dict[str, Any]:
    source = json.loads(article["raw_json"])
    lexicographer = any(unit["role"] == "glossary_set" for unit in units)
    prepared_units = []
    for unit in units:
        prepared = {
            "unit_id": unit["id"], "source_sha256": unit["source_sha256"], "role": unit["role"],
            "protected_tokens": json.loads(unit["protected_tokens_json"]), "local_context": unit["role"],
        }
        if unit["role"] == "glossary_set":
            prepared["english_gloss_evidence"] = glossary_evidence(unit["source_text"])
            prepared["instruction"] = "author one variable-length list of Russian dictionary definitions"
        else:
            prepared["source_text"] = unit["source_text"]
        prepared_units.append(prepared)
    return {
        "article_id": f"a-{article['id']}", "source_sha256": article["source_sha256"],
        "term": article["expression"], "reading": article["reading"], "sequence": article["sequence"],
        "kaishi_evidence": _evidence(connection, article["id"]),
        "read_only_context": lexicographic_context(source) if lexicographer else semantic_context(source),
        "units": prepared_units,
    }


def _manifest(batch_id: str, articles: list[dict[str, Any]], terminology: dict[str, str]) -> tuple[dict[str, Any], bytes]:
    lexicographer = any(
        "preservation_inventory" in article.get("read_only_context", {})
        or any(unit["role"] == "glossary_set" for unit in article["units"])
        for article in articles
    )
    payload = {
        "schema_version": 2 if lexicographer else 1, "pipeline": "lexicographer-v2" if lexicographer else "scalar-v1",
        "batch_id": batch_id, "manifest_sha256": "",
        "target_language": "ru", "terminology": terminology, "articles": articles,
    }
    if not lexicographer:
        payload.pop("pipeline")
    digest = sha256_bytes(canonical_json(payload))
    payload["manifest_sha256"] = digest
    return payload, canonical_json(payload)


def make_batches(
    connection: sqlite3.Connection, run_id: int, inbox: Path, terminology: dict[str, str],
    max_articles: int, max_bytes: int, max_units: int, singleton_threshold: int,
) -> dict[str, int]:
    grouped: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for unit in connection.execute(
        """SELECT tu.* FROM translation_unit tu WHERE tu.run_id=? AND tu.status='ready'
        AND NOT EXISTS (SELECT 1 FROM batch_item bi JOIN batch b ON b.id=bi.batch_id
                        WHERE bi.unit_id=tu.id AND b.kind='translation')
        ORDER BY tu.article_id,tu.json_pointer""", (run_id,)
    ):
        grouped[unit["article_id"]].append(unit)
    articles = {row["id"]: row for row in connection.execute("SELECT * FROM article WHERE selected=1")}
    envelopes = [_article_envelope(connection, articles[article_id], units) for article_id, units in sorted(grouped.items())]
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []

    def measured(candidate: list[dict[str, Any]]) -> tuple[int, int]:
        _, data = _manifest("b-" + "0" * 24, candidate, terminology)
        return len(data), sum(len(article["units"]) for article in candidate)

    for envelope in envelopes:
        article_bytes, article_units = measured([envelope])
        if article_bytes > max_bytes or article_units > max_units:
            raise ValueError(f"article {envelope['article_id']} exceeds a hard batch limit")
        force_singleton = article_bytes > singleton_threshold
        candidate = current + [envelope]
        byte_count, unit_count = measured(candidate)
        if current and (force_singleton or len(candidate) > max_articles or byte_count > max_bytes or unit_count > max_units):
            batches.append(current)
            current = []
        if force_singleton:
            batches.append([envelope])
        else:
            current.append(envelope)
    if current:
        batches.append(current)

    for article_group in batches:
        identity = {"run_id": run_id, "article_ids": [item["article_id"] for item in article_group],
                    "unit_ids": [unit["unit_id"] for item in article_group for unit in item["units"]]}
        batch_id = f"b-{sha256_bytes(canonical_json(identity))[:24]}"
        manifest, data = _manifest(batch_id, article_group, terminology)
        path = inbox / f"{batch_id}.json"
        atomic_write(path, data + b"\n")
        units = [unit for article in article_group for unit in article["units"]]
        connection.execute(
            """INSERT INTO batch(id,run_id,kind,manifest_sha256,serialized_bytes,article_count,unit_count,manifest_path)
            VALUES (?,?,?,?,?,?,?,?)""",
            (batch_id, run_id, "translation", manifest["manifest_sha256"], len(data), len(article_group), len(units), str(path)),
        )
        connection.executemany(
            "INSERT INTO batch_item(batch_id,unit_id,ordinal) VALUES (?,?,?)",
            ((batch_id, unit["unit_id"], ordinal) for ordinal, unit in enumerate(units)),
        )
        audit(connection, "create", "batch", batch_id, {"bytes": len(data), "units": len(units)})
    return {"batches_created": len(batches), "articles": len(envelopes), "units": sum(len(a["units"]) for a in envelopes)}


def claim(
    connection: sqlite3.Connection, worker_id: str, outbox: Path,
    lease_minutes: int = 30, batch_id: str | None = None,
) -> dict[str, str] | None:
    import uuid

    outbox.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)
    with transaction(connection, immediate=True):
        connection.execute(
            """UPDATE batch SET state='ready',lease_token=NULL,lease_expires_at=NULL
            WHERE state='leased' AND lease_expires_at < ? AND NOT EXISTS (
              SELECT 1 FROM translation t JOIN batch_item bi ON bi.unit_id=t.unit_id WHERE bi.batch_id=batch.id)""",
            (now.isoformat(),),
        )
        if batch_id is None:
            batch = connection.execute("SELECT * FROM batch WHERE state='ready' ORDER BY created_at,id LIMIT 1").fetchone()
        else:
            batch = connection.execute("SELECT * FROM batch WHERE id=? AND state='ready'", (batch_id,)).fetchone()
        if batch is None:
            return None
        token = secrets.token_urlsafe(24)
        attempt_id = f"att-{uuid.uuid4().hex}"
        expires = now + dt.timedelta(minutes=lease_minutes)
        response_path = outbox / f"{attempt_id}.json"
        connection.execute(
            "UPDATE batch SET state='leased',lease_token=?,lease_expires_at=?,attempt_count=attempt_count+1 WHERE id=?",
            (token, expires.isoformat(), batch["id"]),
        )
        connection.execute(
            """INSERT INTO attempt(id,batch_id,worker_id,model,prompt_sha256,lease_token,request_path,response_path)
            SELECT ?,?,?,?,CASE WHEN ?='review' THEN r.review_prompt_sha256 ELSE r.prompt_sha256 END,?,?,? FROM run r WHERE r.id=?""",
            (attempt_id, batch["id"], worker_id, "gpt-5.6-terra", batch["kind"], token, batch["manifest_path"], str(response_path), batch["run_id"]),
        )
        audit(connection, "claim", "batch", batch["id"], {"attempt_id": attempt_id, "worker_id": worker_id})
    return {
        "batch_id": batch["id"], "attempt_id": attempt_id, "lease_token": token,
        "request_path": batch["manifest_path"], "response_path": str(response_path), "lease_expires_at": expires.isoformat(),
    }


def retry_or_split(connection: sqlite3.Connection, batch_id: str, *, max_attempts: int = 3) -> dict[str, Any]:
    batch = connection.execute("SELECT * FROM batch WHERE id=?", (batch_id,)).fetchone()
    if batch is None or batch["state"] != "retryable":
        return {"batch_id": batch_id, "requeued": False, "split": False}
    if batch["attempt_count"] < max_attempts:
        connection.execute(
            "UPDATE batch SET state='ready',lease_token=NULL,lease_expires_at=NULL WHERE id=?", (batch_id,)
        )
        audit(connection, "retry", "batch", batch_id, {"attempt_count": batch["attempt_count"]})
        return {"batch_id": batch_id, "requeued": True, "split": False}

    manifest = json.loads(Path(batch["manifest_path"]).read_text(encoding="utf-8"))
    articles = manifest["articles"]
    if len(articles) > 1:
        midpoint = len(articles) // 2
        groups = [articles[:midpoint], articles[midpoint:]]
    else:
        units = articles[0]["units"]
        if len(units) < 2:
            connection.execute("UPDATE batch SET state='blocked' WHERE id=?", (batch_id,))
            audit(connection, "block", "batch", batch_id, {"reason": "singleton unit exhausted retries"})
            return {"batch_id": batch_id, "requeued": False, "split": False, "blocked": True}
        midpoint = len(units) // 2
        groups = []
        for subset in (units[:midpoint], units[midpoint:]):
            article = dict(articles[0])
            article["units"] = subset
            groups.append([article])

    children: list[str] = []
    inbox = Path(batch["manifest_path"]).parent
    for group in groups:
        identity = {"parent": batch_id, "unit_ids": [unit["unit_id"] for article in group for unit in article["units"]]}
        child_id = f"b-{sha256_bytes(canonical_json(identity))[:24]}"
        child_manifest, data = _manifest(child_id, group, manifest.get("terminology", {}))
        path = inbox / f"{child_id}.json"
        atomic_write(path, data + b"\n")
        units = [unit for article in group for unit in article["units"]]
        connection.execute(
            """INSERT INTO batch(id,run_id,kind,manifest_sha256,serialized_bytes,article_count,unit_count,manifest_path)
            VALUES (?,?,?,?,?,?,?,?)""",
            (child_id, batch["run_id"], batch["kind"], child_manifest["manifest_sha256"], len(data), len(group), len(units), str(path)),
        )
        connection.executemany(
            "INSERT INTO batch_item(batch_id,unit_id,ordinal) VALUES (?,?,?)",
            ((child_id, unit["unit_id"], index) for index, unit in enumerate(units)),
        )
        children.append(child_id)
    connection.execute("UPDATE batch SET state='blocked' WHERE id=?", (batch_id,))
    connection.execute(
        """UPDATE validation_issue SET resolved_at=CURRENT_TIMESTAMP,waiver_reason='superseded by deterministic split'
        WHERE attempt_id IN (SELECT id FROM attempt WHERE batch_id=?) AND resolved_at IS NULL""", (batch_id,)
    )
    audit(connection, "split", "batch", batch_id, {"children": children})
    return {"batch_id": batch_id, "requeued": False, "split": True, "children": children}
