from __future__ import annotations

from .database import ConnectionLike, RowLike

import json
import re
import zipfile
from pathlib import Path
from typing import Any, Iterator

from .apply_translations import apply_article
from .attribution import (
    DICTIONARY_VERSION, PRODUCT_ID, PRODUCT_NAME,
    VERSIONED_PRODUCT_ID, VERSIONED_PRODUCT_NAME, release_description,
)
from .db import audit
from .jitendex_tags import (
    TAG_CATALOG_VERSION, load_approved_tag_catalog, localize_embedded_tags,
    localize_tag_bank_rows, localize_term_tag_references,
    verify_localized_embedded_tags, verify_localized_tag_bank_rows,
    verify_localized_term_tag_references,
)
from .util import canonical_json, sha256_bytes, sha256_file
from .yomitan_remediation import (
    YOMITAN_TITLE, build_yomitan_index, localize_yomitan_rows,
    scan_yomitan_rows, validate_yomitan_metadata, yomitan_revision,
)
from .yomitan_audit import verify_yomitan_visible_latin_approval


MEDIA_SUFFIXES = {".avif", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp3", ".ogg"}
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def _rank_label(limit: int) -> str:
    return f"{limit // 1000}k" if limit % 1000 == 0 else str(limit)


def _frequency_metadata(connection: ConnectionLike, run_id: int) -> tuple[str, str, str] | None:
    run_articles = connection.execute(
        "SELECT COUNT(*) FROM run_article WHERE run_id=?", (run_id,),
    ).fetchone()[0]
    mapped_articles = connection.execute(
        """SELECT COUNT(DISTINCT fa.article_id) FROM frequency_article fa
        JOIN run_article ra ON ra.article_id=fa.article_id AND ra.run_id=?""", (run_id,),
    ).fetchone()[0]
    if run_articles > mapped_articles:
        total_articles = connection.execute(
            """SELECT COUNT(*) FROM article WHERE snapshot_id=(
              SELECT jitendex_snapshot_id FROM run WHERE id=?)""", (run_id,),
        ).fetchone()[0]
        complete = run_articles == total_articles
        label = VERSIONED_PRODUCT_NAME if complete else f"{VERSIONED_PRODUCT_NAME} — {run_articles:,} статей".replace(",", " ")
        suffix = VERSIONED_PRODUCT_ID if complete else f"{PRODUCT_ID}-articles-{run_articles}-v{DICTIONARY_VERSION}"
        description = (
            f"{PRODUCT_NAME} — полный производный русскоязычный словарь на основе Jitendex. "
            if complete else
            f"{PRODUCT_NAME} — производный русскоязычный словарь на основе Jitendex; кумулятивная выборка содержит {run_articles:,} статей. "
        )
        return (
            label,
            suffix,
            description + "Атрибуция Jitendex/JMdict/Tatoeba и условия CC BY-SA 4.0 сохранены.",
        )
    mapped = connection.execute(
        """SELECT DISTINCT fs.source,fs.rank_limit FROM frequency_source fs
        JOIN frequency_article fa ON fa.source=fs.source AND fa.source_sha256=fs.source_sha256
        JOIN run_article ra ON ra.article_id=fa.article_id AND ra.run_id=?
        ORDER BY fs.source""",
        (run_id,),
    ).fetchall()
    if not mapped:
        return None
    limits = {row["source"]: row["rank_limit"] for row in mapped}
    jpdb_limit = limits.get("jpdb")
    external_limits = {limit for source, limit in limits.items() if source != "jpdb"}
    if jpdb_limit is not None and external_limits:
        if len(external_limits) != 1:
            raise ValueError("combined frequency sources have inconsistent rank limits")
        external_limit = next(iter(external_limits))
        jpdb_label = _rank_label(jpdb_limit)
        external_label = _rank_label(external_limit)
        return (
            f"Jitendex JPDB {jpdb_label} + frequency-six top{external_label} — русский",
            f"jpdb-{jpdb_label}-freq6-{external_label}-ru",
            "Производный русскоязычный словарь на основе Jitendex; выбор статей объединяет "
            f"JPDB 1–{jpdb_limit:,} и верхние {external_limit:,} рангов шести частотных словарей. "
            "Атрибуция Jitendex/JMdict/Tatoeba и условия CC BY-SA 4.0 сохранены.",
        )
    if jpdb_limit is not None:
        jpdb_label = _rank_label(jpdb_limit)
        return (
            f"Jitendex JPDB {jpdb_label} — русский",
            f"jpdb-{jpdb_label}-ru",
            "Производный русскоязычный словарь на основе Jitendex; выбор статей соответствует "
            f"верхним {jpdb_limit:,} строкам JPDB. Атрибуция Jitendex/JMdict/Tatoeba и условия "
            "CC BY-SA 4.0 сохранены.",
        )
    return None


def _paths(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in {"path", "src"} and isinstance(value, str) and Path(value).suffix.lower() in MEDIA_SUFFIXES:
                yield value
            else:
                yield from _paths(value)
    elif isinstance(node, list):
        for item in node:
            yield from _paths(item)


def _write_member(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, data, compresslevel=9)


def _chunk(rows: list[list[Any]], max_bytes: int = 4 * 1024 * 1024) -> list[list[list[Any]]]:
    chunks: list[list[list[Any]]] = []
    current: list[list[Any]] = []
    current_bytes = 2  # JSON array brackets.
    for row in rows:
        row_bytes = len(canonical_json(row))
        separator_bytes = 1 if current else 0
        if current and current_bytes + separator_bytes + row_bytes > max_bytes:
            chunks.append(current)
            current = [row]
            current_bytes = 2 + row_bytes
        else:
            current.append(row)
            current_bytes += separator_bytes + row_bytes
    if current:
        chunks.append(current)
    return chunks


def materialize_run(
    connection: ConnectionLike, run_id: int,
) -> tuple[RowLike, RowLike, list[list[Any]]]:
    """Apply every accepted translation and return run, source, and articles."""
    run = connection.execute("SELECT * FROM run WHERE id=?", (run_id,)).fetchone()
    if run is None:
        raise ValueError(f"unknown run {run_id}")
    blocking = connection.execute(
        "SELECT COUNT(*) FROM validation_issue WHERE run_id=? AND severity='error' AND resolved_at IS NULL", (run_id,)
    ).fetchone()[0]
    if blocking:
        raise ValueError(f"run has {blocking} unresolved blocking issues")
    source_row = connection.execute(
        """SELECT ss.* FROM run r JOIN source_snapshot ss ON ss.id=r.jitendex_snapshot_id
        WHERE r.id=? AND ss.kind='jitendex'""", (run_id,)
    ).fetchone()
    if source_row is None:
        raise ValueError("no Jitendex source snapshot")
    articles = connection.execute(
        """SELECT a.*,ra.structural_fingerprint run_structural_fingerprint
        FROM run_article ra JOIN article a ON a.id=ra.article_id
        WHERE ra.run_id=? ORDER BY a.bank_number,a.entry_ordinal""", (run_id,)
    ).fetchall()
    unit_rows = connection.execute(
        """SELECT tu.article_id,tu.json_pointer,tu.role,tu.source_text,
        t.id translation_id,t.target_text,t.target_sha256
        FROM translation_unit tu
        LEFT JOIN translation t ON t.unit_id=tu.id AND t.accepted=1
        WHERE tu.run_id=? ORDER BY tu.article_id,tu.json_pointer""", (run_id,),
    ).fetchall()
    units_by_article: dict[int, list[Any]] = {}
    for unit_row in unit_rows:
        units_by_article.setdefault(unit_row["article_id"], []).append(unit_row)
    rows = [apply_article(connection, run_id, article, units_by_article.get(article["id"], [])) for article in articles]
    if not rows:
        raise ValueError("selection is empty")
    return run, source_row, rows


def build(
    connection: ConnectionLike, run_id: int, output: Path, *, updatable: bool = False,
) -> dict[str, Any]:
    run, source_row, rows = materialize_run(connection, run_id)
    localization = localize_yomitan_rows(rows)
    catalog = load_approved_tag_catalog(connection, run["jitendex_snapshot_id"])
    embedded = localize_embedded_tags(rows, catalog)
    media = sorted({path for row in rows for path in _paths(row)})
    files: dict[str, bytes] = {}
    with zipfile.ZipFile(source_row["local_path"]) as source:
        source_index = json.loads(source.read("index.json"))
        frequency_metadata = _frequency_metadata(connection, run_id)
        suffix = frequency_metadata[1] if frequency_metadata else (
            "kaishi-ru-lexicographer-v2" if run["pipeline_version"] == "lexicographer-v2" else "kaishi-ru-v1"
        )
        description = release_description(
            frequency_metadata[2]
            if frequency_metadata else
            "Производный русскоязычный словарь на основе Jitendex; выбор статей ограничен лексикой Kaishi 1.5k. "
            "Jitendex/JMdict/Tatoeba attribution and CC BY-SA 4.0 terms are retained. No affiliation with Kaishi."
        )
        index = build_yomitan_index(
            source_index,
            description=description,
            revision=f"{yomitan_revision(suffix)}-{TAG_CATALOG_VERSION}",
            updatable=updatable,
        )
        files["index.json"] = canonical_json(index)
        if "styles.css" in source.namelist():
            files["styles.css"] = source.read("styles.css")
        tag_bank_names = sorted(
            (name for name in source.namelist() if re.fullmatch(r"tag_bank_\d+\.json", name)),
            key=lambda name: int(re.search(r"\d+", name)[0]),
        )
        source_tag_banks = {name: json.loads(source.read(name)) for name in tag_bank_names}
        tag_bank_rows = [row for name in tag_bank_names for row in source_tag_banks[name]]
        localized_tag_rows, tag_mapping = localize_tag_bank_rows(tag_bank_rows, catalog)
        offset = 0
        for name in tag_bank_names:
            size = len(source_tag_banks[name])
            files[name] = canonical_json(localized_tag_rows[offset:offset + size])
            offset += size
        tag_references = localize_term_tag_references(rows, tag_mapping)
        for path in media:
            if path not in source.namelist():
                raise ValueError(f"missing referenced media {path}")
            files[path] = source.read(path)
    for number, chunk in enumerate(_chunk(rows), 1):
        files[f"term_bank_{number}.json"] = canonical_json(chunk)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w") as archive:
        for name in sorted(files, key=lambda item: (item != "index.json", item)):
            _write_member(archive, name, files[name])
    manifest = [{"path": name, "sha256": sha256_bytes(data), "bytes": len(data)} for name, data in sorted(files.items())]
    manifest_hash = sha256_bytes(canonical_json(manifest))
    zip_hash = sha256_file(output)
    cursor = connection.execute(
        """INSERT INTO export(run_id,output_path,manifest_sha256,zip_sha256)
        VALUES (?,?,?,?) RETURNING id""",
        (run_id, str(output), manifest_hash, zip_hash),
    )
    export_id = cursor.fetchone()[0]
    connection.executemany(
        "INSERT INTO export_file(export_id,path,sha256,byte_count) VALUES (?,?,?,?)",
        ((export_id, item["path"], item["sha256"], item["bytes"]) for item in manifest),
    )
    tag_summary = {
        "tag_catalog_version": catalog["version"],
        "tag_catalog_sha256": catalog["source_sha256"],
        "embedded_tag_occurrences": embedded["embedded_tag_occurrences"],
        "embedded_labels_replaced": embedded["embedded_labels_replaced"],
        "embedded_tooltips_replaced": embedded["embedded_tooltips_replaced"],
        "tag_bank_rows": len(catalog["tag_bank"]),
        **tag_references,
    }
    audit(connection, "build", "export", export_id, {
        "output": str(output), "zip_sha256": zip_hash, "updatable": updatable,
        **localization, **tag_summary,
    })
    return {
        "export_id": export_id, "files": len(files), "articles": len(rows),
        "zip_sha256": zip_hash, "updatable": updatable, **localization, **tag_summary,
    }


def verify(
    connection: ConnectionLike, path: Path, *, require_updatable: bool = False,
    lexical_approval: Path | None = None,
) -> dict[str, Any]:
    zip_hash = sha256_file(path)
    export = connection.execute(
        """SELECT e.run_id,r.jitendex_snapshot_id FROM export e
        JOIN run r ON r.id=e.run_id
        WHERE e.output_path=? AND e.zip_sha256=? ORDER BY e.id DESC LIMIT 1""",
        (str(path), zip_hash),
    ).fetchone()
    if export is None:
        raise ValueError("archive has no matching export record")
    catalog = load_approved_tag_catalog(connection, export["jitendex_snapshot_id"])
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if not names or names[0] != "index.json":
            raise ValueError("index.json is not the first root member")
        if len(names) != len(set(names)):
            raise ValueError("duplicate ZIP members")
        index = json.loads(archive.read("index.json"))
        validate_yomitan_metadata(index, require_updatable=require_updatable)
        if index.get("title") != YOMITAN_TITLE:
            raise ValueError("archive title is not the stable Yomitan title")
        if not str(index.get("revision", "")).endswith(f"-{TAG_CATALOG_VERSION}"):
            raise ValueError("archive revision lacks the approved tag-catalog version")
        tag_names = sorted(
            (name for name in names if re.fullmatch(r"tag_bank_\d+\.json", name)),
            key=lambda name: int(re.search(r"\d+", name)[0]),
        )
        tag_rows = [row for name in tag_names for row in json.loads(archive.read(name))]
        tag_mapping = verify_localized_tag_bank_rows(tag_rows, catalog)
        term_names = sorted((name for name in names if re.fullmatch(r"term_bank_\d+\.json", name)), key=lambda name: int(re.search(r"\d+", name)[0]))
        article_count = 0
        embedded_tag_occurrences = 0
        tag_bank_references = 0
        missing_media: set[str] = set()
        localization_issue_counts: dict[str, int] = {}
        for name in term_names:
            rows = json.loads(archive.read(name))
            article_count += len(rows)
            embedded_tag_occurrences += verify_localized_embedded_tags(rows, catalog)[
                "embedded_tag_occurrences"
            ]
            tag_bank_references += verify_localized_term_tag_references(rows, tag_mapping)
            scan = scan_yomitan_rows(rows)
            for code, count in scan["issue_counts"].items():
                localization_issue_counts[code] = localization_issue_counts.get(code, 0) + count
            for row in rows:
                missing_media.update(path for path in _paths(row) if path not in names)
        if localization_issue_counts:
            raise ValueError(f"Yomitan localization gate failed: {localization_issue_counts}")
        if missing_media:
            raise ValueError(f"missing media: {sorted(missing_media)}")
    expected = connection.execute("SELECT COUNT(*) FROM run_article WHERE run_id=?", (export["run_id"],)).fetchone()[0]
    if article_count != expected:
        raise ValueError(f"expected {expected} articles, found {article_count}")
    connection.execute("UPDATE export SET verified=1 WHERE output_path=? AND zip_sha256=?", (str(path), zip_hash))
    result = {
        "verified": True, "articles": article_count, "files": len(names), "zip_sha256": zip_hash,
        "tag_catalog_version": catalog["version"],
        "tag_catalog_sha256": catalog["source_sha256"],
        "embedded_tag_occurrences": embedded_tag_occurrences,
        "tag_bank_rows": len(tag_mapping), "tag_bank_references": tag_bank_references,
        "localization_issue_counts": localization_issue_counts,
        "updatable": index.get("isUpdatable") is True,
    }
    if lexical_approval is not None:
        result.update(verify_yomitan_visible_latin_approval(path, lexical_approval))
    return result


YOMITAN_SMOKE_CHECKS = {
    "expression_lookup", "reading_lookup", "inflected_lookup", "kana_only_lookup",
    "multiple_readings", "xrefs", "ruby", "examples", "tables", "links", "long_entry",
    "redirect_localization", "restriction_localization", "preserved_terminology",
    "repaired_mixed_alphabet", "owned_update_upgrade", "settings_preserved", "no_jitendex",
}


def record_yomitan_smoke(connection: ConnectionLike, path: Path, actor: str) -> dict[str, Any]:
    """Persist the human-observed clean-profile import/render release gate."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if set(payload) != {"schema_version", "zip_sha256", "clean_profile", "imported", "checks", "notes"}:
        raise ValueError("unexpected Yomitan smoke-report fields")
    if payload["schema_version"] != 1 or payload["clean_profile"] is not True or payload["imported"] is not True:
        raise ValueError("Yomitan smoke report must attest a successful clean-profile import")
    checks = payload["checks"]
    if not isinstance(checks, dict) or set(checks) != YOMITAN_SMOKE_CHECKS or not all(value is True for value in checks.values()):
        raise ValueError("every required Yomitan lookup/render check must pass")
    if not isinstance(payload["notes"], str):
        raise ValueError("Yomitan smoke notes must be a string")
    export = connection.execute(
        "SELECT * FROM export WHERE zip_sha256=? AND verified=1 ORDER BY id DESC LIMIT 1",
        (payload["zip_sha256"],),
    ).fetchone()
    if export is None:
        raise ValueError("smoke report does not match a verified export")
    existing = connection.execute(
        "SELECT 1 FROM audit_event WHERE event_type='yomitan_smoke_pass' AND entity_type='export' AND entity_id=?",
        (str(export["id"]),),
    ).fetchone()
    if existing:
        return {"recorded": False, "already_recorded": True, "export_id": export["id"]}
    audit(connection, "yomitan_smoke_pass", "export", export["id"], {
        "actor": actor, "report_path": str(path), "report_sha256": sha256_file(path), **payload,
    })
    connection.execute("UPDATE run SET state='complete' WHERE id=?", (export["run_id"],))
    return {"recorded": True, "export_id": export["id"], "run_id": export["run_id"]}
