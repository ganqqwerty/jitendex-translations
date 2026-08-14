from __future__ import annotations

from .database import ConnectionLike, RowLike

import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .db import audit
from .util import nfc, sha256_file


PARSER_VERSION = "combined-frequency-v1"
EXTERNAL_SOURCES = (
    "aozora_bunko",
    "bccwj",
    "cc100",
    "monodicts_206k",
    "wikipedia_v2",
    "kokugo_jiten",
)


@dataclass(frozen=True)
class FrequencySpec:
    source: str
    path: Path
    limit: int
    rank_mode: str


def _bank_names(archive: zipfile.ZipFile) -> list[str]:
    pattern = re.compile(r"^term_meta_bank_(\d+)\.json$")
    names: list[tuple[int, str]] = []
    for name in archive.namelist():
        match = pattern.fullmatch(name)
        if match:
            names.append((int(match.group(1)), name))
    return [name for _, name in sorted(names)]


def _rank(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, dict):
        for key in ("frequency", "value"):
            rank = value.get(key)
            if isinstance(rank, (int, float)) and not isinstance(rank, bool):
                return int(rank)
    return None


def _load_terms(spec: FrequencySpec) -> tuple[list[tuple[int, str]], dict[str, Any]]:
    if spec.limit < 1:
        raise ValueError(f"{spec.source} limit must be positive")
    best_ranks: dict[str, int] = {}
    with zipfile.ZipFile(spec.path) as archive:
        try:
            index = json.loads(archive.read("index.json"))
        except KeyError:
            index = {}
        names = _bank_names(archive)
        if not names:
            raise ValueError(f"{spec.source} archive has no term_meta_bank_N.json")
        rows = [row for name in names for row in json.loads(archive.read(name))]

    if spec.rank_mode == "row_order":
        if len(rows) < spec.limit:
            raise ValueError(f"{spec.source} archive has fewer than {spec.limit} frequency rows")
        candidates: Iterable[tuple[int, Any]] = enumerate(rows[: spec.limit], 1)
    elif spec.rank_mode == "recorded":
        candidates = ((_rank(row[2]) if isinstance(row, list) and len(row) >= 3 else None, row) for row in rows)
    else:
        raise ValueError(f"unsupported rank mode for {spec.source}: {spec.rank_mode}")

    for rank, row in candidates:
        if rank is None or rank < 1 or rank > spec.limit:
            continue
        if not isinstance(row, list) or len(row) < 3 or row[1] != "freq" or not isinstance(row[0], str):
            raise ValueError(f"invalid {spec.source} frequency row at rank {rank}")
        term = nfc(row[0])
        if not term:
            raise ValueError(f"empty {spec.source} frequency term at rank {rank}")
        best_ranks[term] = min(rank, best_ranks.get(term, rank))

    ranked = sorted(((rank, term) for term, rank in best_ranks.items()), key=lambda item: (item[0], item[1]))
    if not ranked:
        raise ValueError(f"{spec.source} rank scope is empty")
    return ranked, {
        "title": index.get("title"),
        "revision": index.get("revision"),
        "records_total": len(rows),
        "rank_mode": spec.rank_mode,
    }


