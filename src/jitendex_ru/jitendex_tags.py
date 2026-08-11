from __future__ import annotations

import json
import re
import sqlite3
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from .db import audit
from .util import canonical_json, sha256_bytes


TERM_BANK_RE = re.compile(r"^term_bank_(\d+)\.json$")
TAG_BANK_RE = re.compile(r"^tag_bank_(\d+)\.json$")
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
TOOLTIP_ABBREVIATION_RE = re.compile(r"(?<![А-Яа-яЁё])(?:гл|сущ|прил|нар|межд|телеком|машиностр)\.")
FULL_POS_LABEL_RE = re.compile(r"\b(?:глагол|существительное|прилагательное|наречие|междометие)\b", re.IGNORECASE)
ASCII_WORD_RE = re.compile(r"[A-Za-z]{2,}")
ENDING_KANA = {
    "bu": "ぶ", "gu": "ぐ", "hu/fu": "ふ", "ku": "く", "mu": "む", "nu": "ぬ",
    "ru": "る", "su": "す", "tsu": "つ", "u": "う", "dzu": "づ", "yu": "ゆ", "zu": "ず",
}
SOURCE_FORM_KANA = {
    "kureru": "くれる", "Kuru": "くる", "suru": "する", "zuru": "ずる", "jiru": "じる",
    "-aru": "ある", "Iku/Yuku": "行く／ゆく",
}


