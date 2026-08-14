from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence


TABLES = (
    "schema_meta", "source_snapshot", "kaishi_note", "article",
    "selection_candidate", "selection_decision", "run", "translation_unit",
    "batch", "batch_item", "attempt", "translation", "review",
    "validation_issue", "audit_event", "export", "export_file", "run_article",
    "attempt_cost_report", "jitendex_tag", "jitendex_tag_translation_history",
    "frequency_source", "frequency_term", "frequency_article",
    "translation_canonicalization_history",
)
OPTIONAL_TABLES = ("benchmark_marker",)

IDENTITY_TABLES = (
    "source_snapshot", "kaishi_note", "article", "selection_candidate",
    "selection_decision", "run", "translation", "review", "validation_issue",
    "audit_event", "export", "attempt_cost_report", "jitendex_tag",
    "jitendex_tag_translation_history", "translation_canonicalization_history",
)

TERMINAL_BATCH_STATES = ("deterministic_validated", "accepted", "superseded")


def sqlite_readonly(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise ValueError(f"SQLite source does not exist: {path}")
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def source_safety(connection: Any) -> dict[str, int]:
    claimed = connection.execute(
        "SELECT COUNT(*) FROM attempt WHERE outcome='claimed'"
    ).fetchone()[0]
    unfinished = connection.execute(
        "SELECT COUNT(*) FROM batch WHERE state IN ('ready','leased','retryable')",
    ).fetchone()[0]
    terminal_blocked = connection.execute(
        """SELECT COUNT(*) FROM batch b WHERE b.state='blocked' AND NOT EXISTS (
        SELECT 1 FROM audit_event ae WHERE ae.entity_type='batch'
          AND ae.entity_id=b.id AND ae.event_type='split')"""
    ).fetchone()[0]
    blocking = connection.execute(
        """SELECT COUNT(*) FROM validation_issue
        WHERE severity IN ('blocking','error') AND resolved_at IS NULL"""
    ).fetchone()[0]
    latest_run = connection.execute("SELECT MAX(id) FROM run").fetchone()[0]
    unaccepted = 0
    verified_exports = 0
    if latest_run is not None:
        unaccepted = connection.execute(
            """SELECT COUNT(*) FROM translation_unit tu WHERE tu.run_id=? AND NOT EXISTS (
            SELECT 1 FROM translation t WHERE t.run_id=tu.run_id AND t.unit_id=tu.id AND t.accepted=1)""",
            (latest_run,),
        ).fetchone()[0]
        verified_exports = connection.execute(
            "SELECT COUNT(*) FROM export WHERE run_id=? AND verified=1", (latest_run,),
        ).fetchone()[0]
    return {"claimed_attempts": claimed, "unfinished_batches": unfinished,
            "terminal_blocked_leaves": terminal_blocked,
            "blocking_errors": blocking, "latest_run_id": latest_run or 0,
            "unaccepted_units": unaccepted, "verified_exports": verified_exports}


def require_migration_safe(connection: Any, *, disposable_test: bool) -> dict[str, int]:
    state = source_safety(connection)
    if state["claimed_attempts"]:
        raise RuntimeError("source has claimed attempts; stop all writers before migration")
    if not disposable_test and (
        state["unfinished_batches"] or state["terminal_blocked_leaves"] or state["blocking_errors"]
        or state["unaccepted_units"] or (state["latest_run_id"] and not state["verified_exports"])
    ):
        raise RuntimeError(
            "source has unfinished production work; only --disposable-test-source may bypass this gate"
        )
    return state


def table_columns(connection: Any, table: str, *, backend: str) -> list[str]:
    if backend == "sqlite":
        return [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]
    return [row[0] for row in connection.execute(
        """SELECT column_name FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position""",
        (table,),
    )]


def utc_timestamp(value: Any) -> Any:
    if value is None or isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise ValueError(f"invalid timestamp type: {type(value).__name__}")
    text = value.strip()
    if not text:
        raise ValueError("empty timestamp")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalized_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, memoryview):
        return bytes(value).hex()
    return value


def normalized_table_hash(rows: Iterable[Sequence[Any]]) -> str:
    # A commutative multiset digest keeps verification streaming while avoiding
    # backend collation differences in ORDER BY for Japanese text.  Sum, xor,
    # and count together retain duplicate-row sensitivity.
    modulus = 1 << 256
    total = 0
    xor = 0
    count = 0
    for row in rows:
        line = json.dumps([normalized_value(value) for value in row], ensure_ascii=False,
                          separators=(",", ":"), sort_keys=True)
        value = int.from_bytes(hashlib.sha256(line.encode("utf-8")).digest(), "big")
        total = (total + value) % modulus
        xor ^= value
        count += 1
    payload = count.to_bytes(16, "big") + total.to_bytes(32, "big") + xor.to_bytes(32, "big")
    return hashlib.sha256(payload).hexdigest()


def primary_key_columns(connection: Any, table: str, *, backend: str) -> list[str]:
    if backend == "sqlite":
        return [
            row[1] for row in sorted(
                connection.execute(f'PRAGMA table_info("{table}")'), key=lambda row: row[5],
            ) if row[5]
        ]
    return [row[0] for row in connection.execute(
        """SELECT a.attname FROM pg_index i
        JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=ANY(i.indkey)
        WHERE i.indrelid=%s::regclass AND i.indisprimary
        ORDER BY array_position(i.indkey,a.attnum)""",
        (table,),
    )]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_hash(payload: Any) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()
