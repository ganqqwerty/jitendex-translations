from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path

from .db import audit
from .util import atomic_write, canonical_json, nfc, reading_variants, sha256_bytes


def _is_kana(value: str) -> bool:
    return bool(value) and all("ぁ" <= char <= "ゖ" or "ァ" <= char <= "ヺ" or char in "ー・" for char in value)


def generate_candidates(connection: sqlite3.Connection) -> dict[str, int]:
    articles = connection.execute("SELECT id,expression,reading,sequence,raw_json FROM article ORDER BY id").fetchall()
    expression_index: dict[str, list[sqlite3.Row]] = defaultdict(list)
    reading_index: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for article in articles:
        expression_index[nfc(article["expression"])].append(article)
        for reading in reading_variants(article["reading"]):
            reading_index[reading].append(article)

    inserted = auto = unresolved = 0
    notes = connection.execute("SELECT * FROM kaishi_note ORDER BY id").fetchall()
    for note in notes:
        variants = set(reading_variants(note["reading"]))
        matches: dict[int, tuple[sqlite3.Row, str]] = {}
        for article in expression_index.get(nfc(note["word"]), []):
            if not variants or variants.intersection(reading_variants(article["reading"])):
                matches[article["id"]] = (article, "expression_reading")
        if _is_kana(note["word"]):
            lookup = set(reading_variants(note["word"])) | variants
            for reading in lookup:
                for article in reading_index.get(reading, []):
                    matches.setdefault(article["id"], (article, "reading_fallback"))

        sequences: set[int] = set()
        for article, kind in matches.values():
            evidence = {
                "word": note["word"], "reading": note["reading"], "meaning_en": note["meaning_en"],
                "sentence_ja": note["sentence_ja"], "sentence_en": note["sentence_en"],
                "article_expression": article["expression"], "article_reading": article["reading"],
            }
            connection.execute(
                """INSERT OR IGNORE INTO selection_candidate
                (note_id,article_id,sequence,match_kind,evidence_json) VALUES (?,?,?,?,?)""",
                (note["id"], article["id"], article["sequence"], kind, json.dumps(evidence, ensure_ascii=False, sort_keys=True)),
            )
            inserted += connection.execute("SELECT changes()").fetchone()[0]
            sequences.add(article["sequence"])

        if len(sequences) == 1:
            sequence = next(iter(sequences))
            connection.execute(
                """INSERT OR IGNORE INTO selection_decision
                (note_id,sequence,decision,actor,reason,review_status) VALUES (?,?,?,?,?,?)""",
                (note["id"], sequence, "included", "deterministic-v1", "single compatible sequence", "accepted"),
            )
            auto += connection.execute("SELECT changes()").fetchone()[0]
        else:
            existing = connection.execute(
                "SELECT 1 FROM selection_decision WHERE note_id=? AND sequence IS NULL AND actor='deterministic-v1'",
                (note["id"],),
            ).fetchone()
            if not existing:
                connection.execute(
                    """INSERT INTO selection_decision
                    (note_id,sequence,decision,actor,reason,review_status) VALUES (?,?,?,?,?,?)""",
                    (note["id"], None, "unresolved", "deterministic-v1",
                     "no compatible sequence" if not sequences else "multiple compatible sequences", "pending"),
                )
                unresolved += 1

    _refresh_selected(connection)
    audit(connection, "resolve_candidates", "selection", "current", {"candidates_added": inserted, "auto": auto, "unresolved": unresolved})
    return {"candidates_added": inserted, "auto_resolved": auto, "unresolved": unresolved}


def _refresh_selected(connection: sqlite3.Connection) -> None:
    connection.execute("UPDATE article SET selected=0")
    connection.execute(
        """UPDATE article SET selected=1 WHERE id IN (
        SELECT sc.article_id FROM selection_candidate sc
        JOIN selection_decision sd ON sd.note_id=sc.note_id AND sd.sequence=sc.sequence
        WHERE sd.decision='included' AND sd.review_status='accepted')"""
    )