def _walk(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _source_hash(row: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json({
        key: row[key]
        for key in ("source_kind", "source_key", "code", "category", "label_en", "description_en")
    }))


def extract_jitendex_tags(archive_path: Path) -> list[dict[str, Any]]:
    """Return every distinct visible tag and its English tooltip from a Jitendex ZIP."""
    embedded: Counter[tuple[str, str, str, str]] = Counter()
    tag_bank: list[dict[str, Any]] = []
    with zipfile.ZipFile(archive_path) as archive:
        term_banks = sorted(
            (name for name in archive.namelist() if TERM_BANK_RE.fullmatch(name)),
            key=lambda name: int(TERM_BANK_RE.fullmatch(name).group(1)),
        )
        for name in term_banks:
            for article in json.loads(archive.read(name)):
                for node in _walk(article):
                    data = node.get("data")
                    if not (
                        isinstance(data, dict)
                        and data.get("class") == "tag"
                        and isinstance(node.get("content"), str)
                        and isinstance(node.get("title"), str)
                    ):
                        continue
                    code = data.get("code", "")
                    category = data.get("content", "")
                    if not isinstance(code, str) or not isinstance(category, str):
                        raise ValueError(f"invalid embedded Jitendex tag in {name}")
                    embedded[(code, node["content"], node["title"], category)] += 1

        tag_banks = sorted(
            (name for name in archive.namelist() if TAG_BANK_RE.fullmatch(name)),
            key=lambda name: int(TAG_BANK_RE.fullmatch(name).group(1)),
        )
        for name in tag_banks:
            for ordinal, item in enumerate(json.loads(archive.read(name))):
                if not (
                    isinstance(item, list) and len(item) >= 5
                    and isinstance(item[0], str) and isinstance(item[1], str)
                    and isinstance(item[3], str)
                ):
                    raise ValueError(f"invalid tag row {ordinal} in {name}")
                tag_bank.append({
                    "source_kind": "tag_bank",
                    "source_key": item[0],
                    "code": item[0],
                    "category": item[1],
                    "label_en": item[0],
                    "description_en": item[3],
                    "occurrence_count": 1,
                    "source_metadata_json": json.dumps({
                        "bank": name, "order": item[2], "score": item[4], "ordinal": ordinal,
                    }, ensure_ascii=False, sort_keys=True),
                })

    rows = [{
        "source_kind": "embedded_tooltip",
        "source_key": code or label,
        "code": code,
        "category": category,
        "label_en": label,
        "description_en": description,
        "occurrence_count": count,
        "source_metadata_json": "{}",
    } for (code, label, description, category), count in embedded.items()]
    rows.extend(tag_bank)
    for row in rows:
        row["source_sha256"] = _source_hash(row)
    return sorted(rows, key=lambda row: (
        row["source_kind"], row["category"], row["code"], row["label_en"], row["description_en"],
    ))


def import_jitendex_tags(
    connection: sqlite3.Connection, snapshot_id: int, archive_path: Path,
) -> dict[str, int]:
    snapshot = connection.execute(
        "SELECT id FROM source_snapshot WHERE id=? AND kind='jitendex'", (snapshot_id,),
    ).fetchone()
    if snapshot is None:
        raise ValueError(f"unknown Jitendex snapshot {snapshot_id}")
    rows = extract_jitendex_tags(archive_path)
    for row in rows:
        connection.execute(
            """INSERT INTO jitendex_tag(
              snapshot_id,source_kind,source_key,code,category,label_en,description_en,
              source_sha256,occurrence_count,source_metadata_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(snapshot_id,source_kind,source_key) DO UPDATE SET
              code=excluded.code,
              category=excluded.category,
              label_en=excluded.label_en,
              description_en=excluded.description_en,
              occurrence_count=excluded.occurrence_count,
              source_metadata_json=excluded.source_metadata_json,
              label_ru=CASE WHEN jitendex_tag.source_sha256=excluded.source_sha256 THEN jitendex_tag.label_ru END,
              description_ru=CASE WHEN jitendex_tag.source_sha256=excluded.source_sha256 THEN jitendex_tag.description_ru END,
              confidence=CASE WHEN jitendex_tag.source_sha256=excluded.source_sha256 THEN jitendex_tag.confidence END,
              review_reason=CASE WHEN jitendex_tag.source_sha256=excluded.source_sha256 THEN jitendex_tag.review_reason END,
              translation_model=CASE WHEN jitendex_tag.source_sha256=excluded.source_sha256 THEN jitendex_tag.translation_model END,
              reasoning_effort=CASE WHEN jitendex_tag.source_sha256=excluded.source_sha256 THEN jitendex_tag.reasoning_effort END,
              prompt_sha256=CASE WHEN jitendex_tag.source_sha256=excluded.source_sha256 THEN jitendex_tag.prompt_sha256 END,
              translation_source=CASE WHEN jitendex_tag.source_sha256=excluded.source_sha256 THEN jitendex_tag.translation_source END,
              translation_source_sha256=CASE WHEN jitendex_tag.source_sha256=excluded.source_sha256 THEN jitendex_tag.translation_source_sha256 END,
              translation_source_path=CASE WHEN jitendex_tag.source_sha256=excluded.source_sha256 THEN jitendex_tag.translation_source_path END,
              approved_at=CASE WHEN jitendex_tag.source_sha256=excluded.source_sha256 THEN jitendex_tag.approved_at END,
              translated_at=CASE WHEN jitendex_tag.source_sha256=excluded.source_sha256 THEN jitendex_tag.translated_at END,
              source_sha256=excluded.source_sha256""",
            (snapshot_id, row["source_kind"], row["source_key"], row["code"], row["category"],
             row["label_en"], row["description_en"], row["source_sha256"],
             row["occurrence_count"], row["source_metadata_json"]),
        )
    counts = Counter(row["source_kind"] for row in rows)
    audit(connection, "import", "jitendex_tag", snapshot_id, {
        "total": len(rows), "embedded_tooltips": counts["embedded_tooltip"],
        "tag_bank": counts["tag_bank"],
    })
    return {
        "jitendex_tags": len(rows),
        "embedded_tooltips": counts["embedded_tooltip"],
        "tag_bank_tags": counts["tag_bank"],
    }


def translation_manifest(rows: list[sqlite3.Row], batch_id: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "batch_id": batch_id,
        "target_language": "ru",
        "tags": [{
            "tag_id": row["id"],
            "source_sha256": row["source_sha256"],
            "source_kind": row["source_kind"],
            "code": row["code"],
            "category": row["category"],
            "label_en": row["label_en"],
            "tooltip_description_en": row["description_en"],
        } for row in rows],
    }


def ingest_tag_translations(
    connection: sqlite3.Connection,
    payload: Mapping[str, Any],
    expected_rows: list[sqlite3.Row],
    *,
    model: str,
    reasoning_effort: str,
    prompt_sha256: str,
) -> int:
    translations = payload.get("translations")
    if payload.get("schema_version") != 1 or not isinstance(translations, list):
        raise ValueError("invalid tag translation response envelope")
    expected = [(row["id"], row["source_sha256"]) for row in expected_rows]
    actual = [(item.get("tag_id"), item.get("source_sha256")) for item in translations if isinstance(item, dict)]
    if actual != expected:
        raise ValueError("tag order, IDs, or source hashes do not match the manifest")
    for index, item in enumerate(translations):
        source_row = expected_rows[index]
        if "translation_source" in source_row.keys() and source_row["translation_source"] == "approved_workbook":
            raise ValueError(f"tag {source_row['id']} is controlled by an approved workbook")
        label = item.get("label_ru")
        description = item.get("tooltip_description_ru")
        confidence = item.get("confidence")
        reason = item.get("review_reason")
        if not isinstance(label, str) or not label.strip() or not isinstance(description, str) or not description.strip():
            raise ValueError(f"empty Russian tag translation for {item.get('tag_id')}")
        if label != "★" and not CYRILLIC_RE.search(label):
            raise ValueError(f"Russian tag label lacks Cyrillic for {item.get('tag_id')}")
        if label == "★" and source_row["label_en"] != "★":
            raise ValueError(f"Russian star label does not match the source for {item.get('tag_id')}")
        if len(label) > 16:
            raise ValueError(f"Russian tag label is too long for {item.get('tag_id')}")
        if not CYRILLIC_RE.search(description):
            raise ValueError(f"Russian tooltip lacks Cyrillic for {item.get('tag_id')}")
        if ASCII_WORD_RE.search(description):
            raise ValueError(f"Russian tooltip contains untranslated Latin text for {item.get('tag_id')}")
        if TOOLTIP_ABBREVIATION_RE.search(description):
            raise ValueError(f"Russian tooltip contains a shortened term for {item.get('tag_id')}")
        if FULL_POS_LABEL_RE.search(label):
            raise ValueError(f"Russian tag label contains an unshortened part of speech for {item.get('tag_id')}")
        ending = re.search(r"with '([^']+)' ending", source_row["description_en"])
        if ending and (kana := ENDING_KANA.get(ending.group(1))) and kana not in description:
            raise ValueError(f"Russian tooltip does not use kana {kana} for {item.get('tag_id')}")
        for source_form, kana in SOURCE_FORM_KANA.items():
            if source_form in source_row["description_en"] and kana not in description:
                raise ValueError(f"Russian tooltip does not use Japanese form {kana} for {item.get('tag_id')}")
        if confidence not in {"high", "medium", "low"}:
            raise ValueError(f"invalid confidence for {item.get('tag_id')}")
        if (confidence == "high" and reason is not None) or (
            confidence != "high" and (not isinstance(reason, str) or not reason.strip())
        ):
            raise ValueError(f"confidence/review_reason mismatch for {item.get('tag_id')}")
        connection.execute(
            """UPDATE jitendex_tag SET
              label_ru=?,description_ru=?,confidence=?,review_reason=?,translation_model=?,
              reasoning_effort=?,prompt_sha256=?,translated_at=CURRENT_TIMESTAMP
            WHERE id=? AND source_sha256=?""",
            (label.strip(), description.strip(), confidence, reason, model, reasoning_effort,
             prompt_sha256, item["tag_id"], item["source_sha256"]),
        )
        if connection.execute("SELECT changes()").fetchone()[0] != 1:
            raise ValueError(f"tag {item['tag_id']} changed before ingestion")
    audit(connection, "translate", "jitendex_tag_batch", payload.get("batch_id", "unknown"), {
        "model": model, "reasoning_effort": reasoning_effort, "tags": len(translations),
        "prompt_sha256": prompt_sha256,
    })
    return len(translations)


def ingest_approved_tag_rows(
    connection: sqlite3.Connection,
    snapshot_id: int,
    rows: Sequence[Mapping[str, Any]],
    *,
    source_path: str,
    source_sha256: str,
) -> dict[str, int | str]:
    """Replace catalog translations only after an exact source-side reconciliation."""
    database_rows = connection.execute(
        "SELECT * FROM jitendex_tag WHERE snapshot_id=? ORDER BY id", (snapshot_id,),
    ).fetchall()
    if not database_rows:
        raise ValueError(f"snapshot {snapshot_id} has no Jitendex tag catalog")

    def identity(row: Mapping[str, Any]) -> tuple[str, str, str, str, str, int]:
        code = row.get("code")
        return (
            str(row.get("source_kind") or ""),
            str(row.get("category") or ""),
            "" if code is None else str(code),
            str(row.get("label_en") or ""),
            str(row.get("description_en") or ""),
            int(row.get("occurrence_count") or 0),
        )

    approved_by_identity: dict[tuple[str, str, str, str, str, int], Mapping[str, Any]] = {}
    for row in rows:
        key = identity(row)
        if key in approved_by_identity:
            raise ValueError(f"duplicate approved tag identity: {key}")
        approved_by_identity[key] = row
    database_by_identity = {identity(dict(row)): row for row in database_rows}
    missing = database_by_identity.keys() - approved_by_identity.keys()
    extra = approved_by_identity.keys() - database_by_identity.keys()
    if missing or extra:
        raise ValueError(
            f"approved workbook does not exactly match the catalog: missing={len(missing)}, extra={len(extra)}"
        )

    replacements: list[tuple[sqlite3.Row, str, str, str, str | None]] = []
    for key, database_row in database_by_identity.items():
        approved = approved_by_identity[key]
        label = approved.get("label_ru")
        description = approved.get("description_ru")
        confidence = approved.get("confidence")
        reason = approved.get("review_reason")
        reason = None if reason in (None, "") else str(reason).strip()
        if not isinstance(label, str) or not label.strip() or not isinstance(description, str) or not description.strip():
            raise ValueError(f"approved tag {database_row['id']} has an empty Russian label or tooltip")
        if not CYRILLIC_RE.search(label) and label != "★":
            raise ValueError(f"approved tag {database_row['id']} label lacks Cyrillic")
        if not CYRILLIC_RE.search(description):
            raise ValueError(f"approved tag {database_row['id']} tooltip lacks Cyrillic")
        if confidence not in {"high", "medium", "low"}:
            raise ValueError(f"approved tag {database_row['id']} has invalid confidence")
        if (confidence == "high" and reason is not None) or (confidence != "high" and reason is None):
            raise ValueError(f"approved tag {database_row['id']} has inconsistent confidence/review_reason")
        replacements.append((database_row, label.strip(), description.strip(), str(confidence), reason))

    changed = 0
    for database_row, label, description, confidence, reason in replacements:
        current_state = (
            database_row["label_ru"], database_row["description_ru"], database_row["confidence"],
            database_row["review_reason"], database_row["translation_source"],
            database_row["translation_source_sha256"], database_row["translation_source_path"],
        )
        approved_state = (
            label, description, confidence, reason, "approved_workbook", source_sha256, source_path,
        )
        if current_state == approved_state:
            continue
        connection.execute(
            """INSERT INTO jitendex_tag_translation_history(
              tag_id,label_ru,description_ru,confidence,review_reason,translation_model,
              reasoning_effort,prompt_sha256,translation_source,translation_source_sha256,
              translation_source_path,translated_at,replacement_source_sha256
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (database_row["id"], database_row["label_ru"], database_row["description_ru"],
             database_row["confidence"], database_row["review_reason"], database_row["translation_model"],
             database_row["reasoning_effort"], database_row["prompt_sha256"],
             database_row["translation_source"], database_row["translation_source_sha256"],
             database_row["translation_source_path"], database_row["translated_at"], source_sha256),
        )
        connection.execute(
            """UPDATE jitendex_tag SET
              label_ru=?,description_ru=?,confidence=?,review_reason=?,
              translation_model=NULL,reasoning_effort=NULL,prompt_sha256=NULL,
              translation_source='approved_workbook',translation_source_sha256=?,
              translation_source_path=?,approved_at=CURRENT_TIMESTAMP,translated_at=CURRENT_TIMESTAMP
            WHERE id=?""",
            (label, description, confidence, reason, source_sha256, source_path, database_row["id"]),
        )
        changed += 1
    audit(connection, "approve", "jitendex_tag_catalog", snapshot_id, {
        "source_path": source_path,
        "source_sha256": source_sha256,
        "rows": len(replacements),
        "changed": changed,
    })
    return {
        "snapshot_id": snapshot_id,
        "rows_reconciled": len(replacements),
        "rows_replaced": changed,
        "source_sha256": source_sha256,
    }


def translated_tag_notes(connection: sqlite3.Connection, snapshot_id: int) -> dict[str, str]:
    rows = connection.execute(
        """SELECT description_en,description_ru FROM jitendex_tag
        WHERE snapshot_id=? AND source_kind='tag_bank' ORDER BY id""", (snapshot_id,),
    ).fetchall()
    missing = [row["description_en"] for row in rows if not row["description_ru"]]
    if missing:
        raise ValueError(f"{len(missing)} Jitendex tag-bank descriptions lack Russian translations")
    return {row["description_en"]: row["description_ru"] for row in rows}
