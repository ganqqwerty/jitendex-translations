from __future__ import annotations

from .database import ConnectionLike, RowLike

import csv
import json
import re
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
APPROVED_TAG_COLUMNS = (
    "source_kind", "category", "code", "label_en", "label_ru",
    "description_en", "description_ru", "occurrence_count", "confidence", "review_reason",
)
APPROVED_TAG_ROW_COUNT = 236
TAG_CATALOG_VERSION = "tags-ru-v1"
NON_BREAKING_SPACE = "\u00a0"


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


def read_approved_tag_csv(path: Path) -> list[dict[str, Any]]:
    """Read the exact approved CSV schema without changing its wording."""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != APPROVED_TAG_COLUMNS:
            raise ValueError(
                f"approved tag CSV columns must be {APPROVED_TAG_COLUMNS}, found {reader.fieldnames}"
            )
        rows: list[dict[str, Any]] = []
        for line_number, source in enumerate(reader, 2):
            if None in source:
                raise ValueError(f"approved tag CSV row {line_number} has extra columns")
            row = {key: value if value is not None else "" for key, value in source.items()}
            try:
                row["occurrence_count"] = int(row["occurrence_count"])
            except ValueError as error:
                raise ValueError(
                    f"approved tag CSV row {line_number} has an invalid occurrence_count"
                ) from error
            rows.append(row)
    if len(rows) != APPROVED_TAG_ROW_COUNT:
        raise ValueError(
            f"approved tag CSV must contain exactly {APPROVED_TAG_ROW_COUNT} rows, found {len(rows)}"
        )
    return rows


def load_approved_tag_catalog(
    connection: ConnectionLike, snapshot_id: int,
) -> dict[str, Any]:
    """Load one complete approved catalog and reject mixed or ambiguous provenance."""
    rows = connection.execute(
        "SELECT * FROM jitendex_tag WHERE snapshot_id=? ORDER BY id", (snapshot_id,),
    ).fetchall()
    if not rows:
        raise ValueError(f"snapshot {snapshot_id} has no Jitendex tag catalog")
    unapproved = [row["id"] for row in rows if row["translation_source"] != "approved_workbook"]
    if unapproved:
        raise ValueError(f"snapshot {snapshot_id} has {len(unapproved)} unapproved Jitendex tags")
    source_hashes = {row["translation_source_sha256"] for row in rows}
    source_paths = {row["translation_source_path"] for row in rows}
    if len(source_hashes) != 1 or None in source_hashes or len(source_paths) != 1 or None in source_paths:
        raise ValueError("approved Jitendex tags do not share one source path and SHA-256")

    by_identity: dict[tuple[str, str, str], dict[str, Any]] = {}
    embedded: dict[tuple[str, str], dict[str, Any]] = {}
    tag_bank: dict[str, dict[str, Any]] = {}
    for database_row in rows:
        row = dict(database_row)
        if (
            not isinstance(row["label_ru"], str) or not row["label_ru"].strip()
            or not isinstance(row["description_ru"], str) or not row["description_ru"].strip()
        ):
            raise ValueError(f"approved Jitendex tag {row['id']} is incomplete")
        identity = (row["source_kind"], row["category"], row["code"] or "")
        if identity in by_identity:
            raise ValueError(f"duplicate approved Jitendex tag identity {identity}")
        by_identity[identity] = row
        if row["source_kind"] == "embedded_tooltip":
            key = (row["category"], row["code"] or "")
            if key in embedded:
                raise ValueError(f"duplicate approved embedded Jitendex tag {key}")
            embedded[key] = row
        elif row["source_kind"] == "tag_bank":
            code = row["code"] or ""
            if not code or code in tag_bank:
                raise ValueError(f"invalid or duplicate approved tag-bank code {code!r}")
            tag_bank[code] = row
        else:
            raise ValueError(f"unsupported approved Jitendex tag source {row['source_kind']!r}")
    encoded_labels = [row["label_ru"].replace(" ", NON_BREAKING_SPACE) for row in tag_bank.values()]
    if len(encoded_labels) != len(set(encoded_labels)):
        raise ValueError("approved Russian tag-bank labels collide")
    return {
        "snapshot_id": snapshot_id,
        "version": TAG_CATALOG_VERSION,
        "source_sha256": next(iter(source_hashes)),
        "source_path": next(iter(source_paths)),
        "embedded": embedded,
        "tag_bank": tag_bank,
    }