def apply_resolutions(connection: sqlite3.Connection, path: Path, actor: str) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    count = 0
    for item in payload["resolutions"]:
        note = connection.execute("SELECT id FROM kaishi_note WHERE note_id=?", (item["note_id"],)).fetchone()
        if note is None:
            raise ValueError(f"unknown Kaishi note {item['note_id']}")
        sequence = item.get("sequence")
        if sequence is not None:
            exists = connection.execute(
                "SELECT 1 FROM selection_candidate WHERE note_id=? AND sequence=?", (note["id"], sequence)
            ).fetchone()
            if not exists:
                raise ValueError(f"sequence {sequence} is not a candidate for note {item['note_id']}")
        connection.execute(
            """INSERT INTO selection_decision(note_id,sequence,decision,actor,reason,review_status)
            VALUES (?,?,?,?,?,?)""",
            (note["id"], sequence, item["decision"], actor, item["reason"], item.get("review_status", "accepted")),
        )
        count += 1
    _refresh_selected(connection)
    audit(connection, "apply_resolutions", "selection", "current", {"count": count, "actor": actor})
    return count


def selection_manifest_hash(connection: sqlite3.Connection) -> str:
    decisions = connection.execute(
        """SELECT kn.note_id,sd.sequence,sd.decision,sd.actor,sd.reason,sd.review_status
        FROM selection_decision sd JOIN kaishi_note kn ON kn.id=sd.note_id
        ORDER BY kn.note_id,sd.created_at,sd.id"""
    ).fetchall()
    selected_articles = connection.execute(
        "SELECT id,source_sha256 FROM article WHERE selected=1 ORDER BY id"
    ).fetchall()
    payload = {
        "decisions": [dict(row) for row in decisions],
        "selected_articles": [dict(row) for row in selected_articles],
    }
    return sha256_bytes(canonical_json(payload))


def unresolved_report(connection: sqlite3.Connection) -> list[dict[str, object]]:
    rows = connection.execute(
        """SELECT kn.id,kn.note_id,kn.word,kn.reading,kn.meaning_en,kn.sentence_ja,kn.sentence_en
        FROM kaishi_note kn WHERE NOT EXISTS (
          SELECT 1 FROM selection_decision sd WHERE sd.note_id=kn.id AND sd.decision='included' AND sd.review_status='accepted'
        ) ORDER BY kn.note_id"""
    ).fetchall()
    result = []
    for row in rows:
        candidates = connection.execute(
            """SELECT sc.sequence,sc.match_kind,a.expression,a.reading,a.raw_json
            FROM selection_candidate sc JOIN article a ON a.id=sc.article_id
            WHERE sc.note_id=? ORDER BY sc.sequence,a.id""", (row["id"],)
        ).fetchall()
        result.append({
            **{key: row[key] for key in ("note_id", "word", "reading", "meaning_en", "sentence_ja", "sentence_en")},
            "candidates": [{**dict(candidate), "raw_json": json.loads(candidate["raw_json"])} for candidate in candidates],
        })
    return result


def make_resolution_batches(connection: sqlite3.Connection, inbox: Path, max_notes: int = 10) -> dict[str, object]:
    from .extract_units import semantic_context

    unresolved = unresolved_report(connection)
    inbox.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for offset in range(0, len(unresolved), max_notes):
        notes = []
        for item in unresolved[offset:offset + max_notes]:
            grouped: dict[int, dict[str, object]] = {}
            for candidate in item["candidates"]:
                sequence = candidate["sequence"]
                group = grouped.setdefault(sequence, {"sequence": sequence, "match_kinds": [], "entries": []})
                if candidate["match_kind"] not in group["match_kinds"]:
                    group["match_kinds"].append(candidate["match_kind"])
                raw = candidate["raw_json"]
                group["entries"].append({
                    "expression": candidate["expression"], "reading": candidate["reading"],
                    "semantic_context": semantic_context(raw),
                })
            notes.append({
                key: item[key] for key in ("note_id", "word", "reading", "meaning_en", "sentence_ja", "sentence_en")
            } | {"candidate_sequences": list(grouped.values())})
        batch_number = offset // max_notes + 1
        payload = {
            "schema_version": 1,
            "instructions": (
                "For every note choose exactly one candidate sequence matching the Kaishi meaning and examples. "
                "If candidate_sequences is empty or none is defensible, use sequence null and decision unresolved. "
                "Return strict JSON with a resolutions array in input order; each item has note_id, sequence, "
                "decision (included or unresolved), reason with concise evidence, and review_status pending."
            ),
            "notes": notes,
        }
        identity = sha256_bytes(canonical_json(payload))[:16]
        path = inbox / f"resolution-{batch_number:03d}-{identity}.json"
        atomic_write(path, canonical_json(payload) + b"\n")
        paths.append(str(path))
    audit(connection, "create", "selection_resolution_batches", "current", {"paths": paths, "notes": len(unresolved)})
    return {"batches_created": len(paths), "notes": len(unresolved), "paths": paths}
