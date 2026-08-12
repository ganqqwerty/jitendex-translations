from __future__ import annotations

import json
import re
import sqlite3
import zipfile
from pathlib import Path
from typing import Any, Iterator

from .apply_translations import apply_article
from .db import audit
from .util import canonical_json, sha256_bytes, sha256_file


MEDIA_SUFFIXES = {".avif", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp3", ".ogg"}
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def _rank_label(limit: int) -> str:
    return f"{limit // 1000}k" if limit % 1000 == 0 else str(limit)


def _frequency_metadata(connection: sqlite3.Connection, run_id: int) -> tuple[str, str, str] | None:
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


def build(
    connection: sqlite3.Connection, run_id: int, output: Path,
    tag_notes: dict[str, str] | None = None,
) -> dict[str, Any]:
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
        """SELECT a.* FROM run_article ra JOIN article a ON a.id=ra.article_id
        WHERE ra.run_id=? ORDER BY a.bank_number,a.entry_ordinal""", (run_id,)
    ).fetchall()
    rows = [apply_article(connection, run_id, article) for article in articles]
    if not rows:
        raise ValueError("selection is empty")
    media = sorted({path for row in rows for path in _paths(row)})
    files: dict[str, bytes] = {}
    with zipfile.ZipFile(source_row["local_path"]) as source:
        index = json.loads(source.read("index.json"))
        frequency_metadata = _frequency_metadata(connection, run_id)
        index["title"] = frequency_metadata[0] if frequency_metadata else "Jitendex Kaishi 1.5k — русский"
        suffix = frequency_metadata[1] if frequency_metadata else (
            "kaishi-ru-lexicographer-v2" if run["pipeline_version"] == "lexicographer-v2" else "kaishi-ru-v1"
        )
        index["revision"] = f"{index.get('revision', '')}-{suffix}"
        index["targetLanguage"] = "ru"
        index["description"] = (
            frequency_metadata[2]
            if frequency_metadata else
            "Производный русскоязычный словарь на основе Jitendex; выбор статей ограничен лексикой Kaishi 1.5k. "
            "Jitendex/JMdict/Tatoeba attribution and CC BY-SA 4.0 terms are retained. No affiliation with Kaishi."
        )
        files["index.json"] = canonical_json(index)
        if "styles.css" in source.namelist():
            files["styles.css"] = source.read("styles.css")
        for name in source.namelist():
            if re.fullmatch(r"tag_bank_\d+\.json", name):
                tag_rows = json.loads(source.read(name))
                localized = []
                for row in tag_rows:
                    if not isinstance(row, list) or len(row) < 4 or not isinstance(row[3], str):
                        raise ValueError(f"invalid tag row in {name}")
                    translated = (tag_notes or {}).get(row[3])
                    if row[3] and translated is None:
                        raise ValueError(f"missing Russian tag note for {row[3]!r}")
                    localized.append([*row[:3], translated or row[3], *row[4:]])
                files[name] = canonical_json(localized)
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
        "INSERT INTO export(run_id,output_path,manifest_sha256,zip_sha256) VALUES (?,?,?,?)",
        (run_id, str(output), manifest_hash, zip_hash),
    )
    export_id = cursor.lastrowid
    connection.executemany(
        "INSERT INTO export_file(export_id,path,sha256,byte_count) VALUES (?,?,?,?)",
        ((export_id, item["path"], item["sha256"], item["bytes"]) for item in manifest),
    )
    audit(connection, "build", "export", export_id, {"output": str(output), "zip_sha256": zip_hash})
    return {"export_id": export_id, "files": len(files), "articles": len(rows), "zip_sha256": zip_hash}


def verify(connection: sqlite3.Connection, path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if not names or names[0] != "index.json":
            raise ValueError("index.json is not the first root member")
        if len(names) != len(set(names)):
            raise ValueError("duplicate ZIP members")
        index = json.loads(archive.read("index.json"))
        if index.get("targetLanguage") != "ru":
            raise ValueError("targetLanguage is not ru")
        term_names = sorted((name for name in names if re.fullmatch(r"term_bank_\d+\.json", name)), key=lambda name: int(re.search(r"\d+", name)[0]))
        article_count = 0
        missing_media: set[str] = set()
        for name in term_names:
            rows = json.loads(archive.read(name))
            article_count += len(rows)
            for row in rows:
                missing_media.update(path for path in _paths(row) if path not in names)
        if missing_media:
            raise ValueError(f"missing media: {sorted(missing_media)}")
    export = connection.execute(
        "SELECT run_id FROM export WHERE output_path=? AND zip_sha256=? ORDER BY id DESC LIMIT 1",
        (str(path), sha256_file(path)),
    ).fetchone()
    if export is None:
        raise ValueError("archive has no matching export record")
    expected = connection.execute("SELECT COUNT(*) FROM run_article WHERE run_id=?", (export["run_id"],)).fetchone()[0]
    if article_count != expected:
        raise ValueError(f"expected {expected} articles, found {article_count}")
    zip_hash = sha256_file(path)
    connection.execute("UPDATE export SET verified=1 WHERE output_path=? AND zip_sha256=?", (str(path), zip_hash))
    return {"verified": True, "articles": article_count, "files": len(names), "zip_sha256": zip_hash}


YOMITAN_SMOKE_CHECKS = {
    "expression_lookup", "reading_lookup", "inflected_lookup", "kana_only_lookup",
    "multiple_readings", "xrefs", "ruby", "examples", "tables", "links", "long_entry",
}


def record_yomitan_smoke(connection: sqlite3.Connection, path: Path, actor: str) -> dict[str, Any]:
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
