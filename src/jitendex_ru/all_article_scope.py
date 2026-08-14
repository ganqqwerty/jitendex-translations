from __future__ import annotations

from .database import ConnectionLike, RowLike

from typing import Any

from .db import audit


def select_all_article_scope(
    connection: ConnectionLike, source_run_id: int, add_articles: int = 10_000,
) -> dict[str, Any]:
    if add_articles < 1:
        raise ValueError("add_articles must be positive")
    run = connection.execute("SELECT * FROM run WHERE id=?", (source_run_id,)).fetchone()
    if run is None:
        raise ValueError(f"unknown source run {source_run_id}")
    source_ids = [row[0] for row in connection.execute(
        "SELECT article_id FROM run_article WHERE run_id=? ORDER BY article_id", (source_run_id,),
    )]
    if not source_ids:
        raise ValueError(f"source run {source_run_id} has no articles")
    next_ids = [row[0] for row in connection.execute(
        """SELECT a.id FROM article a
        WHERE a.snapshot_id=?
          AND NOT EXISTS (SELECT 1 FROM run_article ra WHERE ra.run_id=? AND ra.article_id=a.id)
        ORDER BY a.bank_number,a.entry_ordinal,a.id LIMIT ?""",
        (run["jitendex_snapshot_id"], source_run_id, add_articles),
    )]
    if not next_ids:
        raise ValueError("source run already covers every Jitendex article")
    connection.execute("UPDATE article SET selected=0")
    connection.executemany(
        "UPDATE article SET selected=1 WHERE id=? AND snapshot_id=?",
        ((article_id, run["jitendex_snapshot_id"]) for article_id in (*source_ids, *next_ids)),
    )
    selected = connection.execute("SELECT COUNT(*) FROM article WHERE selected=1").fetchone()[0]
    expected = len(source_ids) + len(next_ids)
    if selected != expected:
        raise ValueError(f"all-article selection mismatch: {selected}/{expected}")
    total = connection.execute(
        "SELECT COUNT(*) FROM article WHERE snapshot_id=?", (run["jitendex_snapshot_id"],),
    ).fetchone()[0]
    result = {
        "source_run_id": source_run_id,
        "source_articles": len(source_ids),
        "articles_added": len(next_ids),
        "selected_articles": selected,
        "total_articles": total,
        "remaining_articles": total - selected,
        "complete": selected == total,
    }
    audit(connection, "select_all_article_scope", "run", source_run_id, result)
    return result