def tag_bank_mapping(catalog: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    return {
        code: {
            "label_ru": row["label_ru"],
            "encoded_label_ru": row["label_ru"].replace(" ", NON_BREAKING_SPACE),
            "description_ru": row["description_ru"],
        }
        for code, row in catalog["tag_bank"].items()
    }


def localize_embedded_tags(value: Any, catalog: Mapping[str, Any]) -> dict[str, Any]:
    """Override every structured tag label and tooltip and describe the replaced variants."""
    details: dict[tuple[str, str], dict[str, Any]] = {}
    label_replacements = 0
    tooltip_replacements = 0
    for node in _walk(value):
        data = node.get("data")
        if not (isinstance(data, dict) and data.get("class") == "tag"):
            continue
        category = data.get("content")
        code = data.get("code", "")
        label = node.get("content")
        tooltip = node.get("title")
        if not all(isinstance(item, str) for item in (category, code, label, tooltip)):
            raise ValueError("invalid embedded Jitendex tag structure")
        key = (category, code)
        approved = catalog["embedded"].get(key)
        if approved is None:
            raise ValueError(f"missing approved embedded Jitendex tag {key}")
        detail = details.setdefault(key, {
            "source_kind": "embedded_tooltip", "category": category, "code": code,
            "approved_label_ru": approved["label_ru"],
            "approved_description_ru": approved["description_ru"],
            "occurrences": 0, "label_variants": Counter(), "tooltip_variants": Counter(),
        })
        detail["occurrences"] += 1
        detail["label_variants"][label] += 1
        detail["tooltip_variants"][tooltip] += 1
        if label != approved["label_ru"]:
            label_replacements += 1
            node["content"] = approved["label_ru"]
        if tooltip != approved["description_ru"]:
            tooltip_replacements += 1
            node["title"] = approved["description_ru"]
    return {
        "embedded_tag_occurrences": sum(item["occurrences"] for item in details.values()),
        "embedded_labels_replaced": label_replacements,
        "embedded_tooltips_replaced": tooltip_replacements,
        "embedded_tags": [
            {
                **{key: value for key, value in detail.items() if key not in {"label_variants", "tooltip_variants"}},
                "label_variants": dict(sorted(detail["label_variants"].items())),
                "tooltip_variants": dict(sorted(detail["tooltip_variants"].items())),
            }
            for _identity, detail in sorted(details.items())
        ],
    }


def localize_tag_bank_rows(
    rows: Sequence[Sequence[Any]], catalog: Mapping[str, Any],
) -> tuple[list[list[Any]], dict[str, dict[str, str]]]:
    """Localize tag-bank names and descriptions after exact source-side validation."""
    mapping = tag_bank_mapping(catalog)
    localized: list[list[Any]] = []
    seen: set[str] = set()
    for source in rows:
        if len(source) < 4 or not all(isinstance(source[index], str) for index in (0, 1, 3)):
            raise ValueError("invalid Jitendex tag-bank row")
        code, category, description = source[0], source[1], source[3]
        approved = catalog["tag_bank"].get(code)
        if approved is None:
            raise ValueError(f"missing approved Jitendex tag-bank mapping for {code!r}")
        if category != approved["category"] or description != approved["description_en"]:
            raise ValueError(f"Jitendex tag-bank source identity changed for {code!r}")
        seen.add(code)
        localized.append([
            mapping[code]["encoded_label_ru"], *source[1:3], approved["description_ru"], *source[4:],
        ])
    missing = set(mapping) - seen
    if missing:
        raise ValueError(f"source archive lacks approved Jitendex tag-bank rows: {sorted(missing)}")
    return localized, mapping


def localize_term_tag_references(
    rows: Sequence[list[Any]], mapping: Mapping[str, Mapping[str, str]],
) -> dict[str, int]:
    """Rewrite Yomitan tag references, using ASCII spaces only as separators."""
    references = 0
    fields_changed = 0
    for row in rows:
        if len(row) < 8:
            raise ValueError("invalid Yomitan term row")
        for index in (2, 7):
            value = row[index]
            if not isinstance(value, str):
                raise ValueError("invalid Yomitan term tag reference field")
            if not value:
                continue
            tags = [tag for tag in value.split(" ") if tag]
            unknown = [tag for tag in tags if tag not in mapping]
            if unknown:
                raise ValueError(f"missing approved tag-bank references: {unknown}")
            localized = " ".join(mapping[tag]["encoded_label_ru"] for tag in tags)
            references += len(tags)
            fields_changed += int(localized != value)
            row[index] = localized
    return {"tag_bank_references": references, "tag_bank_reference_fields_replaced": fields_changed}


def count_tag_bank_references(
    rows: Sequence[Sequence[Any]], mapping: Mapping[str, Mapping[str, str]],
) -> int:
    """Count source tag references while rejecting unknown codes before export."""
    references = 0
    for row in rows:
        if len(row) < 8:
            raise ValueError("invalid Yomitan term row")
        for index in (2, 7):
            value = row[index]
            if not isinstance(value, str):
                raise ValueError("invalid Yomitan term tag reference field")
            tags = [tag for tag in value.split(" ") if tag]
            unknown = [tag for tag in tags if tag not in mapping]
            if unknown:
                raise ValueError(f"missing approved tag-bank references: {unknown}")
            references += len(tags)
    return references


def verify_localized_embedded_tags(value: Any, catalog: Mapping[str, Any]) -> dict[str, Any]:
    """Independently require every emitted structured tag to equal the approved catalog."""
    result = localize_embedded_tags(value, catalog)
    if result["embedded_labels_replaced"] or result["embedded_tooltips_replaced"]:
        raise ValueError(
            "export contains non-canonical embedded Jitendex tag labels or tooltips"
        )
    return result


def verify_localized_tag_bank_rows(
    rows: Sequence[Sequence[Any]], catalog: Mapping[str, Any],
) -> dict[str, dict[str, str]]:
    mapping = tag_bank_mapping(catalog)
    by_label = {item["encoded_label_ru"]: (code, item) for code, item in mapping.items()}
    seen: set[str] = set()
    for row in rows:
        if len(row) < 4 or not all(isinstance(row[index], str) for index in (0, 1, 3)):
            raise ValueError("invalid localized Jitendex tag-bank row")
        match = by_label.get(row[0])
        if match is None:
            raise ValueError(f"unapproved localized Jitendex tag-bank label {row[0]!r}")
        code, approved = match
        source = catalog["tag_bank"][code]
        if row[1] != source["category"] or row[3] != approved["description_ru"]:
            raise ValueError(f"localized Jitendex tag-bank row differs from the catalog for {code!r}")
        if code in seen:
            raise ValueError(f"duplicate localized Jitendex tag-bank row for {code!r}")
        seen.add(code)
    missing = set(mapping) - seen
    if missing:
        raise ValueError(f"localized archive lacks approved tag-bank rows: {sorted(missing)}")
    return mapping


def verify_localized_term_tag_references(
    rows: Sequence[Sequence[Any]], mapping: Mapping[str, Mapping[str, str]],
) -> int:
    approved_labels = {item["encoded_label_ru"] for item in mapping.values()}
    references = 0
    for row in rows:
        if len(row) < 8:
            raise ValueError("invalid localized Yomitan term row")
        for index in (2, 7):
            value = row[index]
            if not isinstance(value, str):
                raise ValueError("invalid localized Yomitan term tag reference field")
            if not value:
                continue
            tags = [tag for tag in value.split(" ") if tag]
            unknown = [tag for tag in tags if tag not in approved_labels]
            if unknown:
                raise ValueError(f"unapproved localized term tag references: {unknown}")
            references += len(tags)
    return references


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
    connection: ConnectionLike, snapshot_id: int, archive_path: Path,
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


def translation_manifest(rows: list[RowLike], batch_id: str) -> dict[str, Any]:
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
    connection: ConnectionLike,
    payload: Mapping[str, Any],
    expected_rows: list[RowLike],
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
        cursor = connection.execute(
            """UPDATE jitendex_tag SET
              label_ru=?,description_ru=?,confidence=?,review_reason=?,translation_model=?,
              reasoning_effort=?,prompt_sha256=?,translated_at=CURRENT_TIMESTAMP
            WHERE id=? AND source_sha256=?""",
            (label.strip(), description.strip(), confidence, reason, model, reasoning_effort,
             prompt_sha256, item["tag_id"], item["source_sha256"]),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"tag {item['tag_id']} changed before ingestion")
    audit(connection, "translate", "jitendex_tag_batch", payload.get("batch_id", "unknown"), {
        "model": model, "reasoning_effort": reasoning_effort, "tags": len(translations),
        "prompt_sha256": prompt_sha256,
    })
    return len(translations)


def ingest_approved_tag_rows(
    connection: ConnectionLike,
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

    def identity(row: Mapping[str, Any]) -> tuple[str, str, str]:
        code = row.get("code")
        return (
            str(row.get("source_kind") or ""),
            str(row.get("category") or ""),
            "" if code is None else str(code),
        )

    approved_by_identity: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for row in rows:
        key = identity(row)
        if key in approved_by_identity:
            raise ValueError(f"duplicate approved tag identity: {key}")
        approved_by_identity[key] = row
    database_by_identity: dict[tuple[str, str, str], RowLike] = {}
    for row in database_rows:
        key = identity(dict(row))
        if key in database_by_identity:
            raise ValueError(f"duplicate database tag identity: {key}")
        database_by_identity[key] = row
    missing = database_by_identity.keys() - approved_by_identity.keys()
    extra = approved_by_identity.keys() - database_by_identity.keys()
    if missing or extra:
        raise ValueError(
            f"approved workbook does not exactly match the catalog: missing={len(missing)}, extra={len(extra)}"
        )

    replacements: list[tuple[RowLike, str, str, str, str | None]] = []
    for key, database_row in database_by_identity.items():
        approved = approved_by_identity[key]
        approved_source = (
            str(approved.get("label_en") or ""),
            str(approved.get("description_en") or ""),
            int(approved.get("occurrence_count") or 0),
        )
        database_source = (
            database_row["label_en"], database_row["description_en"],
            database_row["occurrence_count"],
        )
        if approved_source != database_source:
            raise ValueError(f"approved workbook source fields differ for tag identity {key}")
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
        replacements.append((database_row, label, description, str(confidence), reason))

    changed = 0
    provenance_updated = 0
    for database_row, label, description, confidence, reason in replacements:
        current_terminology = (
            database_row["label_ru"], database_row["description_ru"], database_row["confidence"],
            database_row["review_reason"],
        )
        approved_terminology = (label, description, confidence, reason)
        same_authority = database_row["translation_source"] == "approved_workbook"
        same_provenance = (
            same_authority
            and database_row["translation_source_sha256"] == source_sha256
            and database_row["translation_source_path"] == source_path
        )
        if current_terminology == approved_terminology and same_provenance:
            continue
        if current_terminology == approved_terminology and same_authority:
            connection.execute(
                """UPDATE jitendex_tag SET
                  translation_source_sha256=?,translation_source_path=?,approved_at=CURRENT_TIMESTAMP
                WHERE id=?""",
                (source_sha256, source_path, database_row["id"]),
            )
            provenance_updated += 1
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
        "provenance_updated": provenance_updated,
    })
    return {
        "snapshot_id": snapshot_id,
        "rows_reconciled": len(replacements),
        "rows_replaced": changed,
        "rows_provenance_updated": provenance_updated,
        "source_sha256": source_sha256,
    }


def translated_tag_notes(connection: ConnectionLike, snapshot_id: int) -> dict[str, str]:
    rows = connection.execute(
        """SELECT description_en,description_ru FROM jitendex_tag
        WHERE snapshot_id=? AND source_kind='tag_bank' ORDER BY id""", (snapshot_id,),
    ).fetchall()
    missing = [row["description_en"] for row in rows if not row["description_ru"]]
    if missing:
        raise ValueError(f"{len(missing)} Jitendex tag-bank descriptions lack Russian translations")
    return {row["description_en"]: row["description_ru"] for row in rows}