def select_combined_scope(
    connection: ConnectionLike,
    jpdb_path: Path,
    jpdb_limit: int,
    frequency_paths: dict[str, Path],
    frequency_limit: int,
) -> dict[str, Any]:
    missing = set(EXTERNAL_SOURCES) - set(frequency_paths)
    extra = set(frequency_paths) - set(EXTERNAL_SOURCES)
    if missing or extra:
        raise ValueError(f"frequency source mismatch: missing={sorted(missing)}, extra={sorted(extra)}")
    specs = [FrequencySpec("jpdb", jpdb_path, jpdb_limit, "row_order")]
    specs.extend(
        FrequencySpec(source, frequency_paths[source], frequency_limit, "recorded")
        for source in EXTERNAL_SOURCES
    )

    loaded: list[tuple[FrequencySpec, str, list[tuple[int, str]], dict[str, Any]]] = []
    for spec in specs:
        path = spec.path.resolve()
        if not path.is_file():
            raise ValueError(f"missing frequency archive for {spec.source}: {path}")
        resolved = FrequencySpec(spec.source, path, spec.limit, spec.rank_mode)
        terms, metadata = _load_terms(resolved)
        loaded.append((resolved, sha256_file(path), terms, metadata))

    expression_index: dict[str, list[int]] = {}
    reading_index: dict[str, list[int]] = {}
    for article in connection.execute("SELECT id,expression,reading FROM article ORDER BY id"):
        expression_index.setdefault(nfc(article["expression"]), []).append(article["id"])
        reading_index.setdefault(nfc(article["reading"]), []).append(article["id"])

    connection.execute("UPDATE article SET selected=0")
    connection.execute("DELETE FROM frequency_article")
    connection.execute("DELETE FROM frequency_term")
    connection.execute("DELETE FROM frequency_source")

    source_results: list[dict[str, Any]] = []
    union_terms: set[str] = set()
    union_matched_terms: set[str] = set()
    selected_articles: set[int] = set()
    for spec, archive_hash, terms, metadata in loaded:
        connection.execute(
            """INSERT INTO frequency_source
            (source,source_sha256,rank_limit,local_path,title,revision,parser_version,metadata_json)
            VALUES (?,?,?,?,?,?,?,?)""",
            (
                spec.source, archive_hash, spec.limit, str(spec.path), metadata["title"], metadata["revision"],
                PARSER_VERSION, json.dumps(metadata, ensure_ascii=False, sort_keys=True),
            ),
        )
        connection.executemany(
            "INSERT INTO frequency_term(source,source_sha256,rank,term) VALUES (?,?,?,?)",
            ((spec.source, archive_hash, rank, term) for rank, term in terms),
        )
        mappings: list[tuple[str, str, int, str, int, str]] = []
        matched_terms: set[str] = set()
        expression_matches = 0
        reading_matches = 0
        for rank, term in terms:
            matches: dict[int, str] = {}
            for article_id in expression_index.get(term, []):
                matches[article_id] = "expression"
            for article_id in reading_index.get(term, []):
                matches.setdefault(article_id, "reading")
            if matches:
                matched_terms.add(term)
            for article_id, match_kind in matches.items():
                mappings.append((spec.source, archive_hash, rank, term, article_id, match_kind))
                selected_articles.add(article_id)
                expression_matches += match_kind == "expression"
                reading_matches += match_kind == "reading"
        connection.executemany(
            "UPDATE frequency_term SET matched=1 WHERE source=? AND source_sha256=? AND term=?",
            ((spec.source, archive_hash, term) for term in matched_terms),
        )
        connection.executemany(
            """INSERT INTO frequency_article
            (source,source_sha256,rank,term,article_id,match_kind) VALUES (?,?,?,?,?,?)""",
            mappings,
        )
        source_results.append({
            "source": spec.source,
            "source_sha256": archive_hash,
            "rank_limit": spec.limit,
            "unique_terms": len(terms),
            "matched_terms": len(matched_terms),
            "skipped_terms": len(terms) - len(matched_terms),
            "article_mappings": len(mappings),
            "expression_matches": expression_matches,
            "reading_matches": reading_matches,
        })
        source_terms = {term for _, term in terms}
        union_terms.update(source_terms)
        union_matched_terms.update(matched_terms)

    connection.executemany("UPDATE article SET selected=1 WHERE id=?", ((item,) for item in selected_articles))
    result = {
        "parser_version": PARSER_VERSION,
        "jpdb_limit": jpdb_limit,
        "frequency_limit": frequency_limit,
        "sources": source_results,
        "six_frequency_union_terms": len({
            term
            for spec, _, terms, _ in loaded
            if spec.source != "jpdb"
            for _, term in terms
        }),
        "combined_union_terms": len(union_terms),
        "combined_matched_terms": len(union_matched_terms),
        "combined_skipped_terms": len(union_terms - union_matched_terms),
        "selected_articles": len(selected_articles),
    }
    audit(connection, "select_combined_frequency_scope", "frequency_scope", PARSER_VERSION, result)
    return result


