from __future__ import annotations

import sqlite3
from typing import Any

from .util import canonical_json, sha256_bytes


EXPECTED_LEXICOGRAPHER_V2_ROLES = {
    "tooltip": 8992,
    "glossary_set": 5580,
    "pos": 4172,
    "example": 3176,
    "note": 1784,
    "xref_gloss": 1650,
    "register": 1108,
    "label": 1056,
}


def source_identity_report(
    connection: sqlite3.Connection, candidate_run_id: int, baseline_run_id: int = 2,
) -> dict[str, Any]:
    """Compare a new run with the immutable source-unit identity of a baseline run."""
    for run_id in (candidate_run_id, baseline_run_id):
        if connection.execute("SELECT 1 FROM run WHERE id=?", (run_id,)).fetchone() is None:
            raise ValueError(f"unknown run {run_id}")
    articles, units = connection.execute(
        "SELECT COUNT(DISTINCT article_id),COUNT(*) FROM translation_unit WHERE run_id=?",
        (candidate_run_id,),
    ).fetchone()
    roles = {
        row["role"]: row["units"]
        for row in connection.execute(
            "SELECT role,COUNT(*) units FROM translation_unit WHERE run_id=? GROUP BY role ORDER BY role",
            (candidate_run_id,),
        )
    }
    key_sql = "SELECT article_id,json_pointer,role,source_sha256 FROM translation_unit WHERE run_id=?"
    missing = connection.execute(
        f"SELECT COUNT(*) FROM ({key_sql} EXCEPT {key_sql})",
        (baseline_run_id, candidate_run_id),
    ).fetchone()[0]
    extra = connection.execute(
        f"SELECT COUNT(*) FROM ({key_sql} EXCEPT {key_sql})",
        (candidate_run_id, baseline_run_id),
    ).fetchone()[0]
    passed = (
        articles == 1704
        and units == 27518
        and roles == EXPECTED_LEXICOGRAPHER_V2_ROLES
        and missing == 0
        and extra == 0
    )
    return {
        "candidate_run_id": candidate_run_id,
        "baseline_run_id": baseline_run_id,
        "articles": articles,
        "units": units,
        "roles": roles,
        "missing_from_candidate": missing,
        "extra_in_candidate": extra,
        "passed": passed,
    }


def run_history_fingerprint(connection: sqlite3.Connection, run_id: int) -> dict[str, Any]:
    """Hash every row owned by a run without including unrelated database state."""
    queries = {
        "run": ("SELECT * FROM run WHERE id=? ORDER BY id", (run_id,)),
        "translation_unit": ("SELECT * FROM translation_unit WHERE run_id=? ORDER BY id", (run_id,)),
        "run_article": ("SELECT * FROM run_article WHERE run_id=? ORDER BY article_id", (run_id,)),
        "batch": ("SELECT * FROM batch WHERE run_id=? ORDER BY id", (run_id,)),
        "batch_item": (
            "SELECT bi.* FROM batch_item bi JOIN batch b ON b.id=bi.batch_id WHERE b.run_id=? ORDER BY bi.batch_id,bi.ordinal",
            (run_id,),
        ),
        "attempt": (
            "SELECT a.* FROM attempt a JOIN batch b ON b.id=a.batch_id WHERE b.run_id=? ORDER BY a.id",
            (run_id,),
        ),
        "translation": ("SELECT * FROM translation WHERE run_id=? ORDER BY id", (run_id,)),
        "review": (
            "SELECT r.* FROM review r JOIN translation t ON t.id=r.translation_id WHERE t.run_id=? ORDER BY r.id",
            (run_id,),
        ),
        "validation_issue": ("SELECT * FROM validation_issue WHERE run_id=? ORDER BY id", (run_id,)),
        "export": ("SELECT * FROM export WHERE run_id=? ORDER BY id", (run_id,)),
        "export_file": (
            "SELECT ef.* FROM export_file ef JOIN export e ON e.id=ef.export_id WHERE e.run_id=? ORDER BY ef.export_id,ef.path",
            (run_id,),
        ),
    }
    tables: dict[str, dict[str, Any]] = {}
    for table, (sql, parameters) in queries.items():
        rows = [dict(row) for row in connection.execute(sql, parameters)]
        tables[table] = {"rows": len(rows), "sha256": sha256_bytes(canonical_json(rows))}
    return {
        "run_id": run_id,
        "tables": tables,
        "sha256": sha256_bytes(canonical_json(tables)),
    }