def combined_coverage_report(connection: ConnectionLike, run_id: int) -> dict[str, Any]:
    if connection.execute("SELECT 1 FROM run WHERE id=?", (run_id,)).fetchone() is None:
        raise ValueError(f"unknown run {run_id}")
    sources = connection.execute("SELECT * FROM frequency_source ORDER BY source").fetchall()
    if not sources:
        raise ValueError("combined frequency scope has not been selected")

    source_results = []
    for source in sources:
        counts = connection.execute(
            """SELECT COUNT(*) terms,SUM(matched) matched_terms
            FROM frequency_term WHERE source=? AND source_sha256=?""",
            (source["source"], source["source_sha256"]),
        ).fetchone()
        terms = int(counts["terms"])
        matched = int(counts["matched_terms"] or 0)
        covered = connection.execute(
            """SELECT COUNT(*) FROM frequency_term ft
            WHERE ft.source=? AND ft.source_sha256=? AND ft.matched=1
              AND NOT EXISTS (
                SELECT 1 FROM frequency_article fa
                WHERE fa.source=ft.source AND fa.source_sha256=ft.source_sha256 AND fa.term=ft.term
                  AND NOT EXISTS (
                    SELECT 1 FROM run_article ra WHERE ra.run_id=? AND ra.article_id=fa.article_id
                  )
              )""",
            (source["source"], source["source_sha256"], run_id),
        ).fetchone()[0]
        source_results.append({
            "source": source["source"],
            "source_sha256": source["source_sha256"],
            "rank_limit": source["rank_limit"],
            "unique_terms": terms,
            "matched_terms": matched,
            "skipped_terms": terms - matched,
            "covered_terms": covered,
        })

    union = connection.execute(
        """SELECT COUNT(DISTINCT term) terms,
        COUNT(DISTINCT CASE WHEN matched=1 THEN term END) matched_terms
        FROM frequency_term"""
    ).fetchone()
    six_union = connection.execute(
        "SELECT COUNT(DISTINCT term) FROM frequency_term WHERE source<>'jpdb'"
    ).fetchone()[0]
    mapped_articles = connection.execute("SELECT COUNT(DISTINCT article_id) FROM frequency_article").fetchone()[0]
    missing_mapped_articles = connection.execute(
        """SELECT COUNT(DISTINCT fa.article_id) FROM frequency_article fa
        WHERE NOT EXISTS (
          SELECT 1 FROM run_article ra WHERE ra.run_id=? AND ra.article_id=fa.article_id
        )""",
        (run_id,),
    ).fetchone()[0]
    selected_articles = connection.execute("SELECT COUNT(*) FROM run_article WHERE run_id=?", (run_id,)).fetchone()[0]
    fully_accepted_articles = connection.execute(
        """SELECT COUNT(*) FROM run_article ra WHERE ra.run_id=? AND NOT EXISTS (
          SELECT 1 FROM translation_unit tu WHERE tu.run_id=ra.run_id AND tu.article_id=ra.article_id
          AND NOT EXISTS (
            SELECT 1 FROM translation t
            WHERE t.run_id=tu.run_id AND t.unit_id=tu.id AND t.accepted=1
          )
        )""",
        (run_id,),
    ).fetchone()[0]
    matched_terms = union["matched_terms"] or 0
    complete = (
        all(item["covered_terms"] == item["matched_terms"] for item in source_results)
        and missing_mapped_articles == 0
        and fully_accepted_articles == selected_articles
    )
    return {
        "run_id": run_id,
        "sources": source_results,
        "six_frequency_union_terms": six_union,
        "combined_union_terms": union["terms"],
        "combined_matched_terms": matched_terms,
        "combined_skipped_terms": union["terms"] - matched_terms,
        "mapped_articles": mapped_articles,
        "missing_mapped_articles": missing_mapped_articles,
        "selected_articles": selected_articles,
        "fully_accepted_articles": fully_accepted_articles,
        "complete": complete,
    }
